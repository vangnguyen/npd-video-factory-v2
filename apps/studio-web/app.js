import {
  RADAR_VIEWS,
  filterClusters,
  formatScore,
  lifecycleLabel,
  lifecycleTone,
} from "/trend-utils.mjs";

const state = {
  workspaceId: null,
  sources: [],
  signals: [],
  clusters: [],
  ideas: [],
  queue: [],
  selectedClusterId: null,
  view: "trending",
  query: "",
};

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const safeUrl = (value) => {
  try {
    const parsed = new URL(value);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "#";
  } catch {
    return "#";
  }
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body?.detail?.error?.message ?? `API ${response.status}`);
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

function currentContext() {
  return {
    channel: $("#channel-filter").value,
    niche: $("#niche-filter").value,
    business_objective: $("#objective-filter").value,
  };
}

function renderTabs() {
  $("#view-tabs").innerHTML = Object.entries(RADAR_VIEWS).map(([key, label]) =>
    `<button type="button" role="tab" data-view="${key}" aria-selected="${state.view === key}" class="${state.view === key ? "active" : ""}">${label}</button>`
  ).join("");
}

function renderMetrics() {
  const platforms = new Set(state.signals.map((item) => item.source));
  $("#metric-clusters").textContent = state.clusters.length;
  $("#metric-signals").textContent = state.signals.length;
  $("#metric-platforms").textContent = platforms.size;
  $("#metric-queue").textContent = state.queue.length;
  const select = $("#platform-filter");
  const selected = select.value;
  select.innerHTML = `<option value="">Tất cả</option>${[...platforms].sort().map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item.replaceAll("_", " "))}</option>`).join("")}`;
  select.value = selected;
  const formats = new Set(state.clusters.flatMap((cluster) => cluster.formats ?? []));
  const formatSelect = $("#format-filter");
  const selectedFormat = formatSelect.value;
  formatSelect.innerHTML = `<option value="">Tất cả</option>${[...formats].sort().map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item.replaceAll("_", " "))}</option>`).join("")}`;
  formatSelect.value = selectedFormat;
}

function renderClusters() {
  const filtered = filterClusters(state.clusters, {
    view: state.view,
    platform: $("#platform-filter").value,
    country: $("#country-filter").value,
    language: $("#language-filter").value,
    format: $("#format-filter").value,
    days: $("#time-filter").value,
    query: state.query,
  });
  $("#result-count").textContent = `${filtered.length} cơ hội`;
  $("#trend-grid").innerHTML = filtered.length ? filtered.map((cluster) => `
    <button type="button" class="trend-card ${cluster.cluster_id === state.selectedClusterId ? "selected" : ""}" data-cluster-id="${escapeHtml(cluster.cluster_id)}">
      <div class="card-top">
        <span class="lifecycle ${lifecycleTone(cluster.lifecycle)}">${escapeHtml(lifecycleLabel(cluster.lifecycle))}</span>
        <span class="score-ring"><span>${formatScore(cluster.score?.total_score)}</span></span>
      </div>
      <h3>${escapeHtml(cluster.topic)}</h3>
      <p>${escapeHtml(cluster.summary)}</p>
      <div class="platform-list">${cluster.platforms.map((item) => `<span>${escapeHtml(item.replaceAll("_", " "))}</span>`).join("")}</div>
      <div class="keyword-list">${cluster.keywords.slice(0, 3).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
      <div class="card-foot"><span>${cluster.signal_count} tín hiệu</span><span>${cluster.platforms.length} nền tảng</span><span>ước tính</span></div>
    </button>
  `).join("") : `<div class="empty-state"><strong>Chưa có cơ hội phù hợp.</strong><p>Nạp tín hiệu demo hoặc đổi bộ lọc để tiếp tục.</p></div>`;
}

function selectedCluster() {
  return state.clusters.find((item) => item.cluster_id === state.selectedClusterId) ?? null;
}

