import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash, webcrypto} from 'node:crypto';
import {validateVideoWords, videoWordPayload, videoWordReceiptMatches, boundedVideoWordSource,
  initializeVideoTranscriptWordReview, videoWordSessionStorage} from '../video-transcript-word-review.mjs';

// Actual ASGI/SQLite captures preserve historical genuine ASR. Transport races
// below are explicit UI fixtures, with no model, listening or Owner acceptance.
const clone = structuredClone;
// Public /auth/session DTO intentionally does not expose a token identifier.
function publicSessionState(role = 'editor') {
  const s = state();
  s.principal = {subject: fixture.context.actor_ref, display_name: 'Explicit public session fixture',
    platform_role: null, workspace_roles: {[s.workspaceId]: role},
    expires_at: '2100-01-01T00:00:00Z', human_write_enabled: true};
  return s;
}
const capturedBytes = readFileSync(new URL('./fixtures/sql-video-word-review/asgi.json', import.meta.url));
const fixture = JSON.parse(capturedBytes), manifest = JSON.parse(readFileSync(new URL('./fixtures/sql-video-word-review/manifest.json', import.meta.url)));
const base = fixture.responses.base.body, edited = fixture.responses.edited.body;
function state(role = 'editor') {
  return {workspaceId: fixture.context.workspace_id, projectId: fixture.context.project_id,
    principal: {subject: fixture.context.actor_ref, token_id: 'explicit-word-ui-session', expires_at: '2100-01-01T00:00:00Z', platform_role: role},
    busy: false, dirty: false, assets: [clone(fixture.asset)], analysis: clone(base), analyses: [clone(base)],
    timeline: clone(fixture.responses.timeline_before.body)};
}
function pending() {return {analysisId: base.analysis_id, projectId: base.project_id, workspaceId: base.workspace_id,
  actor: fixture.context.actor_ref, base: clone(base), latest: clone(base), body: clone(fixture.responses.edited.request)};}
function harness({s = state(), handler, storage, crypto, onSaved, mediaFetch, getSessionToken} = {}) {
  class Element {
    constructor(tag) {this.tagName = tag; this.children = []; this.attributes = {}; this.listeners = {}; this.value = ''; this.checked = false; this.disabled = false; this.textContent = '';}
    append(...items) {this.children.push(...items);} replaceChildren(...items) {this.children = items;}
    setAttribute(k, v) {this.attributes[k] = String(v);} removeAttribute(k) {delete this.attributes[k]; if (k === 'src') delete this.src;}
    addEventListener(k, action) {this.listeners[k] = action;}
  }
  const dom = {createElement: tag => new Element(tag)}, root = dom.createElement('section'), all = e => [e, ...e.children.flatMap(all)];
  const calls = [], messages = [], memory = new Map(), revoked = [], saved = []; let response = clone(base), busyEvents = 0;
  let token = 'EXPLICIT_NODE_TRANSIENT_TOKEN_NOT_AUTHENTICATED_OR_PERSISTED';
  const get = name => all(root).filter(e => Object.hasOwn(e.attributes, 'data-video-word-' + name));
  const receipt = body => {const a = clone(edited); a.transcript.provenance.edit_note = body.note; return a;};
  const api = async (path, options) => {
    const call = {path, method: options?.method ?? 'GET', body: options?.body ? JSON.parse(options.body) : null}; calls.push(call);
    if (handler) return handler(call, s, {receipt, setResponse: a => {response = a;}});
    if (call.method === 'POST') {response = receipt(call.body); return clone(response);}
    if (path.includes('?transcript_id=')) return clone(base); return clone(response);
  };
  const controller = initializeVideoTranscriptWordReview({root, api, dom, mediaFetch, getState: () => s,
    getSessionToken: getSessionToken ?? (() => token),
    storage: storage ?? {getItem: k => memory.get(k) ?? null, setItem: (k, v) => memory.set(k, v),
      compareAndRemoveItem: (k, v) => {if (memory.get(k) !== v) return false; memory.delete(k); return true;}},
    cryptoImpl: crypto ?? {...webcrypto, subtle: webcrypto.subtle, randomUUID: () => 'fixture-word-intent-0001'},
    onMessage: (...v) => messages.push(v), onBusyChanged: () => busyEvents++,
    onSaved: async selection => {saved.push(selection); if (onSaved) return onSaved(selection, s);
      s.analysis = clone(selection.receipt); s.analyses = [clone(selection.receipt)]; s.timeline = clone(fixture.responses.timeline_after.body);},
    urls: {createObjectURL: () => 'blob:explicit-fixture', revokeObjectURL: value => revoked.push(value)}});
  function edit() {get('text')[0].value += '!'; get('text')[0].listeners.input(); get('ack')[0].checked = true; get('ack')[0].listeners.change();}
  return {s, controller, get, calls, messages, memory, saved, revoked, root, edit, receipt, setToken: value => {token = value;},
    click: name => get(name)[0].listeners.click(), busyEvents: () => busyEvents};
}

