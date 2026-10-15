import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
import {initializeSqlBrollInternalResolution, validateBrollInternalContext} from '../sql-broll-internal-resolution.mjs';

const fixture = JSON.parse(readFileSync(new URL('./fixtures/sql-broll-internal-resolution.json', import.meta.url)));
const copy = structuredClone;
const raw = name => copy(fixture.records.find(x => x.name === name).response.json);
function harness({memory = new Map(), transport, onResolved, onRead} = {}) {
  const state = copy(fixture.state_projection), calls = [], received = [], messages = [];
  let token = 'vf1.local-only-controller-fixture', now = fixture.clock_ms, hashHook = null, getHook = null;
  const storage = {getItem(k) {const value = memory.get(k) ?? null; getHook?.(k, value); return value;},
    setItem: (k, v) => memory.set(k, v), compareAndRemoveItem(k, value) {
      if (memory.get(k) !== value) return false; memory.delete(k); return true;
    }};
  const api = async (path, options = {}) => {
    const call = {path, method: options.method ?? 'GET', body: options.body ? JSON.parse(options.body) : null}; calls.push(call);
    const value = await transport?.(call, {state, calls, memory}); if (value !== undefined) return value;
    if (path === '/api/v1/auth/session') return raw('session');
    if (options.method === 'POST') return raw('admitted');
    return raw(path.includes('/requests/') ? 'poll-resolved' : 'review-context');
  };
  const controller = initializeSqlBrollInternalResolution({api, getState: () => state, getSessionToken: () => token,
    storage, clock: () => now, newRequestKey: () => raw('admitted').receipt.request_key,
    cryptoImpl: {subtle: {digest: async (...args) => {const value = await webcrypto.subtle.digest(...args); hashHook?.(); return value;}}},
    onResolved: async (value, guard) => {received.push(value); return onResolved ? await onResolved(value, guard) : true;},
    onRead, onStatus: v => messages.push(v)});
  return {controller, state, calls, received, memory, storage, messages, setToken: x => token = x,
    setNow: x => now = x, setHashHook: x => hashHook = x, setGetHook: x => getHook = x};
}
const selected = () => raw('admitted').receipt.asset_id;
async function queued(h) {await h.controller.reload(); return h.controller.admit(selected(), true);}

