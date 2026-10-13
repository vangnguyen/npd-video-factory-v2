// SQL uploaded speech: immutable evidence and explicit human revisions only.
const sha = /^[a-f0-9]{64}$/, ids = {audio: /^aud_[a-f0-9]{24}$/, transcript: /^trn_[a-f0-9]{24}$/,
  segment: /^seg_[a-f0-9]{24}$/, word: /^wrd_[a-f0-9]{24}$/};
const ranks = {viewer: 10, editor: 20, reviewer: 30, owner: 40};
const activeJobs = new Set(['queued', 'running']);
const statuses = {queued: 'Đang chờ nhận diện', running: 'Đang nhận diện', awaiting_review: 'Có lời nhận diện · cần nghe và kiểm tra',
  failed: 'Nhận diện bị chặn hoặc thất bại', cancelled: 'Đã hủy', needs_attention: 'Cần kiểm tra kết quả dịch vụ · không tự chạy lại'};
const maxBytes = 64 * 1024 * 1024;
const playbackMaxBytes = 32 * 1024 * 1024;
const mimeTypes = ['audio/wav', 'audio/x-wav', 'audio/mpeg', 'audio/flac'];
const copy = value => structuredClone(value);
const stable = value => JSON.stringify(value, (_key, v) => v && typeof v === 'object' && !Array.isArray(v)
  ? Object.fromEntries(Object.keys(v).sort().map(k => [k, v[k]])) : v);
const same = (a, b) => stable(a) === stable(b);
// Labels use milliseconds; inputs, drafts and payloads keep exact source numbers.
const displaySeconds = value => Number.isFinite(value) ? String(Number(value.toFixed(3))) : '—';
const demand = (condition, message) => {if (!condition) throw Error(message);};
const duration = asset => asset?.provenance?.media_metadata?.duration_seconds;

