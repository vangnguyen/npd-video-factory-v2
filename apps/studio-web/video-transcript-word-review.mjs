// Saved SQL video words. Explicit revisions share the canonical transcript/timeline CAS.
import {audioRole, audioByteHash} from './uploaded-audio-review.mjs';
import {videoAnalysisAssets} from './video-analysis-jobs.mjs';
import {loadVariantReceipt, verifiedVariantReceipt} from './verified-variant-source.mjs';
import {sessionToken as browserSessionToken} from './auth.mjs';

const ids = {analysis: /^ana_[a-f0-9]{24}$/, transcript: /^trn_[a-f0-9]{24}$/,
  segment: /^seg_[a-f0-9]{24}$/, word: /^wrd_[a-f0-9]{24}$/};
const copy = structuredClone;
const stable = value => JSON.stringify(value, (_key, v) => v && typeof v === 'object' && !Array.isArray(v)
  ? Object.fromEntries(Object.keys(v).sort().map(k => [k, v[k]])) : v);
const same = (a, b) => stable(a) === stable(b);
const demand = (ok, text) => {if (!ok) throw Error(text);};
function seconds(input) {
  demand(typeof input.value === 'string' && input.value === input.value.trim()
    && /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(input.value)
    && Number.isFinite(Number(input.value)), 'Điền số giây rõ ràng; ô trống không được đổi thành 0.');
  return Number(input.value);
}
const freeze = value => {if (value && typeof value === 'object') {Object.values(value).forEach(freeze); Object.freeze(value);} return value;};
const scope = s => stable([s.workspaceId, s.projectId, s.principal?.subject, s.principal?.token_id,
  s.principal?.expires_at, audioRole(s)]);
