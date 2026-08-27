import {
  canDropOnTrack,
  clipStyle,
  describePreview,
  formatTime,
  getClip,
  pixelsPerSecond,
  timelinePositionFromPointer,
} from "/studio-utils.mjs?v=0.8.0";

const state = {
  workspaceId: null,
  projects: [],
  projectId: null,
  assets: [],
  analyses: [],
  mediaPlans: [],
  timeline: null,
  versions: [],
  preview: null,
  selectedClipId: null,
  panelTab: "media",
  query: "",
  zoom: 1,
  snapping: true,
  playhead: 0,
  redoStack: [],
  draggingClipId: null,
  pollTimer: null,
};

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);

class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body?.detail ?? {};
    const message = detail?.error?.message ?? detail?.message ?? body?.message ?? `API ${response.status}`;
    throw new ApiError(message, response.status, detail);
  }
  return response.status === 204 ? null : response.json();
}

function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.className = `toast show${error ? " error" : ""}`;
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => { element.className = "toast"; }, 3200);
}

function setSaveStatus(label, tone = "safe") {
  const element = $("#save-status");
  element.textContent = label;
  element.className = `pill ${tone}`;
}

function activeAnalysis() {
  if (!state.timeline) return state.analyses.find((item) => item.status === "succeeded") ?? null;
  return state.analyses.find((item) => item.analysis_id === state.timeline.source_analysis_id) ?? null;
}

function activeMediaPlan() {
  if (!state.timeline) return state.mediaPlans[0] ?? null;
  return state.mediaPlans.find((item) => item.media_plan_id === state.timeline.source_media_plan_id) ?? null;
}

function selectedClip() {
  return getClip(state.timeline, state.selectedClipId);
}

async function loadProjectList() {
  const workspaces = await api("/api/v1/workspaces");
  state.workspaceId = workspaces[0]?.workspace_id ?? null;
  if (!state.workspaceId) {
    renderNoProject("Workspace chưa được khởi tạo.", "Tạo workspace và project trước khi mở Studio.");
    return;
  }
  state.projects = await api(`/api/v1/workspaces/${state.workspaceId}/projects`);
  const select = $("#project-select");
  select.innerHTML = state.projects.length
    ? state.projects.map((item) => `<option value="${escapeHtml(item.project_id)}">${escapeHtml(item.name)}</option>`).join("")
    : `<option value="">Chưa có dự án</option>`;
  const stored = window.localStorage.getItem("npd-studio-project");
  state.projectId = state.projects.some((item) => item.project_id === stored)
    ? stored
    : state.projects[0]?.project_id ?? null;
  select.value = state.projectId ?? "";
  if (!state.projectId) {
    renderNoProject("Chưa có project để dựng.", "Tạo draft project từ Trend Radar hoặc API trước khi mở Studio.");
    return;
  }
  await loadProject();
}

async function loadProject({ quiet = false } = {}) {
  if (!state.projectId) return;
  stopPreviewPolling();
  if (!quiet) setSaveStatus("Đang tải…", "muted");
  try {
    const [assets, analyses, mediaPlans, timeline] = await Promise.all([
      api(`/api/v1/projects/${state.projectId}/assets`),
      api(`/api/v1/projects/${state.projectId}/analyses`),
      api(`/api/v1/projects/${state.projectId}/media-plans`),
      api(`/api/v1/projects/${state.projectId}/timeline`).catch((error) => {
        if (error.status === 404) return null;
        throw error;
      }),
    ]);
    Object.assign(state, { assets, analyses, mediaPlans, timeline, selectedClipId: null, redoStack: [] });
    state.versions = timeline ? await api(`/api/v1/projects/${state.projectId}/timeline/versions`) : [];
    state.preview = null;
    if (timeline?.latest_preview_id) {
      state.preview = await api(`/api/v1/projects/${state.projectId}/previews/${timeline.latest_preview_id}`).catch(() => null);
    }
    state.playhead = Math.min(state.playhead, timeline?.snapshot?.duration_seconds ?? 0);
    render();
    if (["queued", "running"].includes(state.preview?.status)) startPreviewPolling();
    setSaveStatus("Đã lưu", "safe");
  } catch (error) {
    setSaveStatus("Lỗi tải", "danger");
    toast(error.message, true);
  }
}