test('immutable actual ASGI bytes include one scoped SQL word CAS and untouched original/source/usage', () => {
  assert.equal(createHash('sha256').update(capturedBytes).digest('hex'), manifest.asgi_sha256);
  assert.equal(capturedBytes.length, manifest.asgi_bytes);
  assert.equal(manifest.actual_sql_api_assertions_passed, true);
  assert.equal(manifest.successful_word_posts, 1);
  assert.equal(manifest.original_cold_db_sha256_before, manifest.original_cold_db_sha256_after);
  assert.equal(manifest.source_sha256_before, manifest.source_sha256_after);
  assert.deepEqual(fixture.responses.original_after.body.transcript, base.transcript);
  assert.equal(fixture.responses.stale.status, 409); assert.equal(fixture.responses.viewer_denied.status, 403);
  assert.equal(fixture.responses.extra_actor.status, 422); assert.equal(fixture.responses.foreign_scope.status, 404);
  assert.equal(fixture.scope.new_model_calls, 0); assert.equal(fixture.scope.human_listening, false);
  assert.equal(fixture.scope.owner_uat_accepted, false); assert.equal(manifest.provider_usage_rows_unchanged, true);
});
test('actual normalized 23 source words and receipt preserve times and remove revised confidence honestly', () => {
  assert.equal(validateVideoWords(base, state()), base);
  assert.equal(base.transcript.segments.flatMap(s => s.words).length, 23);
  assert.equal(videoWordReceiptMatches(edited, pending()), true);
  const p = pending(); p.actor = 'pretended-owner'; assert.equal(videoWordReceiptMatches(edited, p), false);
  const v = clone(edited); v.transcript.segments[0].words[0].confidence = .99;
  assert.equal(videoWordReceiptMatches(v, pending()), false);
});
test('mount and sync do zero API work; explicit read exposes saved source times without acknowledgement', async () => {
  const h = harness(); h.controller.sync(); assert.equal(h.calls.length, 0); await h.click('read');
  assert.deepEqual(h.calls.map(c => c.method), ['GET']); assert.equal(h.get('text').length, 23);
  assert.equal(h.get('start')[0].value, String(base.transcript.segments[0].words[0].start_seconds));
  assert.equal(h.get('ack')[0].checked, false); assert.equal(h.controller.isDirty(), false);
  assert.equal(h.get('save')[0].disabled, true); assert.equal(h.get('listen')[0].disabled, true);
});
test('explicit unchanged-clock word revision uses original selected IDs and canonical CAS then requires review', async () => {
  const h = harness(); await h.click('read'); h.edit(); await h.click('save');
  const c = h.calls.find(c => c.method === 'POST'); assert.ok(c.path.endsWith('/transcript-words'));
  assert.equal(c.body.expected_version, 1); assert.equal(c.body.expected_transcript_id, base.transcript.transcript_id);
  assert.equal(c.body.expected_timeline_version, 1); assert.equal(Object.hasOwn(c.body, 'actor_ref'), false);
  assert.deepEqual(c.body.segments[0].words.map(w => [w.start_seconds, w.end_seconds]),
    base.transcript.segments[0].words.map(w => [w.start_seconds, w.end_seconds]));
  assert.equal(h.saved.length, 1); assert.equal(h.controller.isPending(), false); assert.equal(h.memory.size, 0);
  assert.match(h.get('status')[0].textContent, /Preview và phê duyệt cần cập nhật/);
});
test('viewer, expired/service role, foreign dirty or busy never dispatch a write', async () => {
  for (const change of [s => s.principal.platform_role = 'viewer', s => s.principal.platform_role = 'service',
    s => s.principal.expires_at = '2000-01-01T00:00:00Z', s => s.dirty = true, s => s.busy = true]) {
    const h = harness(); await h.click('read'); h.edit(); change(h.s); await h.click('save');
    assert.equal(h.calls.some(c => c.method === 'POST'), false); assert.equal(h.memory.size, 0);
  }
});
test('word/source/canonical drift before dispatch closes revision and keeps local draft', async () => {
  for (const change of [s => s.assets[0].checksum_sha256 = 'f'.repeat(64), s => s.assets[0].version++,
    s => s.timeline.current_version++, s => s.analysis.transcript.segments[0].words[0].text = 'foreign edit',
    s => s.timeline.source_analysis_id = 'ana_' + 'f'.repeat(24)]) {
    const h = harness(); await h.click('read'); h.edit(); change(h.s); await h.click('save');
    assert.equal(h.calls.some(c => c.method === 'POST'), false); assert.equal(h.controller.isDirty(), true);
  }
});
test('strict word ordering/foreign word identity and whitespace source numbers never send invalid body', async () => {
  const h = harness(); await h.click('read'); h.edit(); h.get('end')[0].value = h.get('start')[0].value;
  await h.click('save'); assert.equal(h.calls.some(c => c.method === 'POST'), false);
  const bad = clone(base); bad.transcript.segments[0].words[0].word_id = bad.transcript.segments[0].words[1].word_id;
  assert.throws(() => validateVideoWords(bad, state()), /Từ hoặc/);
  const blank = harness(); await blank.click('read'); blank.edit(); blank.get('start')[0].value = '';
  await blank.click('save'); assert.equal(blank.calls.some(c => c.method === 'POST'), false);
  assert.match(blank.messages.at(-1)[0], /ô trống/);
});
test('POST response loss retains exact intent; only exact captured append reconciles, no repeated provider/job', async () => {
  let committed = null;
  const h = harness({handler: (c, _s, tools) => {if (c.method === 'POST') {committed = tools.receipt(c.body); throw Error('explicit lost response fixture');}
    return clone(committed ?? base);}});
  await h.click('read'); h.edit(); await h.click('save'); const body = JSON.stringify(h.calls.find(c => c.method === 'POST').body);
  assert.equal(h.controller.isPending(), true); assert.equal(h.memory.size, 1); await h.click('reconcile');
  assert.equal(h.controller.isPending(), false); assert.equal(h.calls.filter(c => c.method === 'POST').length, 1);
  assert.equal(JSON.stringify(h.calls.find(c => c.method === 'POST').body), body);
});
test('successful POST then callback reload failure keeps pending until explicit reconciliation succeeds', async () => {
  let fail = true;
  const h = harness({onSaved: (selection, s) => {if (fail) throw Error('explicit GET/reload failure');
    s.analysis = clone(selection.receipt); s.timeline = clone(fixture.responses.timeline_after.body);}});
  await h.click('read'); h.edit(); await h.click('save'); assert.equal(h.controller.isPending(), true);
  fail = false; await h.click('reconcile'); assert.equal(h.controller.isPending(), false);
  assert.equal(h.calls.filter(c => c.method === 'POST').length, 1);
});
test('uncommitted response loss permits only frozen exact request after GET proves old persisted sequence', async () => {
  let first = true;
  const h = harness({handler: (c, _s, tools) => {if (c.method === 'GET') return clone(base);
    if (first) {first = false; throw Error('explicit precommit transport loss');} return tools.receipt(c.body);}});
  await h.click('read'); h.edit(); await h.click('save'); await h.click('reconcile'); await h.click('retry');
  const posts = h.calls.filter(c => c.method === 'POST'); assert.equal(posts.length, 2); assert.deepEqual(posts[0].body, posts[1].body);
  assert.equal(h.controller.isPending(), false);
});
test('unrelated higher transcript/marker or actor is never receipt proof and never rebases CAS', async () => {
  let value = clone(base);
  const h = harness({handler: (c, _s, tools) => {if (c.method === 'POST') {value = tools.receipt(c.body);
    value.transcript.provenance.actor_ref = 'other-editor'; throw Error('lost fixture');} return clone(value);}});
  await h.click('read'); h.edit(); await h.click('save'); await h.click('reconcile');
  assert.equal(h.controller.isPending(), true); assert.equal(h.calls.filter(c => c.method === 'POST').length, 1);
  assert.equal(h.get('retry')[0].disabled, true); assert.equal(h.saved.length, 0);
});
test('late GET/session/source changes never install old words or send write', async () => {
  for (const change of [s => s.projectId = 'prj_other', s => s.principal.token_id = 'new-session', s => s.assets[0].version++]) {
    const h = harness({handler: (_c, s) => {change(s); return clone(base);}}); await h.click('read');
    assert.equal(h.get('text').length, 0); assert.equal(h.saved.length, 0); assert.equal(h.memory.size, 0);
    if (h.s.projectId !== base.project_id || h.s.principal.token_id !== 'explicit-word-ui-session') assert.equal(h.controller.isWorking(), false);
  }
});
test('late POST or onSaved callback session drift retains stored unknown intent without new-project writes', async () => {
  const h = harness({handler: (c, s, tools) => {if (c.method === 'POST') {s.principal.token_id = 'changed'; return tools.receipt(c.body);} return clone(base);}});
  await h.click('read'); h.edit(); await h.click('save'); assert.equal(h.saved.length, 0); assert.equal(h.memory.size, 1);
  const late = harness({onSaved: (_selection, s) => {s.projectId = 'prj_elsewhere';}});
  await late.click('read'); late.edit(); await late.click('save'); assert.equal(late.memory.size, 1);
});
test('single flight and dispose before final awaited response cannot grant saved authority', async () => {
  let release, entered; const hold = new Promise(r => {release = r;}), firstPost = new Promise(r => {entered = r;});
  const h = harness({handler: async (c, _s, tools) => {if (c.method === 'POST') {entered(); await hold; return tools.receipt(c.body);} return clone(base);}});
  await h.click('read'); h.edit(); const first = h.click('save'); await h.click('save');
  await firstPost;
  assert.equal(h.calls.filter(c => c.method === 'POST').length, 1); h.controller.dispose(); release(); await first;
  assert.equal(h.saved.length, 0); assert.equal(h.memory.size, 1);
});
test('history reads original provider evidence explicitly and does not round source-clock drafts', async () => {
  const s = state(); s.analysis = clone(edited); s.timeline = clone(fixture.responses.timeline_after.body);
  const h = harness({s, handler: c => clone(c.path.includes('?') ? fixture.responses.original_after.body : edited)});
  await h.click('read'); assert.equal(h.calls.length, 2);
  assert.ok(h.get('historical-words').some(e => e.textContent.includes(String(base.transcript.segments[0].words[0].confidence))));
  assert.equal(h.get('start')[0].value, String(edited.transcript.segments[0].words[0].start_seconds));
});
test('selected immutable older canonical base freezes latest CAS sequence separately', async () => {
  const s = state(); s.analysis = clone(fixture.responses.original_after.body);
  const h = harness({s, handler: c => clone(c.path.includes('?') ? fixture.responses.original_after.body : edited)});
  await h.click('read'); h.edit(); await h.click('save');
  const post = h.calls.find(c => c.method === 'POST'); assert.equal(post.body.expected_version, 2);
  assert.equal(post.body.expected_transcript_id, base.transcript.transcript_id);
  assert.equal(post.body.expected_timeline_version, 1);
  assert.equal(h.controller.isPending(), true); // Returned v2 is not proof of expected v3.
});
test('missing provider word times is informational and never creates guessed intervals', async () => {
  const s = state(); s.analysis.transcript.segments[0].words = []; const a = clone(s.analysis);
  const h = harness({s, handler: () => clone(a)}); await h.click('read');
  assert.equal(h.get('text').length, 0); assert.equal(h.get('save')[0].disabled, true);
  assert.match(h.get('status')[0].textContent, /Không tạo thời gian giả/);
});
test('storage persistence failure stops before POST; forged session/foreign retained intent is closed', async () => {
  const h = harness({storage: {getItem: () => null, setItem: () => {throw Error('storage full');}}});
  await h.click('read'); h.edit(); await h.click('save'); assert.equal(h.calls.some(c => c.method === 'POST'), false);
  const bad = harness({storage: {getItem: () => JSON.stringify({...pending(), scope: 'foreign', sourceIdentity: 'foreign'}), setItem() {}}});
  await bad.click('read'); assert.equal(bad.controller.isPending(), true); assert.equal(bad.get('text').length, 0);
  assert.equal(bad.calls.length, 0); assert.equal(bad.calls.some(c => c.method === 'POST'), false);
});
test('storage callback drift before the wire and changed timeline after reconcile never dispatch old CAS', async () => {
  const s = state(), memory = new Map(); const h = harness({s, storage: {
    getItem: k => memory.get(k) ?? null,
    setItem: (k, value) => {memory.set(k, value); s.principal.token_id = 'storage-callback-session';},
    removeItem: k => memory.delete(k)}});
  await h.click('read'); h.edit(); await h.click('save'); assert.equal(h.calls.some(c => c.method === 'POST'), false);
  assert.equal(memory.size, 1);
  const held = harness({handler: c => {if (c.method === 'POST') throw Error('explicit no-commit fixture'); return clone(base);}});
  await held.click('read'); held.edit(); await held.click('save'); await held.click('reconcile');
  held.s.timeline.current_version++; await held.click('retry'); assert.equal(held.calls.filter(c => c.method === 'POST').length, 1);
});
function response(bytes, asset, override = {}) {return new Response(bytes, {status: 200,
  headers: {'content-type': asset.content_type, 'content-length': String(asset.size_bytes), 'cache-control': 'no-store',
    etag: `"sha256-${asset.checksum_sha256}"`, ...override}});}