function session(s, write = false) {
  demand(s.workspaceId && s.projectId && typeof s.principal?.subject === 'string' && s.principal.subject
    && typeof s.principal.token_id === 'string' && s.principal.token_id && Number.isFinite(Date.parse(s.principal.expires_at))
    && Date.parse(s.principal.expires_at) > Date.now() && ['viewer', 'editor', 'reviewer', 'owner'].includes(audioRole(s)),
  'Cần phiên truy cập còn hiệu lực của dự án.');
  if (write) demand(['editor', 'reviewer', 'owner'].includes(audioRole(s)), 'Cần quyền biên tập để sửa từ.');
  demand(!s.busy && !s.dirty, 'Lưu thay đổi khác và chờ Studio tải xong trước khi kiểm tra từ.');
}
function source(s, analysis) {
  const asset = videoAnalysisAssets(s).find(a => a.asset_id === analysis?.asset_id);
  demand(asset && analysis.project_id === s.projectId && analysis.workspace_id === s.workspaceId,
    'Kết quả hoặc video nguồn không còn thuộc dự án hiện tại.');
  return asset;
}
function rootBinding(s) {
  const a = s.analysis;
  return stable([scope(s), a, a ? source(s, a) : null, s.timeline]);
}
function sourceIdentity(s, analysis) {return stable([scope(s), source(s, analysis)]);}
export function validateVideoWords(analysis, s) {
  const asset = source(s, analysis), t = analysis.transcript, limit = asset.provenance.media_metadata.duration_seconds;
  demand(ids.analysis.test(analysis.analysis_id) && analysis.status === 'succeeded' && analysis.source_media_mutated === false
    && analysis.publish_requested === false && analysis.configuration?.asset_id === asset.asset_id
    && typeof analysis.fingerprint === 'string' && /^[a-f0-9]{64}$/.test(analysis.fingerprint)
    && Number.isFinite(analysis.source_media?.duration_seconds) && Math.abs(analysis.source_media.duration_seconds - limit) < .000001,
  'Phân tích video hoặc thời lượng nguồn không khớp.');
  demand(t && ids.transcript.test(t.transcript_id) && t.analysis_id === analysis.analysis_id && t.asset_id === asset.asset_id
    && Number.isInteger(t.version) && t.version >= 1 && typeof t.is_original_evidence === 'boolean'
    && typeof t.provider_key === 'string' && typeof t.language === 'string' && t.provenance && Array.isArray(t.segments)
    && t.segments.length <= 1000, 'Transcript chưa sẵn sàng hoặc sai nguồn.');
  for (const key of ['source_checksum', 'source_asset_sha256']) demand(t.provenance[key] == null
    || t.provenance[key] === asset.checksum_sha256, 'Checksum của transcript không khớp video.');
  let end = 0, ordinal = 0; const segments = new Set(), words = new Set();
  for (const segment of t.segments) {
    demand(ids.segment.test(segment.segment_id) && !segments.has(segment.segment_id) && typeof segment.text === 'string'
      && segment.text.trim() && Number.isFinite(segment.start_seconds) && Number.isFinite(segment.end_seconds)
      && segment.start_seconds >= end && segment.end_seconds > segment.start_seconds && segment.end_seconds <= limit
      && Array.isArray(segment.words), 'Đoạn transcript không khớp thời gian nguồn.');
    segments.add(segment.segment_id); end = segment.end_seconds; let previous = segment.start_seconds;
    for (const w of segment.words) {
      demand(ids.word.test(w.word_id) && !words.has(w.word_id) && w.ordinal === ordinal++ && typeof w.text === 'string'
        && w.text.trim() && w.text.length <= 240 && Number.isFinite(w.start_seconds) && Number.isFinite(w.end_seconds)
        && w.start_seconds >= previous && w.end_seconds > w.start_seconds && w.end_seconds <= end
        && (w.confidence === null || Number.isFinite(w.confidence) && w.confidence >= 0 && w.confidence <= 1),
      'Từ hoặc thời gian từng từ không hợp lệ.');
      words.add(w.word_id); previous = w.end_seconds;
    }
  }
  demand(ordinal <= 10000, 'Transcript vượt giới hạn 10.000 từ.');
  return analysis;
}
function selectedId(s, latest) {
  if (!s.timeline) return latest.transcript.transcript_id;
  demand(s.timeline.project_id === s.projectId && s.timeline.workspace_id === s.workspaceId
    && s.timeline.source_analysis_id === latest.analysis_id && Number.isInteger(s.timeline.current_version)
    && s.timeline.current_version >= 1, 'Timeline đang dùng video khác; tải đúng nguồn trước khi sửa.');
  const id = s.timeline.snapshot?.metadata?.transcript_revision?.transcript_id;
  demand(ids.transcript.test(id), 'Timeline chưa xác định transcript đã chọn.'); return id;
}
export function videoWordPayload(s, view, segments, acknowledged, note, key) {
  session(s, true); validateVideoWords(view.latest, s); validateVideoWords(view.selected, s);
  const asset = source(s, view.selected);
  if (asset.provenance.source_type === 'verified_variant_derivative') verifiedVariantReceipt(s, asset);
  demand(view.binding === rootBinding(s) && selectedId(s, view.latest) === view.selected.transcript.transcript_id,
    'Nguồn, transcript hoặc timeline đã đổi; đọc lại trước khi sửa.');
  demand(acknowledged === true, 'Xác nhận các từ và thời gian do bạn kiểm tra trước khi lưu.');
  demand(typeof key === 'string' && /^[A-Za-z0-9._:-]{8,120}$/.test(key)
    && typeof note === 'string' && note.length <= 1800 && Array.isArray(segments) && segments.length > 0 && segments.length <= 1000,
  'Nội dung hoặc mã lần sửa không hợp lệ.');
  const base = view.selected.transcript, changed = new Map(), used = new Set();
  for (const segment of segments) {
    const old = base.segments.find(v => v.segment_id === segment.segment_id);
    demand(old && old.words.length && !changed.has(segment.segment_id) && Number.isFinite(segment.start_seconds)
      && Number.isFinite(segment.end_seconds) && segment.start_seconds >= 0 && segment.end_seconds > segment.start_seconds
      && segment.end_seconds <= asset.provenance.media_metadata.duration_seconds && Array.isArray(segment.words)
      && segment.words.length > 0 && segment.words.length <= 2000, 'Đoạn cần sửa không có thời gian từ hoặc vượt nguồn.');
    let end = segment.start_seconds;
    for (const w of segment.words) {
      demand(old.words.some(v => v.word_id === w.word_id) && !used.has(w.word_id) && typeof w.text === 'string'
        && w.text.trim() && w.text.length <= 240 && Number.isFinite(w.start_seconds) && Number.isFinite(w.end_seconds)
        && w.start_seconds >= end && w.end_seconds > w.start_seconds && w.end_seconds <= segment.end_seconds,
      'Từ trùng, sai nguồn hoặc nằm ngoài khoảng của đoạn.');
      used.add(w.word_id); end = w.end_seconds;
    }
    changed.set(segment.segment_id, segment);
  }
  let end = 0, count = 0;
  for (const old of base.segments) {const item = changed.get(old.segment_id) ?? old;
    demand(item.start_seconds >= end, 'Các đoạn không được chồng thời gian.'); end = item.end_seconds; count += item.words.length;}
  demand(count <= 10000, 'Tối đa 10.000 từ trong một phiên bản.');
  return {expected_version: view.latest.transcript.version, expected_transcript_id: base.transcript_id,
    expected_timeline_version: s.timeline?.current_version ?? null, acknowledged: true, segments: copy(segments),
    note: `${note}${note ? '\n' : ''}Mã lần sửa giao diện: ${key}`};
}
function content(segment) {
  return {text: segment.text, start_seconds: segment.start_seconds, end_seconds: segment.end_seconds,
    speaker: segment.speaker, confidence: segment.confidence,
    words: segment.words.map(w => ({text: w.text, start_seconds: w.start_seconds, end_seconds: w.end_seconds, confidence: w.confidence}))};
}
export function videoWordReceiptMatches(analysis, pending) {
  try {
    const t = analysis.transcript, base = pending.base.transcript, body = pending.body, p = t.provenance;
    if (analysis.analysis_id !== pending.analysisId || analysis.asset_id !== base.asset_id
      || analysis.project_id !== pending.projectId || analysis.workspace_id !== pending.workspaceId
      || t.version !== body.expected_version + 1 || t.analysis_id !== base.analysis_id || t.asset_id !== base.asset_id
      || t.is_original_evidence !== false || t.provider_key !== base.provider_key || t.language !== base.language || t.confidence !== null
      || p.actor_ref !== pending.actor || p.derived_from_transcript_id !== base.transcript_id || p.human_edit !== true
      || p.edit_note !== body.note || p.word_timestamp_policy !== 'human_supplied_source_intervals'
      || p.human_timing_acknowledged !== true || p.timing_independently_measured !== false || p.remote_calls !== 0
      || p.source_media_mutated !== false || p.review_required !== true || t.segments.length !== base.segments.length
      || !same([...p.reviewed_segment_ids].sort(), body.segments.map(v => v.segment_id).sort())) return false;
    const replaced = new Set(['human_edit', 'actor_ref', 'derived_from_transcript_id', 'changed_segment_ids',
      'reviewed_segment_ids', 'segment_id_mapping', 'word_timestamp_policy', 'word_alignment_source',
      'timing_rewrite_applied', 'human_timing_acknowledged', 'timing_independently_measured', 'review_required',
      'edit_note', 'source_media_mutated', 'remote_calls', 'derived_from_version']);
    if (Object.keys(base.provenance).some(k => !replaced.has(k) && !same(p[k], base.provenance[k]))) return false;
    const changes = new Map(body.segments.map(v => [v.segment_id, v]));
    return base.segments.every((old, i) => {
      const change = changes.get(old.segment_id), expected = content(old), actual = t.segments[i];
      if (p.segment_id_mapping?.[old.segment_id] !== actual.segment_id) return false;
      if (change) Object.assign(expected, {start_seconds: change.start_seconds, end_seconds: change.end_seconds, confidence: null,
        text: change.words.map(w => w.text.trim().normalize('NFC')).join(' '),
        words: change.words.map(w => ({text: w.text.trim().normalize('NFC'), start_seconds: w.start_seconds,
          end_seconds: w.end_seconds, confidence: null}))});
      return same(content(actual), expected);
    });
  } catch {return false;}
}
export async function boundedVideoWordSource(response, asset, signal, maximum) {
  demand(response.ok && response.status === 200 && response.headers.get('content-type')?.split(';')[0] === asset.content_type
    && response.headers.get('cache-control')?.includes('no-store')
    && response.headers.get('etag') === `"sha256-${asset.checksum_sha256}"`
    && /^[0-9]+$/.test(response.headers.get('content-length') ?? '')
    && Number(response.headers.get('content-length')) === asset.size_bytes && asset.size_bytes <= maximum && response.body?.getReader,
  'Video nguồn chưa khả dụng, sai metadata hoặc vượt giới hạn phát tại máy.');
  const reader = response.body.getReader(), chunks = []; let count = 0;
  const abort = () => {reader.cancel().catch(() => {});}; signal.addEventListener('abort', abort, {once: true});
  try {
    for (;;) {demand(!signal.aborted, 'Đã dừng tải nguồn.'); const {done, value} = await reader.read(); if (done) break;
      count += value.byteLength; demand(count <= asset.size_bytes && count <= maximum, 'Video trả về vượt giới hạn đã xác minh.'); chunks.push(value);}
    demand(count === asset.size_bytes && !signal.aborted, 'Không phát video tải thiếu.');
    const bytes = new Uint8Array(count); let cursor = 0; for (const chunk of chunks) {bytes.set(chunk, cursor); cursor += chunk.length;} return bytes;
  } catch (error) {await reader.cancel().catch(() => {}); throw error;}
  finally {signal.removeEventListener('abort', abort); reader.releaseLock();}
}

