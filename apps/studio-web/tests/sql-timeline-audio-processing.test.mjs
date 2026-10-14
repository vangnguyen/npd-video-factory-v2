import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash, webcrypto} from 'node:crypto';
import {audioProcessingConfiguration, audioProcessingRead, initializeSqlTimelineAudioProcessing} from '../sql-timeline-audio-processing.mjs';

// EXPLICIT UI CONTRACT fixtures wrap a preserved TimelineRead. ProcessingRead,
// receipts, transports and token strings are mocked; no SQL/API/DSP acceptance.
const fixture = JSON.parse(readFileSync(new URL('./fixtures/sql-video-word-review/asgi.json', import.meta.url)));
const clone = structuredClone;
const defaults = {normalize_original_audio: false, normalize_music: false, duck_music: false,
  original_target_lufs: -16, music_target_lufs: -24, duck_threshold: .02, duck_ratio: 8, duck_attack_ms: 20, duck_release_ms: 250};
function state(role = 'editor') {
  const t = clone(fixture.responses.timeline_before.body);
  return {workspaceId: t.workspace_id, projectId: t.project_id, timeline: t, busy: false, dirty: false,
    principal: {subject: fixture.context.actor_ref, display_name: 'Explicit public DTO fixture', platform_role: null,
      workspace_roles: {[t.workspace_id]: role}, expires_at: '2100-01-01T00:00:00Z', human_write_enabled: true}};
}
function data(s) {return {timeline: clone(s.timeline), configuration: clone(s.timeline.snapshot.metadata.source_audio_processing ?? defaults),
  locked_audio_track_ids: s.timeline.snapshot.tracks.filter(t => t.type === 'audio' && t.locked).map(t => t.track_id).sort(), receipt: null, replayed: false};}
function result(s, body) {
  const value = data(s); value.timeline.current_version = body.expected_version + 1; value.timeline.current_version_id = 'tlv_explicit_processing_result';
  value.timeline.snapshot.metadata.source_audio_processing = clone(body.configuration); value.configuration = clone(body.configuration);
  value.timeline.approval_status = 'draft'; value.timeline.approved_timeline_version = null; value.timeline.latest_preview_valid = false;
  value.receipt = {schema_version: 'source-audio-processing-v1', request_key: body.request_key, request_sha256: 'a'.repeat(64),
    workspace_id: s.workspaceId, project_id: s.projectId, timeline_id: value.timeline.timeline_id,
    parent_version: body.expected_version, result_version: body.expected_version + 1, actor_ref: s.principal.subject, configuration: clone(body.configuration)};
  return value;
}
function harness({s = state(), handler, storage, crypto, onSaved, onBusyChanged, getSessionToken} = {}) {
  class Element {
    constructor(tag) {this.tagName = tag; this.children = []; this.attributes = {}; this.listeners = {}; this.value = ''; this.checked = false; this.disabled = false; this.textContent = '';}
    append(...items) {this.children.push(...items);} setAttribute(k, v) {this.attributes[k] = String(v);}
    addEventListener(k, fn) {this.listeners[k] = fn;}
  }
  const dom = {createElement: tag => new Element(tag)}, root = dom.createElement('section'), all = e => [e, ...e.children.flatMap(all)];
  const get = name => all(root).find(e => Object.hasOwn(e.attributes, 'data-audio-processing-' + name));
  const calls = [], memory = new Map(), saved = [], messages = []; let token = 'EXPLICIT_TRANSIENT_NOT_AUTHENTICATED', response = data(s);
  const api = async (path, options) => {const call = {path, method: options?.method ?? 'GET', body: options?.body ? JSON.parse(options.body) : null}; calls.push(call);
    const tools = {result: body => result(s, body), setResponse: value => {response = clone(value);}};
    if (handler) return handler(call, tools);
    if (call.method === 'PUT') response = result(s, call.body); return clone(response);
  };
  const controller = initializeSqlTimelineAudioProcessing({root, api, dom, getState: () => s,
    getSessionToken: getSessionToken ?? (() => token), cryptoImpl: crypto ?? {subtle: webcrypto.subtle, randomUUID: () => 'explicit-processing-intent-0001'},
    storage: storage ?? {getItem: k => memory.get(k) ?? null, setItem: (k, v) => memory.set(k, v),
      compareAndRemoveItem: (k, raw) => {if (memory.get(k) !== raw) return false; memory.delete(k); return true;}},
    onMessage: (...value) => messages.push(value), onBusyChanged: () => {if (onBusyChanged) onBusyChanged();},
    onSaved: async value => {saved.push(value); if (onSaved) return onSaved(value, s); s.timeline = clone(value.timeline);}});
  const edit = (name = 'duck_threshold', value = '0.025') => {const input = get(name); if (input.type === 'checkbox') input.checked = value;
    else input.value = value; input.listeners[input.type === 'checkbox' ? 'change' : 'input'](); get('ack').checked = true; get('ack').listeners.change();};
  return {s, controller, get, calls, saved, memory, messages, edit, setToken: value => {token = value;}, click: name => get(name).listeners.click()};
}

