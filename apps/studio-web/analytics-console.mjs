const activeStatuses = new Set(['scheduled', 'queued', 'running', 'retry_scheduled']);
const fixtureProfiles = new Set(['normal', 'winner_candidate', 'underperforming', 'insufficient_data']);

export function canCollectAnalytics(principal, workspace, slug) {
  const roles = principal?.workspace_roles ?? {};
  return [principal?.platform_role, roles[workspace], roles['*'], slug ? roles[`slug:${slug}`] : null]
    .some(role => ['owner', 'editor'].includes(role));
}

function validDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value ?? '')) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}

export function analyticsSyncPlan(state, selection) {
  const publication = state.publications.find(row => row.publication_id === selection.publicationId);
  if (!publication || publication.project_id !== state.projectId || publication.workspace_id !== state.workspaceId)
    throw new Error('Chọn publication thuộc project hiện tại.');
  if (!canCollectAnalytics(state.principal, state.workspaceId, state.workspaceSlug)) throw new Error('Cần quyền editor hoặc owner trong workspace này.');
  const body = {publication_id: publication.publication_id, provider_mode: selection.mode,
    trigger: 'manual_refresh', actor_ref: 'studio-user'};
  if (selection.mode === 'fixture') {
    if (!['dry_run_succeeded', 'published'].includes(publication.status) || !fixtureProfiles.has(selection.fixtureProfile))
      throw new Error('Publication hoặc profile mô phỏng chưa sẵn sàng.');
    body.fixture_profile = selection.fixtureProfile;
    return body;
  }
  if (selection.mode !== 'official') throw new Error('Chọn nguồn analytics hợp lệ.');
  const provider = state.analyticsProviders.find(row => row.platform === publication.platform && row.mode === 'official');
  if (provider?.supports_sync !== true) throw new Error('Adapter analytics chưa cấu hình.');
  if (publication.status !== 'published' || publication.mode !== 'live' || publication.dry_run !== false
      || !publication.receipt || !publication.receipt.remote_post_id)
    throw new Error('Cần receipt của publication live đã hoàn tất.');
  if (provider.external_calls_enabled === true && (publication.mock !== false || publication.receipt.mock !== false
      || publication.receipt.external_action !== true)) throw new Error('Receipt mô phỏng không được dùng với provider thật.');
  if (publication.platform === 'youtube') {
    if (!validDate(selection.startDate) || !validDate(selection.endDate)) throw new Error('Chọn hai ngày hợp lệ.');
    const days = (Date.parse(`${selection.endDate}T00:00:00Z`) - Date.parse(`${selection.startDate}T00:00:00Z`)) / 86400000;
    if (days < 0 || days > 365 || typeof selection.includeRevenue !== 'boolean') throw new Error('Khoảng ngày tối đa 366 ngày.');
    body.query = {start_date: selection.startDate, end_date: selection.endDate, include_revenue: selection.includeRevenue};
  } else if (publication.platform !== 'tiktok') throw new Error('Adapter này chưa hỗ trợ trong console.');
  return body;
}

export function analyticsSeriesScope(snapshot) {
  const query = snapshot?.evidence?.query ?? null;
  return JSON.stringify([snapshot?.workspace_id, snapshot?.project_id, snapshot?.publication_id,
    snapshot?.platform, snapshot?.provider_key, snapshot?.source_kind, snapshot?.mock,
    snapshot?.evidence?.target_binding_sha256 ?? null, query]);
}

export function snapshotDelta(previous, current, metric) {
  if (!previous || !current || analyticsSeriesScope(previous) !== analyticsSeriesScope(current)) return null;
  const before = previous.metrics?.[metric], after = current.metrics?.[metric];
  if (typeof before !== 'number' || typeof after !== 'number' || !Number.isFinite(before) || !Number.isFinite(after)) return null;
  return after - before;
}

export function analyticsSeries(snapshots, metric, {workspaceId, projectId, publicationId, mode}) {
  const kind = mode === 'fixture' ? 'fixture' : 'official_api';
  return snapshots.filter(row => row.workspace_id === workspaceId && row.project_id === projectId
    && row.publication_id === publicationId && row.source_kind === kind)
    .sort((a, b) => a.collected_at.localeCompare(b.collected_at))
    .map(row => ({snapshotId: row.snapshot_id, time: row.collected_at, scope: analyticsSeriesScope(row),
      value: typeof row.metrics?.[metric] === 'number' && Number.isFinite(row.metrics[metric]) ? row.metrics[metric] : null,
      source: row.mock ? 'Mô phỏng' : 'Provider', query: row.evidence?.query ?? null}));
}

