import {z} from "zod";

const strictObject = <T extends z.ZodRawShape>(shape: T) => z.object(shape).strict();

const visualSchema = strictObject({
  type: z.enum(["video", "image"]),
  uri: z.string().min(1),
  trim_start_seconds: z.number().nonnegative().optional(),
  trim_end_seconds: z.number().positive().optional(),
  fit: z.enum(["cover", "contain"]).optional(),
});

const overlaySchema = strictObject({
  headline: z.string().max(100).optional(),
  body: z.string().max(240).optional(),
  emphasis: z.string().max(60).optional(),
});

export const videoManifestSchema = strictObject({
  version: z.literal("1.0"),
  metadata: strictObject({
    title: z.string().min(1),
    project: z.string().min(1),
    niche: z.enum([
      "real_estate", "technology", "ai", "education", "knowledge", "story",
      "comedy", "entertainment", "product_review", "affiliate", "news_explainer", "custom",
    ]),
    template: z.enum(["vertical-short-v1", "real-estate-short-v1"]),
    duration_seconds: z.number().positive().max(90),
    fps: z.literal(30),
    width: z.literal(1080),
    height: z.literal(1920),
    language: z.literal("vi"),
  }),
  brand: strictObject({
    name: z.string().min(1),
    logo_uri: z.string().min(1),
    cta: z.string().min(1).max(160),
    primary_color: z.string().regex(/^#[0-9A-Fa-f]{6}$/).optional(),
    accent_color: z.string().regex(/^#[0-9A-Fa-f]{6}$/).optional(),
  }),
  voice: strictObject({
    audio_uri: z.string().min(1),
    gain_db: z.number().min(-24).max(12).optional(),
  }).optional(),
  music: strictObject({
    audio_uri: z.string().min(1),
    gain_db: z.number().min(-40).max(0),
  }).optional(),
  scenes: z.array(strictObject({
    id: z.string().regex(/^scene_[0-9]{2}$/),
    start_seconds: z.number().nonnegative(),
    duration_seconds: z.number().positive().max(20),
    role: z.enum(["hook", "identity", "information", "evidence", "value", "sales_angle", "cta"]),
    narration: z.string().min(1),
    visual: visualSchema,
    overlay: overlaySchema.optional(),
  })).min(1).max(20),
  subtitles: z.array(strictObject({
    start_seconds: z.number().nonnegative(),
    end_seconds: z.number().positive(),
    text: z.string().min(1).max(160),
  })),
}).superRefine((manifest, context) => {
  const frameTolerance = 1 / manifest.metadata.fps;
  const sceneDuration = manifest.scenes.reduce((sum, scene) => sum + scene.duration_seconds, 0);
  if (Math.abs(sceneDuration - manifest.metadata.duration_seconds) > 0.1) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["scenes"],
      message: "scene duration total must match metadata duration",
    });
  }
  let expectedSceneStart = 0;
  for (let index = 0; index < manifest.scenes.length; index += 1) {
    const scene = manifest.scenes[index];
    if (Math.abs(scene.start_seconds - expectedSceneStart) > frameTolerance) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["scenes", index, "start_seconds"],
        message: "scenes must form a contiguous global timeline",
      });
    }
    expectedSceneStart = scene.start_seconds + scene.duration_seconds;
  }
  let previousSubtitleEnd = 0;
  for (let index = 0; index < manifest.subtitles.length; index += 1) {
    const subtitle = manifest.subtitles[index];
    if (subtitle.end_seconds <= subtitle.start_seconds) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["subtitles", index, "end_seconds"],
        message: "subtitle end must be after start",
      });
    }
    if (subtitle.start_seconds < previousSubtitleEnd - frameTolerance) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["subtitles", index, "start_seconds"],
        message: "subtitle cues must be monotonic and non-overlapping",
      });
    }
    if (subtitle.end_seconds > manifest.metadata.duration_seconds + frameTolerance) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["subtitles", index, "end_seconds"],
        message: "subtitle cue exceeds the composition duration",
      });
    }
    previousSubtitleEnd = subtitle.end_seconds;
  }
});

const timelineCropSchema = strictObject({
  x: z.number().min(0).max(1),
  y: z.number().min(0).max(1),
  width: z.number().positive().max(1),
  height: z.number().positive().max(1),
});

const timelineTransformSchema = strictObject({
  x: z.number().min(-2).max(2),
  y: z.number().min(-2).max(2),
  scale: z.number().positive().max(8),
  rotation_degrees: z.number().min(-360).max(360),
});

const subtitleWordSchema = strictObject({
  text: z.string().min(1).max(60),
  start_seconds: z.number().nonnegative(),
  end_seconds: z.number().positive(),
});

const timelineSubtitleSchema = strictObject({
  cue_id: z.string().regex(/^sub_[A-Za-z0-9_-]{4,60}$/),
  start_seconds: z.number().nonnegative(),
  end_seconds: z.number().positive(),
  text: z.string().min(1).max(180),
  words: z.array(subtitleWordSchema).max(40),
});

