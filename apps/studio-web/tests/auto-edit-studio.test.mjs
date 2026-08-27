import assert from "node:assert/strict";
import test from "node:test";

import {
  analyticsMetricItems,
  canDropOnTrack,
  clipStyle,
  describeAnalytics,
  describeApproval,
  describePublication,
  describeProductionRender,
  describePreview,
  formatTime,
  formatAnalyticsMetric,
  getClip,
  pixelsPerSecond,
  publicationGateItems,
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

test("labels publishing dry-run truthfully and flattens gate evidence", () => {
  const publication = {
    status: "dry_run_succeeded",
    provider_validation: { checks: [{ key: "approval", passed: true, code: "APPROVED", message: "Approved" }] },
    rights_validation: { checks: [{ key: "asset", passed: true, code: "RIGHTS_VERIFIED", message: "Owned" }] },
    platform_validation: { checks: [{ key: "codec", passed: false, code: "CODEC_BLOCKED", message: "Blocked" }] },
  };
  assert.deepEqual(describePublication(publication), { label: "Dry-run PASS", tone: "safe" });
  assert.equal(describePublication({ status: "blocked" }).tone, "danger");
  const gates = publicationGateItems(publication);
  assert.equal(gates.length, 3);
  assert.deepEqual(gates.map((item) => item.group), ["Approval / final", "Quyền media", "Nền tảng"]);
  assert.equal(gates[2].passed, false);
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

test("renders analytics truth states and never turns missing metrics into zero", () => {
  assert.deepEqual(describeAnalytics(null), {
    label: "Chưa thu thập",
    tone: "muted",
    winnerLabel: "Chưa đủ dữ liệu",
  });
  assert.equal(
    describeAnalytics({ status: "ready", latest_assessment: { state: "winner_candidate" } }).winnerLabel,
    "Ứng viên nội dung thắng",
  );
  assert.equal(describeAnalytics({ status: "not_configured" }).tone, "warning");
  assert.equal(formatAnalyticsMetric(null), "Không có dữ liệu");
  assert.equal(formatAnalyticsMetric(0), "0");
  assert.equal(formatAnalyticsMetric(0.321, "percent"), "32.1%");
  assert.match(formatAnalyticsMetric(125000, "currency"), /125[.\s]000 VND/u);
});

test("builds a stable V2-10 metric panel from normalized nullable metrics", () => {
  const items = analyticsMetricItems({
    latest_snapshot: {
      metrics: {
        views: 1250,
        average_view_duration: 18.4,
        completion_rate: 0.61,
        ctr: null,
        followers_gained: 14,
        revenue: null,
      },
    },
  });
  assert.equal(items.length, 6);
  assert.equal(items.find((item) => item.key === "ctr").value, "Không có dữ liệu");
  assert.equal(items.find((item) => item.key === "revenue").value, "Không có dữ liệu");
  assert.equal(items.find((item) => item.key === "average_view_duration").value, "18.4 giây");
});
