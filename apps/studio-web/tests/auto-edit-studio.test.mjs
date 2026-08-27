import assert from "node:assert/strict";
import test from "node:test";

import {
  canDropOnTrack,
  clipStyle,
  describeApproval,
  describeProductionRender,
  describePreview,
  formatTime,
  getClip,
  pixelsPerSecond,
  qcItems,
  snapTime,
  timelinePositionFromPointer,
} from "../studio-utils.mjs";

const timeline = {
  current_version: 3,
  snapshot: {
    tracks: [
      {
        track_id: "trk_video",
        type: "video",
        kind: "source",
        clips: [
          { clip_id: "clip_one", timeline_start: 1.25, duration: 2.5, disabled: false },
        ],
      },
    ],
  },
};

test("formats editor timecodes and zoom deterministically", () => {
  assert.equal(formatTime(0), "00:00.0");
  assert.equal(formatTime(65.25), "01:05.3");
  assert.equal(pixelsPerSecond(1), 34);
  assert.equal(pixelsPerSecond(10), 136);
});

test("labels version-bound approval and production render states", () => {
  assert.deepEqual(describeApproval({ status: "approved" }), { label: "Đã duyệt", tone: "safe" });
  assert.equal(describeApproval({ status: "changes_requested" }).tone, "danger");
  assert.equal(
    describeProductionRender({ status: "awaiting_review", qc_status: "passed", progress: 100 }).label,
    "Review sẵn sàng · QC PASS",
  );
  assert.equal(describeProductionRender({ status: "running", progress: 42 }).terminal, false);
  assert.deepEqual(qcItems({
    status: "passed",
    width: 1080,
    height: 1920,
    fps: 30,
    video_codec: "h264",
    audio_codec: "aac",
    av_sync_delta_seconds: 0.01,
  })[1], ["Kích thước", "1080×1920"]);
});

test("snaps pointer placement to quarter seconds", () => {
  assert.equal(snapTime(1.12, true), 1);
  assert.equal(snapTime(1.14, false), 1.14);
  assert.equal(timelinePositionFromPointer(168, 100, 0, 1, true), 2);
});

test("computes timeline clip placement and respects track compatibility", () => {
  const style = clipStyle(timeline.snapshot.tracks[0].clips[0], "source", 1);
  assert.equal(style.left, "42.5px");
  assert.equal(style.width, "85px");
  assert.equal(canDropOnTrack("video", "video", false), true);
  assert.equal(canDropOnTrack("video", "audio", false), false);
  assert.equal(canDropOnTrack("video", "video", true), false);
  assert.equal(getClip(timeline, "clip_one").track.track_id, "trk_video");
});

test("labels ready, stale and running previews without overstating readiness", () => {
  assert.deepEqual(
    describePreview({ status: "ready", timeline_version: 3, valid_for_current_timeline: true }, 3),
    { label: "Sẵn sàng · v3", tone: "safe" },
  );
  assert.equal(describePreview({ status: "ready", timeline_version: 2, valid_for_current_timeline: false }, 3).tone, "warning");
  assert.equal(describePreview({ status: "running", timeline_version: 3, progress: 45 }, 3).label, "Đang tạo · 45%");
});