function renderNoProject(title, description) {
  $("#studio-workspace").hidden = true;
  $("#empty-state").hidden = false;
  $("#empty-title").textContent = title;
  $("#empty-description").textContent = description;
  $("#create-timeline-button").hidden = true;
}

function render() {
  if (!state.timeline) {
    const analysis = activeAnalysis();
    renderNoProject(
      analysis ? "Kết quả phân tích đã sẵn sàng." : "Project chưa có phân tích Auto Edit.",
      analysis
        ? "Khởi tạo timeline từ scene, transcript, khoảng lặng và B-roll đã lưu."
        : "Hoàn thành upload và Auto Edit analysis ở luồng V2-04 trước khi dựng.",
    );
    $("#create-timeline-button").hidden = !analysis;
    return;
  }
  $("#empty-state").hidden = true;
  $("#studio-workspace").hidden = false;
  renderSummary();
  renderBrowser();
  renderTimeline();
  renderInspector();
  renderPreview();
}

function renderSummary() {
  const clips = state.timeline.snapshot.tracks.flatMap((track) => track.clips);
  const analysis = activeAnalysis();
  const previewState = describePreview(state.preview, state.timeline.current_version);
  $("#metric-version").textContent = `v${state.timeline.current_version}`;
  $("#metric-version-note").textContent = `${state.versions.length} phiên bản đã lưu`;
  $("#metric-duration").textContent = formatTime(state.timeline.snapshot.duration_seconds);
  $("#metric-clips").textContent = clips.length;
  $("#metric-scenes").textContent = `${analysis?.scenes?.length ?? 0} scene AI`;
  $("#metric-preview").textContent = previewState.label.split(" · ")[0];
}

function renderBrowser() {
  document.querySelectorAll("[data-panel-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.panelTab === state.panelTab);
  });
  const query = state.query.trim().toLocaleLowerCase("vi");
  const matches = (value) => !query || String(value ?? "").toLocaleLowerCase("vi").includes(query);
  const panel = $("#browser-content");
  const analysis = activeAnalysis();
  if (state.panelTab === "media") {
    const assets = state.assets.filter((item) => matches(`${item.filename} ${item.kind} ${item.asset_class}`));
    panel.innerHTML = assets.length ? `<div class="browser-list">${assets.map((item) => `
      <button class="browser-item" data-asset-id="${escapeHtml(item.asset_id)}">
        <span class="browser-thumb">${item.content_type.startsWith("video/") ? "▶" : item.content_type.startsWith("image/") ? "▧" : "♪"}</span>
        <span><strong>${escapeHtml(item.filename)}</strong><small>${escapeHtml(item.kind)} · ${formatBytes(item.size_bytes)}</small></span>
      </button>`).join("")}</div>` : browserEmpty("Chưa có media phù hợp.");
  } else if (state.panelTab === "transcript") {
    const segments = (analysis?.transcript?.segments ?? []).filter((item) => matches(item.text));
    panel.innerHTML = segments.length ? segments.map((item) => `
      <article class="transcript-item" data-seek="${item.start_seconds}"><time>${formatTime(item.start_seconds)} → ${formatTime(item.end_seconds)}</time><p>${escapeHtml(item.text)}</p></article>
    `).join("") : browserEmpty("Project chưa có transcript hoặc không khớp tìm kiếm.");
  } else if (state.panelTab === "scenes") {
    const scenes = (analysis?.scenes ?? []).filter((item) => matches(`${item.semantic_label} ${item.description}`));
    panel.innerHTML = scenes.length ? scenes.map((item) => `
      <article class="scene-item" data-seek="${item.start_seconds}"><time>Cảnh ${item.ordinal + 1} · ${formatTime(item.start_seconds)}</time><p><strong>${escapeHtml(item.semantic_label)}</strong><br>${escapeHtml(item.description)}</p></article>
    `).join("") : browserEmpty("Chưa có scene AI phù hợp.");
  } else {
    const items = (activeMediaPlan()?.items ?? []).filter((item) => matches(`${item.broll?.search_query} ${item.strategy}`));
    panel.innerHTML = items.length ? items.map((item) => `
      <article class="scene-item" data-seek="${item.broll.placement_start_seconds}"><time>${formatTime(item.broll.placement_start_seconds)} · ${escapeHtml(item.status)}</time><p><strong>${escapeHtml(item.strategy)}</strong><br>${escapeHtml(item.broll.search_query)}</p></article>
    `).join("") : browserEmpty("Chưa có media plan/B-roll. Timeline vẫn dùng video gốc.");
  }
}

