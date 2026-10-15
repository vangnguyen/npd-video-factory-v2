import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
import {createBrollPlanRootAdmission} from '../broll-plan-root-admission.mjs';
import {initializeBrollPlanReview, defaultBrollPlanSettings} from '../broll-plan-review.mjs';
import {witnessStable as stable} from '../broll-request-witness.mjs';

const copy = structuredClone;
const fixture = JSON.parse(readFileSync(new URL('./fixtures/sql-broll-witness-review.json', import.meta.url), 'utf8'));
const oldFixture = JSON.parse(readFileSync(new URL('./fixtures/broll-request-recovery.json', import.meta.url), 'utf8'));
const originalToken = 'vf1.test-owner.' + 'x'.repeat(48), newToken = 'vf1.renewed-owner.' + 'r'.repeat(40);
function harness(name = 'committed', memory = new Map(), legacy = null) {
  const f = copy(fixture.scenarios.find(s => s.name === name)), state = copy(legacy?.state ?? f.state);
  const calls = [], adopted = [], recovered = [], reads = [];
  let token = legacy ? newToken : originalToken, now = legacy?.clock ?? f.clock, current = null;
  let transport = null, nativeHook = null, digestHook = null, apiHook = null, epoch = 0, guardResult = true;
  const key = () => 'vf-broll-plan-pending-v1:' + stable([state.workspaceId, state.projectId, state.principal.subject]);
  const base = '/api/v1/projects/' + state.projectId + '/broll-plan-review';
  const choice = {readContext: null, settings: defaultBrollPlanSettings(), learningSnapshotId: null,
    prepareAcknowledged: false, abandonAcknowledged: false, witnessOptIn: false};
  if (legacy) memory.set(key(), legacy.pending_raw);
  const cryptoImpl = {subtle: {digest: async (...args) => {const value = await webcrypto.subtle.digest(...args);
    digestHook?.(new TextDecoder().decode(args[1])); return value;}}};
  const storage = {getItem: k => memory.get(k) ?? null, setItem: (k, v) => memory.set(k, v), removeItem: k => memory.delete(k),
    compareAndRemoveItem: (k, raw) => memory.get(k) === raw && memory.delete(k)};
  async function wire(path, options) {
    calls.push({path, method: options.method ?? 'GET', body: options.body ? JSON.parse(options.body) : null});
    const supplied = await transport?.(path, options); if (supplied !== undefined) return supplied;
    if (path === '/api/v1/auth/session') return copy(state.principal);
    if (legacy) {
      if (path.endsWith('/recovery/inspect')) return copy(legacy.observed);
      if (path.endsWith('/recovery/abandon') || path.includes('/recovery/settlements/')) return copy(legacy.settled);
      return copy(legacy.context);
    }
    if (path.endsWith('/witness/status')) return copy(f.capability);
    if (path.endsWith('/witness/verify')) return copy(token === originalToken ? f.verified_same : f.verified_fresh);
    if (path.endsWith('/witness')) return copy(f.issued);
    if (path.endsWith('/witnessed-recovery/inspect')) return copy(f.observed);
    if (path.endsWith('/witnessed-recovery/abandon') || path.includes('/witnessed-recovery/settlements/')) return copy(f.settled);
    if (path.includes('/requests/')) return copy(f.receipt);
    return copy(options.method === 'POST' ? f.prepared : token === originalToken ? f.context : f.fresh_context);
  }
  const api = (path, options = {}) => {
    assert.ok(current, 'No explicit operation');
    apiHook?.(path, options);
    return current.admission.run(path, options, safe => wire(path, safe));
  };
  const controller = initializeBrollPlanReview({api, getState: () => state, getSessionToken: () => token, storage,
    cryptoImpl, clock: () => now, newRequestKey: () => f.request.request_key,
    onPrepared: async (plan, receipt, guard) => {guard(); adopted.push({plan, receipt});},
    onRecoveryRead: async (value, guard, proof) => {guard(); reads.push({value, proof}); return true;},
    onRecovered: async (value, guard, proof) => {guard(); recovered.push({value, proof}); return true;}});
  async function operation(kind, fn, write = !['read', 'witness-capability', 'reconcile'].includes(kind)) {
    const op = {epoch}; current = op;
    op.admission = createBrollPlanRootAdmission({kind, write, getState: () => state, getSessionToken: () => token,
      getChoices: () => choice, getPendingState: () => controller.state(), getRaw: k => {const value = memory.get(k) ?? null; nativeHook?.(k); return value;},
      assertCurrent: () => current === op && op.epoch === epoch ? guardResult : false, cryptoImpl, clock: () => now});
    try {return await fn(op.admission);} finally {op.admission.dispose(); current = null;}
  }
  return {f, state, choice, calls, memory, controller, operation, api, key, base, adopted, recovered, reads,
    setTransport: fn => transport = fn, setNativeHook: fn => nativeHook = fn, setDigestHook: fn => digestHook = fn,
    setToken: value => token = value, setNow: value => now = value, bumpEpoch: () => epoch++, setGuard: value => guardResult = value,
    setApiHook: fn => apiHook = fn,
    renew: () => {token = newToken; state.principal = copy(f.current_principal);}};
}
async function read(h) {await h.operation('read', async () => {h.choice.readContext = await h.controller.reload();});}
async function ready(h) {await read(h); await h.operation('witness-capability', () => h.controller.readWitnessCapability());}
async function hold(h) {
  await ready(h); h.choice.witnessOptIn = true; h.choice.prepareAcknowledged = true;
  h.setTransport((path, o) => {if (path === h.base && o.method === 'POST') throw Error('fixture lost prepare response');});
  await assert.rejects(h.operation('prepare-witnessed', () => h.controller.prepareWithWitness(h.choice.settings, true)));
  h.setTransport(null); assert.equal(h.memory.size, 1); return h.memory.get(h.key());
}
const posts = h => h.calls.filter(c => c.method === 'POST');
const sends = (h, suffix) => h.calls.filter(c => c.path.endsWith(suffix));

