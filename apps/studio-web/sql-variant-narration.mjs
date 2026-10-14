// Explicit S5 proposal/import/review intent. It grants no approval or rights.
import {audioRole} from './uploaded-audio-review.mjs';
import {sessionToken} from './auth.mjs';
import {reframeProfiles} from './reframe.mjs';

const sha = /^[a-f0-9]{64}$/;
const ids = {project: /^prj_[A-Za-z0-9_-]{4,60}$/, family: /^vfa_[a-f0-9]{32}$/,
  member: /^vfm_[a-f0-9]{32}$/, receipt: /^vfr_[a-f0-9]{32}$/, render: /^rnd_[A-Za-z0-9_-]{4,60}$/};
const clone = structuredClone;
const stable = value => JSON.stringify(value, (_key, v) => v && typeof v === 'object' && !Array.isArray(v)
  ? Object.fromEntries(Object.keys(v).sort().map(k => [k, v[k]])) : v);
const demand = (value, message = 'Nguồn, phiên truy cập hoặc phiên bản đã đổi. Đọc lại trước khi tiếp tục.') => {if (!value) throw Error(message);};
const freeze = v => {if (v && typeof v === 'object') {Object.values(v).forEach(freeze);Object.freeze(v);}return v;};
const integer = n => Number.isSafeInteger(n) && n > 0;
const templateFields = ['schema_version','enabled','expected_version','expected_snapshot_sha256','member_id','child_project_id',
  'expected_child_content_version_id','expected_child_timeline_version_id','expected_child_timeline_version',
  'source_review_render_id','source_approval_id','expected_source_manifest_sha256','expected_semantic_sha256',
  'expected_profile_sha256s','expected_normalization_sha256s','voice_config','acknowledge_fresh_child_review'];
const readProfile = p => ['review-540x960','review-960x540','review-540x540','review-432x540'].includes(p);

export function narrationOrigin(s) {
  const timeline = s.timeline;
  demand(s.projectId && s.workspaceId && timeline?.project_id === s.projectId && timeline.workspace_id === s.workspaceId
    && integer(timeline.current_version) && typeof timeline.current_version_id === 'string');
  const canonical = timeline.snapshot?.metadata?.sql_variant_derivative;
  const project = (s.projects ?? []).find(p => p.project_id === s.projectId && p.workspace_id === s.workspaceId);
  const p = canonical ?? project?.provenance;
  demand(p && (['sql-variant-storyboard-lineage.v1','sql-variant-evidence-lineage.v1'].includes(p.schema_version)
    || p.source_type === 'storyboard_variant_derivative'), 'Chọn bản con đã được tạo từ nhóm phiên bản trong Studio.');
  demand(ids.project.test(p.master_project_id) && p.master_project_id !== s.projectId
    && ids.family.test(p.family_id) && ids.member.test(p.member_id) && p.approval_inherited === false
    && (p.publishing_enabled === undefined || p.publishing_enabled === false));
  return {workspace_id:s.workspaceId, master_project_id:p.master_project_id, child_project_id:s.projectId,
    family_id:p.family_id, member_id:p.member_id};
}
const endpoint = s => {const o = narrationOrigin(s);return `/api/v1/projects/${o.master_project_id}/variant-families/${o.family_id}/children/${o.child_project_id}`;};
const scope = s => stable([s.workspaceId,s.projectId,s.principal?.subject,s.principal?.token_id,s.principal?.expires_at,audioRole(s)]);
const fingerprint = s => stable([scope(s),narrationOrigin(s),s.timeline.current_version_id,s.timeline.current_version,
  s.timeline.source_content_version_id,s.productionPackage?.package_id,s.productionPackage?.timeline_version_id,
  s.productionPackage?.subtitle?.subtitle_version_id,s.productionPackage?.audio_mix?.audio_version_id,
  s.productionPackage?.audio_mix?.config?.voice]);
function guard(s, write = false) {
  narrationOrigin(s);
  demand(['viewer','editor','reviewer','owner'].includes(audioRole(s)) && typeof s.principal?.subject === 'string'
    && Date.parse(s.principal.expires_at) > Date.now(), 'Cần phiên truy cập còn hiệu lực cho workspace này.');
  demand(!s.busy, 'Chờ Studio tải xong.');
  if (write) demand(['editor','reviewer','owner'].includes(audioRole(s)) && !s.dirty,
    'Cần quyền biên tập; lưu các thay đổi đang sửa trước khi tiếp tục.');
}

