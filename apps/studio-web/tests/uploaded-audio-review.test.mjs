import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto, createHash} from 'node:crypto';
import {audioRole, uploadedSpeechAssets, validateAudioRead, audioCreatePayload, audioTextPayload,
  audioWordsPayload, audioRestorePayload, audioByteHash, audioRevisionMatches, compatibleAudioBinding, audioCaptionPayload,
  boundedAudioBytes, initializeUploadedAudioReview} from '../uploaded-audio-review.mjs';

// These HTTP response bodies came from isolated SQLite + ASGI + explicit MockASR.
// The source is owned silent PCM WAV. It is not real provider or Owner acceptance.
const captured = JSON.parse(readFileSync(new URL('./fixtures/sql-uploaded-audio/read.json', import.meta.url), 'utf8'));
const wav = readFileSync(new URL('./fixtures/sql-uploaded-audio/source.wav', import.meta.url));
const clone = structuredClone, key = 'sql-audio-ui-request-00001';
const capabilities = {human_write_enabled: true, uploaded_audio_transcription: 'independent_async_versioned_evidence',
  transcription_provider: 'contract', asr_external_execution_enabled: false, asr_paid_execution_enabled: false};
function fixture() {return clone(captured);}
function textEdit(value = captured.original) {return [{segment_id: value.current.segments[0].segment_id, text: 'Chữ do người dùng sửa.'}];}
function wordEdit(value = captured.original) {
  const s = value.current.segments[0]; return [{segment_id: s.segment_id, start_seconds: s.start_seconds,
    end_seconds: s.end_seconds, words: s.words.map(w => ({word_id: w.word_id, text: w.text, start_seconds: w.start_seconds, end_seconds: w.end_seconds}))}];
}
function requestResult(state, body) {
  const audioId = 'aud_' + createHash('sha256').update(JSON.stringify([state.projectId, body.idempotency_key])).digest('hex').slice(0, 24);
  const row = clone(captured.original); row.audio_id = audioId; row.current = row.original = null; row.versions = [];
  row.job.status = 'queued'; row.job.request.audio_id = audioId; return row;
}
function harness({transport, fetcher, values = [captured.original], storageMap = new Map(), storageImpl, canonicalSaved} = {}) {
  class Element {
    constructor(tag) {this.tagName = tag; this.children = []; this.attributes = {}; this.listeners = {}; this.value = ''; this.checked = false; this.disabled = false; this.hidden = false;}
    append(...nodes) {this.children.push(...nodes);}
    replaceChildren(...nodes) {this.children = nodes;}
    setAttribute(k, v) {this.attributes[k] = String(v);}
    removeAttribute(k) {delete this.attributes[k]; if (k === 'src') delete this.src;}
    addEventListener(k, fn) {this.listeners[k] = fn;}
    querySelectorAll(selector) {return all(this).slice(1).filter(n => selector.split(',').includes(n.tagName));}
    pause() {this.pauses = (this.pauses ?? 0) + 1;}
    get disabled() {return this._disabled;}
    set disabled(value) {this._disabled = Boolean(value);}
  }
  const all = n => [n, ...n.children.flatMap(all)];
  const dom = {createElement: tag => new Element(tag)}, root = dom.createElement('details');
  const data = fixture(), calls = [], media = [], messages = [], created = [], revoked = [], timeouts = new Map(); let timerId = 0;
  const api = async (path, options) => {
    const body = options?.body ? JSON.parse(options.body) : null; calls.push({path, method: options?.method ?? 'GET', body});
    if (transport) {const result = await transport(path, body, data); if (result !== undefined) return result;}
    if (path === '/api/v1/capabilities') return clone(capabilities);
    if (path.endsWith('/audio-transcriptions') && !body) return clone(values);
    if (body) return requestResult(data.state, body);
    return clone(data.original);
  };
  const mediaFetch = async (path, options) => {media.push({path, options}); return fetcher ? fetcher(path, options, data)
    : new Response(wav, {status: 200, headers: captured.source.headers});};
  const controller = initializeUploadedAudioReview({root, dom, api, mediaFetch, getState: () => data.state,
    onMessage: (...args) => messages.push(args), newKey: () => key, cryptoImpl: webcrypto,
    urls: {createObjectURL: blob => {created.push(blob); return `blob:owned-${created.length}`;}, revokeObjectURL: url => revoked.push(url)},
    timers: {setTimeout: fn => {timeouts.set(++timerId, fn); return timerId;}, clearTimeout: id => timeouts.delete(id)},
    storage: storageImpl ?? {getItem: key => storageMap.get(key) ?? null, setItem: (key, value) => storageMap.set(key, value), removeItem: key => storageMap.delete(key)},
    onUploaded: async () => {data.uploaded = (data.uploaded ?? 0) + 1;},
    onCanonicalSaved: async () => {data.canonicalSaved = (data.canonicalSaved ?? 0) + 1; await canonicalSaved?.(data);}});
  const get = name => all(root).find(n => Object.hasOwn(n.attributes, 'data-audio-' + name));
  const click = async name => {await get(name).listeners.click();};
  const change = (name, value) => {get(name).value = value; get(name).listeners.change?.();};
  const check = name => {get(name).checked = true; get(name).listeners.change?.();};
  const textInput = () => all(root).find(n => Object.hasOwn(n.attributes, 'data-audio-segment-text'));
  const textDraft = value => {const n = textInput(); n.value = value; n.listeners.input();};
  return {...data, data, controller, root, calls, media, messages, created, revoked, timeouts, storageMap, all: () => all(root), get, click, change, check, textInput, textDraft};
}