test('bounded source accepts exact owned bytes, refuses wrong MIME/ETag/length/oversize/truncation', async () => {
  const bytes = new Uint8Array([1, 2, 3]), asset = {content_type: 'video/mp4', size_bytes: 3, checksum_sha256: 'a'.repeat(64)};
  assert.deepEqual(await boundedVideoWordSource(response(bytes, asset), asset, new AbortController().signal, 3), bytes);
  for (const res of [response(bytes, asset, {'content-type': 'text/html'}), response(bytes, asset, {etag: 'other'}),
    response(bytes, asset, {'content-length': '4'}), response(bytes.slice(0, 2), asset), response(new Uint8Array(4), asset)])
    await assert.rejects(boundedVideoWordSource(res, asset, new AbortController().signal, 3));
});
test('bounded source cancellation cancels reader, preserves no partial playback or listening acknowledgement', async () => {
  const signal = new AbortController(); signal.abort(); const asset = {content_type: 'video/mp4', size_bytes: 3, checksum_sha256: 'a'.repeat(64)};
  await assert.rejects(boundedVideoWordSource(response(new Uint8Array(3), asset), asset, signal.signal, 3), /dừng tải/);
});
test('copied child video requires current opaque import receipt and never master-job/upload aliases', async () => {
  const imported = JSON.parse(readFileSync(new URL('./fixtures/sql-variant-import-review/read.json', import.meta.url)));
  const s = state(); s.workspaceId = imported.context.workspace_id; s.projectId = imported.context.project_id;
  s.assets = clone(imported.responses.assets.body); s.timeline = clone(imported.responses.timeline.body);
  s.analysis = clone(imported.responses.analyses.body[0]); s.analyses = clone(imported.responses.analyses.body);
  const h = harness({s, handler: c => clone(c.path.includes('/variant-families/') ? imported.responses.receipt.body : s.analysis)});
  await h.click('read'); assert.equal(h.calls[0].path, imported.responses.receipt.path);
  assert.equal(h.calls.some(c => c.method === 'POST'), false);
  assert.ok(h.get('text').length > 0); assert.equal(h.controller.isPending(), false);
  const broken = clone(s); delete broken.timeline.snapshot.metadata.sql_variant_derivative.family_id;
  const denied = harness({s: broken, handler: () => {throw Error('must not dispatch missing origin');}});
  await denied.click('read'); assert.equal(denied.calls.length, 0);
});
test('final source WebCrypto drift or endpoint absence cannot create playback/acknowledgement', async () => {
  const bytes = new Uint8Array([1, 2, 3]), hash = createHash('sha256').update(bytes).digest('hex');
  const s = state(); s.assets[0].size_bytes = 3; s.assets[0].checksum_sha256 = hash;
  for (const key of ['source_checksum', 'source_asset_sha256']) if (s.analysis.transcript.provenance[key]) s.analysis.transcript.provenance[key] = hash;
  const digest = async (...args) => {const value = await webcrypto.subtle.digest(...args); s.principal.token_id = 'late-hash-session'; return value;};
  const h = harness({s, handler: () => clone(s.analysis), crypto: {subtle: {digest}, randomUUID: () => 'explicit-fixture-operation'},
    mediaFetch: async path => {assert.ok(path.endsWith('/source')); return response(bytes, s.assets[0]);}});
  await h.click('read'); await h.click('listen'); assert.equal(h.get('source')[0].hidden, true);
  assert.equal(h.get('ack')[0].checked, false); assert.equal(h.controller.isWorking(), false);
  const unavailable = harness({mediaFetch: async () => new Response('', {status: 404})});
  await unavailable.click('read'); await unavailable.click('listen'); assert.equal(unavailable.get('source')[0].hidden, true);
  assert.equal(unavailable.calls.some(c => c.method === 'POST'), false); assert.equal(unavailable.get('ack')[0].checked, false);
});

