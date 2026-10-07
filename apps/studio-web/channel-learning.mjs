export function canCreateLearning(state) {
  const roles = state.principal?.workspace_roles ?? {};
  return [state.principal?.platform_role, roles[state.workspaceId], roles['*'], state.workspaceSlug ? roles[`slug:${state.workspaceSlug}`] : null]
    .some(role => ['owner', 'reviewer', 'editor'].includes(role));
}

export function learningIntent(state, values) {
  if (!canCreateLearning(state)) throw new Error('Cần quyền chỉnh sửa trong workspace này.');
  const parent = state.publications.find(row => row.publication_id === values.publicationId);
  if (values.mode !== 'official' || !parent || parent.project_id !== state.projectId || parent.workspace_id !== state.workspaceId
      || parent.status !== 'published' || parent.mode !== 'live' || parent.dry_run !== false || !parent.receipt?.remote_post_id)
    throw new Error('Chọn publication live và nguồn analytics nền tảng.');
  const count = (raw, min, max) => {
    if (!/^\d+$/.test(String(raw))) throw new Error('Số video cần là số nguyên.');
    const result = Number(raw); if (result < min || result > max) throw new Error('Số video ngoài giới hạn.'); return result;
  };
  const group = count(values.groupPosts, 3, 50), control = count(values.controlPosts, 3, 50);
  if (group + control > 100 || !/^\d+(?:\.\d+)?$/.test(String(values.difference))) throw new Error('Ngưỡng so sánh không hợp lệ.');
  const difference = Number(values.difference); if (difference < 0 || difference > 100) throw new Error('Ngưỡng so sánh ngoài giới hạn.');
  return {publication_id: parent.publication_id, provider_mode: 'official',
    policy: {minimum_group_posts: group, minimum_control_posts: control, maximum_posts: 100, minimum_score_difference: difference}};
}

