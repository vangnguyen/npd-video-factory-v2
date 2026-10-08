const ID=/^[a-f0-9]{32}$/,HASH=/^[a-f0-9]{64}$/;
const LABELS={generate:'Ảnh từ mô tả',image_to_image:'Ảnh từ ảnh tham chiếu',variation:'Biến thể ảnh',inpaint:'Sửa vùng bằng mask',upscale:'Phóng lớn ảnh',
  text_to_video:'Video từ mô tả',image_to_video:'Video từ ảnh',reference_assisted:'Video với ảnh tham chiếu'};
const STATES={not_configured:'Chưa cấu hình',queued:'Đang chờ',running:'Đang xử lý',succeeded:'Tư liệu sẵn sàng để kiểm tra',failed:'Không hoàn tất',
  cancelled:'Đã hủy',recovery_required:'Cần đối soát kết quả',needs_approval:'Cần Owner duyệt chi phí'};
export const supportsNativeGeneration=session=>session?.capabilities?.native_generation_media===true;

export function initializeNativeGeneration({api,getState,dom=document,onMessage=()=>{},onSaved=async()=>{},onWorking=()=>{},uuid=()=>crypto.randomUUID(),
  setTimer=(fn,time)=>setTimeout(fn,time),clearTimer=id=>clearTimeout(id)}){
  const root=dom.getElementById('native-generation-panel'),node=(tag,text)=>{const value=dom.createElement(tag);value.textContent=text??'';return value;};
  const status=node('p','Đọc cấu hình để chọn cách tạo tư liệu.'),read=node('button','Đọc khả năng & lịch sử'),operation=node('select'),prompt=node('textarea'),negative=node('textarea');
  prompt.maxLength=4000;prompt.rows=3;negative.maxLength=2000;negative.rows=2;
  const aspect=node('select'),seed=node('input'),duration=node('input'),references=node('select'),mask=node('select'),scale=node('select');references.multiple=true;
  seed.type=duration.type='number';seed.value='1';seed.min='0';seed.max='2147483647';seed.step='1';duration.value='5';duration.min='.1';duration.max='30';duration.step='.1';
  function options(control,rows){control.replaceChildren();for(const [value,text]of rows){const option=node('option',text);option.value=value;control.append(option);}}
  options(aspect,[['9:16','Dọc 9:16'],['16:9','Ngang 16:9'],['1:1','Vuông 1:1'],['4:5','Dọc 4:5']]);aspect.value='9:16';options(scale,[['2','2 lần'],['4','4 lần']]);scale.value='2';
  const ack=node('input'),ackLabel=node('label'),ackText=node('span','Tôi chọn gửi yêu cầu tạo tư liệu và sẽ kiểm tra kết quả, chi phí, quyền sử dụng.');ack.type='checkbox';ackLabel.className='check';ackLabel.append(ack,ackText);
  const create=node('button','Tạo tư liệu'),jobs=node('select'),summary=node('p'),preview=node('div'),cancel=node('button','Yêu cầu hủy'),recover=node('button','Đối soát yêu cầu cũ');
  const recoveryAck=node('input'),recoveryLabel=node('label');recoveryAck.type='checkbox';recoveryLabel.className='check';recoveryLabel.append(recoveryAck,node('span','Tôi chọn đối soát yêu cầu cũ; thao tác này không gửi lại yêu cầu tạo mới.'));
  const importAck=node('input'),importLabel=node('label');importAck.type='checkbox';importLabel.className='check';importLabel.append(importAck,node('span','Tôi đã xem tư liệu và chọn thêm vào dự án. Quyền sử dụng vẫn cần kiểm tra; dự án cần được duyệt lại.'));
  const attach=node('button','Thêm vào dự án'),more=node('button','Đọc thêm lịch sử');preview.className='native-generation-preview';status.className=summary.className='hint';
  function label(text,control){const wrapper=node('label',text);wrapper.append(control);return wrapper;}
  const durationLabel=label('Độ dài video (giây)',duration),maskLabel=label('Mask đen trắng đã tải lên',mask),scaleLabel=label('Mức phóng lớn',scale);
  root.append(status,read,label('Cách tạo',operation),label('Mô tả tư liệu',prompt),label('Nội dung cần tránh',negative),label('Khung hình',aspect),label('Seed',seed),
    label('Ảnh tham chiếu trong dự án',references),durationLabel,maskLabel,scaleLabel,ackLabel,create,label('Yêu cầu đã lưu',jobs),summary,preview,cancel,recoveryLabel,recover,importLabel,attach,more);
  for(const control of [read,operation,prompt,negative,aspect,seed,duration,references,mask,scale,ack,create,jobs,cancel,recoveryAck,recover,importAck,attach,more]){
    control.dataset.workspaceControl='';if(control.tagName==='BUTTON')control.type='button';}
  for(const control of [operation,prompt,negative,aspect,seed,duration,references,mask,scale,ack,create,cancel,recoveryAck,recover,importAck,attach])control.dataset.vfPermission='edit';
  let scope='',serial=0,working=false,configuration=null,rows=[],selected=null,timer=null,polls=0,limit=25,hasMore=false;const keys=new Map();
  const context=()=>JSON.stringify([getState().workspace_id,getState().project?.id,getState().project?.revision]);
  const blocked=()=>working||getState().busy;
  const editable=()=>!blocked()&&getState().canEdit&&getState().project&&!getState().dirty&&!getState().active&&!getState().project.archived;
  const spec=()=>configuration?.items.find(item=>`${item.modality}:${item.operation}`===operation.value);
  function controls(){const edit=editable(),state=getState();read.disabled=blocked()||!state.project;more.disabled=blocked()||!hasMore||limit>=200;
    for(const control of [operation,prompt,negative,aspect,seed,references,mask,scale,duration,ack])control.disabled=!edit;
    create.disabled=!edit||spec()?.status!=='CONFIGURED'||!ack.checked||!prompt.value.trim();jobs.disabled=blocked()||!rows.length;
    cancel.disabled=!edit||!selected||!['queued','running','recovery_required','needs_approval'].includes(selected.status)||selected.cancel_requested;
    recoveryAck.disabled=!edit||selected?.status!=='recovery_required'||!selected.dispatch_started||selected.recovery_count>=3;recover.disabled=recoveryAck.disabled||!recoveryAck.checked;
    importAck.disabled=!edit||selected?.status!=='succeeded'||Boolean(selected.attachment);attach.disabled=importAck.disabled||!importAck.checked;
  }
  function render(){const selectedSpec=spec(),state=getState();status.textContent=!configuration?'Đọc cấu hình để chọn cách tạo tư liệu.':selectedSpec?.mode==='fixture'?
    'MÔ PHỎNG: chỉ dùng tư liệu kiểm thử, chưa phải kết quả từ mô hình AI thật.':selectedSpec?.status==='CONFIGURED'?
    'Đã cấu hình. Kết quả vẫn cần kiểm tra chất lượng, chi phí và quyền sử dụng.':'Chưa cấu hình nhà cung cấp hoặc workflow; các chức năng khác vẫn sử dụng được.';
    ackText.textContent=selectedSpec?.mode==='fixture'?'Tôi hiểu đây là media kiểm thử mô phỏng, không phải kết quả AI từ nhà cung cấp thật.':'Tôi chọn gửi yêu cầu tạo tư liệu và sẽ kiểm tra kết quả, chi phí, quyền sử dụng.';
    durationLabel.hidden=selectedSpec?.modality!=='video';maskLabel.hidden=selectedSpec?.operation!=='inpaint';scaleLabel.hidden=selectedSpec?.operation!=='upscale';
    jobs.replaceChildren();for(const row of rows){const choice=node('option',`${LABELS[row.snapshot.request.parameters.operation??row.snapshot.request.parameters.mode]} · ${STATES[row.status]}${row.attachment?' · đã thêm':''}`);choice.value=row.generation_id;jobs.append(choice);}jobs.value=selected?.generation_id??'';
    summary.textContent=selected?`${STATES[selected.status]}${selected.cancel_requested&&selected.status!=='cancelled'?' · đang chờ xác nhận hủy':''}${selected.snapshot.selection.mode==='fixture'?' · MÔ PHỎNG':''}${selected.result?' · Quyền sử dụng chưa xác minh · chi phí thực tế chưa biết':''}`:'Chọn yêu cầu để theo dõi và kiểm tra tư liệu.';
    preview.replaceChildren();if(selected?.status==='succeeded'){const asset=selected.result.asset,media=node(asset.kind==='image'?'img':'video');
      media.src=`/api/projects/${state.project.id}/generation/${selected.generation_id}/file`;if(asset.kind==='image')media.alt='Tư liệu AI cần kiểm tra quyền sử dụng';else{media.controls=true;media.preload='metadata';}
      preview.append(node('p',`${asset.width} × ${asset.height}${asset.kind==='video'?` · ${asset.duration_seconds} giây`:''} · chưa được cấp quyền xuất bản`),media);}
    controls();}
  function sync(){if(context()!==scope){scope=context();serial++;configuration=null;rows=[];selected=null;hasMore=false;limit=25;polls=0;operation.replaceChildren();references.replaceChildren();mask.replaceChildren();
      ack.checked=recoveryAck.checked=importAck.checked=false;prompt.value=negative.value='';clearTimer(timer);timer=null;}render();}
  function validateRow(row,state){const selection=row?.snapshot?.selection;if(row?.schema_version!=='native-generation-job-v1'||!ID.test(row.generation_id??'')||row.workspace_id!==state.workspace_id||row.project_id!==state.project.id
    ||!Object.hasOwn(STATES,row.status)||!HASH.test(row.request_fingerprint??'')||row.worker_wired!==true||row.publish_enabled!==false||row.automatic_attachment!==false||row.real_provider_tested!==false
    ||row.snapshot.workspace_id!==state.workspace_id||row.snapshot.project_id!==state.project.id||row.snapshot.generation_id!==row.generation_id||!['fixture','official'].includes(selection?.mode)
    ||!['comfyui-image','comfyui-video'].includes(selection.provider))throw new Error('Yêu cầu tạo tư liệu ngoài dự án hiện tại.');
    if(row.status==='succeeded'){const value=row.result,asset=value?.asset;if(value?.generation_id!==row.generation_id||value.workspace_id!==state.workspace_id||value.project_id!==state.project.id
      ||value.rights_status!=='unknown'||value.production_eligible!==false||value.actual_cost_vnd!==null||value.real_provider_tested!==false||value.automatic_attachment!==false||value.canonical_timeline_mutated!==false
      ||value.fixture!==(selection.mode==='fixture')||!['image','video'].includes(asset?.kind)||!HASH.test(asset.sha256??'')||asset.rights_status!=='unknown'||asset.production_eligible!==false||asset.needs_attention!==true
      ||asset.explicit_fixture!==(selection.mode==='fixture')||asset.generation_provenance?.native_generation_id!==row.generation_id)throw new Error('Kết quả cần giữ bằng chứng và trạng thái kiểm tra.');}
    else if(row.result!==null)throw new Error('Yêu cầu chưa hoàn tất không có tư liệu sẵn sàng.');
    if(row.attachment&&(row.attachment.generation_id!==row.generation_id||row.attachment.project_id!==state.project.id||row.attachment.workspace_id!==state.workspace_id
      ||row.attachment.asset_sha256!==row.result?.asset.sha256||row.attachment.approval_invalidated!==true||row.attachment.rights_independently_verified!==false))throw new Error('Biên nhận thêm tư liệu không hợp lệ.');return row;}
  function choose(row){selected=row;ack.checked=recoveryAck.checked=importAck.checked=false;polls=0;render();}
  function polling(){clearTimer(timer);timer=null;if(!selected||!['queued','running'].includes(selected.status)||polls>=80)return;
    const expected=context(),identity=selected.generation_id;timer=setTimer(async()=>{if(expected!==context())return;polls++;
      await perform(async()=>{const state=getState(),row=validateRow(await api(`/api/projects/${state.project.id}/generation/${identity}`),state);return()=>{rows=rows.map(old=>old.generation_id===identity?row:old);selected=row;};});},5000);}
  async function perform(fn){sync();if(blocked())return;const token=++serial,expected=context();working=true;onWorking();controls();
    try{const apply=await fn();if(token===serial&&expected===context())await apply?.();}catch(error){if(token===serial&&expected===context())onMessage(error.message,true);}
    finally{working=false;if(expected!==context())sync();else render();onWorking();polling();}}
  async function load(moreRows=false){const state=getState();if(!state.project)return;const nextLimit=moreRows?Math.min(200,limit+25):limit;
    return perform(async()=>{const [config,page]=await Promise.all([api('/api/generation/providers'),api(`/api/projects/${state.project.id}/generation?limit=${nextLimit}`)]);
      if(config?.schema_version!=='native-generation-providers-v1'||config.workspace_id!==state.workspace_id||config.ui_enablement_supported!==false||config.automatic_attachment!==false||config.publish_enabled!==false||config.real_provider_tested!==false
        ||!Array.isArray(config.items)||config.items.length!==8||new Set(config.items.map(item=>`${item.modality}:${item.operation}`)).size!==8
        ||config.items.some(item=>!['image','video'].includes(item.modality)||!Object.hasOwn(LABELS,item.operation)||!['fixture','official'].includes(item.mode)||!['CONFIGURED','NOT_CONFIGURED'].includes(item.status)
          ||(item.workflow_sha256!==null&&!HASH.test(item.workflow_sha256??''))||(item.status==='CONFIGURED'&&(!HASH.test(item.provider_configuration_sha256??'')||!HASH.test(item.workflow_sha256??''))))
        ||page?.schema_version!=='native-generation-page-v1'||page.workspace_id!==state.workspace_id||page.project_id!==state.project.id||page.worker_wired!==true||page.publish_enabled!==false||page.automatic_attachment!==false
        ||!Array.isArray(page.items)||page.items.length>nextLimit||!Number.isInteger(page.total)||page.total<page.items.length||page.total>200||typeof page.has_more!=='boolean')throw new Error('Khả năng hoặc lịch sử tạo tư liệu không hợp lệ.');
      const incoming=page.items.map(row=>validateRow(row,state));return()=>{configuration=config;limit=nextLimit;hasMore=page.has_more;rows=incoming;
        const previous=operation.value;options(operation,config.items.map(item=>[`${item.modality}:${item.operation}`,`${LABELS[item.operation]}${item.status==='NOT_CONFIGURED'?' · chưa cấu hình':''}`]));operation.value=previous||`${config.items[0].modality}:${config.items[0].operation}`;
        const assets=(state.project.document?.assets??[]).filter(asset=>asset.kind==='image'&&/^[a-f0-9]{32}\.(jpg|png)$/.test(asset.id)&&HASH.test(asset.sha256??''));
        options(references,assets.map(asset=>[asset.id,asset.filename??asset.id]));options(mask,[['','Chọn mask'],...assets.map(asset=>[asset.id,asset.filename??asset.id])]);mask.value='';
        choose(rows.find(row=>row.generation_id===selected?.generation_id)??rows[0]??null);};});}
  async function execute(action){const state=getState();if(!editable()||!state.project)return;
    if(action==='create'&&(spec()?.status!=='CONFIGURED'||!ack.checked||!prompt.value.trim()))return;
    if(action==='import'&&(!importAck.checked||selected?.status!=='succeeded'||selected.attachment))return;
    if(action==='recover'&&(!recoveryAck.checked||selected?.status!=='recovery_required'||!selected.dispatch_started||selected.recovery_count>=3))return;
    if(action==='cancel'&&(!selected||!['queued','running','recovery_required','needs_approval'].includes(selected.status)||selected.cancel_requested))return;
    const own=selected,selectedSpec=spec();return perform(async()=>{let path=`/api/projects/${state.project.id}/generation`,request;
      if(action==='create'){const assets=state.project.document?.assets??[],byId=new Map(assets.map(asset=>[asset.id,asset])),chosen=Array.from(references.selectedOptions??[]).map(option=>byId.get(option.value));
        if(chosen.some(asset=>!asset)||chosen.length>10)throw new Error('Chọn tối đa 10 ảnh có trong dự án.');
        const seedValue=Number(seed.value);if(!seed.value||!Number.isInteger(seedValue)||seedValue<0||seedValue>2147483647)throw new Error('Seed cần là số nguyên từ 0 đến 2147483647.');
        const parameters={modality:selectedSpec.modality,prompt:prompt.value.trim(),negative_prompt:negative.value,aspect_ratio:aspect.value,seed:seedValue,references:chosen.map(asset=>({asset_id:asset.id,asset_sha256:asset.sha256}))};
        if(selectedSpec.modality==='image'){parameters.operation=selectedSpec.operation;if(selectedSpec.operation==='inpaint'){const asset=byId.get(mask.value);if(!asset)throw new Error('Chọn mask đã tải lên trong dự án.');parameters.mask={asset_id:asset.id,asset_sha256:asset.sha256};}
          if(selectedSpec.operation==='upscale')parameters.upscale_factor=Number(scale.value);}
        else{parameters.mode=selectedSpec.operation;parameters.duration_seconds=Number(duration.value);if(!duration.value||!Number.isFinite(parameters.duration_seconds)||parameters.duration_seconds<=0||parameters.duration_seconds>30)throw new Error('Độ dài video cần lớn hơn 0 và không quá 30 giây.');}
        if(!['generate','text_to_video'].includes(selectedSpec.operation)&&!chosen.length)throw new Error('Chọn ảnh tham chiếu trong dự án.');
        request={revision:state.project.revision,parameters,external_acknowledged:selectedSpec.mode==='official',fixture_acknowledged:selectedSpec.mode==='fixture'};
      }else{path+=`/${own.generation_id}/${action}`;request={expected_fingerprint:own.request_fingerprint};
        if(action==='recover')request.acknowledged=true;if(action==='import')Object.assign(request,{revision:state.project.revision,expected_asset_sha256:own.result.asset.sha256,acknowledged:true});}
      if(action!=='cancel'){const signature=scope+action+JSON.stringify(request),key=keys.get(signature)??`native-generation-${uuid()}`;keys.set(signature,key);request.request_key=key;}
      const value=await api(path,request);
      if(action==='import'){if(value?.schema_version!=='native-generation-import-v1'||value.project_id!==state.project.id||value.workspace_id!==state.workspace_id||value.generation_id!==own.generation_id
        ||value.asset_sha256!==own.result.asset.sha256||value.revision!==state.project.revision+1||value.approval_invalidated!==true||value.rights_independently_verified!==false||value.canonical_timeline_auto_edited!==false||value.external_calls!==0)throw new Error('Biên nhận thêm tư liệu không hợp lệ.');
        return async()=>{await onSaved(value);onMessage('Đã thêm tư liệu. Chọn vị trí trong shot/timeline, kiểm tra quyền sử dụng và duyệt lại dự án.');};}
      if(action==='recover'){if(value?.schema_version!=='native-generation-reconciliation-request-v1'||value.generation_id!==own.generation_id||value.project_id!==state.project.id||value.workspace_id!==state.workspace_id
        ||value.mode!=='reconcile'||value.generation_submission_authorized!==false||value.external_calls!==0)throw new Error('Biên nhận đối soát không hợp lệ.');
        const row=validateRow(await api(`/api/projects/${state.project.id}/generation/${own.generation_id}`),state);return()=>{rows=rows.map(old=>old.generation_id===row.generation_id?row:old);choose(row);onMessage('Đã lưu yêu cầu đối soát kết quả cũ.');};}
      const row=validateRow(value,state);return()=>{rows=[row,...rows.filter(old=>old.generation_id!==row.generation_id)];choose(row);onMessage(action==='cancel'?'Đã ghi nhận yêu cầu hủy; chờ xác nhận trạng thái.':'Đã lưu yêu cầu tạo tư liệu. Kiểm tra kết quả trước khi thêm vào dự án.');};});}
  read.addEventListener('click',()=>load());more.addEventListener('click',()=>load(true));create.addEventListener('click',()=>execute('create'));cancel.addEventListener('click',()=>execute('cancel'));
  recover.addEventListener('click',()=>execute('recover'));attach.addEventListener('click',()=>execute('import'));jobs.addEventListener('change',()=>{choose(rows.find(row=>row.generation_id===jobs.value)??null);polling();});
  operation.addEventListener('change',()=>{ack.checked=false;render();});for(const control of [ack,recoveryAck,importAck,prompt])control.addEventListener(control===prompt?'input':'change',controls);
  sync();return {sync,controls,load,execute,isWorking:()=>working,close:()=>{clearTimer(timer);serial++;}};
}