function renderDetail() {
  const cluster = selectedCluster();
  const panel = $("#trend-detail");
  $("#generate-button").disabled = !cluster;
  if (!cluster) {
    panel.className = "detail-panel empty-panel";
    panel.innerHTML = "<p>Chọn một thẻ xu hướng để xem lifecycle, thành phần điểm và nguồn tham khảo.</p>";
    return;
  }
  const components = cluster.score?.components ?? {};
  panel.className = "detail-panel";
  panel.innerHTML = `
    <div class="detail-head"><div><h3>${escapeHtml(cluster.topic)}</h3><p>${escapeHtml(lifecycleLabel(cluster.lifecycle))} · ${cluster.signal_count} tín hiệu · ${cluster.platforms.length} nền tảng</p></div><span class="pill muted">Estimate ${formatScore(cluster.score?.total_score)}</span></div>
    <div class="score-breakdown">
      ${Object.entries(components).slice(0, 8).map(([key, value]) => `<div class="score-line"><span>${escapeHtml(key.replaceAll("_", " "))}</span><progress max="100" value="${Math.max(0, Math.min(100, Number(value)))}"></progress><strong>${formatScore(value)}</strong></div>`).join("")}
    </div>
    <ul class="source-list">${cluster.source_references.map((url) => `<li><a href="${safeUrl(url)}" target="_blank" rel="noreferrer noopener">↗ ${escapeHtml(url)}</a></li>`).join("")}</ul>
  `;
}

function renderIdeas() {
  const items = state.ideas.filter((idea) => !state.selectedClusterId || idea.cluster_id === state.selectedClusterId);
  const panel = $("#idea-list");
  if (!items.length) {
    panel.className = "idea-list empty-panel";
    panel.innerHTML = "<p>Chưa có brief. Chọn xu hướng và tạo các góc nội dung độc lập.</p>";
    return;
  }
  panel.className = "idea-list";
  panel.innerHTML = items.map((idea) => `
    <article class="idea-card">
      <header><h3>${escapeHtml(idea.title)}</h3><span class="idea-score">${formatScore(idea.score.total_score)}</span></header>
      <p><strong>Hook:</strong> ${escapeHtml(idea.hook_concept)}</p>
      <p>${escapeHtml(idea.angle)}</p>
      <div class="idea-actions"><small>${idea.recommended_duration_seconds}s · ${escapeHtml(idea.format)} · draft</small><button type="button" data-idea-id="${escapeHtml(idea.idea_id)}" ${idea.project_id ? "disabled" : ""}>${idea.project_id ? "Đã tạo project" : "Tạo draft project"}</button></div>
    </article>
  `).join("");
}

function renderQueue() {
  $("#queue-body").innerHTML = state.queue.length ? state.queue.map((item) => `
    <tr><td class="rank-cell">#${item.rank}</td><td><span class="table-title">${escapeHtml(item.idea.title)}</span></td><td>${escapeHtml(state.clusters.find((cluster) => cluster.cluster_id === item.cluster_id)?.topic ?? item.cluster_id)}</td><td>${escapeHtml(item.channel)}</td><td class="queue-score">${formatScore(item.score)}</td><td><span class="pill muted">Đề xuất</span></td></tr>
  `).join("") : `<tr><td colspan="6" class="table-empty">Chưa có cơ hội được xếp hạng.</td></tr>`;
}

function renderAll() {
  renderTabs();
  renderMetrics();
  renderClusters();
  renderDetail();
  renderIdeas();
  renderQueue();
}

async function loadWorkspace() {
  const workspaces = await api("/api/v1/workspaces");
  state.workspaceId = workspaces[0]?.workspace_id ?? null;
  if (!state.workspaceId) throw new Error("Workspace chưa được khởi tạo.");
}

async function reloadData() {
  if (!state.workspaceId) await loadWorkspace();
  const [sources, signals, clusters, ideas, queue] = await Promise.all([
    api("/api/v1/trend-sources"),
    api(`/api/v1/workspaces/${state.workspaceId}/trend-signals`),
    api(`/api/v1/workspaces/${state.workspaceId}/trend-clusters`),
    api(`/api/v1/workspaces/${state.workspaceId}/ideas`),
    api(`/api/v1/workspaces/${state.workspaceId}/content-opportunities`),
  ]);
  Object.assign(state, { sources, signals, clusters, ideas, queue });
  const healthy = sources.filter((source) => source.status === "healthy");
  $("#provider-status").textContent = `${healthy.length}/${sources.length} nguồn khả dụng`;
  $("#provider-status").className = `pill ${healthy.length ? "safe" : "warning"}`;
  renderAll();
}

