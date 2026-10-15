// An explicit, deferred B-roll plan. Mount/read/selection never POST or run a provider.
import {sessionToken} from './auth.mjs';
import {validateWitnessCapability, validateWitnessEnvelope, validateIssuedWitness, decodeWitnessPending,
  validateVerifiedWitness, validateWitnessRecovery} from './broll-request-witness.mjs';
const copy = structuredClone;
const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
const stable = value => JSON.stringify(value, (_k, v) => object(v)
  ? Object.fromEntries(Object.keys(v).sort().map(k => [k, v[k]])) : v);
const same = (a, b) => stable(a) === stable(b);
const hash = v => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const demand = (v, text) => {if (!v) throw Error(text);};
const exact = (v, keys) => object(v) && same(Object.keys(v).sort(), [...keys].sort());
const sessionFields = ['subject', 'display_name', 'platform_role', 'workspace_roles', 'expires_at', 'human_write_enabled'];
const session = p => Object.fromEntries(sessionFields.map(k => [k, p?.[k]]));
const roles = {viewer: 10, editor: 20, reviewer: 30, owner: 40};
export const defaultBrollPlanSettings = () => ({allow_stock: false, allow_ai_image: false, allow_ai_video: false,
  max_ai_cost_vnd: '0', resolver_priority: ['user_asset', 'internal_library']});

export function brollPlanSettings(value) {
  demand(exact(value, ['allow_stock', 'allow_ai_image', 'allow_ai_video', 'max_ai_cost_vnd', 'resolver_priority'])
    && typeof value.allow_stock === 'boolean' && value.allow_ai_image === false && value.allow_ai_video === false
    && value.max_ai_cost_vnd === '0' && Array.isArray(value.resolver_priority) && value.resolver_priority.length >= 1
    && value.resolver_priority.length <= 3 && new Set(value.resolver_priority).size === value.resolver_priority.length
    && value.resolver_priority.every(v => ['user_asset', 'internal_library', 'licensed_stock'].includes(v))
    && value.allow_stock === value.resolver_priority.includes('licensed_stock'), 'Chọn rõ nguồn và thứ tự B-roll. AI cần quy trình ngân sách được duyệt riêng.');
  return copy(value);
}

function boundary(s) {return stable([s.workspaceId, s.projectId, session(s.principal), s.timeline, s.analysis, s.assets,
  s.learning_snapshot_id ?? null]);}
function witnessSelection(s) {return stable([s.videoReviewSelection ?? null, s.analyses ?? null,
  s.versions ?? null, s.preview ?? null, s.productionPackage ?? null]);}
function validateState(s, write = false, now = Date.now()) {
  const p = s.principal, rank = Math.max(...[p?.platform_role, p?.workspace_roles?.['*'], p?.workspace_roles?.[s.workspaceId],
    s.workspaceSlug ? p?.workspace_roles?.['slug:' + s.workspaceSlug] : null].map(v => roles[v] ?? 0));
  demand(/^wsp_[A-Za-z0-9_-]{4,60}$/.test(s.workspaceId) && /^prj_[A-Za-z0-9_-]{4,60}$/.test(s.projectId)
    && typeof p?.subject === 'string' && p.subject && Date.parse(p.expires_at) > now
    && rank >= roles.viewer && !s.busy && !s.dirty, 'Cần phiên hợp lệ, lưu thay đổi và chờ tải xong.');
  if (write) demand(rank >= roles.editor && p.human_write_enabled === true, 'Phiên này chưa được phép tạo đề xuất.');
  demand(s.timeline?.workspace_id === s.workspaceId && s.timeline?.project_id === s.projectId
    && s.timeline.source_kind === 'video_analysis' && s.analysis?.analysis_id === s.timeline.source_analysis_id,
  'Chọn timeline video và kết quả phân tích cùng nguồn.');
}

