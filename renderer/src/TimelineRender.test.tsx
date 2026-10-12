import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {describe, expect, it, vi} from "vitest";

vi.mock("remotion", async () => {
  const ReactModule = await import("react");
  const container = ({children}: React.PropsWithChildren) => ReactModule.createElement("div", null, children);
  return {
    AbsoluteFill: container,
    Audio: (props: React.AudioHTMLAttributes<HTMLAudioElement>) => ReactModule.createElement("audio", props),
    Img: (props: React.ImgHTMLAttributes<HTMLImageElement>) => ReactModule.createElement("img", props),
    OffthreadVideo: (props: React.VideoHTMLAttributes<HTMLVideoElement>) => ReactModule.createElement("video", props),
    Sequence: container,
    interpolate: () => 1,
    useCurrentFrame: () => 15,
    useVideoConfig: () => ({fps: 30, width: 1080, height: 1920, durationInFrames: 30}),
    delayRender: () => 1,
    continueRender: vi.fn(),
    cancelRender: vi.fn(),
  };
});

import {TimelineRender, activeSubtitleWordIndex, assertSubtitleFits, crossfadeTail, visualTransitionStyle, visualEffectCss, incomingVisualTransition, orderedVisualClips, contiguousVisualPeer} from "./TimelineRender";
import {makeTimelineManifest} from "./test-fixtures";