test('captured SQL HTTP history uses actual source checksum and immutable original across edits and restore', async () => {
  const {state, original, text, words, restored} = fixture();
  assert.match(captured.fixture_notice, /MockASR.*No real ASR/);
  assert.equal(await audioByteHash(wav, webcrypto), state.assets[0].checksum_sha256);
  assert.equal(wav.subarray(0, 4).toString(), 'RIFF'); assert.equal(wav.length, state.assets[0].size_bytes);
  for (const row of [original, text, words, restored]) assert.equal(validateAudioRead(row, state), row);
  assert.deepEqual(original.original, restored.original); assert.equal(restored.current.version, 4);
  assert.equal(restored.current.provenance.restored_from_transcript_id, original.original.transcript_id);
});
test('audio picker keeps explicit speech uploads and excludes music, video, foreign and unregistered sources', () => {
  const {state} = fixture(); assert.equal(uploadedSpeechAssets(state).length, 1);
  const asset = clone(state.assets[0]);
  for (const mutate of [a => a.kind = 'music', a => a.project_id = 'prj_foreign', a => a.workspace_id = 'wsp_foreign',
    a => a.asset_class = 'generated', a => a.provenance.source_type = 'stock', a => a.provenance.media_metadata.media_kind = 'video']) {
    const s = clone(state); mutate(s.assets[0]); assert.deepEqual(uploadedSpeechAssets(s), []);
  }
  assert.deepEqual(state.assets[0], asset);
});
test('role contract matches platform, wildcard, workspace and slug ranks without granting absent roles', () => {
  const {state} = fixture(); state.principal.platform_role = null; state.principal.workspace_roles = {'*': 'viewer', [state.workspaceId]: 'editor', 'slug:ui-audio-fixture': 'reviewer'};
  assert.equal(audioRole(state), 'reviewer'); state.principal.platform_role = 'owner'; assert.equal(audioRole(state), 'owner');
  state.principal = {}; assert.equal(audioRole(state), null);
});
test('create payload freezes SHA and idempotency key without inventing rights, provider choice or paid permission', () => {
  const {state} = fixture(); const body = audioCreatePayload(state, state.assets[0].asset_id, key, true);
  assert.deepEqual(body, {asset_id: state.assets[0].asset_id, source_sha256: state.assets[0].checksum_sha256, idempotency_key: key, rights: []});
  assert.throws(() => audioCreatePayload(state, body.asset_id, key, 1));
});
test('all writes deny viewer, busy, unsaved Studio drafts, source and timeline drift', () => {
  for (const mutate of [s => s.principal.platform_role = 'viewer', s => s.busy = true, s => s.dirty = true,
    s => s.assets[0].checksum_sha256 = 'b'.repeat(64), s => s.timeline = {current_version: 2}]) {
    const {state, original} = fixture(); state.principal.workspace_roles = {}; mutate(state);
    assert.throws(() => audioTextPayload(state, original, textEdit(original)));
    assert.throws(() => audioWordsPayload(state, original, wordEdit(original), true));
    assert.throws(() => audioRestorePayload(state, captured.restored, original.current.transcript_id, true));
  }
});
test('foreign parent/job/history, duplicate snapshots and approval promotion refuse read', () => {
  for (const mutate of [r => r.project_id = 'prj_foreign', r => r.workspace_id = 'wsp_foreign', r => r.publishing_enabled = true,
    r => r.human_review_required = false, r => r.source_media_mutated = true, r => r.job.request.source_sha256 = 'b'.repeat(64),
    r => r.job.request.audio_id = 'aud_' + 'b'.repeat(24), r => r.current.analysis_id = 'anl_foreign',
    r => r.versions.push(clone(r.versions[0])), r => r.original.segments[0].text = 'tampered']) {
    const {state, restored} = fixture(); mutate(restored); assert.throws(() => validateAudioRead(restored, state));
  }
});
test('manual word intervals reject blank, missing, NaN, overlaps, out-of-source and foreign identity', () => {
  for (const mutate of [s => s.words[0].text = ' ', s => s.words[0].start_seconds = '', s => s.words[0].start_seconds = NaN,
    s => s.words[1].start_seconds = .3, s => s.end_seconds = 3, s => s.words[0].word_id = 'wrd_' + 'f'.repeat(24)]) {
    const {state, original} = fixture(), segments = wordEdit(original); mutate(segments[0]);
    assert.throws(() => audioWordsPayload(state, original, segments, true));
  }
  assert.throws(() => audioWordsPayload(captured.state, captured.original, wordEdit(), false));
});
test('restore requires explicit acknowledgement, scoped old target and current CAS', () => {
  const {state, original, restored} = fixture(); const body = audioRestorePayload(state, restored, original.current.transcript_id, true);
  assert.equal(body.expected_version, 4); assert.equal(body.expected_transcript_id, restored.current.transcript_id);
  assert.equal(body.source_sha256, original.source_sha256); assert.equal(body.expected_timeline_version, null);
  assert.throws(() => audioRestorePayload(state, restored, restored.current.transcript_id, true));
  assert.throws(() => audioRestorePayload(state, restored, original.current.transcript_id, false));
});
test('bound audio captions surface a concrete limitation and prevent silent timeline mutation', () => {
  const {state, original} = fixture(); state.timeline = {current_version: 1, snapshot: {tracks: [{clips: [{kind: 'subtitle', metadata: {transcript_id: original.current.transcript_id}}]}]}};
  original.timeline_version = 1; assert.throws(() => audioTextPayload(state, original, textEdit()), /liên kết hiện tại chưa khớp/);
});
function emptyTimeline(state, version = 1) {
  return {timeline_id: 'tl_fixture_audio', workspace_id: state.workspaceId, project_id: state.projectId, current_version: version,
    snapshot: {duration_seconds: 2, metadata: {}, tracks: [{track_id: 'trk_clock_fixture', type: 'metadata', kind: 'metadata', clips: []}]}};
}
function boundTimeline(state, value, version = 2) {
  const timeline = emptyTimeline(state, version), id = 'abn_' + 'c'.repeat(24);
  timeline.snapshot.metadata.uploaded_audio_bindings_v1 = {[value.audio_id]: {audio_id: value.audio_id, binding_id: id,
    source_sha256: value.source_sha256, transcript_id: value.current.transcript_id, transcript: clone(value.current),
    voice_track_id: 'trk_audio_fixture', subtitle_track_id: 'trk_caption_fixture', human_review_required: true}};
  timeline.snapshot.tracks.push({track_id: 'trk_audio_fixture', type: 'audio', kind: 'voice', clips: [{kind: 'voice', asset_id: value.asset_id,
    metadata: {audio_binding_id: id, source_asset_sha256: value.source_sha256}}]},
  {track_id: 'trk_caption_fixture', kind: 'subtitles', clips: [{kind: 'subtitle', metadata: {audio_binding_id: id, transcript_id: value.current.transcript_id}}]});
  return timeline;
}
test('explicit caption apply binds current source/transcript/timeline without an implicit media addition', () => {
  const {state, original} = fixture(); state.timeline = emptyTimeline(state); original.timeline_version = 1;
  const fields = {source_start: 0, source_end: 2, timeline_start: 0, speed: 1, mute_original: false, acknowledged: true};
  const body = audioCaptionPayload(state, original, key, fields);
  assert.equal(body.expected_timeline_version, 1); assert.equal(body.expected_transcript_id, original.current.transcript_id);
  for (const change of [f => f.acknowledged = false, f => f.source_end = 3, f => f.source_start = .5, f => f.speed = 0,
    f => f.speed = 9, f => f.source_end = NaN, f => f.timeline_start = 2]) {
    const changed = clone(fields); change(changed);
    if (changed.source_start === .5) changed.source_end = .4;
    assert.throws(() => audioCaptionPayload(state, original, key, changed));
  }
  const missing = clone(state); missing.timeline = null; assert.throws(() => audioCaptionPayload(missing, {...original, timeline_version: null}, key, fields));
});
test('apply requires reviewing existing captions, speech and locked original audio before writing', () => {
  const fields = {source_start: 0, source_end: 2, timeline_start: 0, speed: 1, mute_original: false, acknowledged: true};
  for (const track of [{kind: 'subtitles', clips: [{}]}, {type: 'audio', kind: 'voice', clips: [{volume: 1}]},
    {type: 'audio', kind: 'original_audio', locked: true, clips: [{volume: 1}]}]) {
    const {state, original} = fixture(); state.timeline = emptyTimeline(state); state.timeline.snapshot.tracks.push(track); original.timeline_version = 1;
    assert.throws(() => audioCaptionPayload(state, original, key, {...fields, mute_original: true}));
  }
  const {state, original} = fixture(); state.timeline = emptyTimeline(state); state.timeline.snapshot.tracks.push({type: 'audio', kind: 'original_audio', clips: [{volume: 1}]}); original.timeline_version = 1;
  assert.throws(() => audioCaptionPayload(state, original, key, fields));
  assert.equal(audioCaptionPayload(state, original, key, {...fields, mute_original: true}).mute_original, true);
});
test('matching canonical binding permits edits while lock/manual/foreign/current drift fail closed', () => {
  const {state, original} = fixture(); state.timeline = boundTimeline(state, original); original.timeline_version = 2;
  assert.equal(compatibleAudioBinding(state, original), true); assert.doesNotThrow(() => audioTextPayload(state, original, textEdit()));
  const b = state.timeline.snapshot.metadata.uploaded_audio_bindings_v1[original.audio_id];
  b.transcript = Object.fromEntries(Object.entries(b.transcript).reverse()); assert.equal(compatibleAudioBinding(state, original), true, 'JSONB key order has no authority');
  for (const change of [s => s.timeline.snapshot.tracks.at(-1).locked = true, s => s.timeline.snapshot.tracks.at(-1).clips[0].metadata.human_caption_edit = true,
    s => s.timeline.snapshot.tracks.at(-1).clips[0].metadata.audio_binding_id = 'foreign', s => s.timeline.snapshot.metadata.uploaded_audio_bindings_v1[original.audio_id].transcript_id = 'foreign']) {
    const changed = clone(state); change(changed); assert.throws(() => audioTextPayload(changed, original, textEdit()));
  }
});
test('caption form dispatches nothing until explicit typed bounds and acknowledgement then refreshes canonical state', async () => {
  const row = clone(captured.original); row.timeline_version = 1; const after = {...clone(row), timeline_version: 2};
  const h = harness({values: [row], transport: (path, body) => {
    if (body && path.endsWith('/apply-captions')) return {audio_id: row.audio_id, binding_id: 'abn_' + 'c'.repeat(24), applied_timeline_version: 2, replayed: false, human_review_required: true};
    if (path.endsWith('/' + row.audio_id)) return clone(after);
  }, canonicalSaved: data => {data.state.timeline = boundTimeline(data.state, after);}});
  h.state.timeline = emptyTimeline(h.state); await h.click('read'); assert.equal(h.calls.some(c => c.method === 'POST'), false);
  await h.click('apply'); assert.equal(h.calls.some(c => c.method === 'POST'), false);
  h.get('source-end').value = '2'; h.check('apply-ack'); await h.click('apply');
  const write = h.calls.find(c => c.method === 'POST'); assert.match(write.path, /apply-captions$/); assert.equal(write.body.source_end, 2);
  assert.equal(write.body.acknowledged, true); assert.equal(write.body.mute_original, false); assert.equal(h.data.canonicalSaved, 1);
  assert.match(h.get('warning').textContent, /đã gắn đúng/); assert.equal(h.get('apply').disabled, true);
});
test('ambiguous caption apply freezes its original key and bounds; retry uses backend idempotent receipt', async () => {
  const row = clone(captured.original); row.timeline_version = 1; const after = {...clone(row), timeline_version: 2}; let attempt = 0;
  const h = harness({values: [row], transport: (path, body) => {
    if (body && path.endsWith('/apply-captions')) {if (++attempt === 1) throw Error('lost apply receipt'); return {audio_id: row.audio_id, binding_id: 'abn_' + 'c'.repeat(24), applied_timeline_version: 2, replayed: true, human_review_required: true};}
    if (path.endsWith('/' + row.audio_id)) return clone(after);
  }, canonicalSaved: data => {data.state.timeline = boundTimeline(data.state, after);}});
  h.state.timeline = emptyTimeline(h.state); await h.click('read'); h.get('source-end').value = '2'; h.check('apply-ack'); await h.click('apply');
  assert.equal(h.controller.isDirty(), true); assert.equal(h.get('source-end').disabled, true); h.get('source-end').value = '1'; await h.click('apply');
  const writes = h.calls.filter(c => c.method === 'POST'); assert.equal(writes.length, 2); assert.deepEqual(writes[0], writes[1]); assert.equal(h.controller.isDirty(), false);
});
test('historical view cannot apply latest transcript unseen and changing history resets acknowledgement', async () => {
  const row = clone(captured.text); row.timeline_version = 1; const h = harness({values: [row]}); h.state.timeline = emptyTimeline(h.state);
  await h.click('read'); h.get('source-end').value = '2'; h.check('apply-ack'); h.change('history', captured.original.current.transcript_id);
  assert.equal(h.get('apply-ack').checked, false); h.check('apply-ack'); await h.click('apply');
  assert.equal(h.calls.filter(c => c.method === 'POST').length, 0); assert.equal(h.get('apply').disabled, true);
});
test('source picker changes saved request/editor together and resets all action acknowledgements', async () => {
  const h = harness(); const second = clone(h.state.assets[0]); second.asset_id = 'ast_sql_audio_other_fixture'; second.filename = 'other.wav'; h.state.assets.push(second);
  await h.click('read'); h.check('request-ack'); h.get('source-end').value = '2'; h.check('apply-ack'); h.change('source', second.asset_id);
  assert.equal(h.get('editor').children.length, 0); assert.equal(h.get('listen').disabled, true);
  assert.equal(h.get('request-ack').checked, false); assert.equal(h.get('apply-ack').checked, false); assert.equal(h.get('source-end').value, '');
});
test('bound text save refreshes canonical state and uses the same timeline CAS while keeping original evidence', async () => {
  const row = clone(captured.original); row.timeline_version = 2; const after = {...clone(captured.text), timeline_version: 3};
  const h = harness({values: [row], transport: (path, body) => body && path.endsWith('/transcript') ? clone(after) : undefined,
    canonicalSaved: data => {data.state.timeline = boundTimeline(data.state, after, 3);}});
  h.state.timeline = boundTimeline(h.state, row); await h.click('read'); h.textDraft('Chữ do người dùng sửa.'); await h.click('save-text');
  const write = h.calls.find(c => c.method === 'POST'); assert.equal(write.body.edit.expected_timeline_version, 2);
  assert.equal(h.data.canonicalSaved, 1); assert.equal(h.state.timeline.current_version, 3); assert.equal(h.get('history').children.length, 2);
  assert.equal(h.controller.isDirty(), false); assert.match(h.get('warning').textContent, /duyệt video lại/);
});
test('initialization has no network/provider I/O and uses text nodes for untrusted labels', () => {
  const h = harness(); assert.deepEqual(h.calls, []); assert.deepEqual(h.media, []);
  assert.ok(h.all().every(n => n.innerHTML === undefined)); assert.match(h.get('provider').textContent, /NOT_CONFIGURED/);
  assert.equal(h.get('queue').disabled, true); assert.equal(h.get('player').hidden, true);
});
test('read uses only authenticated GETs and visibly labels captured MockASR fixture', async () => {
  const h = harness(); await h.click('read'); assert.equal(h.calls.length, 2); assert.ok(h.calls.every(c => c.method === 'GET'));
  assert.match(h.get('evidence').textContent, /FIXTURE.*không phải ASR thật/); assert.match(h.get('job').textContent, /cần nghe và kiểm tra/);
  assert.match(h.get('provider').textContent, /NOT_CONFIGURED/); assert.equal(h.media.length, 0);
});
test('viewer reads and hears source but cannot upload, queue, edit, restore or cancel', async () => {
  const h = harness(); h.state.principal.platform_role = 'viewer'; h.state.principal.workspace_roles = {}; h.controller.sync(); await h.click('read');
  assert.equal(h.get('listen').disabled, false); for (const n of ['queue', 'upload', 'save-text', 'save-words', 'restore', 'cancel']) assert.equal(h.get(n).disabled, true);
  h.check('request-ack'); await h.click('queue'); assert.equal(h.calls.filter(c => c.method === 'POST').length, 0);
});
test('NOT_CONFIGURED is an actual blocked API response with no fake result or fallback retry', async () => {
  const h = harness({values: [], transport: (_path, body) => {if (body) throw Object.assign(Error('blocked'), {status: 503, detail: {error: {code: 'AUDIO_PROVIDER_NOT_CONFIGURED'}}});}});
  await h.click('read'); h.check('request-ack'); await h.click('queue');
  assert.match(h.get('status').textContent, /NOT_CONFIGURED.*Không có lời nhận diện giả/);
  assert.equal(h.calls.filter(c => c.method === 'POST').length, 1); assert.equal(h.controller.isDirty(), false);
  assert.equal(h.get('saved').children.length, 0); assert.equal(h.timeouts.size, 0);
});
test('explicit queued create uses frozen key and reads status through bounded GET polling only', async () => {
  const h = harness({values: []}); await h.click('read'); h.check('request-ack'); await h.click('queue');
  const write = h.calls.find(c => c.method === 'POST'); assert.equal(write.body.idempotency_key, key); assert.match(h.get('job').textContent, /Đang chờ/);
  assert.equal(h.timeouts.size, 1); assert.equal(h.get('queue').disabled, true);
  const poll = [...h.timeouts.values()][0]; h.timeouts.clear(); await poll();
  await new Promise(resolve => setImmediate(resolve)); assert.equal(h.calls.filter(c => c.method === 'POST').length, 1);
  assert.ok(h.calls.slice(3).every(c => c.method === 'GET'));
});
test('needs_attention never creates a new recognition request and offers explicit cancellation', async () => {
  const row = clone(captured.original); row.current = row.original = null; row.versions = []; row.job.status = 'needs_attention'; row.job.error = {code: 'AUDIO_PROVIDER_OUTCOME_UNKNOWN'};
  const h = harness({values: [row]}); await h.click('read'); h.check('request-ack'); await h.click('queue');
  assert.equal(h.calls.filter(c => c.method === 'POST').length, 0); assert.equal(h.get('cancel').disabled, false);
  assert.match(h.get('job').textContent, /không tự chạy lại/); assert.equal(h.timeouts.size, 0);
});
test('ambiguous create keeps the exact original key/body and locks changing the source', async () => {
  let writes = 0; const h = harness({values: [], transport: (_path, body, data) => {if (body) {if (++writes === 1) throw Error('lost response'); return requestResult(data.state, body);}}});
  await h.click('read'); h.check('request-ack'); await h.click('queue'); assert.equal(h.controller.isDirty(), true); assert.equal(h.get('source').disabled, true);
  h.get('request-ack').checked = false; await h.click('queue'); const posted = h.calls.filter(c => c.method === 'POST');
  assert.equal(posted.length, 2); assert.deepEqual(posted[0], posted[1]); assert.equal(h.controller.isDirty(), false);
});
test('ambiguous create can reconcile deterministic server parent through GET without another provider request', async () => {
  let posted; const h = harness({values: [], transport: (path, body, data) => {
    if (body) {posted = requestResult(data.state, body); throw Error('lost response');}
    if (posted && path.endsWith('/' + posted.audio_id)) return clone(posted);
  }});
  await h.click('read'); h.check('request-ack'); await h.click('queue'); await h.click('reconcile');
  assert.equal(h.calls.filter(c => c.method === 'POST').length, 1); assert.equal(h.controller.isDirty(), false); assert.match(h.get('job').textContent, /Đang chờ/);
});
test('late read after project change cannot expose previous source history', async () => {
  let finish; const h = harness({transport: path => path.endsWith('/audio-transcriptions') ? new Promise(resolve => finish = resolve) : undefined});
  const reading = h.click('read'); h.state.projectId = 'prj_foreign'; h.controller.sync(); finish([clone(h.original)]); await reading;
  assert.equal(h.get('saved').children.length, 0); assert.equal(h.get('editor').children.length, 0); assert.equal(h.get('listen').disabled, true);
});
test('late write after role/source drift cannot replace local editor or authorize new writes', async () => {
  for (const drift of [h => h.state.principal.platform_role = 'viewer', h => h.state.assets[0].checksum_sha256 = 'b'.repeat(64)]) {
    let finish; const h = harness({transport: (_path, body) => body ? new Promise(resolve => finish = resolve) : undefined});
    h.state.principal.workspace_roles = {}; await h.click('read'); h.textDraft('Chữ do người dùng sửa.');
    const saving = h.click('save-text'); drift(h); h.controller.sync(); finish(clone(h.text)); await saving;
    assert.equal(h.get('save-text').disabled, true); assert.equal(h.get('listen').disabled, true);
  }
});
test('dirty audio drafts pause polling and block reload, selection, queue and cancellation without losing text', async () => {
  const h = harness(); await h.click('read'); h.textDraft('Lời đang sửa <script>không thực thi</script>');
  const count = h.calls.length; await h.click('read'); h.check('request-ack'); await h.click('queue'); await h.click('cancel');
  assert.equal(h.calls.length, count); assert.equal(h.textInput().value, 'Lời đang sửa <script>không thực thi</script>');
  assert.equal(h.get('history').disabled, true); await h.click('discard'); assert.equal(h.controller.isDirty(), false);
  assert.equal(h.textInput().value, captured.original.current.segments[0].text);
});
test('text save sends only changed segments and frozen source/transcript/timeline CAS', async () => {
  const h = harness({transport: (path, body) => body && path.endsWith('/transcript') ? clone(captured.text) : undefined});
  await h.click('read'); h.textDraft('Chữ do người dùng sửa.'); await h.click('save-text');
  const write = h.calls.find(c => c.method === 'POST'); assert.equal(write.path.endsWith('/transcript'), true);
  assert.deepEqual(write.body, audioTextPayload(h.state, captured.original, textEdit()));
  assert.equal(h.get('history').children.length, 2); assert.equal(h.controller.isDirty(), false);
});
test('word editor requires manual timings and acknowledgement; it never estimates time for a new word', async () => {
  const h = harness(); await h.click('read');
  const input = h.all().find(n => n.tagName === 'input' && n.type === 'text'); input.value = 'Chào'; input.listeners.input();
  await h.click('save-words'); assert.equal(h.calls.filter(c => c.method === 'POST').length, 0);
  const add = h.all().find(n => n.textContent === 'Thêm từ (tự nhập thời gian)'); add.listeners.click();
  const numeric = h.get('editor').querySelectorAll('input').filter(n => n.type === 'number'); assert.equal(numeric.at(-1).value, ''); assert.equal(numeric.at(-2).value, '');
  h.check('word-ack'); await h.click('save-words'); assert.equal(h.calls.filter(c => c.method === 'POST').length, 0);
});
test('separate text/timing edits cannot silently discard each other', async () => {
  const h = harness(); await h.click('read'); h.textDraft('Text edit');
  const numeric = h.all().find(n => n.tagName === 'input' && n.type === 'number'); numeric.value = '.15'; numeric.listeners.input();
  h.check('word-ack'); await h.click('save-text'); await h.click('save-words'); assert.equal(h.calls.filter(c => c.method === 'POST').length, 0);
  assert.equal(h.controller.isDirty(), true);
});
test('ambiguous text retry keeps exact CAS and content; an unchanged read does not falsely declare completion', async () => {
  let attempts = 0; const h = harness({transport: (path, body) => {if (body && path.endsWith('/transcript')) {if (++attempts === 1) throw Error('lost response'); return clone(captured.text);}}});
  await h.click('read'); h.textDraft('Chữ do người dùng sửa.'); await h.click('save-text'); await h.click('reconcile');
  assert.equal(h.controller.isDirty(), true); assert.match(h.get('status').textContent, /có thể còn đang xử lý/);
  await h.click('save-text'); const writes = h.calls.filter(c => c.method === 'POST'); assert.equal(writes.length, 2); assert.deepEqual(writes[0], writes[1]);
  assert.equal(h.controller.isDirty(), false);
});
test('unknown edit reconciliation preserves own dirty draft when another actor or unrelated higher version appears', async () => {
  for (const mutate of [r => r.current.provenance.actor_ref = 'usr:other-editor', r => r.current.segments[0].text = 'Someone else changed this',
    r => r.current.provenance.derived_from_transcript_id = captured.restored.current.transcript_id]) {
    const foreign = clone(captured.text); mutate(foreign);
    // Keep aliases consistent where a response passes the shared read contract.
    foreign.versions[1] = clone(foreign.current);
    const h = harness({transport: (path, body) => {
      if (body) throw Error('lost edit response');
      if (path.endsWith('/' + captured.original.audio_id)) return clone(foreign);
    }});
    await h.click('read'); h.textDraft('Chữ do người dùng sửa.'); await h.click('save-text'); await h.click('reconcile');
    assert.equal(h.controller.isDirty(), true); assert.equal(h.textInput().value, 'Chữ do người dùng sửa.');
    assert.equal(h.get('history').children.length, 1); assert.equal(h.calls.filter(c => c.method === 'POST').length, 1);
    assert.equal(h.get('discard').disabled, true);
  }
});
test('unknown edit reconciles only the exact actor, payload, original and immediate immutable append', async () => {
  const body = audioTextPayload(captured.state, captured.original, textEdit());
  assert.equal(audioRevisionMatches(captured.text, captured.original, 'text', body, captured.state.principal.subject), true);
  assert.equal(audioRevisionMatches(captured.restored, captured.original, 'text', body, captured.state.principal.subject), false);
  const h = harness({transport: (path, posted) => {
    if (posted) throw Error('lost edit response'); if (path.endsWith('/' + captured.original.audio_id)) return clone(captured.text);
  }});
  await h.click('read'); h.textDraft('Chữ do người dùng sửa.'); await h.click('save-text'); await h.click('reconcile');
  assert.equal(h.controller.isDirty(), false); assert.equal(h.get('history').children.length, 2);
  assert.equal(h.calls.filter(c => c.method === 'POST').length, 1);
});
test('ambiguous create survives browser recreation and reconciles its stored key without a new ASR POST', async () => {
  const store = new Map(); let result;
  const first = harness({values: [], storageMap: store, transport: (_path, body, data) => {if (body) {result = requestResult(data.state, body); throw Error('lost create response');}}});
  await first.click('read'); first.check('request-ack'); await first.click('queue'); assert.equal(store.size, 1); first.controller.dispose();
  const second = harness({storageMap: store, transport: path => path.endsWith('/' + result.audio_id) ? clone(result) : undefined});
  assert.equal(second.controller.isDirty(), true); assert.equal(second.get('source').disabled, true); await second.click('reconcile');
  assert.equal(second.calls.some(c => c.method === 'POST'), false); assert.equal(second.controller.isDirty(), false); assert.equal(store.size, 0);
});
test('unavailable persistent request storage blocks recognition before dispatch', async () => {
  const h = harness({values: [], storageImpl: {getItem: () => null, setItem: () => {throw Error('storage denied');}, removeItem() {}}});
  await h.click('read'); h.check('request-ack'); await h.click('queue');
  assert.equal(h.calls.some(c => c.method === 'POST'), false); assert.match(h.get('status').textContent, /chưa được gửi/);
});
test('valid manual word review from a text-only version sends explicit intervals and creates one new snapshot', async () => {
  const h = harness({values: [captured.text], transport: (path, body) => body && path.endsWith('/transcript-words') ? clone(captured.words) : undefined});
  await h.click('read'); h.all().find(n => n.textContent === 'Thêm từ (tự nhập thời gian)').listeners.click();
  const input = h.all().find(n => n.tagName === 'input' && n.type === 'text'); input.value = 'Chữ do người dùng sửa.'; input.listeners.input();
  const timing = h.get('editor').querySelectorAll('input').filter(n => n.type === 'number');
  timing.at(-2).value = '.1'; timing.at(-2).listeners.input(); timing.at(-1).value = '.9'; timing.at(-1).listeners.input();
  h.check('word-ack'); await h.click('save-words'); const write = h.calls.find(c => c.method === 'POST');
  assert.equal(write.body.edit.expected_version, 2); assert.equal(write.body.edit.acknowledged, true);
  assert.deepEqual(write.body.edit.segments[0].words, [{text: 'Chữ do người dùng sửa.', start_seconds: .1, end_seconds: .9}]);
  assert.equal(h.controller.isDirty(), false); assert.equal(h.get('history').children.length, 3);
});
test('explicit cancel reads terminal status and never creates a second recognition job', async () => {
  const queued = clone(captured.original); queued.original = queued.current = null; queued.versions = []; queued.job.status = 'queued';
  const h = harness({values: [queued], transport: (path, body) => body && path.endsWith('/cancel') ? {...clone(queued), job: {...clone(queued.job), status: 'cancelled'}} : undefined});
  await h.click('read'); await h.click('cancel'); assert.equal(h.calls.filter(c => c.method === 'POST').length, 1);
  assert.match(h.get('job').textContent, /Đã hủy/); assert.equal(h.timeouts.size, 0);
});
test('GET polling of an active job keeps an already verified original player usable', async () => {
  const queued = clone(captured.original); queued.original = queued.current = null; queued.versions = []; queued.job.status = 'queued';
  const h = harness({values: [queued]}); await h.click('read'); await h.click('listen'); const url = h.get('player').src;
  const polling = [...h.timeouts.values()][0]; h.timeouts.clear(); await polling(); await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.get('player').src, url); assert.equal(h.get('player').hidden, false); assert.equal(h.revoked.length, 0);
});
test('a stale edit rejection retains user draft and never blindly replays', async () => {
  const h = harness({transport: (_path, body) => {if (body) throw Object.assign(Error('AUDIO_VERSION_CHANGED'), {status: 409});}});
  await h.click('read'); h.textDraft('Draft to preserve'); await h.click('save-text'); assert.equal(h.controller.isDirty(), true);
  assert.equal(h.textInput().value, 'Draft to preserve'); assert.equal(h.calls.filter(c => c.method === 'POST').length, 1); assert.equal(h.timeouts.size, 0);
});
test('history is read only and explicit restore appends a snapshot without rewriting the original', async () => {
  // The words response has three versions; restore API returns version four.
  const h = harness({values: [captured.words], transport: (path, body) => body && path.endsWith('/restore') ? clone(captured.restored) : undefined});
  await h.click('read'); h.change('history', captured.original.current.transcript_id);
  assert.equal(h.textInput().disabled, true); await h.click('restore'); assert.equal(h.calls.filter(c => c.method === 'POST').length, 0);
  h.check('restore-ack'); await h.click('restore'); const write = h.calls.find(c => c.method === 'POST');
  assert.equal(write.body.target_transcript_id, captured.original.current.transcript_id); assert.equal(write.body.expected_version, 3);
  assert.equal(h.get('history').children.length, 4); assert.equal(h.get('restore-ack').checked, false);
});
test('authenticated original source playback verifies actual WAV bytes, size, MIME and hash before Blob URL', async () => {
  const h = harness(); await h.click('read'); assert.equal(h.media.length, 0); await h.click('listen');
  assert.equal(h.media.length, 1); assert.match(h.media[0].path, /\/source$/); assert.equal(h.media[0].options.cache, 'no-store');
  assert.equal(h.created.length, 1); assert.equal(h.get('player').src, 'blob:owned-1'); assert.equal(h.get('player').hidden, false);
  assert.deepEqual(Buffer.from(await h.created[0].arrayBuffer()), wav); h.controller.dispose(); assert.deepEqual(h.revoked, ['blob:owned-1']);
});
test('tampered MIME, size or checksum never reaches audio playback', async () => {
  for (const [bytes, headers] of [[wav, {...captured.source.headers, 'content-type': 'text/html'}], [wav.subarray(0, 32), captured.source.headers],
    [Buffer.alloc(wav.length), captured.source.headers]]) {
    const h = harness({fetcher: () => new Response(bytes, {status: 200, headers})}); await h.click('read'); await h.click('listen');
    assert.equal(h.created.length, 0); assert.equal(h.get('player').hidden, true);
  }
});
test('late source download after switching projects or changing source checksum is discarded', async () => {
  for (const drift of [h => h.state.projectId = 'prj_foreign', h => h.state.assets[0].checksum_sha256 = 'b'.repeat(64)]) {
    let finish; const h = harness({fetcher: () => new Promise(resolve => finish = resolve)}); await h.click('read'); const playing = h.click('listen');
    drift(h); h.controller.sync(); finish(new Response(wav, {status: 200, headers: captured.source.headers})); await playing;
    assert.equal(h.created.length, 0); assert.equal(h.get('player').hidden, true);
  }
});
test('multipart speech upload verifies actual file SHA and chunk SHA, then requires trusted completed source', async () => {
  let session; const h = harness({transport: (path, body, data) => {
    if (path === '/api/v1/uploads/init') {assert.equal(body.media_kind, 'audio'); assert.equal(body.checksum_sha256, data.original.source_sha256);
      session = {upload_id: 'upl_sql_audio_ui_fixture', project_id: data.state.projectId, workspace_id: data.state.workspaceId,
        media_kind: 'audio', size_bytes: wav.length, expected_checksum_sha256: body.checksum_sha256, part_size_bytes: 65536,
        total_parts: 1, received_parts: [], status: 'initialized'}; return clone(session);}
    if (path.endsWith('/complete')) {assert.equal(body.checksum_sha256, data.original.source_sha256); return {upload: {...session,
      asset_id: data.original.asset_id, status: 'completed', quarantine_state: 'trusted'}, checksum_sha256: body.checksum_sha256,
      asset_id: data.original.asset_id, media_metadata: {media_kind: 'audio'}};}
  }, fetcher: async (_path, options) => {
    assert.equal(options.method, 'PUT'); assert.equal(options.headers['X-Part-SHA256'], await audioByteHash(wav, webcrypto));
    session.received_parts = [{part_number: 1, size_bytes: wav.length, checksum_sha256: options.headers['X-Part-SHA256']}]; session.status = 'uploading';
    return new Response(JSON.stringify(session), {status: 200});
  }});
  await h.click('read'); h.get('file').files = [Object.assign(new Blob([wav], {type: 'audio/wav'}), {name: 'owned-audio.bin'})]; h.get('mime').value = 'audio/wav'; h.check('upload-rights');
  await h.click('upload'); assert.equal(h.data.uploaded, 1); assert.equal(h.media.length, 1); assert.equal(h.controller.isDirty(), false);
  assert.equal(h.calls.some(c => c.path.includes('audio-transcriptions') && c.method === 'POST'), false);
});
test('multipart resume reads the old session after lost part response and never reinitializes or rewrites a matching part', async () => {
  let session, parts = 0; const h = harness({transport: (path, body, data) => {
    if (path === '/api/v1/uploads/init') return session = {upload_id: 'upl_sql_audio_ui_resume', project_id: data.state.projectId, workspace_id: data.state.workspaceId,
      media_kind: 'audio', size_bytes: wav.length, expected_checksum_sha256: data.original.source_sha256, part_size_bytes: 65536,
      total_parts: 1, received_parts: [], status: 'initialized'};
    if (path.endsWith('/upl_sql_audio_ui_resume') && !body) return clone(session);
    if (path.endsWith('/complete')) return {upload: {...session, asset_id: data.original.asset_id, status: 'completed_duplicate', quarantine_state: 'trusted'},
      asset_id: data.original.asset_id, checksum_sha256: data.original.source_sha256, media_metadata: {media_kind: 'audio'}};
  }, fetcher: async (_path, options) => {parts++; session.status = 'uploading'; session.received_parts = [{part_number: 1, size_bytes: wav.length, checksum_sha256: options.headers['X-Part-SHA256']}]; throw Error('lost part response');}});
  await h.click('read'); h.get('file').files = [Object.assign(new Blob([wav]), {name: 'source.wav'})]; h.get('mime').value = 'audio/wav'; h.check('upload-rights');
  await h.click('upload'); assert.equal(h.controller.isDirty(), true); await h.click('upload');
  assert.equal(parts, 1); assert.equal(h.calls.filter(c => c.path === '/api/v1/uploads/init').length, 1); assert.equal(h.data.uploaded, 1);
});
test('upload continuation after project or role drift dispatches no new chunks or completion', async () => {
  let finish, entered; const started = new Promise(resolve => entered = resolve);
  const h = harness({transport: (path, body) => path === '/api/v1/uploads/init' ? new Promise(resolve => {finish = resolve; entered();}) : undefined});
  await h.click('read'); h.get('file').files = [Object.assign(new Blob([wav]), {name: 'source.wav'})]; h.get('mime').value = 'audio/wav'; h.check('upload-rights');
  const loading = h.click('upload'); await started; h.state.projectId = 'prj_foreign'; h.controller.sync(); finish({}); await loading;
  assert.equal(h.media.length, 0); assert.equal(h.calls.filter(c => c.path.endsWith('/complete')).length, 0);
});
test('playback refuses sources over 32 MiB before fetching and aborts active downloads on scope change', async () => {
  const large = harness(); large.state.assets[0].size_bytes = 32 * 1024 * 1024 + 1; await large.click('read'); await large.click('listen');
  assert.equal(large.media.length, 0); assert.match(large.get('status').textContent, /32 MiB/);
  let finish; const h = harness({fetcher: () => new Promise(resolve => finish = resolve)}); await h.click('read'); const playing = h.click('listen');
  const signal = h.media[0].options.signal; assert.equal(signal.aborted, false); h.state.projectId = 'prj_foreign'; h.controller.sync(); assert.equal(signal.aborted, true);
  finish(new Response(wav, {headers: captured.source.headers})); await playing; assert.equal(h.created.length, 0);
});
test('bounded source reader rejects missing/spoofed length, partial bodies and overflow while cancelling the stream', async () => {
  await assert.rejects(() => boundedAudioBytes(new Response(wav), wav.length), /Kích thước/);
  await assert.rejects(() => boundedAudioBytes(new Response(wav.subarray(0, 32), {headers: {'content-length': String(wav.length)}}), wav.length), /chưa tải đầy đủ/);
  let cancelled = false; const overflow = new Response(new ReadableStream({start(c) {c.enqueue(new Uint8Array(17));}, cancel() {cancelled = true;}}),
    {headers: {'content-length': '16'}});
  await assert.rejects(() => boundedAudioBytes(overflow, 16), /vượt kích thước/); assert.equal(cancelled, true);
  await assert.rejects(() => boundedAudioBytes(new Response(wav, {headers: {'content-length': '50000000'}}), wav.length), /Kích thước/);
});
test('SQL HTML and bounded Studio integration keep speech panel discoverable and separate from video analysis', () => {
  const html = readFileSync(new URL('../studio.html', import.meta.url), 'utf8'); const source = readFileSync(new URL('../studio.js', import.meta.url), 'utf8');
  assert.match(html, /id="uploaded-audio-review"[^>]*open/); assert.match(source, /initializeUploadedAudioReview/);
  assert.match(source, /mediaFetch: authenticatedFetch/); assert.match(source, /audioReview\.isDirty\(\)/);
  assert.match(source, /multiInputBaseline = audioWorkbenchDraft/); assert.match(source, /audioReview\.dispose\(\)/);
});
