import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto, createHash} from 'node:crypto';
import {initializeBrollPlanReview, defaultBrollPlanSettings} from '../broll-plan-review.mjs';
import {witnessStable, witnessJson, decodeWitnessPending, validateWitnessEnvelope} from '../broll-request-witness.mjs';

const fixture = JSON.parse(readFileSync(new URL('./fixtures/sql-broll-witness-review.json', import.meta.url), 'utf8'));
const copy = structuredClone, hash = v => createHash('sha256').update(typeof v === 'string' ? v : witnessStable(v)).digest('hex');
// Deliberate public fixture value, authenticated only in the owned ASGI fixture.
const originalToken = 'vf1.test-owner.' + 'x'.repeat(48), renewedToken = 'vf1.renewed-owner.' + 'r'.repeat(40);
function harness(name = 'committed', memory = new Map()) {
  const f = copy(fixture.scenarios.find(s => s.name === name)), state = copy(f.state), calls = [], adopted = [], reads = [], recovered = [];
  let token = originalToken, now = f.clock, transport = null, getHook = null, digestHook = null, callbackHook = null;
  const key = () => 'vf-broll-plan-pending-v1:' + witnessStable([state.workspaceId, state.projectId, state.principal.subject]);
  const base = '/api/v1/projects/' + state.projectId + '/broll-plan-review';
  const storage = {getItem: k => {getHook?.(k); return memory.get(k) ?? null;},
    setItem: (k, raw) => memory.set(k, raw), removeItem: k => memory.delete(k),
    compareAndRemoveItem: (k, raw) => memory.get(k) === raw && memory.delete(k)};
  const api = async (path, options = {}) => {
    const body = options.body ? JSON.parse(options.body) : null;
    calls.push({path, method: options.method ?? 'GET', body});
    const custom = await transport?.(path, options, body); if (custom !== undefined) return custom;
    if (path === '/api/v1/auth/session') return copy(state.principal);
    if (path.endsWith('/witness/status')) return copy(f.capability);
    if (path.endsWith('/witness/verify')) return copy(token === originalToken ? f.verified_same : f.verified_fresh);
    if (path.endsWith('/witness')) return copy(f.issued);
    if (path.endsWith('/witnessed-recovery/inspect')) return copy(f.observed);
    if (path.endsWith('/witnessed-recovery/abandon') || path.includes('/witnessed-recovery/settlements/')) return copy(f.settled);
    if (path.includes('/requests/')) return copy(f.receipt);
    if (path === base) return copy(options.method === 'POST' ? f.prepared : token === originalToken ? f.context : f.fresh_context);
    throw Error('Unexpected fixture path: ' + path);
  };
  const controller = initializeBrollPlanReview({api, getState: () => state, getSessionToken: () => token, storage,
    cryptoImpl: {subtle: {digest: async (...args) => {const result = await webcrypto.subtle.digest(...args);
      digestHook?.(new TextDecoder().decode(args[1])); return result;}}}, newRequestKey: () => f.request.request_key,
    clock: () => now, onPrepared: async (plan, receipt, guard) => {guard(); await callbackHook?.('prepared', guard); guard(); adopted.push({plan, receipt});},
    onRecoveryRead: async (value, guard, proof) => {guard(); await callbackHook?.('read', guard); guard(); reads.push({value, proof}); return true;},
    onRecovered: async (value, guard, proof) => {guard(); await callbackHook?.('recovered', guard); guard(); recovered.push({value, proof}); return true;}});
  return {f, state, calls, memory, controller, storage, adopted, reads, recovered, base, key,
    setTransport: fn => transport = fn, setGetHook: fn => getHook = fn, setDigestHook: fn => digestHook = fn,
    setCallbackHook: fn => callbackHook = fn, setNow: n => now = n, setToken: t => token = t,
    renew: () => {token = renewedToken; state.principal = copy(f.current_principal);}};
}
const posts = h => h.calls.filter(c => c.method === 'POST');
const prepares = h => posts(h).filter(c => c.path === h.base);
const signatures = h => posts(h).filter(c => c.path.endsWith('/witness'));
async function ready(h) {await h.controller.reload(); await h.controller.readWitnessCapability();}
async function held(h) {
  await ready(h); h.setTransport((path, o) => {if (path === h.base && o.method === 'POST') throw Error('fixture lost prepare response');});
  await assert.rejects(h.controller.prepareWithWitness(defaultBrollPlanSettings(), true));
  h.setTransport(null); assert.equal(h.memory.size, 1); return h.memory.get(h.key());
}

