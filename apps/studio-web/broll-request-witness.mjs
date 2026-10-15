// Public proof validation only. The VF server owns HMAC keys and verification.
const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
export const witnessStable = v => JSON.stringify(v, (_k, x) => object(x)
  ? Object.fromEntries(Object.keys(x).sort().map(k => [k, x[k]])) : x);
const same = (a, b) => witnessStable(a) === witnessStable(b);
const exact = (v, keys) => object(v) && same(Object.keys(v).sort(), [...keys].sort());
const hash = v => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const demand = (v, text = 'Bằng chứng yêu cầu B-roll không hợp lệ; giữ nguyên lần tạo đang chờ.') => {if (!v) throw Error(text);};
const bytes = s => new TextEncoder().encode(s).length;
const publicFields = ['subject', 'display_name', 'platform_role', 'workspace_roles', 'expires_at', 'human_write_enabled'];
const authorityFields = [...publicFields.filter(k => k !== 'human_write_enabled'), 'token_id', 'credential_sha256'];
const flags = v => v.execution_status === 'NOT_ASSERTED' && v.provider_calls === 0
  && v.source_media_mutated === false && v.publish_requested === false && v.owner_approval_inferred === false;

// Detect duplicate JSON keys without normalizing Python's literal numeric text.
// Bounds are checked before scanning, parsing or hashing untrusted storage.
export function witnessJson(raw, maxBytes = 262144) {
  demand(typeof raw === 'string' && bytes(raw) > 0 && bytes(raw) <= maxBytes);
  let i = 0, tokens = 0;
  const ws = () => {while (/[\x20\t\r\n]/.test(raw[i] ?? '') && i < raw.length) i++;};
  function string() {
    const start = i++; let escaped = false;
    while (i < raw.length) {
      const c = raw[i++];
      if (!escaped && c === '"') return JSON.parse(raw.slice(start, i));
      if (!escaped && c === '\\') escaped = true; else escaped = false;
    }
    demand(false);
  }
  function value(depth) {
    demand(depth <= 64 && ++tokens <= 100000); ws();
    if (raw[i] === '"') {string(); return;}
    if (raw[i] === '{') {
      i++; ws(); const keys = new Set(); if (raw[i] === '}') {i++; return;}
      while (true) {
        demand(raw[i] === '"'); const key = string(); demand(!keys.has(key)); keys.add(key);
        ws(); demand(raw[i++] === ':'); value(depth + 1); ws(); const end = raw[i++];
        if (end === '}') return; demand(end === ','); ws();
      }
    }
    if (raw[i] === '[') {
      i++; ws(); if (raw[i] === ']') {i++; return;}
      while (true) {value(depth + 1); ws(); const end = raw[i++]; if (end === ']') return; demand(end === ',');}
    }
    const match = /^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(raw.slice(i));
    demand(match); if (!['true', 'false', 'null'].includes(match[0])) demand(Number.isFinite(Number(match[0]))); i += match[0].length;
  }
  value(0); ws(); demand(i === raw.length); return JSON.parse(raw);
}

export function validateWitnessCapability(v, s) {
  demand(exact(v, ['schema_version', 'workspace_id', 'project_id', 'actor_ref', 'status', 'issuance_available', 'optional',
    'witness_schema_version', 'algorithm', 'execution_status', 'provider_calls', 'source_media_mutated', 'publish_requested', 'owner_approval_inferred'])
    && v.schema_version === 'vf-broll-request-witness-capability.v1' && v.workspace_id === s.workspaceId
    && v.project_id === s.projectId && v.actor_ref === s.principal?.subject
    && ['READY', 'NOT_CONFIGURED', 'UNAVAILABLE'].includes(v.status) && v.issuance_available === (v.status === 'READY')
    && v.optional === true && v.witness_schema_version === 'vf-broll-request-witness.v1' && v.algorithm === 'HMAC-SHA256' && flags(v));
  return v;
}

