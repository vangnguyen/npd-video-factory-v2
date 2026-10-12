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
import {captionParts} from './subtitles';

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
  previous?: TimelineRenderManifest["visual_clips"][number];
}> = ({clip, previous}) => {
  const {fps, width} = useVideoConfig();
  const frame = useCurrentFrame();
  const transition = visualTransitionStyle(clip, frame, fps, previous);
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
    opacity: clip.opacity * transition.opacity,
  };
  return (
    <AbsoluteFill style={{overflow: "hidden",filter:visualEffectCss(clip.effects,width*(clip.viewport?.width??1)),
      ...(transition.slideXPercent?{transform:`translateX(${transition.slideXPercent}%)`}:{}),
      ...(clip.viewport?{left:`${clip.viewport.x*100}%`,top:`${clip.viewport.y*100}%`,width:`${clip.viewport.width*100}%`,height:`${clip.viewport.height*100}%`}: {})}}>
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
      if (style.animation === 'word_by_word') {
        const probe = element.cloneNode(false) as HTMLDivElement;
        Object.assign(probe.style, {position:'absolute', visibility:'hidden', width:`${element.getBoundingClientRect().width}px`,
          boxSizing:'border-box', left:'0', right:'auto', top:'0', bottom:'auto', transform:'none'});
        element.parentElement!.appendChild(probe);
        try {
          for (const word of cue.words) {
            probe.textContent = word.text;
            assertSubtitleFits(probe.scrollHeight, Number.parseFloat(measured.lineHeight),
              Number.parseFloat(measured.paddingTop) + Number.parseFloat(measured.paddingBottom), style.max_lines);
          }
        } finally {probe.remove();}
      }
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
  const parts = captionParts(cue, style, now);
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
        opacity: style.animation === 'word_by_word' && !parts.length ? 0
          : style.animation === "fade" || style.animation === "pop" ? fade : 1,
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
      {parts.map((part, index) => (
        <React.Fragment key={`${cue.cue_id}-${index}`}>
          <span
            style={{
              color: part.highlighted ? style.highlight_color : style.text_color,
              ...(style.animation === 'karaoke' && part.wordIndex !== null ? {
                backgroundImage: `linear-gradient(90deg, ${style.highlight_color} ${part.progress * 100}%, ${style.text_color} ${part.progress * 100}%)`,
                backgroundClip: 'text', WebkitBackgroundClip: 'text', color: 'transparent', textShadow:'none',
              } : {}),
            }}
          >
            {part.text}
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
      {orderedVisualClips(manifest.visual_clips)
        .map((clip, index, clips) => (
          <Sequence
            key={clip.clip_id}
            from={Math.round(clip.timeline_start * fps)}
            durationInFrames={Math.max(1, Math.round((clip.duration + crossfadeTail(clip, contiguousVisualPeer(clips,clip,'next'))) * fps))}
          >
            <HeldVisual clip={clip} previous={contiguousVisualPeer(clips,clip,'previous')}
              hold={crossfadeTail(clip, contiguousVisualPeer(clips,clip,'next')) > 0} />
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

const HeldVisual: React.FC<{clip: TimelineRenderManifest["visual_clips"][number]; previous?: TimelineRenderManifest["visual_clips"][number]; hold:boolean}> = ({clip,previous,hold}) => {
  const frame=useCurrentFrame(); const {fps}=useVideoConfig();
  const end=Math.max(1,Math.round(clip.duration*fps));
  // Do not read extra source-video frames beyond the validated source window.
  return hold && frame>=end ? <Freeze frame={end-1}><VisualLayer clip={clip} previous={previous}/></Freeze> : <VisualLayer clip={clip} previous={previous}/>;
};

export const crossfadeTail = (clip: TimelineRenderManifest["visual_clips"][number], next?: TimelineRenderManifest["visual_clips"][number]): number => {
  // Keep only contiguous same-track predecessor visible under the incoming
  // crossfade. Explicit historical fade still means fade-through-background.
  if (!next || next.track_order !== clip.track_order || incomingVisualTransition(next,clip)?.kind !== "crossfade"
      || Math.abs(next.timeline_start-clip.timeline_start-clip.duration)>0.001) return 0;
  return Math.min(next.duration, incomingVisualTransition(next,clip)?.duration_seconds??0);
};

type VisualClip = TimelineRenderManifest['visual_clips'][number];
// Track order controls layers; time controls the predecessor/incoming order
// inside a track, even when an edit changed the snapshot's array order.
export const orderedVisualClips = (clips:VisualClip[]):VisualClip[] => [...clips].sort((a,b)=>a.track_order-b.track_order || a.timeline_start-b.timeline_start);
export const contiguousVisualPeer = (clips:VisualClip[],clip:VisualClip,direction:'previous'|'next'):VisualClip|undefined =>
  clips.find(peer=>peer.clip_id!==clip.clip_id && peer.track_order===clip.track_order &&
    Math.abs(direction==='next'?peer.timeline_start-clip.timeline_start-clip.duration:clip.timeline_start-peer.timeline_start-peer.duration)<.001);
export const incomingVisualTransition = (clip:VisualClip, previous?:VisualClip):VisualClip['transition_in'] => {
  if (previous?.transition_out?.kind==='crossfade' && previous.track_order===clip.track_order
      && Math.abs(clip.timeline_start-previous.timeline_start-previous.duration)<.001
      && (!clip.transition_in || ['none','cut'].includes(clip.transition_in.kind))) return previous.transition_out;
  return clip.transition_in;
};
export const visualTransitionStyle = (clip:VisualClip,frame:number,fps:number,previous?:VisualClip):{opacity:number;slideXPercent:number} => {
  const incoming=incomingVisualTransition(clip,previous),outgoing=clip.transition_out;
  const progress=(value:number)=>Math.max(0,Math.min(1,value));
  const inFrames=Math.max(1,Math.round((incoming?.duration_seconds??0)*fps));
  const outFrames=Math.max(1,Math.round((outgoing?.duration_seconds??0)*fps));
  const end=Math.max(1,Math.round(clip.duration*fps));
  const entry=incoming?.duration_seconds?progress(frame/inFrames):1;
  const exit=outgoing?.duration_seconds?progress((frame-(end-outFrames))/Math.max(1,outFrames-1)):0;
  const fadeIn=['fade','crossfade','dissolve'].includes(incoming?.kind??'')?entry:1;
  const fadeOut=['fade','dissolve'].includes(outgoing?.kind??'')?1-exit:1;
  return {opacity:fadeIn*fadeOut,slideXPercent:(incoming?.kind==='slide'?(1-entry)*100:0)-(outgoing?.kind==='slide'?exit*100:0)};
};
export const visualEffectCss = (effects:VisualClip['effects'],width:number):string|undefined => {
  if (!effects?.length) return undefined;
  return effects.map(effect=>effect.type==='hue_rotate'?`hue-rotate(${effect.value}deg)`:
    effect.type==='blur'?`blur(${effect.value*width}px)`:
    `${effect.type==='saturation'?'saturate':effect.type}(${effect.value})`).join(' ');
};
