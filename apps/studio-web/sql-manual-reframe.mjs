// Explicit manual source-second crops. The server owns geometry; no Vision dispatch.
import {audioRole, audioByteHash} from './uploaded-audio-review.mjs';
import {videoAnalysisAssets} from './video-analysis-jobs.mjs';
import {sessionToken as browserSessionToken} from './auth.mjs';
import {videoWordSessionStorage} from './video-transcript-word-review.mjs';

const copy = structuredClone;
const stable = value => JSON.stringify(value, (_key, value) => value && typeof value === 'object' && !Array.isArray(value)
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, value[key]])) : value);
const same = (a, b) => stable(a) === stable(b);
const demand = (condition, message) => {if (!condition) throw Error(message);};
const object = value => value && typeof value === 'object' && !Array.isArray(value);
const exact = (value, fields) => object(value) && same(Object.keys(value).sort(), [...fields].sort());
const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const keyValid = value => typeof value === 'string' && /^[A-Za-z0-9_-]{8,128}$/.test(value);
const finite = (value, low, high = Infinity) => typeof value === 'number' && Number.isFinite(value) && value >= low && value <= high;
const freeze = value => {if (object(value) || Array.isArray(value)) {Object.values(value).forEach(freeze); Object.freeze(value);} return value;};
const ratios = ['9:16', '16:9', '1:1', '4:5'];
export function manualReframeSettings(value, duration = Infinity) {
  demand(exact(value, ['aspect_ratio', 'points']) && typeof value.aspect_ratio === 'string' && ratios.includes(value.aspect_ratio)
    && Array.isArray(value.points) && value.points.length >= 1 && value.points.length <= 200,
  'Chọn một tỷ lệ và từ 1 đến 200 điểm crop rõ ràng.');
  let previous = -1;
  for (const p of value.points) {
    demand(exact(p, ['time', 'x', 'y', 'zoom']) && finite(p.time, 0, duration) && p.time > previous
      && finite(p.x, 0, 1) && finite(p.y, 0, 1) && finite(p.zoom, 1, 4),
    'Điểm crop phải tăng theo giây nguồn; x/y từ 0 đến 1 và zoom từ 1 đến 4.');
    previous = p.time;
  }
  return value;
}