export function validateBrollPlanContext(value, s, now = Date.now()) {
  validateState(s, false, now);
  const t = s.timeline, a = s.analysis, m = t.snapshot?.metadata;
  demand(object(value) && value.schema_version === 'broll-plan-review-context.v1' && hash(value.context_sha256)
    && hash(value.authority_sha256) && value.actor_ref === s.principal.subject
    && value.workspace_id === s.workspaceId && value.project_id === s.projectId && value.timeline_id === t.timeline_id
    && value.timeline_version === t.current_version && value.timeline_version_id === t.current_version_id
    && hash(value.timeline_sha256) && hash(value.supporting_assets_sha256) && hash(value.project_sha256)
    && value.source?.analysis_id === a.analysis_id && value.source.analysis_fingerprint === a.fingerprint
    && value.source.asset_id === m?.source_asset_id && value.source.source_sha256 === a.provenance?.source_asset_checksum
    && value.source.transcript_id === (m?.transcript_revision?.transcript_id ?? null)
    && value.source.transcript_version === (m?.transcript_revision?.version ?? null)
    && typeof value.can_prepare === 'boolean' && typeof value.licensed_stock_enabled === 'boolean'
    && value.ai_planning_enabled === false && value.max_ai_cost_vnd === '0' && value.preparation_provider_calls === 0
    && value.publishing_enabled === false && value.owner_approval_inferred === false,
  'Bản đọc B-roll thiếu hoặc khác nguồn, transcript, phiên bản đang xem.');
  if (value.licensed_stock_enabled) demand(value.providers?.stock?.status === 'healthy'
    && value.providers.stock.paid === false && object(value.stock_binding) && value.stock_binding.paid === false
    && hash(value.stock_binding.configuration_sha256), 'Stock chưa có cấu hình hợp lệ, miễn phí và được phép.');
  return value;
}