function browserEmpty(message) {
  return `<div class="browser-empty">${escapeHtml(message)}</div>`;
}

function renderTimeline() {
  const snapshot = state.timeline.snapshot;
  const pps = pixelsPerSecond(state.zoom);
  const laneWidth = Math.max(650, snapshot.duration_seconds * pps + 120);
  const canvas = $("#timeline-canvas");
  canvas.style.width = `${145 + laneWidth}px`;
  $("#timeline-ruler").style.width = `${laneWidth}px`;
  const ticks = [];
  const interval = snapshot.duration_seconds > 180 ? 10 : snapshot.duration_seconds > 60 ? 5 : 1;
  for (let second = 0; second <= Math.ceil(snapshot.duration_seconds + 2); second += interval) {
    const major = second % (interval * 5) === 0;
    ticks.push(`<span class="ruler-tick ${major ? "major" : ""}" style="left:${second * pps}px"><span>${major ? formatTime(second) : ""}</span></span>`);
  }
  $("#timeline-ruler").innerHTML = ticks.join("");
  $("#timeline-tracks").innerHTML = snapshot.tracks.map((track) => `
    <div class="track-row" data-track-row="${escapeHtml(track.track_id)}">
      <div class="track-head"><div><strong>${escapeHtml(track.label)}</strong><small>${escapeHtml(track.type)} · ${track.clips.length} clip${track.type === "audio" ? " · waveform proxy" : ""}</small></div>
        <div class="track-controls">
          <button data-track-action="lock" data-track-id="${escapeHtml(track.track_id)}" class="${track.locked ? "active" : ""}" title="Khóa track">${track.locked ? "🔒" : "◇"}</button>
          <button data-track-action="mute" data-track-id="${escapeHtml(track.track_id)}" class="${track.muted ? "active" : ""}" title="Tắt tiếng">M</button>
        </div>
      </div>
      <div class="track-lane" data-track-id="${escapeHtml(track.track_id)}" data-track-type="${escapeHtml(track.type)}" data-track-locked="${track.locked}" style="width:${laneWidth}px">
        ${track.clips.map((clip) => {
          const style = clipStyle(clip, track.kind, state.zoom);
          return `<button draggable="${!track.locked}" class="timeline-clip ${track.type === "audio" ? "waveform" : ""} ${clip.disabled ? "disabled" : ""} ${clip.clip_id === state.selectedClipId ? "selected" : ""}" data-clip-id="${escapeHtml(clip.clip_id)}" data-track-type="${escapeHtml(track.type)}" style="left:${style.left};width:${style.width};background-color:${style.color};opacity:${style.opacity}"><strong>${escapeHtml(clip.label)}</strong><small>${formatTime(clip.timeline_start)} · ${clip.duration.toFixed(1)}s</small></button>`;
        }).join("")}
      </div>
    </div>`).join("");
  $("#timeline-playhead").style.left = `${145 + state.playhead * pps}px`;
  $("#playhead-range").max = snapshot.duration_seconds;
  $("#playhead-range").value = state.playhead;
  $("#playhead-label").textContent = formatTime(state.playhead);
  $("#duration-label").textContent = formatTime(snapshot.duration_seconds);
  $("#undo-button").disabled = state.timeline.current_version <= 1;
  $("#redo-button").disabled = !state.redoStack.length;
}