export function audioRole(state) {
  const p = state.principal, roles = [p?.platform_role, p?.workspace_roles?.['*'], p?.workspace_roles?.[state.workspaceId],
    state.workspaceSlug ? p?.workspace_roles?.[`slug:${state.workspaceSlug}`] : null];
  return roles.filter(role => ranks[role]).sort((a, b) => ranks[b] - ranks[a])[0] ?? null;
}
export function uploadedSpeechAssets(state) {
  return (state.assets ?? []).filter(a => a.project_id === state.projectId && a.workspace_id === state.workspaceId
    && a.asset_class === 'source' && a.kind === 'audio' && mimeTypes.includes(a.content_type)
    && sha.test(a.checksum_sha256) && a.provenance?.source_type === 'user_upload'
    && a.provenance?.media_metadata?.media_kind === 'audio' && Number.isFinite(duration(a)) && duration(a) > 0 && duration(a) <= 3600);
}
function assetFor(state, id) {
  const asset = uploadedSpeechAssets(state).find(a => a.asset_id === id);
  demand(asset, 'Audio lời nói không còn thuộc dự án hiện tại.');
  return asset;
}
function scope(state) {
  return JSON.stringify([state.workspaceId, state.projectId, state.principal?.subject, state.principal?.token_id,
    state.principal?.expires_at, audioRole(state)]);
}
function revisionScope(state, assetId) {
  const asset = assetFor(state, assetId);
  return JSON.stringify([scope(state), asset.asset_id, asset.checksum_sha256, asset.size_bytes,
    asset.provenance?.media_metadata, state.timeline?.timeline_id, state.timeline?.current_version ?? null]);
}
function writeGuard(state) {
  demand(state.projectId && state.workspaceId && ranks[audioRole(state)] >= ranks.editor, 'Cần quyền biên tập của dự án để lưu hoặc nhận diện.');
  demand(!state.busy && !state.dirty, 'Lưu thay đổi đang sửa trong Studio và chờ tải xong trước khi thao tác audio.');
}
export function audioHasCaptions(state, value) {
  const transcriptIds = new Set(value.versions.map(v => v.transcript_id));
  return (state.timeline?.snapshot?.tracks ?? []).some(track => (track.clips ?? []).some(clip =>
    clip.kind === 'subtitle' && (transcriptIds.has(clip.metadata?.transcript_id)
      || clip.metadata?.audio_transcription_id === value.audio_id)));
}
export function compatibleAudioBinding(state, value) {
  const timeline = state.timeline, b = timeline?.snapshot?.metadata?.uploaded_audio_bindings_v1?.[value.audio_id];
  if (!b || timeline.project_id !== state.projectId || timeline.workspace_id !== state.workspaceId
    || b.audio_id !== value.audio_id || b.source_sha256 !== value.source_sha256 || b.transcript_id !== value.current?.transcript_id
    || !same(b.transcript, value.current) || b.human_review_required !== true) return false;
  const voice = timeline.snapshot.tracks.find(t => t.track_id === b.voice_track_id), captions = timeline.snapshot.tracks.find(t => t.track_id === b.subtitle_track_id);
  return voice?.kind === 'voice' && captions?.kind === 'subtitles' && !captions.locked
    && captions.clips.every(c => c.metadata?.audio_binding_id === b.binding_id && !c.metadata?.human_caption_edit)
    && voice.clips.every(c => c.asset_id === value.asset_id && c.metadata?.audio_binding_id === b.binding_id
      && c.metadata?.source_asset_sha256 === value.source_sha256);
}
function editGuard(state, value) {
  writeGuard(state); validateAudioRead(value, state);
  demand(value.current, 'Chưa có lời nhận diện để sửa.');
  demand(!activeJobs.has(value.job.status), 'Chờ job kết thúc trước khi sửa.');
  demand(value.timeline_version === (state.timeline?.current_version ?? null), 'Timeline đã đổi. Tải lại dự án và audio trước khi lưu.');
  demand(!audioHasCaptions(state, value) || compatibleAudioBinding(state, value),
    'Audio đã gắn với phụ đề timeline nhưng liên kết hiện tại chưa khớp hoặc cần kiểm tra riêng.');
}
export function audioCaptionPayload(state, value, key, fields) {
  editGuard(state, value); const timeline = state.timeline;
  demand(timeline?.project_id === state.projectId && timeline.workspace_id === state.workspaceId
    && Number.isInteger(timeline.current_version) && timeline.current_version >= 1 && Number.isFinite(timeline.snapshot?.duration_seconds),
  'Cần timeline đã lưu trong dự án hiện tại trước khi thêm audio và phụ đề.');
  demand(!timeline.snapshot.metadata?.uploaded_audio_bindings_v1?.[value.audio_id], 'Audio này đã gắn; kiểm tra hoặc sửa liên kết đang lưu.');
  demand(fields.acknowledged === true && typeof fields.mute_original === 'boolean'
    && /^[A-Za-z0-9][A-Za-z0-9._:-]{7,159}$/.test(key), 'Xác nhận thao tác thêm audio/phụ đề trước khi gửi.');
  const {source_start, source_end, timeline_start, speed} = fields;
  demand([source_start, source_end, timeline_start, speed].every(Number.isFinite) && source_start >= 0
    && source_end > source_start && source_end <= duration(assetFor(state, value.asset_id)) && timeline_start >= 0 && speed > 0 && speed <= 8
    && timeline_start + (source_end - source_start) / speed <= timeline.snapshot.duration_seconds + .000001,
  'Nhập khoảng nguồn và vị trí nằm trong thời lượng timeline; tốc độ >0 và tối đa 8.');
  demand(!timeline.snapshot.tracks.some(t => t.kind === 'subtitles' && !t.disabled && t.clips.some(c => !c.disabled)),
    'Timeline có phụ đề đang bật. Kiểm tra và tắt phụ đề cũ rõ ràng trước khi thêm.');
  for (const t of timeline.snapshot.tracks) {
    if (t.type !== 'audio' || t.disabled || t.muted || !t.clips.some(c => !c.disabled && c.volume > 0)) continue;
    demand(t.kind !== 'voice' && (t.kind !== 'original_audio' || fields.mute_original && !t.locked),
      'Timeline còn lời nói đang bật hoặc track khóa. Kiểm tra/tắt lời cũ hoặc xác nhận tắt audio gốc trên track không khóa.');
  }
  return {source_sha256: value.source_sha256, expected_transcript_id: value.current.transcript_id,
    expected_version: value.current.version, expected_timeline_version: timeline.current_version,
    source_start, source_end, timeline_start, speed, mute_original: fields.mute_original, acknowledged: true, idempotency_key: key};
}
function validateTranscript(value, parent, index, limit) {
  demand(value && ids.transcript.test(value.transcript_id) && value.analysis_id === parent.audio_id
    && value.asset_id === parent.asset_id && value.version === index && value.is_original_evidence === (index === 1)
    && typeof value.provider_key === 'string' && typeof value.language === 'string' && Array.isArray(value.segments)
    && value.segments.length <= 1000 && value.provenance && typeof value.provenance === 'object', 'Phiên bản lời nhận diện sai nguồn hoặc cấu trúc.');
  let last = 0; const segmentIds = new Set(), wordIds = new Set();
  for (const segment of value.segments) {
    demand(ids.segment.test(segment.segment_id) && !segmentIds.has(segment.segment_id) && typeof segment.text === 'string'
      && segment.text.trim() && Number.isFinite(segment.start_seconds) && Number.isFinite(segment.end_seconds)
      && segment.start_seconds >= last && segment.end_seconds > segment.start_seconds && segment.end_seconds <= limit
      && Array.isArray(segment.words), 'Đoạn lời nhận diện không khớp thời gian nguồn.');
    segmentIds.add(segment.segment_id); last = segment.end_seconds; let end = segment.start_seconds;
    for (const word of segment.words) {
      demand(ids.word.test(word.word_id) && !wordIds.has(word.word_id) && typeof word.text === 'string' && word.text.trim()
        && Number.isFinite(word.start_seconds) && Number.isFinite(word.end_seconds) && word.start_seconds >= end
        && word.end_seconds > word.start_seconds && word.end_seconds <= segment.end_seconds, 'Từ hoặc thời gian từ không hợp lệ.');
      wordIds.add(word.word_id); end = word.end_seconds;
    }
  }
}
export function validateAudioRead(value, state) {
  const asset = assetFor(state, value?.asset_id);
  demand(value?.schema_version === 'uploaded-audio-transcription.v1' && ids.audio.test(value.audio_id)
    && value.workspace_id === state.workspaceId && value.project_id === state.projectId && value.source_sha256 === asset.checksum_sha256
    && value.human_review_required === true && value.source_media_mutated === false && value.publishing_enabled === false,
  'Kết quả audio sai dự án, nguồn hoặc giới hạn kiểm tra.');
  const job = value.job;
  demand(job && job.project_id === value.project_id && job.workspace_id === value.workspace_id
    && Object.hasOwn(statuses, job.status) && job.request?.kind === 'uploaded_audio_transcription'
    && job.request.audio_id === value.audio_id
    && job.request.source_sha256 === value.source_sha256 && Array.isArray(value.versions) && value.versions.length <= 51,
  'Job hoặc lịch sử audio không khớp nguồn.');
  demand(value.timeline_version === null || Number.isInteger(value.timeline_version) && value.timeline_version >= 1, 'Phiên bản timeline không hợp lệ.');
  const seen = new Set();
  value.versions.forEach((v, i) => {
    validateTranscript(v, value, i + 1, duration(asset));
    demand(!seen.has(v.transcript_id) && (i === 0 || seen.has(v.provenance.derived_from_transcript_id)), 'Lịch sử audio bị trùng hoặc mất gốc.');
    seen.add(v.transcript_id);
  });
  demand(same(value.original, value.versions[0] ?? null) && same(value.current, value.versions.at(-1) ?? null), 'Bản gốc hoặc bản hiện tại không khớp lịch sử.');
  return value;
}
export function audioCreatePayload(state, assetId, key, acknowledged) {
  writeGuard(state); const asset = assetFor(state, assetId);
  demand(acknowledged === true, 'Xác nhận nguồn cần nhận diện trước khi gửi.');
  demand(/^[A-Za-z0-9][A-Za-z0-9._:-]{7,159}$/.test(key), 'Khóa yêu cầu không hợp lệ.');
  return {asset_id: asset.asset_id, source_sha256: asset.checksum_sha256, idempotency_key: key, rights: []};
}
export function audioTextPayload(state, value, segments, note = '') {
  editGuard(state, value); const sourceIds = new Set(value.current.segments.map(s => s.segment_id));
  demand(Array.isArray(segments) && segments.length > 0 && segments.length <= 1000 && new Set(segments.map(s => s.segment_id)).size === segments.length,
    'Chọn các đoạn cần sửa.');
  demand(segments.every(s => sourceIds.has(s.segment_id) && typeof s.text === 'string' && s.text.trim() && s.text.length <= 4000)
    && typeof note === 'string' && note.length <= 2000, 'Nội dung trống, quá dài hoặc sai đoạn nguồn.');
  return {source_sha256: value.source_sha256, expected_transcript_id: value.current.transcript_id, edit: {
    expected_version: value.current.version, base_transcript_id: value.current.transcript_id,
    expected_timeline_version: value.timeline_version, segments: copy(segments), note}};
}
export function audioWordsPayload(state, value, segments, acknowledged, note = '') {
  editGuard(state, value); demand(acknowledged === true, 'Xác nhận thời gian do bạn kiểm tra trước khi lưu từ.');
  demand(Array.isArray(segments) && segments.length > 0 && segments.length <= 1000 && typeof note === 'string' && note.length <= 2000,
    'Chọn đoạn cần sửa từ.');
  const changed = new Map(), used = new Set(); let count = 0, previous = 0;
  for (const s of segments) {
    const old = value.current.segments.find(v => v.segment_id === s.segment_id);
    demand(old && !changed.has(s.segment_id) && Number.isFinite(s.start_seconds) && Number.isFinite(s.end_seconds)
      && s.start_seconds >= 0 && s.end_seconds > s.start_seconds && s.end_seconds <= duration(assetFor(state, value.asset_id))
      && Array.isArray(s.words) && s.words.length > 0 && s.words.length <= 2000, 'Thời gian đoạn hoặc nguồn không hợp lệ.');
    let end = s.start_seconds;
    for (const w of s.words) {
      demand(typeof w.text === 'string' && w.text.trim() && w.text.length <= 240 && Number.isFinite(w.start_seconds)
        && Number.isFinite(w.end_seconds) && w.start_seconds >= end && w.end_seconds > w.start_seconds && w.end_seconds <= s.end_seconds,
      'Điền thời gian từng từ; các từ phải theo thứ tự và nằm trong đoạn.');
      demand(!w.word_id || old.words.some(v => v.word_id === w.word_id) && !used.has(w.word_id), 'Từ bị trùng hoặc thuộc đoạn khác.');
      if (w.word_id) used.add(w.word_id); end = w.end_seconds; count++;
    }
    changed.set(s.segment_id, s);
  }
  for (const old of value.current.segments) {
    const s = changed.get(old.segment_id) ?? old;
    demand(s.start_seconds >= previous, 'Các đoạn lời nói không được chồng thời gian.'); previous = s.end_seconds;
    if (!changed.has(old.segment_id)) count += old.words.length;
  }
  demand(count <= 10000, 'Tối đa 10.000 từ trong một phiên bản.');
  return {source_sha256: value.source_sha256, edit: {expected_version: value.current.version,
    expected_transcript_id: value.current.transcript_id, expected_timeline_version: value.timeline_version,
    acknowledged: true, segments: copy(segments), note}};
}
export function audioRestorePayload(state, value, targetId, acknowledged, note = '') {
  editGuard(state, value); demand(acknowledged === true, 'Xác nhận khôi phục thành phiên bản mới.');
  demand(value.versions.some(v => v.transcript_id === targetId) && targetId !== value.current.transcript_id
    && typeof note === 'string' && note.length <= 2000, 'Chọn một phiên bản cũ của audio hiện tại.');
  return {source_sha256: value.source_sha256, expected_version: value.current.version,
    expected_transcript_id: value.current.transcript_id, expected_timeline_version: value.timeline_version,
    target_transcript_id: targetId, acknowledged: true, note};
}
function segmentContent(s) {
  return {text: s.text, start_seconds: s.start_seconds, end_seconds: s.end_seconds, speaker: s.speaker,
    confidence: s.confidence, words: s.words.map(w => ({text: w.text, start_seconds: w.start_seconds,
      end_seconds: w.end_seconds, confidence: w.confidence}))};
}
export function audioRevisionMatches(value, base, kind, body, actor) {
  // The backend currently has no per-edit request receipt. An unrelated higher
  // version is not proof of this request. Require the exact append and intent.
  try {
    const expected = body.expected_version ?? body.edit.expected_version, current = value.current, edit = body.edit;
    if (!base || current?.version !== expected + 1 || base.current.version !== expected
      || !same(value.original, base.original) || !base.versions.every((v, i) => same(v, value.versions[i]))
      || current.provenance.actor_ref !== actor || current.provenance.human_edit !== true
      || current.provenance.edit_note !== (body.note ?? edit.note) || current.provider_key !== base.current.provider_key
      || current.language !== base.current.language) return false;
    const source = kind === 'restore' ? base.versions.find(v => v.transcript_id === body.target_transcript_id) : base.current;
    if (!source || current.provenance.derived_from_transcript_id !== source.transcript_id
      || kind === 'restore' && current.provenance.restored_from_transcript_id !== source.transcript_id
      || source.segments.length !== current.segments.length) return false;
    const changes = new Map((edit?.segments ?? []).map(s => [s.segment_id, s]));
    if (kind === 'text' && (current.provenance.word_timestamp_policy !== 'discard_for_changed_text'
      || !same([...changes.keys()].sort(), [...current.provenance.changed_segment_ids].sort()))) return false;
    if (kind === 'words' && (current.provenance.word_timestamp_policy !== 'human_supplied_source_intervals'
      || current.provenance.human_timing_acknowledged !== true
      || !same([...changes.keys()].sort(), [...current.provenance.reviewed_segment_ids].sort()))) return false;
    return source.segments.every((old, i) => {
      const changed = changes.get(old.segment_id), expected = segmentContent(old), actual = current.segments[i];
      if (current.provenance.segment_id_mapping?.[old.segment_id] !== actual.segment_id) return false;
      if (kind === 'text' && changed) {expected.text = changed.text.normalize('NFC'); expected.words = []; expected.confidence = null;}
      if (kind === 'words' && changed) {
        expected.text = changed.words.map(w => w.text.trim().normalize('NFC')).join(' ');
        expected.start_seconds = changed.start_seconds; expected.end_seconds = changed.end_seconds; expected.confidence = null;
        expected.words = changed.words.map(w => ({text: w.text.trim().normalize('NFC'), start_seconds: w.start_seconds,
          end_seconds: w.end_seconds, confidence: null}));
      }
      return same(segmentContent(actual), expected);
    });
  } catch {return false;}
}
export async function audioByteHash(bytes, cryptoImpl = globalThis.crypto) {
  return [...new Uint8Array(await cryptoImpl.subtle.digest('SHA-256', bytes))].map(v => v.toString(16).padStart(2, '0')).join('');
}
export async function boundedAudioBytes(response, expectedBytes, signal) {
  const length = response.headers.get('content-length');
  demand(Number.isInteger(expectedBytes) && expectedBytes > 0 && expectedBytes <= playbackMaxBytes
    && /^\d+$/.test(length ?? '') && Number(length) === expectedBytes, 'Kích thước audio nghe không khớp hoặc vượt 32 MiB.');
  demand(response.body?.getReader, 'Trình duyệt chưa hỗ trợ đọc audio có giới hạn.');
  const reader = response.body.getReader(), chunks = []; let size = 0;
  const abort = () => {reader.cancel().catch(() => {});}; signal?.addEventListener('abort', abort, {once: true});
  try {
    for (;;) {
      demand(!signal?.aborted, 'Đã dừng tải audio do đổi nguồn/ngữ cảnh.');
      const {done, value} = await reader.read(); if (done) break;
      size += value.byteLength; demand(size <= expectedBytes && size <= playbackMaxBytes, 'Audio trả về vượt kích thước nguồn; đã dừng tải.');
      chunks.push(value);
    }
    demand(size === expectedBytes && !signal?.aborted, 'Audio chưa tải đầy đủ; không phát dữ liệu một phần.');
    const bytes = new Uint8Array(size); let offset = 0;
    for (const chunk of chunks) {bytes.set(chunk, offset); offset += chunk.byteLength;}
    return bytes;
  } catch (error) {await reader.cancel().catch(() => {}); throw error;}
  finally {signal?.removeEventListener('abort', abort); reader.releaseLock();}
}
const errorCode = error => error?.detail?.error?.code ?? '';
const errorText = error => /NOT_CONFIGURED/.test(errorCode(error))
  ? 'NOT_CONFIGURED · chưa cấu hình nhận diện audio. Không có lời nhận diện giả; nhờ người quản lý cấu hình dịch vụ và quyền chi phí.'
  : errorCode(error) === 'AUDIO_CANONICAL_CAPTION_REVIEW_REQUIRED'
    ? 'Audio đã gắn với phụ đề timeline. Đồng bộ phụ đề audio chưa hỗ trợ; thay đổi chưa được lưu.'
    : `${error.message}${errorCode(error) ? ` · ${errorCode(error)}` : ''}`;
