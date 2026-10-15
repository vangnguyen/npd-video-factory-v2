import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
import {defaultBrollPlanSettings, brollPlanSettings, validateBrollPlanContext, initializeBrollPlanReview} from '../broll-plan-review.mjs';
const captured = JSON.parse(readFileSync(new URL('./fixtures/sql-broll-plan-review.json', import.meta.url), 'utf8'));
const copy = structuredClone;
function harness(transport, memory = new Map()) {
  const state = copy(captured.state), calls = [], adopted = [], notices = [];
  let token = 'vf1.fixture-local-not-provider', now = captured.clock;
  let cryptoHook = null;
  const storage = {getItem: k => memory.get(k) ?? null, setItem: (k, v) => memory.set(k, v), removeItem: k => memory.delete(k)};
  const api = async (path, options = {}) => {
    calls.push({path, method: options.method ?? 'GET', body: options.body ? JSON.parse(options.body) : null});
    const value = await transport?.(path, options, {state, calls, memory});
    if (value !== undefined) return value;
    if (path === '/api/v1/auth/session') return copy(state.principal);
    return copy(options.method === 'POST' || path.includes('/requests/') ? captured.response : captured.context);
  };
  const controller = initializeBrollPlanReview({api, getState: () => state, getSessionToken: () => token, storage,
    cryptoImpl: {subtle: {digest: async (...args) => {const result = await webcrypto.subtle.digest(...args); cryptoHook?.(); return result;}}},
    newRequestKey: () => captured.request.request_key, clock: () => now,
    onPrepared: async (...args) => adopted.push(args), onStatus: text => notices.push(text)});
  return {controller, state, calls, memory, adopted, notices, storage,
    setCryptoHook: fn => cryptoHook = fn, setToken: v => token = v, setNow: v => now = v};
}