test('actual shipped-main SQL captures preserve two exact old-intent literals and no private key', () => {
  assert.match(fixture.fixture_notice, /Actual authenticated shipped-main ASGI/); assert.deepEqual(fixture.network_attempts, []);
  for (const f of fixture.scenarios) {
    assert.equal(hash(f.intent_json), f.intent_sha256); assert.equal(witnessStable(f.intent), f.intent_json);
    assert.equal(f.issued.witness_sha256, hash(f.issued.witness));
    assert.deepEqual(validateWitnessEnvelope(f.issued.witness, f.intent, f.clock).body, f.request);
    assert.equal(f.after_counts.service_api_operations - f.before_counts.service_api_operations, f.name === 'committed' ? 2 : 1);
  }
});
test('construction/state/reload/capability read never POST or sign, and default v1 remains unchanged', async () => {
  const h = harness(); assert.deepEqual(h.calls, []); assert.equal(h.controller.state().pending, null);
  await ready(h); assert.equal(posts(h).length, 0);
  await h.controller.prepare(defaultBrollPlanSettings(), true);
  assert.equal(posts(h).length, 1); assert.deepEqual(prepares(h)[0].body, h.f.request); assert.equal(signatures(h).length, 0);
});
test('explicit opt-in signs and verifies exact basebody before durable v2 then adopts exact actual plan', async () => {
  const h = harness(); await ready(h);
  h.setTransport((path, o, body) => {
    if (path.endsWith('/witness') || path.endsWith('/witness/verify')) assert.equal(h.memory.size, 0);
    if (path === h.base && o.method === 'POST') {
      const record = JSON.parse(h.memory.get(h.key()));
      assert.equal(record.schema_version, 'broll-plan-pending.v2'); assert.equal(record.intent_json, h.f.intent_json);
      assert.equal(record.intent_sha256, h.f.intent_sha256); assert.deepEqual(record.witness, h.f.issued.witness);
      assert.deepEqual(body, h.f.request); assert.ok(!h.memory.get(h.key()).includes(originalToken));
    }
  });
  await h.controller.prepareWithWitness(defaultBrollPlanSettings(), true);
  assert.equal(signatures(h).length, 1); assert.equal(prepares(h).length, 1);
  assert.equal(h.adopted.length, 1); assert.equal(h.memory.size, 0);
});
test('missing captured capability or acknowledgement blocks all POST; NOT_CONFIGURED does not change ordinary v1', async () => {
  const h = harness(); await h.controller.reload();
  await assert.rejects(h.controller.prepareWithWitness(defaultBrollPlanSettings(), true));
  assert.equal(posts(h).length, 0);
  h.setTransport(path => path.endsWith('/witness/status') ? {...copy(h.f.capability), status: 'NOT_CONFIGURED', issuance_available: false} : undefined);
  await h.controller.readWitnessCapability(); await assert.rejects(h.controller.prepareWithWitness(defaultBrollPlanSettings(), true));
  assert.equal(posts(h).length, 0); await h.controller.prepare(defaultBrollPlanSettings(), true); assert.equal(prepares(h).length, 1);
  const other = harness(); await ready(other); await assert.rejects(other.controller.prepareWithWitness(defaultBrollPlanSettings(), false)); assert.equal(posts(other).length, 0);
});
test('issuer or verification failure never falls back, prepares, or leaves an unsigned durable intent', async () => {
  for (const suffix of ['/witness', '/witness/verify']) {
    const h = harness(); await ready(h); h.setTransport(path => {if (path.endsWith(suffix)) throw Error('fixture signing unavailable');});
    await assert.rejects(h.controller.prepareWithWitness(defaultBrollPlanSettings(), true));
    assert.equal(prepares(h).length, 0); assert.equal(h.memory.size, 0);
  }
});
test('cold v2 reconcile verifies exact retained proof then reads committed receipt without reissuing or preparing', async () => {
  const h = harness(), raw = await held(h), cold = harness('committed', h.memory);
  assert.deepEqual(cold.calls, []); await assert.rejects(cold.controller.reload()); assert.equal(cold.memory.get(cold.key()), raw);
  await cold.controller.reconcile(); assert.equal(cold.adopted.length, 1); assert.equal(cold.memory.size, 0);
  assert.equal(signatures(cold).length, 0); assert.equal(prepares(cold).length, 0);
  assert.deepEqual(posts(cold)[0].body, {request: cold.f.request, witness: cold.f.issued.witness});
});
test('explicit 404 retry sends the exact basebody, retains proof/key, and never signs a replacement', async () => {
  const h = harness(); await held(h);
  h.setTransport(path => {if (path.includes('/requests/')) {const e = Error('fixture absent'); e.status = 404; throw e;}});
  await h.controller.reconcile(); assert.equal(h.controller.state().mayResend, true);
  await assert.rejects(h.controller.resend(false)); await h.controller.resend(true);
  assert.equal(signatures(h).length, 1); assert.equal(prepares(h).length, 2); assert.deepEqual(prepares(h)[0].body, prepares(h)[1].body);
  assert.equal(h.memory.size, 0);
});
for (const name of ['absent', 'committed']) test('renewed/pruned v2 recovery uses reviewed wrapper and exact inner intent: ' + name, async () => {
  const h = harness(name), raw = await held(h); h.renew();
  await assert.rejects(h.controller.reconcile()); assert.equal(h.memory.get(h.key()), raw);
  const observed = await h.controller.inspectRecovery(); assert.deepEqual(observed, h.f.observed.recovery);
  assert.equal(h.reads[0].proof.stored_raw, raw); assert.equal(h.reads[0].proof.intent_json, h.f.intent_json);
  assert.deepEqual(h.reads[0].proof.response, h.f.observed);
  await assert.rejects(h.controller.abandonRecovery(false)); await h.controller.abandonRecovery(true);
  assert.equal(h.recovered.length, 1); assert.deepEqual(h.recovered[0].value, h.f.settled.recovery);
  assert.equal(h.memory.size, 0); assert.equal(signatures(h).length, 1); assert.equal(prepares(h).length, 1);
  for (const call of posts(h).filter(c => c.path.includes('witnessed-recovery'))) {
    assert.equal(call.body.intent_json, h.f.intent_json); assert.equal(call.body.intent_sha256, h.f.intent_sha256);
    assert.deepEqual(call.body.witness, h.f.issued.witness); assert.notEqual(call.body.intent_json, raw);
  }
});
test('lost signed settlement response retains raw then explicit reinspection/replay clears only same proof', async () => {
  const h = harness('absent'), raw = await held(h); h.renew(); await h.controller.inspectRecovery();
  h.setTransport(path => {if (path.endsWith('/witnessed-recovery/abandon')) throw Error('lost committed seal response');});
  await assert.rejects(h.controller.abandonRecovery(true)); assert.equal(h.memory.get(h.key()), raw);
  h.setTransport(path => path.endsWith('/witnessed-recovery/inspect') ? copy(h.f.settled) : undefined);
  await h.controller.inspectRecovery(); await h.controller.abandonRecovery(true);
  assert.equal(h.memory.size, 0); assert.equal(prepares(h).length, 1);
});