test('mount/sync perform zero calls; explicit GET loads exact server off defaults and .02 without token_id', async () => {
  const h = harness(); h.controller.sync(); assert.equal(h.calls.length, 0); assert.equal(h.get('duck_threshold').value, '');
  await h.click('read'); assert.equal(h.calls.length, 1); assert.equal(h.get('duck_threshold').value, '0.02');
  assert.equal(h.get('normalize_music').checked, false); assert.equal(h.get('duck_music').checked, false);
  assert.equal(Object.hasOwn(h.s.principal, 'token_id'), false); assert.equal(h.get('save').disabled, true);
});
test('explicit save binds current canonical IDs/config, updates through callback and performs no automatic extra GET', async () => {
  const h = harness(), source = clone(h.s.timeline.snapshot.tracks); await h.click('read'); h.edit(); await h.click('save');
  const writes = h.calls.filter(c => c.method === 'PUT'); assert.equal(writes.length, 1); assert.equal(h.calls.length, 2);
  assert.deepEqual(Object.keys(writes[0].body).sort(), ['acknowledged', 'configuration', 'expected_timeline_id', 'expected_version', 'request_key']);
  assert.equal(writes[0].body.expected_version, 1); assert.equal(writes[0].body.configuration.duck_threshold, .025);
  assert.equal(h.s.timeline.current_version, 2); assert.deepEqual(h.s.timeline.snapshot.tracks, source);
  assert.equal(h.saved.length, 1); assert.equal(h.memory.size, 0); assert.equal(h.controller.isPending(), false);
  assert.match(h.get('status').textContent, /chưa nghiệm thu/);
});
test('viewer reads but cannot save; write switch, expiry, role, blank token and peer drafts close admission', async () => {
  const viewer = harness({s: state('viewer')}); await viewer.click('read'); assert.equal(viewer.calls.length, 1);
  assert.equal(viewer.get('duck_threshold').disabled, true); await viewer.click('save'); assert.equal(viewer.calls.length, 1);
  const off = state(); off.principal.human_write_enabled = false; const readOnly = harness({s: off});
  await readOnly.click('read'); readOnly.edit(); await readOnly.click('save'); assert.equal(readOnly.calls.length, 1);
  for (const change of [s => {s.principal.expires_at = '2000-01-01T00:00:00Z';}, s => {s.principal.workspace_roles = {};},
    s => {s.principal.subject = '';}, s => {s.busy = true;}, s => {s.dirty = true;}]) {
    const s = state(); change(s); const h = harness({s}); await h.click('read'); assert.equal(h.calls.length, 0);
  }
  const empty = harness({getSessionToken: () => ''}); await empty.click('read'); assert.equal(empty.calls.length, 0);
});
test('numeric inputs never coerce blanks, whitespace, nonfinite or out-of-range values and booleans stay strict', async () => {
  for (const value of ['', ' .02', 'NaN', 'Infinity', '0x10', '1e999', '.0001', '.3']) {
    const h = harness(); await h.click('read'); h.edit('duck_threshold', value); await h.click('save');
    assert.equal(h.calls.some(c => c.method === 'PUT'), false); assert.equal(h.memory.size, 0);
  }
  assert.throws(() => audioProcessingConfiguration({...defaults, duck_music: 'false'}));
  assert.throws(() => audioProcessingConfiguration({...defaults, unexpected: true}));
});
test('missing/malformed/foreign read data never falls back to editable defaults', async () => {
  for (const change of [d => {delete d.configuration;}, d => {d.configuration.duck_threshold = '0.02';},
    d => {d.timeline.project_id = 'prj_foreign_fixture';}, d => {d.timeline.current_version++;},
    d => {d.locked_audio_track_ids = ['track_foreign'];}]) {
    const s = state(), value = data(s); change(value); const h = harness({s, handler: () => value});
    await h.click('read'); assert.equal(h.get('duck_threshold').value, ''); assert.equal(h.get('save').disabled, true);
  }
  const absent = harness({handler: () => {throw Object.assign(Error('NOT_CONFIGURED'), {status: 503});}});
  await absent.click('read'); assert.equal(absent.get('save').disabled, true); assert.match(absent.get('status').textContent, /Không đọc/);
});
test('locked audio tracks remain reviewable but never produce a write', async () => {
  const s = state(); const audio = s.timeline.snapshot.tracks.find(t => t.type === 'audio'); assert.ok(audio); audio.locked = true;
  const h = harness({s}); await h.click('read'); h.edit(); await h.click('save'); assert.equal(h.calls.length, 1);
  assert.match(h.get('summary').textContent, /bị khóa/);
});
test('POST-equivalent PUT response loss after commit reconciles only the exact current receipt with zero repeat write', async () => {
  const h = harness({handler: (c, tools) => {if (c.method === 'PUT') {tools.setResponse(tools.result(c.body)); throw Error('explicit response lost');}
    return c.method === 'GET' && h.calls.length > 2 ? result(h.s, h.calls.find(c => c.method === 'PUT').body) : data(h.s);}});
  await h.click('read'); h.edit(); await h.click('save'); const raw = [...h.memory.values()][0];
  assert.equal(h.controller.isPending(), true); assert.equal(JSON.parse(raw).body.expected_version, 1);
  await h.click('reconcile'); assert.equal(h.memory.size, 0); assert.equal(h.calls.filter(c => c.method === 'PUT').length, 1);
  assert.equal(h.s.timeline.current_version, 2);
});
test('uncommitted UNKNOWN permits only exact same key/body after explicit old configuration/source proof', async () => {
  let attempt = 0; const h = harness({handler: (c, tools) => {if (c.method === 'PUT') {if (++attempt === 1) throw Error('no commit fixture'); return tools.result(c.body);} return data(h.s);}});
  await h.click('read'); h.edit(); await h.click('save'); await h.click('retry'); assert.equal(attempt, 1);
  await h.click('reconcile'); await h.click('retry'); const puts = h.calls.filter(c => c.method === 'PUT');
  assert.equal(puts.length, 2); assert.deepEqual(puts[0].body, puts[1].body); assert.equal(h.memory.size, 0);
});
test('canonical/source drift after old-parent reconciliation never sends even the frozen request', async () => {
  for (const mutate of [s => {s.timeline.current_version++;}, s => {s.timeline.snapshot.duration_seconds += 1;}]) {
    const h = harness({handler: c => {if (c.method === 'PUT') throw Error('no commit'); return data(h.s);}});
    await h.click('read'); h.edit(); await h.click('save'); await h.click('reconcile'); mutate(h.s); await h.click('retry');
    assert.equal(h.calls.filter(c => c.method === 'PUT').length, 1); assert.equal(h.memory.size, 1);
  }
});
test('missing/unrelated/foreign receipt or newer result never clears UNKNOWN or guesses configuration as proof', async () => {
  for (const mutation of ['missing', 'key', 'actor', 'version', 'source', 'configuration', 'digest']) {
    let savedBody; const h = harness({handler: (c, tools) => {if (c.method === 'PUT') {savedBody = c.body; throw Error('explicit UNKNOWN');}
      if (!savedBody) return data(h.s); const d = tools.result(savedBody);
      if (mutation === 'missing') d.receipt = null;
      if (mutation === 'key') d.receipt.request_key = 'sap_foreign_fixture_key';
      if (mutation === 'actor') d.receipt.actor_ref = 'usr:foreign-fixture';
      if (mutation === 'version') {d.timeline.current_version++; d.receipt.parent_version++; d.receipt.result_version++;}
      if (mutation === 'source') d.timeline.snapshot.duration_seconds += 1;
      if (mutation === 'configuration') d.configuration.duck_threshold = .05;
      if (mutation === 'digest') d.receipt.request_sha256 = 'malformed'; return d;}});
    await h.click('read'); h.edit(); await h.click('save'); const raw = [...h.memory.values()][0]; await h.click('reconcile');
    assert.equal(h.memory.size, 1); assert.equal([...h.memory.values()][0], raw); assert.equal(h.saved.length, 0);
  }
});
test('callback failure retains exact intent and pins observed opaque receipt digest for later read', async () => {
  let current; const h = harness({handler: (c, tools) => {if (c.method === 'PUT') {current = tools.result(c.body); return current;} return current ?? data(h.s);},
    onSaved: () => {throw Error('explicit callback unavailable');}});
  await h.click('read'); h.edit(); await h.click('save'); const raw = [...h.memory.values()][0];
  assert.equal(h.saved.length, 1); current.receipt.request_sha256 = 'b'.repeat(64); await h.click('reconcile');
  assert.equal(h.saved.length, 1); assert.equal([...h.memory.values()][0], raw); assert.equal(h.controller.isPending(), true);
});
test('same-session restore retains exact request while refreshed or malformed/foreign records gate before GET', async () => {
  const seed = harness({handler: c => {if (c.method === 'PUT') throw Error('UNKNOWN'); return data(seed.s);}});
  await seed.click('read'); seed.edit(); await seed.click('save'); const entry = [...seed.memory.entries()][0];
  const memory = new Map([entry]), storage = {getItem: k => memory.get(k) ?? null, setItem: (k, v) => memory.set(k, v),
    compareAndRemoveItem: (k, raw) => {if (memory.get(k) !== raw) return false; memory.delete(k); return true;}};
  const restored = harness({storage}); await restored.click('read'); await restored.click('reconcile'); await restored.click('retry');
  assert.deepEqual(restored.calls.find(c => c.method === 'PUT').body, seed.calls.find(c => c.method === 'PUT').body); assert.equal(memory.size, 0);
  for (const raw of [entry[1], '{malformed', JSON.stringify({...JSON.parse(entry[1]), actor_ref: 'usr:foreign'})]) {
    const foreign = new Map([[entry[0], raw]]); const h = harness({getSessionToken: () => 'CHANGED_RAW_TOKEN',
      storage: {getItem: k => foreign.get(k) ?? null, setItem: () => {throw Error('no overwrite');}}});
    await h.click('read'); await h.click('save'); assert.equal(h.calls.length, 0); assert.equal(h.controller.isPending(), true);
    assert.equal(foreign.get(entry[0]), raw);
  }
});
test('literal token is absent from persisted record; expiry/token changes during GET/hash/callback close authority', async () => {
  let h; h = harness({handler: () => {h.setToken('changed-get'); return data(h.s);}}); await h.click('read'); assert.equal(h.get('duck_threshold').value, '');
  let digests = 0, hashed; hashed = harness({crypto: {randomUUID: () => 'hash-fixture-key', subtle: {digest: async (...args) => {
    if (++digests === 2) hashed.setToken('changed-submit-hash'); return webcrypto.subtle.digest(...args);}}}});
  await hashed.click('read'); hashed.edit(); await hashed.click('save'); assert.equal(hashed.calls.some(c => c.method === 'PUT'), false);
  let callback; callback = harness({onSaved: () => callback.setToken('changed-callback')});
  await callback.click('read'); callback.edit(); await callback.click('save'); const raw = [...callback.memory.values()][0];
  assert.equal(raw.includes('EXPLICIT_TRANSIENT_NOT_AUTHENTICATED'), false);
  assert.equal(JSON.parse(raw).session_sha256, createHash('sha256').update('EXPLICIT_TRANSIENT_NOT_AUTHENTICATED').digest('hex'));
  assert.equal(callback.controller.isPending(), true);
  const expired = harness(); await expired.click('read'); expired.edit(); expired.s.principal.expires_at = '2000-01-01T00:00:00Z';
  await expired.click('save'); assert.equal(expired.calls.length, 1);
});
test('last storage readback callback cannot dispatch after token/canonical drift and never deletes foreign replacement', async () => {
  for (const mutation of ['token', 'canonical']) {
    const memory = new Map(); let h, armed = false;
    h = harness({storage: {setItem: (k, v) => {memory.set(k, v); armed = true;}, getItem: k => {
      const raw = memory.get(k) ?? null; if (armed && raw !== null) {armed = false;
        if (mutation === 'token') h.setToken('final-readback-token'); else h.s.timeline.current_version++;} return raw;}}});
    await h.click('read'); h.edit(); await h.click('save'); assert.equal(h.calls.some(c => c.method === 'PUT'), false); assert.equal(memory.size, 1);
  }
  const memory = new Map(), foreign = '{foreign UNKNOWN}'; let armed = false, removed = 0;
  const h = harness({storage: {setItem: (k, v) => memory.set(k, v), getItem: k => {const raw = memory.get(k) ?? null;
    if (armed && raw !== null) {armed = false; memory.set(k, foreign);} return raw;}, removeItem: () => {removed++;}},
    onSaved: (value, s) => {s.timeline = clone(value.timeline); armed = true;}});
  await h.click('read'); h.edit(); await h.click('save'); assert.equal([...memory.values()][0], foreign);
  assert.equal(removed, 0); assert.equal(h.controller.isPending(), true);
});
test('storage unavailable or persistence failure never writes; dispose keeps durable UNKNOWN', async () => {
  const unavailable = harness({storage: {getItem: () => {throw Error('unavailable');}}}); await unavailable.click('read'); assert.equal(unavailable.calls.length, 0);
  const persist = harness({storage: {getItem: () => null, setItem: () => {throw Error('quota');}}});
  await persist.click('read'); persist.edit(); await persist.click('save'); assert.equal(persist.calls.length, 1);
  const held = harness({handler: c => {if (c.method === 'PUT') throw Error('unknown'); return data(held.s);}});
  await held.click('read'); held.edit(); await held.click('save'); const raw = [...held.memory.values()][0]; held.controller.dispose();
  assert.equal([...held.memory.values()][0], raw); await held.click('retry'); assert.equal(held.calls.filter(c => c.method === 'PUT').length, 1);
});
test('source digest final await cannot install defaults after source timing changes', async () => {
  let h; h = harness({crypto: {randomUUID: () => 'unused-read-key', subtle: {digest: async (...args) => {
    const value = await webcrypto.subtle.digest(...args); h.s.timeline.snapshot.duration_seconds += .01; return value;}}}});
  await h.click('read'); assert.equal(h.get('duck_threshold').value, ''); assert.equal(h.get('save').disabled, true);
});
test('configuration validator rejects false metric defaults or malformed receipt with no actor/source alias', () => {
  const s = state(); const d = data(s); assert.equal(audioProcessingRead(d, s), d);
  const forged = result(s, {expected_version: 1, request_key: 'explicit-key', configuration: defaults}); forged.receipt.actor_ref = '';
  assert.throws(() => audioProcessingRead(forged, s));
  assert.throws(() => audioProcessingRead({...d, configuration: {...defaults, duck_ratio: true}}, s));
});