test('constructor/state/dispose have no getter, storage, crypto or transport IO', () => {
  const no = () => {throw Error('constructor must not touch supplied surfaces');};
  const a = createBrollPlanRootAdmission({kind: 'read', write: false, getState: no, getSessionToken: no,
    getChoices: no, getPendingState: no, getRaw: no, assertCurrent: no});
  assert.deepEqual(a.state(), {busy: false, disposed: false, failed: false}); a.dispose(); assert.equal(a.state().disposed, true);
});
test('actual common controller uses explicit readiness/issue/verify/durable-v2/base prepare through real admission helper', async () => {
  const h = harness(); await ready(h); assert.equal(posts(h).length, 0);
  h.choice.witnessOptIn = true; h.choice.prepareAcknowledged = true;
  await h.operation('prepare-witnessed', () => h.controller.prepareWithWitness(h.choice.settings, true));
  assert.equal(posts(h).length, 3); assert.equal(h.adopted.length, 1); assert.equal(h.memory.size, 0);
  assert.deepEqual(posts(h)[0].body, h.f.request); assert.deepEqual(posts(h)[1].body, {request: h.f.request, witness: h.f.issued.witness});
  assert.deepEqual(posts(h)[2].body, h.f.request);
});
test('actual common defaultv1 remains one unchanged prepare POST without any witness route', async () => {
  const h = harness(); await read(h); h.choice.prepareAcknowledged = true;
  await h.operation('prepare', () => h.controller.prepare(h.choice.settings, true));
  assert.deepEqual(posts(h).map(c => c.body), [h.f.request]); assert.equal(h.adopted.length, 1);
});
test('cold v2 reconcile verifies held proof and reads exact receipt without reissuing/preparing', async () => {
  const h = harness(); await hold(h); const cold = harness('committed', h.memory);
  await cold.operation('reconcile', () => cold.controller.reconcile());
  assert.equal(posts(cold).length, 1); assert.ok(posts(cold)[0].path.endsWith('/witness/verify'));
  assert.equal(cold.adopted.length, 1); assert.equal(cold.memory.size, 0);
});
test('resend requires prior404 proof, verification and unchanged context, forwarding the identical body', async () => {
  const h = harness(); await hold(h);
  h.setTransport(path => {if (path.includes('/requests/')) throw Object.assign(Error('missing'), {status: 404});});
  await h.operation('reconcile', () => h.controller.reconcile()); assert.equal(h.controller.state().mayResend, true);
  await h.operation('resend', () => h.controller.resend(true));
  const sent = h.calls.filter(c => c.method === 'POST' && c.path === h.base);
  assert.equal(sent.length, 2); assert.deepEqual(sent[0].body, sent[1].body); assert.equal(h.memory.size, 0);
});
for (const name of ['absent', 'committed']) test('actual controller renewal uses exact inner literal and witnessed settlement proof: ' + name, async () => {
  const h = harness(name), raw = await hold(h); h.renew();
  await h.operation('recover-inspect', () => h.controller.inspectRecovery());
  h.choice.abandonAcknowledged = true;
  await h.operation('abandon', () => h.controller.abandonRecovery(true));
  assert.equal(h.recovered.length, 1); assert.equal(h.memory.size, 0); assert.equal(h.reads[0].proof.stored_raw, raw);
  for (const call of posts(h).filter(c => c.path.includes('/witnessed-recovery/'))) {
    assert.equal(call.body.intent_json, h.f.intent_json); assert.notEqual(call.body.intent_json, raw);
    assert.deepEqual(call.body.witness, h.f.issued.witness);
  }
});
for (const scenario of oldFixture.scenarios) test('actual old v1 recovery fixture retains exact legacy routes/intent bytes: ' + scenario.scenario, async () => {
  const h = harness('committed', new Map(), scenario);
  await h.operation('recover-inspect', () => h.controller.inspectRecovery()); h.choice.abandonAcknowledged = true;
  await h.operation('abandon', () => h.controller.abandonRecovery(true));
  assert.equal(h.memory.size, 0); assert.equal(h.recovered.length, 1);
  assert.ok(posts(h).every(c => c.path.includes('/recovery/') && c.body.intent_json === scenario.pending_raw && !('witness' in c.body)));
});