async function collectFixture() {
  const button = $("#refresh-button");
  button.disabled = true;
  button.textContent = "Đang chuẩn hóa…";
  try {
    await api(`/api/v1/workspaces/${state.workspaceId}/trend-signals/collect`, {
      method: "POST",
      body: JSON.stringify({ provider_key: "fixture-trends", country: "VN", language: "vi" }),
    });
    await api(`/api/v1/workspaces/${state.workspaceId}/trend-clusters/refresh`, {
      method: "POST",
      body: JSON.stringify(currentContext()),
    });
    await reloadData();
    toast("Đã nạp và chuẩn hóa tín hiệu demo. Không có gọi API trả phí.");
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "Nạp tín hiệu demo";
  }
}

async function generateIdeas() {
  const cluster = selectedCluster();
  if (!cluster) return;
  try {
    await api(`/api/v1/trend-clusters/${cluster.cluster_id}/ideas/generate`, {
      method: "POST",
      body: JSON.stringify({ ...currentContext(), audience: "Khách hàng quan tâm bất động sản", cta: "Đăng ký nhận tư vấn", count: 3 }),
    });
    await reloadData();
    toast("Đã tạo 3 brief khác biệt ở trạng thái draft.");
  } catch (error) { toast(error.message, true); }
}

async function refreshQueue() {
  try {
    state.queue = await api(`/api/v1/workspaces/${state.workspaceId}/content-opportunities/refresh`, {
      method: "POST",
      body: JSON.stringify({ ...currentContext(), audience: "Khách hàng quan tâm bất động sản", cta: "Đăng ký nhận tư vấn", top_n: 10, ideas_per_cluster: 3 }),
    });
    state.ideas = await api(`/api/v1/workspaces/${state.workspaceId}/ideas`);
    renderAll();
    toast("Queue đã được xếp hạng bằng điểm ước tính, chưa thực thi nội dung.");
  } catch (error) { toast(error.message, true); }
}

async function createProject(ideaId) {
  try {
    await api(`/api/v1/ideas/${ideaId}/projects`, { method: "POST", body: "{}" });
    state.ideas = await api(`/api/v1/workspaces/${state.workspaceId}/ideas`);
    renderIdeas();
    toast("Đã tạo project draft. Publishing vẫn bị vô hiệu hóa.");
  } catch (error) { toast(error.message, true); }
}

$("#view-tabs").addEventListener("click", (event) => {
  const button = event.target.closest("[data-view]");
  if (!button) return;
  state.view = button.dataset.view;
  renderTabs();
  renderClusters();
});
$("#trend-grid").addEventListener("click", (event) => {
  const card = event.target.closest("[data-cluster-id]");
  if (!card) return;
  state.selectedClusterId = card.dataset.clusterId;
  renderClusters(); renderDetail(); renderIdeas();
});
$("#idea-list").addEventListener("click", (event) => {
  const button = event.target.closest("[data-idea-id]");
  if (button) createProject(button.dataset.ideaId);
});
$("#search-input").addEventListener("input", (event) => { state.query = event.target.value; renderClusters(); });
for (const id of ["platform-filter", "country-filter", "language-filter", "format-filter", "time-filter"]) {
  $(`#${id}`).addEventListener("change", renderClusters);
}
for (const id of ["channel-filter", "niche-filter", "objective-filter"]) {
  $(`#${id}`).addEventListener("change", () => toast("Ngữ cảnh điểm đã đổi; hãy nạp lại cụm để tính profile mới."));
}
$("#refresh-button").addEventListener("click", collectFixture);
$("#generate-button").addEventListener("click", generateIdeas);
$("#queue-button").addEventListener("click", refreshQueue);
$("#menu-button").addEventListener("click", () => $(".sidebar").classList.toggle("open"));
document.addEventListener("click", (event) => {
  if (window.innerWidth <= 860 && !event.target.closest(".sidebar") && !event.target.closest("#menu-button")) $(".sidebar").classList.remove("open");
});

renderTabs();
reloadData().catch((error) => { toast(error.message, true); renderAll(); });
