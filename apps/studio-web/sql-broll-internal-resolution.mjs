// Explicit reuse of a saved internal candidate. No timers, latest-job lookup or timeline write.
import {audioRole, audioByteHash} from './uploaded-audio-review.mjs';
import {sessionToken} from './auth.mjs';
import {videoWordSessionStorage} from './video-transcript-word-review.mjs';

const copy = structuredClone;
const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
const stable = v => JSON.stringify(v, (_k, x) => object(x)
  ? Object.fromEntries(Object.keys(x).sort().map(k => [k, x[k]])) : x);
const same = (a, b) => stable(a) === stable(b);
const demand = (v, message) => {if (!v) throw Error(message);};
const exact = (v, keys) => object(v) && same(Object.keys(v).sort(), [...keys].sort());
const sha = v => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const id = (v, prefix) => typeof v === 'string' && new RegExp('^' + prefix + '_[A-Za-z0-9_-]{4,60}$').test(v);
const key = v => typeof v === 'string' && /^[A-Za-z0-9_-]{8,128}$/.test(v);
const positive = v => typeof v === 'number' && Number.isFinite(v) && v > 0;
const sessionFields = ['subject', 'display_name', 'platform_role', 'workspace_roles', 'expires_at', 'human_write_enabled'];
const principal = p => Object.fromEntries(sessionFields.map(k => [k, p?.[k]]));
const flags = v => v.provider_calls === 0 && v.publishing_enabled === false && v.owner_approval_inferred === false;
const contextKeys = ['schema_version', 'workspace_id', 'project_id', 'actor_ref', 'authority_sha256', 'timeline_id',
  'timeline_version', 'timeline_version_id', 'timeline_sha256', 'source', 'source_asset_custody', 'project', 'plan',
  'item', 'candidates', 'provider_calls', 'publishing_enabled', 'owner_approval_inferred', 'context_json', 'context_sha256'];
const receiptKeys = ['schema_version', 'operation_id', 'workspace_id', 'project_id', 'actor_ref', 'authority_sha256',
  'request_key', 'request_sha256', 'context_sha256', 'media_plan_id', 'media_plan_item_id', 'resolution_job_id',
  'asset_id', 'asset_custody_sha256', 'timeline_id', 'timeline_version_id', 'timeline_version', 'source',
  'provider_calls', 'publishing_enabled', 'owner_approval_inferred'];
const resultKeys = ['schema_version', 'receipt', 'job', 'state', 'source_current', 'can_adopt', 'output', 'error_code',
  'needs_attention', 'handoff', 'provider_calls', 'publishing_enabled', 'owner_approval_inferred'];
const bodyKeys = ['request_key', 'context_sha256', 'asset_id', 'acknowledged'];
const recordKeys = ['schema_version', 'body', 'context', 'core_sha256', 'principal_sha256', 'credential_sha256', 'receipt'];
const ownItemFields = ['status', 'updated_at', 'selected_media_asset_id', 'needs_attention'];
const custodyFields = ['asset_id', 'workspace_id', 'project_id', 'project_version_id', 'asset_class', 'kind',
  'object_key', 'storage_provider', 'content_type', 'size_bytes', 'checksum_sha256', 'version'];

function core(s) {return [s.workspaceId, s.workspaceSlug ?? null, s.projectId, principal(s.principal), s.timeline,
  s.analysis, s.assets, s.mediaPlanId, s.mediaPlanItemId, s.internalResolutionDraft ?? null];}