test('actual SQLite/ASGI fixture, default no external/AI/paid and construction does no IO', () => {
  assert.match(captured.fixture_notice, /Actual SQLite.*authenticated ASGI/);
  assert.equal(captured.network_attempts, 0);
  assert.deepEqual(defaultBrollPlanSettings(), captured.request.settings);
  const h = harness(); assert.deepEqual(h.calls, []); assert.equal(h.controller.state().context, null);
  assert.equal(validateBrollPlanContext(captured.context, captured.state, captured.clock), captured.context);
});
test('explicit reload reads session/context only; exact reviewed create stores matching actual DTO then adopts once', async () => {
  const h = harness(); await h.controller.reload(); assert.equal(h.calls.length, 2);
  assert.ok(h.calls.every(v => v.method === 'GET'));
  const result = await h.controller.prepare(defaultBrollPlanSettings(), true);
  assert.equal(result.state, 'prepared'); assert.equal(h.adopted.length, 1);
  assert.deepEqual(h.calls.find(v => v.method === 'POST').body, captured.request);
  assert.equal(h.memory.size, 0);
});
test('missing confirmation, unavailable stock, malformed settings and paid/AI attempt make zero POST', async () => {
  const h = harness(); await h.controller.reload();
  await assert.rejects(h.controller.prepare(defaultBrollPlanSettings(), false));
  const stock = {...defaultBrollPlanSettings(), allow_stock: true, resolver_priority: ['licensed_stock']};
  await assert.rejects(h.controller.prepare(stock, true));
  for (const change of [v => v.allow_stock = 'false', v => v.allow_ai_image = true, v => v.max_ai_cost_vnd = '1',
    v => v.resolver_priority.push('user_asset'), v => v.actor_ref = 'fake-owner', v => v.resolver_priority = []]) {
    const settings = defaultBrollPlanSettings(); change(settings); assert.throws(() => brollPlanSettings(settings));
  }
  assert.equal(h.calls.filter(v => v.method === 'POST').length, 0);
});
test('source/transcript/role/write/dirty/current version drift blocks POST', async () => {
  for (const change of [s => s.timeline.current_version++, s => s.timeline.current_version_id = 'tvr_foreign',
    s => s.analysis.fingerprint = 'f'.repeat(64), s => s.timeline.snapshot.metadata.transcript_revision.version++,
    s => s.principal.platform_role = 'viewer', s => s.principal.human_write_enabled = false, s => s.dirty = true]) {
    const h = harness(); await h.controller.reload(); change(h.state);
    await assert.rejects(h.controller.prepare(defaultBrollPlanSettings(), true));
    assert.equal(h.calls.filter(v => v.method === 'POST').length, 0);
  }
});
test('token or role change during awaited public session fences before POST', async () => {
  let h, reads = 0;
  h = harness(async path => {if (path === '/api/v1/auth/session' && ++reads === 2) h.setToken('vf1.replaced-local-credential');});
  await h.controller.reload(); await assert.rejects(h.controller.prepare(defaultBrollPlanSettings(), true));
  assert.equal(h.calls.filter(v => v.method === 'POST').length, 0);
});
test('malformed or hash-tampered context cannot be selected', async () => {
  const h = harness(path => {if (!path.endsWith('/auth/session')) return {...copy(captured.context), context_json: captured.context.context_json + ' '};});
  await assert.rejects(h.controller.reload()); assert.equal(h.controller.state().context, null);
});
test('uncertain request survives cold load, blocks new request and reconciles exact receipt without redispatch', async () => {
  const memory = new Map();
  const h = harness((_p, options) => {if (options.method === 'POST') throw Error('fixture lost response');}, memory);
  await h.controller.reload(); await assert.rejects(h.controller.prepare(defaultBrollPlanSettings(), true));
  assert.equal(memory.size, 1); assert.equal(h.adopted.length, 0);
  assert.ok(![...memory.values()][0].includes('vf1.fixture-local-not-provider'));
  const cold = harness(undefined, memory); await assert.rejects(cold.controller.reload());
  await cold.controller.reconcile(); assert.equal(cold.adopted.length, 1); assert.equal(memory.size, 0);
  assert.equal(cold.calls.filter(v => v.method === 'POST').length, 0);
});
test('UNKNOWN read retains intent and never enables repeat/new POST', async () => {
  const memory = new Map(), unknown = {...copy(captured.response), state: 'unknown', plan: null};
  const h = harness((_p, o) => o.method === 'POST' ? unknown : undefined, memory);
  await h.controller.reload(); await h.controller.prepare(defaultBrollPlanSettings(), true);
  assert.equal(memory.size, 1); await assert.rejects(h.controller.reload()); await assert.rejects(h.controller.resend(true));
  assert.equal(h.calls.filter(v => v.method === 'POST').length, 1); assert.equal(h.adopted.length, 0);
});
test('explicit resend after scoped 404 uses identical held body only and requires fresh unchanged context', async () => {
  let posts = 0;
  const h = harness((path, o) => {if (path.includes('/requests/')) {const e = Error('missing'); e.status = 404; throw e;}
    if (o.method === 'POST' && ++posts === 1) throw Error('request did not arrive');});
  await h.controller.reload(); await assert.rejects(h.controller.prepare(defaultBrollPlanSettings(), true));
  await h.controller.reconcile(); await assert.rejects(h.controller.resend(false)); await h.controller.resend(true);
  const sent = h.calls.filter(v => v.method === 'POST'); assert.equal(sent.length, 2); assert.deepEqual(sent[0].body, sent[1].body);
});
test('storage write failure, response scope/config tamper and deletion before completion never adopt', async () => {
  for (const change of [v => v.receipt.source.source_sha256 = 'f'.repeat(64), v => v.plan.project_id = 'prj_foreign',
    v => v.plan.configuration.allow_ai_image = true, v => v.receipt.settings.resolver_priority.reverse(),
    v => v.plan.status = 'failed', v => v.plan.items = []]) {
    const h = harness((_p, o) => {if (o.method === 'POST') {const v = copy(captured.response); change(v); return v;}});
    await h.controller.reload(); await assert.rejects(h.controller.prepare(defaultBrollPlanSettings(), true)); assert.equal(h.adopted.length, 0);
  }
  const h = harness((_p, o, {memory}) => {if (o.method === 'POST') memory.clear();});
  await h.controller.reload(); await assert.rejects(h.controller.prepare(defaultBrollPlanSettings(), true)); assert.equal(h.adopted.length, 0);
});
test('expiry and dispose prevent further reads or writes', async () => {
  const h = harness(); h.setNow(Date.parse(h.state.principal.expires_at)); await assert.rejects(h.controller.reload()); assert.equal(h.calls.length, 0);
  const disposed = harness(); disposed.controller.dispose(); await assert.rejects(disposed.controller.reload()); assert.equal(disposed.calls.length, 0);
});
test('learning selection is frozen with the read authority and cannot be silently added later', async () => {
  const h = harness(); await h.controller.reload(); h.state.learning_snapshot_id = 'lsn_explicit_selected';
  await assert.rejects(h.controller.prepare(defaultBrollPlanSettings(), true));
  assert.equal(h.calls.filter(v => v.method === 'POST').length, 0);
});
test('elapsed expiry and peer dirty at the final credential digest cannot POST', async () => {
  for (const drift of [h => h.setNow(Date.parse(h.state.principal.expires_at)), h => h.state.dirty = true]) {
    const h = harness(); await h.controller.reload(); let calls = 0;
    h.setCryptoHook(() => {if (++calls === 2) drift(h);});
    await assert.rejects(h.controller.prepare(defaultBrollPlanSettings(), true));
    assert.equal(h.calls.filter(v => v.method === 'POST').length, 0); assert.equal(h.adopted.length, 0);
  }
});
test('foreign pending slot arriving during final digest is preserved without overwrite or POST', async () => {
  const h = harness(); await h.controller.reload(); let calls = 0;
  const foreign = JSON.stringify({foreign: 'existing owned request B'});
  h.setCryptoHook(() => {if (++calls === 2) h.memory.set('vf-broll-plan-pending-v1:' + JSON.stringify([
    h.state.workspaceId, h.state.projectId, h.state.principal.subject]), foreign);});
  await assert.rejects(h.controller.prepare(defaultBrollPlanSettings(), true));
  assert.deepEqual([...h.memory.values()], [foreign]); assert.equal(h.calls.filter(v => v.method === 'POST').length, 0);
});
test('last storage read changing project cannot adopt or remove a different scope request', async () => {
  let afterPost = false, reads = 0;
  const h = harness((_p, o) => {if (o.method === 'POST') afterPost = true;});
  await h.controller.reload(); const get = h.storage.getItem;
  const foreignKey = 'foreign-scope-record', foreign = 'keep foreign scope bytes';
  h.storage.getItem = key => {
    const raw = get(key);
    if (afterPost && ++reads === 2) {h.state.projectId = 'prj_another_scope'; h.memory.set(foreignKey, foreign);}
    return raw;
  };
  await assert.rejects(h.controller.prepare(defaultBrollPlanSettings(), true));
  assert.equal(h.adopted.length, 0); assert.equal(h.memory.get(foreignKey), foreign); assert.equal(h.memory.size, 2);
});
test('foreign slot during resend context GET is retained and blocks the second POST', async () => {
  let h, posts = 0, resending = false, foreignRaw, key;
  h = harness((path, o) => {
    if (path.includes('/requests/')) throw Object.assign(Error('scoped missing'), {status: 404});
    if (o.method === 'POST' && ++posts === 1) throw Error('request did not arrive');
    if (resending && path.endsWith('/broll-plan-review') && o.method !== 'POST') {
      key = [...h.memory.keys()][0]; const foreign = JSON.parse(h.memory.get(key));
      foreign.body.request_key = 'foreign-broll-request-B'; foreignRaw = JSON.stringify(foreign); h.memory.set(key, foreignRaw);
    }
  });
  await h.controller.reload(); await assert.rejects(h.controller.prepare(defaultBrollPlanSettings(), true));
  await h.controller.reconcile(); resending = true; await assert.rejects(h.controller.resend(true));
  assert.equal(posts, 1); assert.equal(h.memory.get(key), foreignRaw); assert.equal(h.adopted.length, 0);
});
test('observed UNKNOWN revokes an earlier 404 resend permission', async () => {
  let posts = 0, reads = 0; const unknown = {...copy(captured.response), state: 'unknown', plan: null};
  const h = harness((path, o) => {
    if (path.includes('/requests/')) {if (++reads === 1) throw Object.assign(Error('scoped missing'), {status: 404}); return unknown;}
    if (o.method === 'POST') {posts++; throw Error('lost response');}
  });
  await h.controller.reload(); await assert.rejects(h.controller.prepare(defaultBrollPlanSettings(), true));
  await h.controller.reconcile(); assert.equal(h.controller.state().mayResend, true);
  await h.controller.reconcile(); assert.equal(h.controller.state().mayResend, false);
  await assert.rejects(h.controller.resend(true)); assert.equal(posts, 1); assert.equal(h.adopted.length, 0);
});
