// Explicit Owner controls for durable read-only intent. No publishing operation.
export function canManageAnalyticsRefresh(state) {
  const roles = state.principal?.workspace_roles ?? {};
  return [state.principal?.platform_role, roles[state.workspaceId], roles['*'], state.workspaceSlug ? roles[`slug:${state.workspaceSlug}`] : null].includes('owner');
}

export function refreshIntent(state, values) {
  if (!canManageAnalyticsRefresh(state)) throw new Error('Cần quyền Owner trong workspace này.');
  const parent = state.publications.find(value => value.publication_id === values.publicationId);
  if (!parent || parent.project_id !== state.projectId || parent.workspace_id !== state.workspaceId
      || !['published', 'dry_run_succeeded'].includes(parent.status)) throw new Error('Chọn publication phù hợp.');
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(values.firstRun ?? '')) throw new Error('Chọn lần đọc đầu theo giờ máy.');
  const date = new Date(values.firstRun);
  if (!Number.isFinite(date.valueOf())) throw new Error('Lần đọc đầu không hợp lệ.');
  const parts = values.firstRun.split(/[-T:]/).map(Number);
  if ([date.getFullYear(), date.getMonth() + 1, date.getDate(), date.getHours(), date.getMinutes()].some((value, index) => value !== parts[index]))
    throw new Error('Lần đọc đầu không tồn tại theo giờ máy.');
  const count = (raw, maximum) => {
    if (!/^\d+$/.test(String(raw))) throw new Error('Khoảng cách và số lượt cần là số nguyên.');
    const value = Number(raw); if (value < 1 || value > maximum) throw new Error('Khoảng cách hoặc số lượt ngoài giới hạn.'); return value;
  };
  if (typeof values.enabled !== 'boolean' || typeof values.acknowledged !== 'boolean') throw new Error('Trạng thái lịch không hợp lệ.');
  if (values.enabled && !values.acknowledged) throw new Error('Xác nhận lịch chỉ đọc analytics trước khi bật.');
  const body = {publication_id: parent.publication_id, provider_mode: values.mode, first_run_at: date.toISOString(),
    interval_hours: count(values.intervalHours, 168), max_runs: count(values.maxRuns, 365), enabled: values.enabled,
    acknowledged_read_only: values.acknowledged};
  if (values.mode === 'fixture') {
    if (!['normal', 'winner_candidate', 'underperforming', 'insufficient_data'].includes(values.fixtureProfile)) throw new Error('Chọn profile mô phỏng.');
    body.fixture_profile = values.fixtureProfile; body.query_policy = 'cumulative';
  } else if (values.mode === 'official') {
    if (parent.status !== 'published' || parent.mode !== 'live' || parent.dry_run !== false || !parent.receipt?.remote_post_id)
      throw new Error('Lịch nền tảng cần publication live đã hoàn tất.');
    if (parent.platform === 'youtube') {
      body.query_policy = 'rolling_complete_days'; body.lookback_days = count(values.lookbackDays, 366);
      if (typeof values.includeRevenue !== 'boolean') throw new Error('Lựa chọn revenue không hợp lệ.');
      body.include_revenue = values.includeRevenue;
    } else {body.query_policy = 'cumulative';}
  } else throw new Error('Chọn nguồn analytics hợp lệ.');
  return body;
}