test('UNKNOWN intent survives token-id refresh; stored mismatch gates before rows and cannot be overwritten', async () => {
  const h = harness({handler: c => {if (c.method === 'POST') throw Error('explicit UNKNOWN transport'); return clone(base);}});
  await h.click('read'); h.edit(); await h.click('save'); const old = [...h.memory.values()][0], calls = h.calls.length;
  h.s.principal.token_id = 'refreshed-principal-id'; h.controller.sync();
  assert.equal(h.controller.isPending(), true); await h.click('read');
  assert.equal(h.get('text').length, 0); assert.equal(h.get('save')[0].disabled, true); assert.equal(h.calls.length, calls);
  await h.click('save'); assert.equal(h.calls.filter(c => c.method === 'POST').length, 1);
  assert.equal([...h.memory.values()][0], old); assert.match(h.get('status')[0].textContent, /khóa/);
});
test('malformed, foreign or legacy unhashed retained record stays gated without GET/POST/delete', async () => {
  const seed = harness({handler: c => {if (c.method === 'POST') throw Error('explicit UNKNOWN'); return clone(base);}});
  await seed.click('read'); seed.edit(); await seed.click('save'); const entry = [...seed.memory.entries()][0];
  const valid = JSON.parse(entry[1]);
  const mutations = [p => {delete p.session_sha256;}, p => {p.scope = 'foreign';}, p => {p.body.segments = [];},
    p => {p.body.actor_ref = 'pretended-owner';}, p => {p.body.segments[0].words[0].start_seconds = '';},
    p => {p.base.transcript.words = 'malformed'; p.body.acknowledged = false;}];
  const records = ['{invalid json', ...mutations.map(change => {const p = clone(valid); change(p); return JSON.stringify(p);})];
  for (const raw of records) {
    const memory = new Map([[entry[0], raw]]); const h = harness({storage: {getItem: k => memory.get(k) ?? null,
      setItem: (k, v) => memory.set(k, v), removeItem: k => memory.delete(k)}});
    assert.equal(h.controller.isPending(), true); await h.click('read'); await h.click('save'); await h.click('retry');
    assert.equal(h.calls.length, 0); assert.equal(h.get('text').length, 0); assert.equal(h.get('save')[0].disabled, true);
    assert.equal(memory.get(entry[0]), raw); assert.equal(h.controller.isPending(), true);
  }
});
test('same-session reload validates hashed held intent and existing immutable base before exact retry', async () => {
  const seed = harness({handler: c => {if (c.method === 'POST') throw Error('explicit no commit'); return clone(base);}});
  await seed.click('read'); seed.edit(); await seed.click('save');
  const memory = new Map(seed.memory); const h = harness({storage: {getItem: k => memory.get(k) ?? null,
    setItem: (k, v) => memory.set(k, v),
    compareAndRemoveItem: (k, v) => {if (memory.get(k) !== v) return false; memory.delete(k); return true;}}});
  assert.equal(h.controller.isPending(), true); await h.click('read'); assert.equal(h.get('text').length, 23);
  assert.equal(h.get('save')[0].disabled, true); await h.click('reconcile'); await h.click('retry');
  assert.deepEqual(h.calls.find(c => c.method === 'POST').body, seed.calls.find(c => c.method === 'POST').body);
  assert.equal(h.controller.isPending(), false); assert.equal(memory.size, 0);
});
test('persisted intent stores only SHA256 of transient token; literal refresh with unchanged principal closes gate', async () => {
  const token = 'EXPLICIT_TRANSIENT_SECRET_FIXTURE_MUST_NOT_ENTER_PENDING_JSON';
  let current = token;
  const h = harness({getSessionToken: () => current, handler: c => {if (c.method === 'POST') throw Error('unknown'); return clone(base);}});
  await h.click('read'); h.edit(); await h.click('save'); const raw = [...h.memory.values()][0];
  assert.equal(raw.includes(token), false); assert.equal(JSON.parse(raw).session_sha256, createHash('sha256').update(token).digest('hex'));
  const calls = h.calls.length; current = 'EXPLICIT_REPLACEMENT_TOKEN_SAME_PRINCIPAL'; h.controller.sync(); await h.click('read');
  assert.equal(h.controller.isPending(), true); assert.equal(h.get('text').length, 0); assert.equal(h.calls.length, calls);
  assert.equal([...h.memory.values()][0], raw);
});
test('transient token changes during GET or intent hashing cannot install words or create a persisted/wire intent', async () => {
  let read;
  read = harness({handler: () => {read.setToken('literal-token-after-get'); return clone(base);}});
  await read.click('read'); assert.equal(read.get('text').length, 0); assert.equal(read.controller.isWorking(), false);
  let hashed;
  hashed = harness({crypto: {randomUUID: () => 'explicit-hash-fixture-intent', subtle: {digest: async (...args) => {
    hashed.setToken('literal-token-during-intent-hash'); return webcrypto.subtle.digest(...args);}}}});
  await hashed.click('read'); hashed.edit(); await hashed.click('save');
  assert.equal(hashed.calls.some(c => c.method === 'POST'), false); assert.equal(hashed.memory.size, 0);
});
test('transient token changes after POST or during callback retain UNKNOWN record and grant no live authority', async () => {
  let posted;
  posted = harness({handler: (c, _s, tools) => {if (c.method === 'POST') {posted.setToken('literal-post-token-change'); return tools.receipt(c.body);} return clone(base);}});
  await posted.click('read'); posted.edit(); await posted.click('save'); assert.equal(posted.saved.length, 0);
  assert.equal(posted.memory.size, 1); assert.equal(posted.controller.isPending(), true);
  let callback;
  callback = harness({onSaved: () => {callback.setToken('literal-callback-token-change');}});
  await callback.click('read'); callback.edit(); await callback.click('save');
  assert.equal(callback.memory.size, 1); assert.equal(callback.controller.isPending(), true); assert.equal(callback.get('save')[0].disabled, true);
});
test('storage unreadable and missing transient session token remain closed without exposing or overwriting record', async () => {
  const failed = harness({storage: {getItem: () => {throw Error('private storage exception');}, setItem() {throw Error('must not write');}}});
  assert.equal(failed.controller.isPending(), true); await failed.click('read'); assert.equal(failed.calls.length, 0);
  assert.equal(failed.get('text').length, 0); assert.match(failed.get('status')[0].textContent, /khóa/);
  const noToken = harness({getSessionToken: () => ''}); await noToken.click('read'); assert.equal(noToken.calls.length, 0);
});
test('record replacement during callback is retained even if sync observes the foreign bytes', async () => {
  let h; const foreign = '{foreign unresolved record}';
  h = harness({onSaved: (_selection, s) => {s.timeline = clone(fixture.responses.timeline_after.body);
    const bucket = [...h.memory.keys()][0]; h.memory.set(bucket, foreign); h.controller.sync();}});
  await h.click('read'); h.edit(); await h.click('save');
  assert.equal([...h.memory.values()][0], foreign); assert.equal(h.controller.isPending(), true);
  assert.equal(h.get('save')[0].disabled, true);
});
test('token change during restore hash blocks before provider-independent GET and retains original bytes', async () => {
  const seed = harness({handler: c => {if (c.method === 'POST') throw Error('unknown'); return clone(base);}});
  await seed.click('read'); seed.edit(); await seed.click('save'); const memory = new Map(seed.memory), raw = [...memory.values()][0];
  let restored; restored = harness({storage: {getItem: k => memory.get(k) ?? null, setItem() {throw Error('must not write');}},
    crypto: {randomUUID: () => 'unused-restored-key', subtle: {digest: async (...args) => {
      restored.setToken('changed-during-held-hash'); return webcrypto.subtle.digest(...args);}}}});
  await restored.click('read'); assert.equal(restored.calls.length, 0); assert.equal(restored.get('text').length, 0);
  assert.equal(restored.controller.isPending(), true); assert.equal([...memory.values()][0], raw);
});

