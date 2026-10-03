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

import {TimelineRender, activeSubtitleWordIndex, assertSubtitleFits, crossfadeTail} from "./TimelineRender";
import {makeTimelineManifest} from "./test-fixtures";

describe("timeline-render-v1 composition", () => {
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
