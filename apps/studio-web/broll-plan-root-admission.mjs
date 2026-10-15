// One explicit Root operation. No DOM, storage writes, automatic requests or providers.
import {brollPlanSettings, validateBrollPlanContext} from './broll-plan-review.mjs';
import {witnessStable as stable, witnessJson, decodeWitnessPending, validateWitnessCapability,
  validateIssuedWitness, validateVerifiedWitness, validateWitnessRecovery} from './broll-request-witness.mjs';

const copy = structuredClone, object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
const same = (a, b) => stable(a) === stable(b);
const exact = (v, keys) => object(v) && same(Object.keys(v).sort(), [...keys].sort());
const hash = v => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const demand = (v, text = 'Lệnh B-roll không khớp thao tác, nguồn hoặc bản ghi đang giữ.') => {if (!v) throw Error(text);};
const pubKeys = ['subject', 'display_name', 'platform_role', 'workspace_roles', 'expires_at', 'human_write_enabled'];
const publicSession = p => Object.fromEntries(pubKeys.map(k => [k, p?.[k]]));
const kinds = new Set(['read', 'witness-capability', 'prepare', 'prepare-witnessed', 'reconcile', 'resend', 'recover-inspect', 'abandon']);
const recovering = kind => ['recover-inspect', 'abandon'].includes(kind);
const snapshot = s => stable([s.workspaceId, s.workspaceSlug ?? null, s.projectId, publicSession(s.principal), s.timeline,
  s.analysis, s.assets, s.learning_snapshot_id ?? null, s.videoReviewSelection ?? null, s.analyses ?? null,
  s.versions ?? null, s.preview ?? null, s.productionPackage ?? null]);
const innerBoundary = s => stable([s.workspaceId, s.projectId, publicSession(s.principal), s.timeline,
  s.analysis, s.assets, s.learning_snapshot_id ?? null]);
const requestKeys = ['request_key', 'context_sha256', 'acknowledged', 'settings', 'learning_snapshot_id'];
const recoveryKeys = ['schema_version', 'state', 'workspace_id', 'project_id', 'actor_ref', 'intent_sha256',
  'original_request_key', 'original_authority_sha256', 'original_context_sha256', 'current_authority_sha256',
  'current_context_sha256', 'source', 'observation_sha256', 'original_result', 'preserved_plan',
  'preserved_plan_is_original_snapshot', 'absent_credential_renewal_supported', 'requires_server_identity_or_current_original_authority',
  'settlement', 'provider_calls', 'source_media_mutated', 'publish_requested', 'owner_approval_inferred'];
const operationId = v => typeof v === 'string' && /^sop_[a-f0-9]{32}$/.test(v);