test('frozen actual ASGI fixture and constructor do no API/storage mutation', () => {
  assert.match(fixture.scope, /Actual in-process main\/SQLite\/Local/);
  assert.match(fixture.ui_projection_notice, /not extra HTTP response/);
  assert.equal(fixture.checks.external_network_attempts, 0);
  const h = harness(); assert.equal(validateBrollInternalContext(raw('review-context'), h.state, fixture.clock_ms).schema_version,
    'broll-internal-resolution-context.v1'); assert.deepEqual(h.calls, []); assert.equal(h.memory.size, 0);
});
test('explicit context/read/admit/exact observation keeps one request and never changes canonical timeline', async () => {
  const h = harness(), timeline = copy(h.state.timeline); await queued(h);
  assert.equal(h.calls.filter(x => x.method === 'POST').length, 1); assert.equal(h.memory.size, 1);
  assert.equal(h.received.length, 0); assert.equal(h.controller.state().observation.state, 'queued');
  const value = await h.controller.observe(); assert.deepEqual(value, raw('poll-resolved'));
  assert.equal(h.received.length, 1); assert.equal(h.memory.size, 0); assert.deepEqual(h.state.timeline, timeline);
  const poll = h.calls.find(x => x.path.includes('/requests/'));
  assert.ok(poll.path.endsWith(`/requests/${raw('admitted').receipt.request_key}/jobs/${raw('admitted').receipt.resolution_job_id}`));
  assert.equal(h.calls.filter(x => x.method === 'POST').length, 1);
});
test('lost HTTP response preserves exact original intent; cold mount/read never sends POST; explicit retry uses same body', async () => {
  const memory = new Map();
  const h = harness({memory, transport: c => {if (c.method === 'POST') throw Error('owned lost HTTP acknowledgement');}});
  await assert.rejects(queued(h)); const kept = [...memory.values()][0];
  assert.ok(!kept.includes('vf1.local-only-controller-fixture'));
  const cold = harness({memory}); cold.state.internalResolutionDraft = null; await cold.controller.reload();
  assert.ok(cold.calls.every(x => x.method === 'GET')); await assert.rejects(cold.controller.observe());
  await assert.rejects(cold.controller.retry(false)); await cold.controller.retry(true);
  assert.deepEqual(cold.calls.find(x => x.method === 'POST').body, h.calls.find(x => x.method === 'POST').body);
  await cold.controller.observe(); assert.equal(cold.received.length, 1); assert.equal(memory.size, 0);
});
test('known queued job restores cold and reads only exact original job, with no handoff', async () => {
  const memory = new Map(), h = harness({memory}); await queued(h); const cold = harness({memory});
  await cold.controller.observe(); assert.equal(cold.received.length, 1); assert.ok(cold.calls.every(x => x.method === 'GET'));
});
test('failed handoff is retained; only explicit retry replays original saved key/body', async () => {
  const h = harness({transport: c => c.method === 'POST' ? {...raw('admitted'), handoff: 'handoff_pending'} : undefined});
  await queued(h); const before = h.calls.length; h.controller.sync(); h.controller.state(); assert.equal(h.calls.length, before);
  await h.controller.retry(true); const posts = h.calls.filter(x => x.method === 'POST'); assert.equal(posts.length, 2);
  assert.deepEqual(posts[0].body, posts[1].body); assert.equal(h.memory.size, 1);
});
test('missing acknowledgement/noncandidate/disabled write/viewer/new intent while held produce no new POST', async () => {
  const h = harness(); await h.controller.reload();
  await assert.rejects(h.controller.admit(selected(), false)); await assert.rejects(h.controller.admit('ast_foreign_asset', true));
  h.state.principal.human_write_enabled = false; await assert.rejects(h.controller.admit(selected(), true));
  assert.equal(h.calls.filter(x => x.method === 'POST').length, 0);
  const own = harness(); await queued(own); await assert.rejects(own.controller.admit(selected(), true));
  assert.equal(own.calls.filter(x => x.method === 'POST').length, 1);
});
test('Python numeric hashes stay opaque inside literal canonical JSON; tampered projection/literal is rejected', async () => {
  const h = harness(); await h.controller.reload();
  for (const mutate of [v => v.context_json += ' ', v => v.source_asset_custody.storage_provider = 's3',
    v => v.candidates[0].candidate.rights_status = 'licensed', v => v.plan.configuration_json.allow_ai_image = true]) {
    const bad = harness({transport: c => {if (c.path.endsWith('internal-resolution-review')) {const v = raw('review-context'); mutate(v); return v;}}});
    await assert.rejects(bad.controller.reload()); assert.equal(bad.controller.state().context, null);
  }
});
test('full local source/asset/form/plan drift after review prevents all admission writes', async () => {
  for (const mutate of [s => s.assets[1].storage_provider = 's3', s => s.assets[1].version++, s => s.assets[1].size_bytes++,
    s => s.assets[1].provenance.rights_status = 'restricted', s => s.analysis.fingerprint = 'f'.repeat(64),
    s => s.timeline.current_version++,
    s => s.mediaPlans[0].items[0].description += ' changed', s => s.dirty = true]) {
    const h = harness(); await h.controller.reload(); mutate(h.state); await assert.rejects(h.controller.admit(selected(), true));
    assert.equal(h.calls.filter(x => x.method === 'POST').length, 0);
  }
});
test('authority/source/form drift during awaited session/context/hash never dispatches POST', async () => {
  for (const stage of ['session', 'context', 'hash', 'form']) {
    let h, armed = false;
    h = harness({transport: c => {if (armed && (stage === 'session' && c.path.endsWith('/auth/session')
      || stage === 'context' && c.path.endsWith('internal-resolution-review'))) h.state.assets[1].provenance.changed = true;}});
    await h.controller.reload(); armed = true;
    if (stage === 'hash' || stage === 'form') h.setHashHook(() => {h.setHashHook(null);
      if (stage === 'hash') h.state.principal.expires_at = new Date(fixture.clock_ms - 1).toISOString();
      else h.state.internalResolutionDraft.asset_id = 'ast_another_selection';});
    await assert.rejects(h.controller.admit(selected(), true)); assert.equal(h.calls.filter(x => x.method === 'POST').length, 0);
  }
});
test('replacement and deletion of exact stored intent during POST or poll never adopt/remove foreign data', async () => {
  for (const phase of ['post', 'poll']) {
    let h, armed = false;
    h = harness({transport: c => {if (armed && (phase === 'post' && c.method === 'POST' || phase === 'poll' && c.path.includes('/requests/')))
      {const k = [...h.memory.keys()][0]; h.memory.set(k, 'foreign-intent-B');}}});
    if (phase === 'post') {await h.controller.reload(); armed = true; await assert.rejects(h.controller.admit(selected(), true));}
    else {await queued(h); armed = true; await assert.rejects(h.controller.observe());}
    assert.equal(h.received.length, 0); assert.equal([...h.memory.values()][0], 'foreign-intent-B');
  }
});
test('strict exact job/receipt/marker/flags prevent borrowing a foreign or external resolution', async () => {
  for (const mutate of [v => v.receipt.asset_id = 'ast_foreign_candidate', v => v.job.resolution_job_id = 'mrj_foreign_job',
    v => v.job.paid = true, v => v.job.external_call = true, v => v.job.provenance.reviewed_internal_resolution_v1.binding_sha256 = 'f'.repeat(64),
    v => v.receipt.actor_ref = 'usr:another', v => v.receipt.request_key = 'foreign-key-0001', v => v.owner_approval_inferred = true]) {
    const h = harness({transport: c => {if (c.path.includes('/requests/')) {const v = raw('poll-resolved'); mutate(v); return v;}}});
    await queued(h); await assert.rejects(h.controller.observe()); assert.equal(h.received.length, 0); assert.equal(h.memory.size, 1);
  }
});
test('stale resolved/failed/running observations remain read-only and retained without adoption or new POST', async () => {
  for (const name of ['poll-stale-custody', 'failed', 'running']) {
    const value = name === 'poll-stale-custody' ? raw(name) : {...raw('poll-queued'), state: name === 'running' ? 'unknown' : 'failed',
      job: {...raw('poll-queued').job, status: name}, needs_attention: true};
    const h = harness({transport: c => c.path.includes('/requests/') ? value : undefined}); await queued(h); await h.controller.observe();
    assert.equal(h.received.length, 0); assert.equal(h.memory.size, 1); assert.equal(h.calls.filter(x => x.method === 'POST').length, 1);
  }
});
test('private synchronous callback guard is revoked, and foreign replacement while callback awaits blocks settlement', async () => {
  let escaped, h;
  h = harness({onResolved: async (_v, guard) => {escaped = guard; assert.equal(guard(), true);
    await Promise.resolve(); h.memory.set([...h.memory.keys()][0], 'foreign-intent-B'); return true;}});
  await queued(h); await assert.rejects(h.controller.observe()); assert.throws(() => escaped());
  assert.equal([...h.memory.values()][0], 'foreign-intent-B');
});
test('callback must return literal true, and unrelated plan/timeline/source changes cannot settle', async () => {
  for (const change of [() => undefined, () => false, () => ({}), s => {s.mediaPlans[0].items[1].description += ' foreign'; return true;},
    s => {s.timeline.current_version++; return true;}, s => {s.assets[1].provenance.changed = true; return true;}]) {
    let h; h = harness({onResolved: async () => change(h.state)}); await queued(h); await assert.rejects(h.controller.observe());
    assert.equal(h.memory.size, 1);
  }
});
test('final awaited digest and final storage getter source/authority/selection drift retain exact intent', async () => {
  for (const stage of ['hash', 'get']) {
    let h; h = harness({onResolved: async () => {
      if (stage === 'hash') h.setHashHook(() => {h.setHashHook(null); h.state.assets[1].version++;});
      else h.setGetHook(() => {h.setGetHook(null); h.state.mediaPlanItemId = 'mpi_foreign_item';});
      return true;
    }});
    await queued(h); await assert.rejects(h.controller.observe()); assert.equal(h.memory.size, 1);
  }
});
test('stored whitespace is preserved exactly and token/project changes cannot reclaim or clear old intent', async () => {
  const memory = new Map(), h = harness({memory}); await queued(h);
  const [k, value] = [...memory.entries()][0]; memory.set(k, ' \n' + value + '\n'); const cold = harness({memory});
  await cold.controller.observe(); assert.equal(memory.size, 0);
  const old = harness(); await queued(old); old.setToken('vf1.changed-credential');
  await assert.rejects(old.controller.observe()); assert.equal(old.memory.size, 1);
});
test('no trusted compare-remove, corrupted durable record or expired credential never clears held record', async () => {
  const h = harness(); await queued(h); delete h.storage.compareAndRemoveItem;
  await assert.rejects(h.controller.observe()); assert.equal(h.memory.size, 1);
  const cold = harness({memory: new Map([['vf-sql-broll-internal-pending-v1:' + JSON.stringify([
    h.state.workspaceId, h.state.projectId, h.state.principal.subject]) , 'broken intent']])});
  await assert.rejects(cold.controller.reload()); assert.equal(cold.memory.size, 1);
  const expired = harness(); await queued(expired); expired.setNow(Date.parse(expired.state.principal.expires_at) + 1);
  await assert.rejects(expired.controller.observe()); assert.equal(expired.memory.size, 1);
});
test('read callback guard also proves held raw and cannot escape its lifetime', async () => {
  const memory = new Map(), first = harness({memory}); await queued(first); let guard;
  const cold = harness({memory, onRead: async (_v, g) => {guard = g; assert.equal(g(), true);}});
  await cold.controller.reload(); assert.throws(() => guard()); assert.equal(memory.size, 1);
});
test('inconsistent states/late public job output/rights evidence are rejected without losing original intent', async () => {
  for (const mutate of [v => {v.state = 'failed'; v.job.status = 'succeeded'; v.can_adopt = false; v.output = null;},
    v => v.output.rights_status = 'licensed', v => v.output.width++, v => v.job.output_media_asset_id = 'mas_foreign_output',
    v => {v.output.publishing_allowed = true; v.output.production_eligible = true;},
    v => {v.state = 'queued'; v.can_adopt = false; v.output = null;}]) {
    const h = harness({transport: c => {if (c.path.includes('/requests/')) {const v = raw('poll-resolved'); mutate(v); return v;}}});
    await queued(h); await assert.rejects(h.controller.observe()); assert.equal(h.received.length, 0); assert.equal(h.memory.size, 1);
  }
});
test('unchanged sync preserves a reviewed read; disposed/expired/read-only sessions cannot create jobs', async () => {
  const h = harness(); await h.controller.reload(); h.controller.sync(); await h.controller.admit(selected(), true);
  const viewer = harness(); viewer.state.principal.platform_role = 'viewer'; viewer.state.principal.workspace_roles = {'*': 'viewer'};
  await assert.rejects(viewer.controller.admit(selected(), true)); assert.equal(viewer.calls.length, 0);
  const disposed = harness(); await disposed.controller.reload(); disposed.controller.dispose();
  await assert.rejects(disposed.controller.admit(selected(), true)); assert.equal(disposed.calls.filter(c => c.method === 'POST').length, 0);
});
test('concurrent button calls cannot create a second admission while one awaits transport', async () => {
  let release; const held = new Promise(resolve => {release = resolve;});
  const h = harness({transport: async c => {if (c.method === 'POST') await held;}}); await h.controller.reload();
  const first = h.controller.admit(selected(), true); await new Promise(resolve => setTimeout(resolve, 15));
  await assert.rejects(h.controller.admit(selected(), true)); release(); await first;
  assert.equal(h.calls.filter(c => c.method === 'POST').length, 1);
});
test('native getter authority drift after returning exact owned raw still prevents POST and adoption', async () => {
  for (const operation of ['retry', 'observe']) {
    const h = harness(); await queued(h); let gets = 0;
    h.setGetHook((_k, value) => {if (typeof value === 'string' && ++gets === 2) h.setToken('vf1.replaced-under-storage-read');});
    if (operation === 'retry') await assert.rejects(h.controller.retry(true)); else await assert.rejects(h.controller.observe());
    assert.equal(h.calls.filter(c => c.method === 'POST').length, 1); assert.equal(h.received.length, 0); assert.equal(h.memory.size, 1);
  }
});
test('owned callback may install only matching resolved item fields, while final raw foreign replacement is retained', async () => {
  let h;
  h = harness({onResolved: async v => {const item = h.state.mediaPlans[0].items.find(i => i.media_plan_item_id === v.receipt.media_plan_item_id);
    item.status = 'resolved'; item.selected_media_asset_id = v.job.output_media_asset_id; item.needs_attention = true;
    item.updated_at = v.job.updated_at; return true;}});
  await queued(h); await h.controller.observe(); assert.equal(h.memory.size, 0);
  let bad;
  bad = harness({onResolved: async () => {bad.setHashHook(() => {bad.setHashHook(null); bad.memory.set([...bad.memory.keys()][0], 'late-B');}); return true;}});
  await queued(bad); await assert.rejects(bad.controller.observe()); assert.equal([...bad.memory.values()][0], 'late-B');
});
test('user may choose and acknowledge a candidate after reading; selection is captured before admission awaits', async () => {
  const h = harness(); h.state.internalResolutionDraft = {asset_id: null, acknowledged: false};
  await h.controller.reload(); h.state.internalResolutionDraft = {asset_id: selected(), acknowledged: true};
  h.controller.sync(); await h.controller.admit(selected(), true);
  assert.equal(h.calls.filter(c => c.method === 'POST').length, 1);
});