function safety(v) {
  demand(v.human_review_required === true && v.approval_transferred === false && v.rights_authority_transferred === false
    && v.publishing_enabled === false && v.owner_uat_accepted === false && v.new_inferences === 0 && v.provider_calls === 0);
}
export function validateNarrationAvailability(v) {
  demand(['CONFIGURED','NOT_CONFIGURED'].includes(v?.state) && integer(v.family_version) && sha.test(v.family_snapshot_sha256)
    && typeof v.source_current === 'boolean' && v.new_inferences === 0 && v.human_review_required === true
    && v.production_accepted === false, 'Trạng thái cấu hình narration chưa hợp lệ.');
  return v;
}
export function validateNarrationProposal(v, s) {
  const o = narrationOrigin(s), t = v?.request_template;
  demand(v?.schema_version === 'sql-variant-narration-proposal.v1' && Object.keys(o).every(k => v[k] === o[k])
    && v.actor_ref === s.principal?.subject && v.source_current === true && v.child_script_approved === true
    && integer(v.family_version) && sha.test(v.family_snapshot_sha256) && sha.test(v.proposal_sha256)
    && sha.test(v.source_record_sha256) && v.child_timeline_id === s.timeline.timeline_id
    && v.child_timeline_version_id === s.timeline.current_version_id && v.child_timeline_version === s.timeline.current_version
    && v.child_content_version_id === s.timeline.source_content_version_id && integer(v.unit_count) && v.unit_count <= 300
    && Number.isFinite(v.duration_seconds) && v.duration_seconds > 0 && v.duration_seconds <= 600);
  safety(v);
  demand(v.downloads === 0 && v.copies === 0 && v.queue_calls === 0 && v.cost_writes === 0 && v.automatic_execution === false);
  demand(t && stable(Object.keys(t).sort()) === stable([...templateFields].sort())
    && t.schema_version === 'sql-variant-narration-request.v1' && t.enabled === true && t.acknowledge_fresh_child_review === true
    && t.expected_version === v.family_version && t.expected_snapshot_sha256 === v.family_snapshot_sha256
    && t.member_id === o.member_id && t.child_project_id === o.child_project_id
    && t.expected_child_content_version_id === v.child_content_version_id
    && t.expected_child_timeline_version_id === v.child_timeline_version_id
    && t.expected_child_timeline_version === v.child_timeline_version && ids.render.test(t.source_review_render_id)
    && typeof t.source_approval_id === 'string' && /^apr_[A-Za-z0-9_-]{4,60}$/.test(t.source_approval_id)
    && sha.test(t.expected_source_manifest_sha256) && sha.test(t.expected_semantic_sha256)
    && [t.expected_profile_sha256s,t.expected_normalization_sha256s].every(p => Array.isArray(p)
      && p.length === v.unit_count && p.every(x => typeof x === 'string' && sha.test(x)))
    && t.voice_config?.enabled === true && t.voice_config.language === 'vi' && typeof t.voice_config.voice === 'string'
    && Number.isFinite(t.voice_config.speed), 'Đề xuất không còn khớp giọng, nguồn hoặc lịch dựng hiện tại.');
  return v;
}
export function narrationReusePayload(v, s, key, acknowledged) {
  guard(s, true);validateNarrationProposal(v, s);
  demand(acknowledged === true, 'Xác nhận đề xuất cần dùng cho bản này.');
  demand(typeof key === 'string' && /^[A-Za-z0-9][A-Za-z0-9._:-]{15,99}$/.test(key), 'Khóa yêu cầu chưa hợp lệ.');
  // Server hashes/pins stay literal; no Python canonical JSON recreation in JS.
  return {...clone(v.request_template),request_key:key};
}
export function validateNarrationReceipt(v, s, importBody = null) {
  const o = narrationOrigin(s);
  demand(v?.schema_version === 'sql-variant-narration-receipt.v1' && Object.keys(o).filter(k => k !== 'master_project_id')
    .every(k => v[k] === o[k]) && ['disabled','pending','ready','unknown','cancelled'].includes(v.state)
    && typeof v.actor_ref === 'string');safety(v);
  if (v.state !== 'disabled') demand(ids.receipt.test(v.receipt_id) && sha.test(v.input_sha256));
  if (importBody) demand(v.actor_ref === s.principal.subject && importBody.child_project_id === s.projectId
    && importBody.member_id === o.member_id);
  if (v.state === 'ready') {
    const r = v.result;
    demand(sha.test(v.result_sha256) && v.error_code === null && r?.schema_version === 'sql-variant-narration-result.v1'
      && r.input_sha256 === v.input_sha256 && r.human_review_required === true && r.approval_transferred === false
      && r.rights_authority_transferred === false && r.publishing_enabled === false && r.new_inferences === 0
      && r.provider_calls === 0 && r.operating_cost_vnd === null && r.copies && Object.keys(r.copies).length > 0);
    if (importBody) demand(r.source_review_render_id === importBody.source_review_render_id
      && r.source_approval_id === importBody.source_approval_id && r.source_manifest_sha256 === importBody.expected_source_manifest_sha256);
    for (const c of Object.values(r.copies)) demand(c && sha.test(c.sha256) && integer(c.size_bytes)
      && c.content_type === 'audio/wav' && c.storage_provider === 'local' && typeof c.asset_id === 'string'
      && c.object_key.startsWith(`workspaces/${s.workspaceId}/projects/${s.projectId}/variant-narration/${v.receipt_id}/`)
      && c.asset_proof?.project_id === s.projectId && c.asset_proof.workspace_id === s.workspaceId
      && c.asset_proof.asset_id === c.asset_id && c.asset_proof.asset_class === 'generated'
      && ['variant-narration-source','variant-tts-source'].includes(c.asset_proof.kind)
      && c.asset_proof.object_key === c.object_key && c.asset_proof.storage_provider === c.storage_provider
      && c.asset_proof.content_type === c.content_type && c.asset_proof.size_bytes === c.size_bytes
      && c.asset_proof.checksum_sha256 === c.sha256 && integer(c.asset_proof.asset_version)
      && sha.test(c.asset_proof.provenance_sha256)
      && (!importBody || c.asset_proof.project_version_id === importBody.expected_child_content_version_id));
  }
  return v;
}
export function narrationReviewPayload(receipt, s, acknowledged) {
  guard(s, true);validateNarrationReceipt(receipt, s);
  demand(receipt.state === 'ready' && acknowledged === true, 'Chọn narration đã nhập và xác nhận tạo review riêng cho bản này.');
  const p = s.productionPackage, o = narrationOrigin(s);
  demand(p?.project_id === s.projectId && p.workspace_id === s.workspaceId && p.current_for_timeline === true
    && p.timeline_version_id === s.timeline.current_version_id && p.timeline_version === s.timeline.current_version
    && integer(p.subtitle?.version) && integer(p.audio_mix?.version), 'Khởi tạo gói dựng đúng timeline trước khi tạo review.');
  const profile = reframeProfiles(s.timeline.snapshot).review;
  demand(readProfile(profile));
  return {expected_timeline_version:s.timeline.current_version,expected_subtitle_version:p.subtitle.version,
    expected_audio_version:p.audio_mix.version,profile,selection:{enabled:true,receipt_id:receipt.receipt_id,
      family_id:o.family_id,member_id:o.member_id,master_project_id:o.master_project_id,
      input_sha256:receipt.input_sha256,result_sha256:receipt.result_sha256}};
}