function renderInspector() {
  const selection = selectedClip();
  const controls = [
    "#split-button",
    "#duplicate-button",
    "#reorder-up-button",
    "#reorder-down-button",
    "#toggle-clip-button",
    "#delete-button",
  ];
  controls.forEach((selector) => { $(selector).disabled = !selection || selection.track.locked; });
  $("#inspector-empty").hidden = Boolean(selection);
  $("#clip-inspector").hidden = !selection;
  if (!selection) return;
  const { clip, track } = selection;
  $("#clip-label").value = clip.label;
  $("#clip-source-start").value = clip.source_start;
  $("#clip-source-end").value = clip.source_end;
  $("#clip-timeline-start").value = clip.timeline_start;
  $("#clip-speed").value = clip.speed;
  $("#clip-opacity").value = clip.opacity;
  $("#clip-volume").value = clip.volume;
  $("#clip-crop-x").value = clip.crop.x;
  $("#clip-crop-y").value = clip.crop.y;
  $("#clip-crop-width").value = clip.crop.width;
  $("#clip-crop-height").value = clip.crop.height;
  $("#clip-transform-x").value = clip.transform.x;
  $("#clip-transform-y").value = clip.transform.y;
  $("#clip-transform-scale").value = clip.transform.scale;
  $("#clip-transform-rotation").value = clip.transform.rotation_degrees;
  [
    "#clip-source-start", "#clip-source-end", "#clip-timeline-start", "#clip-speed", "#clip-opacity", "#clip-volume",
    "#clip-crop-x", "#clip-crop-y", "#clip-crop-width", "#clip-crop-height",
    "#clip-transform-x", "#clip-transform-y", "#clip-transform-scale", "#clip-transform-rotation",
  ].forEach((selector) => {
    $(selector).disabled = track.locked;
  });
  $("#clip-inspector button[type=submit]").disabled = track.locked;
  const clipIndex = track.clips.findIndex((item) => item.clip_id === clip.clip_id);
  $("#reorder-up-button").disabled = track.locked || clipIndex <= 0;
  $("#reorder-down-button").disabled = track.locked || clipIndex < 0 || clipIndex >= track.clips.length - 1;
  $("#toggle-clip-button").textContent = clip.disabled ? "Hiện clip" : "Ẩn clip";
}

function renderPreview() {
  const currentVersion = state.timeline?.current_version ?? null;
  const description = describePreview(state.preview, currentVersion);
  const pill = $("#preview-status");
  pill.textContent = description.label;
  pill.className = `pill ${description.tone}`;
  const video = $("#preview-video");
  const placeholder = $("#preview-placeholder");
  const playable = state.preview?.playback_url && ["ready", "stale"].includes(state.preview.status) && state.preview.manifest?.playable !== false;
  if (playable) {
    const nextSource = `${state.preview.playback_url}?version=${state.preview.timeline_version}`;
    if (!video.src.endsWith(nextSource)) video.src = nextSource;
    video.hidden = false;
    placeholder.hidden = true;
  } else {
    video.hidden = true;
    placeholder.hidden = false;
  }
  const busy = ["queued", "running"].includes(state.preview?.status);
  $("#preview-button").disabled = busy;
  $("#preview-button").textContent = busy ? `Đang tạo ${state.preview.progress}%` : state.preview?.status === "stale" ? "Tạo lại preview" : "Tạo preview 540p";
  $("#cancel-preview-button").disabled = !busy;
  $("#preview-title").textContent = currentVersion ? `Timeline v${currentVersion}` : "Timeline hiện tại";
}

async function createTimeline() {
  const analysis = activeAnalysis();
  if (!analysis) return;
  const plan = state.mediaPlans.find((item) => item.analysis_id === analysis.analysis_id) ?? null;
  const button = $("#create-timeline-button");
  button.disabled = true;
  button.textContent = "Đang tạo timeline…";
  try {
    state.timeline = await api(`/api/v1/projects/${state.projectId}/timeline`, {
      method: "POST",
      body: JSON.stringify({
        analysis_id: analysis.analysis_id,
        media_plan_id: plan?.media_plan_id ?? null,
        actor_ref: "studio-user",
      }),
    });
    state.versions = await api(`/api/v1/projects/${state.projectId}/timeline/versions`);
    render();
    toast("Timeline AI đã được tạo từ evidence đã lưu. Media gốc không bị thay đổi.");
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "Khởi tạo timeline AI";
  }
}