for (const target of ['/publish', '/media-plan/resolve', '/render', '/witness?x=1', '/requests/foreign', '/witnessed-recovery/abandon'])
  test('unscoped or operation-mismatched path cannot invoke transport: ' + target, async () => {
    const h = harness(); await assert.rejects(h.operation('read', () => h.api(h.base + target, {method: 'POST', body: '{}'})));
    assert.equal(h.calls.length, 0); assert.equal(h.memory.size, 0);
  });
for (const guard of [false, undefined, Promise.resolve(true)]) test('private Root guard must return literal synchronous true: ' + String(guard), async () => {
  const h = harness(); h.setGuard(guard);
  await assert.rejects(h.operation('read', () => h.controller.reload())); assert.equal(h.calls.length, 0);
});
test('failed issuer poisons its operation, blocking both a second key and silent v1 fallback', async () => {
  const h = harness(); await ready(h); h.choice.witnessOptIn = true; h.choice.prepareAcknowledged = true;
  h.setTransport(path => {if (path.endsWith('/witness')) throw Error('issuer unavailable');});
  await h.operation('prepare-witnessed', async admission => {
    await assert.rejects(h.controller.prepareWithWitness(h.choice.settings, true)); assert.equal(admission.state().failed, true);
    await assert.rejects(h.api(h.base + '/witness', {method: 'POST', body: JSON.stringify({...h.f.request, request_key: 'new-key-forbidden'})}));
    await assert.rejects(h.api(h.base, {method: 'POST', body: JSON.stringify(h.f.request)}));
  });
  assert.equal(posts(h).length, 1); assert.equal(h.memory.size, 0);
});
for (const phase of ['issuer', 'verify', 'prepare', 'recovery-inspect', 'recovery-abandon', 'settlement'])
  test('foreign durable raw during ' + phase + ' is never cleared or adopted', async () => {
    const h = harness('absent'), raw = await hold(h), foreign = '{"foreign":"B"}';
    if (phase.startsWith('recovery') || phase === 'settlement') h.renew();
    if (phase === 'recovery-abandon' || phase === 'settlement') await h.operation('recover-inspect', () => h.controller.inspectRecovery());
    const suffix = {issuer: '/witness', verify: '/witness/verify', prepare: h.base,
      'recovery-inspect': '/witnessed-recovery/inspect', 'recovery-abandon': '/witnessed-recovery/abandon'}[phase];
    h.setTransport(path => {if (phase === 'settlement' ? path.includes('/settlements/') : path.endsWith(suffix)) h.memory.set(h.key(), foreign);});
    if (phase === 'issuer' || phase === 'prepare') {
      // A held intent must refuse any fresh signing/preparation before transport.
      await assert.rejects(h.operation('prepare-witnessed', () => h.controller.prepareWithWitness(h.choice.settings, true)));
      assert.equal(h.memory.get(h.key()), raw); return;
    }
    if (phase === 'verify') await assert.rejects(h.operation('reconcile', () => h.controller.reconcile()));
    else if (phase === 'recovery-inspect') await assert.rejects(h.operation('recover-inspect', () => h.controller.inspectRecovery()));
    else {h.choice.abandonAcknowledged = true; await assert.rejects(h.operation('abandon', () => h.controller.abandonRecovery(true)));}
    assert.equal(h.memory.get(h.key()), foreign); assert.equal(h.recovered.length, 0); assert.equal(h.adopted.length, 0);
  });
