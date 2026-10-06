import React, {useEffect, useRef, useState} from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  delayRender,
  continueRender,
  cancelRender,
  Freeze,
} from "remotion";

import type {TimelineRenderManifest, TimelineRendererInputProps} from "./types";
import {sourceCropAt} from "./reframe";

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

export const assertSubtitleFits = (fullHeight: number, lineHeight: number, padding: number, maxLines: number): void => {
  if (![fullHeight, lineHeight, padding, maxLines].every(Number.isFinite)
      || lineHeight <= 0 || maxLines < 1 || padding < 0
      || fullHeight > lineHeight * maxLines + padding + 2) {
    // Never include user narration or private inputs in render exceptions.
    throw new Error("SUBTITLE_LAYOUT_OVERFLOW: split the cue or adjust its approved style");
  }
};

const VisualLayer: React.FC<{
  clip: TimelineRenderManifest["visual_clips"][number];
}> = ({clip}) => {
  const {fps} = useVideoConfig();
  const frame = useCurrentFrame();
  const fade = ["fade","crossfade"].includes(clip.transition_in?.kind ?? "") && (clip.transition_in?.duration_seconds ?? 0) > 0
    ? interpolate(frame, [0, Math.max(1, Math.round(fps*(clip.transition_in?.duration_seconds ?? 0)))], [0,1], {extrapolateLeft:"clamp",extrapolateRight:"clamp"}) : 1;
  const playbackRate = clip.type === "video" && clip.source_end !== null
    ? Math.max(0.05, (clip.source_end - clip.source_start) / clip.duration) : 1;
  const crop=sourceCropAt(clip,frame/fps);
  const mediaStyle: React.CSSProperties = {
    position: "absolute",
    width: `${100 / crop.width}%`,
    height: `${100 / crop.height}%`,
    left: `${(-crop.x / crop.width) * 100}%`,
    top: `${(-crop.y / crop.height) * 100}%`,
    objectFit: clip.fit,
    transform: `translate(${clip.transform.x * 100}%, ${clip.transform.y * 100}%) scale(${clip.transform.scale}) rotate(${clip.transform.rotation_degrees}deg)`,
    transformOrigin: "center",
    opacity: clip.opacity * fade,
  };
  return (
    <AbsoluteFill style={{overflow: "hidden"}}>
      {clip.type === "video" ? (
        <OffthreadVideo
          src={clip.uri}
          muted
          startFrom={Math.round(clip.source_start * fps)}
          endAt={Math.round((clip.source_end ?? 0) * fps)}
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
  const subtitle = useRef<HTMLDivElement>(null);
  const [layoutHandle] = useState(() => delayRender("Verify full subtitle layout"));
  useEffect(() => {
    let cancelled = false;
    const verify = async () => {
      await document.fonts.ready;
      if (cancelled) return;
      const element = subtitle.current;
      if (!element) throw new Error("SUBTITLE_LAYOUT_UNAVAILABLE");
      const measured = getComputedStyle(element);
      assertSubtitleFits(element.scrollHeight, Number.parseFloat(measured.lineHeight),
        Number.parseFloat(measured.paddingTop) + Number.parseFloat(measured.paddingBottom), style.max_lines);
      continueRender(layoutHandle);
    };
    void verify().catch((error: unknown) => {
      if (!cancelled) cancelRender(error instanceof Error ? error : new Error("SUBTITLE_LAYOUT_UNAVAILABLE"));
    });
    return () => {cancelled = true;};
  }, [layoutHandle, cue, style, width, height]);
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
      ref={subtitle}
      data-subtitle-cue={cue.cue_id}
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
        // Measure the complete cue after fonts load. Do not silently line-clamp
        // or ellipsize words while the audio continues to read them.
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
        .map((clip, index, clips) => (
          <Sequence
            key={clip.clip_id}
            from={Math.round(clip.timeline_start * fps)}
            durationInFrames={Math.max(1, Math.round((clip.duration + crossfadeTail(clip, clips[index+1])) * fps))}
          >
            <HeldVisual clip={clip} hold={crossfadeTail(clip, clips[index+1]) > 0} />
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

const HeldVisual: React.FC<{clip: TimelineRenderManifest["visual_clips"][number]; hold:boolean}> = ({clip,hold}) => {
  const frame=useCurrentFrame(); const {fps}=useVideoConfig();
  const end=Math.max(1,Math.round(clip.duration*fps));
  // Do not read extra source-video frames beyond the validated source window.
  return hold && frame>=end ? <Freeze frame={end-1}><VisualLayer clip={clip}/></Freeze> : <VisualLayer clip={clip}/>;
};

export const crossfadeTail = (clip: TimelineRenderManifest["visual_clips"][number], next?: TimelineRenderManifest["visual_clips"][number]): number => {
  // Keep only contiguous same-track predecessor visible under the incoming
  // crossfade. Explicit historical fade still means fade-through-background.
  if (!next || next.track_order !== clip.track_order || next.transition_in?.kind !== "crossfade"
      || Math.abs(next.timeline_start-clip.timeline_start-clip.duration)>0.001) return 0;
  return Math.min(next.duration, next.transition_in.duration_seconds);
};