async function mutate(operations, reason, { preserveRedo = false } = {}) {
  if (!state.timeline || !operations.length) return;
  setSaveStatus("Đang lưu…", "warning");
  const priorPreview = state.preview;
  try {
    state.timeline = await api(`/api/v1/projects/${state.projectId}/timeline`, {
      method: "PUT",
      body: JSON.stringify({
        expected_version: state.timeline.current_version,
        operations,
        actor_ref: "studio-user",
        reason,
      }),
    });
    if (!preserveRedo) state.redoStack = [];
    state.versions = await api(`/api/v1/projects/${state.projectId}/timeline/versions`);
    if (priorPreview) state.preview = { ...priorPreview, status: "stale", valid_for_current_timeline: false };
    if (state.selectedClipId && !selectedClip()) state.selectedClipId = null;
    state.playhead = Math.min(state.playhead, state.timeline.snapshot.duration_seconds);
    render();
    setSaveStatus("Đã lưu", "safe");
  } catch (error) {
    if (error.status === 409) {
      $("#timeline-conflict").textContent = "Có phiên bản mới — Studio đã nạp lại";
      toast("Timeline đã thay đổi ở phiên khác. Đã nạp bản mới nhất.", true);
      await loadProject({ quiet: true });
    } else {
      setSaveStatus("Chưa lưu", "danger");
      toast(error.message, true);
    }
  }
}

async function restoreVersion(targetVersion, { isUndo = false } = {}) {
  if (!state.timeline) return;
  const previousVersion = state.timeline.current_version;
  setSaveStatus("Đang khôi phục…", "warning");
  try {
    state.timeline = await api(`/api/v1/projects/${state.projectId}/timeline/restore`, {
      method: "POST",
      body: JSON.stringify({
        expected_version: previousVersion,
        restore_version: targetVersion,
        actor_ref: "studio-user",
      }),
    });
    if (isUndo) state.redoStack.push(previousVersion);
    state.preview = state.preview ? { ...state.preview, status: "stale", valid_for_current_timeline: false } : null;
    state.versions = await api(`/api/v1/projects/${state.projectId}/timeline/versions`);
    state.selectedClipId = null;
    render();
    setSaveStatus("Đã lưu", "safe");
  } catch (error) {
    setSaveStatus("Chưa lưu", "danger");
    toast(error.message, true);
  }
}

async function createPreview() {
  if (!state.timeline) return;
  try {
    state.preview = await api(`/api/v1/projects/${state.projectId}/preview`, {
      method: "POST",
      body: JSON.stringify({ timeline_version: state.timeline.current_version, actor_ref: "studio-user" }),
    });
    renderPreview();
    startPreviewPolling();
    toast("Preview đã vào hàng đợi nội bộ. Không có publish hoặc API trả phí.");
  } catch (error) {
    toast(error.message, true);
  }
}

function startPreviewPolling() {
  stopPreviewPolling();
  if (!state.preview) return;
  state.pollTimer = window.setInterval(async () => {
    try {
      state.preview = await api(`/api/v1/projects/${state.projectId}/previews/${state.preview.preview_id}`);
      renderSummary();
      renderPreview();
      if (!["queued", "running"].includes(state.preview.status)) {
        stopPreviewPolling();
        toast(state.preview.status === "ready" ? "Preview timeline đã sẵn sàng." : `Preview kết thúc: ${state.preview.status}`, state.preview.status !== "ready");
      }
    } catch (error) {
      stopPreviewPolling();
      toast(error.message, true);
    }
  }, 1000);
}

function stopPreviewPolling() {
  if (state.pollTimer) window.clearInterval(state.pollTimer);
  state.pollTimer = null;
}

async function cancelPreview() {
  if (!state.preview) return;
  try {
    state.preview = await api(`/api/v1/projects/${state.projectId}/previews/${state.preview.preview_id}/cancel`, { method: "POST" });
    stopPreviewPolling();
    renderPreview();
    renderSummary();
    toast("Đã gửi yêu cầu hủy preview.");
  } catch (error) { toast(error.message, true); }
}

function setPlayhead(value, syncVideo = true) {
  state.playhead = Math.max(0, Math.min(Number(value) || 0, state.timeline?.snapshot?.duration_seconds ?? 0));
  $("#playhead-range").value = state.playhead;
  $("#playhead-label").textContent = formatTime(state.playhead);
  if (state.timeline) $("#timeline-playhead").style.left = `${145 + state.playhead * pixelsPerSecond(state.zoom)}px`;
  const video = $("#preview-video");
  if (syncVideo && !video.hidden && Number.isFinite(video.duration)) video.currentTime = Math.min(state.playhead, video.duration);
}

function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