export function initializeChannelLearning({api, getState, root = document, toast, uuid = () => crypto.randomUUID()}) {
  const $ = id => root.querySelector(`#${id}`), selection = () => ({publicationId: $('analytics-publication').value,
    mode: $('analytics-mode').value, groupPosts: $('learning-group-posts').value,
    controlPosts: $('learning-control-posts').value, difference: $('learning-score-difference').value});
  const key = () => JSON.stringify([getState().workspaceId, getState().projectId, selection().publicationId, selection().mode]);
  let scope = '', revision = 0, busy = false, snapshots = [], selected = null;
  const idempotency = new Map();
  function element(tag, text) {const node = root.createElement(tag); node.textContent = text; return node;}
  function sync() {
    const next = key();
    if (next !== scope) {scope = next; revision++; busy = false; snapshots = []; selected = null; $('learning-use-advice').checked = false;}
    render();
  }
  function render() {
    let reason = ''; try {learningIntent(getState(), selection());} catch (error) {reason = error.message;}
    $('learning-create').disabled = busy || Boolean(reason); $('learning-create').title = reason;
    $('learning-read').disabled = busy || !getState().projectId;
    $('learning-use-advice').disabled = !selected;
    $('learning-snapshot-reference').textContent = selected ? `${selected.learning_snapshot_id} · ${selected.content_sha256}` : 'Chưa chọn snapshot.';
    $('learning-note').textContent = selected ? `${selected.observations.length} video khác nhau · ${selected.scope.mock ? 'Dữ liệu mô phỏng' : 'Dữ liệu provider'} · Ngách ${selected.scope.niche}. Chỉ đề xuất thử nghiệm sau review. Không có dữ liệu giờ đăng thật.`
      : 'Tổng hợp từ analytics đã lưu. Không gọi provider hoặc đổi ngân sách. Lịch sử đọc tối đa 100 snapshot.';
    const rows = $('learning-rows'); rows.replaceChildren();
    for (const dimension of selected?.dimensions ?? []) {
      if (!dimension.groups.length) {
        const tr = element('tr', ''); for (const text of [dimension.dimension, 'Chưa đủ dữ liệu', '—', '—', '—', '—']) tr.append(element('td', text)); rows.append(tr);
      }
      for (const group of dimension.groups) {
        const tr = element('tr', '');
        for (const text of [dimension.dimension, group.value, `${group.sample_count} / ${group.control_count}`,
            group.score_difference === null ? 'Không có dữ liệu' : String(group.score_difference), group.state,
            `${group.snapshot_ids.join(', ')} | So sánh: ${group.control_snapshot_ids.join(', ')}`]) tr.append(element('td', text));
        rows.append(tr);
      }
    }
    const list = $('learning-history'); list.replaceChildren();
    for (const snapshot of snapshots) {
      const button = element('button', `${snapshot.created_at} · ${snapshot.learning_snapshot_id}`); button.type = 'button';
      button.addEventListener('click', () => {selected = snapshot; $('learning-use-advice').checked = false; render();}); list.append(button);
    }
  }
  function validate(value, state) {
    if (value?.workspace_id !== state.workspaceId || value.project_id !== state.projectId || value.publication_id !== selection().publicationId
        || value.schema_version !== 'channel-learning-snapshot-v1' || value.recommendation_only !== true || value.autonomous_execution !== false
        || value.scope?.source_kind !== 'official_api' || !/^lsn_[A-Za-z0-9_-]{4,60}$/.test(value.learning_snapshot_id ?? '')
        || !/^[a-f0-9]{64}$/.test(value.content_sha256 ?? '') || !Array.isArray(value.observations) || value.observations.length > 100
        || !Array.isArray(value.dimensions) || value.dimensions.length !== 7
        || value.dimensions.some(row => !Array.isArray(row.groups) || row.groups.length > 20)) throw new Error('Phạm vi snapshot học không khớp.');
    return value;
  }
  const endpoint = state => `/api/v1/projects/${encodeURIComponent(state.projectId)}/analytics/learning-snapshots`;
  async function create() {
    sync(); if (busy) return; const state = getState(); let body;
    try {body = learningIntent(state, selection());} catch (error) {return toast(error.message, true);}
    const captured = key(), ownRevision = revision, signature = captured + JSON.stringify(body);
    const idem = idempotency.get(signature) ?? `studio-learning-${uuid()}`; idempotency.set(signature, idem); busy = true; render();
    try {
      const value = await api(endpoint(state), {method: 'POST', headers: {'Idempotency-Key': idem}, body: JSON.stringify(body)});
      if (captured !== key() || ownRevision !== revision) return;
      selected = validate(value, state); snapshots = [selected, ...snapshots.filter(row => row.learning_snapshot_id !== selected.learning_snapshot_id)].slice(0, 100);
      idempotency.delete(signature); $('learning-use-advice').checked = false; toast('Đã lưu đề xuất để review.');
    } catch (error) {if (captured === key()) toast(error.message, true);}
    finally {if (captured === key() && ownRevision === revision) {busy = false; render();}}
  }
  async function read() {
    sync(); if (busy || !getState().projectId) return;
    const state = getState(), captured = key(), ownRevision = revision; busy = true; render();
    try {
      const result = await api(endpoint(state) + '?limit=100');
      if (captured !== key() || ownRevision !== revision) return;
      if (!Array.isArray(result) || result.length > 100 || result.some(row => row.project_id !== state.projectId || row.workspace_id !== state.workspaceId))
        throw new Error('Phạm vi lịch sử học không khớp.');
      snapshots = selection().mode === 'official' ? result.filter(row => row.publication_id === selection().publicationId).map(row => validate(row, state)) : [];
      selected = snapshots[0] ?? null; $('learning-use-advice').checked = false;
    } catch (error) {if (captured === key()) toast(error.message, true);}
    finally {if (captured === key() && ownRevision === revision) {busy = false; render();}}
  }
  function advice() {sync(); return selected && $('learning-use-advice').checked ? {learning_snapshot_id: selected.learning_snapshot_id} : {};}
  $('learning-create').addEventListener('click', create); $('learning-read').addEventListener('click', read);
  for (const id of ['analytics-publication', 'analytics-mode', 'learning-group-posts', 'learning-control-posts', 'learning-score-difference']) $(id).addEventListener('change', sync);
  return {sync, create, read, advice};
}
