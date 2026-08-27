export type SceneRole = "hook" | "identity" | "information" | "evidence" | "value" | "sales_angle" | "cta";

export type NicheName =
  | "real_estate" | "technology" | "ai" | "education" | "knowledge" | "story"
  | "comedy" | "entertainment" | "product_review" | "affiliate" | "news_explainer" | "custom";

export type VideoManifest = {
  version: "1.0";
  metadata: {
    title: string;
    project: string;
    niche: NicheName;
    template: "vertical-short-v1" | "real-estate-short-v1";
    duration_seconds: number;
    fps: 30;
    width: 1080;
    height: 1920;
    language: "vi";
  };
  brand: {
    name: string;
    logo_uri: string;
    cta: string;
    primary_color?: string;
    accent_color?: string;
  };
  voice?: {
    audio_uri: string;
    gain_db?: number;
  };
  music?: {
    audio_uri: string;
    gain_db: number;
  };
  scenes: Array<{
    id: string;
    start_seconds: number;
    duration_seconds: number;
    role: SceneRole;
    narration: string;
    visual: {
      type: "video" | "image";
      uri: string;
      trim_start_seconds?: number;
      trim_end_seconds?: number;
      fit?: "cover" | "contain";
    };
    overlay?: {
      headline?: string;
      body?: string;
      emphasis?: string;
    };
  }>;
  subtitles: Array<{
    start_seconds: number;
    end_seconds: number;
    text: string;
  }>;
};

export type RendererInputProps = {
  manifest: VideoManifest;
};

export type TimelineRenderManifest = {
  version: "2.0";
  metadata: {
    title: string;
    project: string;
    niche: string;
    template: "timeline-render-v1";
    duration_seconds: number;
    fps: number;
    width: 540 | 1080 | 1920;
    height: 960 | 1080 | 1920;
    language: "vi";
  };
  brand: {
    name: string;
    primary_color: string;
    accent_color: string;
  };
  audio: {
    mix_uri: string;
    gain_db: number;
    sample_rate: 48000;
    ducking_applied: boolean;
  };
  visual_clips: Array<{
    clip_id: string;
    track_order: number;
    type: "video" | "image";
    uri: string;
    timeline_start: number;
    duration: number;
    source_start: number;
    source_end: number;
    fit: "cover" | "contain";
    crop: {x: number; y: number; width: number; height: number};
    transform: {x: number; y: number; scale: number; rotation_degrees: number};
    opacity: number;
  }>;
  subtitles: Array<{
    cue_id: string;
    start_seconds: number;
    end_seconds: number;
    text: string;
    words: Array<{text: string; start_seconds: number; end_seconds: number}>;
  }>;
  subtitle_style: {
    font_family: "Noto Sans" | "Noto Sans Display";
    font_size: number;
    font_weight: number;
    text_color: string;
    highlight_color: string;
    background_color: string;
    background_opacity: number;
    position: "top" | "center" | "bottom";
    animation: "none" | "fade" | "pop" | "word_highlight";
    max_lines: number;
    safe_margin_percent: number;
  };
  safety: {
    human_approval_required: true;
    publishing_allowed: false;
    external_publish_requested: false;
    source_media_mutated: false;
  };
};

export type AnyVideoManifest = VideoManifest | TimelineRenderManifest;

export type TimelineRendererInputProps = {
  manifest: TimelineRenderManifest;
};
