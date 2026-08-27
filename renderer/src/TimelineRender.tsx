import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import type {TimelineRenderManifest, TimelineRendererInputProps} from "./types";

const dbToAmplitude = (db: number): number => Math.pow(10, db / 20);

const rgba = (hex: string, opacity: number): string => {
  const value = hex.replace("#", "");
  const red = Number.parseInt(value.slice(0, 2), 16);
  const green = Number.parseInt(value.slice(2, 4), 16);
  const blue = Number.parseInt(value.slice(4, 6), 16);
  return `rgba(${red}, ${green}, ${blue}, ${opacity})`;
};

export const activeSubtitleWordIndex = (
  cue: TimelineRenderManifest["subtitles"][number],
  seconds: number,
): number => cue.words.findIndex(
  (word) => seconds >= word.start_seconds && seconds < word.end_seconds,
);

const VisualLayer: React.FC<{
  clip: TimelineRenderManifest["visual_clips"][number];
}> = ({clip}) => {
  const {fps} = useVideoConfig();
  const playbackRate = Math.max(0.05, (clip.source_end - clip.source_start) / clip.duration);
  const mediaStyle: React.CSSProperties = {
    position: "absolute",
    width: `${100 / clip.crop.width}%`,
    height: `${100 / clip.crop.height}%`,
    left: `${(-clip.crop.x / clip.crop.width) * 100}%`,
    top: `${(-clip.crop.y / clip.crop.height) * 100}%`,
    objectFit: clip.fit,
    transform: `translate(${clip.transform.x * 100}%, ${clip.transform.y * 100}%) scale(${clip.transform.scale}) rotate(${clip.transform.rotation_degrees}deg)`,
    transformOrigin: "center",
    opacity: clip.opacity,
  };
  return (
    <AbsoluteFill style={{overflow: "hidden"}}>
      {clip.type === "video" ? (
        <OffthreadVideo
          src={clip.uri}
          muted
          startFrom={Math.round(clip.source_start * fps)}
          endAt={Math.round(clip.source_end * fps)}
          playbackRate={playbackRate}
          style={mediaStyle}
        />
      ) : (
        <Img src={clip.uri} style={mediaStyle} />
      )}
    </AbsoluteFill>
  );
};

const SubtitleLayer: React.FC<{
  cue: TimelineRenderManifest["subtitles"][number];
  style: TimelineRenderManifest["subtitle_style"];
}> = ({cue, style}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const now = cue.start_seconds + frame / fps;
  const activeWord = activeSubtitleWordIndex(cue, now);
  const scale = Math.min(width / 1080, height / 1920);
  const fade = interpolate(frame, [0, Math.max(1, Math.round(fps * 0.16))], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const animationScale = style.animation === "pop"
    ? interpolate(fade, [0, 1], [0.9, 1])
    : 1;
  const position: React.CSSProperties = style.position === "top"
    ? {top: `${style.safe_margin_percent}%`}
    : style.position === "center"
      ? {top: "50%", transform: `translateY(-50%) scale(${animationScale})`}
      : {bottom: `${style.safe_margin_percent + 5}%`};
  const words = cue.words.length > 0 ? cue.words : [{
    text: cue.text,
    start_seconds: cue.start_seconds,
    end_seconds: cue.end_seconds,
  }];
  return (
    <div
      style={{
        position: "absolute",
        left: `${style.safe_margin_percent}%`,
        right: `${style.safe_margin_percent}%`,
        ...position,
        padding: `${Math.round(12 * scale)}px ${Math.round(20 * scale)}px`,
        borderRadius: Math.round(14 * scale),
        backgroundColor: rgba(style.background_color, style.background_opacity),
        color: style.text_color,
        fontFamily: `"${style.font_family}", "Noto Sans", "Liberation Sans", sans-serif`,
        fontSize: Math.max(18, Math.round(style.font_size * scale)),
        fontWeight: style.font_weight,
        lineHeight: 1.22,
        textAlign: "center",
        opacity: style.animation === "fade" || style.animation === "pop" ? fade : 1,
        transform: style.position === "center"
          ? `translateY(-50%) scale(${animationScale})`
          : `scale(${animationScale})`,
        transformOrigin: "center",
        overflow: "hidden",
        display: "-webkit-box",
        WebkitBoxOrient: "vertical",
        WebkitLineClamp: style.max_lines,
        overflowWrap: "anywhere",
        textShadow: "0 2px 8px rgba(0,0,0,0.95)",
      }}
    >
      {words.map((word, index) => (
        <React.Fragment key={`${cue.cue_id}-${index}`}>
          {index > 0 ? " " : null}
          <span
            style={{
              color: style.animation === "word_highlight" && index === activeWord
                ? style.highlight_color
                : style.text_color,
            }}
          >
            {word.text}
          </span>
        </React.Fragment>
      ))}
    </div>
  );
};

export const TimelineRender: React.FC<TimelineRendererInputProps> = ({manifest}) => {
  const {fps} = useVideoConfig();
  return (
    <AbsoluteFill style={{backgroundColor: "#05080d"}}>
      {[...manifest.visual_clips]
        .sort((left, right) => left.track_order - right.track_order)
        .map((clip) => (
          <Sequence
            key={clip.clip_id}
            from={Math.round(clip.timeline_start * fps)}
            durationInFrames={Math.max(1, Math.round(clip.duration * fps))}
          >
            <VisualLayer clip={clip} />
          </Sequence>
        ))}

      <Audio src={manifest.audio.mix_uri} volume={dbToAmplitude(manifest.audio.gain_db)} />

      {manifest.subtitles.map((cue) => (
        <Sequence
          key={cue.cue_id}
          from={Math.round(cue.start_seconds * fps)}
          durationInFrames={Math.max(1, Math.round((cue.end_seconds - cue.start_seconds) * fps))}
        >
          <SubtitleLayer cue={cue} style={manifest.subtitle_style} />
        </Sequence>
      ))}

      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          height: Math.max(6, Math.round(12 * (manifest.metadata.width / 1080))),
          background: `linear-gradient(90deg, ${manifest.brand.primary_color}, ${manifest.brand.accent_color})`,
        }}
      />
    </AbsoluteFill>
  );
};