test('literal token change during source SHA calculation creates no playable URL or listening acknowledgement', async () => {
  const bytes = new Uint8Array([1, 2, 3]), s = state(); s.assets[0].size_bytes = 3;
  s.assets[0].checksum_sha256 = createHash('sha256').update(bytes).digest('hex');
  for (const key of ['source_checksum', 'source_asset_sha256']) if (s.analysis.transcript.provenance[key]) s.analysis.transcript.provenance[key] = s.assets[0].checksum_sha256;
  let h; h = harness({s, handler: () => clone(s.analysis), mediaFetch: async () => response(bytes, s.assets[0]),
    crypto: {randomUUID: () => 'unused-source-fixture-key', subtle: {digest: async (...args) => {
      const value = await webcrypto.subtle.digest(...args); h.setToken('literal-source-sha-token-refresh'); return value;}}}});
  await h.click('read'); await h.click('listen'); assert.equal(h.get('source')[0].hidden, true);
  assert.equal(h.get('ack')[0].checked, false); assert.equal(h.calls.some(c => c.method === 'POST'), false);
});

test('final retained readback callback cannot dispatch when literal token, actor, project or canonical CAS changes', async () => {
  for (const mutation of ['token', 'actor', 'project', 'canonical']) {
    const s = state(), memory = new Map(); let h, armed = false, ran = false;
    h = harness({s, storage: {setItem: (k, v) => {memory.set(k, v); armed = true;},
      getItem: k => {const raw = memory.get(k) ?? null; if (armed && raw !== null) {
        armed = false; ran = true;
        if (mutation === 'token') h.setToken('explicit-last-readback-token');
        if (mutation === 'actor') s.principal.subject = 'usr:explicit-other-editor';
        if (mutation === 'project') s.projectId = 'prj_explicit_other_readback';
        if (mutation === 'canonical') s.timeline.current_version++;
      } return raw;}, removeItem: () => {throw Error('must not delete');}}});
    await h.click('read'); h.edit(); await h.click('save');
    assert.equal(ran, true); assert.equal(h.calls.some(c => c.method === 'POST'), false);
    assert.equal(h.saved.length, 0); assert.equal(memory.size, 1);
  }
});
test('final accepted getter replacement retains foreign UNKNOWN for unsupported or trusted compare-remove stores', async () => {
  for (const compareRemove of [false, true]) {
    const memory = new Map(), foreign = '{explicit-foreign-UNKNOWN}'; let armed = false, deletes = 0, compares = 0;
    const storage = {setItem: (k, v) => memory.set(k, v), getItem: k => {
      const raw = memory.get(k) ?? null;
      if (armed && raw !== null) {armed = false; memory.set(k, foreign);} return raw;
    }, removeItem: () => {deletes++; throw Error('arbitrary removal forbidden');}};
    if (compareRemove) storage.compareAndRemoveItem = (k, raw) => {
      compares++; if (memory.get(k) !== raw) return false; memory.delete(k); return true;
    };
    const h = harness({storage, onSaved: (selection, s) => {
      s.analysis = clone(selection.receipt); s.analyses = [clone(selection.receipt)];
      s.timeline = clone(fixture.responses.timeline_after.body); armed = true;
    }});
    await h.click('read'); h.edit(); await h.click('save');
    assert.equal(h.calls.filter(c => c.method === 'POST').length, 1); assert.equal(h.saved.length, 1);
    assert.equal([...memory.values()][0], foreign); assert.equal(deletes, 0);
    assert.equal(compares, compareRemove ? 1 : 0); assert.equal(h.controller.isPending(), true);
    assert.equal(h.get('save')[0].disabled, true);
  }
});
test('native session adapter captures Storage prototype calls and removes only exact raw in a synchronous turn', () => {
  const oldStorage = Object.getOwnPropertyDescriptor(globalThis, 'Storage');
  const oldSession = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage');
  class ExplicitStorageFixture {
    constructor() {this.records = new Map();}
    getItem(k) {return this.records.get(k) ?? null;}
    setItem(k, v) {this.records.set(k, v);}
    removeItem(k) {this.records.delete(k);}
  }
  const target = new ExplicitStorageFixture(); let injected = 0;
  target.getItem = target.removeItem = () => {injected++; throw Error('instance callback must not run');};
  try {
    Object.defineProperty(globalThis, 'Storage', {value: ExplicitStorageFixture, configurable: true});
    Object.defineProperty(globalThis, 'sessionStorage', {value: target, configurable: true});
    const adapter = videoWordSessionStorage(); adapter.setItem('bucket', 'owned');
    assert.equal(adapter.getItem('bucket'), 'owned');
    target.records.set('bucket', 'foreign'); assert.equal(adapter.compareAndRemoveItem('bucket', 'owned'), false);
    assert.equal(target.records.get('bucket'), 'foreign');
    assert.equal(adapter.compareAndRemoveItem('bucket', 'foreign'), true); assert.equal(target.records.size, 0);
    assert.equal(injected, 0);
  } finally {
    if (oldStorage) Object.defineProperty(globalThis, 'Storage', oldStorage); else delete globalThis.Storage;
    if (oldSession) Object.defineProperty(globalThis, 'sessionStorage', oldSession); else delete globalThis.sessionStorage;
  }
});
test('custom store without synchronous compare-remove keeps accepted UNKNOWN and never calls removeItem', async () => {
  const memory = new Map(); let removed = 0;
  const h = harness({storage: {getItem: k => memory.get(k) ?? null, setItem: (k, v) => memory.set(k, v),
    removeItem: () => {removed++;}}});
  await h.click('read'); h.edit(); await h.click('save');
  assert.equal(h.saved.length, 1); assert.equal(h.controller.isPending(), true); assert.equal(memory.size, 1);
  assert.equal(removed, 0); assert.match(h.get('status')[0].textContent, /đối chiếu đồng bộ/);
});
test('accepted final getter token or canonical drift cannot enter trusted compare-remove', async () => {
  for (const mutation of ['token', 'canonical']) {
    const memory = new Map(); let h, armed = false, compares = 0;
    h = harness({storage: {setItem: (k, v) => memory.set(k, v),
      getItem: k => {const raw = memory.get(k) ?? null; if (armed && raw !== null) {
        armed = false; if (mutation === 'token') h.setToken('explicit-accepted-last-token');
        else h.s.timeline.current_version++;
      } return raw;}, compareAndRemoveItem: () => {compares++; return true;}},
      onSaved: (selection, s) => {s.analysis = clone(selection.receipt);
        s.analyses = [clone(selection.receipt)]; s.timeline = clone(fixture.responses.timeline_after.body); armed = true;}});
    await h.click('read'); h.edit(); await h.click('save');
    assert.equal(compares, 0); assert.equal(memory.size, 1); assert.equal(h.controller.isPending(), true);
  }
});

