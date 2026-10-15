// Explicit terminal-intent release. No output adoption, automatic POST, timer or retry.
import {audioRole,audioByteHash} from './uploaded-audio-review.mjs';
import {sessionToken} from './auth.mjs';
import {videoWordSessionStorage} from './video-transcript-word-review.mjs';
const copy=structuredClone,object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const stable=v=>JSON.stringify(v,(_k,x)=>object(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
const same=(a,b)=>stable(a)===stable(b),demand=(v,m)=>{if(!v)throw Error(m);};
const exact=(v,keys)=>object(v)&&same(Object.keys(v).sort(),[...keys].sort());
const sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const id=(v,p)=>typeof v==='string'&&new RegExp('^'+p+'_[A-Za-z0-9_-]{4,60}$').test(v);
const key=v=>typeof v==='string'&&/^[A-Za-z0-9_-]{8,128}$/.test(v);
const publicFields=['subject','display_name','platform_role','workspace_roles','expires_at','human_write_enabled'];
const principal=p=>Object.fromEntries(publicFields.map(k=>[k,p?.[k]]));
const resultFields=['schema_version','state','workspace_id','project_id','actor_ref','original_operation_id','intent_sha256','admission_receipt','job',
 'worker_claim_present','worker_claim_status','observation_sha256','settlement','can_adopt','output','original_job_preserved','provider_calls','publishing_enabled','owner_approval_inferred'];
const recordFields=['schema_version','body','context','core_sha256','principal_sha256','credential_sha256','receipt'];
const flags=v=>v.provider_calls===0&&v.publishing_enabled===false&&v.owner_approval_inferred===false;
function session(s,now){demand(id(s.workspaceId,'wsp')&&id(s.projectId,'prj')&&typeof s.principal?.subject==='string'&&s.principal.subject
 &&Date.parse(s.principal.expires_at)>now&&['editor','reviewer','owner'].includes(audioRole(s))&&s.principal.human_write_enabled===true&&!s.busy&&!s.dirty,
 'Cần phiên còn hiệu lực và quyền sửa; chờ hoặc lưu bản sửa khác trước khi đóng yêu cầu.');}
function core(s){return stable([s.workspaceId,s.workspaceSlug??null,s.projectId,principal(s.principal),s.timeline??null,s.analysis??null,
 s.analyses??null,s.assets??null,s.mediaPlans??null,s.settlementSource??null]);}
export function validateBrollInternalSettlement(v,held,intentSha){const r=held.receipt,j=v?.job;
 demand(exact(v,resultFields)&&v.schema_version==='broll-internal-terminal-settlement.v1'&&['observed','settled'].includes(v.state)&&flags(v)
  &&v.workspace_id===held.context.workspace_id&&v.project_id===held.context.project_id&&v.actor_ref===held.context.actor_ref
  &&v.original_operation_id===r.operation_id&&v.intent_sha256===intentSha&&sha(v.observation_sha256)&&same(v.admission_receipt,r)
  &&v.can_adopt===false&&v.output===null&&v.original_job_preserved===true&&typeof v.worker_claim_present==='boolean'
  &&(v.worker_claim_present?['running','succeeded','rejected'].includes(v.worker_claim_status):v.worker_claim_status===null),
 'Biên nhận đóng yêu cầu chưa đúng bản ghi gốc hoặc cho phép nhận dữ liệu ngoài phạm vi.');
 demand(j?.resolution_job_id===r.resolution_job_id&&j.workspace_id===r.workspace_id&&j.project_id===r.project_id
  &&j.media_plan_id===r.media_plan_id&&j.media_plan_item_id===r.media_plan_item_id&&['failed','cancelled','succeeded'].includes(j.status)
  &&j.provider_key==='internal-media'&&j.capability==='internal_media'&&j.operation==='reuse-user-asset'&&j.external_call===false&&j.paid===false
  &&j.real_provider_tested===false&&j.provider_job_id===null&&j.selected_candidate_id===null
  &&j.provenance?.reviewed_internal_resolution_v1?.operation_id===r.operation_id
  &&j.provenance.reviewed_internal_resolution_v1.binding_sha256===r.context_sha256
  &&j.provenance.request?.source_asset_id===r.asset_id&&j.provenance.source_media_mutated===false&&j.provenance.publish_requested===false
  &&(j.status!=='succeeded'||v.worker_claim_present&&v.worker_claim_status==='succeeded'&&id(j.output_media_asset_id,'mas')),
 'Chỉ đóng đúng job nội bộ đã kết thúc; không hủy hoặc tiếp quản job đang chạy.');
 if(v.state==='observed')demand(v.settlement===null,'Bản quan sát chưa phải biên nhận đã ghi.');
 else{const x=v.settlement;demand(exact(x,['settlement_id','decision','settled_by_authority_sha256','created_at','original_operation_id',
   'resolution_job_id','terminal_status','current_output_adopted','provider_calls'])&&/^sop_[a-f0-9]{32}$/.test(x.settlement_id)
   &&x.decision==='release_held_intent'&&sha(x.settled_by_authority_sha256)&&Number.isFinite(Date.parse(x.created_at))
   &&x.original_operation_id===r.operation_id&&x.resolution_job_id===r.resolution_job_id&&x.terminal_status===j.status
   &&x.current_output_adopted===false&&x.provider_calls===0,'Biên nhận chưa chứng minh đúng lần đóng yêu cầu.');}
 return v;
}
export function initializeSqlBrollInternalSettlement({api,getState,getSessionToken=sessionToken,storage=videoWordSessionStorage(),
 cryptoImpl=globalThis.crypto,clock=()=>Date.now(),onInspected=async()=>true,onSettled=async()=>false,onReleased=()=>false,onStatus=()=>{},onBusyChanged=()=>{}}){
 let disposed=false,busy=false,epoch=0,view=null,released=false,rebindBlocked=false,status='Chưa kiểm tra yêu cầu nội bộ đã kết thúc.';
 const digest=v=>audioByteHash(new TextEncoder().encode(v),cryptoImpl);
 const token=()=>{const v=getSessionToken();demand(typeof v==='string'&&v.trim()===v&&v.length>=8&&v.length<=2048,'Cần token phiên hiện tại.');return v;};
 const bucket=()=>{const s=getState();return s.workspaceId&&s.projectId&&s.principal?.subject?'vf-sql-broll-internal-pending-v1:'+JSON.stringify([s.workspaceId,s.projectId,s.principal.subject]):null;};
 function current(c){session(getState(),clock());demand(!disposed&&c.ticket===epoch&&token()===c.token&&bucket()===c.bucket
   &&core(getState())===c.core&&stable(getState().settlementDraft??null)===c.draft,'Phiên, nguồn hoặc form đã đổi; giữ yêu cầu gốc.');return true;}
 function owns(c){const raw=storage?.getItem(c.bucket);current(c);demand(raw===c.raw,'Bản ghi đang giữ đã bị thay hoặc xóa; không đóng bản khác.');return true;}
 function absent(c){const raw=storage?.getItem(c.bucket);current(c);demand(raw===null||raw===undefined,'Một bản ghi khác đã xuất hiện; không sửa hoặc xóa.');return true;}
 function capture(){session(getState(),clock());demand(!disposed&&!busy&&!rebindBlocked,'Đang có thao tác hoặc cần tải lại sau khi xác minh biên nhận.');
  const c={ticket:++epoch,token:token(),bucket:bucket(),core:core(getState()),draft:stable(getState().settlementDraft??null)};
  c.raw=storage?.getItem(c.bucket);current(c);demand(typeof c.raw==='string'&&new TextEncoder().encode(c.raw).length<=5*1024*1024,
   'Cần đúng bản ghi nội bộ gốc có thể đọc.');owns(c);return c;}
 async function held(c){let h;try{h=JSON.parse(c.raw);}catch{throw Error('Bản ghi đang giữ không đọc được; giữ nguyên.');}
  const s=getState();demand(exact(h,recordFields)&&h.schema_version==='sql-broll-internal-pending.v1'&&object(h.context)&&object(h.receipt)
   &&['core_sha256','principal_sha256','credential_sha256'].every(k=>sha(h[k]))&&h.context.workspace_id===s.workspaceId&&h.context.project_id===s.projectId
   &&h.context.actor_ref===s.principal.subject&&h.receipt.workspace_id===s.workspaceId&&h.receipt.project_id===s.projectId&&h.receipt.actor_ref===s.principal.subject
   &&/^sop_[a-f0-9]{32}$/.test(h.receipt.operation_id)&&id(h.receipt.media_plan_id,'mpl')&&id(h.receipt.media_plan_item_id,'mpi')
   &&id(h.receipt.resolution_job_id,'mrj')&&h.context.plan?.media_plan_id===h.receipt.media_plan_id&&h.context.item?.media_plan_item_id===h.receipt.media_plan_item_id
   &&exact(h.body,['request_key','context_sha256','asset_id','acknowledged'])&&key(h.body.request_key)&&h.body.acknowledged===true
   &&h.body.request_key===h.receipt.request_key&&h.body.asset_id===h.receipt.asset_id&&sha(h.body.context_sha256)
   &&h.body.context_sha256===h.receipt.context_sha256&&h.context.context_sha256===h.body.context_sha256&&flags(h.receipt),
   'Cần biên nhận gốc có job xác định, cùng người và dự án. Không suy ra job mới nhất.');
  const originalHash=await digest(h.context.context_json);owns(c);const {context_json,context_sha256,...projected}=h.context;
  demand(originalHash===context_sha256&&same(JSON.parse(context_json),projected),'JSON ngữ cảnh gốc không khớp hash.');
  c.intentSha=await digest(c.raw);owns(c);c.held=h;c.path='/api/v1/projects/'+s.projectId+'/media-plans/'+h.receipt.media_plan_id+'/items/'
   +h.receipt.media_plan_item_id+'/internal-resolution-settlement';return h;
 }
 async function freshSession(c){const p=await api('/api/v1/auth/session',{cache:'no-store'});owns(c);
  demand(same(principal(p),principal(getState().principal)),'Phiên công khai hiện tại chưa khớp.');}
 function validate(v,c){return validateBrollInternalSettlement(v,c.held,c.intentSha);}
 function message(text){status=text;onStatus(text);}
 async function inspect(){const c=capture();busy=true;released=false;
  try{onBusyChanged();current(c);await held(c);await freshSession(c);owns(c);
   const result=copy(await api(c.path+'/inspect',{method:'POST',body:JSON.stringify({intent_json:c.raw,intent_sha256:c.intentSha})}));owns(c);validate(result,c);
   let active=true;const guard=()=>{demand(active,'Phạm vi bản đọc đã kết thúc.');return owns(c);};
   try{guard();demand(await onInspected(copy(result),guard)===true,'Studio chưa xác minh bản đọc.');owns(c);}finally{active=false;}
   view={result:copy(result),raw:c.raw,bucket:c.bucket,core:c.core,token:c.token};message(result.state==='settled'?'Đã có biên nhận. Xác nhận rồi đọc đúng biên nhận để đóng bản đang giữ.':'Job đã kết thúc. Chỉ ghi nhận đóng sau xác nhận rõ ràng.');owns(c);return copy(result);
  }catch(e){view=null;throw e;}finally{busy=false;onBusyChanged();}}
 async function complete(c,result){validate(result,c);demand(result.state==='settled','Chưa có biên nhận đã ghi.');
  const audit=copy(await api(c.path+'/settlements/'+result.settlement.settlement_id,{cache:'no-store'}));owns(c);validate(audit,c);demand(same(audit,result),'Biên nhận đọc lại chưa khớp.');
  let active=true;const guard=()=>{demand(active,'Phạm vi xác minh đã kết thúc.');return owns(c);};
  try{guard();demand(await onSettled(copy(audit),guard)===true,'Studio chưa xác minh biên nhận; giữ bản ghi.');owns(c);}finally{active=false;}
  owns(c);demand(typeof storage?.compareAndRemoveItem==='function','Cần bộ nhớ đối chiếu đồng bộ để đóng đúng bản ghi.');
  // A store can throw after its native CAS already removed the proven record.
  // Keep that uncertain local completion blocked; only an explicit false is known not to remove.
  rebindBlocked=true;const removed=storage.compareAndRemoveItem(c.bucket,c.raw);
  if(removed===false){rebindBlocked=false;demand(false,'Bản ghi đã đổi; không xóa yêu cầu khác.');}
  demand(removed===true,'Chưa xác nhận kết quả đóng bản ghi; cần tải lại Studio.');current(c);
  let activeRelease=true;const afterReleaseGuard=()=>{demand(activeRelease,'Phạm vi đóng bản ghi đã kết thúc.');return absent(c);};
  try{afterReleaseGuard();demand(onReleased(copy(audit),afterReleaseGuard)===true,'Biên nhận đã xác minh; cần tải lại Studio để tiếp tục.');afterReleaseGuard();}
  finally{activeRelease=false;}
  rebindBlocked=false;released=true;view=null;message('Đã đóng đúng bản ghi nội bộ. Không nhận media hoặc đổi timeline.');absent(c);return copy(audit);
 }
 async function act(acknowledged,write){demand(acknowledged===true,'Xác nhận rõ việc đóng đúng yêu cầu đang giữ.');const c=capture();busy=true;released=false;
  try{onBusyChanged();current(c);await held(c);demand(view&&view.raw===c.raw&&view.bucket===c.bucket&&view.core===c.core&&view.token===c.token,
     'Kiểm tra lại yêu cầu với phiên và nguồn hiện tại trước khi đóng.');
   const selected=copy(view.result);demand(selected.state===(write?'observed':'settled'),write?'Biên nhận đã tồn tại; chỉ đọc và xác minh.':'Chưa có biên nhận; kiểm tra trước.');
   await freshSession(c);owns(c);let result=selected;
   if(write){result=copy(await api(c.path+'/settle',{method:'POST',body:JSON.stringify({intent_json:c.raw,intent_sha256:c.intentSha,
       observation_sha256:selected.observation_sha256,acknowledged:true})}));owns(c);validate(result,c);
     demand(result.state==='settled'&&result.observation_sha256===selected.observation_sha256,'Kết quả chưa khớp quan sát đã xác nhận.');}
   const done=await complete(c,result);absent(c);return done;
  }catch(e){view=null;throw e;}finally{busy=false;onBusyChanged();}}
 return {inspect,settle:ack=>act(ack,true),readSettlement:ack=>act(ack,false),sync(){if(view&&(view.core!==core(getState())||view.token!==getSessionToken()))view=null;},
  dispose(){disposed=true;epoch++;view=null;},isWorking:()=>busy,isHeld(){if(rebindBlocked)return true;const k=bucket();if(!k)return false;
   try{if(!storage)return true;const before=core(getState()),t=getSessionToken(),raw=storage.getItem(k);return before!==core(getState())||t!==getSessionToken()||raw!==null&&raw!==undefined;}catch{return true;}},
  state:()=>copy({view:view?.result??null,working:busy,released,rebind_blocked:rebindBlocked,status})};
}
