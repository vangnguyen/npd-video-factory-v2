const SHA=/^[a-f0-9]{64}$/,ID=/^[a-f0-9]{32}$/,EX=/^nvr_[a-f0-9]{32}$/;
const schema='native-narration-rights-exception-v1';
const context=s=>JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision]);
function validateRecord(r,s){
  if(r?.schema_version!==schema||r.workspace_id!==s.workspace_id||r.project_id!==s.project.id||!EX.test(r.exception_id??'')||!ID.test(r.narration_job_id??'')
    ||!SHA.test(r.sha256??'')||!SHA.test(r.provenance_sha256??'')||r.rights_independently_verified!==false||r.speech_quality_accepted!==false||r.publishing_authorized!==false
    ||r.provenance?.workspace_id!==s.workspace_id||r.provenance.project_id!==s.project.id||r.provenance.narration_job_id!==r.narration_job_id
    ||r.request?.acknowledged!==true||!['grant','revoke'].includes(r.request.action))throw new Error('Bản ghi ngoại lệ lời đọc không hợp lệ.');
  return r;
}
export function validateNarrationRightsPage(p,s){
  if(p?.schema_version!=='native-narration-rights-review-v1'||p.workspace_id!==s.workspace_id||p.project_id!==s.project?.id||p.revision!==s.project.revision
    ||typeof p.enabled!=='boolean'||p.publishing_enabled!==false||p.rights_independently_verified!==false||p.speech_quality_accepted!==false||p.external_calls!==0
    ||!Array.isArray(p.history)||p.history.length>200)throw new Error('Bằng chứng quyền lời đọc không khớp phiên bản dự án.');
  if(p.provenance!==null){const v=p.provenance;
    if(v?.schema_version!=='native-narration-publication-provenance-v1'||v.workspace_id!==s.workspace_id||v.project_id!==s.project.id||!ID.test(v.narration_job_id??'')
      ||!SHA.test(p.provenance_sha256??'')||!SHA.test(v.voice_audio_sha256??'')||!SHA.test(v.profile_sha256??'')||typeof v.explicit_fixture!=='boolean'
      ||v.rights_status!=='unknown'||v.rights_independently_verified!==false||v.speech_quality_accepted!==false||v.publishing_authorized!==false)throw new Error('Nguồn giọng hoặc mô hình chưa hợp lệ.');
  }else if(p.provenance_sha256!==null)throw new Error('Thiếu nguồn lời đọc.');
  for(const r of p.history)validateRecord(r,s);
  if(p.active_exception){validateRecord(p.active_exception,s);if(p.active_exception.provenance_sha256!==p.provenance_sha256)throw new Error('Ngoại lệ không thuộc lời đọc hiện tại.');}
  return p;
}
const previous=p=>p?.history.filter(r=>r.request.action==='grant'&&!p.history.some(other=>other.request.action==='revoke'&&other.request.exception_id===r.exception_id)).at(-1);
export function narrationRightsRequest(s,page,action,{reason,reference,days=7,allowPublishingReview=false,acknowledged=false,requestKey}={}){
  const p=validateNarrationRightsPage(page,s),prior=previous(p);
  if(!s.canManage||s.dirty||s.busy||s.active||s.project.archived||acknowledged!==true||!['grant','revoke'].includes(action))throw new Error('Lưu thay đổi, chờ tác vụ và xác nhận quyết định của Owner.');
  if(action==='grant'&&(!p.enabled||!p.provenance||p.provenance.explicit_fixture)||action==='revoke'&&!prior)throw new Error('Không thể ghi ngoại lệ cho lời đọc này.');
  if(typeof reason!=='string'||reason.trim().length<10||reason.length>2000||typeof reference!=='string'||reference.trim().length<5||reference.length>1000
    ||!Number.isInteger(days)||days<1||days>30||typeof allowPublishingReview!=='boolean'||typeof requestKey!=='string'||!/^[A-Za-z0-9_-]{16,100}$/.test(requestKey))throw new Error('Nhập lý do, tham chiếu và thời hạn hợp lệ.');
  const v=action==='grant'?p.provenance:prior.provenance;
  return {revision:s.project.revision,narration_job_id:v.narration_job_id,expected_provenance_sha256:action==='grant'?p.provenance_sha256:prior.provenance_sha256,
    action,reason:reason.trim(),evidence_reference:reference.trim(),valid_days:action==='grant'?days:7,allow_publishing_review:action==='grant'&&allowPublishingReview,
    acknowledged:true,exception_id:action==='revoke'?prior.exception_id:null,expected_exception_sha256:action==='revoke'?prior.sha256:null,request_key:requestKey};
}
export function initializeNativeNarrationRights({api,getState,dom=globalThis.document,onMessage=()=>{},onSaved=async()=>{},onWorking=()=>{},newKey=()=>globalThis.crypto.randomUUID()}){
  const root=dom.getElementById('native-narration-rights-panel');
  const node=(tag,text,parent)=>{const v=dom.createElement(tag);v.textContent=text??'';parent?.append(v);return v;};
  node('summary','Nguồn giọng & ngoại lệ quyền · Owner',root);node('p','Xem nguồn mô hình, preset và audio đã đo. Ngoại lệ có thời hạn chỉ cho phép xét duyệt xuất bản; không xác minh giấy phép, chất lượng giọng hoặc tự đăng. Lưu quyết định cần tạo preview có tiếng và duyệt lại.',root);
  const status=node('p','Chưa tải nguồn lời đọc.',root),read=node('button','Đọc nguồn lời đọc',root),detail=node('pre','',root),form=node('div','',root);
  const field=(text,tag='input')=>{const label=node('label',text,form);return node(tag,'',label);};
  const reason=field('Lý do và căn cứ cho ngoại lệ'),reference=field('Tham chiếu bằng chứng (không chứa bí mật)'),days=field('Thời hạn 1–30 ngày'),publish=field('Cho phép xét duyệt xuất bản; chưa cấp quyền đăng'),ack=field('Tôi là Owner và quyết định ngoại lệ này; quyền và chất lượng giọng chưa được xác minh độc lập.');
  reason.maxLength=2000;reference.maxLength=1000;days.type='number';days.min='1';days.max='30';days.value='7';publish.type=ack.type='checkbox';
  const grant=node('button','Ghi ngoại lệ lời đọc',root),revoke=node('button','Thu hồi ngoại lệ lời đọc',root);
  for(const b of [read,grant,revoke])b.type='button';detail.className='native-publication-evidence';form.className='scene-grid';
  let page=null,working=false,serial=0,binding=context(getState());const keys=new Map();
  const clear=()=>{page=null;reason.value=reference.value='';days.value='7';ack.checked=publish.checked=false;};
  function controls(){const s=getState();root.hidden=!s.project||s.project.document?.canonical_timeline?.snapshot?.metadata?.native_auto_edit_schema==='native-auto-edit-timeline-v1';
    const edit=!working&&!s.busy&&s.canManage&&!s.dirty&&!s.active&&!s.project?.archived&&!!page;
    read.disabled=working||s.busy||!s.project;for(const n of [reason,reference,ack])n.disabled=!edit;
    const canGrant=edit&&page.enabled&&page.provenance&&!page.provenance.explicit_fixture;
    days.disabled=publish.disabled=!canGrant;grant.disabled=!canGrant||!ack.checked;revoke.disabled=!edit||!previous(page)||!ack.checked;
  }
  function draw(){status.textContent=page?(page.enabled?'Ngoại lệ được bật bởi cấu hình Owner; xuất bản và chất lượng giọng vẫn cần duyệt riêng.':'Ngoại lệ đang tắt; có thể đọc hoặc thu hồi. Trình duyệt không thể bật tính năng.'):'Chưa tải nguồn lời đọc.';
    detail.textContent=page?JSON.stringify({provenance:page.provenance,attention:page.attention,active_exception:page.active_exception,history:page.history},null,2):'';controls();}
  function sync(){const c=context(getState());if(c!==binding){binding=c;serial++;clear();}draw();}
  async function perform(fn){sync();if(working||getState().busy)return;const ticket=++serial,key=context(getState());working=true;onWorking(true);controls();
    try{const apply=await fn();if(ticket===serial&&key===context(getState()))await apply?.();}
    catch(e){if(ticket===serial&&key===context(getState()))onMessage(e.message,true);}
    finally{working=false;onWorking(false);if(key!==context(getState()))sync();else draw();}
  }
  async function load(){const s=getState();if(!s.project)return;return perform(async()=>{const p=validateNarrationRightsPage(await api(`/api/projects/${s.project.id}/narration-rights`),s);return()=>{page=p;};});}
  async function record(action){controls();if((action==='grant'?grant:revoke).disabled)return;
    const s=getState();try{
      // Retain the same explicit request after a lost reply; never retry automatically.
      const preliminary=narrationRightsRequest(s,page,action,{reason:reason.value,reference:reference.value,days:Number(days.value),allowPublishingReview:publish.checked,acknowledged:ack.checked,requestKey:'native-narration-rights-preliminary'});
      const signature=binding+JSON.stringify({...preliminary,request_key:null}),key=keys.get(signature)??`native-voice-rights-${newKey()}`;keys.set(signature,key);const body={...preliminary,request_key:key};
      return perform(async()=>{const value=await api(`/api/projects/${s.project.id}/narration-rights`,{method:'POST',body:JSON.stringify(body)});validateRecord(value?.record,s);
        if(value.schema_version!==schema||value.workspace_id!==s.workspace_id||value.project_id!==s.project.id||value.revision!==s.project.revision+1||value.approval_invalidated!==true||value.media_bytes_changed!==false||value.external_calls!==0
          ||Object.entries(body).filter(([name])=>name!=='request_key').some(([name,v])=>value.record.request[name]!==v))throw new Error('Biên nhận quyền lời đọc không hợp lệ.');
        return async()=>{clear();await onSaved(value);onMessage('Đã ghi quyết định. Tạo preview có tiếng, xem và nghe rồi duyệt lại; xuất bản cần phê duyệt riêng.');};});
    }catch(e){onMessage(e.message,true);}
  }
  read.addEventListener('click',load);grant.addEventListener('click',()=>record('grant'));revoke.addEventListener('click',()=>record('revoke'));ack.addEventListener('change',controls);
  sync();return {load,record,sync,controls,isWorking:()=>working};
}