test('public session DTO without token_id reads 23 source words and permits explicit editor CAS', async () => {
  for (const role of ['editor', 'owner']) {
    const h = harness({s: publicSessionState(role)});
    assert.equal(h.get('read')[0].disabled, false);
    await h.click('read'); assert.equal(h.get('text').length, 23);
    assert.equal(h.get('save')[0].disabled, true);
    h.edit(); await h.click('save');
    assert.equal(h.calls.filter(c => c.method === 'POST').length, 1);
    assert.equal(h.saved.length, 1); assert.equal(h.memory.size, 0);
    assert.equal(h.calls.find(c => c.method === 'POST').body.expected_timeline_version, 1);
    assert.equal(Object.hasOwn(h.s.principal, 'token_id'), false);
  }
});

test('public viewer can read but cannot revise; expired, unauthorized and tokenless sessions stay closed', async () => {
  const viewer = harness({s: publicSessionState('viewer')});
  await viewer.click('read'); assert.equal(viewer.get('text').length, 23);
  assert.equal(viewer.get('text')[0].disabled, true); await viewer.click('save');
  assert.equal(viewer.calls.some(c => c.method === 'POST'), false);
  for (const change of [s => s.principal.expires_at = '2000-01-01T00:00:00Z',
    s => s.principal.workspace_roles = {}, s => s.principal.subject = '', s => s.busy = true, s => s.dirty = true]) {
    const s = publicSessionState(); change(s); const h = harness({s});
    assert.equal(h.get('read')[0].disabled, true); await h.click('read'); assert.equal(h.calls.length, 0);
  }
  const h = harness({s: publicSessionState(), getSessionToken: () => ''});
  await h.click('read'); assert.equal(h.calls.length, 0);
});

