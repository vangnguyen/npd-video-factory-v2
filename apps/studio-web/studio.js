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
  getClip,
  pixelsPerSecond,
  publicationGateItems,
  qcItems,
  timelinePositionFromPointer,
} from "/studio-utils.mjs?v=0.11.0";

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
  productionPackage: null,
  publications: [],
  publishingPlatforms: [],
  activePublication: null,
  analyticsReport: null,
  analyticsProviders: [],
  activeAnalyticsSync: null,
  publishRequestSignature: null,
  publishIdempotencyKey: null,
  activeProductionRender: null,
  selectedClipId: null,
  panelTab: "media",
  query: "",
  zoom: 1,
  snapping: true,
  playhead: 0,
  redoStack: [],
  draggingClipId: null,
  pollTimer: null,
  productionPollTimer: null,
  analyticsPollTimer: null,
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
  stopProductionPolling();
  stopAnalyticsPolling();
  if (!quiet) setSaveStatus("Đang tải…", "muted");
  try {
    const [assets, analyses, mediaPlans, timeline, publications, publishingPlatforms, analyticsReport, analyticsProviders] = await Promise.all([
      api(`/api/v1/projects/${state.projectId}/assets`),
      api(`/api/v1/projects/${state.projectId}/analyses`),
      api(`/api/v1/projects/${state.projectId}/media-plans`),
      api(`/api/v1/projects/${state.projectId}/timeline`).catch((error) => {
        if (error.status === 404) return null;
        throw error;
      }),
      api(`/api/v1/projects/${state.projectId}/publications`),
      api("/api/v1/publishing-platforms"),
      api(`/api/v1/projects/${state.projectId}/analytics`),
      api("/api/v1/analytics-providers"),
    ]);
    Object.assign(state, {
      assets,
      analyses,
      mediaPlans,
      timeline,
      publications,
      publishingPlatforms,
      activePublication: publications[0] ?? null,
      analyticsReport,
      analyticsProviders,
      activeAnalyticsSync: analyticsReport.latest_sync,
      selectedClipId: null,
      redoStack: [],
      publishRequestSignature: null,
      publishIdempotencyKey: null,
    });
    state.versions = timeline ? await api(`/api/v1/projects/${state.projectId}/timeline/versions`) : [];
    state.preview = null;
    state.productionPackage = null;
    state.activeProductionRender = null;
    if (timeline?.latest_preview_id) {
      state.preview = await api(`/api/v1/projects/${state.projectId}/previews/${timeline.latest_preview_id}`).catch(() => null);
    }
    if (timeline) {
      state.productionPackage = await api(`/api/v1/projects/${state.projectId}/production-package`).catch((error) => {
        if (error.status === 404) return null;
        throw error;
      });
      state.activeProductionRender = state.productionPackage?.latest_final_render
        ?? state.productionPackage?.latest_review_render
        ?? null;
    }
    state.playhead = Math.min(state.playhead, timeline?.snapshot?.duration_seconds ?? 0);
    render();
    if (["queued", "running"].includes(state.preview?.status)) startPreviewPolling();
    if (["queued", "running"].includes(state.activeProductionRender?.status)) startProductionPolling();
    if (["scheduled", "queued", "running", "retry_scheduled"].includes(state.activeAnalyticsSync?.status)) startAnalyticsPolling();
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
  renderProduction();
  renderPublishing();
  renderAnalytics();
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
  $("#metric-approval").textContent = describeApproval(state.productionPackage?.approval).label;
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

function renderProduction() {
  const packageState = state.productionPackage;
  const empty = $("#production-empty");
  const content = $("#production-content");
  const packagePill = $("#production-package-status");
  const packageButton = $("#production-package-button");
  if (!packageState) {
    empty.hidden = false;
    content.hidden = true;
    packagePill.textContent = "Chưa khởi tạo";
    packagePill.className = "pill muted";
    packageButton.textContent = "Khởi tạo gói dựng";
    return;
  }
  empty.hidden = true;
  content.hidden = false;
  packagePill.textContent = packageState.current_for_timeline
    ? `Timeline v${packageState.timeline_version}`
    : `Cần làm mới từ timeline v${state.timeline.current_version}`;
  packagePill.className = `pill ${packageState.current_for_timeline ? "safe" : "warning"}`;
  packageButton.textContent = packageState.current_for_timeline ? "Làm mới gói dựng" : "Đồng bộ timeline mới";

  $("#subtitle-version").textContent = `v${packageState.subtitle.version}`;
  $("#subtitle-list").innerHTML = packageState.subtitle.cues.map((cue) => `
    <div class="subtitle-row" data-cue-id="${escapeHtml(cue.cue_id)}">
      <label>Bắt đầu<input data-cue-field="start" type="number" min="0" step="0.01" value="${Number(cue.start_seconds).toFixed(2)}" /></label>
      <label>Kết thúc<input data-cue-field="end" type="number" min="0.05" step="0.01" value="${Number(cue.end_seconds).toFixed(2)}" /></label>
      <label>Nội dung<textarea data-cue-field="text" maxlength="180">${escapeHtml(cue.text)}</textarea></label>
    </div>
  `).join("");
  $("#subtitle-position").value = packageState.subtitle.style.position;
  $("#subtitle-animation").value = packageState.subtitle.style.animation;
  $("#subtitle-font-size").value = packageState.subtitle.style.font_size;
  $("#subtitle-safe-margin").value = packageState.subtitle.style.safe_margin_percent;

  const mix = packageState.audio_mix.config;
  $("#audio-version").textContent = `v${packageState.audio_mix.version}`;
  $("#audio-provider-status").textContent = `TTS: ${packageState.audio_mix.provider_status === "configured" ? "đã cấu hình" : "chưa cấu hình"} · 48 kHz · limiter ${mix.limiter_peak_db} dB`;
  $("#voice-enabled").checked = mix.voice.enabled;
  $("#voice-speed").value = mix.voice.speed;
  $("#voice-speed-output").textContent = `${Number(mix.voice.speed).toFixed(2)}×`;
  $("#voice-gain").value = mix.voice.gain_db;
  $("#music-gain").value = mix.music.gain_db;
  $("#music-ducking").value = mix.music.ducking_db;
  const licensedAudio = state.assets.filter((asset) => {
    const rights = String(asset.provenance?.rights_status ?? "").toLowerCase();
    return asset.content_type.startsWith("audio/") && ["owned", "licensed", "public_domain", "royalty_free"].includes(rights);
  });
  $("#music-asset").innerHTML = `<option value="">Không dùng nhạc</option>${licensedAudio.map((asset) => `
    <option value="${escapeHtml(asset.asset_id)}">${escapeHtml(asset.filename)} · ${escapeHtml(asset.provenance.rights_status)}</option>
  `).join("")}`;
  $("#music-asset").value = mix.music.asset_id ?? "";

  const approvalState = describeApproval(packageState.approval);
  $("#approval-status").textContent = approvalState.label;
  $("#approval-status").className = `pill ${approvalState.tone}`;
  const render = state.activeProductionRender
    ?? packageState.latest_final_render
    ?? packageState.latest_review_render;
  const renderState = describeProductionRender(render);
  $("#render-summary").textContent = render
    ? `${renderState.label} · ${render.render_kind === "final" ? "Final" : "Review"} v${render.version} · timeline v${render.timeline_version} / subtitle v${render.subtitle_version} / audio v${render.audio_version}`
    : renderState.label;
  const productionVideo = $("#production-video");
  if (render?.playback_url && ["awaiting_review", "ready"].includes(render.status)) {
    productionVideo.src = `${render.playback_url}?render=${encodeURIComponent(render.render_id)}`;
    productionVideo.hidden = false;
  } else {
    productionVideo.hidden = true;
    productionVideo.removeAttribute("src");
  }
  $("#qc-summary").innerHTML = qcItems(render?.qc_report).map(([label, value]) => `
    <div class="qc-item">${escapeHtml(label)}<strong>${escapeHtml(value)}</strong></div>
  `).join("");
  const busy = ["queued", "running"].includes(render?.status);
  const reviewReady = packageState.latest_review_render?.status === "awaiting_review"
    && packageState.latest_review_render?.qc_status === "passed";
  const awaitingDecision = packageState.approval?.status === "awaiting_review";
  const approved = packageState.approval?.status === "approved";
  $("#review-render-button").disabled = busy || !packageState.current_for_timeline;
  $("#review-render-button").textContent = busy && render?.render_kind === "review"
    ? `Đang render ${render.progress}%`
    : "Tạo review A/V 540p";
  $("#request-approval-button").disabled = busy || !reviewReady || awaitingDecision || approved;
  $("#approve-button").disabled = !awaitingDecision;
  $("#changes-button").disabled = !awaitingDecision;
  $("#final-render-button").disabled = busy || !approved;
  $("#final-render-button").textContent = busy && render?.render_kind === "final"
    ? `Đang render ${render.progress}%`
    : "Render final đã duyệt";
  renderPublishing();
}

function selectedPublishingPlatform() {
  const key = $("#publishing-platform")?.value ?? "youtube";
  return state.publishingPlatforms.find((item) => item.platform === key) ?? null;
}

function renderPublishing() {
  const packageState = state.productionPackage;
  const finalRender = packageState?.latest_final_render ?? null;
  const approved = packageState?.approval?.status === "approved";
  const eligible = Boolean(
    packageState?.current_for_timeline
    && approved
    && finalRender?.status === "ready"
    && finalRender?.qc_status === "passed",
  );
  const platformState = selectedPublishingPlatform();
  const liveEnabled = Boolean(platformState?.live_execution_enabled);
  $("#publishing-live-status").textContent = liveEnabled ? "Owner gate đang bật" : "Live bị khóa";
  $("#publishing-live-status").className = `pill ${liveEnabled ? "warning" : "muted"}`;
  $("#publishing-dry-run-button").disabled = !eligible;
  if (!$("#publishing-title").value && state.projectId) {
    const project = state.projects.find((item) => item.project_id === state.projectId);
    $("#publishing-title").value = project?.name ?? "NPD Video";
  }

  const publication = state.activePublication ?? state.publications[0] ?? null;
  const status = describePublication(publication);
  $("#publishing-status").textContent = status.label;
  $("#publishing-status").className = `pill ${status.tone}`;
  const gates = publicationGateItems(publication);
  if (gates.length) {
    $("#publishing-gates").innerHTML = gates.map((item) => `
      <div class="publishing-gate ${item.passed ? "passed" : "failed"}">
        <span>${item.passed ? "✓" : "!"}</span>
        <div><small>${escapeHtml(item.group)} · ${escapeHtml(item.code)}</small><strong>${escapeHtml(item.message)}</strong></div>
      </div>
    `).join("");
  } else {
    const capability = platformState?.capability;
    $("#publishing-gates").innerHTML = `
      <div class="publishing-gate ${eligible ? "passed" : "pending"}">
        <span>${eligible ? "✓" : "…"}</span>
        <div><small>Điều kiện đầu vào</small><strong>${eligible ? "Final render đã duyệt và QC PASS." : "Cần final render đã duyệt và QC PASS."}</strong></div>
      </div>
      <div class="publishing-gate pending">
        <span>i</span>
        <div><small>Capability ${escapeHtml(capability?.version ?? "—")}</small><strong>Internal safe profile · phải xác minh lại trước live.</strong></div>
      </div>
    `;
  }
  $("#publication-history").innerHTML = state.publications.length
    ? `<strong>Receipt gần đây</strong>${state.publications.slice(0, 5).map((item) => {
      const itemStatus = describePublication(item);
      return `<button type="button" data-publication-id="${escapeHtml(item.publication_id)}"><span>${escapeHtml(item.platform)}</span><small class="${escapeHtml(itemStatus.tone)}">${escapeHtml(itemStatus.label)} · ${escapeHtml(item.publication_id)}</small></button>`;
    }).join("")}`
    : `<p class="browser-empty">Chưa có dry-run receipt.</p>`;
}

function analyticsPublication() {
  return state.publications.find((item) => item.status === "dry_run_succeeded" && item.mock === true) ?? null;
}

function analyticsFactorLabel(name) {
  return ({
    view_velocity: "Tốc độ view",
    retention: "Giữ chân",
    completion: "Xem hết",
    engagement: "Tương tác",
    shares: "Chia sẻ",
    saves: "Lưu",
    ctr: "CTR",
    follower_conversion: "Tăng follower",
    revenue_efficiency: "Hiệu quả doanh thu",
    production_cost_efficiency: "Hiệu quả chi phí",
  })[name] ?? name;
}

function renderAnalytics() {
  const report = state.analyticsReport;
  const status = describeAnalytics(report);
  const sync = state.activeAnalyticsSync ?? report?.latest_sync ?? null;
  const collecting = ["scheduled", "queued", "running", "retry_scheduled"].includes(sync?.status);
  const eligiblePublication = analyticsPublication();
  const snapshot = report?.latest_snapshot ?? null;
  const assessment = report?.latest_assessment ?? null;
  const providers = state.analyticsProviders ?? [];
  const officialProviders = providers.filter((item) => item.mode === "official");
  const unavailableCount = officialProviders.filter((item) => !item.supports_sync).length;

  $("#analytics-status").textContent = collecting ? "Đang thu thập" : status.label;
  $("#analytics-status").className = `pill ${collecting ? "warning" : status.tone}`;
  $("#analytics-source-status").textContent = snapshot?.mock === false ? "Nguồn provider" : "Dữ liệu mô phỏng";
  $("#analytics-source-status").className = `pill ${snapshot?.mock === false ? "safe" : "muted"}`;
  $("#analytics-provider-summary").textContent = officialProviders.length
    ? `Provider thật: ${unavailableCount}/${officialProviders.length} chưa cấu hình; external calls=false.`
    : "Provider thật: chưa đăng ký; external calls=false.";

  const syncButton = $("#analytics-sync-button");
  syncButton.disabled = collecting || !eligiblePublication;
  syncButton.textContent = collecting ? "Đang xử lý…" : "Chạy dữ liệu mô phỏng";
  syncButton.title = eligiblePublication
    ? "Tạo một snapshot fixture nội bộ, không gọi nền tảng ngoài."
    : "Cần một V2-09 dry-run receipt thành công trước khi thu thập fixture.";

  $("#analytics-metrics").innerHTML = snapshot
    ? analyticsMetricItems(report).map((item) => `
      <div class="analytics-metric${item.value === "Không có dữ liệu" ? " missing" : ""}">
        <small>${escapeHtml(item.label)}</small><strong>${escapeHtml(item.value)}</strong>
      </div>
    `).join("")
    : `<p class="browser-empty">${collecting ? "Worker đang tạo snapshot…" : "Chưa có snapshot."}</p>`;
  $("#analytics-history-count").textContent = `${report?.history_count ?? 0} snapshot`;
  $("#analytics-winner-score").textContent = assessment?.score === null || assessment?.score === undefined
    ? "—"
    : String(Math.round(assessment.score));
  $("#analytics-winner-state").textContent = status.winnerLabel;
  $("#analytics-factor-list").innerHTML = assessment?.factors?.length
    ? assessment.factors.map((factor) => `
      <div class="analytics-factor">
        <span>${escapeHtml(analyticsFactorLabel(factor.factor))}</span>
        <progress max="100" value="${factor.score ?? 0}"></progress>
        <strong>${factor.score === null || factor.score === undefined ? "—" : Math.round(factor.score)}</strong>
      </div>
    `).join("")
    : `<p class="browser-empty">Chưa có yếu tố đánh giá.</p>`;

  $("#analytics-learning-list").innerHTML = report?.learning_insights?.length
    ? report.learning_insights.map((insight) => `
      <div class="analytics-insight">
        <strong>${escapeHtml(insight.statement)}</strong>
        <span>${escapeHtml(insight.recommendation)}</span>
        <small>${escapeHtml(insight.insight_type)} · confidence ${Math.round(insight.confidence * 100)}% · applied=false</small>
      </div>
    `).join("")
    : `<p class="browser-empty">Chưa có khuyến nghị.</p>`;

  const features = report?.video_features;
  const featureItems = features ? [
    ["Trend", features.trend_cluster_id],
    ["Idea", features.idea_id],
    ["Hook", features.hook_type],
    ["Thời lượng", features.duration_seconds === null ? null : `${features.duration_seconds}s`],
    ["Scene", features.scene_count],
    ["Subtitle", features.subtitle_template],
    ["Voice", features.voice_profile],
    ["Visual", features.visual_strategy],
  ].filter(([, value]) => value !== null && value !== undefined && value !== "") : [];
  $("#analytics-feature-list").innerHTML = featureItems.map(([label, value]) => (
    `<span><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value)}</span>`
  )).join("");
}

async function createAnalyticsFixtureSync() {
  const publication = analyticsPublication();
  if (!publication) return toast("Cần V2-09 dry-run receipt thành công trước khi chạy analytics fixture.", true);
  $("#analytics-sync-button").disabled = true;
  try {
    state.activeAnalyticsSync = await api(`/api/v1/projects/${state.projectId}/analytics/syncs`, {
      method: "POST",
      headers: { "Idempotency-Key": `v2-10-studio-${crypto.randomUUID()}` },
      body: JSON.stringify({
        publication_id: publication.publication_id,
        provider_mode: "fixture",
        trigger: state.analyticsReport?.latest_snapshot ? "manual_refresh" : "initial",
        fixture_profile: "winner_candidate",
        actor_ref: "studio-user",
      }),
    });
    renderAnalytics();
    startAnalyticsPolling();
    toast("Đã xếp hàng fixture analytics; không có external call.");
  } catch (error) {
    toast(error.message, true);
    renderAnalytics();
  }
}

function startAnalyticsPolling() {
  stopAnalyticsPolling();
  state.analyticsPollTimer = window.setInterval(async () => {
    try {
      if (!state.activeAnalyticsSync) return stopAnalyticsPolling();
      state.activeAnalyticsSync = await api(
        `/api/v1/projects/${state.projectId}/analytics/syncs/${state.activeAnalyticsSync.sync_id}`,
      );
      const terminal = ["succeeded", "not_configured", "failed", "cancelled"].includes(state.activeAnalyticsSync.status);
      if (terminal) {
        stopAnalyticsPolling();
        state.analyticsReport = await api(`/api/v1/projects/${state.projectId}/analytics`);
        toast(state.activeAnalyticsSync.status === "succeeded"
          ? "Analytics fixture đã chuẩn hóa; recommendation vẫn chưa áp dụng."
          : `Analytics kết thúc ở trạng thái ${state.activeAnalyticsSync.status}.`,
          state.activeAnalyticsSync.status === "failed");
      }
      renderAnalytics();
    } catch (error) {
      stopAnalyticsPolling();
      toast(error.message, true);
    }
  }, 1000);
}

function stopAnalyticsPolling() {
  if (state.analyticsPollTimer) window.clearInterval(state.analyticsPollTimer);
  state.analyticsPollTimer = null;
}

function publicationPayload() {
  const finalRender = state.productionPackage?.latest_final_render;
  if (!finalRender) return null;
  return {
    platform: $("#publishing-platform").value,
    final_render_id: finalRender.render_id,
    mode: "dry_run",
    metadata: {
      title: $("#publishing-title").value.trim(),
      description: $("#publishing-description").value.trim(),
      caption: $("#publishing-caption").value.trim(),
      hashtags: $("#publishing-hashtags").value.split(",").map((item) => item.trim().replace(/^#/, "")).filter(Boolean),
      privacy: $("#publishing-privacy").value,
    },
    actor_ref: "studio-user",
  };
}

async function createPublishingDryRun(event) {
  event.preventDefault();
  const payload = publicationPayload();
  if (!payload) return toast("Cần final render đã duyệt trước khi kiểm tra publishing.", true);
  const signature = JSON.stringify(payload);
  if (signature !== state.publishRequestSignature) {
    state.publishRequestSignature = signature;
    state.publishIdempotencyKey = `v2-09-${crypto.randomUUID()}`;
  }
  $("#publishing-dry-run-button").disabled = true;
  $("#publishing-dry-run-button").textContent = "Đang kiểm tra…";
  try {
    const publication = await api(`/api/v1/projects/${state.projectId}/publish`, {
      method: "POST",
      headers: { "Idempotency-Key": state.publishIdempotencyKey },
      body: JSON.stringify(payload),
    });
    state.activePublication = publication;
    state.publications = [publication, ...state.publications.filter((item) => item.publication_id !== publication.publication_id)];
    toast("Dry-run PASS: đã tạo receipt, không có bài đăng hoặc external action.");
  } catch (error) {
    const publicationId = error.detail?.error?.publication_id;
    if (publicationId) {
      state.activePublication = await api(`/api/v1/projects/${state.projectId}/publications/${publicationId}`).catch(() => null);
      if (state.activePublication) {
        state.publications = [state.activePublication, ...state.publications.filter((item) => item.publication_id !== publicationId)];
      }
    }
    toast(error.message, true);
  } finally {
    $("#publishing-dry-run-button").textContent = "Kiểm tra và tạo dry-run receipt";
    renderPublishing();
  }
}

function timedWords(text, start, end) {
  const words = String(text).trim().split(/\s+/u).filter(Boolean);
  const slot = (end - start) / Math.max(1, words.length);
  return words.map((word, index) => ({
    text: word,
    start_seconds: Number((start + index * slot).toFixed(3)),
    end_seconds: Number((start + (index + 1) * slot).toFixed(3)),
  }));
}

async function createOrRefreshProductionPackage() {
  if (!state.timeline) return;
  try {
    state.productionPackage = await api(`/api/v1/projects/${state.projectId}/production-package`, {
      method: "POST",
      body: JSON.stringify({
        expected_timeline_version: state.timeline.current_version,
        actor_ref: "studio-user",
      }),
    });
    state.activeProductionRender = null;
    renderSummary();
    renderProduction();
    toast("Gói dựng V2-08 đã đồng bộ với timeline hiện tại.");
  } catch (error) {
    toast(error.message, true);
  }
}

async function saveSubtitles() {
  const packageState = state.productionPackage;
  if (!packageState) return;
  const cues = [...document.querySelectorAll(".subtitle-row")].map((row) => {
    const start = Number(row.querySelector('[data-cue-field="start"]').value);
    const end = Number(row.querySelector('[data-cue-field="end"]').value);
    const text = row.querySelector('[data-cue-field="text"]').value.trim();
    return {
      cue_id: row.dataset.cueId,
      start_seconds: start,
      end_seconds: end,
      text,
      words: timedWords(text, start, end),
    };
  });
  try {
    state.productionPackage = await api(`/api/v1/projects/${state.projectId}/subtitles`, {
      method: "PUT",
      body: JSON.stringify({
        expected_timeline_version: packageState.timeline_version,
        expected_subtitle_version: packageState.subtitle.version,
        cues,
        style: {
          ...packageState.subtitle.style,
          position: $("#subtitle-position").value,
          animation: $("#subtitle-animation").value,
          font_size: Number($("#subtitle-font-size").value),
          safe_margin_percent: Number($("#subtitle-safe-margin").value),
        },
        actor_ref: "studio-user",
        reason: "subtitle-editor",
      }),
    });
    state.activeProductionRender = null;
    renderSummary();
    renderProduction();
    toast("Đã lưu phiên bản phụ đề mới; approval/render cũ đã được vô hiệu hóa nếu có.");
  } catch (error) {
    toast(error.message, true);
  }
}

async function saveAudioMix() {
  const packageState = state.productionPackage;
  if (!packageState) return;
  const config = structuredClone(packageState.audio_mix.config);
  config.voice.enabled = $("#voice-enabled").checked;
  config.voice.speed = Number($("#voice-speed").value);
  config.voice.gain_db = Number($("#voice-gain").value);
  config.music.asset_id = $("#music-asset").value || null;
  config.music.gain_db = Number($("#music-gain").value);
  config.music.ducking_db = Number($("#music-ducking").value);
  try {
    state.productionPackage = await api(`/api/v1/projects/${state.projectId}/audio-mix`, {
      method: "PUT",
      body: JSON.stringify({
        expected_timeline_version: packageState.timeline_version,
        expected_audio_version: packageState.audio_mix.version,
        config,
        actor_ref: "studio-user",
        reason: "audio-mixer",
      }),
    });
    state.activeProductionRender = null;
    renderSummary();
    renderProduction();
    toast("Đã lưu phiên bản audio mix mới; chỉ nhạc có metadata quyền sử dụng mới được chấp nhận.");
  } catch (error) {
    toast(error.message, true);
  }
}

async function createProductionRender(kind) {
  const packageState = state.productionPackage;
  if (!packageState) return;
  const isFinal = kind === "final";
  const path = isFinal ? "final-render" : "review-render";
  try {
    state.activeProductionRender = await api(`/api/v1/projects/${state.projectId}/${path}`, {
      method: "POST",
      body: JSON.stringify({
        expected_timeline_version: packageState.timeline_version,
        expected_subtitle_version: packageState.subtitle.version,
        expected_audio_version: packageState.audio_mix.version,
        profile: isFinal ? $("#final-profile").value : "review-540x960",
        actor_ref: "studio-user",
        ...(isFinal ? {approval_id: packageState.approval?.approval_id} : {}),
      }),
    });
    renderProduction();
    startProductionPolling();
    toast(isFinal ? "Final render đã vào hàng đợi nội bộ." : "Review A/V đã vào hàng đợi nội bộ.");
  } catch (error) {
    toast(error.message, true);
  }
}

function startProductionPolling() {
  stopProductionPolling();
  if (!state.activeProductionRender) return;
  state.productionPollTimer = window.setInterval(async () => {
    try {
      const renderId = state.activeProductionRender.render_id;
      state.activeProductionRender = await api(`/api/v1/projects/${state.projectId}/renders/${renderId}`);
      state.productionPackage = await api(`/api/v1/projects/${state.projectId}/production-package`);
      renderSummary();
      renderProduction();
      const description = describeProductionRender(state.activeProductionRender);
      if (description.terminal) {
        stopProductionPolling();
        toast(description.label, !["awaiting_review", "ready"].includes(state.activeProductionRender.status));
      }
    } catch (error) {
      stopProductionPolling();
      toast(error.message, true);
    }
  }, 1200);
}

function stopProductionPolling() {
  if (state.productionPollTimer) window.clearInterval(state.productionPollTimer);
  state.productionPollTimer = null;
}

async function requestProductionApproval() {
  const review = state.productionPackage?.latest_review_render;
  if (!review) return;
  try {
    const approval = await api(`/api/v1/projects/${state.projectId}/approvals`, {
      method: "POST",
      body: JSON.stringify({
        review_render_id: review.render_id,
        requester_ref: "studio-user",
        note: "Vui lòng duyệt đúng review A/V và các phiên bản đang hiển thị.",
      }),
    });
    state.productionPackage = {...state.productionPackage, approval};
    renderSummary();
    renderProduction();
    toast("Đã gửi gói review gắn phiên bản cho owner.");
  } catch (error) {
    toast(error.message, true);
  }
}

async function decideProductionApproval(decision) {
  const approval = state.productionPackage?.approval;
  if (!approval) return;
  try {
    const updated = await api(`/api/v1/projects/${state.projectId}/approvals/${approval.approval_id}/decision`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        reviewer_ref: "studio-owner",
        comment: decision === "approved"
          ? "Owner xác nhận đã xem hình, nghe audio và kiểm tra phụ đề/QC."
          : "Owner yêu cầu chỉnh lại gói dựng trước khi render final.",
      }),
    });
    state.productionPackage = {...state.productionPackage, approval: updated};
    renderSummary();
    renderProduction();
    toast(decision === "approved" ? "Gói review đã được owner phê duyệt." : "Đã trả gói dựng về trạng thái cần chỉnh sửa.");
  } catch (error) {
    toast(error.message, true);
  }
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
    if (state.productionPackage) {
      state.productionPackage = {
        ...state.productionPackage,
        current_for_timeline: false,
        approval: null,
        latest_review_render: null,
        latest_final_render: null,
      };
      state.activeProductionRender = null;
    }
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
    if (state.productionPackage) {
      state.productionPackage = {
        ...state.productionPackage,
        current_for_timeline: false,
        approval: null,
        latest_review_render: null,
        latest_final_render: null,
      };
      state.activeProductionRender = null;
    }
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
$("#production-package-button").addEventListener("click", createOrRefreshProductionPackage);
$("#save-subtitles-button").addEventListener("click", saveSubtitles);
$("#save-audio-button").addEventListener("click", saveAudioMix);
$("#review-render-button").addEventListener("click", () => createProductionRender("review"));
$("#request-approval-button").addEventListener("click", requestProductionApproval);
$("#approve-button").addEventListener("click", () => decideProductionApproval("approved"));
$("#changes-button").addEventListener("click", () => decideProductionApproval("changes_requested"));
$("#final-render-button").addEventListener("click", () => createProductionRender("final"));
$("#publishing-form").addEventListener("submit", createPublishingDryRun);
$("#analytics-sync-button").addEventListener("click", createAnalyticsFixtureSync);
$("#publishing-platform").addEventListener("change", () => {
  state.activePublication = state.publications.find((item) => item.platform === $("#publishing-platform").value) ?? null;
  state.publishRequestSignature = null;
  state.publishIdempotencyKey = null;
  renderPublishing();
});
$("#publication-history").addEventListener("click", (event) => {
  const button = event.target.closest("[data-publication-id]");
  if (!button) return;
  state.activePublication = state.publications.find((item) => item.publication_id === button.dataset.publicationId) ?? null;
  renderPublishing();
});
$("#voice-speed").addEventListener("input", (event) => {
  $("#voice-speed-output").textContent = `${Number(event.target.value).toFixed(2)}×`;
});
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

window.addEventListener("beforeunload", () => {
  stopPreviewPolling();
  stopProductionPolling();
  stopAnalyticsPolling();
});
loadProjectList().catch((error) => { renderNoProject("Không tải được Studio.", error.message); toast(error.message, true); });
