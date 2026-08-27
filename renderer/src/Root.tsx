import React from "react";
import {Composition} from "remotion";

import {VerticalShort} from "./VerticalShort";
import {TimelineRender} from "./TimelineRender";
import type {
  RendererInputProps,
  TimelineRenderManifest,
  TimelineRendererInputProps,
  VideoManifest,
} from "./types";

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

const defaultTimelineManifest: TimelineRenderManifest = {
  version: "2.0",
  metadata: {
    title: "NPD Timeline Render",
    project: "sample",
    niche: "custom",
    template: "timeline-render-v1",
    duration_seconds: 1,
    fps: 30,
    width: 1080,
    height: 1920,
    language: "vi",
  },
  brand: {
    name: "NPD Video Factory",
    primary_color: "#F5C451",
    accent_color: "#17B9A6",
  },
  audio: {
    mix_uri: "data:audio/wav;base64,UklGRg==",
    gain_db: 0,
    sample_rate: 48000,
    ducking_applied: false,
  },
  visual_clips: [
    {
      clip_id: "clip_sample",
      track_order: 0,
      type: "image",
      uri: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1080' height='1920'%3E%3Crect width='100%25' height='100%25' fill='%2305080d'/%3E%3C/svg%3E",
      timeline_start: 0,
      duration: 1,
      source_start: 0,
      source_end: 1,
      fit: "cover",
      crop: {x: 0, y: 0, width: 1, height: 1},
      transform: {x: 0, y: 0, scale: 1, rotation_degrees: 0},
      opacity: 1,
    },
  ],
  subtitles: [
    {
      cue_id: "sub_sample",
      start_seconds: 0,
      end_seconds: 1,
      text: "NPD Video Factory V2",
      words: [],
    },
  ],
  subtitle_style: {
    font_family: "Noto Sans",
    font_size: 48,
    font_weight: 800,
    text_color: "#FFFFFF",
    highlight_color: "#F5C451",
    background_color: "#000000",
    background_opacity: 0.58,
    position: "bottom",
    animation: "word_highlight",
    max_lines: 3,
    safe_margin_percent: 7,
  },
  safety: {
    human_approval_required: true,
    publishing_allowed: false,
    external_publish_requested: false,
    source_media_mutated: false,
  },
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
    <Composition
      id="timeline-render-v1"
      component={TimelineRender}
      durationInFrames={30}
      fps={30}
      width={1080}
      height={1920}
      defaultProps={{manifest: defaultTimelineManifest} satisfies TimelineRendererInputProps}
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
