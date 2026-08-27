import {describe, expect, it} from "vitest";

import {renderRequestSchema, timelineRenderManifestSchema, videoManifestSchema} from "./contract";
import {makeManifest, makeTimelineManifest} from "./test-fixtures";

describe("renderer contracts", () => {
  it("accepts the current manifest and two-field render request", () => {
    expect(videoManifestSchema.parse(makeManifest("data:image/png;base64,AA==")).metadata).toMatchObject({
      template: "vertical-short-v1",
      niche: "custom",
      width: 1080,
      height: 1920,
      fps: 30,
    });
    expect(renderRequestSchema.parse({job_id: "vid_12345678", manifest_path: "/storage/manifest.json"})).toEqual({
      job_id: "vid_12345678",
      manifest_path: "/storage/manifest.json",
    });
  });

  it("rejects invalid dimensions, unknown fields, and broken timelines", () => {
    const invalid = {
      ...makeManifest("data:image/png;base64,AA=="),
      metadata: {...makeManifest("x").metadata, width: 1920},
      unexpected: true,
    };
    expect(videoManifestSchema.safeParse(invalid).success).toBe(false);

    const brokenTimeline = makeManifest("data:image/png;base64,AA==");
    brokenTimeline.scenes[0].duration_seconds = 0.5;
    expect(videoManifestSchema.safeParse(brokenTimeline).success).toBe(false);

    const gapTimeline = makeManifest("data:image/png;base64,AA==");
    gapTimeline.scenes[0].start_seconds = 0.2;
    expect(videoManifestSchema.safeParse(gapTimeline).success).toBe(false);

    const subtitleOutsideComposition = makeManifest("data:image/png;base64,AA==");
    subtitleOutsideComposition.subtitles[0].end_seconds = 1.2;
    expect(videoManifestSchema.safeParse(subtitleOutsideComposition).success).toBe(false);
  });

  it("accepts the legacy real-estate adapter without making it the core default", () => {
    const legacy = makeManifest("data:image/png;base64,AA==");
    legacy.metadata.niche = "real_estate";
    legacy.metadata.template = "real-estate-short-v1";
    expect(videoManifestSchema.parse(legacy).metadata.template).toBe("real-estate-short-v1");
  });

  it("accepts the V2-08 timeline manifest and production render identifiers", () => {
    const manifest = makeTimelineManifest("data:image/png;base64,AA==");
    expect(timelineRenderManifestSchema.parse(manifest)).toMatchObject({
      version: "2.0",
      safety: {publishing_allowed: false, external_publish_requested: false},
    });
    expect(renderRequestSchema.parse({job_id: "rnd_12345678", manifest_path: "/storage/v2.json"}))
      .toMatchObject({job_id: "rnd_12345678"});
  });

  it("rejects unsafe, mistimed, or unsupported V2-08 manifests", () => {
    const unsafe = makeTimelineManifest("data:image/png;base64,AA==");
    (unsafe.safety as {publishing_allowed: boolean}).publishing_allowed = true;
    expect(timelineRenderManifestSchema.safeParse(unsafe).success).toBe(false);

    const mistimed = makeTimelineManifest("data:image/png;base64,AA==");
    mistimed.subtitles[0].words[0].end_seconds = 2;
    expect(timelineRenderManifestSchema.safeParse(mistimed).success).toBe(false);

    const unsupported = makeTimelineManifest("data:image/png;base64,AA==");
    unsupported.metadata.width = 1920;
    unsupported.metadata.height = 1920;
    expect(timelineRenderManifestSchema.safeParse(unsupported).success).toBe(false);
  });
});