for (const change of ['project', 'token', 'role', 'expiry', 'source', 'selection', 'draft', 'private_epoch'])
  test('late ' + change + ' at native getter is rechecked before any held verification POST', async () => {
    const h = harness(), raw = await hold(h); let once = false;
    h.setNativeHook(() => {if (once) return; once = true;
      if (change === 'project') h.state.projectId = 'prj_foreign_scope';
      if (change === 'token') h.setToken('vf1.other.' + 'q'.repeat(40));
      if (change === 'role') h.state.principal.platform_role = 'viewer';
      if (change === 'expiry') h.setNow(Date.parse(h.state.principal.expires_at));
      if (change === 'source') h.state.analysis.fingerprint = 'f'.repeat(64);
      if (change === 'selection') h.state.videoReviewSelection = {scene: 'other'};
      if (change === 'draft') h.state.dirty = true;
      if (change === 'private_epoch') h.bumpEpoch();
    });
    const before = h.calls.length; await assert.rejects(h.operation('reconcile', () => h.controller.reconcile()));
    assert.ok(h.calls.slice(before).every(c => c.method === 'GET')); assert.equal([...h.memory.values()][0], raw);
  });
test('one operation permits one inflight admission and no access after disposal', async () => {
  const h = harness(); let release; h.setTransport(path => path === '/api/v1/auth/session' ? new Promise(r => release = r) : undefined);
  await h.operation('read', async admission => {
    const first = h.api('/api/v1/auth/session');
    await assert.rejects(h.api('/api/v1/auth/session')); release(copy(h.state.principal)); await first;
    admission.dispose(); await assert.rejects(h.api('/api/v1/auth/session'));
  }); assert.equal(h.calls.length, 1);
});
test('validated immutable options cannot be retargeted by caller mutation across hash awaits', async () => {
  const h = harness(); await read(h); h.choice.prepareAcknowledged = true;
  h.setApiHook((path, original) => {if (path === h.base && original.method === 'POST') h.setDigestHook(() => {
    original.method = 'DELETE'; original.body = '{"untrusted":"new body"}';
  });});
  h.setTransport((path, safe) => {if (path === h.base && safe.method === 'POST') {
    assert.equal(Object.isFrozen(safe), true); assert.throws(() => {safe.method = 'DELETE';});
  }});
  await h.operation('prepare', () => h.controller.prepare(h.choice.settings, true));
  assert.equal(h.adopted.length, 1); assert.deepEqual(posts(h)[0].body, h.f.request);
});
test('a fresh prepare operation cannot turn a preexisting held intent into an implicit retry', async () => {
  const h = harness(), raw = await hold(h), count = h.calls.length;
  await assert.rejects(h.operation('prepare', () => h.api(h.base, {method: 'POST', body: JSON.stringify(h.f.request)})));
  assert.equal(h.calls.length, count); assert.equal(h.memory.get(h.key()), raw);
});
test('own form choices changing during preissuer admission hashes stop before signing or storage', async () => {
  const h = harness(); await ready(h); h.choice.prepareAcknowledged = true; h.choice.witnessOptIn = true;
  h.setApiHook(path => {if (path.endsWith('/witness')) h.setDigestHook(() => {
    h.choice.settings = {...h.choice.settings, resolver_priority: ['internal_library']};
  });});
  await assert.rejects(h.operation('prepare-witnessed', () => h.controller.prepareWithWitness(h.choice.settings, true)));
  assert.equal(sends(h, '/witness').length, 0); assert.equal(h.memory.size, 0);
});
for (const attack of ['legacy_route', 'outer_as_intent', 'other_key', 'other_witness'])
  test('retained v2 recovery cannot downgrade or substitute its complete proof: ' + attack, async () => {
    const h = harness('absent'), raw = await hold(h); h.renew();
    await h.operation('recover-inspect', async () => {
      await h.api(h.base, {cache: 'no-store'}); const count = h.calls.length;
      const body = {intent_json: h.f.intent_json, intent_sha256: h.f.intent_sha256, witness: copy(h.f.issued.witness)};
      if (attack === 'outer_as_intent') body.intent_json = raw;
      if (attack === 'other_key') {const v = JSON.parse(body.intent_json); v.body.request_key = 'foreign-request-0001'; body.intent_json = stable(v);}
      if (attack === 'other_witness') body.witness.signature = 'f'.repeat(64);
      await assert.rejects(h.api(h.base + (attack === 'legacy_route' ? '/recovery/inspect' : '/witnessed-recovery/inspect'),
        {method: 'POST', body: JSON.stringify(body)}));
      assert.equal(h.calls.length, count);
    }); assert.equal(h.memory.get(h.key()), raw);
  });