export function analyticsChartPaths(points) {
  const finite = points.filter(point => typeof point.value === 'number' && Number.isFinite(point.value) && Number.isFinite(Date.parse(point.time)));
  if (!finite.length) return {paths: [], minimum: null, maximum: null};
  let minimum = Infinity, maximum = -Infinity, start = Infinity, end = -Infinity;
  for (const point of finite) {
    minimum = Math.min(minimum, point.value); maximum = Math.max(maximum, point.value);
    start = Math.min(start, Date.parse(point.time)); end = Math.max(end, Date.parse(point.time));
  }
  const paths = []; let current = null;
  for (const point of points) {
    if (point.value === null || !Number.isFinite(point.value) || !Number.isFinite(Date.parse(point.time))) {current = null; continue;}
    const x = 40 + (Date.parse(point.time) - start) / Math.max(1, end - start) * 900;
    const y = 190 - (point.value - minimum) / Math.max(1, maximum - minimum) * 160;
    if (!current || current.scope !== point.scope) {current = {scope: point.scope, d: `M ${x.toFixed(2)} ${y.toFixed(2)}`}; paths.push(current);}
    else current.d += ` L ${x.toFixed(2)} ${y.toFixed(2)}`;
  }
  return {paths, minimum, maximum};
}

export function initializeAnalyticsConsole({api, getState, root = document, onReport, onQueued, toast, uuid = () => crypto.randomUUID()}) {
  const $ = id => root.querySelector(`#${id}`);
  let scope = '', revision = 0, busy = false, snapshots = [], nextCursor = null, totalCount = 0, idempotency = new Map();
  const selected = () => ({publicationId: $('analytics-publication').value, mode: $('analytics-mode').value,
    fixtureProfile: $('analytics-fixture-profile').value, startDate: $('analytics-start-date').value,
    endDate: $('analytics-end-date').value, includeRevenue: $('analytics-revenue').checked});
  const key = () => {const state = getState(); return JSON.stringify([state.workspaceId, state.projectId, selected().publicationId, selected().mode]);};
  function row(tag, text) {const value = root.createElement(tag); value.textContent = text; return value;}
  function options(element, items, placeholder) {
    const current = element.value; element.replaceChildren(); const empty = row('option', placeholder); empty.value = ''; element.append(empty);
    for (const item of items) {const option = row('option', item.label); option.value = item.value; element.append(option);}
    element.value = items.some(item => item.value === current) ? current : '';
  }
  function clearIfChanged() {
    const next = key(); if (next === scope) return;
    scope = next; revision += 1; busy = false; snapshots = []; nextCursor = null; totalCount = 0; idempotency = new Map();
    onReport(null); renderHistory();
  }
  function renderHistory() {
    const state = getState(); const selection = selected(); const metric = $('analytics-history-metric').value || 'views';
    const points = analyticsSeries(snapshots, metric, {...state, ...selection});
    const chart = $('analytics-history-chart');
    if (chart && typeof root.createElementNS === 'function') {
      chart.replaceChildren(); const plotted = analyticsChartPaths(points);
      const svg = root.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', '0 0 1000 220'); svg.setAttribute('role', 'img');
      svg.setAttribute('aria-label', `Giá trị ${metric} theo thời điểm thu thập. Giá trị thiếu không được nối.`);
      for (const path of plotted.paths) {
        const line = root.createElementNS('http://www.w3.org/2000/svg', 'path'); line.setAttribute('d', path.d);
        line.setAttribute('fill', 'none'); line.setAttribute('stroke', '#826eff'); line.setAttribute('stroke-width', '3'); svg.append(line);
        for (const match of path.d.matchAll(/[ML] ([0-9.]+) ([0-9.]+)/g)) {
          const dot = root.createElementNS('http://www.w3.org/2000/svg', 'circle');
          dot.setAttribute('cx', match[1]); dot.setAttribute('cy', match[2]); dot.setAttribute('r', '4'); dot.setAttribute('fill', '#826eff'); svg.append(dot);
        }
      }
      chart.append(svg); chart.append(row('p', plotted.minimum === null ? 'Chưa có metric cho biểu đồ.' : `Khoảng giá trị report: ${plotted.minimum} → ${plotted.maximum}. Xem timestamps chính xác trong bảng.`));
    }
    const table = $('analytics-history-rows'); table.replaceChildren();
    for (const point of points) {
      const tr = row('tr', '');
      for (const text of [point.time, point.source, point.query ? `${point.query.start_date} → ${point.query.end_date}` : 'Counter / fixture',
        point.value === null ? 'Không có dữ liệu' : String(point.value)]) tr.append(row('td', text));
      table.append(tr);
    }
    $('analytics-history-note').textContent = `Đang xem ${snapshots.length}/${totalCount} snapshot (tối đa 500 trong một lần xem). Thời điểm thu thập không xác nhận coverage; chênh lệch report không phải tốc độ view.`;
    options($('analytics-compare-before'), snapshots.map(value => ({value: value.snapshot_id, label: value.collected_at})), 'Snapshot trước');
    options($('analytics-compare-after'), snapshots.map(value => ({value: value.snapshot_id, label: value.collected_at})), 'Snapshot sau');
    compare();
  }
  function compare() {
    const before = snapshots.find(value => value.snapshot_id === $('analytics-compare-before').value);
    const after = snapshots.find(value => value.snapshot_id === $('analytics-compare-after').value);
    const delta = snapshotDelta(before, after, $('analytics-history-metric').value || 'views');
    $('analytics-comparison').textContent = delta === null ? 'Chọn hai snapshot cùng nguồn, tài khoản và khoảng report. Chỉ số thiếu hiển thị “Không có dữ liệu”.'
      : `Chênh lệch giá trị report: ${delta > 0 ? '+' : ''}${delta}. Không suy ra view velocity hoặc coverage.`;
  }
  function sync() {
    const state = getState();
    options($('analytics-publication'), state.publications.filter(value => value.project_id === state.projectId && value.workspace_id === state.workspaceId
      && ['dry_run_succeeded', 'published'].includes(value.status)).map(value => ({value: value.publication_id,
        label: `${value.platform} · ${value.publication_id} · ${value.mock ? 'mô phỏng' : 'provider'}`})), 'Chọn publication');
    clearIfChanged(); const selection = selected();
    const publication = state.publications.find(value => value.publication_id === selection.publicationId);
    const official = selection.mode === 'official'; const youtube = official && publication?.platform === 'youtube';
    $('analytics-fixture-profile').disabled = official;
    $('analytics-start-date').disabled = $('analytics-end-date').disabled = $('analytics-revenue').disabled = !youtube;
    let reason = '';
    try {analyticsSyncPlan(state, selection);} catch (error) {reason = error.message;}
    const active = state.activeAnalyticsSync;
    const collecting = active?.publication_id === selection.publicationId && active?.provider_mode === selection.mode && activeStatuses.has(active.status);
    $('analytics-sync-button').disabled = busy || collecting || Boolean(reason);
    $('analytics-sync-button').textContent = official ? 'Thu thập chỉ số nền tảng' : 'Chạy dữ liệu mô phỏng';
    $('analytics-sync-button').title = reason || (official ? 'Chỉ đọc analytics; không publish hoặc đổi ngân sách.' : 'Fixture được gắn nhãn mô phỏng.');
    $('analytics-read-refresh').disabled = busy || !publication;
    $('analytics-history-more').disabled = busy || !nextCursor || snapshots.length >= 500;
  }
  function checkedPage(page, state, selection) {
    if (page?.workspace_id !== state.workspaceId || page.project_id !== state.projectId
        || page.publication_id !== selection.publicationId || page.provider_mode !== selection.mode
        || !Array.isArray(page.items) || page.items.length > 50 || !Number.isInteger(page.total_count)
        || page.total_count < 0 || (page.next_cursor !== null && !/^ams_[A-Za-z0-9_-]{4,60}$/.test(page.next_cursor ?? '')))
      throw new Error('Analytics page scope không khớp.');
    const kind = selection.mode === 'fixture' ? 'fixture' : 'official_api';
    if (page.items.some(value => value.project_id !== state.projectId || value.workspace_id !== state.workspaceId
        || value.publication_id !== selection.publicationId || value.source_kind !== kind)) throw new Error('Analytics observation scope không khớp.');
    return page;
  }
  async function refresh() {
    clearIfChanged(); const state = getState(); const selection = selected();
    if (!selection.publicationId || !state.projectId) return;
    const captured = key(), ownRevision = revision; busy = true; sync();
    try {
      const base = `/api/v1/projects/${encodeURIComponent(state.projectId)}/publications/${encodeURIComponent(selection.publicationId)}/analytics`;
      const query = `?provider_mode=${selection.mode}`;
      const [report, rawPage] = await Promise.all([api(base + query), api(base + '/observations' + query + '&limit=50')]);
      if (captured !== key() || ownRevision !== revision) return;
      if (report.project_id !== state.projectId || report.publication_id !== selection.publicationId) throw new Error('Analytics scope không khớp.');
      const page = checkedPage(rawPage, state, selection);
      snapshots = page.items; nextCursor = page.next_cursor; totalCount = page.total_count;
      onReport(report); renderHistory();
    } catch (error) {if (captured === key()) toast(error.message, true);}
    finally {if (captured === key() && ownRevision === revision) {busy = false; sync();}}
  }
  async function more() {
    clearIfChanged(); if (busy || !nextCursor || snapshots.length >= 500) return;
    const state = getState(), selection = selected(), captured = key(), ownRevision = revision, cursor = nextCursor;
    busy = true; sync();
    try {
      const path = `/api/v1/projects/${encodeURIComponent(state.projectId)}/publications/${encodeURIComponent(selection.publicationId)}/analytics/observations`;
      const rawPage = await api(path + `?provider_mode=${selection.mode}&limit=50&cursor=${encodeURIComponent(cursor)}`);
      if (captured !== key() || ownRevision !== revision) return;
      const page = checkedPage(rawPage, state, selection);
      if (page.next_cursor === cursor) throw new Error('Analytics cursor không tiến triển.');
      snapshots = [...new Map([...snapshots, ...page.items].map(value => [value.snapshot_id, value])).values()].slice(0, 500);
      nextCursor = page.next_cursor; totalCount = page.total_count; renderHistory();
    } catch (error) {if (captured === key()) toast(error.message, true);}
    finally {if (captured === key() && ownRevision === revision) {busy = false; sync();}}
  }
  async function collect() {
    clearIfChanged(); const state = getState(); let body;
    try {body = analyticsSyncPlan(state, selected());} catch (error) {return toast(error.message, true);}
    if (busy || $('analytics-sync-button').disabled) return;
    const captured = key(), ownRevision = revision; const signature = captured + JSON.stringify(body);
    const idem = idempotency.get(signature) ?? `studio-analytics-${uuid()}`; idempotency.set(signature, idem);
    busy = true; sync();
    try {
      const result = await api(`/api/v1/projects/${encodeURIComponent(state.projectId)}/analytics/syncs`, {
        method: 'POST', headers: {'Idempotency-Key': idem}, body: JSON.stringify(body)});
      if (captured !== key() || ownRevision !== revision) return;
      if (result.project_id !== state.projectId || result.publication_id !== body.publication_id || result.provider_mode !== body.provider_mode)
        throw new Error('Analytics sync scope không khớp.');
      idempotency.delete(signature); // A confirmed sync permits a later, explicitly requested refresh.
      onQueued(result); toast(body.provider_mode === 'fixture' ? 'Đã xếp hàng dữ liệu mô phỏng.' : 'Đã xếp hàng đọc analytics; transport được ghi nhận trong kết quả.');
    } catch (error) {if (captured === key()) toast(error.message, true);}
    finally {if (captured === key() && ownRevision === revision) {busy = false; sync();}}
  }
  for (const id of ['analytics-publication', 'analytics-mode']) $(id).addEventListener('change', () => {clearIfChanged(); sync(); refresh();});
  for (const id of ['analytics-fixture-profile', 'analytics-start-date', 'analytics-end-date', 'analytics-revenue']) $(id).addEventListener('change', sync);
  $('analytics-read-refresh').addEventListener('click', refresh);
  $('analytics-history-more').addEventListener('click', more);
  $('analytics-sync-button').addEventListener('click', collect);
  $('analytics-history-metric').addEventListener('change', renderHistory);
  for (const id of ['analytics-compare-before', 'analytics-compare-after']) $(id).addEventListener('change', compare);
  return {sync, refresh, more, collect, key};
}