function timeline(value, s) {
  demand(object(value) && value.workspace_id === s.workspaceId && value.project_id === s.projectId
    && /^tml_[A-Za-z0-9_-]{4,60}$/.test(value.timeline_id) && typeof value.current_version_id === 'string' && value.current_version_id
    && Number.isSafeInteger(value.current_version) && value.current_version >= 1 && value.source_kind === 'video_analysis'
    && value.source_media_mutated === false && value.publish_requested === false && object(value.snapshot)
    && object(value.snapshot.metadata) && Array.isArray(value.snapshot.tracks) && finite(value.snapshot.duration_seconds, Number.MIN_VALUE, 86400)
    && value.snapshot.source_media_mutated === false && value.snapshot.publish_requested === false,
  'Timeline nguồn thiếu bằng chứng hoặc không thuộc dự án hiện tại.'); return value;
}
function source(s, t = s.timeline) {
  timeline(t, s); const a = s.analysis, meta = t.snapshot.metadata;
  const asset = videoAnalysisAssets(s).find(asset => asset.asset_id === meta.source_asset_id);
  demand(asset && a?.analysis_id === t.source_analysis_id && a.analysis_id === meta.source_analysis_id
    && a.asset_id === asset.asset_id && a.workspace_id === s.workspaceId && a.project_id === s.projectId
    && a.status === 'succeeded' && hash(a.fingerprint) && a.source_media_mutated === false && a.publish_requested === false
    && a.configuration?.asset_id === asset.asset_id && a.source_media?.media_kind === 'video'
    && finite(a.source_media.duration_seconds, Number.MIN_VALUE) && a.source_media.duration_seconds === meta.source_duration_seconds
    && asset.provenance.media_metadata.duration_seconds === meta.source_duration_seconds
    && Object.hasOwn(a.source_media, 'audio_codec') && !['', 'unknown'].includes(a.source_media.audio_codec)
    && Number.isSafeInteger(a.source_media.width) && a.source_media.width >= 1
    && Number.isSafeInteger(a.source_media.height) && a.source_media.height >= 1
    && finite(a.source_media.fps, Number.MIN_VALUE)
    && ['width', 'height', 'fps'].every(key => a.source_media[key] === asset.provenance.media_metadata[key]),
  'Cần kết quả phân tích và video nguồn đúng với timeline.');
  const revision = meta.transcript_revision, hasAudio = a.source_media.audio_codec !== null;
  demand(revision === undefined || revision === null || object(revision) && /^trn_[a-f0-9]{24}$/.test(revision.transcript_id)
    && Number.isSafeInteger(revision.version) && revision.version >= 1, 'Phiên bản lời nói nguồn chưa xác định.');
  demand(!hasAudio || revision != null, 'Nguồn có lời nói cần transcript đã được chọn.');
  const proof = {analysis_id: a.analysis_id, analysis_fingerprint: a.fingerprint, asset_id: asset.asset_id,
    source_sha256: asset.checksum_sha256, object_key: asset.object_key, duration_seconds: meta.source_duration_seconds, has_audio: hasAudio,
    transcript_id: revision?.transcript_id ?? null, transcript_version: revision?.version ?? null,
    width: a.source_media.width, height: a.source_media.height, fps: a.source_media.fps};
  demand(typeof proof.object_key === 'string' && proof.object_key, 'Nguồn chưa có tham chiếu lưu trữ.');
  return {proof, ui: {timeline_id: t.timeline_id, workspace_id: s.workspaceId, project_id: s.projectId,
    source_analysis_id: t.source_analysis_id, source_kind: t.source_kind, source_asset_id: meta.source_asset_id,
    source_duration_seconds: meta.source_duration_seconds, transcript_revision: copy(revision ?? null), analysis: copy(a), asset: copy(asset)}};
}
function receiptSource(value, s, t) {
  demand(exact(value, ['analysis_id', 'analysis_fingerprint', 'asset_id', 'source_sha256', 'object_key', 'duration_seconds',
    'has_audio', 'transcript_id', 'transcript_version', 'transcript_sha256', 'width', 'height', 'fps']), 'Biên nhận nguồn thiếu trường kiểm tra.');
  const proof = source(s, t).proof;
  for (const [key, item] of Object.entries(proof)) demand(same(value[key], item), 'Biên nhận không khớp video hoặc transcript đã chọn.');
  demand(proof.transcript_id === null ? value.transcript_sha256 === null : hash(value.transcript_sha256), 'Hash transcript nguồn chưa hợp lệ.');
}
function appliedPath(value, settings, proof) {
  demand(Array.isArray(value) && value.length === settings.points.length, 'Đường crop thiếu điểm đã áp dụng.');
  for (let i = 0; i < value.length; i++) {
    const p = value[i]; demand(exact(p, ['time', 'x', 'y', 'width', 'height']) && p.time === settings.points[i].time
      && finite(p.time, 0, proof.duration_seconds) && finite(p.x, 0, 1) && finite(p.y, 0, 1)
      && finite(p.width, Number.MIN_VALUE, 1) && finite(p.height, Number.MIN_VALUE, 1)
      && p.x + p.width <= 1.000001 && p.y + p.height <= 1.000001, 'Đường crop áp dụng không nằm trong nguồn.');
    const request = settings.points[i], [tw, th] = settings.aspect_ratio.split(':').map(Number);
    const relative = (proof.width / proof.height) / (tw / th), scale = Math.max(relative, 1 / relative) * request.zoom;
    const width = Math.min(1, relative >= 1 ? 1 / scale : (1 / relative) / scale);
    const height = Math.min(1, relative >= 1 ? relative / scale : 1 / scale);
    const expected = {x: Math.max(0, Math.min(1 - width, request.x - width / 2)),
      y: Math.max(0, Math.min(1 - height, request.y - height / 2)), width, height};
    demand(Object.keys(expected).every(k => Math.abs(p[k] - expected[k]) <= 1e-9),
      'Đường crop áp dụng không khớp tọa độ và zoom đã chọn.');
  }
}
export function manualReframeRead(value, s) {
  demand(exact(value, ['timeline', 'source', 'source_binding_sha256', 'settings', 'receipt', 'replayed'])
    && typeof value.replayed === 'boolean' && (!value.replayed || value.receipt !== null) && hash(value.source_binding_sha256),
  'API crop thủ công thiếu bằng chứng nguồn hiện tại.');
  const t = timeline(value.timeline, s); source(s, t); receiptSource(value.source, s, t);
  if (value.settings !== null) {
    manualReframeSettings(value.settings, value.source.duration_seconds);
    demand(same(t.snapshot.metadata.manual_reframe?.settings, value.settings)
      && same(t.snapshot.metadata.manual_reframe?.source, value.source)
      && t.snapshot.aspect_ratio === value.settings.aspect_ratio, 'Thiết lập crop chưa khớp timeline hiện tại.');
  }
  if (value.receipt !== null) {
    const r = value.receipt;
    demand(exact(r, ['schema_version', 'request_key', 'request_sha256', 'workspace_id', 'project_id', 'timeline_id',
      'parent_version_id', 'parent_version', 'result_version', 'actor_ref', 'source', 'settings', 'applied_keyframes', 'result_snapshot_sha256'])
      && r.schema_version === 'manual-reframe-v1' && keyValid(r.request_key) && hash(r.request_sha256) && hash(r.result_snapshot_sha256)
      && r.workspace_id === t.workspace_id && r.project_id === t.project_id && r.timeline_id === t.timeline_id
      && typeof r.parent_version_id === 'string' && r.parent_version_id && Number.isSafeInteger(r.parent_version) && r.parent_version >= 1
      && r.result_version === r.parent_version + 1 && r.result_version === t.current_version
      && typeof r.actor_ref === 'string' && r.actor_ref && same(r.source, value.source) && same(r.settings, value.settings),
    'Biên nhận crop thủ công không đúng timeline và nguồn.');
    manualReframeSettings(r.settings, r.source.duration_seconds); appliedPath(r.applied_keyframes, r.settings, r.source);
    const tracks = t.snapshot.tracks.filter(track => track.kind === 'source' && track.type === 'video');
    demand(tracks.length === 1 && tracks[0].clips.length > 0 && tracks[0].clips.every(clip =>
      clip.asset_id === r.source.asset_id && clip.metadata?.reframe?.time_space === 'source_seconds'
      && clip.metadata.reframe.confidence === null && clip.metadata.reframe.needs_attention === true
      && clip.metadata.reframe.strategy === 'manual_override' && same(clip.metadata.reframe.keyframes, r.applied_keyframes)),
    'Biên nhận crop chưa khớp đường keyframe canonical.');
  }
  return value;
}