for (const change of ['body', 'key', 'authority', 'signature_hash', 'duplicate_claims', 'oversized_claims', 'future', 'expired', 'provider_flag'])
  test('untrusted issued proof is rejected before durable record/base prepare: ' + change, async () => {
    const h = harness(); await ready(h); h.setTransport(path => {
      if (!path.endsWith('/witness')) return;
      const issued = copy(h.f.issued), c = JSON.parse(issued.witness.claims_json);
      if (change === 'body') c.body.request_key = 'different-request-0001';
      if (change === 'key') issued.witness.key_id = ['fixture-key-a'];
      if (change === 'authority') c.original_authority_sha256 = 'f'.repeat(64);
      if (change === 'signature_hash') issued.witness.signature = 'f'.repeat(64);
      if (change === 'provider_flag') issued.provider_calls = 1;
      if (change === 'future') c.issued_at += 86400;
      if (change === 'expired') {c.issued_at -= 86400; c.expires_at -= 86400;}
      if (['body', 'authority', 'future', 'expired'].includes(change)) issued.witness.claims_json = JSON.stringify(c);
      if (change === 'duplicate_claims') issued.witness.claims_json = '{"purpose":"bad",' + issued.witness.claims_json.slice(1);
      if (change === 'oversized_claims') issued.witness.claims_json = ' '.repeat(262145);
      return issued;
    });
    await assert.rejects(h.controller.prepareWithWitness(defaultBrollPlanSettings(), true));
    assert.equal(prepares(h).length, 0); assert.equal(h.memory.size, 0);
  });
