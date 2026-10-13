// Read-only imported source proof. A receipt never grants approval or ASR authority.
const sha = /^[a-f0-9]{64}$/;
const id = {asset: /^ast_[A-Za-z0-9_-]{4,60}$/, project: /^prj_[A-Za-z0-9_-]{4,60}$/,
  family: /^vfa_[a-f0-9]{32}$/, member: /^vfm_[a-f0-9]{32}$/, receipt: /^vfr_[a-f0-9]{32}$/};
const verified = new WeakSet();
const stable = v => JSON.stringify(v, (_key, value) => value && typeof value === 'object' && !Array.isArray(value)
  ? Object.fromEntries(Object.keys(value).sort().map(k => [k, value[k]])) : value);
const demand = (ok, message = 'Biên nhận nguồn sao chép chưa khớp dự án hiện tại.') => {if (!ok) throw Error(message);};
function freeze(value) {if (value && typeof value === 'object') {Object.values(value).forEach(freeze); Object.freeze(value);} return value;}

export function isVerifiedVariantSource(asset, state) {
  const p = asset?.provenance;
  return !!(p && p.source_type === 'verified_variant_derivative' && id.asset.test(asset.asset_id)
    && asset.project_id === state.projectId && asset.workspace_id === state.workspaceId && asset.asset_class === 'source'
    && ['audio', 'video'].includes(asset.kind) && id.project.test(p.parent_project_id) && p.parent_project_id !== asset.project_id
    && id.asset.test(p.parent_asset_id) && p.parent_asset_id !== asset.asset_id && id.receipt.test(p.derivation_receipt_id)
    && sha.test(p.input_sha256) && sha.test(p.parent_record_sha256) && sha.test(asset.checksum_sha256)
    && Number.isSafeInteger(asset.size_bytes) && asset.size_bytes > 0 && Number.isInteger(asset.version) && asset.version >= 1
    && p.source_bytes_verified === true && p.approval_inherited === false && p.rights_override_inherited === false
    && p.publishing_enabled === false && p.external_call === false && p.new_inference_calls === 0
    && (p.provider_calls === undefined || p.provider_calls === 0));
}

function origin(state, asset) {
  demand(isVerifiedVariantSource(asset, state));
  const timeline = state.timeline, p = timeline?.snapshot?.metadata?.sql_variant_derivative;
  demand(timeline?.project_id === state.projectId && timeline.workspace_id === state.workspaceId
    && Number.isInteger(timeline.current_version) && timeline.current_version >= 1
    && p?.schema_version === 'sql-variant-evidence-lineage.v1' && id.family.test(p.family_id) && id.member.test(p.member_id)
    && p.master_project_id === asset.provenance.parent_project_id && p.approval_inherited === false
    && p.rights_override_inherited === false && p.new_inference_calls === 0 && p.human_review_required === true
    && sha.test(p.family_snapshot_sha256) && sha.test(p.source_timeline_sha256)
    && timeline.snapshot.source_media_mutated === false && timeline.snapshot.publish_requested === false);
  return p;
}

export function variantReceiptPath(state, asset) {
  const p = origin(state, asset);
  return `/api/v1/projects/${encodeURIComponent(p.master_project_id)}/variant-families/${encodeURIComponent(p.family_id)}`
    + `/receipts/${encodeURIComponent(asset.provenance.derivation_receipt_id)}`;
}

function validateReceipt(receipt, state, asset) {
  const p = origin(state, asset), result = receipt?.result, source = asset.provenance;
  demand(receipt?.schema_version === 'sql-variant-uploaded-receipt.v1' && receipt.state === 'ready' && receipt.error_code === null
    && receipt.workspace_id === state.workspaceId && receipt.receipt_id === source.derivation_receipt_id
    && receipt.family_id === p.family_id && receipt.member_id === p.member_id && receipt.input_sha256 === source.input_sha256
    && sha.test(receipt.request_sha256) && sha.test(receipt.result_sha256) && typeof receipt.actor_ref === 'string'
    && receipt.actor_ref.trim() && receipt.actor_ref.length <= 160 && !/[\u0000-\u001f]/.test(receipt.actor_ref)
    && result?.schema_version === 'sql-variant-uploaded-result.v1' && result.child_project_id === state.projectId
    && result.content_version_id === asset.project_version_id && result.timeline_id === state.timeline.timeline_id
    && sha.test(result.timeline_sha256) && sha.test(result.original_graph_sha256) && sha.test(result.original_uploads_sha256)
    && sha.test(result.original_jobs_sha256) && sha.test(result.original_job_relations_sha256)
    && result.asset_map?.[source.parent_asset_id] === asset.asset_id && result.identity_map?.[source.parent_asset_id] === asset.asset_id
    && result.human_review_required === true && result.rights_review_required === true && result.reframe_attention_required === true
    && result.raw_evidence_rewritten === false && result.new_provider_billed_cost_vnd === 0 && result.operating_cost_vnd === null);
  const copied = result.copies?.[source.parent_asset_id];
  demand(copied?.object_key === asset.object_key && copied.sha256 === asset.checksum_sha256
    && copied.size_bytes === asset.size_bytes && copied.content_type === asset.content_type && copied.storage_provider === asset.storage_provider
    && asset.object_key.startsWith(`workspaces/${state.workspaceId}/projects/${state.projectId}/variant-imports/${p.member_id}/`));
  for (const safety of [receipt.safety, result.safety]) demand(safety && safety.provider_calls === 0 && safety.new_inference_calls === 0
    && safety.child_projects_created === 1 && safety.source_bytes_verified === true && safety.approval_inherited === false
    && safety.rights_override_inherited === false && safety.automatic_render === false && safety.publishing_enabled === false);
  return receipt;
}