export function createBrollPlanRootAdmission({kind, write, getState, getSessionToken, getChoices, getPendingState,
  getRaw, assertCurrent, cryptoImpl = globalThis.crypto, clock = () => Date.now()}) {
  // Constructor/state inspection must not read even a native storage getter.
  demand(typeof kind === 'string' && kinds.has(kind) && typeof write === 'boolean');
  let bound = null, busy = false, disposed = false, failed = false;
  let firstBody = null, candidate = null, issued = null, verified = false, issuerSent = false, baseSent = false;
  let acceptedSettlement = null, lastContext = null, choiceSnapshot = null, resendAuthorized = null, heldVerifiedRaw = null;
  let started = false;
  function check(requireWrite = false) {
    demand(!disposed && !failed && assertCurrent() === true);
    const s = getState(), token = getSessionToken(), p = s.principal;
    const ranks = {viewer: 10, editor: 20, reviewer: 30, owner: 40};
    const rank = Math.max(...[p?.platform_role, p?.workspace_roles?.['*'], p?.workspace_roles?.[s.workspaceId],
      s.workspaceSlug ? p?.workspace_roles?.['slug:' + s.workspaceSlug] : null].map(v => ranks[v] ?? 0));
    demand(typeof s.workspaceId === 'string' && /^wsp_[A-Za-z0-9_-]{4,60}$/.test(s.workspaceId)
      && typeof s.projectId === 'string' && /^prj_[A-Za-z0-9_-]{4,60}$/.test(s.projectId)
      && typeof p?.subject === 'string' && p.subject && typeof p.expires_at === 'string' && Date.parse(p.expires_at) > clock()
      && typeof p.display_name === 'string' && object(p.workspace_roles)
      && Object.values(p.workspace_roles).every(r => typeof r === 'string' && Object.hasOwn(ranks, r))
      && (p.platform_role === null || typeof p.platform_role === 'string' && Object.hasOwn(ranks, p.platform_role))
      && typeof p.human_write_enabled === 'boolean'
      && rank >= ranks.viewer && !s.busy && !s.dirty && typeof token === 'string' && token.length >= 8 && token.length <= 2048);
    if (requireWrite) demand(p.human_write_enabled === true && rank >= ranks.editor);
    const current = {snapshot: snapshot(s), token, bucket: 'vf-broll-plan-pending-v1:' + stable([s.workspaceId, s.projectId, p.subject]),
      base: `/api/v1/projects/${s.projectId}/broll-plan-review`};
    if (!bound) bound = current;
    if (kind === 'resend' && resendAuthorized === null) resendAuthorized = getPendingState()?.mayResend === true;
    demand(current.snapshot === bound.snapshot && current.token === bound.token && current.bucket === bound.bucket
      && (choiceSnapshot === null || stable(getChoices()) === choiceSnapshot)
      && assertCurrent() === true && snapshot(getState()) === bound.snapshot && getSessionToken() === bound.token);
    return s;
  }
  function nativeRaw(expected) {
    check(); const raw = getRaw(bound.bucket); check();
    demand(raw === null || raw === undefined || typeof raw === 'string' && new TextEncoder().encode(raw).length <= 5 * 1024 * 1024);
    if (arguments.length) demand(raw === expected);
    return raw;
  }
  function empty() {const raw = nativeRaw(); demand(raw === null || raw === undefined); return raw;}
  async function digest(value, guard = check) {
    guard(); const bytes = await cryptoImpl.subtle.digest('SHA-256', new TextEncoder().encode(typeof value === 'string' ? value : stable(value)));
    guard(); return [...new Uint8Array(bytes)].map(x => x.toString(16).padStart(2, '0')).join('');
  }
  function choices() {check(); const v = copy(getChoices()); check();
    demand(exact(v, ['readContext', 'settings', 'learningSnapshotId', 'prepareAcknowledged', 'abandonAcknowledged', 'witnessOptIn'])
      && typeof v.prepareAcknowledged === 'boolean' && typeof v.abandonAcknowledged === 'boolean' && typeof v.witnessOptIn === 'boolean');
    if (choiceSnapshot === null) choiceSnapshot = stable(v); else demand(stable(v) === choiceSnapshot);
    check(); return v;
  }
  function typedBody(body) {
    demand(exact(body, requestKeys) && typeof body.request_key === 'string' && /^[A-Za-z0-9_-]{8,128}$/.test(body.request_key)
      && hash(body.context_sha256) && body.acknowledged === true && (body.learning_snapshot_id === null
      || typeof body.learning_snapshot_id === 'string' && /^lsn_[A-Za-z0-9_-]{4,60}$/.test(body.learning_snapshot_id)));
    brollPlanSettings(body.settings); return body;
  }
  async function descriptor() {
    const s = check(), state = copy(getPendingState()); check(); const raw = nativeRaw(), p = state?.pending;
    demand(typeof raw === 'string' && object(p));
    const parsed = witnessJson(raw, 5 * 1024 * 1024), v2 = parsed?.schema_version === 'broll-plan-pending.v2';
    const record = v2 ? decodeWitnessPending(raw, clock()).record : null;
    demand(exact(p, ['schema_version', 'body', 'context', 'boundary', 'session_sha256', 'credential_sha256'])
      && p.schema_version === 'broll-plan-pending.v1' && hash(p.session_sha256) && hash(p.credential_sha256));
    typedBody(p.body); validateBrollPlanContext(p.context, s, clock());
    const literal = v2 ? record.intent_json : raw;
    demand(literal === stable(p) && (!v2 ? !state.witness?.pending_record : same(state.witness?.pending_record, record)
      && state.witness.retained_raw === raw));
    const old = witnessJson(p.boundary, 5 * 1024 * 1024), current = witnessJson(innerBoundary(s), 5 * 1024 * 1024);
    demand(Array.isArray(old) && old.length === 7 && exact(old[2], pubKeys)
      && ['subject', 'display_name', 'platform_role', 'workspace_roles', 'human_write_enabled'].every(k => same(old[2][k], current[2][k]))
      && old[2].human_write_enabled === true && same([...old.slice(0, 2), current[2], ...old.slice(3)], current)
      && p.body.context_sha256 === p.context.context_sha256 && p.body.learning_snapshot_id === old[6]);
    const held = () => {check(); nativeRaw(raw);};
    demand(await digest(old[2], held) === p.session_sha256); held();
    if (!recovering(kind)) {demand(p.boundary === innerBoundary(s));
      demand(await digest(bound.token, held) === p.credential_sha256); held();}
    const intentHash = await digest(literal, held); held();
    if (v2) {demand(intentHash === record.intent_sha256);
      demand(await digest(record.witness, held) === record.witness_sha256); held();}
    return {version: v2 ? 2 : 1, raw, intent_json: literal, intent_sha256: intentHash, pending: p, record};
  }
  function receipt(value, d) {
    const p = d.pending, r = value?.receipt;
    demand(exact(value, ['schema_version', 'state', 'receipt', 'plan', 'replayed', 'preparation_provider_calls',
      'publishing_enabled', 'owner_approval_inferred', ...(value?.state === 'unknown' ? [] : ['error_code'])])
      && value.schema_version === 'broll-plan-review-result.v1' && ['prepared', 'unknown', 'rejected'].includes(value.state)
      && typeof value.replayed === 'boolean'
      && value.preparation_provider_calls === 0 && value.publishing_enabled === false && value.owner_approval_inferred === false
      && exact(r, ['schema_version', 'operation_id', 'workspace_id', 'project_id', 'actor_ref', 'authority_sha256', 'request_key',
        'request_sha256', 'context_sha256', 'settings', 'learning_snapshot_id', 'learning_feedback_sha256', 'source',
        'timeline_id', 'timeline_version', 'timeline_version_id'])
      && r.schema_version === 'broll-plan-review-receipt.v1' && hash(r.request_sha256) && operationId(r.operation_id)
      && r.request_key === p.body.request_key && r.context_sha256 === p.context.context_sha256
      && r.authority_sha256 === p.context.authority_sha256 && r.workspace_id === p.context.workspace_id
      && r.project_id === p.context.project_id && r.actor_ref === p.context.actor_ref
      && same(r.source, p.context.source) && same(r.settings, p.body.settings) && r.learning_snapshot_id === p.body.learning_snapshot_id
      && (r.learning_snapshot_id === null ? r.learning_feedback_sha256 === null : hash(r.learning_feedback_sha256))
      && ['timeline_id', 'timeline_version', 'timeline_version_id'].every(k => r[k] === p.context[k]));
    if (value.state !== 'prepared') {demand(value.plan === null);
      if (value.state === 'rejected') demand(value.error_code === 'BROLL_REVIEW_CONTEXT_CHANGED');
    } else {const plan = value.plan, ready = plan?.status === 'draft' && Array.isArray(plan.items) && plan.items.length > 0
      || plan?.status === 'stock_waiting' && plan.stock_planning?.status === 'waiting'
        && Number.isSafeInteger(plan.stock_planning.total_searches) && plan.stock_planning.total_searches > 0;
      demand(value.error_code === null && ready && value.plan?.workspace_id === r.workspace_id && value.plan.project_id === r.project_id
      && value.plan.source_media_mutated === false && value.plan.publish_requested === false && value.plan.paid_external_call === false);
    }
  }
  function recovery(value, d) {
    const inner = d.version === 2 ? validateWitnessRecovery(value, d.record) : value, p = d.pending;
    demand(exact(inner, recoveryKeys) && inner.schema_version === 'broll-request-recovery.v1' && ['observed', 'settled'].includes(inner.state)
      && inner.workspace_id === p.context.workspace_id && inner.project_id === p.context.project_id && inner.actor_ref === p.context.actor_ref
      && inner.intent_sha256 === d.intent_sha256 && inner.original_request_key === p.body.request_key
      && inner.original_authority_sha256 === p.context.authority_sha256 && inner.original_context_sha256 === p.context.context_sha256
      && same(inner.source, p.context.source) && hash(inner.observation_sha256) && hash(inner.current_authority_sha256)
      && hash(inner.current_context_sha256) && inner.provider_calls === 0 && inner.source_media_mutated === false
      && inner.publish_requested === false && inner.owner_approval_inferred === false && inner.preserved_plan_is_original_snapshot === true
      && inner.absent_credential_renewal_supported === false && inner.requires_server_identity_or_current_original_authority === true);
    demand(lastContext && inner.current_authority_sha256 === lastContext.authority_sha256
      && inner.current_context_sha256 === lastContext.context_sha256);
    if (inner.original_result !== null) {receipt(inner.original_result, d); demand(same(inner.preserved_plan, inner.original_result.plan));}
    else demand(inner.preserved_plan === null);
    if (inner.state === 'settled') {const r = inner.settlement;
      demand(exact(r, ['schema_version', 'settlement_id', 'actor_ref', 'settled_by_authority_sha256', 'intent_sha256', 'original_request_key',
        'original_authority_sha256', 'original_context_sha256', 'observed_original_sha256', 'abandoned', 'original_operation_id', 'created_at', 'provider_calls'])
        && r.schema_version === 'broll-request-settlement.v1' && operationId(r.settlement_id)
        && (r.original_operation_id === null || operationId(r.original_operation_id))
        && typeof r.created_at === 'string' && Number.isFinite(Date.parse(r.created_at))
        && r.actor_ref === inner.actor_ref && r.intent_sha256 === d.intent_sha256 && r.original_request_key === p.body.request_key
        && r.original_authority_sha256 === p.context.authority_sha256 && r.original_context_sha256 === p.context.context_sha256
        && hash(r.settled_by_authority_sha256) && hash(r.observed_original_sha256) && r.abandoned === true && r.provider_calls === 0);
    } else demand(inner.settlement === null);
    return inner;
  }
  async function run(path, options = {}, send) {
    demand(!busy && !disposed && !failed && typeof send === 'function'); busy = true;
    try {
      check(); demand(typeof path === 'string' && object(options));
      if (!started) {started = true; if (['prepare', 'prepare-witnessed'].includes(kind)) empty();}
      const safe = copy(options), method = safe.method ?? 'GET'; demand(['GET', 'POST'].includes(method));
      demand(!Object.keys(safe).some(k => !['method', 'body', 'cache'].includes(k)));
      demand(safe.cache === undefined || safe.cache === 'no-store');
      const base = bound.base, body = safe.body === undefined ? null : witnessJson(safe.body, 5 * 1024 * 1024);
      demand(method === 'POST' ? object(body) : body === null);
      let action, d = null, held = check;
      if (path === '/api/v1/auth/session' && method === 'GET') action = 'session';
      else if (path === base && method === 'GET') {
        if (getPendingState()?.pending) {d = await descriptor(); check(); nativeRaw(d.raw); held = () => {check(); nativeRaw(d.raw);};}
        else {empty(); held = () => {check(); empty();};}
        action = 'context';
      }
      else if (path === base + '/witness/status' && method === 'GET' && kind === 'witness-capability') {
        check(true); empty(); const c = choices(); validateBrollPlanContext(c.readContext, getState(), clock()); action = 'capability'; held = () => {check(true); empty();};
      } else if (path === base + '/witness' && method === 'POST' && kind === 'prepare-witnessed') {
        demand(write && !issuerSent && !firstBody); check(true); empty(); const c = choices(), state = check(true);
        demand(c.witnessOptIn && c.prepareAcknowledged && c.readContext?.can_prepare === true); validateBrollPlanContext(c.readContext, state, clock());
        const pending = copy(getPendingState()); check(true); validateWitnessCapability(pending.witness?.capability, state);
        demand(pending.witness.capability.status === 'READY' && pending.pending === null); typedBody(body);
        demand(body.context_sha256 === c.readContext.context_sha256 && same(body.settings, c.settings)
          && body.learning_snapshot_id === c.learningSnapshotId && c.learningSnapshotId === (state.learning_snapshot_id ?? null));
        firstBody = copy(body); held = () => {check(true); empty();};
        const sessionHash = await digest(publicSession(state.principal), held); held();
        const credentialHash = await digest(bound.token, held); held();
        candidate = {schema_version: 'broll-plan-pending.v1', body: copy(body), context: copy(c.readContext),
          boundary: innerBoundary(state), session_sha256: sessionHash, credential_sha256: credentialHash};
        issuerSent = true; action = 'issue';
      } else {
        d = await descriptor(); check(); nativeRaw(d.raw); held = () => {check(); nativeRaw(d.raw);};
        const prefix = base + (d.version === 2 ? '/witnessed-recovery' : '/recovery');
        if (method === 'GET' && path === base + '/requests/' + d.pending.body.request_key
          && ['prepare', 'prepare-witnessed', 'reconcile', 'resend'].includes(kind)) {
          if (d.version === 2 && kind === 'reconcile') demand(heldVerifiedRaw === d.raw);
          action = 'receipt';
        }
        else if (method === 'GET' && acceptedSettlement && path === prefix + '/settlements/' + acceptedSettlement.id && recovering(kind)) action = 'settlement';
        else if (method === 'POST' && path === base && ['prepare', 'prepare-witnessed', 'resend'].includes(kind)) {
          demand(write && !baseSent && same(body, d.pending.body)); check(true);
          if (kind === 'prepare') {const c = choices(); demand(d.version === 1 && !c.witnessOptIn && c.prepareAcknowledged
            && same(body.settings, c.settings) && body.context_sha256 === c.readContext?.context_sha256);}
          if (kind === 'prepare-witnessed') demand(d.version === 2 && verified && candidate && same(body, firstBody)
            && d.record.intent_json === stable(candidate) && same(d.record.witness, issued.witness));
          if (kind === 'resend') demand(resendAuthorized === true && lastContext && same(lastContext, d.pending.context)
            && (d.version === 1 || heldVerifiedRaw === d.raw));
          baseSent = true; action = 'prepare';
        } else if (method === 'POST' && path === base + '/witness/verify' && ['reconcile', 'resend'].includes(kind) && d.version === 2) {
          check(true); demand(exact(body, ['request', 'witness']) && same(body.request, d.pending.body) && same(body.witness, d.record.witness)); action = 'verify-held';
        } else if (method === 'POST' && recovering(kind) && path === prefix + (kind === 'abandon' ? '/abandon' : '/inspect')) {
          demand(write && lastContext); check(true); const extra = kind === 'abandon' ? ['observation_sha256', 'acknowledged'] : [];
          demand(exact(body, ['intent_json', 'intent_sha256', ...(d.version === 2 ? ['witness'] : []), ...extra])
            && body.intent_json === d.intent_json && body.intent_sha256 === d.intent_sha256
            && (d.version === 1 || same(body.witness, d.record.witness)));
          if (kind === 'abandon') {const current = copy(getPendingState()); held();
            demand(choices().abandonAcknowledged && body.acknowledged === true
              && body.observation_sha256 === current.recovery?.observation_sha256
              && current.recovery.intent_sha256 === d.intent_sha256
              && current.recovery.original_request_key === d.pending.body.request_key);}
          action = 'recovery';
        } else demand(false);
      }
      held(); const value = copy(await send(Object.freeze(copy(safe)))); held();
      if (action === 'session') demand(same(value, publicSession(getState().principal)));
      if (action === 'context') {validateBrollPlanContext(value, getState(), clock());
        if (d) {const source = v => Object.fromEntries(Object.entries(v).filter(([k]) => !['context_json', 'context_sha256', 'authority_sha256', 'can_prepare'].includes(k)));
          demand(same(source(value), source(d.pending.context)));}
        lastContext = copy(value);
      }
      if (action === 'capability') validateWitnessCapability(value, getState());
      if (action === 'issue') {
        const claims = validateIssuedWitness(value, candidate, clock());
        demand(await digest(value.witness, held) === value.witness_sha256); held();
        demand(await digest('Bearer ' + bound.token, held) === claims.original_authority.credential_sha256); held();
        issued = copy(value);
      }
      if (action === 'verify-held') {validateVerifiedWitness(value, d.record, d.pending.context); heldVerifiedRaw = d.raw;}
      if (action === 'prepare' || action === 'receipt') receipt(value, d);
      if (action === 'recovery' || action === 'settlement') {
        const inner = recovery(value, d);
        if (action === 'settlement') demand(same(value, acceptedSettlement.value));
        if (inner.state === 'settled') acceptedSettlement = {id: inner.settlement.settlement_id, value: copy(value)};
      }
      held(); return value;
    } catch (error) {failed = true; throw error;} finally {busy = false;}
  }
  // Pre-durable verification has no pending record. Handle it with the exact
  // body and envelope captured by the preceding successful issuer response.
  async function admitted(path, options = {}, send) {
    if (path !== bound?.base + '/witness/verify' || kind !== 'prepare-witnessed') return run(path, options, send);
    demand(!busy && !disposed && !failed && typeof send === 'function'); busy = true;
    try {
      check(true); demand(write && issued && candidate && !verified && options.method === 'POST');
      demand(!Object.keys(options).some(k => !['method', 'body', 'cache'].includes(k)));
      demand(options.cache === undefined || options.cache === 'no-store');
      const safe = copy(options), body = witnessJson(safe.body, 5 * 1024 * 1024);
      demand(exact(body, ['request', 'witness']) && same(body.request, firstBody) && same(body.witness, issued.witness));
      const guard = () => {check(true); empty();}; guard();
      const value = copy(await send(Object.freeze(copy(safe)))); guard();
      validateVerifiedWitness(value, {intent_json: stable(candidate), witness_sha256: issued.witness_sha256}, candidate.context);
      guard(); verified = true; return value;
    } catch (error) {failed = true; throw error;} finally {busy = false;}
  }
  return {run: admitted, dispose: () => {disposed = true; firstBody = null; candidate = null; issued = null; acceptedSettlement = null;},
    state: () => ({busy, disposed, failed})};
}