$("#project-select").addEventListener("change", async (event) => {
  state.projectId = event.target.value || null;
  window.localStorage.setItem("npd-studio-project", state.projectId ?? "");
  await loadProject();
});
$("#reload-button").addEventListener("click", () => loadProject());
$("#create-timeline-button").addEventListener("click", createTimeline);
$("#preview-button").addEventListener("click", createPreview);
$("#cancel-preview-button").addEventListener("click", cancelPreview);
$("#menu-button").addEventListener("click", () => $(".sidebar").classList.toggle("open"));

document.querySelector(".panel-tabs").addEventListener("click", (event) => {
  const button = event.target.closest("[data-panel-tab]");
  if (!button) return;
  state.panelTab = button.dataset.panelTab;
  renderBrowser();
});
$("#browser-search").addEventListener("input", (event) => { state.query = event.target.value; renderBrowser(); });
$("#browser-content").addEventListener("click", (event) => {
  const seek = event.target.closest("[data-seek]");
  if (seek) setPlayhead(Number(seek.dataset.seek));
});

$("#timeline-tracks").addEventListener("click", async (event) => {
  const trackAction = event.target.closest("[data-track-action]");
  if (trackAction) {
    const track = state.timeline.snapshot.tracks.find((item) => item.track_id === trackAction.dataset.trackId);
    if (!track) return;
    const property = trackAction.dataset.trackAction;
    await mutate([{
      type: "set_track_state",
      track_id: track.track_id,
      ...(property === "lock" ? { locked: !track.locked } : { muted: !track.muted }),
    }], `track-${property}`);
    return;
  }
  const clip = event.target.closest("[data-clip-id]");
  if (!clip) return;
  state.selectedClipId = clip.dataset.clipId;
  renderTimeline();
  renderInspector();
});
$("#timeline-tracks").addEventListener("dragstart", (event) => {
  const clip = event.target.closest("[data-clip-id]");
  if (!clip || clip.getAttribute("draggable") !== "true") return;
  event.dataTransfer.effectAllowed = "move";
  state.draggingClipId = clip.dataset.clipId;
  event.dataTransfer.setData("text/plain", clip.dataset.clipId);
  event.dataTransfer.setData("application/x-npd-track-type", clip.dataset.trackType);
});
$("#timeline-tracks").addEventListener("dragover", (event) => {
  const lane = event.target.closest("[data-track-id]");
  if (!lane) return;
  const sourceType = getClip(state.timeline, state.draggingClipId)?.track?.type;
  if (canDropOnTrack(sourceType || lane.dataset.trackType, lane.dataset.trackType, lane.dataset.trackLocked === "true")) {
    event.preventDefault();
    lane.classList.add("drag-target");
  }
});
$("#timeline-tracks").addEventListener("dragend", () => {
  state.draggingClipId = null;
  document.querySelectorAll(".drag-target").forEach((item) => item.classList.remove("drag-target"));
});
$("#timeline-tracks").addEventListener("dragleave", (event) => event.target.closest("[data-track-id]")?.classList.remove("drag-target"));
$("#timeline-tracks").addEventListener("drop", async (event) => {
  const lane = event.target.closest("[data-track-id]");
  document.querySelectorAll(".drag-target").forEach((item) => item.classList.remove("drag-target"));
  if (!lane) return;
  event.preventDefault();
  const clipId = event.dataTransfer.getData("text/plain");
  state.draggingClipId = null;
  const selection = getClip(state.timeline, clipId);
  if (!selection || !canDropOnTrack(selection.track.type, lane.dataset.trackType, lane.dataset.trackLocked === "true")) return;
  const start = timelinePositionFromPointer(event.clientX, lane.getBoundingClientRect().left, 0, state.zoom, state.snapping);
  state.selectedClipId = clipId;
  await mutate([{ type: "move", clip_id: clipId, target_track_id: lane.dataset.trackId, timeline_start: start }], "drag-drop");
});

$("#timeline-ruler").addEventListener("click", (event) => {
  const rect = event.currentTarget.getBoundingClientRect();
  setPlayhead(timelinePositionFromPointer(event.clientX, rect.left, 0, state.zoom, state.snapping));
});
$("#playhead-range").addEventListener("input", (event) => setPlayhead(event.target.value));
$("#zoom-range").addEventListener("input", (event) => { state.zoom = Number(event.target.value); renderTimeline(); });
$("#snap-button").addEventListener("click", (event) => {
  state.snapping = !state.snapping;
  event.currentTarget.classList.toggle("active", state.snapping);
  event.currentTarget.setAttribute("aria-pressed", String(state.snapping));
  event.currentTarget.textContent = state.snapping ? "⌁ Snap 0.25s" : "⌁ Snap off";
});