function browserStorage() {try {return globalThis.sessionStorage ?? null;} catch {return null;}}
function pendingKey(state) {
  return state.projectId && state.workspaceId && state.principal?.subject
    ? `vfns-sql-audio-pending-v1:${[state.workspaceId, state.projectId, state.principal.subject].map(encodeURIComponent).join(':')}` : null;
}

export function initializeUploadedAudioReview({root, api, mediaFetch, getState, onMessage = () => {},
  onUploaded = async () => {}, onCanonicalSaved = async () => {}, dom = globalThis.document, newKey = () => globalThis.crypto.randomUUID(),
  cryptoImpl = globalThis.crypto, urls = globalThis.URL, timers = globalThis, pollMs = 1500, storage = browserStorage()}) {
  if (!root) return {sync() {}, reload: async () => {}, dispose() {}, isDirty: () => false};
  let identity = scope(getState()), epoch = 0, busy = false, rows = [], selectedId = '', selectedAsset = '', capabilities = null;
  let draft = null, dirty = false, pending = null, audioUrl = null, playbackAbort = null, timer = null, pollCount = 0, upload = null;
  let pendingStorageError = false;
  const elements = {}, create = (tag, name, text) => {
    const n = dom.createElement(tag); if (name) {n.setAttribute(`data-audio-${name}`, ''); elements[name] = n;}
    if (text !== undefined) n.textContent = text; return n;
  };
  const label = (text, input) => {const n = create('label'); n.append(create('span', null, text), input); return n;};
  const button = (name, text, fn) => {const n = create('button', name, text); n.type = 'button'; n.addEventListener('click', () => run(fn)); return n;};
  const heading = create('summary', 'heading', 'Lời nói từ audio nguồn');
  const body = create('div', 'body'); body.className = 'uploaded-audio-body';
  const notice = create('p', 'notice', 'Tải audio lời nói riêng tại đây. Bản gốc được giữ nguyên; kết quả cần nghe và kiểm tra.');
  const provider = create('p', 'provider', 'NOT_CONFIGURED mặc định · chỉ xem dữ liệu đã lưu; chưa kiểm tra dịch vụ ASR.');
  const status = create('p', 'status', 'Chọn dự án để xem audio.'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const sourceSelect = create('select', 'source'); sourceSelect.addEventListener('change', () => {
    if (dirty || pending || busy) {sourceSelect.value = selectedAsset; return;} selectedAsset = sourceSelect.value;
    selectedId = rows.filter(r => r.asset_id === selectedAsset).at(-1)?.audio_id ?? ''; requestAck.checked = false;
    renderSaved(); selectRow();
  });
  const sourceFacts = create('p', 'source-facts');
  const read = button('read', 'Tải danh sách và trạng thái', () => reload());
  const requestAck = create('input', 'request-ack'); requestAck.type = 'checkbox'; requestAck.addEventListener('change', sync);
  const queue = button('queue', 'Yêu cầu nhận diện audio đã chọn', queueAudio);
  const uploadFile = create('input', 'file'); uploadFile.type = 'file'; uploadFile.accept = '.wav,.mp3,.flac,audio/wav,audio/mpeg,audio/flac';
  const mime = create('select', 'mime'); for (const type of mimeTypes) {const o = create('option', null, type); o.value = type; mime.append(o);}
  const uploadRights = create('input', 'upload-rights'); uploadRights.type = 'checkbox';
  uploadFile.addEventListener('change', () => {uploadRights.checked = false; if (mimeTypes.includes(uploadFile.files?.[0]?.type)) mime.value = uploadFile.files[0].type; sync();});
  const uploadButton = button('upload', 'Tải audio lời nói lên', uploadAudio);
  const uploads = create('details', 'upload-area'); uploads.append(create('summary', null, 'Thêm audio lời nói'),
    label('File audio (tối đa 64 MiB tại panel này)', uploadFile), label('Định dạng file', mime),
    label('Tôi sở hữu và có quyền sử dụng, xử lý audio này', uploadRights), uploadButton,
    create('p', null, 'File đi qua kiểm tra an toàn, checksum và xác minh định dạng. Audio nhạc nền ở workbench phía trên không dùng làm lời nói.'));
  const saved = create('select', 'saved'); saved.addEventListener('change', () => {
    if (dirty || pending || busy) {saved.value = selectedId; return;} selectedId = saved.value; selectRow();
  });
  const job = create('p', 'job');
  const cancel = button('cancel', 'Hủy yêu cầu nhận diện', cancelAudio);
  const listen = button('listen', 'Nghe audio gốc', listenAudio);
  const player = create('audio', 'player'); player.controls = true; player.preload = 'none'; player.hidden = true;
  const warning = create('p', 'warning');
  const history = create('select', 'history'); history.addEventListener('change', () => {
    if (dirty || pending || busy) {history.value = draft?.transcript_id ?? ''; return;} applyAck.checked = false; renderTranscript(); sync();
  });
  const evidence = create('p', 'evidence'), editor = create('div', 'editor');
  const note = create('textarea', 'note'); note.maxLength = 2000; note.rows = 2;
  note.addEventListener('input', () => markDirty());
  const wordAck = create('input', 'word-ack'); wordAck.type = 'checkbox'; wordAck.addEventListener('change', sync);
  const saveText = button('save-text', 'Lưu sửa lời thành phiên bản mới', () => saveRevision('text'));
  const saveWords = button('save-words', 'Lưu từ và thời gian đã kiểm tra', () => saveRevision('words'));
  const discard = button('discard', 'Bỏ sửa chưa lưu', () => {demand(!pending, 'Đối chiếu yêu cầu chưa rõ kết quả trước khi bỏ sửa.'); dirty = false; selectRow();});
  const restoreAck = create('input', 'restore-ack'); restoreAck.type = 'checkbox'; restoreAck.addEventListener('change', sync);
  const restore = button('restore', 'Khôi phục bản đang xem thành phiên bản mới', restoreAudio);
  const reconcile = button('reconcile', 'Đối chiếu yêu cầu chưa rõ kết quả', reconcileAudio);
  const applyArea = create('details', 'apply-area'); applyArea.append(create('summary', null, 'Thêm audio lời nói và phụ đề vào timeline đã lưu'));
  const applyNumbers = {};
  for (const [name, title, initial] of [['source-start', 'Nguồn bắt đầu (giây)', '0'], ['source-end', 'Nguồn kết thúc (giây)', ''],
    ['timeline-start', 'Vị trí bắt đầu trên timeline (giây)', '0'], ['speed', 'Tốc độ phát', '1']]) {
    const input = create('input', name); input.type = 'number'; input.min = '0'; input.step = '0.001'; input.value = initial;
    input.addEventListener('input', sync); applyNumbers[name] = input; applyArea.append(label(title, input));
  }
  const muteOriginal = create('input', 'mute-original'); muteOriginal.type = 'checkbox';
  const applyAck = create('input', 'apply-ack'); applyAck.type = 'checkbox'; applyAck.addEventListener('change', sync);
  const applyButton = button('apply', 'Thêm audio và phụ đề đã kiểm tra', applyAudio);
  applyArea.append(label('Tắt audio gốc của video (nếu đang bật và track không khóa)', muteOriginal),
    label('Tôi đã kiểm tra lời, khoảng nguồn và vị trí; thêm audio/phụ đề này vào timeline, cần nghe và duyệt video lại', applyAck), applyButton,
    create('p', null, 'Chỉ bấm thêm khi muốn dùng audio này. Phụ đề cũ đang bật và lời nói cũ cần được kiểm tra/tắt rõ ràng. Không cắt giữa từ; không tự duyệt video.'));
  body.append(notice, provider, uploads, label('Audio lời nói đã tải lên', sourceSelect), sourceFacts, read,
    label('Tôi yêu cầu nhận diện nguồn đã chọn; dịch vụ chỉ chạy khi cấu hình, quyền và chi phí cho phép', requestAck), queue,
    label('Yêu cầu đã lưu', saved), job, cancel, listen, player, warning, label('Lịch sử lời nhận diện', history), evidence, editor,
    label('Ghi chú cho sửa bản hiện tại', note), saveText,
    label('Tôi đã nghe nguồn và kiểm tra thời gian từng từ; đây là thời gian do người sửa cung cấp', wordAck), saveWords, discard,
    label('Tôi muốn khôi phục bản đang xem thành một phiên bản mới, giữ lịch sử cũ', restoreAck), restore, applyArea, reconcile, status,
    create('p', null, 'Sửa lời đơn thuần sẽ bỏ thời gian từ của đoạn đã đổi. Sửa từng từ cần thời gian do bạn nhập, không tự ước lượng. '
      + 'Audio và lời nhận diện chỉ thêm vào timeline qua nút thêm riêng. Liên kết phụ đề khóa, sửa tay hoặc sai phiên bản cần kiểm tra riêng. Đây chưa phải duyệt video hoặc duyệt của Owner.'));
  root.replaceChildren(heading, body);
  function currentRow() {return rows.find(r => r.audio_id === selectedId) ?? null;}
  function announce(message, error = false) {status.textContent = message; onMessage(message, error);}
  function stop() {if (timer !== null) timers.clearTimeout(timer); timer = null;}
  function revoke() {playbackAbort?.abort(); playbackAbort = null; if (audioUrl) urls.revokeObjectURL(audioUrl);
    audioUrl = null; player.pause?.(); player.removeAttribute?.('src'); player.hidden = true;}
  function reset() {
    epoch++; stop(); revoke(); rows = []; selectedId = ''; selectedAsset = ''; capabilities = null;
    draft = null; dirty = false; pending = null; upload = null; note.value = ''; requestAck.checked = wordAck.checked = restoreAck.checked = uploadRights.checked = false;
    applyAck.checked = muteOriginal.checked = false;
    resetApplyFields();
    uploadFile.value = ''; saved.replaceChildren(); history.replaceChildren(); editor.replaceChildren();
    provider.textContent = 'NOT_CONFIGURED mặc định · tải lại để kiểm tra cấu hình dịch vụ.';
  }
  function resetApplyFields() {
    applyNumbers['source-start'].value = '0'; applyNumbers['source-end'].value = '';
    applyNumbers['timeline-start'].value = '0'; applyNumbers.speed.value = '1';
  }
  function markDirty() {dirty = true; stop(); sync(); status.textContent = 'Đang sửa audio · lưu hoặc bỏ sửa trước khi đổi nguồn/bản xem.';}
  function hydratePending(state) {
    const key = pendingKey(state); if (!key || pending || !uploadedSpeechAssets(state).length) return;
    try {
      const raw = storage?.getItem(key); if (!raw) return;
      const value = JSON.parse(raw), asset = assetFor(state, value.assetId), body = value.body;
      demand(value.schema_version === 'sql-audio-pending.v1' && value.kind === 'create'
        && /^[A-Za-z0-9][A-Za-z0-9._:-]{7,159}$/.test(body?.idempotency_key)
        && same(body, {asset_id: asset.asset_id, source_sha256: asset.checksum_sha256, idempotency_key: body.idempotency_key, rights: []}),
      'Khóa yêu cầu đã lưu không khớp nguồn hiện tại.');
      pending = {kind: 'create', assetId: asset.asset_id, revision: revisionScope(state, asset.asset_id), body: copy(body)};
      selectedAsset = asset.asset_id; requestAck.checked = true;
      status.textContent = 'Có yêu cầu nhận diện chưa rõ phản hồi từ lần trước. Đối chiếu hoặc thử lại đúng khóa đã lưu.';
    } catch {pendingStorageError = true; status.textContent = 'Không đọc được khóa yêu cầu nhận diện đã lưu; chưa thể gửi yêu cầu mới. Kiểm tra bộ nhớ phiên trình duyệt.';}
  }
  function preserveCreate(operation) {
    demand(storage && !pendingStorageError, 'Trình duyệt không lưu được khóa yêu cầu. Chưa gửi nhận diện; cần bật bộ nhớ phiên trình duyệt.');
    try {storage.setItem(pendingKey(getState()), JSON.stringify({schema_version: 'sql-audio-pending.v1', kind: 'create', assetId: operation.assetId, body: operation.body}));}
    catch {throw Error('Không lưu được khóa nhận diện; yêu cầu chưa được gửi.');}
  }
  function clearPending() {
    if (pending?.kind === 'create') {try {storage?.removeItem(pendingKey(getState()));} catch { /* Retained key still prevents a fresh replay on reload. */ }}
    pending = null;
  }
  function sync() {
    const state = getState(), next = scope(state);
    if (next !== identity) {reset(); identity = next; pendingStorageError = false; status.textContent = 'Ngữ cảnh hoặc quyền đã đổi. Tải lại danh sách audio.';}
    hydratePending(state);
    const assets = uploadedSpeechAssets(state); if (!assets.some(a => a.asset_id === selectedAsset)) selectedAsset = assets[0]?.asset_id ?? '';
    const oldSource = sourceSelect.value; sourceSelect.replaceChildren(...assets.map(a => {const o = create('option', null, a.filename); o.value = a.asset_id; return o;}));
    sourceSelect.value = selectedAsset;
    if (oldSource && oldSource !== selectedAsset) revoke();
    const asset = assets.find(a => a.asset_id === selectedAsset);
    sourceFacts.textContent = asset ? `${asset.filename} · ${duration(asset).toFixed(2)} giây · ${(asset.size_bytes / 1048576).toFixed(2)} MiB · SHA ${asset.checksum_sha256.slice(0, 12)}` : 'Chưa có audio lời nói. Thêm file ở mục trên.';
    const row = currentRow(); let safe = false;
    try {if (row) {validateAudioRead(row, state); safe = true;}} catch {revoke(); status.textContent = 'Nguồn hoặc kết quả đã đổi. Tải lại để kiểm tra.';}
    const editable = !busy && !state.busy && !state.dirty && ranks[audioRole(state)] >= ranks.editor && capabilities?.human_write_enabled === true;
    const mutable = editable && safe && row.current && !activeJobs.has(row.job.status)
      && row.timeline_version === (state.timeline?.current_version ?? null) && (!audioHasCaptions(state, row) || compatibleAudioBinding(state, row));
    const viewingCurrent = row?.current?.transcript_id === history.value;
    root.setAttribute('aria-busy', String(busy));
    read.disabled = busy || state.busy || dirty || !!pending;
    sourceSelect.disabled = saved.disabled = history.disabled = busy || dirty || !!pending || !!upload;
    const blockedSource = rows.some(r => r.asset_id === selectedAsset && ['queued', 'running', 'needs_attention'].includes(r.job.status));
    requestAck.disabled = busy || !!pending; queue.disabled = !editable || !asset || dirty || !!upload || !requestAck.checked
      || pendingStorageError || blockedSource && pending?.kind !== 'create' || pending && pending.kind !== 'create';
    queue.textContent = pending?.kind === 'create' ? 'Thử lại đúng yêu cầu nhận diện trước' : 'Yêu cầu nhận diện audio đã chọn';
    uploadFile.disabled = mime.disabled = uploadRights.disabled = !editable || !!upload || !!pending || dirty;
    uploadButton.disabled = !editable || !!pending || dirty; uploadButton.textContent = upload ? 'Tiếp tục đúng phiên tải lên trước' : 'Tải audio lời nói lên';
    listen.disabled = busy || state.busy || !safe; cancel.disabled = !editable || !safe || !['queued', 'running', 'needs_attention'].includes(row.job.status) || dirty || pending && pending.kind !== 'cancel';
    saveText.disabled = !mutable || !viewingCurrent || !dirty || pending && pending.kind !== 'text';
    saveWords.disabled = !mutable || !viewingCurrent || !dirty || !wordAck.checked || pending && pending.kind !== 'words';
    discard.disabled = busy || !dirty || !!pending;
    restore.disabled = !mutable || viewingCurrent || !restoreAck.checked || dirty || pending && pending.kind !== 'restore';
    reconcile.hidden = !pending || pending.kind === 'apply'; reconcile.disabled = busy || state.busy || !pending;
    const bound = safe && state.timeline?.snapshot?.metadata?.uploaded_audio_bindings_v1?.[row.audio_id];
    applyButton.disabled = !mutable || !viewingCurrent || !state.timeline || !!bound && pending?.kind !== 'apply' || dirty || !applyAck.checked || pending && pending.kind !== 'apply';
    applyButton.textContent = pending?.kind === 'apply' ? 'Thử lại đúng yêu cầu thêm audio/phụ đề trước' : 'Thêm audio và phụ đề đã kiểm tra';
    applyAck.disabled = muteOriginal.disabled = busy || !!pending || !mutable;
    for (const input of Object.values(applyNumbers)) input.disabled = busy || !!pending || !mutable;
    note.disabled = wordAck.disabled = !mutable || !viewingCurrent || !!pending;
    restoreAck.disabled = !mutable || viewingCurrent || !!pending;
    for (const input of editor.querySelectorAll('input,textarea,button')) input.disabled = !mutable || !viewingCurrent || !!pending;
    job.textContent = safe ? `${statuses[row.job.status]}${row.job.error?.code ? ` · ${row.job.error.code}` : ''} · ${row.job.job_id}` : 'Chưa chọn yêu cầu đã lưu.';
    warning.textContent = safe && audioHasCaptions(state, row) ? compatibleAudioBinding(state, row)
      ? 'Audio và phụ đề đã gắn đúng bản hiện tại. Sửa lời/từ sẽ lưu cả timeline mới và cần nghe, tạo preview và duyệt video lại.'
      : 'Audio đã gắn với phụ đề timeline nhưng liên kết đang khóa, sửa tay hoặc chưa khớp. Sửa/khôi phục cần kiểm tra riêng; chưa được lưu.'
      : safe && row.timeline_version !== (state.timeline?.current_version ?? null) ? 'Timeline đã đổi; tải lại dự án và audio trước khi sửa.' : '';
    if (!state.projectId) status.textContent = 'Tạo hoặc chọn dự án trước khi dùng audio lời nói.';
  }
  async function run(fn) {
    if (busy) return;
    sync(); busy = true; const start = identity; sync();
    try {await fn();} catch (error) {if (scope(getState()) === start) announce(errorText(error), true);}
    finally {busy = false; sync();}
  }
  function binding(assetId) {return {epoch, identity, revision: revisionScope(getState(), assetId)};}
  function still(bound, assetId) {
    try {return bound.epoch === epoch && bound.identity === scope(getState()) && bound.revision === revisionScope(getState(), assetId);} catch {return false;}
  }
  function endpoint(audioId = '') {return `/api/v1/projects/${getState().projectId}/audio-transcriptions${audioId ? `/${audioId}` : ''}`;}
  function selectRow({keepPlayback = false} = {}) {
    const row = currentRow(); if (!keepPlayback) revoke(); dirty = false; note.value = ''; wordAck.checked = restoreAck.checked = false;
    applyAck.checked = muteOriginal.checked = false; resetApplyFields();
    if (row) selectedAsset = row.asset_id;
    history.replaceChildren(...(row?.versions ?? []).map(v => {const o = create('option', null,
      `Bản ${v.version}${v.is_original_evidence ? ' · gốc' : ''}${v.transcript_id === row.current?.transcript_id ? ' · hiện tại' : ''} · ${v.created_at}`); o.value = v.transcript_id; return o;}));
    history.value = row?.current?.transcript_id ?? ''; renderTranscript(); sync();
  }
  function adopt(value) {
    validateAudioRead(value, getState()); rows = [...rows.filter(r => r.audio_id !== value.audio_id), copy(value)]; selectedId = value.audio_id;
    renderSaved(); selectRow();
  }
  function renderSaved() {saved.replaceChildren(...rows.map(r => {const o = create('option', null,
    `${assetFor(getState(), r.asset_id).filename} · ${statuses[r.job.status]} · ${r.audio_id.slice(-8)}`); o.value = r.audio_id; return o;})); saved.value = selectedId;}
  function schedule() {
    stop(); if (dirty || pending || !rows.some(r => activeJobs.has(r.job.status)) || pollCount >= 120) return;
    timer = timers.setTimeout(() => {
      timer = null; if (busy || getState().busy) {schedule(); return;}
      pollCount++; run(() => reload(true));
    }, pollMs);
  }
  async function reload(poll = false) {
    demand(!dirty && !pending, 'Lưu/bỏ sửa hoặc đối chiếu yêu cầu trước khi tải lại.');
    const start = {epoch, identity: scope(getState())}; demand(getState().projectId && audioRole(getState()), 'Cần đăng nhập và chọn dự án.');
    const result = await Promise.all([api('/api/v1/capabilities'), api(endpoint())]);
    if (start.epoch !== epoch || start.identity !== scope(getState())) return;
    const [caps, values] = result; demand(Array.isArray(values), 'Danh sách audio không hợp lệ.');
    values.forEach(v => validateAudioRead(v, getState())); demand(new Set(values.map(v => v.audio_id)).size === values.length, 'Danh sách audio bị trùng.');
    const previous = currentRow();
    capabilities = caps; rows = copy(values); provider.textContent = !['openai', 'assemblyai'].includes(caps.transcription_provider)
      ? 'NOT_CONFIGURED · nhận diện audio mặc định tắt. Không thay bằng kết quả thử nghiệm.'
      : `${caps.transcription_provider} · ${caps.asr_external_execution_enabled === true ? 'cổng ASR ngoài đã bật' : 'cổng ASR ngoài đang tắt'} · ${caps.asr_paid_execution_enabled === true ? 'cổng chi phí đã bật' : 'cổng chi phí đang tắt'} · chưa phải nghiệm thu ASR.`;
    if (!rows.some(r => r.audio_id === selectedId)) selectedId = rows[0]?.audio_id ?? '';
    const current = currentRow(), keepPlayback = poll && previous && current && previous.audio_id === current.audio_id
      && previous.source_sha256 === current.source_sha256;
    renderSaved(); selectRow({keepPlayback}); if (!poll) {pollCount = 0; status.textContent = `Đã đọc ${rows.length} yêu cầu; bản gốc và lịch sử được giữ nguyên.`;}
    schedule(); sync();
  }
  function renderTranscript() {
    const row = currentRow(), transcript = row?.versions.find(v => v.transcript_id === history.value);
    draft = transcript ? copy(transcript) : null; editor.replaceChildren();
    evidence.textContent = transcript ? `${transcript.provider_key} · ${transcript.language} · `
      + (transcript.provenance.fixture === true || /fixture|mock/i.test(transcript.provider_key) ? 'FIXTURE · dữ liệu kiểm thử, không phải ASR thật. '
        : transcript.provenance.human_edit ? 'Bản người dùng sửa; thời gian có thể do người sửa cung cấp. ' : 'Lời dịch vụ trả về; cần nghe và kiểm tra. ')
      + `${transcript.segments.length} đoạn · ${transcript.segments.reduce((sum, s) => sum + s.words.length, 0)} từ có thời gian.` : 'Chưa có lời nhận diện. Job bị chặn không tạo nội dung giả.';
    for (const segment of draft?.segments ?? []) {
      const area = create('fieldset'); area.append(create('legend', null, `Đoạn ${segment.ordinal + 1} · ${displaySeconds(segment.start_seconds)}–${displaySeconds(segment.end_seconds)} giây`));
      const text = create('textarea'); text.rows = 2; text.maxLength = 4000; text.value = segment.text; text.setAttribute('data-audio-segment-text', segment.segment_id);
      text.addEventListener('input', () => {segment.text = text.value; markDirty();}); area.append(label('Lời của đoạn', text));
      const wordArea = create('details'); wordArea.append(create('summary', null, 'Sửa từng từ và thời gian theo audio gốc'));
      const segmentTime = (field, title) => {const input = create('input'); input.type = 'number'; input.min = '0'; input.step = '0.001'; input.value = String(segment[field]);
        input.addEventListener('input', () => {segment[field] = input.value.trim() === '' ? NaN : Number(input.value); markDirty();}); wordArea.append(label(title, input));};
      segmentTime('start_seconds', 'Đoạn bắt đầu (giây)'); segmentTime('end_seconds', 'Đoạn kết thúc (giây)');
      const words = create('div'); const renderWords = () => {
        words.replaceChildren(); segment.words.forEach((word, i) => {
          const line = create('div'); line.className = 'uploaded-audio-word';
          for (const [field, title, type] of [['text', `Từ ${i + 1}`, 'text'], ['start_seconds', 'Bắt đầu (giây)', 'number'], ['end_seconds', 'Kết thúc (giây)', 'number']]) {
            const input = create('input'); input.type = type; input.value = String(word[field] ?? ''); if (type === 'number') {input.min = '0'; input.step = '0.001';} else input.maxLength = 240;
            input.addEventListener('input', () => {word[field] = type === 'number' ? input.value.trim() === '' ? NaN : Number(input.value) : input.value; markDirty();}); line.append(label(title, input));
          }
          const remove = create('button', null, 'Bỏ từ'); remove.type = 'button'; remove.addEventListener('click', () => {if (busy || pending) return; segment.words.splice(i, 1); renderWords(); markDirty();}); line.append(remove); words.append(line);
        });
      };
      renderWords(); const add = create('button', null, 'Thêm từ (tự nhập thời gian)'); add.type = 'button'; add.addEventListener('click', () => {
        if (busy || pending) return; segment.words.push({text: '', start_seconds: '', end_seconds: ''}); renderWords(); markDirty();
      }); wordArea.append(words, add); area.append(wordArea); editor.append(area);
    }
  }
  function exactPending(kind, row, make) {
    demand(capabilities?.human_write_enabled === true, 'Chưa đọc cấu hình hoặc ghi dữ liệu đang tắt.');
    if (pending) {
      const matchingScope = kind === 'apply' ? pending.actor === getState().principal?.subject
        && assetFor(getState(), pending.assetId).checksum_sha256 === pending.body.source_sha256
        : pending.revision === revisionScope(getState(), pending.assetId);
      demand(pending.kind === kind && pending.audioId === row?.audio_id && matchingScope,
        'Giữ nguyên yêu cầu chưa rõ kết quả; không chuyển nguồn, phiên bản hoặc kiểu sửa.');
      writeGuard(getState()); return pending;
    }
    const body = make(); return {kind, audioId: row?.audio_id, base: row ? copy(row) : null, actor: getState().principal.subject, assetId: row?.asset_id ?? body.asset_id,
      revision: revisionScope(getState(), row?.asset_id ?? body.asset_id), body};
  }
  async function submit(operation, suffix = '') {
    const bound = binding(operation.assetId); if (operation.kind === 'create') preserveCreate(operation); pending = operation; sync();
    try {
      if (operation.kind === 'create' && !operation.expectedId) operation.expectedId = `aud_${(await audioByteHash(
        new TextEncoder().encode(JSON.stringify([getState().projectId, operation.body.idempotency_key])), cryptoImpl)).slice(0, 24)}`;
      if (!still(bound, operation.assetId)) return;
      const value = await api(endpoint(operation.audioId) + suffix, {method: 'POST', body: JSON.stringify(operation.body)});
      if (!still(bound, operation.assetId)) return;
      validateAudioRead(value, getState());
      demand(value.asset_id === operation.assetId && (!operation.audioId || value.audio_id === operation.audioId), 'Phản hồi thuộc yêu cầu khác.');
      demand(operation.kind !== 'create' || value.audio_id === operation.expectedId, 'Phản hồi nhận diện không khớp khóa yêu cầu.');
      if (['text', 'words', 'restore'].includes(operation.kind)) {
        demand(audioRevisionMatches(value, operation.base, operation.kind, operation.body, operation.actor),
          'Bản trả về chưa chứng minh đúng yêu cầu sửa. Giữ bản đang sửa và đối chiếu; không tự thay bằng bản của người khác.');
      }
      clearPending(); dirty = false; adopt(value); pollCount = 0; schedule();
      if (operation.kind === 'create') requestAck.checked = false;
      if (operation.base && value.timeline_version !== operation.base.timeline_version && !getState().dirty) await onCanonicalSaved();
      announce(operation.kind === 'create' ? 'Đã lưu yêu cầu; chờ dịch vụ, chưa có lời nhận diện giả.' : operation.kind === 'cancel' ? 'Đã đọc trạng thái sau yêu cầu hủy.' : 'Đã lưu phiên bản mới; bản gốc và các bản cũ được giữ nguyên.');
    } catch (error) {
      if (!still(bound, operation.assetId)) return;
      // A response that proves rejection releases the request. Transport/5xx
      // uncertainty retains the exact key/CAS; never issue a fresh paid request.
      if (error.status >= 400 && error.status < 500 || /NOT_CONFIGURED/.test(errorCode(error))) clearPending();
      else status.textContent = 'Chưa biết yêu cầu đã lưu hay chưa. Đối chiếu hoặc thử lại đúng yêu cầu; không tự tạo yêu cầu mới.';
      throw error;
    }
  }
  async function queueAudio() {
    demand(!dirty && !upload, 'Lưu hoặc bỏ thay đổi audio trước khi nhận diện.');
    demand(pending?.kind === 'create' || !rows.some(r => r.asset_id === selectedAsset && ['queued', 'running', 'needs_attention'].includes(r.job.status)),
      'Nguồn này còn yêu cầu đang chạy hoặc chưa rõ kết quả dịch vụ. Đọc trạng thái/hủy để kiểm tra; không tạo nhận diện mới.');
    const operation = exactPending('create', null, () => audioCreatePayload(getState(), selectedAsset, newKey(), requestAck.checked));
    await submit(operation);
  }
  async function saveRevision(kind) {
    const row = currentRow(); const operation = exactPending(kind, row, () => {
      demand(dirty && draft?.transcript_id === row?.current?.transcript_id, 'Chỉ sửa bản hiện tại; tải lại nếu bản đã đổi.');
      if (kind === 'text') {
        demand(draft.segments.every((s, i) => same(s.words, row.current.segments[i].words) && s.start_seconds === row.current.segments[i].start_seconds
          && s.end_seconds === row.current.segments[i].end_seconds), 'Bạn đang sửa từ/thời gian. Dùng nút lưu từ hoặc bỏ sửa trước khi sửa lời đơn thuần.');
        return audioTextPayload(getState(), row, draft.segments.filter((s, i) => s.text.normalize('NFC') !== row.current.segments[i].text).map(s => ({segment_id: s.segment_id, text: s.text})), note.value);
      }
      demand(draft.segments.every((s, i) => s.text === row.current.segments[i].text), 'Bạn đang sửa lời đơn thuần. Lưu hoặc bỏ sửa trước khi sửa từ và thời gian.');
      return audioWordsPayload(getState(), row, draft.segments.filter((s, i) => !same(s.words, row.current.segments[i].words)
        || s.start_seconds !== row.current.segments[i].start_seconds || s.end_seconds !== row.current.segments[i].end_seconds)
        .map(s => ({segment_id: s.segment_id, start_seconds: s.start_seconds, end_seconds: s.end_seconds,
          words: s.words.map(w => ({...(w.word_id ? {word_id: w.word_id} : {}), text: w.text, start_seconds: w.start_seconds, end_seconds: w.end_seconds}))})), wordAck.checked, note.value);
    });
    await submit(operation, kind === 'text' ? '/transcript' : '/transcript-words');
  }
  async function restoreAudio() {
    demand(!dirty, 'Lưu hoặc bỏ sửa trước khi khôi phục.'); const row = currentRow();
    await submit(exactPending('restore', row, () => audioRestorePayload(getState(), row, history.value, restoreAck.checked, note.value)), '/restore');
  }
  async function cancelAudio() {
    demand(!dirty, 'Lưu hoặc bỏ sửa trước khi hủy.'); writeGuard(getState()); const row = currentRow(); validateAudioRead(row, getState());
    await submit(exactPending('cancel', row, () => ({})), '/cancel');
  }
  async function reconcileAudio() {
    demand(pending, 'Không có yêu cầu cần đối chiếu.'); const operation = pending, bound = binding(operation.assetId);
    let id = operation.audioId;
    const caps = await api('/api/v1/capabilities'); if (!still(bound, operation.assetId)) return; capabilities = caps;
    if (!id) id = `aud_${(await audioByteHash(new TextEncoder().encode(JSON.stringify([getState().projectId, operation.body.idempotency_key])), cryptoImpl)).slice(0, 24)}`;
    const value = await api(endpoint(id)); if (!still(bound, operation.assetId)) return;
    validateAudioRead(value, getState()); demand(value.audio_id === id && value.asset_id === operation.assetId, 'Phản hồi đối chiếu sai yêu cầu.');
    if (operation.kind === 'create' || operation.kind === 'cancel' && !['queued', 'running', 'needs_attention'].includes(value.job.status)
      || ['text', 'words', 'restore'].includes(operation.kind) && audioRevisionMatches(value, operation.base, operation.kind, operation.body, operation.actor)) {
      clearPending(); dirty = false; adopt(value); schedule();
      if (operation.base && value.timeline_version !== operation.base.timeline_version && !getState().dirty) await onCanonicalSaved();
      announce('Đã đọc kết quả đang lưu trên máy chủ. Kiểm tra bản mới trước khi sửa tiếp.');
    } else {
      const version = value.current?.version;
      announce(version && version !== operation.base?.current?.version
        ? `Máy chủ hiện có bản ${version}, chưa chứng minh đúng yêu cầu của bạn. Giữ nguyên bản sửa và khóa yêu cầu; cần đối chiếu xung đột trước khi tiếp tục.`
        : 'Máy chủ vẫn giữ bản/trạng thái trước. Yêu cầu có thể còn đang xử lý; chỉ thử lại đúng yêu cầu cũ.');
    }
  }
  async function applyAudio() {
    demand(!dirty, 'Lưu hoặc bỏ sửa lời trước khi thêm audio/phụ đề.'); const row = currentRow();
    demand(history.value === row?.current?.transcript_id, 'Xem và kiểm tra bản hiện tại trước khi thêm phụ đề; bản cũ cần khôi phục rõ ràng.');
    const operation = exactPending('apply', row, () => audioCaptionPayload(getState(), row, newKey(), {
      source_start: applyNumbers['source-start'].value.trim() === '' ? NaN : Number(applyNumbers['source-start'].value),
      source_end: applyNumbers['source-end'].value.trim() === '' ? NaN : Number(applyNumbers['source-end'].value),
      timeline_start: applyNumbers['timeline-start'].value.trim() === '' ? NaN : Number(applyNumbers['timeline-start'].value),
      speed: applyNumbers.speed.value.trim() === '' ? NaN : Number(applyNumbers.speed.value),
      mute_original: muteOriginal.checked, acknowledged: applyAck.checked}));
    const bound = binding(operation.assetId); pending = operation; sync();
    try {
      const receipt = await api(endpoint(operation.audioId) + '/apply-captions', {method: 'POST', body: JSON.stringify(operation.body)});
      if (!still(bound, operation.assetId)) return;
      demand(receipt.audio_id === operation.audioId && /^abn_[a-f0-9]{24}$/.test(receipt.binding_id)
        && receipt.applied_timeline_version === operation.body.expected_timeline_version + 1
        && typeof receipt.replayed === 'boolean' && receipt.human_review_required === true, 'Biên nhận thêm audio/phụ đề không khớp yêu cầu.');
      // Receipt proves the idempotent write. Read canonical state before enabling
      // edits; the parent refresh preserves unrelated local Studio drafts.
      const value = await api(endpoint(operation.audioId)); if (!still(bound, operation.assetId)) return;
      validateAudioRead(value, getState()); demand(value.audio_id === operation.audioId, 'Kết quả đọc sau thêm sai audio.');
      clearPending(); adopt(value); applyAck.checked = muteOriginal.checked = false;
      if (!getState().dirty) await onCanonicalSaved();
      announce('Đã có biên nhận thêm audio/phụ đề. Timeline cần preview, nghe và duyệt lại; chưa duyệt video.');
    } catch (error) {
      if (!still(bound, operation.assetId)) return;
      if (error.status >= 400 && error.status < 500) clearPending();
      throw error;
    }
  }
  async function listenAudio() {
    const row = currentRow(); validateAudioRead(row, getState()); const asset = assetFor(getState(), row.asset_id), bound = binding(row.asset_id);
    demand(asset.size_bytes > 0 && asset.size_bytes <= playbackMaxBytes, 'Panel nghe hỗ trợ tối đa 32 MiB; nguồn lớn cần công cụ nghe riêng.');
    revoke(); playbackAbort = new AbortController(); const signal = playbackAbort.signal;
    try {
      const response = await mediaFetch(endpoint(row.audio_id) + '/source', {cache: 'no-store', signal});
      demand(response.ok && response.status === 200 && response.headers.get('content-type')?.split(';')[0] === asset.content_type
        && response.headers.get('cache-control')?.includes('no-store'), 'Không lấy được audio gốc đã xác minh.');
      const bytes = await boundedAudioBytes(response, asset.size_bytes, signal); if (!still(bound, row.asset_id)) {revoke(); return;}
      demand(bytes.byteLength === asset.size_bytes && await audioByteHash(bytes, cryptoImpl) === row.source_sha256, 'Checksum/kích thước audio nghe không khớp nguồn.');
      if (!still(bound, row.asset_id)) {revoke(); return;}
      revoke(); audioUrl = urls.createObjectURL(new Blob([bytes], {type: asset.content_type})); player.src = audioUrl; player.hidden = false;
      status.textContent = 'Audio gốc đã khớp checksum. Dùng nút phát để nghe và đối chiếu lời nhận diện.';
    } catch (error) {revoke(); throw error;}
  }
  function validateUpload(value, file, checksum, projectId, workspaceId) {
    demand(value && /^upl_[A-Za-z0-9_-]{4,60}$/.test(value.upload_id) && value.project_id === projectId && value.workspace_id === workspaceId
      && value.media_kind === 'audio' && value.size_bytes === file.size && value.expected_checksum_sha256 === checksum
      && Number.isInteger(value.part_size_bytes) && value.part_size_bytes >= 65536 && value.part_size_bytes <= 33554432
      && value.total_parts === Math.ceil(file.size / value.part_size_bytes) && Array.isArray(value.received_parts), 'Phiên tải lên sai nguồn hoặc dự án.');
    return value;
  }
  async function uploadAudio() {
    writeGuard(getState()); demand(capabilities?.human_write_enabled === true, 'Tải danh sách để đọc quyền ghi trước khi tải audio.');
    demand(!dirty && !pending, 'Lưu hoặc đối chiếu yêu cầu trước khi tải audio.');
    const start = {epoch, identity: scope(getState())}, state = getState(), projectId = state.projectId, workspaceId = state.workspaceId;
    const valid = () => start.epoch === epoch && start.identity === scope(getState()) && !getState().dirty && !getState().busy;
    const file = upload?.file ?? uploadFile.files?.[0];
    demand(file && file.size > 0 && file.size <= maxBytes && file.name.length <= 255 && uploadRights.checked === true && mimeTypes.includes(mime.value),
      'Chọn audio tối đa 64 MiB, đúng định dạng và xác nhận quyền sử dụng.');
    const checksum = upload?.checksum ?? await audioByteHash(await file.arrayBuffer(), cryptoImpl); if (!valid()) return;
    if (!upload) {
      const value = await api('/api/v1/uploads/init', {method: 'POST', body: JSON.stringify({project_id: projectId, filename: file.name,
        media_kind: 'audio', content_type: mime.value, size_bytes: file.size, checksum_sha256: checksum, rights_status: 'owned'})});
      if (!valid()) return; validateUpload(value, file, checksum, projectId, workspaceId); upload = {file, checksum, session: value};
    } else {
      const value = await api(`/api/v1/uploads/${upload.session.upload_id}`); if (!valid()) return;
      upload.session = validateUpload(value, file, checksum, projectId, workspaceId);
    }
    sync(); const session = upload.session;
    for (let part = 1; part <= session.total_parts; part++) {
      const partBody = file.slice((part - 1) * session.part_size_bytes, part * session.part_size_bytes);
      const partHash = await audioByteHash(await partBody.arrayBuffer(), cryptoImpl); if (!valid()) return;
      const received = session.received_parts.find(p => p.part_number === part);
      if (received) {demand(received.size_bytes === partBody.size && received.checksum_sha256 === partHash, 'Phần đã lưu không khớp file đang tải.'); continue;}
      demand(['initialized', 'uploading'].includes(session.status), 'Phiên tải lên đã khóa; kiểm tra trạng thái trước khi tiếp tục.');
      const response = await mediaFetch(`/api/v1/uploads/${session.upload_id}/parts/${part}`, {method: 'PUT', body: partBody, headers: {'X-Part-SHA256': partHash}});
      demand(response.ok, `Phần tải lên chưa rõ kết quả (${response.status}); dùng nút tiếp tục để đọc trạng thái trước.`);
      const value = await response.json(); if (!valid()) return; validateUpload(value, file, checksum, projectId, workspaceId); session.received_parts = value.received_parts; session.status = value.status;
    }
    const result = await api(`/api/v1/uploads/${session.upload_id}/complete`, {method: 'POST', body: JSON.stringify({checksum_sha256: checksum})});
    if (!valid()) return; validateUpload(result.upload, file, checksum, projectId, workspaceId);
    demand(['completed', 'completed_duplicate'].includes(result.upload.status) && result.upload.quarantine_state === 'trusted'
      && result.checksum_sha256 === checksum && result.asset_id === result.upload.asset_id && result.media_metadata?.media_kind === 'audio', 'Audio chưa qua kiểm tra nguồn an toàn.');
    upload = null; uploadFile.value = ''; uploadRights.checked = false; await onUploaded();
    if (scope(getState()) === start.identity) announce('Audio lời nói đã lưu qua kiểm tra nguồn. Chọn file rồi yêu cầu nhận diện khi cần.');
  }
  sync();
  return {sync, reload: () => run(() => reload()), dispose: () => {reset();}, isDirty: () => dirty || !!pending || !!upload};
}
