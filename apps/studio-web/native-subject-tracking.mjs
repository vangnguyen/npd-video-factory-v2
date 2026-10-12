// Local image matching never claims face/person inference or final approval.
const sha=/^[a-f0-9]{64}$/,id=/^[a-f0-9]{32}$/,tracking=/^ltr_[a-f0-9]{24}$/;
function stateOf(state){const p=state.project,c=p?.document?.canonical_timeline;if(!p||!id.test(p.id)||!c||c.snapshot?.metadata?.native_auto_edit_schema!=='native-auto-edit-timeline-v1')throw new Error('Mở bản dựng video nguồn trước.');return{p,c};}
function guard(state){if(state.canTrack===false||state.canEdit!==true||state.busy||state.active||state.project?.archived||state.dirty&&state.dirtyPart!=='tracking')throw new Error('Lưu chỉnh sửa và chờ tác vụ hiện tại hoàn tất.');return stateOf(state);}
export function trackingJobRequest(state,region,requestKey){
  const{p,c}=guard(state),box=Object.fromEntries(['x','y','width','height'].map(k=>[k,Number(region[k])/100]));
  if(Object.values(box).some(v=>!Number.isFinite(v)||v<0||v>1)||box.width<=0||box.height<=0||box.x+box.width>1||box.y+box.height>1||!requestKey)throw new Error('Vùng theo dõi cần nằm trong khung đầu video nguồn.');
  return{revision:p.revision,kind:'source_tracking',request_key:requestKey,tracking_request:{expected_version:c.version,
    analysis_id:c.snapshot.metadata.source_analysis_id,configuration:{seed_box:box,sample_interval_seconds:.2}}};
}
export function trackedCropRequest(state,record,ratio){
  const{p,c}=guard(state),value=record?.analysis;
  if(!value||value.project_id!==p.id||value.schema_version!=='native-local-subject-tracking-v1'||!tracking.test(value.tracking_id)||!sha.test(record.sha256)||value.confidence!==null||value.semantic_inference_performed!==false||value.external_provider_calls!==0||!['9:16','16:9','1:1','4:5'].includes(ratio))throw new Error('Chọn kết quả theo dõi hợp lệ của video nguồn hiện tại.');
  return{revision:p.revision,action:'reframe',payload:{expected_version:c.version,aspect_ratio:ratio,mode:'local_tracking',
    tracking_id:value.tracking_id,tracking_sha256:record.sha256}};
}
export function initializeSubjectTracking({root,api,getState,onProject,onMessage,onWorking=()=>{},onDirty=()=>{},dom=globalThis.document,newKey=()=>globalThis.crypto.randomUUID()}){
  let working=false,dirty=false,scope=null,uncertain=false;
  const add=(tag,text,parent=root)=>{const n=dom.createElement(tag);if(text!==null)n.textContent=text;parent.append(n);return n;};
  add('h3','Theo dõi vùng trong video nguồn');add('p','Xem khung đầu của video nguồn và chọn vùng có đủ chi tiết. Hệ thống dò chuyển động theo mẫu ảnh; nếu mất dấu hoặc thấy nhiều vùng giống nhau, crop giữa được giữ. Kết quả cần xem preview và duyệt lại.').className='hint';
  const video=add('video',null);video.controls=true;video.muted=true;video.preload='metadata';video.className='native-tracking-source-video';video.setAttribute('aria-label','Video nguồn để chọn vùng theo dõi');
  const fields={};for(const[k,label,value]of[['x','Trái (%)',20],['y','Trên (%)',25],['width','Rộng (%)',20],['height','Cao (%)',25]]){
    const box=add('label',label),input=add('input',null,box);input.type='number';input.min='0';input.max='100';input.step='1';input.value=String(value);fields[k]=input;
    input.addEventListener('input',()=>{dirty=true;onDirty(true);controls();});
  }
  const analyze=add('button','Theo dõi vùng đã chọn'),discard=add('button','Bỏ thay đổi vùng'),reload=add('button','Làm mới kết quả'),first=add('button','Về khung đầu'),status=add('p','');status.setAttribute('role','status');
  const choices=add('select',null);choices.setAttribute('aria-label','Kết quả theo dõi đã lưu');const ratios=add('select',null);ratios.setAttribute('aria-label','Định dạng crop');
  for(const r of['9:16','16:9','1:1','4:5']){const o=dom.createElement('option');o.textContent=o.value=r;ratios.append(o);}ratios.value='9:16';
  const ackLabel=add('label','Tôi đã xem vùng và chọn áp dụng crop; sẽ kiểm tra preview mới.');const ack=add('input',null,ackLabel);ack.type='checkbox';const apply=add('button','Lưu crop theo kết quả');
  const context=()=>{const s=getState();return JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.project?.document?.canonical_timeline?.sha256,s.canEdit]);};
  function records(){return getState().project?.document?.source_tracking_analyses??[];}
  function clear(){dirty=false;uncertain=false;ack.checked=false;choices.replaceChildren();video.removeAttribute('src');for(const[k,v]of Object.entries({x:20,y:25,width:20,height:25}))fields[k].value=String(v);onDirty(false);}
  function controls(){const s=getState(),key=context(),changed=scope!==null&&key!==scope;scope=key;if(changed)clear();
    const c=s.project?.document?.canonical_timeline;root.hidden=s.canTrack===false||c?.snapshot?.metadata?.native_auto_edit_schema!=='native-auto-edit-timeline-v1';let blocked=false;try{guard(s);}catch{blocked=true;}
    for(const f of Object.values(fields))f.disabled=working||blocked||uncertain;analyze.disabled=working||blocked||uncertain;discard.disabled=working;reload.disabled=working||dirty&&!uncertain;first.disabled=working;
    const selected=choices.value;choices.replaceChildren(...records().map(v=>{const o=dom.createElement('option');o.value=v.analysis.tracking_id;o.textContent=`${v.analysis.status==='tracked'?'Đã dò vị trí':'Cần crop giữa'} · ${v.analysis.sample_count} khung mẫu`;return o;}));
    choices.value=records().some(v=>v.analysis.tracking_id===selected)?selected:records().at(-1)?.analysis.tracking_id??'';
    const savedSeed=records().find(v=>v.analysis.tracking_id===choices.value)?.analysis?.request?.configuration?.seed_box;
    if(!dirty&&!uncertain&&savedSeed)for(const k of ['x','y','width','height'])fields[k].value=String(savedSeed[k]*100);
    choices.disabled=ratios.disabled=ack.disabled=working||blocked||dirty||uncertain;apply.disabled=working||blocked||dirty||uncertain||!choices.value||ack.checked!==true;
    const sourceId=c?.snapshot?.metadata?.source_analysis_id,analysis=s.project?.document?.auto_edit_analyses?.find(v=>v.analysis?.analysis_id===sourceId),asset=s.project?.document?.assets?.find(v=>v.id===analysis?.native_asset_id);
    if(asset&&/^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$/.test(asset.id)){const url='/api/assets/'+encodeURIComponent(asset.id)+'/file';if(video.getAttribute('src')!==url)video.setAttribute('src',url);}else video.removeAttribute('src');
    status.textContent=uncertain?'Chưa xác minh được kết quả gửi. Làm mới dự án trước khi gửi tiếp.':s.active?'Đang phân tích trên máy; có thể xem kết quả khi tác vụ hoàn tất.':records().length?'Vị trí là kết quả khớp mẫu ảnh, chưa nhận diện người/khuôn mặt. Độ tin cậy tracking đã hiệu chuẩn chưa có.':'Chưa có kết quả theo dõi.';
  }
  async function run(mode){if(working||uncertain)return;const binding=context(),s=getState(),p=s.project;let body;
    try{if(mode==='crop'&&ack.checked!==true)throw new Error('Xem và xác nhận lựa chọn crop trước.');body=mode==='job'?trackingJobRequest(s,Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.value])),newKey()):trackedCropRequest(s,records().find(v=>v.analysis.tracking_id===choices.value),ratios.value);}catch(e){onMessage(e.message,true);return;}
    working=true;onWorking();controls();try{const value=await api(`/api/projects/${p.id}/${mode==='job'?'jobs':'auto-edit/timeline'}`,body);if(context()!==binding)return;
      if(mode==='job'){if(!id.test(value?.id)||value.project_id!==p.id||value.kind!=='source_tracking')throw new Error('Chưa xác minh được tác vụ theo dõi.');const updated=await api('/api/projects/'+p.id);if(context()!==binding)return;dirty=false;onDirty(false);onProject(updated,false);onMessage('Đã xếp tác vụ theo dõi trên máy. Timeline chưa đổi.');}
      else{if(value?.id!==p.id||value.revision!==p.revision+1)throw new Error('Chưa xác minh được bản dựng mới.');dirty=false;onDirty(false);ack.checked=false;onProject(value,true);onMessage('Đã lưu đường crop. Tạo preview, xem lại và duyệt bản mới.');}
    }catch(e){if(context()===binding){uncertain=true;onMessage(e.message,true);}}finally{working=false;controls();onWorking();}}
  analyze.addEventListener('click',()=>run('job'));apply.addEventListener('click',()=>run('crop'));ack.addEventListener('change',controls);choices.addEventListener('change',()=>{ack.checked=false;controls();});
  first.addEventListener('click',()=>{video.pause?.();video.currentTime=0;});
  reload.addEventListener('click',async()=>{if(working||dirty&&!uncertain)return;const binding=context(),p=getState().project;if(!p)return;working=true;onWorking();controls();try{const value=await api('/api/projects/'+p.id);if(context()!==binding)return;if(value?.id!==p.id)throw new Error('Chưa đọc được dự án hiện tại.');dirty=false;uncertain=false;onDirty(false);onProject(value,false);}catch(e){onMessage(e.message,true);}finally{working=false;controls();onWorking();}});
  discard.addEventListener('click',()=>{if(working)return;dirty=false;onDirty(false);for(const[k,value]of Object.entries({x:20,y:25,width:20,height:25}))fields[k].value=String(value);controls();});
  controls();return{controls,isWorking:()=>working,isDirty:()=>dirty,fields,analyze,apply,ack,choices,ratios,discard,reload,video,run};
}