export const timelineRenderManifestSchema = strictObject({
  version: z.literal("2.0"),
  metadata: strictObject({
    title: z.string().min(1),
    project: z.string().min(1),
    niche: z.string().min(1),
    template: z.literal("timeline-render-v1"),
    duration_seconds: z.number().positive().max(180),
    fps: z.number().int().min(24).max(60),
    width: z.union([z.literal(540), z.literal(1080), z.literal(1920)]),
    height: z.union([z.literal(960), z.literal(1080), z.literal(1920)]),
    language: z.literal("vi"),
  }),
  brand: strictObject({
    name: z.string().min(1),
    primary_color: z.string().regex(/^#[0-9A-Fa-f]{6}$/),
    accent_color: z.string().regex(/^#[0-9A-Fa-f]{6}$/),
  }),
  audio: strictObject({
    mix_uri: z.string().min(1),
    gain_db: z.number().min(-18).max(9),
    sample_rate: z.literal(48000),
    ducking_applied: z.boolean(),
  }),
  visual_clips: z.array(strictObject({
    clip_id: z.string().regex(/^clip_[A-Za-z0-9_-]{4,60}$/),
    track_order: z.number().int().nonnegative(),
    type: z.enum(["video", "image"]),
    uri: z.string().min(1),
    timeline_start: z.number().nonnegative(),
    duration: z.number().positive(),
    source_start: z.number().nonnegative(),
    source_end: z.number().positive(),
    fit: z.enum(["cover", "contain"]),
    crop: timelineCropSchema,
    transform: timelineTransformSchema,
    opacity: z.number().min(0).max(1),
  })).min(1).max(400),
  subtitles: z.array(timelineSubtitleSchema).min(1).max(300),
  subtitle_style: strictObject({
    font_family: z.enum(["Noto Sans", "Noto Sans Display"]),
    font_size: z.number().int().min(28).max(84),
    font_weight: z.number().int().min(400).max(900),
    text_color: z.string().regex(/^#[0-9A-Fa-f]{6}$/),
    highlight_color: z.string().regex(/^#[0-9A-Fa-f]{6}$/),
    background_color: z.string().regex(/^#[0-9A-Fa-f]{6}$/),
    background_opacity: z.number().min(0).max(1),
    position: z.enum(["top", "center", "bottom"]),
    animation: z.enum(["none", "fade", "pop", "word_highlight"]),
    max_lines: z.number().int().min(1).max(3),
    safe_margin_percent: z.number().min(3).max(15),
  }),
  safety: strictObject({
    human_approval_required: z.literal(true),
    publishing_allowed: z.literal(false),
    external_publish_requested: z.literal(false),
    source_media_mutated: z.literal(false),
  }),
}).superRefine((manifest, context) => {
  const validSize = [
    [540, 960],
    [1080, 1920],
    [1920, 1080],
    [1080, 1080],
  ].some(([width, height]) => width === manifest.metadata.width && height === manifest.metadata.height);
  if (!validSize) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["metadata", "width"],
      message: "unsupported render profile dimensions",
    });
  }
  for (let index = 0; index < manifest.visual_clips.length; index += 1) {
    const clip = manifest.visual_clips[index];
    if (clip.source_end <= clip.source_start) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["visual_clips", index, "source_end"],
        message: "source end must be after source start",
      });
    }
    if (clip.timeline_start + clip.duration > manifest.metadata.duration_seconds + 1 / manifest.metadata.fps) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["visual_clips", index, "duration"],
        message: "visual clip exceeds composition duration",
      });
    }
  }
  let previousSubtitleEnd = 0;
  for (let index = 0; index < manifest.subtitles.length; index += 1) {
    const cue = manifest.subtitles[index];
    if (cue.end_seconds <= cue.start_seconds || cue.start_seconds < previousSubtitleEnd - 1 / manifest.metadata.fps) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["subtitles", index],
        message: "subtitle cues must be ordered, positive, and non-overlapping",
      });
    }
    if (cue.end_seconds > manifest.metadata.duration_seconds + 1 / manifest.metadata.fps) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["subtitles", index, "end_seconds"],
        message: "subtitle cue exceeds composition duration",
      });
    }
    let previousWordEnd = cue.start_seconds;
    for (let wordIndex = 0; wordIndex < cue.words.length; wordIndex += 1) {
      const word = cue.words[wordIndex];
      if (
        word.end_seconds <= word.start_seconds
        || word.start_seconds < previousWordEnd - 0.001
        || word.start_seconds < cue.start_seconds - 0.001
        || word.end_seconds > cue.end_seconds + 0.001
      ) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["subtitles", index, "words", wordIndex],
          message: "subtitle word timing must be ordered and remain inside its cue",
        });
      }
      previousWordEnd = word.end_seconds;
    }
    previousSubtitleEnd = cue.end_seconds;
  }
});

export const anyVideoManifestSchema = z.union([videoManifestSchema, timelineRenderManifestSchema]);

export const renderRequestSchema = strictObject({
  job_id: z.string().regex(/^(?:vid|rnd)_[A-Za-z0-9_-]+$/).max(80),
  manifest_path: z.string().min(1),
  output_path: z.string().min(1).optional(),
});