export function variantSourceFingerprint(state, asset) {
  const p = origin(state, asset);
  return stable({asset, origin: p, timeline_id: state.timeline.timeline_id, workspace_id: state.workspaceId, project_id: state.projectId});
}

export async function verifyVariantReceipt(receipt, state, asset, cryptoImpl = globalThis.crypto) {
  // Keep exactly the response and source binding checked before the first await.
  // The caller may update its DTO while WebCrypto is computing the digest.
  receipt = freeze(structuredClone(receipt));
  validateReceipt(receipt, state, asset);
  const fingerprint = variantSourceFingerprint(state, asset);
  const bytes = new TextEncoder().encode(stable(receipt.result));
  const hash = [...new Uint8Array(await cryptoImpl.subtle.digest('SHA-256', bytes))].map(x => x.toString(16).padStart(2, '0')).join('');
  demand(hash === receipt.result_sha256, 'Checksum biên nhận nguồn sao chép không khớp.');
  const importJobIds = {};
  for (const [parent, child] of Object.entries(receipt.result.identity_map)) {
    if (!/^aud_[a-f0-9]{24}$/.test(parent)) continue;
    demand(/^aud_[a-f0-9]{24}$/.test(child));
    // Backend uuid5(NAMESPACE_URL, 'sql-master-variants.v1/'+member+'/'+parent).
    // This validates the stored import audit; it never creates or queues a job.
    const namespace = Uint8Array.from('6ba7b8119dad11d180b400c04fd430c8'.match(/../g), n => parseInt(n, 16));
    const name = new TextEncoder().encode(`sql-master-variants.v1/${receipt.member_id}/${parent}`);
    const raw = new Uint8Array(namespace.length + name.length); raw.set(namespace); raw.set(name, namespace.length);
    const digest = new Uint8Array(await cryptoImpl.subtle.digest('SHA-1', raw)).slice(0, 16);
    digest[6] = (digest[6] & 15) | 80; digest[8] = (digest[8] & 63) | 128;
    importJobIds[child] = 'job_vimport_' + [...digest].map(x => x.toString(16).padStart(2, '0')).join('');
  }
  const proof = freeze({receipt, importJobIds, fingerprint});
  verified.add(proof); return proof;
}

export function verifiedVariantReceipt(state, asset) {
  const proof = (state.verifiedVariantReceipts ?? []).find(v => verified.has(v)
    && v.receipt.receipt_id === asset.provenance?.derivation_receipt_id && v.fingerprint === variantSourceFingerprint(state, asset));
  demand(proof, 'Đọc lại biên nhận nguồn sao chép trước khi kiểm tra hoặc gửi phân tích mới.');
  return validateReceipt(proof.receipt, state, asset);
}

export function verifiedVariantImportJobId(state, asset, audioId) {
  verifiedVariantReceipt(state, asset);
  const proof = state.verifiedVariantReceipts.find(v => verified.has(v)
    && v.fingerprint === variantSourceFingerprint(state, asset) && v.receipt.receipt_id === asset.provenance.derivation_receipt_id);
  demand(proof?.importJobIds[audioId], 'Nhật ký nhập audio chưa khớp đồ thị bằng chứng đã lưu.');
  return proof.importJobIds[audioId];
}

export async function loadVariantReceipt(state, asset, api, getCurrentState, cryptoImpl = globalThis.crypto) {
  const path = variantReceiptPath(state, asset), bound = variantSourceFingerprint(state, asset);
  const receipt = await api(path), proof = await verifyVariantReceipt(receipt, state, asset, cryptoImpl);
  const current = getCurrentState(), now = current.assets?.find(a => a.asset_id === asset.asset_id);
  demand(now && variantSourceFingerprint(current, now) === bound, 'Nguồn sao chép đã đổi trong lúc đọc biên nhận.');
  return proof;
}