function binding(s) {return stable([core(s), s.mediaPlans ?? null]);}
function readBinding(s) {return stable([core(s).slice(0, -1), s.mediaPlans ?? null]);}
function stateValid(s, write, now) {
  demand(id(s.workspaceId, 'wsp') && id(s.projectId, 'prj') && id(s.mediaPlanId, 'mpl') && id(s.mediaPlanItemId, 'mpi')
    && typeof s.principal?.subject === 'string' && s.principal.subject && Date.parse(s.principal.expires_at) > now
    && ['viewer', 'editor', 'reviewer', 'owner'].includes(audioRole(s)) && !s.busy && !s.dirty,
  'Cần phiên hợp lệ, lưu bản sửa khác và chọn đúng cảnh B-roll.');
  if (write) demand(['editor', 'reviewer', 'owner'].includes(audioRole(s)) && s.principal.human_write_enabled === true,
    'Phiên này chưa được phép phân giải B-roll.');
  const t = s.timeline, a = s.analysis, m = t?.snapshot?.metadata;
  const asset = s.assets?.find(v => v.asset_id === m?.source_asset_id);
  demand(t?.workspace_id === s.workspaceId && t.project_id === s.projectId && id(t.timeline_id, 'tml')
    && t.source_kind === 'video_analysis' && t.source_media_mutated === false && t.publish_requested === false
    && Number.isSafeInteger(t.current_version) && t.current_version >= 1 && typeof t.current_version_id === 'string'
    && t.snapshot?.source_media_mutated === false && t.snapshot.publish_requested === false
    && a?.analysis_id === t.source_analysis_id && a.analysis_id === m?.source_analysis_id && a.asset_id === asset?.asset_id
    && a.workspace_id === s.workspaceId && a.project_id === s.projectId && a.status === 'succeeded'
    && a.source_media_mutated === false && a.publish_requested === false && sha(a.fingerprint)
    && asset?.workspace_id === s.workspaceId && asset.project_id === s.projectId && sha(asset.checksum_sha256)
    && a.configuration?.asset_id === asset.asset_id && a.source_media?.media_kind === 'video'
    && positive(m.source_duration_seconds) && a.source_media.duration_seconds === m.source_duration_seconds
    && asset.provenance?.media_metadata?.duration_seconds === m.source_duration_seconds
    && Object.hasOwn(a.source_media, 'audio_codec') && !['', undefined, 'unknown'].includes(a.source_media.audio_codec),
  'Timeline, phân tích và video nguồn chưa khớp.');
  return asset;
}
function sourceValid(v, s) {
  const a = s.analysis, m = s.timeline.snapshot.metadata, asset = stateValid(s, false, -Infinity), r = m.transcript_revision;
  demand(object(v) && v.analysis_id === a.analysis_id && v.analysis_fingerprint === a.fingerprint && v.asset_id === asset.asset_id
    && v.source_sha256 === asset.checksum_sha256 && v.object_key === asset.object_key && v.duration_seconds === m.source_duration_seconds
    && v.has_audio === (a.source_media.audio_codec !== null) && v.transcript_id === (r?.transcript_id ?? null)
    && v.transcript_version === (r?.version ?? null) && (v.has_audio ? id(v.transcript_id, 'trn') && sha(v.transcript_sha256)
      : v.transcript_id === null && v.transcript_version === null && v.transcript_sha256 === null),
  'Nguồn hoặc transcript đã đổi.');
}
export function validateBrollInternalContext(v, s, now = Date.now()) {
  stateValid(s, false, now); const t = s.timeline;
  demand(exact(v, contextKeys) && v.schema_version === 'broll-internal-resolution-context.v1' && flags(v)
    && v.workspace_id === s.workspaceId && v.project_id === s.projectId && v.actor_ref === s.principal.subject
    && sha(v.authority_sha256) && sha(v.context_sha256) && sha(v.timeline_sha256) && typeof v.context_json === 'string'
    && v.timeline_id === t.timeline_id && v.timeline_version_id === t.current_version_id && v.timeline_version === t.current_version
    && v.plan?.media_plan_id === s.mediaPlanId && v.plan.project_id === s.projectId && v.plan.workspace_id === s.workspaceId
    && v.plan.status === 'draft' && v.plan.analysis_id === s.analysis.analysis_id
    && v.plan.configuration_json?.purpose === 'supporting_broll' && v.plan.configuration_json.analysis_id === s.analysis.analysis_id
    && v.item?.media_plan_id === s.mediaPlanId && v.item.media_plan_item_id === s.mediaPlanItemId
    && Array.isArray(v.candidates) && v.candidates.length > 0 && v.candidates.length <= 200,
  'Bản đọc phân giải chưa đúng dự án, cảnh và nguồn.');
  sourceValid(v.source, s);
  const ids = new Set();
  for (const c of v.candidates) {
    demand(exact(c, ['candidate', 'asset_id', 'asset_custody', 'available', 'unavailable_code']) && id(c.asset_id, 'ast')
      && c.asset_id !== v.source.asset_id && !ids.has(c.asset_id) && c.candidate?.asset_id === c.asset_id
      && typeof c.available === 'boolean' && (c.available ? c.unavailable_code === null : typeof c.unavailable_code === 'string'),
    'Danh sách lựa chọn B-roll chưa hợp lệ.'); ids.add(c.asset_id);
  }
  return v;
}