test('literal token changes in the final PUT response retain UNKNOWN before any saved callback', async () => {
  let h; h = harness({handler: (c, tools) => {
    if (c.method === 'PUT') {const value = tools.result(c.body); h.setToken('changed-final-put-token'); return value;}
    return data(h.s);
  }});
  await h.click('read'); h.edit(); await h.click('save');
  assert.equal(h.calls.filter(c => c.method === 'PUT').length, 1); assert.equal(h.saved.length, 0);
  assert.equal(h.memory.size, 1); assert.equal(h.controller.isPending(), true);
});

test('late callback expiry or canonical drift retains the original frozen intent after successful transport', async () => {
  for (const mutation of ['expiry', 'canonical']) {
    let release, entered;
    const hold = new Promise(r => {release = r;}), started = new Promise(r => {entered = r;});
    const h = harness({onSaved: async (value, s) => {s.timeline = clone(value.timeline); entered(); await hold;}});
    await h.click('read'); h.edit(); const work = h.click('save'); await started;
    const raw = [...h.memory.values()][0];
    if (mutation === 'expiry') h.s.principal.expires_at = '2000-01-01T00:00:00Z';
    else h.s.timeline.current_version++;
    release(); await work;
    assert.equal([...h.memory.values()][0], raw); assert.equal(h.memory.size, 1);
    assert.equal(h.controller.isPending(), true); assert.equal(h.get('save').disabled, true);
  }
});

test('pending scope projects only the six public principal fields and never persists an extra literal bearer field', async () => {
  const s = state(); s.principal.private_bearer = 'EXPLICIT_TRANSIENT_NOT_AUTHENTICATED';
  const h = harness({s, handler: c => {if (c.method === 'PUT') throw Error('explicit UNKNOWN'); return data(s);}});
  await h.click('read'); h.edit(); await h.click('save'); const raw = [...h.memory.values()][0];
  assert.equal(raw.includes('private_bearer'), false); assert.equal(raw.includes('EXPLICIT_TRANSIENT_NOT_AUTHENTICATED'), false);
  assert.equal(JSON.parse(raw).session_sha256, createHash('sha256').update('EXPLICIT_TRANSIENT_NOT_AUTHENTICATED').digest('hex'));
});