for (const phase of ['issue', 'verify', 'intent_hash', 'native_get'])
  test('foreign slot after ' + phase + ' is never overwritten or executed', async () => {
    const h = harness(), foreign = '{"foreign":"request B"}'; await ready(h); let armed = false;
    if (phase === 'issue' || phase === 'verify') h.setTransport(path => {
      if (path.endsWith(phase === 'issue' ? '/witness' : '/witness/verify')) h.memory.set(h.key(), foreign);
    });
    if (phase === 'intent_hash') h.setDigestHook(text => {if (text === h.f.intent_json) h.memory.set(h.key(), foreign);});
    if (phase === 'native_get') {
      h.setTransport(path => {if (path.endsWith('/witness/verify')) armed = true;});
      h.setGetHook(() => {if (armed) h.memory.set(h.key(), foreign);});
    }
    await assert.rejects(h.controller.prepareWithWitness(defaultBrollPlanSettings(), true));
    assert.equal(h.memory.get(h.key()), foreign); assert.equal(prepares(h).length, 0);
  });
for (const change of ['source', 'token', 'principal', 'draft', 'project', 'expiry'])
  test('scope/session drift during signing await makes no durable record or base prepare: ' + change, async () => {
    const h = harness(); await ready(h); h.setTransport(path => {
      if (!path.endsWith('/witness')) return;
      if (change === 'source') h.state.analysis.fingerprint = 'f'.repeat(64);
      if (change === 'token') h.setToken('vf1.changed.' + 'q'.repeat(40));
      if (change === 'principal') h.state.principal.display_name = 'Different';
      if (change === 'draft') h.state.dirty = true;
      if (change === 'project') h.state.projectId = 'prj_foreign_scope';
      if (change === 'expiry') h.setNow(Date.parse(h.state.principal.expires_at));
    });
    await assert.rejects(h.controller.prepareWithWitness(defaultBrollPlanSettings(), true));
    assert.equal(prepares(h).length, 0); assert.equal(h.memory.size, 0);
  });
for (const change of ['intent_hash', 'witness_hash', 'signature', 'body', 'foreign_project', 'expired'])
  test('cold malformed/tampered/expired proof stays held, no receipt adoption or prepare: ' + change, async () => {
    const h = harness(), raw = await held(h); const record = JSON.parse(raw);
    if (change === 'intent_hash') record.intent_sha256 = 'f'.repeat(64);
    if (change === 'witness_hash') record.witness_sha256 = 'f'.repeat(64);
    if (change === 'signature') {record.witness.signature = 'f'.repeat(64); record.witness_sha256 = hash(record.witness);}
    if (change === 'body') {const p = JSON.parse(record.intent_json); p.body.request_key = 'different-request-0001'; record.intent_json = witnessStable(p); record.intent_sha256 = hash(record.intent_json);}
    h.memory.set(h.key(), witnessStable(record)); const cold = harness('committed', h.memory);
    if (change === 'foreign_project') cold.state.projectId = 'prj_foreign_scope';
    if (change === 'expired') cold.setNow(JSON.parse(record.witness.claims_json).expires_at * 1000);
    if (change === 'signature') cold.setTransport(path => {if (path.endsWith('/witness/verify')) throw Error('server HMAC denied');});
    await assert.rejects(cold.controller.reconcile()); assert.equal(h.memory.get(h.key()), witnessStable(record));
    assert.equal(cold.adopted.length, 0); assert.equal(prepares(cold).length, 0); assert.equal(signatures(cold).length, 0);
  });
