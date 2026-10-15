// Reviewed placement of already resolved media. No provider/resolve dispatch.
import {audioRole, audioByteHash} from './uploaded-audio-review.mjs';
import {videoAnalysisAssets} from './video-analysis-jobs.mjs';
import {sessionToken as browserSessionToken} from './auth.mjs';
import {videoWordSessionStorage} from './video-transcript-word-review.mjs';

const copy=structuredClone;
const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const stable=v=>JSON.stringify(v,(_k,x)=>object(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
const same=(a,b)=>stable(a)===stable(b);
const demand=(v,m)=>{if(!v)throw Error(m);};
const exact=(v,keys)=>object(v)&&same(Object.keys(v).sort(),[...keys].sort());
const hash=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const identifier=(v,p)=>typeof v==='string'&&new RegExp('^'+p+'_[A-Za-z0-9_-]{4,60}$').test(v);
const requestKey=v=>typeof v==='string'&&/^[A-Za-z0-9_-]{8,128}$/.test(v);
const itemId=v=>typeof v==='string'&&v.length>0&&v.length<=64&&![...v].some(c=>c.charCodeAt(0)<32);
const positive=v=>typeof v==='number'&&Number.isFinite(v)&&v>0;
const freeze=v=>{if(object(v)||Array.isArray(v)){Object.values(v).forEach(freeze);Object.freeze(v);}return v;};
const readKeys=['schema_version','workspace_id','project_id','actor_ref','timeline_id','timeline_version_id','timeline_version',
 'timeline_sha256','media_plan_id','media_binding_sha256','context_sha256','source','timeline','items','ready_item_ids','receipt','replayed',
 'provider_calls','publishing_enabled','owner_approval_inferred'];
const receiptKeys=['schema_version','workspace_id','project_id','timeline_id','media_plan_id','parent_version_id','parent_version',
 'result_version','actor_ref','request_key','request_sha256','context_sha256','media_binding_sha256','item_ids','replace_plan_clips',
 'result_snapshot_sha256','provider_calls','publishing_enabled','owner_approval_inferred'];
const sourceKeys=['analysis_id','analysis_fingerprint','asset_id','source_sha256','duration_seconds','has_audio','transcript_id',
 'transcript_version','transcript_sha256'];
const bodyKeys=['expected_timeline_id','expected_version','expected_context_sha256','request_key','item_ids','replace_plan_clips','acknowledged'];

export function brollTimelineSelection(v){
 demand(exact(v,['item_ids','replace_plan_clips'])&&Array.isArray(v.item_ids)&&v.item_ids.length>=1&&v.item_ids.length<=200
  &&v.item_ids.every(itemId)&&new Set(v.item_ids).size===v.item_ids.length&&typeof v.replace_plan_clips==='boolean',
 'Chọn từ 1 đến 200 cảnh B-roll khác nhau và lựa chọn thay thế rõ ràng.');return v;
}
function canonical(t,s){
 demand(object(t)&&t.workspace_id===s.workspaceId&&t.project_id===s.projectId&&identifier(t.timeline_id,'tml')
  &&typeof t.current_version_id==='string'&&t.current_version_id&&Number.isSafeInteger(t.current_version)&&t.current_version>=1
  &&t.source_kind==='video_analysis'&&t.source_media_mutated===false&&t.publish_requested===false
  &&object(t.snapshot)&&object(t.snapshot.metadata)&&Array.isArray(t.snapshot.tracks)&&positive(t.snapshot.duration_seconds)
  &&t.snapshot.source_media_mutated===false&&t.snapshot.publish_requested===false,'Timeline nguồn chưa đúng dự án hoặc bằng chứng.');
 return t;
}
function localSource(s,t=s.timeline){
 canonical(t,s);const a=s.analysis,m=t.snapshot.metadata;
 const asset=videoAnalysisAssets(s).find(v=>v.asset_id===m.source_asset_id),measured=asset?.provenance?.media_metadata;
 demand(asset&&a?.analysis_id===t.source_analysis_id&&a.analysis_id===m.source_analysis_id&&a.asset_id===asset.asset_id
  &&a.workspace_id===s.workspaceId&&a.project_id===s.projectId&&a.status==='succeeded'&&hash(a.fingerprint)
  &&a.configuration?.asset_id===asset.asset_id&&a.source_media_mutated===false&&a.publish_requested===false
  &&a.source_media?.media_kind==='video'&&positive(a.source_media.duration_seconds)&&a.source_media.duration_seconds===m.source_duration_seconds
  &&measured.duration_seconds===m.source_duration_seconds&&Object.hasOwn(a.source_media,'audio_codec')
  &&!['','unknown',undefined].includes(a.source_media.audio_codec)
  &&['width','height'].every(k=>Number.isSafeInteger(a.source_media[k])&&a.source_media[k]>0&&a.source_media[k]===measured[k])
  &&positive(a.source_media.fps)&&a.source_media.fps===measured.fps,'Cần phân tích và video nguồn đúng với timeline.');
 const rev=m.transcript_revision,hasAudio=a.source_media.audio_codec!==null;
 demand(rev===undefined||rev===null||object(rev)&&/^trn_[a-f0-9]{24}$/.test(rev.transcript_id)
  &&Number.isSafeInteger(rev.version)&&rev.version>=1,'Phiên bản transcript nguồn chưa rõ.');
 demand(!hasAudio||rev!=null,'Nguồn có âm thanh cần transcript đã chọn.');
 return{analysis_id:a.analysis_id,analysis_fingerprint:a.fingerprint,asset_id:asset.asset_id,source_sha256:asset.checksum_sha256,
  duration_seconds:m.source_duration_seconds,has_audio:hasAudio,transcript_id:rev?.transcript_id??null,transcript_version:rev?.version??null,
  };
}
function sourceMatches(v,s,t){
 demand(exact(v,sourceKeys),'Bằng chứng B-roll thiếu trường nguồn.');
 for(const[k,x]of Object.entries(localSource(s,t)))demand(same(v[k],x),'B-roll không khớp video hoặc transcript đang chọn.');
 demand(v.transcript_id===null?v.transcript_sha256===null:hash(v.transcript_sha256),'Hash transcript nguồn chưa hợp lệ.');
}
function sourceUi(s){localSource(s);return{analysis:s.analysis,assets:s.assets,media_plan_id:s.mediaPlanId,
  media_plans:s.mediaPlans??null,source_metadata:{source_analysis_id:s.timeline.source_analysis_id,...localSource(s)}};}
function scope(s){const p=s.principal;return stable([s.workspaceId,s.workspaceSlug??null,s.projectId,
 {subject:p?.subject,display_name:p?.display_name,platform_role:p?.platform_role,workspace_roles:p?.workspace_roles,
  expires_at:p?.expires_at,human_write_enabled:p?.human_write_enabled},audioRole(s)]);}
function session(s,write=false){
 demand(identifier(s.workspaceId,'wsp')&&identifier(s.projectId,'prj')&&typeof s.mediaPlanId==='string'
  &&/^[A-Za-z0-9_-]{4,80}$/.test(s.mediaPlanId)&&typeof s.principal?.subject==='string'&&s.principal.subject.trim()
  &&Number.isFinite(Date.parse(s.principal.expires_at))&&Date.parse(s.principal.expires_at)>Date.now()
  &&['viewer','editor','reviewer','owner'].includes(audioRole(s)),'Cần phiên hợp lệ và đề xuất B-roll đã chọn.');
 if(write)demand(['editor','reviewer','owner'].includes(audioRole(s))&&s.principal.human_write_enabled===true,'Phiên này chưa được phép áp dụng B-roll.');
 demand(!s.busy&&!s.dirty,'Lưu bản sửa khác và chờ Studio tải xong trước.');localSource(s);
}
function readBinding(s){return stable([scope(s),s.timeline,sourceUi(s)]);}
function binding(s){return stable([readBinding(s),s.brollDraft??null]);}
function contextValue(v){return Object.fromEntries(['workspace_id','project_id','actor_ref','timeline_id','timeline_version_id',
 'timeline_version','timeline_sha256','media_plan_id','media_binding_sha256'].map(k=>[k,v[k]]));}

export function brollTimelineRead(v,s){
 demand(exact(v,readKeys)&&v.schema_version==='broll-timeline-review-read.v1'&&v.workspace_id===s.workspaceId&&v.project_id===s.projectId
  &&v.actor_ref===s.principal?.subject&&v.media_plan_id===s.mediaPlanId&&hash(v.context_sha256)&&hash(v.media_binding_sha256)
  &&hash(v.timeline_sha256)&&typeof v.replayed==='boolean'&&v.provider_calls===0&&v.publishing_enabled===false
  &&v.owner_approval_inferred===false,'API B-roll chưa giữ đúng phiên, dự án và đề xuất.');
 const t=canonical(v.timeline,s);sourceMatches(v.source,s,t);
 demand(v.timeline_id===t.timeline_id&&v.timeline_version_id===t.current_version_id&&v.timeline_version===t.current_version
  &&Array.isArray(v.items)&&v.items.length>0&&v.items.length<=200&&Array.isArray(v.ready_item_ids)
  &&v.ready_item_ids.every(itemId)&&new Set(v.ready_item_ids).size===v.ready_item_ids.length,'Bản đọc B-roll thiếu phiên bản hoặc danh sách cảnh.');
 const ids=new Set();for(const item of v.items){demand(object(item)&&itemId(item.media_plan_item_id)&&!ids.has(item.media_plan_item_id)
   &&item.media_plan_id===v.media_plan_id&&['planned','resolving','resolved','needs_approval','failed'].includes(item.status),
  'Cảnh B-roll thiếu định danh hoặc không thuộc đề xuất.');ids.add(item.media_plan_item_id);}
 demand(v.ready_item_ids.every(id=>v.items.some(item=>item.media_plan_item_id===id&&item.status==='resolved'
  &&typeof item.selected_media_asset_id==='string'&&item.selected_media_asset_id)),'Cảnh B-roll chưa có tư liệu đã phân giải.');
 if(v.receipt!==null){const r=v.receipt;
  demand(exact(r,receiptKeys)&&r.schema_version==='broll-timeline-review.v1'&&r.workspace_id===v.workspace_id&&r.project_id===v.project_id
   &&r.timeline_id===t.timeline_id&&r.media_plan_id===v.media_plan_id&&typeof r.parent_version_id==='string'&&r.parent_version_id
   &&Number.isSafeInteger(r.parent_version)&&r.parent_version>=1&&r.result_version===r.parent_version+1&&r.result_version===t.current_version
   &&typeof r.actor_ref==='string'&&r.actor_ref&&requestKey(r.request_key)&&hash(r.request_sha256)&&hash(r.context_sha256)
   &&r.media_binding_sha256===v.media_binding_sha256&&r.result_snapshot_sha256===v.timeline_sha256
   &&r.provider_calls===0&&r.publishing_enabled===false&&r.owner_approval_inferred===false,'Biên nhận B-roll không đúng phiên bản hoặc nguồn.');
  brollTimelineSelection({item_ids:r.item_ids,replace_plan_clips:r.replace_plan_clips});
  demand(r.item_ids.every(id=>v.ready_item_ids.includes(id)),'Biên nhận chọn cảnh chưa sẵn sàng.');
 }else demand(!v.replayed,'Replay B-roll thiếu biên nhận.');
 return v;
}

export function initializeSqlBrollTimelineReview({root,api,getState,getSessionToken=browserSessionToken,onRead=async()=>{},onSaved=async()=>{},
 onBusyChanged=()=>{},onMessage=()=>{},dom=globalThis.document,storage=videoWordSessionStorage(),cryptoImpl=globalThis.crypto,
 newRequestKey=()=>'brt_'+cryptoImpl.randomUUID()}){
 let disposed=false,working=false,epoch=0,identity=scope(getState()),literal=token(),view=null,pending=null,held=null;
 const parents=new Map(),observed=new Map();let statusText='Chưa đọc B-roll đã lưu. Chỉ áp dụng sau lựa chọn và xác nhận rõ ràng.';
 const controls={};
 if(root){for(const[name,label,fn]of[['read','Đọc B-roll đã lưu',reload],['reconcile','Đối chiếu lần áp dụng chưa rõ kết quả',reconcile],
   ['retry','Gửi lại đúng lựa chọn đang giữ',retry]]){const e=dom.createElement('button');e.type='button';e.textContent=label;
   e.setAttribute('data-broll-timeline-'+name,'');e.addEventListener('click',()=>fn().catch(e=>onMessage(e.message,true)));root.append(e);controls[name]=e;}
  const e=dom.createElement('p');e.setAttribute('role','status');e.setAttribute('data-broll-timeline-status','');root.append(e);controls.status=e;}
 function token(){try{const v=getSessionToken();return typeof v==='string'&&v.trim()===v&&v.length<=2048?v:'';}catch{return'';}}
 function bucket(){const s=getState();return s.workspaceId&&s.projectId&&s.principal?.subject
  ?'vf-sql-broll-timeline-pending-v1:'+stable([s.workspaceId,s.projectId,s.principal.subject]):null;}
 function path(){const s=getState();return`/api/v1/projects/${s.projectId}/timeline/broll-review/${s.mediaPlanId}`;}
 function status(text){statusText=text;if(controls.status)controls.status.textContent=text;}
 function probe(){const key=bucket();if(!key){held=null;return;}try{const raw=storage.getItem(key);
  if(raw!==null&&raw!==undefined){if(held?.bucket!==key||held?.raw!==raw){held={bucket:key,raw};pending=null;}}
  else held=pending?{bucket:key,raw:null}:null;}catch{held={bucket:key,raw:null};pending=null;}}
 function sync(){const next=scope(getState()),now=token();if(next!==identity||now!==literal){identity=next;literal=now;epoch++;view=null;pending=null;working=false;}
  probe();let readable=false,writable=false;try{session(getState());demand(literal,'Cần token phiên.');readable=true;session(getState(),true);writable=true;}catch{}
  if(controls.read)controls.read.disabled=disposed||working||!readable;
  if(controls.reconcile)controls.reconcile.disabled=disposed||working||!writable||!pending;
  if(controls.retry)controls.retry.disabled=disposed||working||!writable||!pending?.retryAllowed;
  if(held&&!pending)status('Có bản ghi chưa rõ kết quả. Giữ nguyên; không tạo lần áp dụng mới.');}
 function live(ticket,owner,bound){return!disposed&&ticket===epoch&&identity===owner&&scope(getState())===owner&&literal&&token()===literal
  &&(bound===undefined||binding(getState())===bound);}
 function current(ticket,owner,bound,write=false){demand(live(ticket,owner,bound),'Nguồn, form hoặc phiên đã đổi; giữ yêu cầu để đối chiếu.');session(getState(),write);}
 function setWorking(value){working=value;sync();onBusyChanged();}
 const digest=v=>audioByteHash(new TextEncoder().encode(typeof v==='string'?v:stable(v)),cryptoImpl);
 async function checkedRead(value,ticket,owner,bound,write=false){brollTimelineRead(value,getState());
  const ctx=await digest(contextValue(value));current(ticket,owner,bound,write);demand(ctx===value.context_sha256,'Hash ngữ cảnh B-roll không khớp.');return value;}
 function custody(p,ticket,owner,bound,write=true){const key=held?.bucket,raw=storage.getItem(key);current(ticket,owner,bound,write);
  demand(pending===p&&typeof p.raw==='string'&&held?.bucket===bucket()&&held.raw===p.raw&&raw===p.raw,
   'Bản ghi đang giữ đã đổi; không nhận hoặc gửi lại lựa chọn khác.');return true;}
 function stored(p){return Object.fromEntries(Object.entries(p).filter(([k])=>!['raw','retryAllowed'].includes(k)));}
 function validateHeld(p,s){demand(exact(p,['schema_version','workspace_id','project_id','actor_ref','scope','media_plan_id','source_ui_sha256',
  'parent_timeline_sha256','parent_version_id','source','media_binding_sha256','session_sha256','body'])
  &&p.schema_version==='sql-broll-timeline-pending.v1'&&p.workspace_id===s.workspaceId&&p.project_id===s.projectId&&p.actor_ref===s.principal.subject
  &&p.scope===scope(s)&&p.media_plan_id===s.mediaPlanId&&hash(p.source_ui_sha256)&&hash(p.parent_timeline_sha256)
  &&hash(p.media_binding_sha256)&&hash(p.session_sha256)&&typeof p.parent_version_id==='string'&&p.parent_version_id
  &&exact(p.body,bodyKeys)&&p.body.expected_timeline_id===s.timeline.timeline_id&&Number.isSafeInteger(p.body.expected_version)
  &&p.body.expected_version>=1&&hash(p.body.expected_context_sha256)&&requestKey(p.body.request_key)&&p.body.acknowledged===true,
  'Bản ghi B-roll không đúng cấu trúc, phiên hoặc đề xuất.');brollTimelineSelection({item_ids:p.body.item_ids,replace_plan_clips:p.body.replace_plan_clips});
  sourceMatches(p.source,s,s.timeline);return p;}
 async function restore(ticket,owner,bound){if(!held)return null;const key=held.bucket,raw=held.raw;
  demand(typeof raw==='string','Chưa đọc được bản ghi đang giữ.');const p=validateHeld(JSON.parse(raw),getState());
  const sh=await digest(literal);current(ticket,owner,bound);demand(sh===p.session_sha256,'Không dùng yêu cầu cũ dưới token khác.');
  const ui=await digest(sourceUi(getState()));current(ticket,owner,bound);demand(ui===p.source_ui_sha256,'Nguồn hoặc tư liệu đang giữ đã đổi.');
  const found=storage.getItem(key);current(ticket,owner,bound);demand(bucket()===key&&found===raw&&held.raw===raw,'Bản ghi đã đổi trong lúc khôi phục.');
  if(getState().timeline.current_version===p.body.expected_version&&getState().timeline.current_version_id===p.parent_version_id){
   const ph=await digest(getState().timeline);current(ticket,owner,bound);demand(ph===p.parent_timeline_sha256,'Timeline cha đã đổi.');parents.set(p.body.request_key,copy(getState().timeline));}
  pending=freeze({...p,raw,retryAllowed:false});return pending;}
 async function reload(){sync();session(getState());demand(literal&&!working,'Phiên hoặc thao tác chưa sẵn sàng.');
  const ticket=epoch,owner=identity,bound=binding(getState()),rb=readBinding(getState());view=null;setWorking(true);
  try{const p=await restore(ticket,owner,bound);current(ticket,owner,bound);const data=copy(await api(path()));current(ticket,owner,bound);
   await checkedRead(data,ticket,owner,bound);if(!p)demand(same(data.timeline,getState().timeline),'Timeline dịch vụ đã đổi; tải đúng bản trước.');
   else{custody(p,ticket,owner,bound,false);demand(data.timeline_id===p.body.expected_timeline_id
    &&[p.body.expected_version,p.body.expected_version+1].includes(data.timeline_version),'Timeline đã vượt lần áp dụng đang giữ.');}
   await onRead(copy(data));current(ticket,owner,undefined);demand(readBinding(getState())===rb,'Nguồn đổi sau bản đọc B-roll.');
   view=freeze({data,readBinding:rb});status(p?'Có lần áp dụng chưa rõ kết quả. Đối chiếu trước khi sửa tiếp.':'Đã đọc B-roll; chọn cảnh và xác nhận trước khi áp dụng.');return copy(data);
  }finally{if(live(ticket,owner))setWorking(false);else sync();}}
 function matches(data,p){const r=data.receipt;return!!r&&r.workspace_id===p.workspace_id&&r.project_id===p.project_id&&r.actor_ref===p.actor_ref
  &&r.media_plan_id===p.media_plan_id&&r.timeline_id===p.body.expected_timeline_id&&r.parent_version_id===p.parent_version_id
  &&r.parent_version===p.body.expected_version&&r.result_version===p.body.expected_version+1&&r.request_key===p.body.request_key
  &&r.context_sha256===p.body.expected_context_sha256&&r.media_binding_sha256===p.media_binding_sha256&&same(r.item_ids,p.body.item_ids)
  &&r.replace_plan_clips===p.body.replace_plan_clips&&same(data.source,p.source)
  &&(!observed.has(r.request_key)||observed.get(r.request_key)===stable({timeline:data.timeline,receipt:r,source:data.source,items:data.items}));}
 function preserved(parent,data,p){if(!parent)return;const before=parent.snapshot,after=data.timeline.snapshot;
  const outer=({schema_version,tracks,metadata,...v})=>v,meta=({broll_review,...v})=>v;
  demand(same(outer(before),outer(after))&&same(meta(before.metadata),meta(after.metadata)),
   'B-roll không được đổi thời lượng, cấu hình hoặc metadata nguồn.');
  const other=t=>t.filter(v=>v.kind!=='broll').map(({order,...v})=>v);
  demand(same(other(before.tracks),other(after.tracks)),'B-roll không được đổi hình nguồn, lời nói hoặc phụ đề.');
  const replaced=c=>p.body.replace_plan_clips&&c.metadata?.media_plan_id===p.media_plan_id&&p.body.item_ids.includes(c.metadata?.media_plan_item_id);
  for(const t of before.tracks.filter(t=>t.kind==='broll')){const saved=after.tracks.find(v=>v.track_id===t.track_id);
   const info=({order,clips,...v})=>v;
   demand(saved&&same(info(t),info(saved))&&t.clips.filter(c=>!replaced(c)).every(c=>saved.clips.some(v=>same(v,c))),
    'B-roll không được xóa hoặc đổi các clip ngoài lựa chọn thay thế.');}}
 async function accept(data,p,ticket,owner,bound){current(ticket,owner,bound,true);await checkedRead(data,ticket,owner,bound,true);
  demand(matches(data,p),'Biên nhận chưa chứng minh đúng lần áp dụng; giữ UNKNOWN.');
  const requestHash=await digest({project_id:p.project_id,media_plan_id:p.media_plan_id,actor_ref:p.actor_ref,request:p.body});current(ticket,owner,bound,true);
  demand(requestHash===data.receipt.request_sha256,'Hash yêu cầu chưa khớp biên nhận B-roll.');custody(p,ticket,owner,bound);
  demand(data.timeline.approval_status==='draft'&&data.timeline.latest_preview_id===null&&data.timeline.latest_preview_valid===false,
   'B-roll chưa vô hiệu hóa preview và duyệt bản cũ.');preserved(parents.get(p.body.request_key),data,p);
  const metadata=data.timeline.snapshot.metadata.broll_review;
  demand(metadata?.media_plan_id===p.media_plan_id&&same(metadata.item_ids,[...p.body.item_ids].sort())
   &&metadata.human_approval_required===true&&metadata.source_media_mutated===false,'Timeline thiếu dấu lựa chọn B-roll đã duyệt.');
  const clips=data.timeline.snapshot.tracks.filter(t=>t.kind==='broll').flatMap(t=>t.clips);
  for(const id of p.body.item_ids){const item=data.items.find(i=>i.media_plan_item_id===id);
   const chosen=clips.filter(c=>c.metadata?.media_plan_id===p.media_plan_id&&c.metadata?.media_plan_item_id===id);
   demand(chosen.length>0&&chosen.every(c=>c.volume===0&&c.metadata.media_asset_id===item.selected_media_asset_id
    &&c.metadata.original_audio_preserved===true&&c.metadata.provider_dispatches===0),'B-roll chưa có clip canonical giữ nguyên âm thanh gốc.');}
  observed.set(p.body.request_key,stable({timeline:data.timeline,receipt:data.receipt,source:data.source,items:data.items}));
  const callbackHeld=held;let active=true;const requestGuard=()=>{demand(active,'Phạm vi đối chiếu đã kết thúc.');custody(p,ticket,owner,bound);
   demand(held===callbackHeld,'Bản ghi yêu cầu đã đổi.');return true;};
  try{requestGuard();await onSaved({workspace_id:p.workspace_id,project_id:p.project_id,actor_ref:p.actor_ref,media_plan_id:p.media_plan_id,
   parent_version_id:p.parent_version_id,parent_version:p.body.expected_version,parent_timeline:copy(parents.get(p.body.request_key)??null),
   parent_timeline_sha256:p.parent_timeline_sha256,result_version:data.timeline_version,source_ui_sha256:p.source_ui_sha256,
   request:copy(p.body),read:copy(data),receipt:copy(data.receipt),timeline:copy(data.timeline)},requestGuard);}finally{active=false;}
  current(ticket,owner,undefined,true);demand(same(getState().timeline,data.timeline),'Studio chưa nhận đúng timeline B-roll; giữ UNKNOWN.');
  const installed=binding(getState()),ui=await digest(sourceUi(getState()));current(ticket,owner,installed,true);
  demand(ui===p.source_ui_sha256&&same(getState().timeline,data.timeline),'Nguồn đổi sau khi nhận B-roll.');
  custody(p,ticket,owner,installed);demand(typeof storage.compareAndRemoveItem==='function'
   &&storage.compareAndRemoveItem(held.bucket,p.raw)===true,'Chưa xóa có đối chiếu được bản ghi; giữ UNKNOWN.');
  pending=null;held=null;parents.delete(p.body.request_key);observed.delete(p.body.request_key);view=null;status('Đã áp dụng B-roll. Tạo preview và duyệt lại trước render hoặc đăng.');}
 async function apply(selected,{acknowledged=false}={}){sync();session(getState(),true);
  demand(acknowledged===true&&literal&&!working&&!held&&!pending&&view?.readBinding===readBinding(getState()),'Đọc đúng đề xuất và xác nhận lựa chọn; xử lý yêu cầu đang giữ trước.');
  const choice=freeze(copy(brollTimelineSelection(selected))),ticket=epoch,owner=identity,bound=binding(getState()),parent=copy(getState().timeline),read=copy(view.data);
  demand(choice.item_ids.every(id=>read.ready_item_ids.includes(id)),'Chỉ chọn tư liệu đã phân giải trong bản đọc.');setWorking(true);
  try{const data=copy(await api(path()));current(ticket,owner,bound,true);await checkedRead(data,ticket,owner,bound,true);
   demand(same({...data,replayed:false},{...read,replayed:false})&&same(data.timeline,parent),'B-roll hoặc timeline dịch vụ đã đổi; đọc lại trước.');
   const ui=await digest(sourceUi(getState()));current(ticket,owner,bound,true);const ph=await digest(parent);current(ticket,owner,bound,true);
   const sh=await digest(literal);current(ticket,owner,bound,true);const key=bucket();
   const body={expected_timeline_id:parent.timeline_id,expected_version:parent.current_version,expected_context_sha256:data.context_sha256,
    request_key:newRequestKey(),item_ids:choice.item_ids,replace_plan_clips:choice.replace_plan_clips,acknowledged:true};demand(requestKey(body.request_key),'Mã lần áp dụng chưa hợp lệ.');
   const record={schema_version:'sql-broll-timeline-pending.v1',workspace_id:getState().workspaceId,project_id:getState().projectId,
    actor_ref:getState().principal.subject,scope:owner,media_plan_id:getState().mediaPlanId,source_ui_sha256:ui,parent_timeline_sha256:ph,
    parent_version_id:parent.current_version_id,source:copy(data.source),media_binding_sha256:data.media_binding_sha256,session_sha256:sh,body};
   const raw=JSON.stringify(record),empty=storage.getItem(key);current(ticket,owner,bound,true);
   demand(bucket()===key&&!held&&!pending&&(empty===null||empty===undefined),'Có bản ghi khác; không ghi đè.');
   storage.setItem(key,raw);current(ticket,owner,bound,true);pending=freeze({...record,raw,retryAllowed:false});held={bucket:key,raw};parents.set(body.request_key,parent);
   custody(pending,ticket,owner,bound);const p=pending,result=copy(await api(path(),{method:'PUT',body:JSON.stringify(body)}));current(ticket,owner,bound,true);
   await accept(result,p,ticket,owner,bound);return copy(result);
  }finally{if(live(ticket,owner))setWorking(false);else sync();}}
 async function reconcile(){sync();session(getState(),true);demand(pending&&literal&&!working,'Đọc yêu cầu đúng phiên trước khi đối chiếu.');
  let p=pending;pending=freeze({...stored(p),raw:p.raw,retryAllowed:false});p=pending;view=null;
  const ticket=epoch,owner=identity,bound=binding(getState());setWorking(true);
  try{custody(p,ticket,owner,bound);const data=copy(await api(path()));current(ticket,owner,bound,true);await checkedRead(data,ticket,owner,bound,true);
   custody(p,ticket,owner,bound);demand(data.media_binding_sha256===p.media_binding_sha256&&same(data.source,p.source),'Nguồn hoặc tư liệu dịch vụ đã đổi; giữ UNKNOWN.');
   if(matches(data,p)){await accept(data,p,ticket,owner,bound);return copy(data);}
   demand(data.receipt?.request_key!==p.body.request_key&&data.context_sha256===p.body.expected_context_sha256
    &&data.timeline_version===p.body.expected_version&&data.timeline_version_id===p.parent_version_id&&same(data.timeline,getState().timeline),
   'Chưa chứng minh đúng bản cha hoặc biên nhận; giữ UNKNOWN.');
   const ph=await digest(data.timeline);current(ticket,owner,bound,true);demand(ph===p.parent_timeline_sha256,'Timeline cha không còn khớp.');custody(p,ticket,owner,bound);
   pending=freeze({...stored(p),raw:p.raw,retryAllowed:true});view=freeze({data,readBinding:readBinding(getState())});
   status('Chưa thấy lần áp dụng. Có thể gửi lại đúng mã, nội dung và phiên bản đang giữ.');return copy(data);
  }finally{if(live(ticket,owner))setWorking(false);else sync();}}
 async function retry(){sync();session(getState(),true);demand(pending?.retryAllowed&&literal&&!working&&view?.readBinding===readBinding(getState()),'Đối chiếu đúng bản cha trước khi gửi lại.');
  const p=pending,ticket=epoch,owner=identity,bound=binding(getState());setWorking(true);
  try{custody(p,ticket,owner,bound);const latest=copy(await api(path()));current(ticket,owner,bound,true);await checkedRead(latest,ticket,owner,bound,true);
   demand(same({...latest,replayed:false},{...view.data,replayed:false})&&latest.context_sha256===p.body.expected_context_sha256,'Bản cha đổi trước khi gửi lại.');
   custody(p,ticket,owner,bound);const result=copy(await api(path(),{method:'PUT',body:JSON.stringify(p.body)}));current(ticket,owner,bound,true);
   await accept(result,p,ticket,owner,bound);return copy(result);
  }finally{if(live(ticket,owner))setWorking(false);else sync();}}
 sync();return{sync,reload,reconcile,retry,applySelection:async(...args)=>{try{await apply(...args);return true;}catch(e){try{onMessage(e.message,true);}catch{}return false;}},
  dispose(){disposed=true;epoch++;working=false;sync();onBusyChanged();},isWorking:()=>working,isPending:()=>!!held||!!pending,isDirty:()=>false,
  getStatus:()=>statusText,state:()=>({pending:pending?copy(stored(pending)):null,held:!!held,read:view?copy(view.data):null,canRetry:pending?.retryAllowed===true})};
}