export function validateWitnessEnvelope(v, intent, now, requireFresh = true) {
  demand(exact(v, ['schema_version', 'key_id', 'claims_json', 'signature']) && v.schema_version === 'vf-broll-request-witness.v1'
    && typeof v.key_id === 'string' && /^[A-Za-z0-9_-]{1,64}$/.test(v.key_id) && hash(v.signature));
  const c = witnessJson(v.claims_json), original = witnessJson(intent.boundary, 5 * 1024 * 1024)[2];
  demand(exact(c, ['schema_version', 'purpose', 'issued_at', 'expires_at', 'workspace_id', 'project_id', 'request_key', 'body',
    'body_sha256', 'prepare_request_sha256', 'original_authority', 'original_authority_sha256', 'credential_sha256',
    'public_session', 'context', 'source', 'timeline_id', 'timeline_version', 'timeline_version_id'])
    && c.schema_version === 'vf-broll-prepare-witness-claims.v1' && c.purpose === 'video-factory:broll-prepare-intent:v1'
    && Number.isSafeInteger(c.issued_at) && c.issued_at >= 0 && Number.isSafeInteger(c.expires_at)
    && c.expires_at - c.issued_at >= 300 && c.expires_at - c.issued_at <= 30 * 86400
    && Number.isFinite(now) && c.issued_at * 1000 <= now && (!requireFresh || now < c.expires_at * 1000)
    && c.workspace_id === intent.context.workspace_id && c.project_id === intent.context.project_id
    && c.request_key === intent.body.request_key && same(c.body, intent.body) && same(c.context, intent.context)
    && hash(c.body_sha256) && hash(c.prepare_request_sha256) && hash(c.original_authority_sha256)
    && c.original_authority_sha256 === intent.context.authority_sha256
    && c.credential_sha256 === intent.credential_sha256 && same(c.source, intent.context.source)
    && exact(c.public_session, publicFields) && same(c.public_session, original) && c.public_session.human_write_enabled === true
    && exact(c.original_authority, authorityFields) && typeof c.original_authority.token_id === 'string'
    && c.original_authority.token_id.length >= 1 && c.original_authority.token_id.length <= 128
    && hash(c.original_authority.credential_sha256)
    && publicFields.filter(k => k !== 'human_write_enabled').every(k => same(c.original_authority[k], original[k]))
    && ['timeline_id', 'timeline_version', 'timeline_version_id'].every(k => c[k] === intent.context[k]));
  return c;
}

export function validateIssuedWitness(v, intent, now) {
  demand(exact(v, ['schema_version', 'witness', 'witness_sha256', 'execution_status', 'provider_calls',
    'source_media_mutated', 'publish_requested', 'owner_approval_inferred'])
    && v.schema_version === 'vf-broll-request-witness-issued.v1' && hash(v.witness_sha256) && flags(v));
  return validateWitnessEnvelope(v.witness, intent, now);
}

export function decodeWitnessPending(raw, now) {
  const record = witnessJson(raw, 5 * 1024 * 1024);
  demand(exact(record, ['schema_version', 'intent_json', 'intent_sha256', 'witness', 'witness_sha256'])
    && record.schema_version === 'broll-plan-pending.v2' && hash(record.intent_sha256) && hash(record.witness_sha256)
    && typeof record.intent_json === 'string' && bytes(record.intent_json) <= 4 * 1024 * 1024 && witnessStable(record) === raw);
  const intent = witnessJson(record.intent_json, 4 * 1024 * 1024);
  demand(exact(intent, ['schema_version', 'body', 'context', 'boundary', 'session_sha256', 'credential_sha256'])
    && intent.schema_version === 'broll-plan-pending.v1' && witnessStable(intent) === record.intent_json);
  validateWitnessEnvelope(record.witness, intent, now, false);
  return {record, intent};
}

export function validateVerifiedWitness(v, record, fresh) {
  const intent = witnessJson(record.intent_json, 4 * 1024 * 1024);
  demand(exact(v, ['schema_version', 'authorization_witness_valid', 'witness_sha256', 'workspace_id', 'project_id', 'request_key',
    'original_authority_sha256', 'current_authority_sha256', 'current_context_sha256', 'source', 'execution_status',
    'provider_calls', 'source_media_mutated', 'publish_requested', 'owner_approval_inferred'])
    && v.schema_version === 'vf-broll-request-witness-verified.v1' && v.authorization_witness_valid === true
    && v.witness_sha256 === record.witness_sha256 && v.workspace_id === intent.context.workspace_id
    && v.project_id === intent.context.project_id && v.request_key === intent.body.request_key
    && v.original_authority_sha256 === intent.context.authority_sha256
    && v.current_authority_sha256 === fresh.authority_sha256 && v.current_context_sha256 === fresh.context_sha256
    && same(v.source, intent.context.source) && flags(v));
  return v;
}

export function validateWitnessRecovery(v, record) {
  demand(exact(v, ['schema_version', 'recovery', 'witness_sha256', 'key_id', 'execution_status', 'provider_calls',
    'source_media_mutated', 'publish_requested', 'owner_approval_inferred'])
    && v.schema_version === 'vf-broll-witnessed-recovery.v1' && v.witness_sha256 === record.witness_sha256
    && v.key_id === record.witness.key_id && object(v.recovery) && flags(v));
  return v.recovery;
}
