import React from "react";
import {Composition} from "remotion";

import {VerticalShort} from "./VerticalShort";
import type {RendererInputProps, VideoManifest} from "./types";

const defaultManifest: VideoManifest = {
  version: "1.0",
  metadata: {
    title: "NPD Video Factory V2",
    project: "sample",
    niche: "custom",
    template: "vertical-short-v1",
    duration_seconds: 1,
    fps: 30,
    width: 1080,
    height: 1920,
    language: "vi",
  },
  brand: {
    name: "NPD Video Factory",
    logo_uri: "",
    cta: "Xem buoc tiep theo",
  },
  scenes: [
    {
      id: "scene_01",
      start_seconds: 0,
      duration_seconds: 1,
      role: "hook",
      narration: "NPD Video Factory V2",
      visual: {
        type: "image",
        uri: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1080' height='1920'%3E%3Crect width='100%25' height='100%25' fill='%23111111'/%3E%3C/svg%3E",
        fit: "cover",
      },
      overlay: {headline: "NPD Video Factory V2"},
    },
  ],
  subtitles: [],
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
    <Composition
      id="vertical-short-v1"
      component={VerticalShort}
      durationInFrames={30}
      fps={30}
      width={1080}
      height={1920}
      defaultProps={{manifest: defaultManifest} satisfies RendererInputProps}
      calculateMetadata={({props}) => ({
        durationInFrames: Math.max(
          1,
          Math.round(props.manifest.metadata.duration_seconds * props.manifest.metadata.fps),
        ),
        fps: props.manifest.metadata.fps,
        width: props.manifest.metadata.width,
        height: props.manifest.metadata.height,
      })}
    />
    <Composition
      id="real-estate-short-v1"
      component={VerticalShort}
      durationInFrames={30}
      fps={30}
      width={1080}
      height={1920}
      defaultProps={{
        manifest: {
          ...defaultManifest,
          metadata: {
            ...defaultManifest.metadata,
            niche: "real_estate",
            template: "real-estate-short-v1",
          },
        },
      } satisfies RendererInputProps}
      calculateMetadata={({props}) => ({
        durationInFrames: Math.max(
          1,
          Math.round(props.manifest.metadata.duration_seconds * props.manifest.metadata.fps),
        ),
        fps: props.manifest.metadata.fps,
        width: props.manifest.metadata.width,
        height: props.manifest.metadata.height,
      })}
    />
    </>
  );
};