export function initializeAnalyticsRefresh({api, getState, root = document, toast, uuid = () => crypto.randomUUID()}) {
  const $ = id => root.querySelector(`#${id}`);
  const selection = () => ({publicationId: $('analytics-publication').value, mode: $('analytics-mode').value,
    fixtureProfile: $('analytics-fixture-profile').value, firstRun: $('analytics-refresh-first').value,
    intervalHours: $('analytics-refresh-interval').value, maxRuns: $('analytics-refresh-runs').value,
    lookbackDays: $('analytics-refresh-lookback').value, includeRevenue: $('analytics-revenue').checked,
    enabled: $('analytics-refresh-enabled').checked, acknowledged: $('analytics-refresh-ack').checked});
  const key = () => JSON.stringify([getState().workspaceId, getState().projectId, selection().publicationId, selection().mode]);
  let scope = '', revision = 0, busy = false, plans = [], idempotency = new Map();
  function element(tag, text) {const value = root.createElement(tag); value.textContent = text; return value;}
  function clear() {const next = key(); if (next !== scope) {scope = next; revision += 1; busy = false; plans = []; idempotency = new Map();}}
  function render() {
    const state = getState(), values = selection(), owner = canManageAnalyticsRefresh(state);
    const table = $('analytics-refresh-rows'); table.replaceChildren();
    for (const plan of plans) {
      const tr = element('tr', '');
      const complete = plan.run_count >= plan.max_runs;
      for (const value of [plan.plan_id, complete ? 'Đã đủ lượt' : plan.enabled ? 'Đang bật' : 'Đang tắt',
          `${plan.run_count}/${plan.max_runs}`, `${plan.config.interval_hours} giờ`, plan.next_due_at,
          plan.updated_by]) tr.append(element('td', String(value)));
      const cell = element('td', ''), button = element('button', plan.enabled ? 'Tắt lịch' : 'Bật lịch');
      button.type = 'button'; button.disabled = busy || !owner || (!plan.enabled && (complete || !$('analytics-refresh-ack').checked));
      button.addEventListener('click', () => change(plan)); cell.append(button); tr.append(cell); table.append(tr);
    }
    let reason = ''; try {refreshIntent(state, values);} catch (error) {reason = error.message;}
    $('analytics-refresh-create').disabled = busy || Boolean(reason); $('analytics-refresh-create').title = reason;
    $('analytics-refresh-read').disabled = busy || !state.projectId;
    const parent = state.publications.find(value => value.publication_id === values.publicationId);
    $('analytics-refresh-lookback').disabled = values.mode !== 'official' || parent?.platform !== 'youtube';
    $('analytics-refresh-note').textContent = 'Lịch chỉ đọc analytics. Owner quản lý; mặc định tắt. Các lượt lỡ không chạy dồn. Khi bật, worker vẫn kiểm tra cấu hình, quyền đọc và ngân sách.';
  }
  function sync() {clear(); render();}
  function endpoint(state) {return `/api/v1/projects/${encodeURIComponent(state.projectId)}/analytics/refresh-plans`;}
  async function refresh() {
    sync(); const state = getState(), values = selection(); if (busy || !state.projectId) return;
    const captured = key(), ownRevision = revision; busy = true; render();
    try {
      const result = await api(endpoint(state));
      if (captured !== key() || ownRevision !== revision) return;
      if (!Array.isArray(result) || result.length > 100 || result.some(plan => plan.project_id !== state.projectId || plan.workspace_id !== state.workspaceId))
        throw new Error('Phạm vi lịch analytics không khớp.');
      plans = result.filter(plan => plan.publication_id === values.publicationId && plan.config.provider_mode === values.mode);
    } catch (error) {if (captured === key()) toast(error.message, true);}
    finally {if (captured === key() && ownRevision === revision) {busy = false; render();}}
  }
  async function create() {
    sync(); if (busy) return; const state = getState(); let body;
    try {body = refreshIntent(state, selection());} catch (error) {return toast(error.message, true);}
    const captured = key(), ownRevision = revision, signature = captured + JSON.stringify(body);
    const idem = idempotency.get(signature) ?? `studio-refresh-${uuid()}`; idempotency.set(signature, idem);
    busy = true; render();
    try {
      const result = await api(endpoint(state), {method: 'POST', headers: {'Idempotency-Key': idem}, body: JSON.stringify(body)});
      if (captured !== key() || ownRevision !== revision) return;
      if (result.project_id !== state.projectId || result.workspace_id !== state.workspaceId || result.publication_id !== body.publication_id
          || result.config.provider_mode !== body.provider_mode) throw new Error('Phạm vi lịch analytics không khớp.');
      plans = [result, ...plans.filter(value => value.plan_id !== result.plan_id)]; toast(result.enabled ? 'Đã tạo lịch chỉ đọc.' : 'Đã lưu lịch đang tắt.');
    } catch (error) {if (captured === key()) toast(error.message, true);}
    finally {if (captured === key() && ownRevision === revision) {busy = false; render();}}
  }
  async function change(plan) {
    sync(); const state = getState();
    if (busy || !canManageAnalyticsRefresh(state) || !plans.some(value => value.plan_id === plan.plan_id)) return;
    const enabled = !plan.enabled;
    if (enabled && !$('analytics-refresh-ack').checked) return toast('Xác nhận lịch chỉ đọc trước khi bật.', true);
    const captured = key(), ownRevision = revision; busy = true; render();
    try {
      const result = await api(endpoint(state) + `/${encodeURIComponent(plan.plan_id)}/state`, {method: 'POST',
        body: JSON.stringify({expected_revision: plan.revision, enabled, acknowledged_read_only: enabled})});
      if (captured !== key() || ownRevision !== revision) return;
      if (result.plan_id !== plan.plan_id || result.project_id !== state.projectId || result.workspace_id !== state.workspaceId
          || result.publication_id !== selection().publicationId || result.config.provider_mode !== selection().mode) throw new Error('Phạm vi lịch analytics không khớp.');
      plans = plans.map(value => value.plan_id === result.plan_id ? result : value);
      toast(result.enabled ? 'Đã bật lịch chỉ đọc.' : 'Đã tắt lịch; các lượt cũ không tự khởi động lại.');
    } catch (error) {if (captured === key()) toast(error.message + ' Đọc lại trạng thái trước khi thử tiếp.', true);}
    finally {if (captured === key() && ownRevision === revision) {busy = false; render();}}
  }
  $('analytics-refresh-create').addEventListener('click', create); $('analytics-refresh-read').addEventListener('click', refresh);
  for (const id of ['analytics-refresh-first', 'analytics-refresh-interval', 'analytics-refresh-runs', 'analytics-refresh-lookback',
    'analytics-refresh-enabled', 'analytics-refresh-ack', 'analytics-publication', 'analytics-mode',
    'analytics-fixture-profile', 'analytics-revenue']) $(id).addEventListener('change', sync);
  return {sync, refresh, create, change};
}
