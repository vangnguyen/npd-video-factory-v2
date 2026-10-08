const schema='native-scene-narration-plan-v1',id=/^[a-f0-9]{32}$/,sha=/^[a-f0-9]{64}$/;
const source=p=>p?.document?.canonical_timeline?.snapshot?.metadata?.native_auto_edit_schema==='native-auto-edit-timeline-v1';
const active=s=>s.active||(s.project?.jobs??[]).some(j=>['queued','running','retrying'].includes(j.status));
const blocked=(s,review=false)=>s.busy||s.dirty||active(s)||s.project?.archived||(review?s.canReview===false:s.canEdit===false)||source(s.project);
export function validateNarrationPage(value,state){
  if(value?.schema_version!==schema||value.project_id!==state.project?.id||value.revision!==state.project?.revision||!Array.isArray(value.items)||value.items.length>50)throw new Error('Kết quả lời đọc không khớp dự án đã lưu.');
  for(const item of value.items){
    if(!id.test(item.job_id)||typeof item.voice_input_current!=='boolean'||typeof item.timing_apply_current!=='boolean')throw new Error('Kết quả lời đọc chưa hợp lệ.');
    if(item.result){const r=item.result,p=r.plan;
      if(!sha.test(r.plan_sha256)||p?.schema_version!==schema||p.project_id!==value.project_id||p.job_id!==item.job_id||p.version!==1||p.word_alignment_claimed!==false||p.speech_quality_accepted!==false||p.confidence!==null||!Array.isArray(p.items)||!p.items.length||p.items.length>20||!Number.isFinite(p.recommended_duration_seconds)||p.recommended_duration_seconds<=0||p.recommended_duration_seconds>180||r.voice_url!==`/api/projects/${value.project_id}/narration/${item.job_id}/audio`)throw new Error('Bằng chứng hoặc nguồn lời đọc không hợp lệ.');
      for(const scene of p.items)if(!Number.isFinite(scene.recommended_duration_seconds)||scene.recommended_duration_seconds<=0||!Number.isFinite(scene.measured_audio_seconds)||scene.measured_audio_seconds<0)throw new Error('Thời lượng lời đọc chưa hợp lệ.');
    }
  }
  return value;
}
export function narrationRequest(state,page,action,{jobId,acknowledged=false,requestKey,reviewer}={}){
  if(!id.test(state.project?.id??'')||blocked(state,action==='approve'))throw new Error('Lưu thay đổi và chờ tác vụ hoàn tất trước khi tạo hoặc áp dụng lời đọc.');
  const p=state.project,base=`/api/projects/${p.id}`;
  if(action==='approve'){
    if(typeof reviewer!=='string'||!reviewer.trim()||reviewer.trim().length>100||acknowledged!==true)throw new Error('Nhập tên và xác nhận duyệt nội dung để tạo lời đọc.');
    return {path:base+'/approve',body:{revision:p.revision,reviewer:reviewer.trim(),acknowledged:true,purpose:'narration'}};
  }
  if(action==='prepare'){
    if(!p.approval||p.approval.revision!==p.revision||!p.document?.canonical_timeline||typeof requestKey!=='string'||requestKey.length<8||requestKey.length>100)throw new Error('Duyệt nội dung đã lưu trước khi tạo lời đọc.');
    return {path:base+'/jobs',body:{revision:p.revision,kind:'narration',request_key:requestKey}};
  }
  const item=validateNarrationPage(page,state).items.find(v=>v.job_id===jobId);
  if(action!=='apply'||!item?.result||!item.timing_apply_current||!item.result.plan.fit_narration_template||acknowledged!==true)throw new Error('Xem kết quả, chọn mẫu theo lời đọc và xác nhận áp dụng thời lượng.');
  return {path:`${base}/narration/${jobId}/apply`,body:{revision:p.revision,expected_plan_sha256:item.result.plan_sha256,acknowledged:true}};
}
export function initializeNativeNarration({api,getState,onMessage,onWorking=()=>{},onSaved=async()=>{},dom=globalThis.document,newKey=()=>globalThis.crypto.randomUUID()}){
  const root=dom.getElementById('native-narration-panel');let page=null,working=false,serial=0,binding=null,pending=null;
  const context=()=>{const s=getState();return `${s.project?.id}:${s.project?.revision}:${source(s.project)}`;};
  function node(tag,text,parent,attributes={}){const value=dom.createElement(tag);if(text!==null)value.textContent=text;for(const [k,v]of Object.entries(attributes))value.setAttribute(k,String(v));parent.append(value);return value;}
  node('summary','Lời đọc & thời lượng đã đo',root);node('p','Duyệt nội dung trước khi tạo giọng. Nghe audio và xem thời lượng từng cảnh, rồi chọn áp dụng. Áp dụng sẽ xóa duyệt trước đó; preview có tiếng và video cuối vẫn cần xem, nghe và duyệt riêng.',root,{class:'hint'});
  const tools=node('div',null,root,{class:'planner-tools'}),refresh=node('button','Tải kết quả lời đọc',tools,{type:'button'}),prepare=node('button','Tạo lời đọc để xem trước',tools,{type:'button'}),list=node('div',null,root);
  const review=node('div',null,root),nameLabel=node('label','Người duyệt nội dung',review),reviewer=node('input',null,nameLabel,{maxlength:'100'}),ackLabel=node('label',null,review,{class:'check'}),reviewAck=node('input',null,ackLabel,{type:'checkbox'});
  node('span','Tôi đã kiểm tra nội dung đã lưu và quyền sử dụng tư liệu. Duyệt để tạo lời đọc; preview có tiếng và video cuối cần xem, nghe và duyệt riêng.',ackLabel);
  const approve=node('button','Duyệt để tạo lời đọc',review,{type:'button'});
  async function execute(request,revisionChange){
    if(working)return;const key=context(),ticket=++serial;working=true;onWorking(true);controls();
    try{await api(request.path,{method:'POST',body:JSON.stringify(request.body)});if(ticket!==serial||key!==context())return;
      pending=null;page=null;draw();await onSaved();onMessage(revisionChange?'Đã áp dụng thời lượng đo được. Tạo preview có tiếng, xem và nghe rồi duyệt lại trước khi render.':request.body.purpose==='narration'?'Đã duyệt nội dung để tạo lời đọc. Tạo giọng, xem thời lượng và áp dụng vào timeline trước khi duyệt preview.':'Đã xếp hàng tạo lời đọc. Chờ tác vụ hoàn tất rồi tải kết quả để nghe và kiểm tra.');
    }catch(error){onMessage(error.message,true);}finally{working=false;onWorking(false);controls();}
  }
  async function load(){
    if(working||!id.test(getState().project?.id??'')||source(getState().project))return;const key=context(),ticket=++serial;working=true;onWorking(true);controls();
    try{const value=await api(`/api/projects/${getState().project.id}/narration`);if(ticket!==serial||key!==context())return;page=validateNarrationPage(value,getState());draw();}
    catch(error){if(ticket===serial)onMessage(error.message,true);}finally{working=false;onWorking(false);controls();}
  }
  function draw(){list.replaceChildren();if(!page)return;
    for(const item of page.items){const card=node('article',null,list,{class:'planner-scene'});node('h3',`Lời đọc · ${item.status}`,card);
      if(!item.result){if(item.error)node('p',String(item.error.code??'Chưa có kết quả'),card);continue;}
      const plan=item.result.plan;node('p',`Audio gốc ${plan.source_duration_seconds.toFixed(2)} giây · bản dựng theo lời đọc ${plan.recommended_duration_seconds.toFixed(2)} giây. Chưa xác nhận chất lượng giọng hoặc căn chỉnh từng từ.`,card);
      node('audio',null,card,{controls:'',preload:'none',src:`/api/projects/${page.project_id}/narration/${item.job_id}/audio`});
      for(const scene of plan.items)node('p',`Cảnh ${scene.scene}: ${scene.narration} · audio ${scene.measured_audio_seconds.toFixed(2)} giây · thời lượng đề xuất ${scene.recommended_duration_seconds.toFixed(2)} giây`,card);
      if(!item.voice_input_current)node('p','Lời đọc hoặc giọng đã thay đổi. Cần tạo lại.',card);
      const label=node('label',null,card,{class:'check'}),ack=node('input',null,label,{type:'checkbox'});node('span','Tôi đã nghe audio và xem thời lượng từng cảnh. Áp dụng vào timeline và duyệt lại sau đó.',label);
      const button=node('button','Áp dụng thời lượng đã đo',card,{type:'button'});button._narrationItem=item;button._narrationAck=ack;
      ack.addEventListener('change',controls);button.addEventListener('click',async()=>{try{await execute(narrationRequest(getState(),page,'apply',{jobId:item.job_id,acknowledged:ack.checked}),true);}catch(error){onMessage(error.message,true);}});
    }
  }
  function controls(){const state=getState();root.hidden=!state.project||source(state.project);refresh.disabled=working||state.busy||!state.project||source(state.project);
    reviewer.disabled=working||blocked(state,true);reviewAck.disabled=reviewer.disabled;approve.disabled=reviewer.disabled||!state.project?.document.proposal||!reviewAck.checked||!reviewer.value?.trim();
    prepare.disabled=working||blocked(state)||!state.project?.approval||state.project.approval.revision!==state.project.revision||!state.project.document?.canonical_timeline;
    for(const button of list.querySelectorAll('button'))button.disabled=working||blocked(state)||!button._narrationItem?.timing_apply_current||!button._narrationItem.result?.plan.fit_narration_template||!button._narrationAck.checked;
    for(const input of list.querySelectorAll('input'))input.disabled=working||blocked(state);
  }
  function sync(){const key=context();if(binding!==key){binding=key;serial++;page=null;pending=null;draw();}controls();}
  refresh.addEventListener('click',load);prepare.addEventListener('click',async()=>{try{const state=getState();pending=pending??narrationRequest(state,page,'prepare',{requestKey:newKey()});await execute(pending,false);}catch(error){onMessage(error.message,true);}});
  reviewer.addEventListener('input',controls);reviewAck.addEventListener('change',controls);approve.addEventListener('click',async()=>{try{await execute(narrationRequest(getState(),page,'approve',{reviewer:reviewer.value,acknowledged:reviewAck.checked}),false);}catch(error){onMessage(error.message,true);}});
  sync();return {load,sync,controls,isWorking:()=>working};
}