$("#clip-inspector").addEventListener("submit", async (event) => {
  event.preventDefault();
  const selection = selectedClip();
  if (!selection) return;
  await mutate([
    {
      type: "trim",
      clip_id: selection.clip.clip_id,
      source_start: Number($("#clip-source-start").value),
      source_end: Number($("#clip-source-end").value),
      timeline_start: Number($("#clip-timeline-start").value),
    },
    {
      type: "set_clip_properties",
      clip_id: selection.clip.clip_id,
      speed: Number($("#clip-speed").value),
      opacity: Number($("#clip-opacity").value),
      volume: Number($("#clip-volume").value),
      crop: {
        x: Number($("#clip-crop-x").value),
        y: Number($("#clip-crop-y").value),
        width: Number($("#clip-crop-width").value),
        height: Number($("#clip-crop-height").value),
      },
      transform: {
        x: Number($("#clip-transform-x").value),
        y: Number($("#clip-transform-y").value),
        scale: Number($("#clip-transform-scale").value),
        rotation_degrees: Number($("#clip-transform-rotation").value),
      },
    },
  ], "inspector-edit");
});
$("#split-button").addEventListener("click", async () => {
  const selection = selectedClip();
  if (!selection) return;
  await mutate([{ type: "split", clip_id: selection.clip.clip_id, at_seconds: state.playhead }], "split-at-playhead");
});
$("#duplicate-button").addEventListener("click", async () => {
  const selection = selectedClip();
  if (!selection) return;
  await mutate([{ type: "duplicate", clip_id: selection.clip.clip_id, timeline_start: selection.clip.timeline_start + selection.clip.duration }], "duplicate-clip");
});
$("#reorder-up-button").addEventListener("click", async () => {
  const selection = selectedClip();
  if (!selection) return;
  const currentIndex = selection.track.clips.findIndex((item) => item.clip_id === selection.clip.clip_id);
  if (currentIndex > 0) {
    await mutate([{ type: "reorder", clip_id: selection.clip.clip_id, target_index: currentIndex - 1 }], "reorder-clip");
  }
});
$("#reorder-down-button").addEventListener("click", async () => {
  const selection = selectedClip();
  if (!selection) return;
  const currentIndex = selection.track.clips.findIndex((item) => item.clip_id === selection.clip.clip_id);
  if (currentIndex >= 0 && currentIndex < selection.track.clips.length - 1) {
    await mutate([{ type: "reorder", clip_id: selection.clip.clip_id, target_index: currentIndex + 1 }], "reorder-clip");
  }
});
$("#toggle-clip-button").addEventListener("click", async () => {
  const selection = selectedClip();
  if (!selection) return;
  await mutate([{ type: "disable", clip_id: selection.clip.clip_id, disabled: !selection.clip.disabled }], "toggle-clip");
});
$("#delete-button").addEventListener("click", async () => {
  const selection = selectedClip();
  if (!selection) return;
  await mutate([{ type: "delete", clip_id: selection.clip.clip_id }], "delete-from-timeline");
});
$("#undo-button").addEventListener("click", async () => {
  if (state.timeline?.current_version > 1) await restoreVersion(state.timeline.current_version - 1, { isUndo: true });
});
$("#redo-button").addEventListener("click", async () => {
  const target = state.redoStack.pop();
  if (target) await restoreVersion(target);
});

$("#play-button").addEventListener("click", () => {
  const video = $("#preview-video");
  if (video.hidden) return toast("Hãy tạo preview trước khi phát.");
  if (video.paused) video.play(); else video.pause();
});
$("#back-button").addEventListener("click", () => setPlayhead(state.playhead - 1));
$("#preview-video").addEventListener("timeupdate", (event) => setPlayhead(event.target.currentTime, false));

window.addEventListener("beforeunload", stopPreviewPolling);
loadProjectList().catch((error) => { renderNoProject("Không tải được Studio.", error.message); toast(error.message, true); });
