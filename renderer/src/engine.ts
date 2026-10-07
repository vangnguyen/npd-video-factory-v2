import {bundle} from "@remotion/bundler";
import {renderMedia, selectComposition} from "@remotion/renderer";
import {fileURLToPath} from "node:url";

import type {RenderEngine} from "./app";

const entryPoint = fileURLToPath(new URL("./index.ts", import.meta.url));
let serveUrlPromise: Promise<string> | null = null;

const getServeUrl = (): Promise<string> => {
  serveUrlPromise ??= bundle({entryPoint});
  return serveUrlPromise;
};

export class RemotionRenderEngine implements RenderEngine {
  constructor(private readonly options:{sourceProfile?:boolean;scale?:number}={}) {}
  async render({manifest, outputPath, onProgress}: Parameters<RenderEngine["render"]>[0]): Promise<void> {
    const serveUrl = await getServeUrl();
    const inputProps = {manifest};
    const composition = await selectComposition({
      serveUrl,
      id: manifest.metadata.template,
      inputProps,
    });
    await renderMedia({
      composition,
      serveUrl,
      codec: "h264",
      audioCodec: "aac",
      crf: 23,
      scale: this.options.scale ?? 1,
      overwrite: false,
      ...(this.options.sourceProfile?{pixelFormat:'yuv420p' as const,colorSpace:'bt709' as const,sampleRate:48000}:{}),
      outputLocation: outputPath,
      inputProps,
      onProgress: ({progress}) => onProgress(progress),
    });
  }
}