function scope(s) {const p = s.principal; return stable([s.workspaceId, s.projectId,
  {subject: p?.subject, display_name: p?.display_name, platform_role: p?.platform_role, workspace_roles: p?.workspace_roles,
    expires_at: p?.expires_at, human_write_enabled: p?.human_write_enabled}, audioRole(s)]);}
function session(s, write = false) {
  demand(/^wsp_[A-Za-z0-9_-]{4,60}$/.test(s.workspaceId) && /^prj_[A-Za-z0-9_-]{4,60}$/.test(s.projectId)
    && typeof s.principal?.subject === 'string' && s.principal.subject.trim() && Number.isFinite(Date.parse(s.principal.expires_at))
    && Date.parse(s.principal.expires_at) > Date.now() && ['viewer', 'editor', 'reviewer', 'owner'].includes(audioRole(s)),
  'Cần phiên truy cập đúng dự án và còn hiệu lực.');
  if (write) demand(['editor', 'reviewer', 'owner'].includes(audioRole(s)) && s.principal.human_write_enabled === true,
    'Phiên này chưa được phép chỉnh nguồn.');
  demand(!s.busy && !s.dirty, 'Lưu thay đổi khác và chờ Studio tải xong trước.'); source(s);
}
function binding(s) {return stable([scope(s), s.timeline, source(s).ui]);}
function settingsForSource(settings, s) {
  manualReframeSettings(settings, source(s).proof.duration_seconds);
  const tracks = s.timeline.snapshot.tracks.filter(t => t.type === 'video' && t.kind === 'source');
  demand(tracks.length === 1 && !tracks[0].locked && !tracks[0].disabled && tracks[0].clips.some(c => !c.disabled),
    'Chỉ chỉnh đường crop trên track nguồn đang bật và chưa khóa.');
  return settings;
}