export function narrationReceiptIds(s) {
  const o=narrationOrigin(s);
  return [...new Set((s.assets??[]).filter(a=>a.project_id===s.projectId&&a.workspace_id===s.workspaceId
    &&a.asset_class==='generated'&&['variant-narration-source','variant-tts-source'].includes(a.kind)
    &&a.content_type==='audio/wav'&&sha.test(a.checksum_sha256)&&integer(a.size_bytes)
    &&a.provenance?.source_type==='variant_narration_copy'&&a.provenance.parent_project_id===o.master_project_id
    &&ids.receipt.test(a.provenance.narration_receipt_id)&&a.provenance.source_bytes_verified===true
    &&a.provenance.approval_transferred===false&&a.provenance.human_accepted===false
    &&a.object_key.startsWith(`workspaces/${s.workspaceId}/projects/${s.projectId}/variant-narration/${a.provenance.narration_receipt_id}/`))
    .map(a=>a.provenance.narration_receipt_id))].sort();
}

function validateReview(v, s, body) {
  const p = s.productionPackage;
  demand(v && ids.render.test(v.render_id) && v.project_id === s.projectId && v.workspace_id === s.workspaceId
    && v.render_kind === 'review' && v.approval_id === null && v.package_id === p?.package_id
    && v.timeline_version === body.expected_timeline_version && v.timeline_version_id === s.timeline.current_version_id
    && v.subtitle_version === body.expected_subtitle_version && v.audio_version === body.expected_audio_version
    && v.profile === body.profile && v.publishing_allowed === false && v.external_publish_requested === false
    && v.manifest?.requested_by === s.principal.subject && stable(v.manifest.variant_narration_request) === stable(body.selection)
    && ['queued','running','awaiting_review','failed','failed_qc','cancelled','stale'].includes(v.status));
  return v;
}

