// Explicit SQL draft families; canonical editing, approval and publishing stay in their existing flows.
import {audioRole} from './uploaded-audio-review.mjs';
const sha=/^[a-f0-9]{64}$/, ids={project:/^prj_[A-Za-z0-9_-]{4,60}$/,family:/^vfa_[a-f0-9]{32}$/,member:/^vfm_[a-f0-9]{32}$/,receipt:/^vfr_[a-f0-9]{32}$/};
const familyStates=new Set(['reserved','deriving','review_required','needs_attention','recovery_required','cancelled','failed']);
const memberStates=new Set(['reserved','deriving','needs_attention','review_required','cancelled','failed']);
const states={reserved:'Chưa tạo bản nháp',deriving:'Đang chuẩn bị',review_required:'Cần duyệt riêng',needs_attention:'Cần kiểm tra bản nháp',recovery_required:'Cần kiểm tra yêu cầu cũ',cancelled:'Đã hủy',failed:'Chưa hoàn tất'};
const copy=structuredClone,stable=v=>JSON.stringify(v,(_k,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
const demand=(ok,message)=>{if(!ok)throw Error(message);};
const scope=s=>stable([s.workspaceId,s.projectId,s.principal?.subject,s.principal?.token_id,s.principal?.expires_at,audioRole(s)]);
function guard(s,write=false){demand(s.workspaceId&&ids.project.test(s.projectId)&&!s.busy,'Chọn dự án và chờ tải xong.');
  if(write)demand(['editor','reviewer','owner'].includes(audioRole(s))&&typeof s.principal?.subject==='string'&&s.principal.subject.length>0&&!s.dirty,
    'Cần quyền biên tập và lưu thay đổi đang sửa trước khi tạo phiên bản.');}
function safety(v){return v?.provider_calls===0&&v.new_inference_calls===0&&v.approval_inherited===false&&v.rights_override_inherited===false
  &&v.automatic_render===false&&v.publishing_enabled===false&&typeof v.source_bytes_verified==='boolean'
  &&Number.isInteger(v.child_projects_created)&&v.child_projects_created>=0&&v.child_projects_created<=6;}
function binding(v,s){return v?.workspace_id===s.workspaceId&&v.master_project_id===s.projectId&&Number.isSafeInteger(v.project_version)&&v.project_version>0
  &&Number.isSafeInteger(v.timeline_version)&&v.timeline_version>0&&typeof v.timeline_version_id==='string'&&v.timeline_version_id.length>0
  &&['video_analysis','storyboard_media','mixed'].includes(v.source_mode)&&Array.isArray(v.records)&&v.records.length<=64;}
function profiles(v){return Array.isArray(v)&&v.length===6&&new Set(v.map(p=>p.profile_ref)).size===6
  &&v.every(p=>typeof p.profile_ref==='string'&&/^[a-z][a-z0-9-]{2,60}@[1-9][0-9]*$/.test(p.profile_ref)
    &&typeof p.label==='string'&&p.label.length>0&&p.label.length<=100&&['16:9','9:16','1:1','4:5'].includes(p.aspect_ratio));}
export function validateSqlVariantAvailability(v,s){const a=v?.availability,d=v?.derivation;
  demand(v?.schema_version==='sql-variant-api-availability.v1'&&a?.schema_version==='sql-variant-availability.v1'
    &&binding(a.binding,s)&&sha.test(a.binding_sha256)&&sha.test(a.catalog_sha256)&&profiles(a.catalog?.profiles)
    &&safety(a.safety)&&a.safety.child_projects_created===0&&a.safety.source_bytes_verified===false
    &&d?.schema_version==='sql-variant-api-dispatch.v1'&&['storyboard','uploaded_evidence','unsupported'].includes(d.engine)
    &&['CONFIGURED','NOT_CONFIGURED','UNSUPPORTED'].includes(d.state)&&d.provider_calls===0&&d.automatic_execution===false
    &&(d.state!=='CONFIGURED'||d.engine!=='unsupported'),'Danh sách phiên bản không khớp dự án hiện tại.');return v;}
export function validateSqlVariantFamily(v,s){demand(v?.schema_version==='sql-variant-family.v1'&&ids.family.test(v.family_id)
  &&v.workspace_id===s.workspaceId&&v.master_project_id===s.projectId&&Number.isSafeInteger(v.version)&&v.version>0
  &&familyStates.has(v.state)&&typeof v.source_current==='boolean'&&sha.test(v.snapshot_sha256)&&sha.test(v.result_sha256)
  &&binding(v.snapshot?.binding,s)&&sha.test(v.snapshot?.binding_sha256)&&profiles(v.snapshot?.catalog?.profiles)
  &&safety(v.safety)&&Array.isArray(v.members)&&v.members.length>0&&v.members.length<=6
  &&new Set(v.members.map(m=>m.member_id)).size===v.members.length&&new Set(v.members.map(m=>m.profile.profile_ref)).size===v.members.length
  &&v.members.every(m=>m.schema_version==='sql-variant-member.v1'&&ids.member.test(m.member_id)&&m.family_id===v.family_id
    &&m.workspace_id===s.workspaceId&&ids.project.test(m.planned_project_id)&&memberStates.has(m.state)&&safety(m.safety)
    &&v.snapshot.catalog.profiles.some(p=>stable(p)===stable(m.profile))
    &&(m.child_project_id===null||m.child_project_id===m.planned_project_id)
    &&(!m.child_project_id||['needs_attention','review_required'].includes(m.state))),'Nhóm phiên bản không khớp nguồn hoặc dự án hiện tại.');return v;}
export function sqlVariantReservePayload(s,v,selected,key,acknowledged){guard(s,true);validateSqlVariantAvailability(v,s);
  const a=v.availability,b=a.binding,t=s.timeline;
  demand(acknowledged===true&&Array.isArray(selected)&&selected.length>0&&selected.length<=6&&new Set(selected).size===selected.length
    &&selected.every(ref=>a.catalog.profiles.some(p=>p.profile_ref===ref))&&typeof key==='string'&&/^[A-Za-z0-9][A-Za-z0-9._:-]{15,99}$/.test(key),
    'Chọn định dạng và xác nhận từng bản nháp sẽ cần duyệt riêng.');
  demand(t&&t.project_id===s.projectId&&t.workspace_id===s.workspaceId&&t.current_version===b.timeline_version&&t.current_version_id===b.timeline_version_id,
    'Timeline đã đổi. Tải lại danh sách định dạng trước khi tạo nhóm.');
  return{schema_version:'sql-variant-family-reserve.v1',expected_project_version:b.project_version,expected_timeline_version:b.timeline_version,
    expected_timeline_version_id:b.timeline_version_id,expected_binding_sha256:a.binding_sha256,catalog_ref:a.catalog.catalog_ref,
    catalog_sha256:a.catalog_sha256,profile_refs:[...selected],request_key:key,acknowledge_draft_derivation:true};}
export function sqlVariantVersionPayload(s,f,key){guard(s,true);validateSqlVariantFamily(f,s);
  demand(typeof key==='string'&&/^[A-Za-z0-9][A-Za-z0-9._:-]{15,99}$/.test(key),'Chưa tạo được khóa yêu cầu.');
  return{expected_version:f.version,expected_snapshot_sha256:f.snapshot_sha256,request_key:key};}
export function sqlVariantDerivePayload(s,f,memberId,key,acknowledged){const payload=sqlVariantVersionPayload(s,f,key);
  const m=f.members.find(m=>m.member_id===memberId);demand(acknowledged===true&&f.source_current&&f.state!=='cancelled'&&m?.state==='reserved'
    &&m.child_project_id===null,'Nguồn hoặc phiên bản chưa sẵn sàng. Mỗi bản nháp cần kiểm tra và duyệt riêng.');
  const graph=f.snapshot.binding.records.some(r=>['auto_edit_analyses','uploaded_audio_transcriptions'].includes(r.table)&&r.count>0);
  demand(graph||f.snapshot.binding.source_mode==='storyboard_media','Cần phân tích nguồn video trước khi tạo bản nháp.');
  return{...payload,schema_version:graph?'sql-variant-uploaded-derive.v1':'sql-variant-storyboard-derive.v1',member_id:memberId,acknowledge_unapproved_child:true};}
export function validateSqlVariantReceipt(v,s,f,memberId){validateSqlVariantFamily(f,s);const m=f.members.find(m=>m.member_id===memberId);
  demand(['sql-variant-storyboard-receipt.v1','sql-variant-uploaded-receipt.v1'].includes(v?.schema_version)&&ids.receipt.test(v.receipt_id)
    &&v.workspace_id===s.workspaceId&&v.family_id===f.family_id&&v.member_id===m?.member_id&&['pending','ready','unknown','cancelled'].includes(v.state)
    &&sha.test(v.input_sha256)&&sha.test(v.request_sha256)&&safety(v.safety)
    &&(v.state!=='ready'||v.result?.child_project_id===m.planned_project_id&&sha.test(v.result_sha256)),'Phản hồi bản nháp không khớp yêu cầu hiện tại.');return v;}

export function initializeSqlVariantFamilies({root,api,getState,onMessage=()=>{},onChild=async()=>{},dom=globalThis.document,
  storage=globalThis.sessionStorage,newKey=()=>globalThis.crypto.randomUUID()}){
  let context=scope(getState()),epoch=0,working=false,disposed=false,available=null,rows=[],selected='',pending=null;
  const make=(tag,name,text)=>{const e=dom.createElement(tag);e.setAttribute('data-sql-variant-'+name,'');if(text)e.textContent=text;return e;};
  const title=make('h3','title','Phiên bản cho các nền tảng'),targets=make('div','targets'),saved=make('select','saved'),member=make('select','member');
  saved.setAttribute('aria-label','Nhóm phiên bản đã lưu');member.setAttribute('aria-label','Định dạng của bản nháp');
  const ack=make('input','ack');ack.type='checkbox';const ackLabel=make('label','ack-label','Mỗi bản nháp cần kiểm tra và duyệt riêng.');ackLabel.append(ack);
  const text=make('p','status','Tải các định dạng của dự án để chuẩn bị bản nháp.');text.setAttribute('role','status');
  const buttons={};for(const[name,label]of[['load','Xem định dạng và nhóm đã lưu'],['create','Tạo nhóm đã chọn'],['refresh','Cập nhật nhóm'],
    ['derive','Chuẩn bị bản nháp'],['retry','Gửi lại đúng yêu cầu cũ'],['cancel','Hủy nhóm'],['open','Mở bản nháp']]){
    buttons[name]=make('button',name,label);buttons[name].type='button';}
  root.append(title,buttons.load,targets,ackLabel,buttons.create,saved,member,text,buttons.refresh,buttons.derive,buttons.retry,buttons.cancel,buttons.open);
  const endpoint=s=>`/api/v1/projects/${encodeURIComponent(s.projectId)}/variant-families`,key=s=>'npd-sql-variant-pending:'+scope(s);
  const selectedFamily=()=>rows.find(f=>f.family_id===selected);
  function status(){const f=selectedFamily(),m=f?.members.find(m=>m.member_id===member.value);
    text.textContent=pending?'Chưa rõ phản hồi yêu cầu cũ. Giữ khóa yêu cầu và gửi lại đúng yêu cầu khi cần.':
      f?`${states[f.state]}${!f.source_current?' · Dự án gốc đã đổi':''}${m?` · ${m.profile.label}: ${states[m.state]}`:''}`:
      available?.derivation.state==='UNSUPPORTED'?'Nguồn video cần phân tích trước khi tạo bản nháp.':
      available?.derivation.state==='NOT_CONFIGURED'?'Chưa cấu hình chức năng tạo bản nháp cho nguồn này.':'Chọn định dạng; quyền sử dụng và duyệt xuất bản được kiểm tra riêng.';}
  function adopt(f,s){validateSqlVariantFamily(f,s);rows=[f,...rows.filter(x=>x.family_id!==f.family_id)];selected=f.family_id;}
  function sync(){const s=getState(),next=scope(s);if(next!==context){epoch++;context=next;available=null;rows=[];selected='';pending=null;ack.checked=false;targets.replaceChildren();}
    const previous=member.value;saved.replaceChildren(...rows.map(f=>{const e=make('option','family-option',`${f.members.length} định dạng · ${states[f.state]}`);e.value=f.family_id;return e;}));saved.value=selected;
    const f=selectedFamily();member.replaceChildren(...(f?.members??[]).map(m=>{const e=make('option','member-option',`${m.profile.label} · ${states[m.state]}`);e.value=m.member_id;return e;}));
    member.value=f?.members.some(m=>m.member_id===previous)?previous:f?.members[0]?.member_id??'';
    let readable=true,writable=true;try{guard(s);}catch{readable=false;}try{guard(s,true);}catch{writable=false;}
    const m=f?.members.find(m=>m.member_id===member.value),held=working||disposed;
    buttons.load.disabled=held||!readable;buttons.refresh.disabled=held||!readable||!f;
    buttons.create.disabled=held||!writable||!!pending||!available||available.derivation.state!=='CONFIGURED'||!ack.checked;
    buttons.derive.disabled=held||!writable||!!pending||!f?.source_current||f?.state==='cancelled'||m?.state!=='reserved'||!ack.checked;
    buttons.cancel.disabled=held||!writable||!!pending||!f||f.state==='cancelled';buttons.retry.disabled=held||!writable||!pending;
    buttons.open.disabled=held||!readable||s.dirty||!m?.child_project_id;saved.disabled=member.disabled=held||!!pending;ack.disabled=held||!!pending;
    for(const e of targets.children)e.children[0].disabled=held||!writable||!!pending;status();}
  function restore(s){const raw=storage?.getItem(key(s));if(!raw)return;const v=JSON.parse(raw);
    const fields=v.kind==='reserve'?['schema_version','expected_project_version','expected_timeline_version','expected_timeline_version_id',
      'expected_binding_sha256','catalog_ref','catalog_sha256','profile_refs','request_key','acknowledge_draft_derivation']:
      v.kind==='derive'?['expected_version','expected_snapshot_sha256','request_key','schema_version','member_id','acknowledge_unapproved_child']:
      ['expected_version','expected_snapshot_sha256','request_key'];
    const shaped=stable(Object.keys(v.body??{}).sort())===stable(fields.sort())&&v.body_json===stable(v.body);
    demand(v.schema_version==='sql-variant-ui-pending.v1'&&v.scope===scope(s)&&['reserve','derive','cancel'].includes(v.kind)
      &&shaped&&(v.kind==='reserve'?v.body.schema_version==='sql-variant-family-reserve.v1'&&v.body.acknowledge_draft_derivation===true
        &&Number.isSafeInteger(v.body.expected_project_version)&&v.body.expected_project_version>0&&Number.isSafeInteger(v.body.expected_timeline_version)
        &&v.body.expected_timeline_version>0&&sha.test(v.body.expected_binding_sha256)&&sha.test(v.body.catalog_sha256)
        &&typeof v.body.expected_timeline_version_id==='string'&&typeof v.body.catalog_ref==='string'
        &&Array.isArray(v.body.profile_refs)&&v.body.profile_refs.length>0&&v.body.profile_refs.length<=6
        &&new Set(v.body.profile_refs).size===v.body.profile_refs.length:
        Number.isSafeInteger(v.body.expected_version)&&v.body.expected_version>0&&sha.test(v.body.expected_snapshot_sha256)
          &&(v.kind!=='derive'||['sql-variant-storyboard-derive.v1','sql-variant-uploaded-derive.v1'].includes(v.body.schema_version)
            &&ids.member.test(v.body.member_id)&&v.body.acknowledge_unapproved_child===true))
      &&typeof v.body?.request_key==='string'&&/^[A-Za-z0-9][A-Za-z0-9._:-]{15,99}$/.test(v.body.request_key)
      &&(v.kind==='reserve'||ids.family.test(v.family_id)),'Chưa đối chiếu được yêu cầu cũ. Giữ dữ liệu phiên để kiểm tra.');pending=v;
    if(v.family_id&&rows.some(f=>f.family_id===v.family_id))selected=v.family_id;}
  function persist(v){demand(storage,'Trình duyệt cần lưu khóa yêu cầu trước khi gửi.');v.body_json=stable(v.body);const raw=JSON.stringify(v);
    storage.setItem(key(getState()),raw);demand(storage.getItem(key(getState()))===raw,'Chưa lưu được khóa yêu cầu.');pending=v;}
  function forget(s){storage?.removeItem(key(s));pending=null;}
  async function run(action){sync();demand(!working&&!disposed,'Chờ thao tác hiện tại hoàn tất.');working=true;sync();
    try{return await action();}catch(error){onMessage(error.message,true);throw error;}finally{working=false;sync();}}
  async function load(){return run(async()=>{const s=getState(),bound=scope(s),ticket=++epoch;guard(s);
    const [v,page]=await Promise.all([api(endpoint(s)+'/availability'),api(endpoint(s)+'?limit=25')]);
    if(disposed||ticket!==epoch||scope(getState())!==bound)return;validateSqlVariantAvailability(v,s);
    demand(page?.schema_version==='sql-variant-family-page.v1'&&Array.isArray(page.items)&&page.items.length<=25
      &&new Set(page.items.map(f=>f.family_id)).size===page.items.length,'Danh sách nhóm chưa hợp lệ.');page.items.forEach(f=>validateSqlVariantFamily(f,s));
    available=copy(v);rows=copy(page.items);selected=rows.some(f=>f.family_id===selected)?selected:rows[0]?.family_id??'';
    targets.replaceChildren(...available.availability.catalog.profiles.map(p=>{const label=make('label','target',p.label),input=make('input','profile');input.type='checkbox';input.value=p.profile_ref;input.checked=true;label.append(input);return label;}));restore(s);});}
  async function refresh(){return run(async()=>{const s=getState(),bound=scope(s),ticket=++epoch,f=selectedFamily();guard(s);demand(f,'Chọn nhóm đã lưu.');
    const value=await api(`${endpoint(s)}/${f.family_id}`);if(disposed||ticket!==epoch||scope(getState())!==bound)return;
    demand(value.family_id===f.family_id,'Nhóm trả về không đúng yêu cầu.');adopt(value,s);});}
  async function submit(v,s){const bound=scope(s),ticket=++epoch;guard(s,true);
    const path=endpoint(s)+(v.kind==='reserve'?'':`/${v.family_id}/${v.kind==='derive'?'derive':'cancel'}`);
    let family;
    if(v.kind==='derive'){
      family=rows.find(f=>f.family_id===v.family_id);
      if(!family)family=await api(`${endpoint(s)}/${v.family_id}`);
      if(disposed||ticket!==epoch||scope(getState())!==bound)return;
      validateSqlVariantFamily(family,s);demand(family.family_id===v.family_id&&family.members.some(m=>m.member_id===v.body.member_id),'Chưa đối chiếu được bản nháp của yêu cầu cũ.');
    }
    const response=await api(path,{method:'POST',body:JSON.stringify(v.body)});if(disposed||ticket!==epoch||scope(getState())!==bound)return;
    if(v.kind==='derive'){demand(response?.schema_version==='sql-variant-api-derive-result.v1'&&typeof response.replayed==='boolean','Phản hồi bản nháp chưa hợp lệ.');
      validateSqlVariantReceipt(response.receipt,s,family,v.body.member_id);
      const current=await api(`${endpoint(s)}/${v.family_id}`);if(disposed||ticket!==epoch||scope(getState())!==bound)return;
      demand(current.family_id===v.family_id,'Nhóm trả về không đúng yêu cầu.');adopt(current,s);
    }else{demand(response?.schema_version==='sql-variant-api-family-result.v1'&&typeof response.replayed==='boolean'
      &&(v.kind==='reserve'||response.family?.family_id===v.family_id),'Phản hồi nhóm chưa hợp lệ.');adopt(response.family,s);}
    forget(s);}
  async function create(){return run(async()=>{const s=getState();demand(!pending,'Đối chiếu yêu cầu cũ trước.');
    const selected=[...targets.children].filter(e=>e.children[0].checked).map(e=>e.children[0].value);
    const body=sqlVariantReservePayload(s,available,selected,newKey(),ack.checked);const v={schema_version:'sql-variant-ui-pending.v1',scope:scope(s),kind:'reserve',body};persist(v);await submit(v,s);});}
  async function derive(){return run(async()=>{const s=getState(),f=selectedFamily();demand(!pending,'Đối chiếu yêu cầu cũ trước.');
    const body=sqlVariantDerivePayload(s,f,member.value,newKey(),ack.checked);const v={schema_version:'sql-variant-ui-pending.v1',scope:scope(s),kind:'derive',family_id:f.family_id,body};persist(v);await submit(v,s);});}
  async function cancel(){return run(async()=>{const s=getState(),f=selectedFamily();demand(!pending&&f?.state!=='cancelled','Đối chiếu yêu cầu cũ trước.');
    const body=sqlVariantVersionPayload(s,f,newKey());const v={schema_version:'sql-variant-ui-pending.v1',scope:scope(s),kind:'cancel',family_id:f.family_id,body};persist(v);await submit(v,s);});}
  async function retry(){return run(async()=>{const s=getState();guard(s,true);if(!pending)restore(s);demand(pending?.scope===scope(s),'Không có yêu cầu cũ trong phiên hiện tại.');await submit(copy(pending),s);});}
  async function open(){return run(async()=>{const s=getState(),f=selectedFamily();guard(s);demand(!s.dirty,'Lưu thay đổi đang sửa trước khi mở bản nháp.');validateSqlVariantFamily(f,s);
    const m=f.members.find(m=>m.member_id===member.value);demand(m?.child_project_id===m?.planned_project_id&&ids.project.test(m.child_project_id),'Chưa có bản nháp để mở.');
    await onChild({workspace_id:s.workspaceId,master_project_id:s.projectId,child_project_id:m.child_project_id,family_id:f.family_id,member_id:m.member_id});});}
  const actions={load,create,refresh,derive,retry,cancel,open};for(const[name,action]of Object.entries(actions))buttons[name].addEventListener('click',()=>action().catch(()=>{}));
  for(const e of[saved,member,ack])e.addEventListener('change',()=>{if(e===saved)selected=saved.value;sync();});sync();
  return{...actions,sync,isPending:()=>!!pending,isBusy:()=>working,dispose:()=>{disposed=true;epoch++;sync();},current:()=>copy(selectedFamily()??null)};
}