export function initializeBrollPlanReview({api, getState, getSessionToken = sessionToken,
  storage = globalThis.sessionStorage, cryptoImpl = globalThis.crypto,
  newRequestKey = () => 'bpr_' + cryptoImpl.randomUUID(), onPrepared = async () => {},
  onRecoveryRead = async () => true, onRecovered = async () => true, onStatus = () => {}, clock = () => Date.now()}) {
  let context = null, viewCapture = null, busy = false, disposed = false, pending = null, mayResend = false;
  let recoveryView = null;
  let pendingRecord = null, witnessCapability = null, witnessCapture = null;
  const retained = new Map();
  const digest = async value => [...new Uint8Array(await cryptoImpl.subtle.digest('SHA-256',
    new TextEncoder().encode(typeof value === 'string' ? value : stable(value))))].map(v => v.toString(16).padStart(2, '0')).join('');
  const bucket = () => 'vf-broll-plan-pending-v1:' + stable([getState().workspaceId, getState().projectId, getState().principal?.subject]);
  const path = () => `/api/v1/projects/${getState().projectId}/broll-plan-review`;
  const token = () => {const v = getSessionToken(); demand(typeof v === 'string' && v.length >= 8 && v.length <= 2048,
    'Cần thông tin xác thực của phiên.'); return v;};
  const capture = (write = false, witnessed = false) => {validateState(getState(), write, clock());
    return {boundary: boundary(getState()), token: token(), bucket: bucket(), write,
      witnessed, selection: witnessSelection(getState())};};
  const unchanged = c => {
    validateState(getState(), c.write, clock());
    demand(!disposed && boundary(getState()) === c.boundary && token() === c.token && bucket() === c.bucket
      && (!c.witnessed || witnessSelection(getState()) === c.selection),
      'Ngữ cảnh hoặc phiên đã đổi; đọc lại trước khi thao tác.');
  };
  async function publicSession(c, write = false) {
    const p = await api('/api/v1/auth/session', {cache: 'no-store'}); unchanged(c);
    demand(same(session(p), session(getState().principal)), 'Quyền hoặc phiên truy cập đã thay đổi.');
    validateState(getState(), write, clock());
  }
  function load(c) {
    const key = c.bucket, raw = storage?.getItem(key); unchanged(c);
    if (recoveryView && (recoveryView.raw !== raw || recoveryView.capture.boundary !== c.boundary || recoveryView.capture.token !== c.token)) recoveryView = null;
    demand(!retained.has(key) || retained.get(key) === raw, 'Yêu cầu B-roll đang giữ đã bị thay đổi hoặc xóa.');
    if (raw) {demand(typeof raw === 'string' && new TextEncoder().encode(raw).length <= 5 * 1024 * 1024,
      'Bản ghi đang giữ quá lớn hoặc sai kiểu; cần kiểm tra riêng.'); const parsed = JSON.parse(raw);
      const decoded = parsed?.schema_version === 'broll-plan-pending.v2' ? decodeWitnessPending(raw, clock()) : null;
      const p = decoded ? decoded.intent : parsed;
      demand(exact(p, ['schema_version', 'body', 'context', 'boundary', 'session_sha256', 'credential_sha256'])
        && p.schema_version === 'broll-plan-pending.v1' && hash(p.session_sha256) && hash(p.credential_sha256)
        && /^[A-Za-z0-9_-]{8,128}$/.test(p.body?.request_key), 'Yêu cầu B-roll đang giữ không hợp lệ; cần kiểm tra trước.');
      pending = p; pendingRecord = decoded?.record ?? null; retained.set(key, raw);
    } else {pending = null; pendingRecord = null;}
  }
  function storedRaw(p) {
    if (!pendingRecord) return stable(p);
    demand(pendingRecord.intent_json === stable(p), 'Nội dung gốc trong bằng chứng đã đổi.');
    return stable(pendingRecord);
  }
  async function buildIntent(c, body) {
    const sessionHash = await digest(session(getState().principal)); unchanged(c);
    const credentialHash = await digest(c.token); unchanged(c);
    return {schema_version: 'broll-plan-pending.v1', body, context: copy(context), boundary: c.boundary,
      session_sha256: sessionHash, credential_sha256: credentialHash};
  }
  function emptySlot(c) {
    const raw = storage?.getItem(c.bucket); unchanged(c);
    demand(raw === null || raw === undefined, 'Một lần tạo B-roll khác đang chờ trong phiên này.');
    return raw;
  }
  async function hold(c, body, proof = null, candidate = null) {
    const previous = storage?.getItem(c.bucket); unchanged(c);
    demand(previous === null || previous === undefined, 'Một lần tạo B-roll khác đang chờ trong phiên này.');
    const value = candidate ?? await buildIntent(c, body); unchanged(c);
    let record = null;
    if (proof) {
      validateIssuedWitness(proof, value, clock());
      const intent_json = stable(value), intent_sha256 = await digest(intent_json); unchanged(c); emptySlot(c);
      record = {schema_version: 'broll-plan-pending.v2', intent_json, intent_sha256,
        witness: copy(proof.witness), witness_sha256: proof.witness_sha256};
    }
    unchanged(c); const observed = storage.getItem(c.bucket); unchanged(c);
    demand(observed === previous, 'Một yêu cầu B-roll khác đã vào ô chờ; không ghi đè.');
    const raw = stable(record ?? value);
    storage.setItem(c.bucket, raw); unchanged(c);
    const stored = storage.getItem(c.bucket); unchanged(c);
    demand(stored === raw, 'Chưa giữ được yêu cầu an toàn trước khi gửi.');
    pending = value; pendingRecord = record; retained.set(c.bucket, raw);
    recoveryView = null;
  }
  async function checkPending(c) {
    load(c); c.witnessed = Boolean(pendingRecord); unchanged(c); const p = pending, raw = retained.get(c.bucket);
    demand(p && p.boundary === c.boundary, 'Lần tạo đang giữ thuộc phiên hoặc bản dựng khác.');
    const sessionHash = await digest(session(getState().principal)); heldGuard(c, p, raw);
    const credentialHash = await digest(c.token); heldGuard(c, p, raw);
    demand(p.session_sha256 === sessionHash && p.credential_sha256 === credentialHash,
      'Lần tạo đang giữ thuộc phiên hoặc bản dựng khác.');
    unchanged(c); brollPlanSettings(pending.body.settings);
    demand(pending.body.acknowledged === true && pending.body.context_sha256 === pending.context.context_sha256,
      'Yêu cầu đang giữ đã thay đổi.');
    validateBrollPlanContext(pending.context, getState(), clock());
    if (pendingRecord) {
      const record = await proofHashes(c, p, raw, true);
      heldGuard(c, p, raw);
      const verified = await api(path() + '/witness/verify', {method: 'POST',
        body: JSON.stringify({request: copy(p.body), witness: copy(record.witness)})});
      heldGuard(c, p, raw); validateVerifiedWitness(verified, record, p.context);
    }
  }
  function heldGuard(c, p, expectedRaw) {
    unchanged(c);
    demand(pending === p && retained.get(c.bucket) === expectedRaw, 'Quyền giữ yêu cầu B-roll đã đổi.');
    const raw = storage.getItem(c.bucket); unchanged(c);
    demand(typeof expectedRaw === 'string' && expectedRaw === storedRaw(p) && raw === expectedRaw,
      'Yêu cầu đang giữ đã bị thay thế; không nhận hoặc xóa nó.');
    return true;
  }
  async function proofHashes(c, p, raw, fresh = false) {
    const record = pendingRecord; demand(record, 'Chưa có bằng chứng ký cho yêu cầu đang giữ.');
    validateWitnessEnvelope(record.witness, p, clock(), fresh);
    const intentHash = await digest(record.intent_json); heldGuard(c, p, raw);
    demand(intentHash === record.intent_sha256, 'Hash ý định gốc đã đổi.');
    const proofHash = await digest(record.witness); heldGuard(c, p, raw);
    demand(proofHash === record.witness_sha256, 'Hash bằng chứng ký đã đổi.');
    return record;
  }
  async function guardedCallback(c, p, raw, callback, ...args) {
    let active = true;
    const guard = () => {demand(active, 'Quyền đối chiếu đã kết thúc.'); return heldGuard(c, p, raw);};
    try {guard(); const result = await callback(...args, guard); guard(); return result;}
    finally {active = false;}
  }
  async function accept(value, c) {
    unchanged(c); const p = pending, r = value?.receipt;
    const expectedRaw = retained.get(c.bucket);
    function retainedRequest() {
      const raw = storage.getItem(c.bucket); unchanged(c);
      demand(typeof expectedRaw === 'string' && expectedRaw === storedRaw(p) && raw === expectedRaw,
        'Yêu cầu đang giữ đã đổi trong lúc đối chiếu.');
    }
    retainedRequest();
    demand(object(value) && value.schema_version === 'broll-plan-review-result.v1' && ['prepared', 'unknown', 'rejected'].includes(value.state)
      && value.preparation_provider_calls === 0 && value.publishing_enabled === false && value.owner_approval_inferred === false
      && r?.schema_version === 'broll-plan-review-receipt.v1' && hash(r.request_sha256)
      && r.request_key === p.body.request_key && r.context_sha256 === p.body.context_sha256
      && r.authority_sha256 === p.context.authority_sha256 && r.actor_ref === getState().principal.subject
      && r.workspace_id === getState().workspaceId && r.project_id === getState().projectId
      && same(r.settings, p.body.settings) && same(r.source, p.context.source)
      && r.learning_snapshot_id === p.body.learning_snapshot_id
      && r.timeline_id === p.context.timeline_id && r.timeline_version === p.context.timeline_version
      && r.timeline_version_id === p.context.timeline_version_id, 'Biên nhận B-roll không khớp yêu cầu đã giữ.');
    if (value.state === 'unknown') {mayResend = false; demand(value.plan === null, 'Kết quả chưa rõ không được có bản đề xuất.');
      onStatus('Chưa rõ kết quả; đối chiếu đúng lần tạo, không tạo yêu cầu mới.'); return value;}
    if (value.state === 'prepared') {
      const plan = value.plan, config = plan?.configuration;
      const ready = plan?.status === 'draft' && Array.isArray(plan.items) && plan.items.length > 0
        || plan?.status === 'stock_waiting' && plan.stock_planning?.status === 'waiting'
          && Number.isSafeInteger(plan.stock_planning.total_searches) && plan.stock_planning.total_searches > 0;
      demand(plan?.workspace_id === r.workspace_id && plan.project_id === r.project_id && /^mpl_[A-Za-z0-9_-]{4,60}$/.test(plan.media_plan_id)
        && ready
        && plan.analysis_id === r.source.analysis_id && config?.purpose === 'supporting_broll'
        && config.transcript_id === r.source.transcript_id && config.max_ai_cost_vnd === '0'
        && config.learning_snapshot_id === r.learning_snapshot_id
        && same(Object.fromEntries(Object.keys(p.body.settings).map(k => [k, config[k]])), p.body.settings)
        && plan.provenance?.source_asset_sha256 === r.source.source_sha256 && plan.provenance.transcript_id === r.source.transcript_id
        && plan.source_media_mutated === false && plan.publish_requested === false && plan.paid_external_call === false,
      'Bản đề xuất trả về sai nguồn hoặc quyền thực thi.');
      retainedRequest(); await guardedCallback(c, p, expectedRaw, onPrepared, copy(plan), copy(r)); unchanged(c);
    } else demand(value.plan === null && value.error_code === 'BROLL_REVIEW_CONTEXT_CHANGED', 'Lý do dừng chưa xác định.');
    retainedRequest(); storage.removeItem(c.bucket); unchanged(c);
    retained.delete(c.bucket); pending = null; pendingRecord = null; mayResend = false; context = null; viewCapture = null; recoveryView = null;
    witnessCapability = null; witnessCapture = null;
    onStatus(value.state === 'prepared' ? 'Đã lưu đề xuất; lịch stock chờ xác nhận tìm kiếm riêng.' : 'Nguồn đã đổi. Đọc lại và xem xét lựa chọn mới.');
    return value;
  }
  async function run(fn) {demand(!disposed && !busy, 'Chờ thao tác B-roll đang chạy.'); busy = true;
    try {return await fn();} finally {busy = false;}}
  async function reload() {return run(async () => {
    const c = capture(); load(c); demand(!pending, 'Đối chiếu lần tạo đang giữ trước khi lập lựa chọn mới.');
    await publicSession(c); unchanged(c); const value = await api(path(), {cache: 'no-store'}); unchanged(c);
    validateBrollPlanContext(value, getState(), clock()); const {context_sha256, context_json, ...raw} = value;
    demand(typeof context_json === 'string' && context_json.length <= 65536 && same(JSON.parse(context_json), raw)
      && await digest(context_json) === context_sha256, 'Hash bản đọc B-roll không hợp lệ.'); unchanged(c);
    context = copy(value); viewCapture = c; witnessCapability = null; witnessCapture = null;
    onStatus('Đã đọc nguồn. Chọn nguồn bổ trợ, thứ tự và xác nhận tạo bản nháp.'); return copy(value);
  });}
  async function readWitnessCapability() {return run(async () => {
    const c = capture(true, true); load(c);
    demand(!pending && context && viewCapture?.boundary === c.boundary && viewCapture.token === c.token,
      'Đọc nguồn trước khi chọn bằng chứng ký cho lần chuẩn bị mới.');
    await publicSession(c, true); unchanged(c); emptySlot(c);
    const value = await api(path() + '/witness/status', {cache: 'no-store'}); unchanged(c); emptySlot(c);
    validateWitnessCapability(value, getState());
    witnessCapability = copy(value); witnessCapture = c; return copy(value);
  });}
  async function prepareInternal(settings, acknowledged, witnessed = false) {return run(async () => {
    const c = capture(true, witnessed); load(c); demand(!pending && context && acknowledged === true, 'Đọc và xác nhận rõ lựa chọn trước khi tạo.');
    demand(viewCapture && viewCapture.boundary === c.boundary && viewCapture.token === c.token,
      'Nguồn, quyền hoặc phiên đã đổi từ lúc đọc đề xuất.');
    validateBrollPlanContext(context, getState(), clock()); settings = brollPlanSettings(settings);
    demand(!settings.allow_stock || context.licensed_stock_enabled, 'Stock chưa được cấu hình hoặc được phép.');
    if (witnessed) demand(witnessCapability?.status === 'READY' && witnessCapability.issuance_available === true
      && witnessCapture?.boundary === c.boundary && witnessCapture.token === c.token && witnessCapture.selection === c.selection,
    'Đọc xác nhận máy chủ sẵn sàng rồi chọn rõ bằng chứng ký; không tự chuyển sang yêu cầu thường.');
    await publicSession(c, true); unchanged(c); const key = newRequestKey(); demand(typeof key === 'string' && /^[A-Za-z0-9_-]{8,128}$/.test(key), 'Mã yêu cầu không hợp lệ.');
    const learning = getState().learning_snapshot_id ?? null;
    demand(learning === null || typeof learning === 'string' && /^lsn_[A-Za-z0-9_-]{4,60}$/.test(learning), 'Gợi ý học chưa có snapshot hợp lệ.');
    const body = {request_key: key, context_sha256: context.context_sha256, acknowledged: true, settings, learning_snapshot_id: learning};
    if (witnessed) {
      const value = await buildIntent(c, body); unchanged(c); emptySlot(c);
      const issued = copy(await api(path() + '/witness', {method: 'POST', body: JSON.stringify(body)})); unchanged(c); emptySlot(c);
      const claims = validateIssuedWitness(issued, value, clock());
      const envelopeHash = await digest(issued.witness); unchanged(c); emptySlot(c);
      const bearerHash = await digest('Bearer ' + c.token); unchanged(c); emptySlot(c);
      demand(envelopeHash === issued.witness_sha256 && claims.original_authority.credential_sha256 === bearerHash,
        'Bằng chứng ký không khớp thông tin xác thực và nội dung đã chọn.');
      const verified = await api(path() + '/witness/verify', {method: 'POST',
        body: JSON.stringify({request: copy(body), witness: copy(issued.witness)})}); unchanged(c); emptySlot(c);
      validateVerifiedWitness(verified, {intent_json: stable(value), witness_sha256: issued.witness_sha256}, context);
      await hold(c, body, issued, value);
    } else await hold(c, body);
    heldGuard(c, pending, retained.get(c.bucket));
    if (pendingRecord) validateWitnessEnvelope(pendingRecord.witness, pending, clock(), true);
    unchanged(c); const result = await api(path(), {method: 'POST', body: JSON.stringify(pending.body)}); return accept(result, c);
  });}
  async function reconcile() {return run(async () => {
    const c = capture(); await publicSession(c); unchanged(c); await checkPending(c);
    heldGuard(c, pending, retained.get(c.bucket));
    mayResend = false;
    try {return await accept(await api(path() + '/requests/' + pending.body.request_key, {cache: 'no-store'}), c);}
    catch (e) {unchanged(c); if (e.status === 404) {mayResend = true; onStatus('Chưa có biên nhận. Có thể gửi lại đúng yêu cầu sau khi xác nhận.'); return null;} throw e;}
  });}
  async function resend(acknowledged) {return run(async () => {
    const c = capture(true); await publicSession(c, true); unchanged(c); await checkPending(c);
    heldGuard(c, pending, retained.get(c.bucket));
    demand(mayResend && acknowledged === true, 'Đối chiếu chưa có biên nhận và xác nhận trước khi gửi lại.');
    const latest = await api(path(), {cache: 'no-store'}); unchanged(c);
    demand(same(latest, pending.context), 'Nguồn hoặc cấu hình đã đổi; không gửi lại yêu cầu cũ.');
    const raw = storage.getItem(c.bucket); unchanged(c);
    demand(typeof retained.get(c.bucket) === 'string' && raw === retained.get(c.bucket) && raw === storedRaw(pending),
      'Yêu cầu đang giữ đã đổi trước khi gửi lại.');
    if (pendingRecord) validateWitnessEnvelope(pendingRecord.witness, pending, clock(), true);
    mayResend = false; return accept(await api(path(), {method: 'POST', body: JSON.stringify(pending.body)}), c);
  });}
  async function recoveryHeld(c) {
    load(c); c.witnessed = Boolean(pendingRecord); unchanged(c); const p = pending, raw = retained.get(c.bucket);
    demand(p && typeof raw === 'string' && hash(p.credential_sha256), 'Chưa có đúng yêu cầu cũ để xác minh trên server.');
    const original = JSON.parse(p.boundary), current = JSON.parse(boundary(getState()));
    demand(Array.isArray(original) && original.length === 7 && exact(original[2], sessionFields)
      && ['subject', 'display_name', 'platform_role', 'workspace_roles', 'human_write_enabled'].every(k => same(original[2][k], current[2][k]))
      && original[2].human_write_enabled === true && same([...original.slice(0, 2), current[2], ...original.slice(3)], current),
    'Chỉ phiên mới của cùng người, quyền và nguồn được đối chiếu yêu cầu cũ.');
    const sessionHash = await digest(original[2]); heldGuard(c, p, raw);
    demand(sessionHash === p.session_sha256 && p.body.acknowledged === true
      && p.body.context_sha256 === p.context.context_sha256 && p.body.learning_snapshot_id === original[6], 'Metadata yêu cầu cũ chưa khớp.');
    brollPlanSettings(p.body.settings); validateBrollPlanContext(p.context, getState(), clock());
    const record = pendingRecord ? await proofHashes(c, p, raw) : null;
    heldGuard(c, p, raw);
    const intentRaw = record ? record.intent_json : raw;
    const intentHash = await digest(intentRaw); heldGuard(c, p, raw);
    return {p, raw, intentRaw, intentHash, record};
  }
  async function freshRecoveryContext(c, p, raw) {
    const value = copy(await api(path(), {cache: 'no-store'})); heldGuard(c, p, raw);
    validateBrollPlanContext(value, getState(), clock()); const {context_json, context_sha256, ...fields} = value;
    demand(typeof context_json === 'string' && context_json.length <= 65536 && same(JSON.parse(context_json), fields)
      && await digest(context_json) === context_sha256, 'Bản đọc nguồn mới chưa có hash đúng.'); heldGuard(c, p, raw);
    const source = v => Object.fromEntries(Object.entries(v).filter(([k]) => !['context_json', 'context_sha256', 'authority_sha256', 'can_prepare'].includes(k)));
    demand(value.can_prepare === true && same(source(value), source(p.context)), 'Nguồn hoặc cấu hình đã đổi; không dừng yêu cầu bằng metadata khác.');
    return value;
  }
  function recoveryResult(value, p, intentHash, fresh) {
    demand(object(value) && value.schema_version === 'broll-request-recovery.v1' && ['observed', 'settled'].includes(value.state)
      && value.workspace_id === getState().workspaceId && value.project_id === getState().projectId && value.actor_ref === getState().principal.subject
      && value.intent_sha256 === intentHash && value.original_request_key === p.body.request_key
      && value.original_authority_sha256 === p.context.authority_sha256 && value.original_context_sha256 === p.context.context_sha256
      && value.current_authority_sha256 === fresh.authority_sha256 && value.current_context_sha256 === fresh.context_sha256
      && same(value.source, p.context.source) && hash(value.observation_sha256) && value.provider_calls === 0
      && value.source_media_mutated === false && value.publish_requested === false && value.owner_approval_inferred === false
      && value.preserved_plan_is_original_snapshot === true && value.absent_credential_renewal_supported === false
      && value.requires_server_identity_or_current_original_authority === true, 'Biên nhận khôi phục không khớp phiên, nguồn hoặc ý định cũ.');
    const original = value.original_result;
    if (original !== null) {
      const r = original?.receipt;
      demand(original.schema_version === 'broll-plan-review-result.v1' && ['unknown', 'prepared', 'rejected'].includes(original.state)
        && original.preparation_provider_calls === 0 && original.publishing_enabled === false && original.owner_approval_inferred === false
        && r?.schema_version === 'broll-plan-review-receipt.v1' && r.actor_ref === value.actor_ref && r.workspace_id === value.workspace_id
        && r.project_id === value.project_id && r.request_key === p.body.request_key && r.context_sha256 === p.body.context_sha256
        && r.authority_sha256 === p.context.authority_sha256 && same(r.settings, p.body.settings) && same(r.source, p.context.source)
        && r.learning_snapshot_id === p.body.learning_snapshot_id && r.timeline_id === p.context.timeline_id
        && r.timeline_version === p.context.timeline_version && r.timeline_version_id === p.context.timeline_version_id
        && same(value.preserved_plan, original.plan), 'Kết quả gốc đã đổi; không dùng nó để xóa yêu cầu đang giữ.');
    } else demand(value.preserved_plan === null, 'Không suy diễn Media Plan cho yêu cầu chưa có bản ghi.');
    if (value.state === 'settled') {
      const r = value.settlement;
      demand(r?.schema_version === 'broll-request-settlement.v1' && /^sop_[a-f0-9]{32}$/.test(r.settlement_id)
        && r.actor_ref === value.actor_ref && r.intent_sha256 === intentHash && r.original_request_key === p.body.request_key
        && r.original_authority_sha256 === p.context.authority_sha256 && r.original_context_sha256 === p.context.context_sha256
        && hash(r.settled_by_authority_sha256) && hash(r.observed_original_sha256) && r.abandoned === true && r.provider_calls === 0,
      'Server chưa xác nhận tombstone cho đúng yêu cầu cũ.');
    } else demand(value.settlement === null, 'Bản đọc chưa được ghép với tombstone khác.');
    return value;
  }
  function recoveryBody(intentRaw, intentHash, record, extra = {}) {
    return {intent_json: intentRaw, intent_sha256: intentHash,
      ...(record ? {witness: copy(record.witness)} : {}), ...extra};
  }
  function recoveryPrefix(record) {return path() + (record ? '/witnessed-recovery' : '/recovery');}
  function recoveryValue(wire, record) {return record ? validateWitnessRecovery(wire, record) : wire;}
  async function recoveryCallback(c, p, raw, record, callback, value, wire) {
    if (!record) return guardedCallback(c, p, raw, callback, copy(value));
    const proof = {schema_version: 'broll-witness-recovery-proof.v1', stored_raw: raw,
      intent_json: record.intent_json, intent_sha256: record.intent_sha256,
      witness: copy(record.witness), witness_sha256: record.witness_sha256, response: copy(wire)};
    // Existing callback positions stay intact. A future Root adapter must
    // explicitly authorize the v2 raw/proof/routes before mounting this path.
    return guardedCallback(c, p, raw, (v, guard) => callback(v, guard, copy(proof)), copy(value));
  }
  async function inspectRecovery() {return run(async () => {
    const c = capture(true); await publicSession(c, true); unchanged(c); const {p, raw, intentRaw, intentHash, record} = await recoveryHeld(c);
    heldGuard(c, p, raw);
    const fresh = await freshRecoveryContext(c, p, raw);
    heldGuard(c, p, raw);
    const wire = copy(await api(recoveryPrefix(record) + '/inspect', {method: 'POST', body: JSON.stringify(recoveryBody(intentRaw, intentHash, record))}));
    const value = recoveryValue(wire, record);
    heldGuard(c, p, raw); recoveryResult(value, p, intentHash, fresh);
    demand(await recoveryCallback(c, p, raw, record, onRecoveryRead, value, wire) === true, 'Studio chưa nhận đúng bản đối chiếu khôi phục.');
    heldGuard(c, p, raw); recoveryView = {raw, capture: c, data: copy(value), wire: copy(wire)}; mayResend = false;
    onStatus('Đã đối chiếu với server. Dừng yêu cầu cũ cần xác nhận riêng; Media Plan đã có vẫn được giữ.'); return copy(value);
  });}
  function removeRecovered(c, p, raw) {
    heldGuard(c, p, raw);
    demand(typeof storage.compareAndRemoveItem === 'function', 'Nơi giữ yêu cầu chưa hỗ trợ xóa đúng bản ghi bằng CAS.');
    demand(storage.compareAndRemoveItem(c.bucket, raw) === true, 'Yêu cầu khác đã thay thế bản ghi; giữ nguyên.'); unchanged(c);
  }
  async function abandonRecovery(acknowledged) {return run(async () => {
    const c = capture(true); await publicSession(c, true); unchanged(c); const {p, raw, intentRaw, intentHash, record} = await recoveryHeld(c);
    heldGuard(c, p, raw);
    demand(acknowledged === true && recoveryView && recoveryView.raw === raw
      && recoveryView.capture.boundary === c.boundary && recoveryView.capture.token === c.token,
    'Đối chiếu server rồi xác nhận rõ dừng đúng yêu cầu cũ trước.');
    const fresh = await freshRecoveryContext(c, p, raw);
    heldGuard(c, p, raw);
    demand(fresh.context_sha256 === recoveryView.data.current_context_sha256
      && fresh.authority_sha256 === recoveryView.data.current_authority_sha256, 'Nguồn hoặc phiên đã đổi sau khi đối chiếu.');
    const wire = copy(await api(recoveryPrefix(record) + '/abandon', {method: 'POST', body: JSON.stringify(recoveryBody(intentRaw,
      intentHash, record, {observation_sha256: recoveryView.data.observation_sha256, acknowledged: true}))}));
    const value = recoveryValue(wire, record);
    heldGuard(c, p, raw); recoveryResult(value, p, intentHash, fresh); demand(value.state === 'settled', 'Yêu cầu chưa được server kết thúc.');
    const proofWire = copy(await api(recoveryPrefix(record) + '/settlements/' + value.settlement.settlement_id, {cache: 'no-store'}));
    const proof = recoveryValue(proofWire, record);
    heldGuard(c, p, raw); recoveryResult(proof, p, intentHash, fresh); demand(same(wire, proofWire), 'Bản đọc tombstone chưa khớp lần xác nhận.');
    demand(await recoveryCallback(c, p, raw, record, onRecovered, proof, proofWire) === true, 'Studio chưa xác minh đúng settlement.');
    heldGuard(c, p, raw); removeRecovered(c, p, raw);
    retained.delete(c.bucket); pending = null; pendingRecord = null; mayResend = false; context = null; viewCapture = null; recoveryView = null;
    witnessCapability = null; witnessCapture = null;
    onStatus('Đã ghi nhận dừng yêu cầu cũ. Media Plan và lịch sử giữ nguyên; đọc lại trước khi chuẩn bị lần mới.'); return copy(proof);
  });}
  return {reload, prepare: (settings, acknowledged) => prepareInternal(settings, acknowledged, false),
    prepareWithWitness: (settings, acknowledged) => prepareInternal(settings, acknowledged, true),
    readWitnessCapability, reconcile, resend, defaults: defaultBrollPlanSettings,
    inspectRecovery, abandonRecovery,
    state: () => ({busy, context: copy(context), pending: copy(pending), mayResend, recovery: copy(recoveryView?.data ?? null),
      ...(pendingRecord || witnessCapability ? {witness: {capability: copy(witnessCapability),
        pending_record: copy(pendingRecord), retained_raw: pendingRecord ? retained.get(bucket()) ?? null : null}} : {})}),
    dispose: () => {disposed = true; context = null; recoveryView = null; witnessCapability = null; witnessCapture = null;}};
}
