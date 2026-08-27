export const TRACK_COLORS = Object.freeze({
  source: "#199c9f",
  broll: "#6f6be8",
  overlay: "#d88b36",
  generated: "#b45cc5",
  subtitles: "#e3a62f",
  original_audio: "#4e9b5f",
  voice: "#3587c7",
  music: "#a85c85",
  sfx: "#a46c42",
  metadata: "#7b8794",
});

export function formatTime(seconds) {
  const safe = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(safe / 60);
  const remaining = safe - minutes * 60;
  return `${String(minutes).padStart(2, "0")}:${remaining.toFixed(1).padStart(4, "0")}`;
}

export function pixelsPerSecond(zoom = 1) {
  return 34 * Math.max(0.5, Math.min(4, Number(zoom) || 1));
}

export function snapTime(seconds, enabled = true, interval = 0.25) {
  const safe = Math.max(0, Number(seconds) || 0);
  if (!enabled) return Number(safe.toFixed(3));
  return Number((Math.round(safe / interval) * interval).toFixed(3));
}

export function timelinePositionFromPointer(clientX, laneLeft, scrollLeft, zoom, snapping = true) {
  const raw = (Math.max(0, clientX - laneLeft) + Math.max(0, scrollLeft)) / pixelsPerSecond(zoom);
  return snapTime(raw, snapping);
}

export function clipStyle(clip, trackKind, zoom = 1) {
  const pps = pixelsPerSecond(zoom);
  return {
    left: `${Math.max(0, Number(clip.timeline_start) || 0) * pps}px`,
    width: `${Math.max(28, (Number(clip.duration) || 0) * pps)}px`,
    color: TRACK_COLORS[trackKind] ?? TRACK_COLORS.metadata,
    opacity: clip.disabled ? "0.42" : "1",
  };
}

export function canDropOnTrack(sourceType, targetType, targetLocked = false) {
  return !targetLocked && sourceType === targetType;
}

export function getClip(timeline, clipId) {
  for (const track of timeline?.snapshot?.tracks ?? []) {
    const index = track.clips.findIndex((item) => item.clip_id === clipId);
    if (index >= 0) return { track, clip: track.clips[index], index };
  }
  return null;
}

export function describePreview(preview, currentVersion) {
  if (!preview) return { label: "Chưa có preview", tone: "muted" };
  if (preview.status === "ready" && preview.timeline_version === currentVersion && preview.valid_for_current_timeline) {
    return { label: `Sẵn sàng · v${preview.timeline_version}`, tone: "safe" };
  }
  if (preview.status === "stale" || preview.timeline_version !== currentVersion) {
    return { label: `Đã cũ · v${preview.timeline_version}`, tone: "warning" };
  }
  if (["queued", "running"].includes(preview.status)) {
    return { label: `${preview.status === "queued" ? "Đang chờ" : "Đang tạo"} · ${preview.progress}%`, tone: "warning" };
  }
  return { label: preview.status === "cancelled" ? "Đã hủy" : "Tạo preview lỗi", tone: "danger" };
}

export function describeApproval(approval) {
  if (!approval) return { label: "Draft", tone: "muted" };
  const labels = {
    awaiting_review: "Chờ owner duyệt",
    approved: "Đã duyệt",
    changes_requested: "Cần chỉnh sửa",
    rejected: "Đã từ chối",
    draft: "Draft",
  };
  const tones = {
    approved: "safe",
    awaiting_review: "warning",
    changes_requested: "danger",
    rejected: "danger",
    draft: "muted",
  };
  return {
    label: labels[approval.status] ?? approval.status,
    tone: tones[approval.status] ?? "muted",
  };
}

export function describeProductionRender(render) {
  if (!render) return { label: "Chưa có render", tone: "muted", terminal: false };
  if (["queued", "running"].includes(render.status)) {
    return {
      label: `${render.status === "queued" ? "Đang chờ" : "Đang render"} · ${render.progress}%`,
      tone: "warning",
      terminal: false,
    };
  }
  if (["awaiting_review", "ready"].includes(render.status) && render.qc_status === "passed") {
    return {
      label: render.status === "ready" ? "Final sẵn sàng · QC PASS" : "Review sẵn sàng · QC PASS",
      tone: "safe",
      terminal: true,
    };
  }
  if (render.status === "stale") return { label: "Render đã cũ", tone: "warning", terminal: true };
  if (render.status === "cancelled") return { label: "Render đã hủy", tone: "muted", terminal: true };
  return { label: `Render lỗi · ${render.error_code ?? "UNKNOWN"}`, tone: "danger", terminal: true };
}

