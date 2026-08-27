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