for (const mode of ['reconcile', 'resend']) test('legacy v1 lost-response ' + mode + ' uses no witness route', async () => {
  const h = harness(); await read(h); h.choice.prepareAcknowledged = true;
  h.setTransport((path, o) => {if (path === h.base && o.method === 'POST') throw Error('lost v1 response');});
  await assert.rejects(h.operation('prepare', () => h.controller.prepare(h.choice.settings, true)));
  h.setTransport(path => {if (mode === 'resend' && path.includes('/requests/')) throw Object.assign(Error('absent'), {status: 404});});
  await h.operation('reconcile', () => h.controller.reconcile());
  if (mode === 'resend') await h.operation('resend', () => h.controller.resend(true));
  assert.equal(h.memory.size, 0); assert.equal(h.adopted.length, 1);
  assert.ok(!h.calls.some(c => c.path.includes('/witness')));
});
for (const phase of ['descriptor_return', 'verified_response']) for (const change of ['raw', 'selection'])
  test('queued ' + change + ' after ' + phase + ' remains fenced across helper/common awaits', async () => {
    const h = harness(), raw = await hold(h); let armed = false, reads = 0;
    h.setApiHook(path => {if (phase === 'descriptor_return' && path.endsWith('/witness/verify')) {
      h.setDigestHook(text => {if (text === stable(h.f.issued.witness)) {armed = true; reads = 0;}});
    }});
    if (phase === 'verified_response') h.setTransport(path => {if (path.endsWith('/witness/verify')) {armed = true; reads = 0;}});
    h.setNativeHook(() => {if (armed && ++reads === 2) queueMicrotask(() => {
      if (change === 'raw') h.memory.set(h.key(), '{"foreign":"queued B"}');
      else h.state.videoReviewSelection = {scene: 'queued'};
    });});
    const before = h.calls.length; await assert.rejects(h.operation('reconcile', () => h.controller.reconcile()));
    if (phase === 'descriptor_return') assert.ok(h.calls.slice(before).every(c => c.method === 'GET'));
    assert.equal(h.adopted.length, 0); assert.equal(h.memory.get(h.key()), change === 'raw' ? '{"foreign":"queued B"}' : raw);
  });
for (const change of ['settlement_array', 'private_field', 'wrapper_proof', 'current_authority', 'observed_body', 'settlement_actor', 'provider'])
  test('strict signed response proof rejects ' + change + ' and retains complete raw', async () => {
    const h = harness('absent'), raw = await hold(h); h.renew();
    await h.operation('recover-inspect', () => h.controller.inspectRecovery()); h.choice.abandonAcknowledged = true;
    h.setTransport(path => {
      if (!path.endsWith('/witnessed-recovery/abandon')) return;
      const v = copy(h.f.settled);
      if (change === 'settlement_array') v.recovery.settlement.settlement_id = [v.recovery.settlement.settlement_id];
      if (change === 'private_field') v.recovery.private_identity = {};
      if (change === 'wrapper_proof') v.witness_sha256 = 'f'.repeat(64);
      if (change === 'current_authority') v.recovery.current_authority_sha256 = 'f'.repeat(64);
      if (change === 'observed_body') v.recovery.original_request_key = 'different-request-0001';
      if (change === 'settlement_actor') v.recovery.settlement.actor_ref = 'usr:foreign';
      if (change === 'provider') v.provider_calls = 1;
      return v;
    });
    await assert.rejects(h.operation('abandon', () => h.controller.abandonRecovery(true)));
    assert.equal(h.memory.get(h.key()), raw); assert.equal(h.recovered.length, 0);
  });
