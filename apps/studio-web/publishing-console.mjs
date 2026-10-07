// Owner controls call only review/consent/queue APIs; they never run a provider.
export function isPublishingOwner(principal, workspaceId, workspaceSlug) {
  return principal?.platform_role === 'owner' || ['*', workspaceId, workspaceSlug ? `slug:${workspaceSlug}` : null]
    .filter(Boolean).some(key => principal?.workspace_roles?.[key] === 'owner');
}

export function publishApprovalPayload(review, publication, acknowledged) {
  const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
  if (acknowledged !== true || publication?.mode !== 'live' || !['awaiting_publish_approval', 'publishing'].includes(publication.status)
    || review?.publication_id !== publication.publication_id
    || review.project_id !== publication.project_id || review.workspace_id !== publication.workspace_id
    || review.request_fingerprint !== publication.request_fingerprint || review.owner_gates_enabled !== true
    || review.final_render_id !== publication.final_render_id || review.output_asset_id !== publication.output_asset_id
    || !hash(review.artifact_sha256) || !hash(review.target_binding_sha256) || !hash(review.request_fingerprint)) {
    throw new Error('Cần đọc và xác nhận đúng bản review hiện tại.');
  }
  return {expected_fingerprint: review.request_fingerprint, expected_artifact_sha256: review.artifact_sha256,
    expected_target_sha256: review.target_binding_sha256, acknowledged: true};
}

export function usablePublishGrant(grant, review, now = Date.now()) {
  return Boolean(grant && review && grant.revoked === false && grant.scope === 'PUBLISH_ONLY'
    && grant.publication_id === review.publication_id && grant.workspace_id === review.workspace_id
    && grant.binding_sha256 === review.binding_sha256 && grant.target_binding_sha256 === review.target_binding_sha256
    && /^pua_[a-f0-9]{32}$/.test(grant.publish_approval_id) && Number.isFinite(Date.parse(grant.expires_at))
    && Date.parse(grant.expires_at) > now);
}