test('public DTO literal token change during GET or hash cannot install or dispatch a new intent', async () => {
  let h; h = harness({s: publicSessionState(), handler: () => {h.setToken('public-get-token-refresh'); return clone(base);}});
  await h.click('read'); assert.equal(h.get('text').length, 0); assert.equal(h.calls.length, 1);
  let hashed; hashed = harness({s: publicSessionState(), crypto: {randomUUID: () => 'public-dto-hash-intent',
    subtle: {digest: async (...args) => {hashed.setToken('public-hash-token-refresh'); return webcrypto.subtle.digest(...args);}}}});
  await hashed.click('read'); assert.equal(hashed.get('text').length, 23); hashed.edit(); await hashed.click('save');
  assert.equal(hashed.calls.some(c => c.method === 'POST'), false); assert.equal(hashed.memory.size, 0);
});

test('public DTO token change after POST or callback retains exact UNKNOWN without live authority', async () => {
  let posted; posted = harness({s: publicSessionState(), handler: (c, _s, tools) => {
    if (c.method === 'POST') {posted.setToken('public-post-token-refresh'); return tools.receipt(c.body);} return clone(base);}});
  await posted.click('read'); assert.equal(posted.get('text').length, 23); posted.edit(); await posted.click('save');
  assert.equal(posted.saved.length, 0); assert.equal(posted.memory.size, 1); assert.equal(posted.controller.isPending(), true);
  let callback; callback = harness({s: publicSessionState(), onSaved: () => callback.setToken('public-callback-token-refresh')});
  await callback.click('read'); callback.edit(); await callback.click('save');
  assert.equal(callback.memory.size, 1); assert.equal(callback.get('save')[0].disabled, true);
});