export function initializeSqlManualReframe({root, api, getState, getSessionToken = browserSessionToken,
  onSaved = async () => {}, onRead = async () => {}, onBusyChanged = () => {}, onMessage = () => {}, dom = globalThis.document,
  storage = videoWordSessionStorage(), cryptoImpl = globalThis.crypto, newRequestKey = () => 'mrf_' + cryptoImpl.randomUUID()}) {
  let disposed = false, working = false, context = scope(getState()), epoch = 0, literal = token(), view = null, held = null, pending = null;
  const retained = new Map(), observed = new Map(), parents = new Map(); let statusText = 'Chưa đọc đường crop thủ công. Chỉ lưu sau thao tác và xác nhận rõ ràng.';
  const controls = {};
  if (root) {
    const make = (tag, name, text) => {const e = dom.createElement(tag); e.setAttribute('data-manual-reframe-' + name, ''); e.textContent = text; return e;};
    const status = controls.status = make('p', 'status', statusText); status.setAttribute('role', 'status');
    for (const [name, label, fn] of [['read', 'Đọc đường crop đã lưu', reload], ['reconcile', 'Đối chiếu lần crop chưa rõ kết quả', reconcile],
      ['retry', 'Gửi lại đúng thay đổi đang giữ', retry]]) {const button = controls[name] = make('button', name, label); button.type = 'button';
      button.addEventListener('click', () => fn().catch(error => onMessage(error.message, true))); root.append(button);}
    root.append(status);
  }
  function token() {try {const value = getSessionToken(); return typeof value === 'string' && value.trim() === value && value.length <= 2048 ? value : '';} catch {return '';}}
  const path = () => `/api/v1/projects/${getState().projectId}/timeline/manual-reframe`;
  const bucket = () => {const s = getState(); return s.workspaceId && s.projectId && s.principal?.subject
    ? 'vf-sql-manual-reframe-pending-v1:' + stable([s.workspaceId, s.projectId, s.principal.subject]) : null;};
  function status(text) {statusText = text; if (controls.status) controls.status.textContent = text;}
  function probe() {const key = bucket(); if (!key) {held = null; return;}
    try {demand(storage && typeof storage.getItem === 'function', 'Không đọc được nơi giữ yêu cầu.'); const raw = storage.getItem(key);
      if (raw !== null && raw !== undefined) {if (held?.bucket !== key || held?.raw !== raw) {held = {bucket: key, raw}; pending = null;}}
      else held = pending ? {bucket: key, raw: null} : null;
    } catch {held = {bucket: key, raw: null}; pending = null;}}
  function sync() {const next = scope(getState()), now = token(); if (next !== context || now !== literal) {
    context = next; literal = now; epoch++; view = null; pending = null; working = false;}
    probe(); if (held && !pending) status('Có bản ghi chưa rõ kết quả. Giữ nguyên; không tạo thay đổi mới.');
    let readable = false, writable = false; try {session(getState()); demand(literal && token() === literal, 'Phiên token không khớp.'); readable = true;
      session(getState(), true); writable = true;} catch {}
    if (controls.read) controls.read.disabled = disposed || working || !readable;
    if (controls.reconcile) controls.reconcile.disabled = disposed || working || !writable || !pending;
    if (controls.retry) controls.retry.disabled = disposed || working || !writable || !pending?.retryAllowed;
  }
  function setWorking(value) {working = value; sync(); onBusyChanged();}
  function live(ticket, identity, bound) {return !disposed && epoch === ticket && scope(getState()) === identity && !!literal && token() === literal
    && (bound === undefined || binding(getState()) === bound);}
  function current(ticket, identity, bound, write = false) {demand(live(ticket, identity, bound), 'Nguồn, phiên hoặc timeline đã đổi; giữ yêu cầu để đối chiếu.'); session(getState(), write);}
  const digest = value => audioByteHash(new TextEncoder().encode(typeof value === 'string' ? value : stable(value)), cryptoImpl);
  function validateHeld(p, s) {
    demand(exact(p, ['schema_version', 'workspace_id', 'project_id', 'actor_ref', 'scope', 'ui_source_sha256', 'parent_timeline_sha256',
      'parent_version_id', 'source_evidence', 'prior_source_receipt', 'body', 'session_sha256']) && p.schema_version === 'sql-manual-reframe-pending.v1'
      && p.scope === scope(s) && p.workspace_id === s.workspaceId && p.project_id === s.projectId && p.actor_ref === s.principal.subject
      && hash(p.session_sha256) && hash(p.ui_source_sha256) && hash(p.parent_timeline_sha256) && typeof p.parent_version_id === 'string' && p.parent_version_id
      && exact(p.body, ['expected_timeline_id', 'expected_version', 'request_key', 'acknowledged', 'expected_source_binding_sha256', 'aspect_ratio', 'points'])
      && p.body.expected_timeline_id === s.timeline.timeline_id && Number.isSafeInteger(p.body.expected_version) && p.body.expected_version >= 1
      && keyValid(p.body.request_key) && p.body.acknowledged === true && hash(p.body.expected_source_binding_sha256) && same(p.source_evidence, source(s).proof), 'Bản ghi đang giữ không đúng phiên hoặc cấu trúc.');
    manualReframeSettings({aspect_ratio: p.body.aspect_ratio, points: p.body.points}, source(s).proof.duration_seconds);
    receiptSource(p.prior_source_receipt, s, s.timeline);
    return p;
  }
  async function restore(ticket, identity, bound, captured) {
    if (!held) return null;
    demand(typeof held.raw === 'string', 'Bản ghi đang giữ chưa khả dụng.'); const p = validateHeld(JSON.parse(held.raw), getState());
    const sessionHash = await digest(captured); current(ticket, identity, bound);
    demand(sessionHash === p.session_sha256, 'Không sử dụng yêu cầu cũ dưới token khác.');
    const sourceHash = await digest(source(getState()).ui); current(ticket, identity, bound);
    demand(sourceHash === p.ui_source_sha256, 'Nguồn của yêu cầu đang giữ đã đổi.');
    if (getState().timeline.current_version === p.body.expected_version && getState().timeline.current_version_id === p.parent_version_id) {
      const parentHash = await digest(getState().timeline); current(ticket, identity, bound);
      demand(parentHash === p.parent_timeline_sha256, 'Bản cha đang mở không khớp yêu cầu đang giữ.');
      parents.set(p.body.request_key, copy(getState().timeline));
    }
    pending = freeze({...p, epoch: ticket, retryAllowed: false}); retained.set(p.body.request_key, held.raw); return pending;
  }
  async function reload() {
    sync(); session(getState()); demand(literal && !working, 'Phiên hoặc thao tác chưa sẵn sàng.');
    const ticket = epoch, identity = context, bound = binding(getState()), captured = literal; view = null; setWorking(true);
    try {const p = await restore(ticket, identity, bound, captured); current(ticket, identity, bound);
      const data = copy(await api(path())); current(ticket, identity, bound); manualReframeRead(data, getState());
      if (!p) demand(same(data.timeline, getState().timeline), 'Timeline dịch vụ đã đổi; tải đúng bản trước khi sửa.');
      else demand([p.body.expected_version, p.body.expected_version + 1].includes(data.timeline.current_version)
        && data.timeline.timeline_id === p.body.expected_timeline_id, 'Không còn phiên bản của yêu cầu đang giữ.');
      current(ticket, identity, bound);
      await onRead(copy(data)); current(ticket, identity, bound);
      view = freeze({data, binding: bound}); status(p ? 'Có lần chỉnh chưa rõ kết quả. Đối chiếu trước khi sửa tiếp.'
        : `Timeline v${data.timeline.current_version} đã đọc. Crop chỉ đổi khung hình; giữ âm thanh, phụ đề và cần duyệt lại.`);
      return copy(data);
    } catch (error) {if (live(ticket, identity)) status('Chưa xác minh được trạng thái; giữ nguyên bản ghi đang chờ.'); throw error;}
    finally {if (live(ticket, identity)) setWorking(false); else sync();}
  }
  function matches(data, p) {const r = data.receipt; return !!r && r.request_key === p.body.request_key && r.actor_ref === p.actor_ref
    && r.workspace_id === p.workspace_id && r.project_id === p.project_id && r.timeline_id === p.body.expected_timeline_id
    && r.parent_version_id === p.parent_version_id && r.parent_version === p.body.expected_version && r.result_version === p.body.expected_version + 1
    && same(r.settings, {aspect_ratio: p.body.aspect_ratio, points: p.body.points}) && data.source_binding_sha256 === p.body.expected_source_binding_sha256 && same(Object.fromEntries(Object.entries(r.source).filter(([k]) => k !== 'transcript_sha256')), p.source_evidence)
    && same(r.source, p.prior_source_receipt)
    && (!observed.has(p.body.request_key) || observed.get(p.body.request_key) === stable({timeline: data.timeline, receipt: data.receipt, source: data.source, source_binding_sha256: data.source_binding_sha256, settings: data.settings}));}
  async function accept(data, p, ticket, identity, bound) {
    current(ticket, identity, bound, true); manualReframeRead(data, getState()); demand(matches(data, p), 'Biên nhận chưa chứng minh đúng lần chỉnh; giữ UNKNOWN.');
    observed.set(p.body.request_key, stable({timeline: data.timeline, receipt: data.receipt, source: data.source, source_binding_sha256: data.source_binding_sha256, settings: data.settings}));

    const callbackBucket = held?.bucket, callbackRaw = retained.get(p.body.request_key), callbackHeld = held;
    let callbackActive = true;
    const requestGuard = () => {
      demand(callbackActive, 'Phạm vi đối chiếu yêu cầu đã kết thúc.');
      const raw = storage.getItem(callbackBucket);
      current(ticket, identity, bound, true);
      demand(bucket() === callbackBucket && pending === p && held === callbackHeld
        && typeof callbackRaw === 'string' && retained.get(p.body.request_key) === callbackRaw
        && held?.raw === callbackRaw && raw === callbackRaw, 'Bản ghi đang giữ đã đổi; chưa được nhận timeline.');
      return true;
    };
    try {requestGuard(); await onSaved({workspace_id: p.workspace_id, project_id: p.project_id, actor_ref: p.actor_ref, parent_version_id: p.parent_version_id,
      parent_version: p.body.expected_version, parent_timeline: copy(parents.get(p.body.request_key) ?? null),
      result_version: data.timeline.current_version, ui_source_sha256: p.ui_source_sha256,
      parent_timeline_sha256: p.parent_timeline_sha256, source_evidence: copy(p.source_evidence), receipt: copy(data.receipt), timeline: copy(data.timeline),
      source: copy(data.source), source_binding_sha256: data.source_binding_sha256,
      settings: copy(data.settings), applied_keyframes: copy(data.receipt.applied_keyframes)}, requestGuard);
    } finally {callbackActive = false;}
    current(ticket, identity, undefined, true); demand(same(getState().timeline, data.timeline), 'Studio chưa chứng minh đúng timeline vừa lưu; giữ UNKNOWN.');
    const installedBinding = binding(getState());
    const fingerprint = await digest(source(getState()).ui); current(ticket, identity, installedBinding, true);
    demand(fingerprint === p.ui_source_sha256 && same(getState().timeline, data.timeline), 'Nguồn đã đổi sau đối chiếu; giữ UNKNOWN.');
    const key = bucket(), exactRaw = retained.get(p.body.request_key), raw = storage.getItem(key);
    current(ticket, identity, installedBinding, true); demand(same(getState().timeline, data.timeline), 'Timeline đổi sau đọc bản ghi; giữ UNKNOWN.');
    demand(typeof exactRaw === 'string' && held?.bucket === key && held.raw === exactRaw && raw === exactRaw,
      'Bản ghi đang giữ đã đổi; không xóa bản ghi khác.');
    demand(typeof storage.compareAndRemoveItem === 'function' && storage.compareAndRemoveItem(key, exactRaw) === true,
      'Chưa xóa có đối chiếu được bản ghi này; giữ UNKNOWN.');
    retained.delete(p.body.request_key); parents.delete(p.body.request_key); pending = null; held = null; view = null;
    status('Đã lưu đường crop thủ công. Cập nhật preview và kiểm tra hình/âm thanh trước khi duyệt lại.');
  }

  async function runSettings(settings, {acknowledged = false} = {}) {
    sync(); session(getState(), true); demand(acknowledged === true && literal && !working && !held && !pending,
      'Xác nhận thao tác cảnh nguồn và hoàn tất yêu cầu đang giữ trước khi sửa.');
    const requested = freeze(copy(settingsForSource(settings, getState())));
    settingsForSource(requested, getState());
    const ticket = epoch, identity = context, bound = binding(getState()), captured = literal;
    const parent = copy(getState().timeline), sourceEvidence = copy(source(getState()).proof); setWorking(true);
    try {
      current(ticket, identity, bound, true);
      const data = copy(await api(path())); current(ticket, identity, bound, true); manualReframeRead(data, getState());
      demand(same(data.timeline, parent), 'Timeline dịch vụ đã đổi; không đổi CAS hoặc áp dụng lại thao tác.');
      const uiHash = await digest(source(getState()).ui); current(ticket, identity, bound, true);
      const parentHash = await digest(parent); current(ticket, identity, bound, true);
      const sessionHash = await digest(captured); current(ticket, identity, bound, true);
      const body = {expected_timeline_id: parent.timeline_id, expected_version: parent.current_version, request_key: newRequestKey(),
        acknowledged: true, expected_source_binding_sha256: data.source_binding_sha256, aspect_ratio: requested.aspect_ratio, points: requested.points}; demand(keyValid(body.request_key), 'Mã lần chỉnh không hợp lệ.');
      probe(); current(ticket, identity, bound, true); demand(!held && !pending, 'Có yêu cầu đang giữ; không ghi đè.');
      const p = freeze({schema_version: 'sql-manual-reframe-pending.v1', workspace_id: getState().workspaceId, project_id: getState().projectId,
        actor_ref: getState().principal.subject, scope: identity, ui_source_sha256: uiHash, parent_timeline_sha256: parentHash,
        parent_version_id: parent.current_version_id, source_evidence: sourceEvidence, prior_source_receipt: copy(data.source), body, session_sha256: sessionHash});
      parents.set(body.request_key, parent);
      const raw = JSON.stringify(p), key = bucket(); demand(storage && typeof storage.setItem === 'function', 'Không giữ được yêu cầu trước khi gửi.');
      storage.setItem(key, raw); pending = p; held = {bucket: key, raw}; retained.set(body.request_key, raw);
      const readback = storage.getItem(key); current(ticket, identity, bound, true);
      demand(readback === raw && held.raw === raw, 'Bản ghi đổi trước khi gửi; giữ UNKNOWN.');
      const result = copy(await api(path(), {method: 'PUT', body: JSON.stringify(body)})); current(ticket, identity, bound, true);
      await accept(result, p, ticket, identity, bound); return copy(result);
    } catch (error) {if (live(ticket, identity)) status('Chưa xác nhận được lần chỉnh. Giữ đúng yêu cầu để đối chiếu. ' + error.message); throw error;}
    finally {if (live(ticket, identity)) setWorking(false); else sync();}
  }
  async function reconcile() {
    sync(); session(getState(), true); demand(pending && literal && !working, 'Đọc yêu cầu đúng phiên trước khi đối chiếu.');
    const p = pending, ticket = epoch, identity = context, bound = binding(getState()); setWorking(true);
    try {current(ticket, identity, bound, true); const data = copy(await api(path())); current(ticket, identity, bound, true); manualReframeRead(data, getState());
      const uiHash = await digest(source(getState(), data.timeline).ui); current(ticket, identity, bound, true);
      demand(uiHash === p.ui_source_sha256, 'Nguồn hiện tại không khớp yêu cầu đang giữ.');
      demand(data.source_binding_sha256 === p.body.expected_source_binding_sha256 && same(data.source, p.prior_source_receipt), 'Nguồn dịch vụ đã đổi; giữ UNKNOWN.');
      if (matches(data, p)) {await accept(data, p, ticket, identity, bound); return copy(data);}
      demand(data.receipt?.request_key !== p.body.request_key && data.timeline.current_version === p.body.expected_version
        && data.timeline.current_version_id === p.parent_version_id && same(data.timeline, getState().timeline), 'Không chứng minh được bản cũ hoặc đúng biên nhận; giữ UNKNOWN.');
      const parentHash = await digest(data.timeline); current(ticket, identity, bound, true);
      demand(parentHash === p.parent_timeline_sha256, 'Nội dung bản cũ không còn khớp yêu cầu đang giữ.');
      view = freeze({data, binding: bound}); pending = freeze({...p, retryAllowed: true});
      status('Chưa thấy lần chỉnh. Có thể gửi lại chính yêu cầu cũ; mã, nội dung và phiên bản không đổi.'); return copy(data);
    } finally {if (live(ticket, identity)) setWorking(false); else sync();}
  }
  async function retry() {
    sync(); session(getState(), true); demand(pending?.retryAllowed && literal && !working && view?.binding === binding(getState()),
      'Đối chiếu đúng bản cũ trước khi gửi lại yêu cầu đang giữ.');
    const p = pending, ticket = epoch, identity = context, bound = binding(getState()); setWorking(true);
    try {demand(same(getState().timeline, view.data.timeline) && getState().timeline.current_version_id === p.parent_version_id
      && getState().timeline.current_version === p.body.expected_version, 'Timeline đã đổi; không gửi lại.');
      const raw = storage.getItem(bucket()); current(ticket, identity, bound, true);
      demand(typeof retained.get(p.body.request_key) === 'string' && raw === retained.get(p.body.request_key) && held?.raw === raw,
        'Bản ghi đang giữ đã đổi; không gửi lại.');
      const data = copy(await api(path(), {method: 'PUT', body: JSON.stringify(p.body)})); current(ticket, identity, bound, true);
      await accept(data, p, ticket, identity, bound); return copy(data);
    } finally {if (live(ticket, identity)) setWorking(false); else sync();}
  }
  async function runAcknowledged(settings, options) {
    try {await runSettings(settings, options); return true;}
    catch (error) {try {onMessage(error.message, true);} catch {} return false;}
  }
  sync(); return {sync, reload, runSettings: runAcknowledged, reconcile, retry, dispose() {disposed = true; epoch++; working = false; sync(); onBusyChanged();},
    isWorking: () => working, isPending: () => !!pending || !!held, isDirty: () => false, getStatus: () => statusText};
}