describe("timeline-render-v1 composition", () => {
  it('keeps an incoming crossfade above its predecessor after snapshot array reordering, without changing track layers',()=>{
    const a={...makeTimelineManifest('data:image/png;base64,AA==').visual_clips[0],clip_id:'clip_before',timeline_start:0,duration:1,
      transition_out:{kind:'crossfade' as const,duration_seconds:.2}};
    const b={...a,clip_id:'clip_after',timeline_start:1,transition_out:undefined};
    const overlay={...a,clip_id:'clip_overlay',track_order:a.track_order+1};
    const input=[overlay,b,a];
    expect(orderedVisualClips(input).map(c=>c.clip_id)).toEqual(['clip_before','clip_after','clip_overlay']);
    expect(input.map(c=>c.clip_id)).toEqual(['clip_overlay','clip_after','clip_before']);
    expect(contiguousVisualPeer(input,b,'previous')).toBe(a);
    expect(contiguousVisualPeer(input,a,'next')).toBe(b);
    expect(incomingVisualTransition(b,a)?.kind).toBe('crossfade');
  });
  it('never treats an extremely short clip as its own transition peer',()=>{
    const clip={...makeTimelineManifest('data:image/png;base64,AA==').visual_clips[0],duration:.0005};
    expect(contiguousVisualPeer([clip],clip,'next')).toBeUndefined();
    expect(contiguousVisualPeer([clip],clip,'previous')).toBeUndefined();
  });
  it('applies fade-out within saved duration and preserves the incoming envelope',()=>{
    const clip={...makeTimelineManifest('data:image/png;base64,AA==').visual_clips[0],duration:2,
      transition_in:{kind:'fade' as const,duration_seconds:.5},transition_out:{kind:'fade' as const,duration_seconds:.5}};
    expect(visualTransitionStyle(clip,0,30).opacity).toBe(0);
    expect(visualTransitionStyle(clip,30,30).opacity).toBe(1);
    expect(visualTransitionStyle(clip,59,30).opacity).toBe(0);
  });
  it('incoming/outgoing slide positions affect the clip viewport without changing its source window',()=>{
    const clip={...makeTimelineManifest('data:image/png;base64,AA==').visual_clips[0],duration:2,
      transition_in:{kind:'slide' as const,duration_seconds:.5},transition_out:{kind:'slide' as const,duration_seconds:.5}};
    expect(visualTransitionStyle(clip,0,30)).toEqual({opacity:1,slideXPercent:100});
    expect(visualTransitionStyle(clip,30,30)).toEqual({opacity:1,slideXPercent:0});
    expect(visualTransitionStyle(clip,59,30)).toEqual({opacity:1,slideXPercent:-100});
  });
  it('outgoing crossfade derives a contiguous incoming blend and holds only the last allowed source frame',()=>{
    const clip={...makeTimelineManifest('data:image/png;base64,AA==').visual_clips[0],duration:2,
      transition_out:{kind:'crossfade' as const,duration_seconds:.5}};
    const next={...clip,clip_id:'clip_next_visual',timeline_start:clip.timeline_start+2,transition_out:undefined};
    expect(incomingVisualTransition(next,clip)).toEqual(clip.transition_out);
    expect(crossfadeTail(clip,next)).toBe(.5);
    expect(visualTransitionStyle(next,0,30,clip).opacity).toBe(0);
    expect(visualTransitionStyle(next,15,30,clip).opacity).toBe(1);
    expect(crossfadeTail(clip,{...next,track_order:clip.track_order+1})).toBe(0);
  });
  it('approved filter chain retains order and scales blur with its rendered viewport',()=>{
    const effects=[{type:'brightness' as const,value:.8},{type:'hue_rotate' as const,value:-30},{type:'saturation' as const,value:.5},{type:'blur' as const,value:.01}];
    expect(visualEffectCss(effects,1080)).toBe('brightness(0.8) hue-rotate(-30deg) saturate(0.5) blur(10.8px)');
    expect(visualEffectCss([{type:'blur',value:.01}],540)).toBe('blur(5.4px)');
    expect(visualEffectCss([],1080)).toBeUndefined();
  });
  it("retains the predecessor only for explicit contiguous crossfade, not dark fade", () => {
    const clip=makeTimelineManifest("data:image/png;base64,AA==").visual_clips[0];
    const next={...clip,timeline_start:clip.timeline_start+clip.duration,transition_in:{kind:"crossfade" as const,duration_seconds:0.25}};
    expect(crossfadeTail(clip,next)).toBe(0.25);
    expect(crossfadeTail(clip,{...next,transition_in:{kind:"fade",duration_seconds:0.25}})).toBe(0);
    expect(crossfadeTail(clip,{...next,track_order:clip.track_order+1})).toBe(0);
    expect(crossfadeTail(clip,{...next,timeline_start:next.timeline_start+1})).toBe(0);
  });
  it("renders layered media, mixed audio, Vietnamese subtitles, and brand styling", () => {
    const manifest = makeTimelineManifest("data:image/png;base64,AA==");
    const html = renderToStaticMarkup(<TimelineRender manifest={manifest} />);

    expect(html).toContain("data:image/png;base64,AA==");
    expect(html).toContain("Phụ");
    expect(html).toContain("Noto Sans");
    expect(html).toContain("linear-gradient");
    expect(html).not.toContain("publish");
    expect(html).not.toContain("-webkit-line-clamp");
  });

  it("selects the active word from deterministic global timings", () => {
    const cue = makeTimelineManifest("data:image/png;base64,AA==").subtitles[0];
    expect(activeSubtitleWordIndex(cue, 0.1)).toBe(0);
    expect(activeSubtitleWordIndex(cue, 0.6)).toBe(2);
    expect(activeSubtitleWordIndex(cue, 1.1)).toBe(-1);
  });

  it("admits a measured complete cue within its approved line count", () => {
    expect(() => assertSubtitleFits(200, 58.56, 24, 3)).not.toThrow();
  });

  it("rejects glyph overflow instead of hiding words behind an ellipsis", () => {
    expect(() => assertSubtitleFits(259, 58.56, 24, 3)).toThrow("SUBTITLE_LAYOUT_OVERFLOW");
  });

  it.each([NaN, Infinity, -1])("rejects unavailable or invalid layout measurements %s", (lineHeight) => {
    expect(() => assertSubtitleFits(200, lineHeight, 24, 3)).toThrow("SUBTITLE_LAYOUT_OVERFLOW");
  });
});