// Native Storage calls are synchronous and cannot invoke injected instance getters.
// Custom stores may clear an intent only through a trusted synchronous
// compareAndRemoveItem(key, exactRaw) primitive; arbitrary get/remove pairs
// cannot prove that a replacement is still the record being removed.
export function videoWordSessionStorage() {
  try {
    const target = globalThis.sessionStorage, prototype = globalThis.Storage?.prototype;
    demand(target instanceof globalThis.Storage && prototype
      && [prototype.getItem, prototype.setItem, prototype.removeItem].every(v => typeof v === 'function'), 'Không có nơi giữ yêu cầu trong phiên.');
    const read = prototype.getItem, write = prototype.setItem, remove = prototype.removeItem;
    return Object.freeze({
      getItem: key => read.call(target, key),
      setItem: (key, raw) => write.call(target, key, raw),
      compareAndRemoveItem: (key, exactRaw) => {
        if (read.call(target, key) !== exactRaw) return false;
        remove.call(target, key); return true;
      },
    });
  } catch {return null;}
}

export function initializeVideoTranscriptWordReview({root, api, mediaFetch, getState, onMessage = () => {},
  onSaved = async () => {}, onBusyChanged = () => {}, dom = globalThis.document, storage = videoWordSessionStorage(),
  cryptoImpl = globalThis.crypto, urls = globalThis.URL, maxPlaybackBytes = 64 * 1024 ** 2,
  getSessionToken = browserSessionToken}) {
  if (!root) return {sync() {}, reload: async () => {}, dispose() {}, isDirty: () => false, isWorking: () => false, isPending: () => false};
  demand(Number.isSafeInteger(maxPlaybackBytes) && maxPlaybackBytes > 0 && maxPlaybackBytes <= 256 * 1024 ** 2, 'Giới hạn phát video không hợp lệ.');
  const live = getState; let receipts = []; getState = () => ({...live(), verifiedVariantReceipts: receipts});
  const transientToken = () => {try {const value = getSessionToken(); return typeof value === 'string' && value.length <= 2048 ? value : '';} catch {return '';}};
  let context = scope(getState()), contextToken = transientToken(), epoch = 0, disposed = false, working = false, dirty = false, view = null, pending = null;
  let held = null;
  const retainedBytes = new Map();
  let fields = [], mediaAbort = null, url = null; const history = new Map();
  const node = (tag, name, text) => {const e = dom.createElement(tag); e.setAttribute('data-video-word-' + name, ''); if (text) e.textContent = text; return e;};
  const button = (name, text, action) => {const e = node('button', name, text); e.type = 'button'; e.addEventListener('click', () => action().catch(error => onMessage(error.message, true))); return e;};
  const label = (text, input) => {const e = node('label', 'label', text); e.append(input); return e;};
  const read = button('read', 'Đọc từ đã lưu', reload), listen = button('listen', 'Tải video nguồn để kiểm tra', loadSource);
  const choose = node('select', 'segment'), rows = node('div', 'rows'), summary = node('p', 'summary'), status = node('p', 'status'); status.setAttribute('role', 'status');
  const start = node('input', 'segment-start'), end = node('input', 'segment-end'); for (const e of [start, end]) {e.type = 'number'; e.step = 'any'; e.addEventListener('input', draftChanged);}
  const ack = node('input', 'ack'); ack.type = 'checkbox'; ack.addEventListener('change', sync);
  const note = node('textarea', 'note'); note.maxLength = 1800; note.addEventListener('input', draftChanged);
  const save = button('save', 'Lưu phiên bản từ đã kiểm tra', () => submit(false));
  const reconcile = button('reconcile', 'Đối chiếu lần lưu chưa rõ kết quả', checkPending);
  const retry = button('retry', 'Gửi lại đúng yêu cầu đang giữ', () => submit(true));
  const discard = button('discard', 'Bỏ bản sửa chưa lưu', async () => {if (!pending) {dirty = false; renderSegment(); sync();}});
  const player = node('video', 'source'); player.controls = true; player.preload = 'metadata'; player.hidden = true;
  const historical = node('details', 'history'); historical.append(node('summary', 'history-title', 'Bằng chứng từ đã lưu · chỉ đọc'));
  root.append(node('h3', 'title', 'Kiểm tra từng từ của video'), read, summary, listen, player,
    label('Đoạn lời nhận diện', choose), label('Bắt đầu đoạn (giây nguồn)', start), label('Kết thúc đoạn (giây nguồn)', end), rows,
    label('Ghi chú lần sửa', note), label('Tôi đã kiểm tra video nguồn và các từ/thời gian này; phiên bản mới là quyết định của người sửa', ack),
    save, discard, reconcile, retry, historical, status);
  choose.addEventListener('change', () => {if (!dirty && !pending) {renderSegment(); sync();}});
  function path(a = view?.selected) {return `/api/v1/projects/${encodeURIComponent(a.project_id)}/analyses/${encodeURIComponent(a.analysis_id)}`;}
  function key(s = getState()) {return s.workspaceId && s.projectId && s.principal?.subject
    ? 'vf-video-word-pending-v1:' + stable([s.workspaceId, s.projectId, s.principal.subject]) : null;}
  function probeHeld() {
    const bucket = key(); if (!bucket) {held = null; return;}
    try {
      demand(storage && typeof storage.getItem === 'function', 'Không đọc được nơi giữ yêu cầu.');
      const raw = storage.getItem(bucket);
      if (raw !== null && raw !== undefined) {
        if (!held || held.bucket !== bucket || held.raw !== raw) {held = {bucket, raw, reason: 'Có bản ghi chưa rõ kết quả; sửa mới đang khóa.'}; pending = null;}
      } else if (pending) held = {bucket, raw: null, reason: 'Bản ghi đang giữ bị mất; không gửi thêm hoặc xóa bằng chứng.'};
      else held = null;
    } catch {held = {bucket, raw: null, reason: 'Không đọc được bản ghi đang giữ; sửa mới đang khóa.'}; pending = null;}
  }
  function requireTransient() {demand(contextToken && transientToken() === contextToken, 'Phiên token tạm thời không còn khớp; đọc lại sau khi xác thực.');}
  function storedBodyValid(p) {
    const body = p.body, base = p.base.transcript;
    demand(same(Object.keys(body).sort(), ['acknowledged', 'expected_timeline_version', 'expected_transcript_id', 'expected_version', 'note', 'segments'].sort())
      && Number.isInteger(body.expected_version) && body.expected_version >= base.version
      && (body.expected_timeline_version === null || Number.isInteger(body.expected_timeline_version) && body.expected_timeline_version >= 1)
      && body.note.length <= 2000 && body.segments.length > 0 && body.segments.length <= 1000, 'Yêu cầu lưu sai cấu trúc.');
    const changed = new Map(), used = new Set(); let total = 0, previous = 0;
    for (const segment of body.segments) {
      const old = base.segments.find(v => v.segment_id === segment.segment_id);
      demand(old && !changed.has(segment.segment_id) && same(Object.keys(segment).sort(), ['segment_id', 'start_seconds', 'end_seconds', 'words'].sort())
        && Number.isFinite(segment.start_seconds) && Number.isFinite(segment.end_seconds) && segment.start_seconds >= 0
        && segment.end_seconds > segment.start_seconds && segment.end_seconds <= p.base.source_media.duration_seconds
        && Array.isArray(segment.words) && segment.words.length > 0 && segment.words.length <= 2000, 'Đoạn lưu không hợp lệ.');
      let end = segment.start_seconds;
      for (const w of segment.words) {
        demand(same(Object.keys(w).sort(), ['word_id', 'text', 'start_seconds', 'end_seconds'].sort())
          && old.words.some(v => v.word_id === w.word_id) && !used.has(w.word_id)
          && typeof w.text === 'string' && w.text.trim() && w.text.length <= 240
          && Number.isFinite(w.start_seconds) && Number.isFinite(w.end_seconds)
          && w.start_seconds >= end && w.end_seconds > w.start_seconds && w.end_seconds <= segment.end_seconds, 'Từ lưu không hợp lệ.');
        used.add(w.word_id); end = w.end_seconds;
      }
      changed.set(segment.segment_id, segment);
    }
    for (const old of base.segments) {const item = changed.get(old.segment_id) ?? old;
      demand(item.start_seconds >= previous, 'Đoạn lưu chồng thời gian.'); previous = item.end_seconds; total += item.words.length;}
    demand(total <= 10000, 'Yêu cầu lưu vượt giới hạn từ.');
  }
  function message(text) {status.textContent = text;}
  function revoke() {mediaAbort?.abort(); mediaAbort = null; if (url) urls.revokeObjectURL(url); url = null; player.removeAttribute?.('src'); player.hidden = true;}
  function still(ticket, identity) {return !disposed && epoch === ticket && scope(getState()) === identity
    && !!contextToken && transientToken() === contextToken;}
  function sameSource(p) {try {const s = getState(); return still(p.epoch ?? epoch, p.scope)
    && sourceIdentity(s, p.base) === p.sourceIdentity;} catch {return false;}}
  function setWorking(value) {working = value; sync(); onBusyChanged();}
  function draftChanged() {if (!view || pending || held || working) return; dirty = true; ack.checked = false; sync(); onBusyChanged();}
  function currentView() {const s = getState(); session(s, true); demand(view && view.binding === rootBinding(s), 'Dữ liệu đã đổi; đọc lại trước khi lưu.');}
  function sync() {
    const next = scope(getState()), token = transientToken(); if (next !== context || token !== contextToken) {context = next; contextToken = token; epoch++; revoke(); receipts = []; view = null; fields = []; history.clear(); dirty = false; pending = null; working = false;
      rows.replaceChildren(); choose.replaceChildren(); message('Dự án hoặc phiên truy cập đã đổi. Đọc lại từ đã lưu.');}
    probeHeld(); if (held && !pending) message(held.reason);
    let readable = false, editable = false; try {session(getState()); requireTransient(); readable = true; currentView(); editable = !held;} catch {}
    read.disabled = disposed || working || dirty || !readable;
    choose.disabled = !editable || dirty || !!pending || working; start.disabled = end.disabled = note.disabled = !editable || !!pending || working;
    for (const f of fields) for (const input of [f.text, f.start, f.end]) input.disabled = !editable || !!pending || working;
    ack.disabled = !editable || !dirty || !!pending || working;
    save.disabled = !editable || !dirty || !ack.checked || !!pending || working || !fields.length;
    discard.disabled = !dirty || !!pending || working;
    reconcile.disabled = !pending || !readable || working;
    retry.disabled = !pending || !pending.retryAllowed || !readable || working;
    listen.disabled = !view || !readable || working || !mediaFetch;
  }
  function renderHistory() {
    historical.replaceChildren(node('summary', 'history-title', 'Bằng chứng từ đã lưu · chỉ đọc'));
    for (const a of [...history.values()].sort((a, b) => a.transcript.version - b.transcript.version)) {
      const t = a.transcript, article = node('article', 'historical-version');
      article.append(node('strong', 'version', `Bản ${t.version} · ${t.is_original_evidence ? 'bằng chứng gốc' : 'phiên bản sửa'} · ${t.provider_key}`));
      for (const s of t.segments) article.append(node('p', 'historical-words', s.words.map(w => `${w.text} [${w.start_seconds}–${w.end_seconds}; độ tin cậy ${w.confidence ?? 'không có'}]`).join(' ') || s.text));
      historical.append(article);
    }
  }
  function renderSegment() {
    const segment = view?.selected.transcript.segments.find(s => s.segment_id === choose.value); fields = []; rows.replaceChildren(); ack.checked = false; note.value = '';
    if (!segment) return; start.value = String(segment.start_seconds); end.value = String(segment.end_seconds);
    for (const w of segment.words) {const row = node('div', 'row'), text = node('input', 'text'), begin = node('input', 'start'), finish = node('input', 'end');
      text.value = w.text; text.maxLength = 240; for (const input of [begin, finish]) {input.type = 'number'; input.step = 'any';}
      begin.value = String(w.start_seconds); finish.value = String(w.end_seconds);
      for (const input of [text, begin, finish]) input.addEventListener('input', draftChanged);
      row.append(label('Từ', text), label('Từ giây nguồn', begin), label('Đến giây nguồn', finish), node('small', 'confidence', `Bằng chứng cũ: ${w.confidence ?? 'không có độ tin cậy'}`),
        button('seek', 'Xem khoảng nguồn', async () => {demand(!player.hidden, 'Tải video nguồn đã xác minh trước.'); player.currentTime = w.start_seconds;}));
      rows.append(row); fields.push({wordId: w.word_id, text, start: begin, end: finish});}
    if (!segment.words.length) message('Đoạn này không có thời gian từng từ. Không tạo thời gian giả; dùng chỉnh văn bản đoạn riêng.');
  }
  async function sourceReceipt(s, a, ticket, identity) {
    const asset = source(s, a); if (asset.provenance.source_type !== 'verified_variant_derivative') return;
    const receipt = await loadVariantReceipt(s, asset, api, getState, cryptoImpl);
    demand(still(ticket, identity) && same(source(getState(), a), asset), 'Nguồn hoặc phiên truy cập đổi trong lúc kiểm tra biên nhận.'); receipts = [receipt];
  }
  async function reload() {
    sync(); requireTransient();
    session(getState()); demand(!dirty && !working, 'Giữ bản sửa hiện tại hoặc chờ thao tác kết thúc.');
    const s = copy(getState()), a = s.analysis; demand(a && ids.analysis.test(a.analysis_id), 'Chọn kết quả video đã lưu.');
    const ticket = epoch, identity = scope(s), bound = rootBinding(s), token = contextToken;
    let retained = null; setWorking(true);
    try {
      demand(still(ticket, identity) && rootBinding(getState()) === bound, 'Ngữ cảnh đã đổi trước khi đọc nguồn.'); session(getState());
      if (held) {
        try {
          demand(typeof held.raw === 'string', 'Bản ghi chưa khả dụng.');
          retained = JSON.parse(held.raw);
          demand(retained && retained.scope === identity && retained.actor === s.principal.subject
            && retained.workspaceId === s.workspaceId && retained.projectId === s.projectId && retained.analysisId === a.analysis_id
            && /^[A-Za-z0-9._:-]{8,120}$/.test(retained.key) && /^[a-f0-9]{64}$/.test(retained.session_sha256)
            && typeof retained.body?.note === 'string' && retained.body.note.endsWith('Mã lần sửa giao diện: ' + retained.key)
            && retained.body.expected_transcript_id === retained.base?.transcript?.transcript_id
            && retained.body.expected_version === retained.latest?.transcript?.version
            && retained.body.acknowledged === true && Array.isArray(retained.body.segments)
            && typeof retained.viewBinding === 'string', 'Bản ghi sai phạm vi hoặc cấu trúc.');
          validateVideoWords(retained.base, s); validateVideoWords(retained.latest, s); storedBodyValid(retained);
          const digest = await audioByteHash(new TextEncoder().encode(token), cryptoImpl);
          demand(still(ticket, identity) && rootBinding(getState()) === bound && digest === retained.session_sha256
            && retained.sourceIdentity === sourceIdentity(getState(), retained.base), 'Token hoặc nguồn của bản ghi không còn khớp.');
        } catch {
          pending = null; view = null; fields = []; rows.replaceChildren(); choose.replaceChildren();
          if (held) held.reason = 'Bản ghi chưa rõ kết quả không khớp phiên/nguồn hoặc chưa hợp lệ. Giữ nguyên bản ghi; sửa mới đang khóa.';
          throw Error('Không thể xác minh bản ghi đang giữ. Không gửi lại, ghi đè hoặc xóa yêu cầu cũ.');
        }
      }
      await sourceReceipt(s, a, ticket, identity);
      const latest = copy(await api(path(a))); demand(still(ticket, identity) && rootBinding(getState()) === bound, 'Dữ liệu đã đổi trong lúc đọc.'); validateVideoWords(latest, getState());
      const selected = selectedId(getState(), latest); let selectedAnalysis = latest;
      if (selected !== latest.transcript.transcript_id) {selectedAnalysis = copy(await api(path(a) + '?transcript_id=' + encodeURIComponent(selected)));
        demand(still(ticket, identity) && rootBinding(getState()) === bound, 'Dữ liệu đã đổi trong lúc đọc bản đã chọn.'); validateVideoWords(selectedAnalysis, getState());}
      if (retained) {
        const savedBase = selectedAnalysis.transcript.transcript_id === retained.base.transcript.transcript_id ? selectedAnalysis
          : copy(await api(path(a) + '?transcript_id=' + encodeURIComponent(retained.base.transcript.transcript_id)));
        demand(still(ticket, identity) && rootBinding(getState()) === bound, 'Ngữ cảnh đã đổi khi kiểm tra bản gốc của yêu cầu.');
        validateVideoWords(savedBase, getState()); demand(same(savedBase.transcript, retained.base.transcript), 'Bản gốc của yêu cầu không còn khớp bằng chứng đã lưu.');
        pending = freeze({...retained, epoch: ticket, retryAllowed: false});
        retainedBytes.set(retained.key, held.raw);
      }
      view = freeze({latest, selected: selectedAnalysis, binding: bound}); history.set(latest.transcript.transcript_id, latest); history.set(selected, selectedAnalysis);
      let prior = selectedAnalysis; const seen = new Set([selected]);
      for (let count = 0; count < 50 && !prior.transcript.is_original_evidence; count++) {
        const parent = prior.transcript.provenance.derived_from_transcript_id;
        if (!ids.transcript.test(parent) || seen.has(parent)) break;
        const version = prior.transcript.version; seen.add(parent);
        prior = copy(await api(path(a) + '?transcript_id=' + encodeURIComponent(parent)));
        demand(still(ticket, identity) && rootBinding(getState()) === bound, 'Dữ liệu đã đổi khi đọc bằng chứng cũ.');
        validateVideoWords(prior, getState()); demand(prior.transcript.version < version, 'Lịch sử transcript không theo thứ tự.');
        history.set(parent, prior);
      }
      choose.replaceChildren(); for (const segment of selectedAnalysis.transcript.segments) {const option = node('option', 'option'); option.value = segment.segment_id; option.textContent = segment.text; choose.append(option);}
      choose.value = selectedAnalysis.transcript.segments[0]?.segment_id ?? ''; dirty = false; renderSegment(); renderHistory();
      summary.textContent = `Bản được chọn ${selectedAnalysis.transcript.version} · số phiên bản SQL mới nhất ${latest.transcript.version} · ${latest.provenance.fixture ? 'lời mô phỏng' : 'bằng chứng dịch vụ đã lưu, chưa nghiệm thu chất lượng'} · nguồn giữ nguyên`;
      if (fields.length) message('Kiểm tra video gốc và các từ trước khi xác nhận. Không chạy nhận diện mới.');
      if (pending) message('Có lần lưu chưa rõ kết quả. Đối chiếu trước khi sửa tiếp.');
    } finally {if (still(ticket, identity)) setWorking(false); else sync();}
  }
  function intent(session_sha256) {
    currentView(); const s = getState(), operation = cryptoImpl.randomUUID(), segment = {segment_id: choose.value,
      start_seconds: seconds(start), end_seconds: seconds(end), words: fields.map(f => ({word_id: f.wordId,
        text: f.text.value, start_seconds: seconds(f.start), end_seconds: seconds(f.end)}))};
    const body = videoWordPayload(s, view, [segment], ack.checked, note.value, operation);
    return freeze({key: operation, body, base: copy(view.selected), latest: copy(view.latest), scope: scope(s),
      sourceIdentity: sourceIdentity(s, view.selected), actor: s.principal.subject, workspaceId: s.workspaceId,
      projectId: s.projectId, analysisId: view.selected.analysis_id, viewBinding: view.binding, session_sha256, epoch, retryAllowed: false});
  }
  async function accepted(a, p) {
    demand(sameSource(p), 'Dự án, nguồn hoặc phiên truy cập đã đổi sau lần lưu.'); session(getState(), true); validateVideoWords(a, getState());
    demand(videoWordReceiptMatches(a, p), 'Phản hồi chưa chứng minh đúng lần sửa; giữ yêu cầu để đối chiếu.');
    await onSaved({workspace_id: p.workspaceId, project_id: p.projectId, analysis_id: p.analysisId, asset_id: a.asset_id,
      source_sha256: source(getState(), a).checksum_sha256, base_transcript_id: p.body.expected_transcript_id,
      result_transcript_id: a.transcript.transcript_id, expected_timeline_version: p.body.expected_timeline_version, receipt: copy(a)});
    function currentReceipt() {
      demand(sameSource(p), 'Ngữ cảnh đã đổi khi tải lại dự án; yêu cầu vẫn được giữ.'); session(getState(), true);
      if (p.body.expected_timeline_version !== null) demand(getState().timeline?.current_version === p.body.expected_timeline_version + 1
        && getState().timeline.snapshot?.metadata?.transcript_revision?.transcript_id === a.transcript.transcript_id,
      'Timeline chưa chứng minh phiên bản từ đã đồng bộ; giữ yêu cầu để đối chiếu.');
    }
    currentReceipt();
    const bucket = key(), exactRaw = retainedBytes.get(p.key), readback = storage.getItem(bucket);
    currentReceipt(); // The final injected getter may have changed token/source/CAS.
    demand(held && held.bucket === bucket && typeof exactRaw === 'string' && held.raw === exactRaw && readback === exactRaw,
      'Bản ghi đang giữ đã đổi; không xóa bản ghi khác.');
    demand(typeof storage.compareAndRemoveItem === 'function',
      'Nơi giữ yêu cầu chưa hỗ trợ xóa có đối chiếu đồng bộ. Giữ bản ghi chưa rõ kết quả; không xóa riêng lẻ.');
    demand(storage.compareAndRemoveItem(bucket, exactRaw) === true,
      'Bản ghi đang giữ đã đổi hoặc chưa đối chiếu được; không xóa bản ghi khác.');
    retainedBytes.delete(p.key); pending = null; held = null; dirty = false; view = null; revoke(); fields = []; rows.replaceChildren();
    history.set(a.transcript.transcript_id, freeze(copy(a))); renderHistory(); message('Đã lưu phiên bản từ. Preview và phê duyệt cần cập nhật; đọc lại trước khi sửa tiếp.');
  }
  async function submit(retryOld) {
    sync(); requireTransient(); session(getState(), true); demand(!working, 'Đang lưu hoặc đọc dữ liệu.');
    if (retryOld) demand(pending?.retryAllowed && sameSource(pending), 'Đối chiếu nguồn và lần lưu cũ trước khi gửi lại.');
    else demand(!pending && !held && dirty, 'Chưa có bản sửa mới hoặc đang giữ lần lưu cũ.');
    const ticket = epoch, identity = scope(getState()), token = contextToken, binding = rootBinding(getState());
    let p = retryOld ? pending : intent(null); setWorking(true);
    try {
      if (!retryOld) {
        const digest = await audioByteHash(new TextEncoder().encode(token), cryptoImpl);
        demand(still(ticket, identity) && rootBinding(getState()) === binding, 'Ngữ cảnh đã đổi trong lúc ràng buộc token.');
        session(getState(), true); probeHeld(); demand(!held && !pending, 'Có yêu cầu đang giữ; không ghi đè.');
        p = freeze({...p, session_sha256: digest});
        demand(storage && typeof storage.setItem === 'function', 'Không lưu được yêu cầu đang giữ; chưa gửi thao tác.');
        const raw = JSON.stringify(p), bucket = key();
        try {storage.setItem(bucket, raw);} catch {throw Error('Không lưu được yêu cầu đang giữ; chưa gửi thao tác.');}
        pending = p; held = {bucket, raw, reason: 'Lần lưu chưa được xác nhận.'};
        retainedBytes.set(p.key, raw);
      }
      session(getState(), true); demand(sameSource(p) && rootBinding(getState()) === p.viewBinding,
        'Nguồn, phiên bản hoặc phiên đã đổi trước khi gửi; yêu cầu giữ nguyên.');
      const readback = storage.getItem(key());
      demand(held?.raw === retainedBytes.get(p.key) && readback === held.raw,
        'Bản ghi đang giữ đã đổi trước khi gửi; không ghi đè hoặc gửi thêm.');
      session(getState(), true); demand(sameSource(p) && rootBinding(getState()) === p.viewBinding,
        'Nguồn, phiên bản hoặc phiên đã đổi trong lúc đọc bản ghi; yêu cầu giữ nguyên.');
      const a = copy(await api(path(p.base) + '/transcript-words', {method: 'POST', body: JSON.stringify(p.body)}));
      if (!sameSource(p)) return; await accepted(a, p);
    } catch (error) {if (p && sameSource(p)) message('Lần lưu chưa được xác nhận. Giữ đúng yêu cầu và dùng Đối chiếu. ' + error.message); throw error;}
    finally {if (still(ticket, identity)) setWorking(false); else sync();}
  }
  async function checkPending() {
    sync(); requireTransient(); session(getState(), true); demand(pending && !working && sameSource(pending), 'Không có lần lưu đúng nguồn/phiên để đối chiếu.');
    const p = pending; setWorking(true);
    try {
      let a = copy(await api(path(p.base))); demand(sameSource(p), 'Ngữ cảnh đã đổi trong lúc đối chiếu.'); validateVideoWords(a, getState());
      const seen = new Set(); for (let count = 0; count < 50; count++) {
        if (videoWordReceiptMatches(a, p)) {await accepted(a, p); return;}
        const t = a.transcript;
        if (t.version === p.body.expected_version) {
          demand(t.transcript_id === p.latest.transcript.transcript_id && same(t, p.latest.transcript)
            && (getState().timeline?.current_version ?? null) === p.body.expected_timeline_version,
          'Lần lưu không khớp bản cũ; không gửi lại hoặc đổi CAS.');
          pending = freeze({...p, retryAllowed: true}); message('Chưa thấy bản sửa đúng yêu cầu. Có thể gửi lại chính yêu cầu đã giữ; CAS không đổi.'); return;
        }
        const parent = t.provenance.derived_from_transcript_id;
        demand(ids.transcript.test(parent) && !seen.has(parent) && t.version > p.body.expected_version + 1, 'Không chứng minh được lần sửa; yêu cầu vẫn giữ.');
        seen.add(parent); const priorVersion = t.version;
        a = copy(await api(path(p.base) + '?transcript_id=' + encodeURIComponent(parent)));
        demand(sameSource(p), 'Ngữ cảnh đã đổi khi đọc lịch sử.'); validateVideoWords(a, getState());
        demand(a.transcript.version < priorVersion, 'Lịch sử phiên bản không theo thứ tự.');
      }
      throw Error('Lịch sử cần kiểm tra thêm; không tự gửi lại.');
    } finally {if (still(p.epoch, p.scope)) setWorking(false); else sync();}
  }
  async function loadSource() {
    sync(); requireTransient(); session(getState()); demand(view && !working && mediaFetch, 'Đường phát video nguồn chưa khả dụng.');
    const a = view.selected, asset = copy(source(getState(), a)), ticket = epoch, identity = scope(getState()), bound = rootBinding(getState());
    demand(asset.size_bytes <= maxPlaybackBytes, 'Video vượt giới hạn phát tại máy; không tải không giới hạn.'); revoke(); mediaAbort = new AbortController(); const signal = mediaAbort.signal; setWorking(true);
    try {
      demand(still(ticket, identity) && rootBinding(getState()) === bound, 'Ngữ cảnh đã đổi trước khi tải video.'); session(getState());
      const response = await mediaFetch(path(a) + '/source', {cache: 'no-store', signal});
      const bytes = await boundedVideoWordSource(response, asset, signal, maxPlaybackBytes);
      demand(await audioByteHash(bytes, cryptoImpl) === asset.checksum_sha256, 'Checksum video nguồn khác bằng chứng đã lưu.');
      demand(still(ticket, identity) && rootBinding(getState()) === bound && !signal.aborted, 'Ngữ cảnh đã đổi khi tải nguồn.'); session(getState());
      url = urls.createObjectURL(new Blob([bytes], {type: asset.content_type})); player.src = url; player.hidden = false;
      message('Video gốc đã khớp checksum. Dùng nút phát và khoảng nguồn để kiểm tra; hệ thống không tự xác nhận đã nghe.');
    } catch (error) {revoke(); throw error;} finally {if (still(ticket, identity)) setWorking(false); else sync();}
  }
  sync(); return {sync, reload, dispose() {disposed = true; epoch++; revoke(); working = false; sync(); onBusyChanged();},
    isDirty: () => dirty, isWorking: () => working, isPending: () => !!pending || !!held};
}
