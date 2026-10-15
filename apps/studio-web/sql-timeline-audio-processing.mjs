// Explicit canonical source-audio choices. No media/provider/approval dispatch.
import {audioRole, audioByteHash} from './uploaded-audio-review.mjs';
import {sessionToken as browserSessionToken} from './auth.mjs';
import {videoWordSessionStorage} from './video-transcript-word-review.mjs';

const copy = structuredClone;
const stable = value => JSON.stringify(value, (_key, item) => item && typeof item === 'object' && !Array.isArray(item)
  ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
const same = (a, b) => stable(a) === stable(b);
const demand = (ok, message) => {if (!ok) throw Error(message);};
const freeze = value => {if (value && typeof value === 'object') {Object.values(value).forEach(freeze); Object.freeze(value);} return value;};
const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const requestKey = value => typeof value === 'string' && /^[A-Za-z0-9_-]{8,128}$/.test(value);
const schema = {
  normalize_original_audio: {label: 'Cân bằng âm lượng lời và âm thanh nguồn', boolean: true, default: false},
  normalize_music: {label: 'Cân bằng âm lượng nhạc', boolean: true, default: false},
  duck_music: {label: 'Giảm nhạc khi âm thanh nguồn phát', boolean: true, default: false},
  original_target_lufs: {label: 'Mức âm thanh nguồn (LUFS)', min: -24, max: -12, default: -16},
  music_target_lufs: {label: 'Mức nhạc (LUFS)', min: -35, max: -16, default: -24},
  duck_threshold: {label: 'Ngưỡng giảm nhạc', min: .001, max: .2, default: .02},
  duck_ratio: {label: 'Tỷ lệ giảm nhạc', min: 2, max: 20, default: 8},
  duck_attack_ms: {label: 'Thời gian bắt đầu giảm nhạc (ms)', min: 1, max: 500, default: 20},
  duck_release_ms: {label: 'Thời gian trả âm lượng nhạc (ms)', min: 20, max: 2000, default: 250},
};
const defaults = Object.fromEntries(Object.entries(schema).map(([name, field]) => [name, field.default]));
export function audioProcessingConfiguration(value) {
  demand(value && typeof value === 'object' && !Array.isArray(value)
    && same(Object.keys(value).sort(), Object.keys(schema).sort()), 'Cấu hình âm thanh thiếu hoặc sai trường.');
  for (const [name, field] of Object.entries(schema)) demand(field.boolean ? typeof value[name] === 'boolean'
    : typeof value[name] === 'number' && Number.isFinite(value[name]) && value[name] >= field.min && value[name] <= field.max,
  `Giá trị ${field.label} không hợp lệ.`);
  return value;
}
function timeline(value, s) {
  demand(value && value.project_id === s.projectId && value.workspace_id === s.workspaceId
    && /^tml_[A-Za-z0-9_-]{4,60}$/.test(value.timeline_id)
    && typeof value.current_version_id === 'string' && value.current_version_id
    && Number.isInteger(value.current_version) && value.current_version >= 1
    && value.source_media_mutated === false && value.publish_requested === false
    && value.snapshot && Array.isArray(value.snapshot.tracks) && value.snapshot.metadata
    && typeof value.snapshot.metadata === 'object' && !Array.isArray(value.snapshot.metadata)
    && value.snapshot.source_media_mutated === false && value.snapshot.publish_requested === false,
  'Timeline không còn thuộc dự án hoặc thiếu bằng chứng hiện tại.');
  return value;
}
function configured(value) {
  const saved = value.snapshot.metadata.source_audio_processing;
  return saved === undefined || saved === null ? defaults : audioProcessingConfiguration(saved);
}
export function audioProcessingRead(value, s) {
  demand(value && same(Object.keys(value).sort(), ['timeline', 'configuration', 'locked_audio_track_ids', 'receipt', 'replayed'].sort()),
    'API âm thanh trả dữ liệu chưa đủ kiểm tra.');
  const t = timeline(value.timeline, s); audioProcessingConfiguration(value.configuration);
  demand(same(value.configuration, configured(t)) && typeof value.replayed === 'boolean', 'Cấu hình không khớp timeline đã lưu.');
  const locked = t.snapshot.tracks.filter(track => track.type === 'audio' && track.locked === true).map(track => track.track_id).sort();
  demand(Array.isArray(value.locked_audio_track_ids) && same(value.locked_audio_track_ids, locked), 'Thông tin khóa track chưa khớp timeline.');
  if (value.receipt !== null) {
    const r = value.receipt;
    demand(r && same(Object.keys(r).sort(), ['schema_version', 'request_key', 'request_sha256', 'workspace_id', 'project_id', 'timeline_id',
      'parent_version', 'result_version', 'actor_ref', 'configuration'].sort()) && r.schema_version === 'source-audio-processing-v1'
      && requestKey(r.request_key) && hash(r.request_sha256) && r.project_id === t.project_id && r.workspace_id === t.workspace_id
      && r.timeline_id === t.timeline_id && Number.isInteger(r.parent_version) && r.parent_version >= 1
      && r.result_version === r.parent_version + 1 && r.result_version === t.current_version
      && typeof r.actor_ref === 'string' && r.actor_ref && same(audioProcessingConfiguration(r.configuration), value.configuration),
    'Biên nhận cấu hình âm thanh không hợp lệ.');
  }
  return value;
}
function sourceValue(t) {
  const snapshot = copy(t.snapshot); delete snapshot.metadata.source_audio_processing;
  return {timeline_id: t.timeline_id, project_id: t.project_id, workspace_id: t.workspace_id,
    source_analysis_id: t.source_analysis_id, source_content_version_id: t.source_content_version_id,
    source_kind: t.source_kind, source_media_plan_id: t.source_media_plan_id, snapshot};
}
function scope(s) {
  const p = s.principal;
  // Persist the six public session fields, never an arbitrary caller's object.
  return stable([s.workspaceId, s.projectId, {subject: p?.subject, display_name: p?.display_name,
    platform_role: p?.platform_role, workspace_roles: p?.workspace_roles, expires_at: p?.expires_at,
    human_write_enabled: p?.human_write_enabled}, audioRole(s)]);
}
function binding(s) {return stable([scope(s), s.timeline]);}
function session(s, write = false) {
  demand(/^wsp_[A-Za-z0-9_-]{4,60}$/.test(s.workspaceId) && /^prj_[A-Za-z0-9_-]{4,60}$/.test(s.projectId)
    && typeof s.principal?.subject === 'string' && s.principal.subject.trim()
    && Number.isFinite(Date.parse(s.principal.expires_at)) && Date.parse(s.principal.expires_at) > Date.now()
    && ['viewer', 'editor', 'reviewer', 'owner'].includes(audioRole(s)), 'Cần phiên truy cập đúng dự án và còn hiệu lực.');
  if (write) demand(['editor', 'reviewer', 'owner'].includes(audioRole(s)) && s.principal.human_write_enabled === true,
    'Phiên này chưa được phép lưu cấu hình âm thanh.');
  demand(!s.busy && !s.dirty, 'Lưu thay đổi khác và chờ Studio tải xong trước.'); timeline(s.timeline, s);
}
function number(input, name) {
  demand(typeof input.value === 'string' && input.value === input.value.trim()
    && /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(input.value), `Điền số rõ ràng cho ${schema[name].label}.`);
  return Number(input.value);
}
export function initializeSqlTimelineAudioProcessing({root, api, getState, onMessage = () => {}, onSaved = async () => {},
  onBusyChanged = () => {}, getSessionToken = browserSessionToken, cryptoImpl = globalThis.crypto,
  dom = globalThis.document, storage = videoWordSessionStorage()}) {
  if (!root) return {sync() {}, reload: async () => {}, dispose() {}, isDirty: () => false, isWorking: () => false, isPending: () => false};
  const token = () => {try {const value = getSessionToken(); return typeof value === 'string' && value.trim() === value && value.length <= 2048 ? value : '';} catch {return '';}};
  let context = scope(getState()), literal = token(), epoch = 0, disposed = false, working = false, dirty = false, view = null, pending = null, held = null;
  const retained = new Map(), observedReceipts = new Map();
  const node = (tag, name, text) => {const e = dom.createElement(tag); e.setAttribute('data-audio-processing-' + name, ''); if (text) e.textContent = text; return e;};
  const button = (name, text, fn) => {const e = node('button', name, text); e.type = 'button'; e.addEventListener('click', () => fn().catch(error => onMessage(error.message, true))); return e;};
  const read = button('read', 'Đọc cấu hình âm thanh đã lưu', reload), save = button('save', 'Lưu cấu hình âm thanh', () => submit(false));
  const reconcile = button('reconcile', 'Đối chiếu lần lưu chưa rõ kết quả', reconcilePending);
  const retry = button('retry', 'Gửi lại đúng cấu hình đang giữ', () => submit(true));
  const discard = button('discard', 'Bỏ thay đổi chưa lưu', async () => {demand(!held && !working, 'Yêu cầu đang giữ cần đối chiếu.'); dirty = false; populate(); sync(); onBusyChanged();});
  const summary = node('p', 'summary', 'Chưa đọc cấu hình. Mặc định dịch vụ tắt cân bằng/giảm nhạc; chưa đo chất lượng âm thanh.');
  const status = node('p', 'status'); status.setAttribute('role', 'status');
  const controls = new Map(); root.append(node('h3', 'title', 'Âm thanh nguồn và nhạc'), read, summary);
  for (const [name, field] of Object.entries(schema)) {
    const input = node('input', name); input.type = field.boolean ? 'checkbox' : 'number';
    if (!field.boolean) {input.step = 'any'; input.min = String(field.min); input.max = String(field.max);}
    const label = node('label', 'label', field.label); label.append(input); root.append(label); controls.set(name, input);
    input.addEventListener(field.boolean ? 'change' : 'input', () => {if (!view || held || working) return; dirty = true; ack.checked = false; sync(); onBusyChanged();});
  }
  const ack = node('input', 'ack'); ack.type = 'checkbox'; ack.addEventListener('change', sync);
  const label = node('label', 'label', 'Tôi muốn lưu lựa chọn này; preview, audio review và phê duyệt cũ cần cập nhật'); label.append(ack);
  root.append(label, save, discard, reconcile, retry, node('p', 'note', 'Lưu lựa chọn không chạy xử lý media. Nghe review riêng để kiểm tra chất lượng.'), status);
  const path = () => `/api/v1/projects/${getState().projectId}/timeline/audio-processing`;
  const bucket = () => {const s = getState(); return s.workspaceId && s.projectId && s.principal?.subject
    ? 'vf-sql-audio-processing-pending-v1:' + stable([s.workspaceId, s.projectId, s.principal.subject]) : null;};
  function probe() {
    const key = bucket(); if (!key) {held = null; return;}
    try {
      demand(storage && typeof storage.getItem === 'function', 'Không đọc được nơi giữ yêu cầu.');
      const raw = storage.getItem(key);
      if (raw !== null && raw !== undefined) {
        if (!held || held.bucket !== key || held.raw !== raw) {held = {bucket: key, raw}; pending = null;}
      } else if (pending) held = {bucket: key, raw: null}; else held = null;
    } catch {held = {bucket: key, raw: null}; pending = null;}
  }
  function live(ticket, identity, bound) {return !disposed && epoch === ticket && scope(getState()) === identity
    && !!literal && token() === literal && (bound === undefined || binding(getState()) === bound);}
  function current(ticket, identity, bound, write = false) {demand(live(ticket, identity, bound), 'Nguồn, phiên hoặc timeline đã đổi. Giữ yêu cầu để đối chiếu.'); session(getState(), write);}
  function populate() {for (const [name, field] of Object.entries(schema)) {const input = controls.get(name);
    if (field.boolean) input.checked = view?.data.configuration[name] ?? false; else input.value = view ? String(view.data.configuration[name]) : '';}
    ack.checked = false;}
  function sync() {
    const next = scope(getState()), now = token();
    if (next !== context || now !== literal) {context = next; literal = now; epoch++; view = null; pending = null; dirty = false; working = false; populate();}
    probe(); if (held && !pending) status.textContent = 'Có bản ghi chưa rõ kết quả. Giữ nguyên bản ghi; sửa mới đang khóa.';
    let readable = false, editable = false; try {session(getState()); demand(literal && token() === literal, 'Phiên token không còn khớp.'); readable = true;
      session(getState(), true); editable = view?.binding === binding(getState()) && !view?.data.locked_audio_track_ids.length && !held;} catch {}
    read.disabled = disposed || working || dirty || !readable;
    for (const control of controls.values()) control.disabled = !editable || working;
    ack.disabled = !editable || !dirty || working; save.disabled = !editable || !dirty || !ack.checked || working;
    discard.disabled = !dirty || !!held || working; reconcile.disabled = !pending || !readable || working;
    retry.disabled = !pending?.retryAllowed || !readable || working;
  }
  function setWorking(value) {working = value; sync(); onBusyChanged();}
  async function sourceHash(t) {return audioByteHash(new TextEncoder().encode(stable(sourceValue(t))), cryptoImpl);}
  function validateHeld(p, s) {
    demand(p && same(Object.keys(p).sort(), ['schema_version', 'workspace_id', 'project_id', 'actor_ref', 'scope', 'ui_source_sha256',
      'parent_version_id', 'base_configuration', 'body', 'session_sha256'].sort())
      && p.schema_version === 'sql-source-audio-processing-pending.v1' && p.scope === scope(s)
      && p.workspace_id === s.workspaceId && p.project_id === s.projectId && p.actor_ref === s.principal.subject
      && hash(p.session_sha256) && hash(p.ui_source_sha256) && p.body && same(Object.keys(p.body).sort(),
        ['expected_timeline_id', 'expected_version', 'request_key', 'configuration', 'acknowledged'].sort())
      && p.body.expected_timeline_id === s.timeline.timeline_id && Number.isInteger(p.body.expected_version) && p.body.expected_version >= 1
      && requestKey(p.body.request_key) && p.body.acknowledged === true && typeof p.parent_version_id === 'string' && p.parent_version_id,
    'Bản ghi đang giữ không khớp phiên hoặc cấu trúc.');
    audioProcessingConfiguration(p.body.configuration); audioProcessingConfiguration(p.base_configuration);
    return p;
  }
  async function reload() {
    sync(); session(getState()); demand(literal && !working && !dirty, 'Chờ thao tác hoặc giữ bản sửa hiện tại.');
    const ticket = epoch, identity = context, bound = binding(getState()), captured = literal;
    view = null; populate(); setWorking(true);
    try {
      current(ticket, identity, bound);
      let p = null;
      if (held) {
        try {
          demand(typeof held.raw === 'string', 'Bản ghi chưa khả dụng.'); p = validateHeld(JSON.parse(held.raw), getState());
          const digest = await audioByteHash(new TextEncoder().encode(captured), cryptoImpl); current(ticket, identity, bound);
          demand(digest === p.session_sha256, 'Token của bản ghi không còn khớp.');
        } catch {view = null; pending = null; populate(); throw Error('Không xác minh được bản ghi đang giữ; không ghi đè hoặc gửi lại dưới phiên khác.');}
      }
      const data = copy(await api(path())); current(ticket, identity, bound); audioProcessingRead(data, getState());
      if (!p) demand(same(data.timeline, getState().timeline), 'Timeline dịch vụ đã đổi. Cần tải đúng phiên bản trước khi sửa.');
      const fingerprint = await sourceHash(data.timeline); current(ticket, identity, bound);
      if (p) {
        demand(fingerprint === p.ui_source_sha256 && data.timeline.timeline_id === p.body.expected_timeline_id
          && [p.body.expected_version, p.body.expected_version + 1].includes(data.timeline.current_version), 'Nguồn hoặc phiên bản không còn khớp yêu cầu đang giữ.');
        pending = freeze({...p, epoch: ticket, retryAllowed: false}); retained.set(p.body.request_key, held.raw);
      }
      view = freeze({data, binding: bound, ui_source_sha256: fingerprint}); dirty = false; populate();
      summary.textContent = `Timeline v${data.timeline.current_version} · đã đọc 9 lựa chọn · ngưỡng ${data.configuration.duck_threshold}${data.locked_audio_track_ids.length ? ' · có track âm thanh bị khóa' : ''}. Chưa đo chất lượng âm thanh.`;
      status.textContent = pending ? 'Có lần lưu chưa rõ kết quả. Đối chiếu trước khi sửa tiếp.' : 'Thay đổi rõ ràng, xác nhận rồi lưu. Không tự chạy xử lý hoặc duyệt video.';
    } catch (error) {
      if (live(ticket, identity)) status.textContent = 'Không đọc được cấu hình đã kiểm tra. Giữ nguyên bản ghi đang chờ; không tạo giá trị mặc định giả.';
      throw error;
    } finally {if (live(ticket, identity)) setWorking(false); else sync();}
  }
  function resultMatches(data, p) {const r = data.receipt;
    return !!r && r.request_key === p.body.request_key && r.actor_ref === p.actor_ref && r.workspace_id === p.workspace_id
      && r.project_id === p.project_id && r.timeline_id === p.body.expected_timeline_id && r.parent_version === p.body.expected_version
      && r.result_version === p.body.expected_version + 1 && data.timeline.current_version === r.result_version
      && same(r.configuration, p.body.configuration) && same(data.configuration, p.body.configuration)
      && (!observedReceipts.has(p.body.request_key) || observedReceipts.get(p.body.request_key) === r.request_sha256);
  }
  async function accepted(data, p, ticket, identity, bound) {
    current(ticket, identity, bound, true); audioProcessingRead(data, getState()); demand(resultMatches(data, p), 'Biên nhận chưa chứng minh đúng lần lưu; giữ yêu cầu.');
    demand(await sourceHash(data.timeline) === p.ui_source_sha256, 'Nguồn timeline trong biên nhận đã đổi.'); current(ticket, identity, bound, true);
    observedReceipts.set(p.body.request_key, data.receipt.request_sha256);
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
    try {requestGuard(); await onSaved({workspace_id: p.workspace_id, project_id: p.project_id, actor_ref: p.actor_ref, parent_version: p.body.expected_version,
      result_version: data.timeline.current_version, ui_source_sha256: p.ui_source_sha256, receipt: copy(data.receipt), timeline: copy(data.timeline)}, requestGuard);
    } finally {callbackActive = false;}
    current(ticket, identity, undefined, true);
    demand(same(getState().timeline, data.timeline), 'Studio chưa chứng minh đúng timeline vừa lưu; giữ yêu cầu.');
    const key = bucket(), exact = retained.get(p.body.request_key), readback = storage.getItem(key);
    current(ticket, identity, undefined, true); demand(same(getState().timeline, data.timeline), 'Timeline đã đổi sau đối chiếu bản ghi.');
    demand(held && held.bucket === key && typeof exact === 'string' && held.raw === exact && readback === exact,
      'Bản ghi đang giữ đã đổi; không xóa bản ghi khác.');
    demand(typeof storage.compareAndRemoveItem === 'function' && storage.compareAndRemoveItem(key, exact) === true,
      'Chưa xóa có đối chiếu được bản ghi này. Giữ UNKNOWN; không xóa riêng lẻ.');
    retained.delete(p.body.request_key); pending = null; held = null; view = null; dirty = false; populate();
    status.textContent = 'Đã lưu lựa chọn. Preview, audio review và phê duyệt cần cập nhật; chưa nghiệm thu chất lượng.';
  }
  async function submit(retryOld) {
    sync(); session(getState(), true); demand(literal && !working, 'Phiên hoặc thao tác chưa sẵn sàng.');
    if (retryOld) demand(pending?.retryAllowed, 'Đối chiếu lần lưu cũ trước khi gửi lại.');
    else demand(view && view.binding === binding(getState()) && dirty && ack.checked && !held && !view.data.locked_audio_track_ids.length,
      'Đọc đúng cấu hình, sửa và xác nhận trước khi lưu.');
    const ticket = epoch, identity = context, bound = binding(getState()), captured = literal;
    let p = pending;
    if (!retryOld) {
      const configuration = Object.fromEntries([...controls].map(([name, input]) => [name, schema[name].boolean ? input.checked : number(input, name)]));
      audioProcessingConfiguration(configuration);
      p = {schema_version: 'sql-source-audio-processing-pending.v1', workspace_id: getState().workspaceId, project_id: getState().projectId,
        actor_ref: getState().principal.subject, scope: identity, ui_source_sha256: view.ui_source_sha256, parent_version_id: view.data.timeline.current_version_id,
        base_configuration: copy(view.data.configuration), body: {expected_timeline_id: view.data.timeline.timeline_id,
          expected_version: view.data.timeline.current_version, request_key: 'sap_' + cryptoImpl.randomUUID(), configuration, acknowledged: true}};
      demand(requestKey(p.body.request_key), 'Mã yêu cầu không hợp lệ.');
    }
    setWorking(true);
    try {
      current(ticket, identity, bound, true);
      if (!retryOld) {
        const digest = await audioByteHash(new TextEncoder().encode(captured), cryptoImpl); current(ticket, identity, bound, true);
        probe(); demand(!held && !pending, 'Có bản ghi đang giữ; không ghi đè.');
        p = freeze({...p, session_sha256: digest}); const raw = JSON.stringify(p), key = bucket();
        demand(storage && typeof storage.setItem === 'function', 'Không lưu được yêu cầu trước khi gửi.'); storage.setItem(key, raw);
        pending = p; held = {bucket: key, raw}; retained.set(p.body.request_key, raw);
      } else demand(view && view.binding === bound && same(getState().timeline, view.data.timeline)
        && view.data.timeline.current_version === p.body.expected_version
        && view.data.timeline.current_version_id === p.parent_version_id && same(view.data.configuration, p.base_configuration)
        && view.ui_source_sha256 === p.ui_source_sha256, 'Không còn đúng bản cũ để gửi lại.');
      const readback = storage.getItem(bucket());
      current(ticket, identity, bound, true);
      demand(held?.raw === retained.get(p.body.request_key) && readback === held.raw, 'Bản ghi đã đổi trước khi gửi.');
      const data = copy(await api(path(), {method: 'PUT', body: JSON.stringify(p.body)}));
      current(ticket, identity, bound, true); await accepted(data, p, ticket, identity, bound);
    } catch (error) {if (live(ticket, identity)) status.textContent = 'Lần lưu chưa rõ kết quả. Giữ đúng yêu cầu và dùng Đối chiếu. ' + error.message; throw error;}
    finally {if (live(ticket, identity)) setWorking(false); else sync();}
  }
  async function reconcilePending() {
    sync(); session(getState(), true); demand(pending && literal && !working, 'Không có yêu cầu đúng phiên để đối chiếu.');
    const p = pending, ticket = epoch, identity = context, bound = binding(getState()); setWorking(true);
    try {
      const data = copy(await api(path())); current(ticket, identity, bound, true); audioProcessingRead(data, getState());
      const fingerprint = await sourceHash(data.timeline); current(ticket, identity, bound, true);
      demand(fingerprint === p.ui_source_sha256, 'Nguồn timeline đã đổi; không tự áp dụng hoặc đổi CAS.');
      if (resultMatches(data, p)) {await accepted(data, p, ticket, identity, bound); return;}
      demand(data.receipt?.request_key !== p.body.request_key && data.timeline.current_version === p.body.expected_version
        && data.timeline.current_version_id === p.parent_version_id && same(data.configuration, p.base_configuration)
        && same(getState().timeline, data.timeline), 'Không chứng minh được bản cũ hoặc đúng biên nhận; giữ UNKNOWN.');
      view = freeze({data, binding: bound, ui_source_sha256: fingerprint}); pending = freeze({...p, retryAllowed: true});
      status.textContent = 'Chưa thấy đúng lần lưu. Có thể gửi lại chính yêu cầu đang giữ; phiên bản và mã không đổi.';
    } finally {if (live(ticket, identity)) setWorking(false); else sync();}
  }
  sync(); return {sync, reload, dispose() {disposed = true; epoch++; working = false; sync(); onBusyChanged();},
    isDirty: () => dirty, isWorking: () => working, isPending: () => !!pending || !!held};
}