export function describePublication(publication) {
  if (!publication) return { label: "Chưa chạy", tone: "muted" };
  if (publication.status === "dry_run_succeeded") return { label: "Dry-run PASS", tone: "safe" };
  if (publication.status === "blocked") return { label: "Bị chặn an toàn", tone: "danger" };
  if (["validating", "publishing"].includes(publication.status)) return { label: "Đang kiểm tra", tone: "warning" };
  if (publication.status === "published") return { label: "Đã publish", tone: "safe" };
  return { label: publication.status === "cancelled" ? "Đã hủy" : "Thất bại", tone: "danger" };
}

export function publicationGateItems(publication) {
  if (!publication) return [];
  const groups = [
    ["Approval / final", publication.provider_validation?.checks ?? []],
    ["Quyền media", publication.rights_validation?.checks ?? []],
    ["Nền tảng", publication.platform_validation?.checks ?? []],
  ];
  return groups.flatMap(([group, checks]) => checks.map((check) => ({
    group,
    key: check.key,
    passed: Boolean(check.passed),
    code: check.code,
    message: check.message,
  })));
}

export function describeAnalytics(report) {
  if (!report || report.status === "not_started") {
    return { label: "Chưa thu thập", tone: "muted", winnerLabel: "Chưa đủ dữ liệu" };
  }
  if (["collecting"].includes(report.status)) {
    return { label: "Đang thu thập", tone: "warning", winnerLabel: "Đang đánh giá" };
  }
  if (report.status === "not_configured") {
    return { label: "Provider chưa cấu hình", tone: "warning", winnerLabel: "Không đánh giá" };
  }
  if (report.status === "failed") {
    return { label: "Thu thập lỗi", tone: "danger", winnerLabel: "Không đánh giá" };
  }
  const winnerLabels = {
    winner_candidate: "Ứng viên nội dung thắng",
    normal: "Hiệu suất bình thường",
    underperforming: "Hiệu suất thấp",
    insufficient_data: "Chưa đủ dữ liệu",
  };
  return {
    label: "Dữ liệu đã chuẩn hóa",
    tone: "safe",
    winnerLabel: winnerLabels[report.latest_assessment?.state] ?? "Chưa đủ dữ liệu",
  };
}

export function formatAnalyticsMetric(value, kind = "number") {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "Không có dữ liệu";
  const numeric = Number(value);
  if (kind === "percent") return `${(numeric * 100).toFixed(1)}%`;
  if (kind === "seconds") return `${numeric.toFixed(1)} giây`;
  if (kind === "currency") return `${Math.round(numeric).toLocaleString("vi-VN")} VND`;
  if (kind === "decimal") return numeric.toLocaleString("vi-VN", { maximumFractionDigits: 2 });
  return Math.round(numeric).toLocaleString("vi-VN");
}

export function analyticsMetricItems(report) {
  const metrics = report?.latest_snapshot?.metrics ?? {};
  return [
    { key: "views", label: "Lượt xem", value: formatAnalyticsMetric(metrics.views) },
    { key: "average_view_duration", label: "Thời lượng xem TB", value: formatAnalyticsMetric(metrics.average_view_duration, "seconds") },
    { key: "completion_rate", label: "Tỷ lệ xem hết", value: formatAnalyticsMetric(metrics.completion_rate, "percent") },
    { key: "ctr", label: "CTR", value: formatAnalyticsMetric(metrics.ctr, "percent") },
    { key: "followers_gained", label: "Follower tăng", value: formatAnalyticsMetric(metrics.followers_gained) },
    { key: "revenue", label: "Doanh thu", value: formatAnalyticsMetric(metrics.revenue, "currency") },
  ];
}

export function qcItems(report = {}) {
  if (!report || report.status !== "passed") return [];
  return [
    ["QC", "PASS"],
    ["Kích thước", `${report.width ?? "—"}×${report.height ?? "—"}`],
    ["FPS", String(report.fps ?? "—")],
    ["Video", String(report.video_codec ?? "—").toUpperCase()],
    ["Audio", String(report.audio_codec ?? "—").toUpperCase()],
    ["A/V sync", `${Number(report.av_sync_delta_seconds ?? 0).toFixed(3)}s`],
  ];
}