for (const phase of ['inspect', 'abandon', 'settlement', 'callback'])
  test('signed recovery foreign raw at ' + phase + ' is retained without settlement adoption/local clear', async () => {
    const h = harness('absent'); await held(h); h.renew(); const foreign = '{"foreign":"request B"}';
    if (phase !== 'inspect') await h.controller.inspectRecovery();
    h.setTransport(path => {
      if (phase === 'inspect' && path.endsWith('/witnessed-recovery/inspect')
        || phase === 'abandon' && path.endsWith('/witnessed-recovery/abandon')
        || phase === 'settlement' && path.includes('/witnessed-recovery/settlements/')) h.memory.set(h.key(), foreign);
    });
    if (phase === 'callback') h.setCallbackHook((kind, guard) => {if (kind === 'recovered') {h.memory.set(h.key(), foreign); guard();}});
    await assert.rejects(phase === 'inspect' ? h.controller.inspectRecovery() : h.controller.abandonRecovery(true));
    assert.equal(h.memory.get(h.key()), foreign); assert.equal(h.recovered.length, 0);
  });
test('strict bounded JSON rejects duplicate keys nonfinite overflow/deep input and keeps literal floats', () => {
  assert.deepEqual(witnessJson('{"time":16.0}'), {time: 16});
  for (const raw of ['{"a":1,"a":2}', '{"a":{"x":1,"x":2}}', '[1e999]', '['.repeat(66) + '0' + ']'.repeat(66), ' '.repeat(262145)])
    assert.throws(() => witnessJson(raw));
  const f = fixture.scenarios[0], record = {schema_version: 'broll-plan-pending.v2', intent_json: f.intent_json,
    intent_sha256: f.intent_sha256, witness: f.issued.witness, witness_sha256: f.issued.witness_sha256};
  assert.equal(decodeWitnessPending(witnessStable(record), f.clock).record.intent_json, f.intent_json);
});

for (const phase of ['session', 'verification', 'envelope_hash', 'bearer_hash', 'intent_hash', 'storage_readback'])
  test('witness opt-in retains selection boundary across ' + phase, async () => {
    const h = harness(); await ready(h); let armed = false;
    const drift = () => {h.state.videoReviewSelection = {analysis_id: 'ana_other_selection'};};
    h.setTransport(path => {
      if (phase === 'session' && path === '/api/v1/auth/session') drift();
      if (phase === 'verification' && path.endsWith('/witness/verify')) drift();
    });
    h.setDigestHook(text => {
      if (phase === 'envelope_hash' && text === witnessStable(h.f.issued.witness)
        || phase === 'bearer_hash' && text === 'Bearer ' + originalToken
        || phase === 'intent_hash' && text === h.f.intent_json) drift();
    });
    if (phase === 'storage_readback') {
      const set = h.storage.setItem; h.storage.setItem = (k, raw) => {set(k, raw); armed = true;};
      h.setGetHook(() => {if (armed) drift();});
    }
    await assert.rejects(h.controller.prepareWithWitness(defaultBrollPlanSettings(), true));
    assert.equal(prepares(h).length, 0); assert.equal(h.adopted.length, 0);
    assert.equal(h.memory.size, phase === 'storage_readback' ? 1 : 0);
  });
