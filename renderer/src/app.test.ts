import {mkdtemp, rm, writeFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import request from "supertest";
import {afterEach, describe, expect, it, vi} from "vitest";

import {createRendererApp, mapRenderProgress, type RenderEngine} from "./app";
import {makeManifest, makeTimelineManifest} from "./test-fixtures";

const roots: string[] = [];

afterEach(async () => {
  vi.restoreAllMocks();
  await Promise.all(roots.splice(0).map((root) => rm(root, {recursive: true, force: true})));
});

const fixture = async () => {
  const root = await mkdtemp(join(tmpdir(), "npd-renderer-"));
  roots.push(root);
  const assetPath = join(root, "fixture.png");
  const manifestPath = join(root, "video-manifest.json");
  await writeFile(assetPath, Buffer.from("png fixture"));
  const manifest = makeManifest(assetPath);
  manifest.brand.logo_uri = assetPath;
  manifest.voice = {audio_uri: assetPath, gain_db: 0};
  await writeFile(manifestPath, JSON.stringify(manifest));
  return {assetPath, manifestPath, root};
};

describe("renderer HTTP service", () => {
  it("completes a render with metadata and 70-95 progress mapping", async () => {
    const {manifestPath, root} = await fixture();
    const progresses: number[] = [];
    const engine: RenderEngine = {
      render: vi.fn(async ({onProgress}) => {
        for (const value of [0, 0.5, 1]) {
          progresses.push(mapRenderProgress(value));
          onProgress(value);
        }
      }),
    };
    const app = createRendererApp({engine, port: 3001, storageRoot: root});

    const response = await request(app).post("/render").send({
      job_id: "vid_12345678",
      manifest_path: manifestPath,
    });

    expect(response.status).toBe(200);
    expect(response.body).toMatchObject({
      status: "success",
      duration: 1,
      width: 1080,
      height: 1920,
      fps: 30,
      codec: "h264",
    });
    expect(progresses).toEqual([70, 83, 95]);
    expect(engine.render).toHaveBeenCalledOnce();
    const renderInput = vi.mocked(engine.render).mock.calls[0][0];
    if (renderInput.manifest.version !== "1.0") throw new Error("expected legacy manifest");
    expect(renderInput.manifest.scenes[0].visual.uri).toMatch(
      /^http:\/\/127\.0\.0\.1:3001\/media\/fixture\.png$/,
    );
    expect(renderInput.manifest.brand.logo_uri).toMatch(/^http:\/\/127\.0\.0\.1:3001\/media\//);
    expect(renderInput.manifest.voice?.audio_uri).toMatch(/^http:\/\/127\.0\.0\.1:3001\/media\//);
  });

  it("returns a stable error for a missing local scene asset", async () => {
    const {manifestPath, root} = await fixture();
    await writeFile(manifestPath, JSON.stringify(makeManifest(join(root, "missing.png"))));
    const engine: RenderEngine = {render: vi.fn(async () => undefined)};
    const response = await request(createRendererApp({engine, port: 3001, storageRoot: root}))
      .post("/render")
      .send({job_id: "vid_12345678", manifest_path: manifestPath});

    expect(response.status).toBe(422);
    expect(response.body).toMatchObject({status: "failed", error_code: "RENDER_ASSET_MISSING"});
    expect(engine.render).not.toHaveBeenCalled();
  });

  it("renders a V2-08 timeline manifest with local audio and visual URLs", async () => {
    const root = await mkdtemp(join(tmpdir(), "npd-renderer-v208-"));
    roots.push(root);
    const assetPath = join(root, "fixture.png");
    const audioPath = join(root, "audio.wav");
    const manifestPath = join(root, "timeline-render.json");
    await writeFile(assetPath, Buffer.from("png fixture"));
    await writeFile(audioPath, Buffer.from("wav fixture"));
    await writeFile(manifestPath, JSON.stringify(makeTimelineManifest(assetPath, audioPath)));
    const engine: RenderEngine = {render: vi.fn(async () => undefined)};

    const response = await request(createRendererApp({engine, port: 3001, storageRoot: root}))
      .post("/render")
      .send({job_id: "rnd_12345678", manifest_path: manifestPath});

    expect(response.status).toBe(200);
    const input = vi.mocked(engine.render).mock.calls[0][0];
    expect(input.manifest.version).toBe("2.0");
    if (input.manifest.version !== "2.0") throw new Error("expected timeline manifest");
    expect(input.manifest.audio.mix_uri).toMatch(/^http:\/\/127\.0\.0\.1:3001\/media\/audio\.wav$/);
    expect(input.manifest.visual_clips[0].uri).toMatch(/^http:\/\/127\.0\.0\.1:3001\/media\/fixture\.png$/);
  });

  it("returns a stable error for an invalid manifest", async () => {
    const {manifestPath, root} = await fixture();
    await writeFile(manifestPath, JSON.stringify({version: "invalid"}));
    const engine: RenderEngine = {render: vi.fn(async () => undefined)};
    const response = await request(createRendererApp({engine, port: 3001, storageRoot: root}))
      .post("/render")
      .send({job_id: "vid_12345678", manifest_path: manifestPath});

    expect(response.status).toBe(422);
    expect(response.body).toMatchObject({status: "failed", error_code: "MANIFEST_VALIDATION_FAILED"});
  });

  it.each([
    {prefix: "generic render failure:", status: 500, code: "RENDER_FAILED"},
    {prefix: "SUBTITLE_LAYOUT_OVERFLOW:", status: 422, code: "SUBTITLE_LAYOUT_OVERFLOW"},
  ])("redacts $code exceptions in both HTTP and structured stdout/stderr logging", async ({prefix, status, code}) => {
    const {manifestPath, root} = await fixture();
    const sentinels = [
      "PRIVATE_NARRATION_SENTINEL_03",
      "https://assets.invalid/image.png?token=SYNTHETIC_TOKEN_SENTINEL_03",
      "Authorization: Bearer SYNTHETIC_AUTH_SENTINEL_03",
      "/private/SYNTHETIC_PATH_SENTINEL_03",
      "PRIVATE_STACK_SENTINEL_03",
    ];
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const progressLog = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const engine: RenderEngine = {render: vi.fn(async ({onProgress}) => {
      onProgress(0.5);
      const error = new Error(`${prefix} ${sentinels.slice(0, 4).join(" ")}`);
      error.stack = sentinels[4];
      throw error;
    })};
    const response = await request(createRendererApp({engine, port: 3001, storageRoot: root}))
      .post("/render")
      .send({job_id: "vid_12345678", manifest_path: manifestPath});

    expect(response.status).toBe(status);
    expect(response.body).toMatchObject({status: "failed", error_code: code, retryable: false});
    expect(errorLog).toHaveBeenCalledOnce();
    expect(JSON.parse(errorLog.mock.calls[0][0])).toEqual({
      event: "render_failed", job_id: "vid_12345678", error_code: code,
    });
    expect(progressLog).toHaveBeenCalledWith(JSON.stringify({
      event: "render_progress", job_id: "vid_12345678", progress: 0.5, overall_progress: 83,
    }));
    const outputs = JSON.stringify({body: response.body, stdout: progressLog.mock.calls, stderr: errorLog.mock.calls});
    for (const sentinel of sentinels) expect(outputs).not.toContain(sentinel);
  });

  it("returns actionable allowlisted layout failure without user text", async () => {
    const {manifestPath, root} = await fixture();
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const engine: RenderEngine = {render: vi.fn(async () => { throw new Error("SUBTITLE_LAYOUT_OVERFLOW: private cue content"); })};
    const response = await request(createRendererApp({engine, port: 3001, storageRoot: root}))
      .post("/render").send({job_id: "vid_12345678", manifest_path: manifestPath});
    expect(response.status).toBe(422);
    expect(response.body).toMatchObject({error_code: "SUBTITLE_LAYOUT_OVERFLOW", retryable: false});
    expect(response.body.message).toContain("Split the subtitle cue");
    expect(JSON.stringify(response.body)).not.toContain("private cue content");
    expect(JSON.stringify(errorLog.mock.calls)).not.toContain("private cue content");
    expect(errorLog).toHaveBeenCalledWith(JSON.stringify({
      event: "render_failed", job_id: "vid_12345678", error_code: "SUBTITLE_LAYOUT_OVERFLOW",
    }));
  });

  it("does not echo non-Error throws in response or logs", async () => {
    const {manifestPath, root} = await fixture();
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const engine: RenderEngine = {render: vi.fn(async () => { throw "SYNTHETIC_THROW_SENTINEL_03"; })};
    const response = await request(createRendererApp({engine, port: 3001, storageRoot: root}))
      .post("/render").send({job_id: "vid_12345678", manifest_path: manifestPath});
    expect(response.status).toBe(500);
    expect(response.body.error_code).toBe("RENDER_FAILED");
    expect(JSON.parse(errorLog.mock.calls[0][0])).toEqual({
      event: "render_failed", job_id: "vid_12345678", error_code: "RENDER_FAILED",
    });
    expect(JSON.stringify([response.body, errorLog.mock.calls])).not.toContain("SYNTHETIC_THROW_SENTINEL_03");
  });

  it("rejects invalid correlation IDs before render logging", async () => {
    const {manifestPath, root} = await fixture();
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const progressLog = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const engine: RenderEngine = {render: vi.fn(async () => undefined)};
    const response = await request(createRendererApp({engine, port: 3001, storageRoot: root}))
      .post("/render").send({job_id: "vid_123\nPRIVATE_CORRELATION_SENTINEL_03", manifest_path: manifestPath});
    expect(response.status).toBe(422);
    expect(engine.render).not.toHaveBeenCalled();
    expect(errorLog).not.toHaveBeenCalled();
    expect(progressLog).not.toHaveBeenCalled();
    expect(JSON.stringify(response.body)).not.toContain("PRIVATE_CORRELATION_SENTINEL_03");
  });
});
