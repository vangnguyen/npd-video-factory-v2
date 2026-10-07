import {frameImageUrl} from './native-media-frames.mjs';

export const supportsNativeVision=session=>session?.capabilities?.native_vision_review===true;
export function initializeNativeVision({api,getState,root=document,onMessage=()=>{},uuid=()=>crypto.randomUUID()}){
  const $=id=>root.getElementById(id),element=(tag,text)=>{const node=root.createElement(tag);node.textContent=text;return node;};
  let scope='',sequence=0,working=false,rows=[],selected=null,cursor=null;const keys=new Map();
  const context=()=>JSON.stringify([getState().workspace_id,getState().project?.id,getState().project?.revision]);
  const base=()=>`/api/projects/${getState().project.id}/vision`;
  function controls(){const state=getState(),blocked=working||state.busy,fixture=$('native-vision-mode').value==='fixture';
    for(const id of ['native-vision-sources','native-vision-read'])$(id).disabled=blocked||!state.project;
    $('native-vision-more').disabled=blocked||!state.project||!cursor;
    $('native-vision-create').disabled=blocked||!state.canManage||state.dirty||!state.project||state.project.archived||!$('native-vision-observation').value||(fixture&&!$('native-vision-ack').checked);
    $('native-vision-process').disabled=blocked||!state.canManage||state.dirty||!selected||selected.status!=='queued';
    $('native-vision-cancel').disabled=blocked||!state.canManage||!selected||['succeeded','cancelled'].includes(selected.status);
    $('native-vision-ack').disabled=blocked||!state.canManage||!fixture;
  }
  function render(){const history=$('native-vision-history'),results=$('native-vision-results');history.replaceChildren();results.replaceChildren();
    for(const row of rows){const button=element('button',`${row.snapshot.request.provider_mode==='fixture'?'Mẫu Vision':'API thật chưa cấu hình'} · ${row.status} · ${row.created_at??''}`);
      button.type='button';button.className='secondary full';button.dataset.vfPermission='read';button.addEventListener('click',()=>{selected=row;render();});history.append(button);}
    for(const asset of selected?.result?.assets??[]){const article=element('article','');article.append(element('h3',`Mẫu ngữ nghĩa · ${asset.asset_id}`));
      article.append(element('p',`Provider mẫu: ${asset.provider} · ${asset.model}. Chưa nhận diện nội dung thật, chưa tracking; B-roll chưa suy luận.`));
      for(const frame of asset.frames){const figure=element('figure',''),image=element('img',''),source=asset.source_frame_evidence.find(item=>item.reference===frame.evidence_frame_reference);
        image.src=frameImageUrl(getState().project.id,source.frame_id);image.alt=`Khung hình nguồn tại ${frame.timestamp_seconds}s; dự đoán ngữ nghĩa là mẫu`;
        image.loading='lazy';image.width=240;image.height=160;image.style.maxWidth='100%';image.style.objectFit='contain';
        image.className='native-vision-frame';figure.append(image,element('figcaption',`${frame.timestamp_seconds}s · ${frame.caption}`));
        figure.append(element('p',`Mẫu đối tượng: ${frame.objects.map(item=>`${item.label} (${item.confidence})`).join(', ')||'chưa có'}`));
        figure.append(element('p',`Mẫu OCR: ${frame.ocr.map(item=>`${item.language}: ${item.text}`).join(' · ')||'chưa có'}`));
        figure.append(element('p',`Mẫu môi trường/hành động: ${frame.environment} / ${frame.action}. Mẫu độ tin cậy: ${frame.confidence}.`));article.append(figure);}
      article.append(element('p',`Crop cần kiểm tra: ${asset.reframe_plans.map(plan=>`${plan.aspect_ratio}: center crop`).join(' · ')}. Chưa áp dụng vào timeline.`));results.append(article);}
    $('native-vision-detail').textContent=selected?JSON.stringify(selected,null,2):'Chọn kết quả đã lưu. Chưa có suy luận Vision thật.';
    $('native-vision-status').textContent=selected?.result?'Kết quả ngữ nghĩa là mẫu kiểm thử, gắn với khung hình thật đã đo. Không dùng mẫu để tự chọn B-roll, crop hoặc QC.':'Vision thật chưa cấu hình. Khung hình/pixel đã đo vẫn được giữ riêng.';controls();
  }
  function sync(){const next=context();if(next!==scope){scope=next;sequence++;working=false;rows=[];selected=null;cursor=null;keys.clear();
    $('native-vision-observation').replaceChildren();$('native-vision-observation').value='';$('native-vision-ack').checked=false;}render();}
  function validateRow(row){const state=getState();if(row?.schema_version!=='native-vision-intent-v1'||row.workspace_id!==state.workspace_id||row.project_id!==state.project?.id
    ||!/^nvis_[a-f0-9]{32}$/.test(row.vision_id??'')||!/^[a-f0-9]{64}$/.test(row.request_fingerprint??'')||row.external_provider_calls!==0
    ||row.official_adapter_state!=='NOT_CONFIGURED'||row.real_provider_tested!==false||row.snapshot?.automatic_planning_eligible!==false
    ||!['official','fixture'].includes(row.snapshot?.request?.provider_mode))throw new Error('Kết quả Vision không khớp phạm vi.');
    const result=row.result;if((row.status==='succeeded')!==(result!==null))throw new Error('Trạng thái Vision không khớp bằng chứng.');
    if(result){if(result.schema_version!=='native-semantic-vision-fixture-v1'||result.mock!==true||result.semantic_inference_performed!==false||result.external_provider_calls!==0
      ||result.automatic_planning_eligible!==false||result.canonical_timeline_mutated!==false||!Array.isArray(result.assets)||result.assets.length>16)throw new Error('Không thể dùng kết quả mẫu như suy luận thật.');
      for(const asset of result.assets){if(asset.tracking_available!==false||asset.provenance?.semantic_model_saw_pixels!==false||!Array.isArray(asset.frames)||asset.frames.length>8
        ||!Array.isArray(asset.source_frame_evidence)||asset.frames.length!==asset.source_frame_evidence.length)throw new Error('Bằng chứng khung hình Vision không hợp lệ.');
        for(const [i,frame]of asset.frames.entries()){const source=asset.source_frame_evidence[i];if(frame.evidence_frame_reference!==source.reference||frame.timestamp_seconds!==source.timestamp_seconds)throw new Error('Khung hình ngoài bằng chứng nguồn.');frameImageUrl(state.project.id,source.frame_id);}
        if(!Array.isArray(asset.reframe_plans)||asset.reframe_plans.some(plan=>plan.fallback!=='center_crop'||plan.confidence!==0||plan.needs_attention!==true))throw new Error('Mẫu crop cần giữ trạng thái kiểm tra.');}}
    return row;
  }
  async function perform(fn){sync();if(working||getState().busy)return;const own=sequence,captured=context();working=true;controls();
    try{const apply=await fn();if(own===sequence&&captured===context())apply();}catch(error){if(own===sequence&&captured===context())onMessage(error.message,true);}
    finally{if(own===sequence&&captured===context()){working=false;render();}}
  }
  async function sources(){if(!getState().project)return;return perform(async()=>{const value=await api(`/api/projects/${getState().project.id}/media-frames`);
    if(value?.project_id!==getState().project?.id||!Array.isArray(value.observations)||value.observations.length>400)throw new Error('Khung hình nguồn không hợp lệ.');
    for(const item of value.observations)if(!/^mfo_[a-f0-9]{24}$/.test(item.observation_id??'')||item.semantic_inference_performed!==false||item.semantic_provider_status!=='NOT_CONFIGURED')throw new Error('Phép đo nguồn không hợp lệ.');
    return()=>{const select=$('native-vision-observation');select.replaceChildren();const blank=element('option','Chọn phép đo khung hình');blank.value='';select.append(blank);
      for(const item of value.observations){const option=element('option',`${item.asset_id} · ${item.frames.length} mẫu đã đo`);option.value=item.observation_id;select.append(option);}
      if(!value.observations.length)onMessage('Lưu nguồn rồi đo khung hình trước.');};});}
  async function read(more=false){if(!getState().project)return;return perform(async()=>{const value=await api(`${base()}?limit=25${more&&cursor?`&cursor=${encodeURIComponent(cursor)}`:''}`);
    if(value?.schema_version!=='native-vision-page-v1'||value.workspace_id!==getState().workspace_id||value.project_id!==getState().project?.id||value.external_provider_calls!==0
      ||!Array.isArray(value.items)||value.items.length>25||(value.next_cursor!==null&&typeof value.next_cursor!=='string'))throw new Error('Lịch sử Vision không hợp lệ.');
    const incoming=value.items.map(validateRow);return()=>{rows=more?[...rows,...incoming.filter(row=>!rows.some(old=>old.vision_id===row.vision_id))]:incoming;
      selected=rows.find(row=>row.vision_id===selected?.vision_id)??rows[0]??null;cursor=value.next_cursor;};});}
  async function execute(action){const state=getState();if(!state.canManage||!state.project||state.dirty)return onMessage('Cần quyền chủ không gian và lưu dự án trước.',true);
    return perform(async()=>{let path=base(),body;if(action==='create'){const observation=$('native-vision-observation').value,mode=$('native-vision-mode').value;
      if(!/^mfo_[a-f0-9]{24}$/.test(observation)||!['fixture','official'].includes(mode))throw new Error('Chọn phép đo và nguồn Vision.');
      if(mode==='fixture'&&!$('native-vision-ack').checked)throw new Error('Cần xác nhận đây là dự đoán mẫu.');
      const request={revision:state.project.revision,observation_ids:[observation],provider_mode:mode,fixture_acknowledged:mode==='fixture'},signature=scope+JSON.stringify(request);
      const key=keys.get(signature)??`native-vision-${uuid()}`;keys.set(signature,key);body={...request,request_key:key};
    }else{if(!selected)throw new Error('Chọn yêu cầu Vision.');path+=`/${selected.vision_id}/${action}`;body={expected_fingerprint:selected.request_fingerprint};}
      const row=validateRow(await api(path,body));return()=>{selected=row;rows=[row,...rows.filter(old=>old.vision_id!==row.vision_id)];cursor=null;$('native-vision-ack').checked=false;
        onMessage(row.status==='not_configured'?'Vision thật chưa cấu hình; không tạo kết quả mẫu thay thế.':'Đã lưu tiến trình mẫu Vision. Chưa suy luận nội dung thật.');};});}
  $('native-vision-sources').addEventListener('click',sources);$('native-vision-read').addEventListener('click',()=>read());$('native-vision-more').addEventListener('click',()=>read(true));
  for(const action of ['create','process','cancel'])$(`native-vision-${action}`).addEventListener('click',()=>execute(action));
  for(const id of ['native-vision-mode','native-vision-ack','native-vision-observation'])$(id).addEventListener('change',controls);
  sync();return{sync,controls,read,sources,execute,isWorking:()=>working};
}