const browserToken = () => {try{return sessionToken();}catch{return '';}};
export function initializeSqlVariantNarration({root,api,getState,onMessage=()=>{},onImported=async()=>{},
  onReviewQueued=async()=>{},dom=globalThis.document,storage=globalThis.sessionStorage,
  newKey=()=>globalThis.crypto.randomUUID(),getSessionToken=browserToken,cryptoImpl=globalThis.crypto}) {
  if (!root) return {sync(){},isPending:()=>false,isWorking:()=>false,dispose(){}};
  let context=scope(getState()),tokenSnapshot=getSessionToken(),epoch=0,working=false,disposed=false;
  let available=null,proposal=null,receipt=null,pending=null,storedPending=false;
  const make=(tag,name,text)=>{const e=dom.createElement(tag);e.setAttribute('data-narration-'+name,'');if(text)e.textContent=text;return e;};
  const title=make('h3','title','Dùng lại lời đã duyệt'),status=make('p','status');status.setAttribute('role','status');
  const details=make('p','details','Mỗi bản con cần review và duyệt riêng. Dùng lại lời không chuyển quyền media hoặc quyền xuất bản.');
  const importAck=make('input','import-ack'),reviewAck=make('input','review-ack');importAck.type=reviewAck.type='checkbox';
  const importLabel=make('label','import-label','Tôi chọn lời, giọng và nguồn đã nêu cho bản này; vẫn cần review riêng.');importLabel.append(importAck);
  const reviewLabel=make('label','review-label','Tạo review riêng từ narration đã nhập và gói dựng hiện tại.');reviewLabel.append(reviewAck);
  const saved=make('select','saved'),savedLabel=make('label','saved-label','Narration đã lưu');savedLabel.append(saved);
  const buttons={};for (const [name,text] of [['prepare','Chuẩn bị đề xuất'],['read','Đọc trạng thái đã lưu'],
    ['reuse','Nhập narration đã chọn'],['review','Tạo review cho bản này'],['retry','Đối chiếu đúng yêu cầu cũ']]) {
    const e=make('button',name,text);e.type='button';buttons[name]=e;
  }
  root.append(title,details,buttons.prepare,savedLabel,buttons.read,status,importLabel,buttons.reuse,reviewLabel,buttons.review,buttons.retry);
  const key=bound=>'npd-sql-narration-pending:'+bound;
  const knownKey=bound=>'npd-sql-narration-receipt:'+bound;
  function sync() {
    const s=getState(),now=scope(s),token=getSessionToken();
    if (now!==context||token!==tokenSnapshot) {epoch++;context=now;tokenSnapshot=token;available=proposal=receipt=pending=null;importAck.checked=reviewAck.checked=false;}
    let readable=true,writable=true,current=true;
    try{guard(s);}catch{readable=false;}try{guard(s,true);}catch{writable=false;}
    try{if(proposal)validateNarrationProposal(proposal,s);}catch{current=false;}
    try{storedPending=Boolean(storage?.getItem(key(context)));}catch{storedPending=true;}
    let choices=[];try{choices=narrationReceiptIds(s);}catch{}
    if(receipt?.receipt_id&&!choices.includes(receipt.receipt_id))choices.push(receipt.receipt_id);
    const previous=saved.value;saved.replaceChildren(...choices.map((rid,i)=>{const option=make('option','saved-option',`Bản lời đã nhập ${i+1}`);option.value=rid;return option;}));
    saved.value=choices.includes(previous)?previous:choices[0]??'';
    const held=working||disposed,configured=available?.state==='CONFIGURED'&&available.source_current===true;
    const unresolved=!!pending||storedPending;
    buttons.prepare.disabled=held||!writable||unresolved;buttons.read.disabled=held||!readable;
    const alreadyImported=receipt?.state==='ready'&&proposal&&receipt.input_sha256===proposal.source_record_sha256;
    buttons.reuse.disabled=held||!writable||unresolved||!configured||!proposal||!current||alreadyImported||!importAck.checked;
    buttons.review.disabled=held||!writable||unresolved||!configured||!proposal||!current||!s.productionPackage
      ||receipt?.state!=='ready'||!reviewAck.checked;
    buttons.retry.disabled=held||!writable||!unresolved;importAck.disabled=reviewAck.disabled=held||!writable||unresolved;
    saved.disabled=held||unresolved;
    status.textContent=unresolved?'Chưa đối chiếu xong yêu cầu cũ. Khóa và nội dung yêu cầu vẫn được giữ; không tự gửi lại.':
      !current?'Timeline đã đổi. Lưu và chuẩn bị đề xuất mới.':
      available?.state==='NOT_CONFIGURED'?'Chức năng dùng lại lời chưa được cấu hình.':
      receipt?.state==='unknown'?'Chưa rõ kết quả nhập trước. Cần kiểm tra; không tạo bản sao hoặc giọng mới.':
      receipt?.state==='ready'?'Narration đã nhập. Tạo review và duyệt riêng cho bản này.':
      proposal?`${proposal.unit_count} phần lời · ${proposal.duration_seconds.toFixed(2)} giây · giọng ${proposal.request_template.voice_config.voice}. Chọn xác nhận trước khi nhập.`:
      'Chuẩn bị để kiểm tra narration đã được duyệt ở dự án gốc. Chưa có thao tác tự động.';
  }
  function live(ticket, bound, token, expected) {
    demand(!disposed&&epoch===ticket&&scope(getState())===bound&&getSessionToken()===token);
    if(expected)demand(fingerprint(getState())===expected);
  }
  async function sessionHash(ticket,bound,token) {
    demand(typeof token==='string'&&token.length>0,'Cần phiên truy cập còn hiệu lực.');
    const digest=await cryptoImpl.subtle.digest('SHA-256',new TextEncoder().encode(token));live(ticket,bound,token);
    return [...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');
  }
  function persist(v) {
    demand(storage,'Cần lưu được khóa yêu cầu trước khi gửi.');
    const value={...clone(v),body_json:stable(v.body)},raw=JSON.stringify(value);
    storage.setItem(key(v.scope),raw);demand(storage.getItem(key(v.scope))===raw,'Chưa lưu được khóa yêu cầu.');pending=freeze(value);
  }
  function restore(s,hash) {
    const raw=storage?.getItem(key(scope(s)));if(!raw)return;
    const v=JSON.parse(raw),o=narrationOrigin(s);
    demand(v.schema_version==='sql-narration-ui-pending.v1'&&v.scope===scope(s)&&v.session_sha256===hash
      &&['reuse','review'].includes(v.kind)&&v.body_json===stable(v.body)&&stable(v.origin)===stable(o)
      &&sha.test(v.proposal_sha256)&&sha.test(v.source_record_sha256)&&typeof v.local_intent_key==='string');
    if(v.kind==='reuse')demand(stable(Object.keys(v.body).sort())===stable([...templateFields,'request_key'].sort())
      &&/^[A-Za-z0-9][A-Za-z0-9._:-]{15,99}$/.test(v.body.request_key)&&v.body.child_project_id===s.projectId&&v.body.member_id===o.member_id);
    else demand(stable(Object.keys(v.body).sort())===stable(['expected_timeline_version','expected_subtitle_version','expected_audio_version','profile','selection'].sort())
      &&readProfile(v.body.profile)&&ids.receipt.test(v.body.selection?.receipt_id)&&v.body.selection.family_id===o.family_id
      &&v.body.selection.member_id===o.member_id&&v.body.selection.master_project_id===o.master_project_id
      &&v.body.selection.enabled===true&&sha.test(v.body.selection.input_sha256)&&sha.test(v.body.selection.result_sha256));
    pending=freeze(clone(v));
  }
  function forget(bound) {storage.removeItem(key(bound));pending=null;}
  async function requestProposal(s,ticket,bound,token,expected) {
    const [a,p]=await Promise.all([api(endpoint(s)+'/narration-reuse-availability'),api(endpoint(s)+'/narration-reuse-proposal')]);
    live(ticket,bound,token,expected);guard(getState(),true);
    validateNarrationAvailability(a);validateNarrationProposal(p,getState());
    demand(a.state==='CONFIGURED'&&a.source_current&&a.family_version===p.family_version&&a.family_snapshot_sha256===p.family_snapshot_sha256,
      'Nguồn đã đổi hoặc chức năng chưa được cấu hình.');
    available=freeze(clone(a));return freeze(clone(p));
  }
  async function run(action) {
    sync();if(working||disposed)return;working=true;sync();
    try{await action();}catch(e){onMessage(e.status===404||e.status===503?'Chức năng chưa sẵn sàng hoặc yêu cầu cũ cần được kiểm tra.':e.message,true);}
    finally{working=false;sync();}
  }
  async function prepare() {return run(async()=>{
    const s=getState();guard(s,true);const bound=scope(s),token=getSessionToken(),ticket=++epoch,expected=fingerprint(s);
    const hash=await sessionHash(ticket,bound,token);restore(s,hash);demand(!pending,'Đối chiếu yêu cầu cũ trước khi chuẩn bị mới.');
    proposal=await requestProposal(s,ticket,bound,token,expected);importAck.checked=reviewAck.checked=false;
  });}
  async function read() {return run(async()=>{
    const s=getState();guard(s);const bound=scope(s),token=getSessionToken(),ticket=++epoch,expected=fingerprint(s);
    const hash=await sessionHash(ticket,bound,token);restore(s,hash);
    const a=await api(endpoint(s)+'/narration-reuse-availability');live(ticket,bound,token,expected);validateNarrationAvailability(a);available=freeze(clone(a));
    let rid=pending?.receipt_id;
    if(!rid&&saved.value){demand(narrationReceiptIds(getState()).includes(saved.value)||receipt?.receipt_id===saved.value);rid=saved.value;}
    if(!rid)rid=receipt?.receipt_id;
    if(!rid) {const saved=storage?.getItem(knownKey(bound));if(saved){const v=JSON.parse(saved);demand(v.scope===bound&&ids.receipt.test(v.receipt_id));rid=v.receipt_id;}}
    if(!rid)return;
    const v=await api(endpoint(s)+'/narration-receipts/'+rid);live(ticket,bound,token,expected);
      validateNarrationReceipt(v,getState(),pending?.kind==='reuse'?pending.body:null);
      if(pending?.kind==='reuse')demand(v.input_sha256===pending.source_record_sha256);
      receipt=freeze(clone(v));
    if(pending?.kind==='reuse'&&v.state==='ready')forget(bound);
  });}
  async function submit(v,ticket,bound,token,expected) {
    const fresh=await requestProposal(getState(),ticket,bound,token,expected);
    demand(fresh.proposal_sha256===v.proposal_sha256&&fresh.source_record_sha256===v.source_record_sha256,
      'Đề xuất đã đổi. Giữ yêu cầu cũ để kiểm tra; không thay khóa hoặc ràng buộc nguồn.');
    if(v.kind==='reuse')demand(stable({...fresh.request_template,request_key:v.body.request_key})===v.body_json);
    else {validateNarrationReceipt(receipt,getState());demand(stable(narrationReviewPayload(receipt,getState(),true))===v.body_json);}
    const response=await api(endpoint(getState())+(v.kind==='reuse'?'/narration-reuse':'/narration-review-render'),
      {method:'POST',body:v.body_json});live(ticket,bound,token,expected);guard(getState(),true);
    if(v.kind==='reuse') {
      demand(typeof response?.replayed==='boolean');validateNarrationReceipt(response.receipt,getState(),v.body);
      demand(response.receipt.input_sha256===v.source_record_sha256);
      persist({...v,receipt_id:response.receipt.receipt_id});
      storage.setItem(knownKey(bound),JSON.stringify({scope:bound,receipt_id:response.receipt.receipt_id}));
      const actual=await api(endpoint(getState())+'/narration-receipts/'+response.receipt.receipt_id);
      live(ticket,bound,token,expected);guard(getState(),true);validateNarrationReceipt(actual,getState(),v.body);
      demand(stable(actual)===stable(response.receipt));receipt=freeze(clone(actual));
      if(actual.state==='ready'){forget(bound);await onImported(clone(actual));}
    } else {
      validateReview(response,getState(),v.body);
      if(response.manifest.variant_narration_handoff?.state==='unknown') {
        persist({...v,render_id:response.render_id});onMessage('Hàng đợi chưa rõ kết quả. Giữ nguyên yêu cầu để kiểm tra.',true);return;
      }
      forget(bound);await onReviewQueued(clone(response));
    }
  }
  async function reuse() {return run(async()=>{
    const s=getState();guard(s,true);const bound=scope(s),token=getSessionToken(),ticket=++epoch,expected=fingerprint(s);
    const hash=await sessionHash(ticket,bound,token);restore(s,hash);demand(!pending,'Đối chiếu yêu cầu cũ trước.');
    demand(!(receipt?.state==='ready'&&receipt.input_sha256===proposal?.source_record_sha256),
      'Narration này đã nhập. Dùng bản đã lưu và tạo review riêng.');
    const body=narrationReusePayload(proposal,getState(),newKey(),importAck.checked);
    const v={schema_version:'sql-narration-ui-pending.v1',scope:bound,session_sha256:hash,kind:'reuse',origin:narrationOrigin(s),
      proposal_sha256:proposal.proposal_sha256,source_record_sha256:proposal.source_record_sha256,local_intent_key:body.request_key,body};
    persist(v);await submit(pending,ticket,bound,token,expected);
  });}
  async function review() {return run(async()=>{
    const s=getState();guard(s,true);const bound=scope(s),token=getSessionToken(),ticket=++epoch,expected=fingerprint(s);
    const hash=await sessionHash(ticket,bound,token);restore(s,hash);demand(!pending,'Đối chiếu yêu cầu cũ trước.');
    validateNarrationProposal(proposal,getState());const body=narrationReviewPayload(receipt,getState(),reviewAck.checked);
    const v={schema_version:'sql-narration-ui-pending.v1',scope:bound,session_sha256:hash,kind:'review',origin:narrationOrigin(s),
      proposal_sha256:proposal.proposal_sha256,source_record_sha256:proposal.source_record_sha256,local_intent_key:newKey(),body};
    persist(v);await submit(pending,ticket,bound,token,expected);
  });}
  async function retry() {return run(async()=>{
    const s=getState();guard(s,true);const bound=scope(s),token=getSessionToken(),ticket=++epoch,expected=fingerprint(s);
    const hash=await sessionHash(ticket,bound,token);restore(s,hash);demand(pending,'Chưa có yêu cầu cũ trong phiên này.');
    if(pending.kind==='review'&&!receipt) {
      const r=await api(endpoint(s)+'/narration-receipts/'+pending.body.selection.receipt_id);
      live(ticket,bound,token,expected);validateNarrationReceipt(r,getState());receipt=freeze(clone(r));
    }
    await submit(pending,ticket,bound,token,expected);
  });}
  for(const [name,action] of Object.entries({prepare,read,reuse,review,retry}))buttons[name].addEventListener('click',action);
  saved.addEventListener('change',()=>{if(!working&&!pending){receipt=null;reviewAck.checked=false;sync();}});
  importAck.addEventListener('change',sync);reviewAck.addEventListener('change',sync);sync();
  return {prepare,read,reuse,review,retry,sync,isPending:()=>!!pending||storedPending,isWorking:()=>working,
    current:()=>clone({proposal,receipt,available}),dispose:()=>{disposed=true;epoch++;proposal=receipt=null;sync();}};
}