export function initializePublishingConsole({api, getState, publicationPayload, setPublication, toast, root = document,
  uuid = () => crypto.randomUUID()}) {
  const el = id => root.querySelector(`#${id}`);
  let scope = '', profiles = [], review = null, work = null, grant = null, busy = false, reviewError = '', workError = '';
  let prepareKey = null, prepareSignature = '', approvalKey = null;
  const context = () => {
    const state = getState(); const publication = state.activePublication ?? state.publications[0] ?? null;
    return {state, publication, owner: isPublishingOwner(state.principal, state.workspaceId, state.workspaceSlug),
      platform: el('publishing-platform').value};
  };
  function sync() {
    const {state, publication, owner, platform} = context();
    const next = `${state.projectId ?? ''}:${publication?.publication_id ?? ''}`;
    if (next !== scope) {
      scope = next; review = null; work = null; grant = null; reviewError = ''; workError = ''; approvalKey = null;
      el('publishing-acknowledge').checked = false;
    }
    const select = el('publishing-profile'); const selected = select.value;
    select.replaceChildren();
    const option = (value, label) => {
      const row = root.createElement('option'); row.value = value; row.textContent = label; select.append(row);
    };
    option('', 'Chọn kênh đã cấu hình');
    profiles.filter(p => p.target.workspace_id === state.workspaceId && p.target.platform === platform)
      .forEach(p => option(p.target.profile_id, `${p.target.target_account_id} · bản ${p.target.profile_version}`));
    if ([...select.options].some(item => item.value === selected)) select.value = selected;
    const enabled = state.publishingPlatforms.some(p => p.platform === platform && p.live_execution_enabled === true);
    const final = state.productionPackage?.latest_final_render;
    const eligible = state.productionPackage?.current_for_timeline === true && state.productionPackage?.approval?.status === 'approved'
      && final?.status === 'ready' && final.qc_status === 'passed';
    el('publishing-prepare').disabled = busy || !owner || !enabled || !eligible || !select.value;
    el('publishing-refresh').disabled = busy || !state.projectId;
    const applicable = publication?.mode === 'live' && ['awaiting_publish_approval', 'publishing'].includes(publication.status);
    el('publishing-acknowledge').disabled = busy || !owner || !applicable || !review || review.owner_gates_enabled !== true;
    el('publishing-consent').disabled = busy || !owner || !applicable || !review || !el('publishing-acknowledge').checked
      || review.owner_gates_enabled !== true;
    const valid = usablePublishGrant(grant, review);
    el('publishing-enqueue').disabled = busy || !owner || !valid || review?.owner_gates_enabled !== true || Boolean(work);
    el('publishing-revoke').disabled = busy || !owner || !grant || grant.revoked;
    el('publishing-review-text').textContent = review ? [
      review.mock ? 'Mô phỏng provider' : 'Provider đã cấu hình; thao tác thật vẫn cần Owner',
      `Video: ${review.final_render_id}`, `SHA256: ${review.artifact_sha256}`,
      `Kênh: ${review.target_binding?.target_account_id ?? 'chưa có'}`,
      `Tiêu đề: ${review.metadata?.title ?? ''}`, `Quyền riêng tư: ${review.metadata?.privacy ?? ''}`,
      `Mô tả: ${review.metadata?.description ?? ''}`, `Caption: ${review.metadata?.caption ?? ''}`,
      `Hashtag: ${(review.metadata?.hashtags ?? []).join(', ')}`,
      `Lịch: ${review.metadata?.scheduled_at ?? 'không đặt'}`,
      valid ? `Duyệt publish có hiệu lực tới ${grant.expires_at}` : 'Chưa có duyệt publish hiện tại',
    ].join('\n') : reviewError || 'Cập nhật để đọc bản review và kênh. Việc đọc không cấp quyền publish.';
    el('publishing-work-text').textContent = work ? `Hàng đợi: ${work.status} · ${work.work_id}${work.failure_code ? ` · ${work.failure_code}` : ''}`
      : workError || 'Chưa có tác vụ publish được xếp hàng.';
  }
  async function refresh() {
    const {state, publication} = context(); const project = state.projectId; const expected = scope;
    const base = `/api/v1/projects/${project}`;
    const results = await Promise.allSettled([
      api(`${base}/publishing-profiles`, {cache: 'no-store'}), api('/api/v1/publishing-platforms', {cache: 'no-store'}),
      publication?.mode === 'live' ? api(`${base}/publications/${publication.publication_id}/publish-review`, {cache: 'no-store'}) : Promise.resolve(null),
      publication?.mode === 'live' ? api(`${base}/publications/${publication.publication_id}/publishing-work`, {cache: 'no-store'}) : Promise.resolve(null),
      publication ? api(`${base}/publications/${publication.publication_id}`, {cache: 'no-store'}) : Promise.resolve(null),
    ]);
    if (scope !== expected || getState().projectId !== project) return;
    profiles = results[0].status === 'fulfilled' ? results[0].value : [];
    state.publishingPlatforms = results[1].status === 'fulfilled' ? results[1].value : [];
    review = results[2].status === 'fulfilled' ? results[2].value : null;
    reviewError = results[2].status === 'rejected' ? results[2].reason.message : '';
    work = results[3].status === 'fulfilled' ? results[3].value : null;
    workError = results[3].status === 'rejected' ? `Hàng đợi chưa khả dụng: ${results[3].reason.message}` : '';
    grant = review?.active_publish_approval ?? null;
    if (!usablePublishGrant(grant, review)) approvalKey = null;
    el('publishing-acknowledge').checked = false;
    if (results[4].status === 'fulfilled' && results[4].value) setPublication(results[4].value);
    sync();
  }
  async function action(callback) {
    if (busy) return;
    busy = true; sync();
    try { await callback(); } catch (error) { toast(error.message, true); }
    finally { busy = false; sync(); }
  }
  function ownerRequired() {
    if (!context().owner) throw new Error('Cần quyền Owner của workspace này.');
  }
  el('publishing-refresh').addEventListener('click', () => action(refresh));
  el('publishing-prepare').addEventListener('click', () => action(async () => {
    ownerRequired(); const {state} = context(); const project = state.projectId;
    const currentPayload = publicationPayload();
    if (!currentPayload) throw new Error('Cần final render hiện tại đã duyệt.');
    const payload = {...currentPayload, mode: 'live', publishing_profile_id: el('publishing-profile').value};
    if (!payload.publishing_profile_id) throw new Error('Chọn kênh trước khi chuẩn bị review.');
    const signature = JSON.stringify(payload);
    if (signature !== prepareSignature) { prepareSignature = signature; prepareKey = `publish-review-${uuid()}`; }
    const result = await api(`/api/v1/projects/${project}/publish`, {method: 'POST', headers: {'Idempotency-Key': prepareKey}, body: JSON.stringify(payload)});
    if (getState().projectId !== project) return;
    setPublication(result); sync(); await refresh();
    toast('Đã chuẩn bị review. Chưa có duyệt publish hoặc upload.');
  }));
  el('publishing-consent').addEventListener('click', () => action(async () => {
    ownerRequired(); const {state, publication} = context(); const expected = scope;
    const payload = publishApprovalPayload(review, publication, el('publishing-acknowledge').checked);
    approvalKey ??= `publish-consent-${uuid()}`;
    const result = await api(`/api/v1/projects/${state.projectId}/publications/${publication.publication_id}/publish-approval`,
      {method: 'POST', headers: {'Idempotency-Key': approvalKey}, body: JSON.stringify(payload)});
    if (scope !== expected) return;
    grant = result; el('publishing-acknowledge').checked = false;
    toast('Đã duyệt riêng cho publish. Chưa xếp hàng hoặc upload.');
  }));
  el('publishing-enqueue').addEventListener('click', () => action(async () => {
    ownerRequired(); const {state, publication} = context(); const expected = scope;
    if (!usablePublishGrant(grant, review)) throw new Error('Duyệt publish hết hạn hoặc đã thay đổi.');
    const result = await api(`/api/v1/projects/${state.projectId}/publications/${publication.publication_id}/publishing-work`,
      {method: 'POST', body: JSON.stringify({publish_approval_id: grant.publish_approval_id})});
    if (scope !== expected) return;
    work = result; toast('Đã xếp hàng. Worker chỉ thực hiện khi mọi điều kiện hiện tại còn hợp lệ.');
  }));
  el('publishing-revoke').addEventListener('click', () => action(async () => {
    ownerRequired(); const {state, publication} = context(); const expected = scope;
    if (!grant) throw new Error('Chưa có duyệt publish.');
    const result = await api(`/api/v1/projects/${state.projectId}/publications/${publication.publication_id}/publish-approval/revoke`,
      {method: 'POST', body: JSON.stringify({publish_approval_id: grant.publish_approval_id})});
    if (scope !== expected) return;
    grant = result; approvalKey = null; toast('Đã thu hồi lần duyệt này; bài đăng hoặc yêu cầu đã gửi không bị xóa.');
  }));
  el('publishing-acknowledge').addEventListener('change', sync);
  el('publishing-profile').addEventListener('change', sync);
  return {sync, refresh};
}
