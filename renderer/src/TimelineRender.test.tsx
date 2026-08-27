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
  };
});

import {TimelineRender, activeSubtitleWordIndex} from "./TimelineRender";
import {makeTimelineManifest} from "./test-fixtures";

describe("timeline-render-v1 composition", () => {
  it("renders layered media, mixed audio, Vietnamese subtitles, and brand styling", () => {
    const manifest = makeTimelineManifest("data:image/png;base64,AA==");
    const html = renderToStaticMarkup(<TimelineRender manifest={manifest} />);

    expect(html).toContain("data:image/png;base64,AA==");
    expect(html).toContain("Phụ");
    expect(html).toContain("Noto Sans");
    expect(html).toContain("linear-gradient");
    expect(html).not.toContain("publish");
  });

  it("selects the active word from deterministic global timings", () => {
    const cue = makeTimelineManifest("data:image/png;base64,AA==").subtitles[0];
    expect(activeSubtitleWordIndex(cue, 0.1)).toBe(0);
    expect(activeSubtitleWordIndex(cue, 0.6)).toBe(2);
    expect(activeSubtitleWordIndex(cue, 1.1)).toBe(-1);
  });
});