test('public DTO held intent validates same literal token; a refreshed token keeps original UNKNOWN bytes', async () => {
  const seed = harness({s: publicSessionState(), handler: c => {if (c.method === 'POST') throw Error('explicit public DTO UNKNOWN'); return clone(base);}});
  await seed.click('read'); assert.equal(seed.get('text').length, 23); seed.edit(); await seed.click('save');
  const memory = new Map(seed.memory), raw = [...memory.values()][0], key = [...memory.keys()][0];
  const storage = {getItem: k => memory.get(k) ?? null, setItem: (k, v) => memory.set(k, v),
    compareAndRemoveItem: (k, v) => {if (memory.get(k) !== v) return false; memory.delete(k); return true;}};
  const sameSession = harness({s: publicSessionState(), storage});
  await sameSession.click('read'); assert.equal(sameSession.get('text').length, 23);
  await sameSession.click('reconcile'); await sameSession.click('retry');
  assert.deepEqual(sameSession.calls.find(c => c.method === 'POST').body, seed.calls.find(c => c.method === 'POST').body);
  assert.equal(memory.size, 0);
  const foreignMemory = new Map([[key, raw]]);
  const refreshed = harness({s: publicSessionState(), getSessionToken: () => 'public-restore-refreshed-token',
    storage: {getItem: k => foreignMemory.get(k) ?? null, setItem() {throw Error('must not overwrite');}}});
  await refreshed.click('read'); assert.equal(refreshed.calls.length, 0); assert.equal(refreshed.controller.isPending(), true);
  assert.equal(foreignMemory.get(key), raw);
});