export function initializeSqlBrollInternalResolution({api, getState, getSessionToken = sessionToken,
  storage = videoWordSessionStorage(), cryptoImpl = globalThis.crypto, clock = () => Date.now(),
  newRequestKey = () => 'bri_' + cryptoImpl.randomUUID(), onRead = async () => {}, onResolved = async () => true,
  onStatus = () => {}, onBusyChanged = () => {}}) {
  let disposed = false, busy = false, epoch = 0, view = null, pending = null, observation = null;
  const retained = new Map();
  const digest = v => audioByteHash(new TextEncoder().encode(typeof v === 'string' ? v : stable(v)), cryptoImpl);
  function token() {const v = getSessionToken(); demand(typeof v === 'string' && v.trim() === v && v.length >= 8 && v.length <= 2048,
    'Cần token phiên hợp lệ.'); return v;}
  const bucket = () => 'vf-sql-broll-internal-pending-v1:' + stable([getState().workspaceId, getState().projectId, getState().principal?.subject]);
  function capture(write) {stateValid(getState(), write, clock()); demand(!disposed && !busy, 'Đang có thao tác B-roll hoặc đã đóng controller.');
    const s = getState(); return {ticket: ++epoch, write, token: token(), bucket: bucket(), binding: binding(s), core: stable(core(s)),
      storedCore: stable(core(s).slice(0, -1)),
      path: `/api/v1/projects/${s.projectId}/media-plans/${s.mediaPlanId}/items/${s.mediaPlanItemId}/internal-resolution-review`};}
  function current(c, full = true) {stateValid(getState(), c.write, clock()); demand(!disposed && c.ticket === epoch
    && token() === c.token && bucket() === c.bucket && (full ? binding(getState()) === c.binding : stable(core(getState())) === c.core),
  'Phiên, nguồn, đề xuất hoặc lựa chọn đã đổi; giữ yêu cầu để đối chiếu.'); return true;}
  function raw(c) {const v = storage?.getItem(c.bucket); current(c); demand(v === null || v === undefined || typeof v === 'string',
    'Không đọc được ô chờ B-roll.'); if (retained.has(c.bucket)) demand(retained.get(c.bucket) === v, 'Ô chờ đã bị thay hoặc xóa.'); return v;}
  function owns(c, p, full = true) {const value = storage?.getItem(c.bucket); current(c, full);
    demand(pending === p && retained.get(c.bucket) === p.raw && value === p.raw, 'Yêu cầu đang giữ đã bị thay hoặc xóa.'); return true;}
  async function session(c) {const p = await api('/api/v1/auth/session', {cache: 'no-store'}); current(c);
    demand(same(principal(p), principal(getState().principal)), 'Phiên công khai đã thay đổi.');}
  async function checkedContext(v, c) {
    validateBrollInternalContext(v, getState(), clock());
    const hash = await digest(v.context_json); current(c); demand(hash === v.context_sha256, 'Hash ngữ cảnh B-roll không đúng.');
    const {context_json, context_sha256, ...projected} = v;
    demand(same(JSON.parse(context_json), projected), 'Nội dung ngữ cảnh không khớp JSON gốc.');
    // Python JSON retains 16.0 where JS emits 16. The server snapshot/provenance
    // hashes are opaque evidence inside the verified literal context_json.
    // IDs/versions/fields and the entire local snapshot remain fenced instead.
    for (const evidence of [v.source_asset_custody, ...v.candidates.map(x => x.asset_custody)]) {
      const asset = getState().assets.find(a => a.asset_id === evidence?.asset_id);
      demand(asset && asset.workspace_id === getState().workspaceId && asset.project_id === getState().projectId,
        'Tài sản không còn trong dự án.');
      const expected = Object.fromEntries(custodyFields.map(k => [k, asset[k]]));
      demand(sha(evidence.provenance_sha256), 'Bằng chứng provenance chưa hợp lệ.');
      expected.provenance_sha256 = evidence.provenance_sha256;
      demand(same(expected, evidence), 'Quyền, phiên bản hoặc nơi lưu tài sản đã đổi.');
    }
    for (const c of v.candidates.filter(x => x.available)) {
      const asset = getState().assets.find(a => a.asset_id === c.asset_id), candidate = c.candidate, m = asset.provenance?.media_metadata;
      demand(candidate.checksum_sha256 === asset.checksum_sha256 && candidate.content_type === asset.content_type
        && candidate.rights_status === (asset.provenance.rights_status ?? 'unknown')
        && candidate.license === (asset.provenance.license ?? 'unknown') && candidate.width === m?.width && candidate.height === m?.height
        && (!asset.content_type.startsWith('video/') || candidate.duration_seconds === m.duration_seconds),
      'Danh sách tư liệu đã lưu không còn đúng quyền hoặc thông số hiện tại.');
    }
    return v;
  }
  async function load(c) {
    const found = raw(c); if (found === null || found === undefined) {pending = null; return null;}
    const value = JSON.parse(found);
    demand(exact(value, recordKeys) && value.schema_version === 'sql-broll-internal-pending.v1'
      && exact(value.body, bodyKeys) && key(value.body.request_key) && sha(value.body.context_sha256)
      && id(value.body.asset_id, 'ast') && value.body.acknowledged === true && sha(value.core_sha256)
      && sha(value.principal_sha256) && sha(value.credential_sha256) && (value.receipt === null || object(value.receipt)),
    'Bản ghi đang giữ thiếu bằng chứng; không xóa hoặc gửi yêu cầu khác.');
    await checkedContext(value.context, c); current(c);
    demand(value.body.context_sha256 === value.context.context_sha256
      && value.context.candidates.some(x => x.asset_id === value.body.asset_id && x.available), 'Lựa chọn đang giữ không thuộc bản đọc.');
    for (const [field, data] of [['core_sha256', c.storedCore], ['principal_sha256', principal(getState().principal)], ['credential_sha256', c.token]]) {
      const h = await digest(data); current(c); demand(h === value[field], 'Yêu cầu đang giữ thuộc nguồn hoặc phiên khác.');
    }
    const p = {value, raw: found}; pending = p; retained.set(c.bucket, found); owns(c, p); return p;
  }
  async function hold(c, body) {
    demand(raw(c) == null, 'Có yêu cầu chưa rõ kết quả; không tạo yêu cầu mới.');
    const coreHash = await digest(c.storedCore); current(c);
    const principalHash = await digest(principal(getState().principal)); current(c);
    const credentialHash = await digest(c.token); current(c);
    const value = {schema_version: 'sql-broll-internal-pending.v1', body: copy(body), context: copy(view.context),
      core_sha256: coreHash, principal_sha256: principalHash, credential_sha256: credentialHash, receipt: null};
    demand(raw(c) == null, 'Một yêu cầu khác đã xuất hiện.');
    const p = {value, raw: stable(value)}; storage.setItem(c.bucket, p.raw); current(c);
    demand(storage.getItem(c.bucket) === p.raw, 'Không giữ được yêu cầu trước khi gửi.'); current(c);
    pending = p; retained.set(c.bucket, p.raw); owns(c, p); return p;
  }
  function matchesReceipt(r, p) {const v = p.value, x = v.context, b = v.body;
    demand(exact(r, receiptKeys) && r.schema_version === 'broll-internal-resolution-receipt.v1' && flags(r)
      && id(r.operation_id, 'sop') && id(r.resolution_job_id, 'mrj') && sha(r.request_sha256) && sha(r.asset_custody_sha256)
      && r.workspace_id === x.workspace_id && r.project_id === x.project_id && r.actor_ref === x.actor_ref
      && r.authority_sha256 === x.authority_sha256 && r.request_key === b.request_key && r.context_sha256 === b.context_sha256
      && r.asset_id === b.asset_id && r.media_plan_id === x.plan.media_plan_id && r.media_plan_item_id === x.item.media_plan_item_id
      && r.timeline_id === x.timeline_id && r.timeline_version_id === x.timeline_version_id && r.timeline_version === x.timeline_version
      && same(r.source, x.source) && (v.receipt === null || same(r, v.receipt)), 'Biên nhận không đúng lựa chọn và job ban đầu.');
  }
  async function checkedResult(v, c, p) {
    owns(c, p); demand(exact(v, resultKeys) && v.schema_version === 'broll-internal-resolution-observation.v1' && flags(v), 'Bản theo dõi chưa hợp lệ.');
    matchesReceipt(v.receipt, p); const r = v.receipt, j = v.job, x = p.value.context;
    demand(j?.resolution_job_id === r.resolution_job_id && j.workspace_id === r.workspace_id && j.project_id === r.project_id
      && j.media_plan_id === r.media_plan_id && j.media_plan_item_id === r.media_plan_item_id && j.provider_key === 'internal-media'
      && j.capability === 'internal_media' && j.operation === 'reuse-user-asset' && j.external_call === false && j.paid === false
      && j.real_provider_tested === false && j.provider_job_id === null && j.selected_candidate_id === null
      && j.provenance?.reviewed_internal_resolution_v1?.operation_id === r.operation_id
      && j.provenance.reviewed_internal_resolution_v1.binding_sha256 === r.context_sha256
      && j.provenance.request?.source_asset_id === r.asset_id && j.provenance.source_media_mutated === false && j.provenance.publish_requested === false
      && ['queued', 'running', 'failed', 'cancelled', 'succeeded'].includes(j.status)
      && ['resolved', 'queued', 'failed', 'cancelled', 'unknown'].includes(v.state) && typeof v.source_current === 'boolean'
      && typeof v.can_adopt === 'boolean' && typeof v.needs_attention === 'boolean'
      && ['enqueued', 'handoff_pending', 'unverified', 'not_queued', 'source_changed'].includes(v.handoff), 'Job không đúng phân giải nội bộ đã giữ.');
    demand((v.state !== 'queued' || j.status === 'queued' && v.source_current === true)
      && (v.state !== 'failed' || j.status === 'failed') && (v.state !== 'cancelled' || j.status === 'cancelled')
      && (v.state !== 'unknown' || ['queued', 'running', 'succeeded'].includes(j.status))
      && (v.source_current || v.needs_attention === true)
      && (!['running', 'failed', 'cancelled'].includes(j.status) || v.needs_attention === true)
      && (j.status === 'succeeded' || j.output_media_asset_id === null), 'Trạng thái job và bằng chứng theo dõi mâu thuẫn.');
    const chosen = x.candidates.find(a => a.asset_id === r.asset_id);
    const h = await digest(chosen.asset_custody); owns(c, p); demand(h === r.asset_custody_sha256
      && j.provenance.request.checksum_sha256 === chosen.asset_custody.checksum_sha256, 'Biên nhận tài sản đã đổi.');
    if (v.can_adopt) {
      const o = v.output, asset = getState().assets.find(a => a.asset_id === r.asset_id), m = asset?.provenance?.media_metadata;
      demand(v.state === 'resolved' && v.source_current === true && v.error_code === null && j.status === 'succeeded'
        && o?.media_asset_id === j.output_media_asset_id && o.asset_id === r.asset_id && o.project_id === r.project_id
        && o.workspace_id === r.workspace_id && o.provenance?.asset_checksum_sha256 === chosen.asset_custody.checksum_sha256
        && o.width === m?.width && o.height === m?.height && (!asset.content_type.startsWith('video/') || o.duration_seconds === m.duration_seconds)
        && o.rights_status === (asset.provenance.rights_status ?? 'unknown') && o.license === (asset.provenance.license ?? 'unknown')
        && typeof o.publishing_allowed === 'boolean' && (!o.publishing_allowed || ['owned', 'licensed', 'verified'].includes(o.rights_status)
          && o.production_eligible === true && !asset.provenance.fixture), 'Kết quả chưa chứng minh đúng tài sản hiện tại.');
    } else demand(v.output === null && v.state !== 'resolved', 'Job chưa xác minh không được có kết quả để nhận.');
    return v;
  }
  function saveReceipt(c, p, receipt) {
    if (p.value.receipt !== null) return p;
    owns(c, p); const next = {value: {...p.value, receipt: copy(receipt)}}; next.raw = stable(next.value);
    storage.setItem(c.bucket, next.raw); current(c);
    const found = storage.getItem(c.bucket); current(c); demand(found === next.raw, 'Không giữ được định danh job; không nhận kết quả.');
    pending = next; retained.set(c.bucket, next.raw); owns(c, next); return next;
  }
  function allowedInstall(before, after, v) {
    const normalize = plans => (plans ?? []).map(plan => ({...plan, items: plan.items?.map(item => {
      if (item.media_plan_item_id !== v.receipt.media_plan_item_id) return item;
      const result = {...item}; for (const k of ownItemFields) delete result[k]; return result;
    })}));
    demand(same(normalize(before), normalize(after)), 'Callback đã đổi dữ liệu ngoài cảnh B-roll đang phân giải.');
    const find = plans => plans?.flatMap(p => p.items ?? []).find(i => i.media_plan_item_id === v.receipt.media_plan_item_id);
    const old = find(before), now = find(after);
    if (!same(old, now)) demand(now?.status === 'resolved' && now.selected_media_asset_id === v.job.output_media_asset_id
      && typeof now.needs_attention === 'boolean', 'Callback chưa nhận đúng tư liệu của job ban đầu.');
  }
  async function receive(v, c, p) {
    await checkedResult(v, c, p); owns(c, p); p = saveReceipt(c, p, v.receipt); observation = copy(v);
    if (!v.can_adopt) {onStatus(v.state === 'queued' ? 'Job đã lưu. Chỉ gửi lại cùng yêu cầu khi cần.'
      : 'Kết quả chưa xác minh hoặc đã kết thúc; giữ nguyên yêu cầu để kiểm tra.'); return copy(v);}
    const beforePlans = copy(getState().mediaPlans ?? null); let active = true;
    const requestGuard = () => {demand(active, 'Phạm vi callback đã kết thúc.'); return owns(c, p);};
    try {requestGuard(); const result = await onResolved({receipt: copy(v.receipt), job: copy(v.job), output: copy(v.output),
      observation: copy(v), request: copy(p.value.body), context: copy(p.value.context)}, requestGuard);
      demand(result === true, 'Studio chưa xác nhận nhận đúng kết quả; giữ yêu cầu.');
    } finally {active = false;}
    current(c, false); allowedInstall(beforePlans, getState().mediaPlans, v);
    const installed = binding(getState());
    const final = () => {current(c, false); demand(binding(getState()) === installed, 'Studio đã đổi sau callback.');
      const found = storage.getItem(c.bucket); current(c, false); demand(binding(getState()) === installed && pending === p
        && retained.get(c.bucket) === p.raw && found === p.raw, 'Ô chờ hoặc nguồn đã đổi trước khi hoàn tất.'); return true;};
    final(); const h = await digest(p.value.context.context_json); final(); demand(h === p.value.body.context_sha256, 'Ngữ cảnh đã đổi.');
    demand(typeof storage.compareAndRemoveItem === 'function', 'Cần bộ nhớ có đối chiếu đồng bộ để hoàn tất.');
    final(); demand(storage.compareAndRemoveItem(c.bucket, p.raw) === true, 'Ô chờ đã đổi; không xóa yêu cầu khác.');
    current(c, false); demand(binding(getState()) === installed, 'Nguồn đã đổi khi hoàn tất.');
    retained.delete(c.bucket); pending = null; view = null; onStatus('Đã xác minh tư liệu nội bộ. Chưa áp dụng vào timeline.'); return copy(v);
  }
  async function run(write, fn) {const c = capture(write); busy = true;
    try {onBusyChanged(); current(c); return await fn(c);} finally {busy = false; onBusyChanged();}}
  async function reload() {return run(false, async c => {
    const p = await load(c); await session(c); const data = copy(await api(c.path, {cache: 'no-store'})); current(c);
    await checkedContext(data, c);
    if (p) {const old = copy(p.value.context), fresh = copy(data); for (const f of ownItemFields) fresh.item[f] = old.item[f];
      delete old.context_json; delete old.context_sha256; delete fresh.context_json; delete fresh.context_sha256;
      demand(same(old, fresh), 'Bản dựng đang giữ đã đổi; không tự khôi phục hoặc gửi lại.'); owns(c, p);}
    let active = true; const guard = () => {demand(active, 'Phạm vi bản đọc đã kết thúc.'); return p ? owns(c, p) : current(c);};
    try {guard(); await onRead(copy(data), guard);} finally {active = false;}
    current(c); if (p) owns(c, p); view = {context: copy(data), binding: readBinding(getState())}; return copy(data);
  });}
  async function admit(assetId, acknowledged) {return run(true, async c => {
    demand(acknowledged === true && id(assetId, 'ast') && view && view.binding === readBinding(getState()), 'Đọc bản mới, chọn tài sản và xác nhận rõ ràng.');
    demand(raw(c) == null && !pending, 'Đang có yêu cầu được giữ; không tạo yêu cầu mới.');
    await session(c); const latest = copy(await api(c.path, {cache: 'no-store'})); current(c); await checkedContext(latest, c);
    demand(same(latest, view.context) && latest.candidates.some(a => a.asset_id === assetId && a.available), 'Lựa chọn hoặc ngữ cảnh đã đổi.');
    const body = {request_key: newRequestKey(), context_sha256: latest.context_sha256, asset_id: assetId, acknowledged: true};
    demand(key(body.request_key), 'Khóa yêu cầu chưa hợp lệ.'); const p = await hold(c, body); owns(c, p);
    const result = copy(await api(c.path, {method: 'POST', body: stable(body)})); owns(c, p); return receive(result, c, p);
  });}
  async function observe() {return run(false, async c => {
    const p = await load(c); demand(p?.value.receipt, 'Chưa biết job chính xác. Chỉ gửi lại yêu cầu gốc khi xác nhận.'); await session(c); owns(c, p);
    const r = p.value.receipt; matchesReceipt(r, p); const result = copy(await api(c.path
      + `/requests/${p.value.body.request_key}/jobs/${r.resolution_job_id}`, {cache: 'no-store'})); owns(c, p);
    // Receiving a result is an editor action even when observation itself is readable.
    if (result.can_adopt) {stateValid(getState(), true, clock()); c.write = true;}
    return receive(result, c, p);
  });}
  async function retry(acknowledged) {return run(true, async c => {
    demand(acknowledged === true, 'Xác nhận gửi lại đúng yêu cầu đang giữ.'); const p = await load(c); demand(p, 'Không có yêu cầu gốc.');
    await session(c); owns(c, p);
    // The server atomically replays the original receipt/job and validates full custody before handoff.
    const result = copy(await api(c.path, {method: 'POST', body: stable(p.value.body)})); owns(c, p); return receive(result, c, p);
  });}
  return {reload, admit, observe, retry, sync() {if (view && view.binding !== readBinding(getState())) view = null;}, dispose() {disposed = true; epoch++; view = null;},
    isWorking: () => busy, isPending() {try {return pending !== null || storage?.getItem(bucket()) != null;} catch {return true;}},
    state: () => copy({context: view?.context ?? null, observation, pending: pending?.value ?? null, working: busy})};
}