for (const change of ['selection', 'analysis', 'asset', 'token', 'draft', 'raw'])
  test('private prepared callback rejects late ' + change + ' and retains durable outer', async () => {
    const h = harness(); await ready(h); let original;
    h.setTransport((path, o) => {if (path === h.base && o.method === 'POST') original = h.memory.get(h.key());});
    h.setCallbackHook(async (kind, guard) => {
      if (kind !== 'prepared') return;
      await Promise.resolve();
      if (change === 'selection') h.state.videoReviewSelection = {scene: 'other'};
      if (change === 'analysis') h.state.analysis.fingerprint = 'f'.repeat(64);
      if (change === 'asset') h.state.assets[0].storage_provider = 's3';
      if (change === 'token') h.setToken('vf1.changed.' + 'q'.repeat(40));
      if (change === 'draft') h.state.dirty = true;
      if (change === 'raw') h.memory.set(h.key(), '{"foreign":"B"}');
      guard();
    });
    await assert.rejects(h.controller.prepareWithWitness(defaultBrollPlanSettings(), true));
    assert.equal(h.adopted.length, 0); assert.equal(h.memory.get(h.key()), change === 'raw' ? '{"foreign":"B"}' : original);
  });
for (const change of ['wrapper_hash', 'wrapper_key', 'scope', 'provider', 'settlement_scope'])
  test('signed recovery receipt tamper never clears/adopts: ' + change, async () => {
    const h = harness('absent'), raw = await held(h); h.renew(); await h.controller.inspectRecovery();
    h.setTransport(path => {
      if (!path.endsWith('/witnessed-recovery/abandon')) return;
      const v = copy(h.f.settled);
      if (change === 'wrapper_hash') v.witness_sha256 = 'f'.repeat(64);
      if (change === 'wrapper_key') v.key_id = 'foreign-key';
      if (change === 'scope') v.recovery.project_id = 'prj_foreign_scope';
      if (change === 'provider') v.provider_calls = 1;
      if (change === 'settlement_scope') v.recovery.settlement.actor_ref = 'usr:foreign';
      return v;
    });
    await assert.rejects(h.controller.abandonRecovery(true));
    assert.equal(h.memory.get(h.key()), raw); assert.equal(h.recovered.length, 0);
  });

for (const phase of ['inspect', 'abandon']) for (const change of ['raw', 'selection'])
  test('queued ' + change + ' after fresh-context helper returns fences ' + phase + ' before POST', async () => {
    const h = harness('absent'), raw = await held(h); h.renew();
    if (phase === 'abandon') await h.controller.inspectRecovery();
    let armed = false, nativeReads = 0;
    h.setTransport((path, o) => {if (path === h.base && o.method !== 'POST') armed = true;});
    h.setGetHook(() => {if (armed && ++nativeReads === 2) queueMicrotask(() => {
      if (change === 'raw') h.memory.set(h.key(), '{"foreign":"queued B"}');
      else h.state.videoReviewSelection = {scene: 'queued selection'};
    });});
    const suffix = '/witnessed-recovery/' + phase, count = h.calls.filter(c => c.path.endsWith(suffix)).length;
    await assert.rejects(phase === 'inspect' ? h.controller.inspectRecovery() : h.controller.abandonRecovery(true));
    assert.equal(h.calls.filter(c => c.path.endsWith(suffix)).length, count);
    assert.equal(h.memory.get(h.key()), change === 'raw' ? '{"foreign":"queued B"}' : raw);
  });
test('queued foreign raw after proof-hash helper returns cannot dispatch witness verification POST', async () => {
  const h = harness(), raw = await held(h); let armed = false;
  h.setDigestHook(text => {if (text === witnessStable(h.f.issued.witness)) armed = true;});
  h.setGetHook(() => {if (armed) {armed = false; queueMicrotask(() => h.memory.set(h.key(), '{"foreign":"queued B"}'));}});
  const count = h.calls.filter(c => c.path.endsWith('/witness/verify')).length;
  await assert.rejects(h.controller.reconcile());
  assert.equal(h.calls.filter(c => c.path.endsWith('/witness/verify')).length, count);
  assert.notEqual(h.memory.get(h.key()), raw); assert.equal(h.memory.get(h.key()), '{"foreign":"queued B"}');
});
