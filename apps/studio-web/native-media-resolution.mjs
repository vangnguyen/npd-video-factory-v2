// Explicit storyboard jobs use existing stock/generation workers and imports.
const HASH=/^[a-f0-9]{64}$/,ID=/^[a-f0-9]{32}$/,PLAN=/^nmp_[a-f0-9]{32}$/,SHOT=/^shot_[a-f0-9]{32}$/,RES=/^nmr_[a-f0-9]{32}$/,STOCK=/^nstk_[a-f0-9]{32}$/,ASSET=/^[a-f0-9]{32}\.(jpg|png|mp4|mov)$/;
const source=state=>Boolean(state.project?.document?.canonical_timeline?.snapshot?.metadata?.native_auto_edit_schema);
export function validateResolution(value,state){
  const b=value?.binding,c=value?.child;
  if(!b||!c||b.schema_version!=='native-storyboard-media-resolution-v1'||!RES.test(b.resolution_id??'')||!PLAN.test(b.media_plan_id??'')||!SHOT.test(b.shot_id??'')
    ||b.workspace_id!==state.workspace_id||b.project_id!==state.project?.id||!ID.test(b.project_id)||!Number.isInteger(b.plan_version)||b.plan_version<1
    ||!Number.isInteger(b.revision)||b.revision<1||b.revision>state.project.revision||[value.binding_sha256,b.plan_sha256,b.plan_fingerprint,b.input_sha256,b.document_sha256,b.request_fingerprint,b.child_fingerprint,b.child_request_sha256].some(sha=>!HASH.test(sha??''))
    ||!['generation','stock_search','stock_download'].includes(b.child_kind)||!(b.child_kind==='generation'?ID:STOCK).test(b.child_id??'')
    ||b.automatic_attachment!==false||b.automatic_timeline_apply!==false||b.provider_calls_at_creation!==0||b.paid_operations_at_creation!==0
    ||value.automatic_attachment!==false||value.automatic_timeline_apply!==false||value.real_provider_acceptance_complete!==false
    ||c.schema_version!==(b.child_kind==='generation'?'native-generation-job-v1':'native-stock-job-v1')||c.workspace_id!==state.workspace_id||c.project_id!==b.project_id||c.request_fingerprint!==b.child_fingerprint||c.snapshot?.document_sha256!==b.document_sha256||c.snapshot?.request?.revision!==b.revision
    ||(b.child_kind==='generation'?c.generation_id:c.stock_id)!==b.child_id||c.automatic_attachment!==false)throw new Error('Yêu cầu tư liệu không khớp dự án hoặc bằng chứng đã thay đổi.');
  const asset=c.result?.asset;if(asset&&(!ASSET.test(asset.id??'')||!HASH.test(asset.sha256??'')))throw new Error('Tư liệu kết quả chưa hợp lệ.');
  if(b.child_kind==='stock_search'&&c.result){if(!Array.isArray(c.result.candidates)||c.result.candidates.length>20||!HASH.test(c.result_sha256??'')
    ||c.result.candidates.some(candidate=>!/^smc_[a-f0-9]{24}$/.test(candidate.candidate_id??'')||!HASH.test(c.result.candidate_sha256?.[candidate.candidate_id]??'')))throw new Error('Kết quả tìm kiếm cần được đọc lại.');}
  return value;
}
export function resolutionRequest(state,page,operation,args,key){
  if(!state.project||source(state)||state.dirty||state.busy||state.active||state.project.archived||!state.canEdit)throw new Error('Lưu dự án storyboard trước khi yêu cầu hoặc nhập tư liệu.');
  if(!/^[A-Za-z0-9_-]{16,100}$/.test(key??''))throw new Error('Mã yêu cầu chưa hợp lệ.');
  const base=`/api/projects/${state.project.id}`;
  if(operation==='import'){
    const value=validateResolution(args.resolution,state),b=value.binding,c=value.child,asset=c.result?.asset;
    if(b.child_kind==='stock_search'||c.status!=='succeeded'||!asset||c.attachment||!args.acknowledged)throw new Error('Xem kết quả và xác nhận trước khi thêm vào dự án.');
    return {path:`${base}/media-resolutions/${b.resolution_id}/import`,body:{revision:state.project.revision,expected_binding_sha256:value.binding_sha256,
      expected_fingerprint:c.request_fingerprint,expected_asset_sha256:asset.sha256,acknowledged:true,request_key:key}};
  }
  if(page?.workspace_id!==state.workspace_id||page.project_id!==state.project.id||page.revision!==state.project.revision)throw new Error('Tải kế hoạch hiện tại trước khi yêu cầu tư liệu.');
  const record=page.items?.find(row=>row.plan.media_plan_id===args.planId),item=record?.plan.items.find(row=>row.shot_id===args.shotId);
  if(!record?.input_current||!HASH.test(record.sha256??'')||!item||item.selected_asset_id||!args.acknowledged)throw new Error('Kiểm tra kế hoạch hiện tại và xác nhận gửi yêu cầu.');
  const common={revision:state.project.revision,expected_plan_version:record.plan.version,expected_plan_sha256:record.sha256,request_key:key};let spec;
  if(operation==='generate'){
    if(!['ai_image','ai_video'].includes(item.strategy)||item.new_generation_budget_blocked?.includes(item.strategy))throw new Error('Cần giá ước tính trước khi tạo AI trong ngân sách giới hạn.');
    if(!Number.isInteger(args.seed??1)||(args.seed??1)<0||(args.seed??1)>2147483647||item.strategy==='ai_video'&&item.duration_seconds>30)throw new Error('Seed hoặc thời lượng video chưa được hỗ trợ.');
    spec=page.input?.provider_availability.generation.items.find(row=>row.modality===(item.strategy==='ai_image'?'image':'video')&&row.operation===(item.strategy==='ai_image'?'generate':'text_to_video'));
    Object.assign(common,{shot_id:item.shot_id,seed:args.seed??1});
  }else if(operation==='search'){
    if(!state.canManage||!['stock_image','stock_video'].includes(item.strategy))throw new Error('Owner chọn tìm stock theo kế hoạch.');
    spec=page.input?.provider_availability.stock.items.find(row=>row.provider===args.provider);Object.assign(common,{shot_id:item.shot_id,provider:args.provider});
  }else if(operation==='download'){
    if(!state.canManage||!['stock_image','stock_video'].includes(item.strategy))throw new Error('Owner chọn tải stock theo kế hoạch.');
    const parent=validateResolution(args.resolution,state),b=parent.binding,c=parent.child;
    if(b.child_kind!=='stock_search'||b.media_plan_id!==args.planId||b.plan_sha256!==record.sha256||b.shot_id!==args.shotId||c.status!=='succeeded')throw new Error('Tìm lại stock cho kế hoạch hiện tại.');
    const candidate=c.result.candidates.find(row=>row.candidate_id===args.candidateId);if(!candidate)throw new Error('Chọn kết quả stock đã lưu.');
    spec=page.input?.provider_availability.stock.items.find(row=>row.provider===c.snapshot.provider);
    Object.assign(common,{parent_resolution_id:b.resolution_id,expected_result_sha256:c.result_sha256,candidate_id:candidate.candidate_id,expected_candidate_sha256:c.result.candidate_sha256[candidate.candidate_id]});
  }else throw new Error('Thao tác tư liệu chưa được hỗ trợ.');
  if(spec?.status!=='CONFIGURED'||!['official','fixture'].includes(spec.mode))throw new Error('Nhà cung cấp chưa được cấu hình.');
  Object.assign(common,{external_acknowledged:spec.mode==='official',fixture_acknowledged:spec.mode==='fixture'});
  return {path:`${base}/media-plans/${record.plan.media_plan_id}/resolve/${operation}`,body:common};
}

export function initializeNativeMediaResolution({api,getState,getPlanPage,dom,root,onMessage,onWorking=()=>{},onSaved=async()=>{},uuid=()=>crypto.randomUUID()}){
  let rows=[],working=false,scope='',serial=0,pending=null;const sceneControls=[];
  const context=()=>JSON.stringify([getState().workspace_id,getState().project?.id,getState().project?.revision]);
  const blocked=()=>working||getState().busy||getState().dirty||getState().active||getState().project?.archived;
  function el(tag,text,parent,attrs={}){const node=dom.createElement(tag);if(text!==null)node.textContent=text;for(const [name,value] of Object.entries(attrs))node.setAttribute(name,String(value));parent.append(node);return node;}
  const history=el('section',null,root),read=el('button','Đọc lịch sử tư liệu theo shot',history,{type:'button'}),retry=el('button','Đối soát phản hồi chưa nhận',history,{type:'button'}),status=el('p','',history,{role:'status'}),body=el('div',null,history);
  function controls(){const state=getState();read.disabled=working||state.busy||!state.project;retry.hidden=!pending;retry.disabled=blocked()||!pending||!state.canEdit||(pending.operation==='search'||pending.operation==='download')&&!state.canManage;
    for(const node of sceneControls)node.disabled=blocked()||!state.canEdit||node.dataset.locked==='true'||node.dataset.manage==='true'&&!state.canManage;
    body.querySelectorAll('button,input,select').forEach(node=>node.disabled=blocked()||!state.canEdit||node.dataset.locked==='true'||node.dataset.manage==='true'&&!state.canManage);}
  function show(){body.replaceChildren();status.textContent=`${rows.length} yêu cầu đã lưu. Thêm tư liệu không tự đổi shot; kiểm tra quyền và tạo kế hoạch mới sau khi nhập.`;
    for(const value of rows){const b=value.binding,c=value.child,row=el('article',null,body);el('strong',`${b.child_kind} · ${c.status}`,row);el('p',`Kế hoạch v${b.plan_version} · shot ${b.shot_id} · ${b.resolution_id}`,row,{class:'hint'});
      if(c.result?.mock||c.snapshot.selection?.mode==='fixture'||c.snapshot.provider_mode==='fixture')el('p','MÔ PHỎNG: chưa phải kiểm thử nhà cung cấp thật hoặc xác minh quyền.',row,{class:'hint'});
      if(b.child_kind==='stock_search'&&c.status==='succeeded')for(const candidate of c.result.candidates){
        el('p',`${candidate.provider_asset_id} · ${candidate.license} · ${candidate.media_type}`,row);
        const label=el('label','Tôi chọn tải kết quả stock này để xem lại.',row,{class:'check'}),ack=el('input',null,label,{type:'checkbox'}),download=el('button','Tải stock đã chọn',row,{type:'button'});
        ack.dataset.manage=download.dataset.manage='true';const record=getPlanPage()?.items.find(item=>item.plan.media_plan_id===b.media_plan_id);
        download.dataset.locked=String(!record?.input_current||record.sha256!==b.plan_sha256);download.addEventListener('click',()=>change('download',{planId:b.media_plan_id,shotId:b.shot_id,resolution:value,candidateId:candidate.candidate_id,acknowledged:ack.checked}));
      }
      const asset=c.result?.asset;if(asset){el('p',`Quyền: ${asset.rights_status} · chi phí thực tế: ${c.result.actual_cost_vnd??'chưa rõ'}`,row,{class:'hint'});
        el('a','Xem tư liệu kết quả',row,{href:`/api/projects/${b.project_id}/${b.child_kind==='generation'?'generation':'stock'}/${b.child_id}/file`,target:'_blank',rel:'noopener'});
        if(c.attachment)el('p','Đã thêm vào dự án. Kiểm tra quyền, tạo lại kế hoạch và chọn tư liệu trước khi áp dụng.',row);
        else{const label=el('label','Tôi đã xem kết quả và chọn thêm vào dự án; cần kiểm tra quyền và duyệt lại.',row,{class:'check'}),ack=el('input',null,label,{type:'checkbox'}),attach=el('button','Thêm kết quả vào dự án',row,{type:'button'});
          attach.addEventListener('click',()=>change('import',{resolution:value,acknowledged:ack.checked}));}
      }
      if(c.failure_code)el('p',`Trạng thái: ${c.failure_code}. Xem Assets để hủy hoặc đối soát yêu cầu cũ.`,row,{class:'hint'});
    }controls();}
  function sync(){if(scope!==context()){scope=context();serial++;rows=[];pending=null;show();}else controls();}
  async function perform(fn){sync();if(blocked())return;working=true;onWorking();controls();try{await fn();}catch(error){onMessage(error.message,true);}finally{working=false;sync();show();onWorking();}}
  async function load(){return perform(async()=>{const state=getState(),expected=context(),token=++serial,value=await api(`/api/projects/${state.project.id}/media-resolutions`);
    if(expected!==context()||token!==serial)return;
    if(value?.schema_version!=='native-storyboard-media-resolutions-page-v1'||value.workspace_id!==state.workspace_id||value.project_id!==state.project.id||!Array.isArray(value.items)||value.items.length>200||value.automatic_attachment!==false||value.automatic_timeline_apply!==false)throw new Error('Lịch sử tư liệu không khớp dự án.');
    rows=value.items.map(row=>validateResolution(row,state));});}
  async function send(intent){return perform(async()=>{const expected=context(),token=++serial;pending=intent;const value=await api(intent.request.path,{method:'POST',body:JSON.stringify(intent.request.body)});
    if(expected!==context()||token!==serial)return;validateResolution(value,getState());pending=null;
    if(intent.operation==='import'){await onSaved();onMessage('Đã thêm tư liệu. Kiểm tra quyền và tạo kế hoạch mới trước khi đổi shot.');}
    else{rows=[...rows.filter(row=>row.binding.resolution_id!==value.binding.resolution_id),value];onMessage(value.child.status==='not_configured'?'Nhà cung cấp chưa cấu hình; chưa gửi ra ngoài.':'Đã lưu yêu cầu tư liệu theo shot. Đọc lịch sử để kiểm tra kết quả.');}});}
  async function change(operation,args){sync();if(pending){onMessage('Đối soát phản hồi hoặc đọc lịch sử trước khi tạo yêu cầu khác.',true);return;}let request;
    try{request=resolutionRequest(getState(),getPlanPage(),operation,args,'storyboard-'+uuid());}catch(error){onMessage(error.message,true);return;}return send({operation,request});}
  function scene(record,item,parent,{isDraftChanged=()=>false}={}){if(!['ai_image','ai_video','stock_image','stock_video'].includes(item.strategy)||item.selected_asset_id)return;
    const submit=(operation,args)=>{if(isDraftChanged()){onMessage('Lưu cách tìm / tạo tư liệu trước khi gửi yêu cầu theo shot.',true);return;}return change(operation,args);};
    const fixture=item.strategy.startsWith('ai_')?getPlanPage()?.input?.provider_availability.generation.items.find(row=>row.modality===(item.strategy==='ai_image'?'image':'video')&&row.operation===(item.strategy==='ai_image'?'generate':'text_to_video'))?.mode==='fixture':false;
    const label=el('label',fixture?'MÔ PHỎNG: tôi chọn tạo tư liệu để kiểm thử.':'Tôi chọn gửi yêu cầu tư liệu và sẽ kiểm tra chi phí, kết quả, quyền sử dụng.',parent,{class:'check'}),ack=el('input',null,label,{type:'checkbox'});
    const args={planId:record.plan.media_plan_id,shotId:item.shot_id};let input,button;
    if(item.strategy.startsWith('ai_')){input=el('input',null,parent,{type:'number',min:0,max:2147483647,step:1,'aria-label':`Seed shot ${item.ordinal}`});input.value='1';button=el('button','Tạo AI theo shot',parent,{type:'button'});
      button.addEventListener('click',()=>submit('generate',{...args,seed:Number(input.value),acknowledged:ack.checked}));button.dataset.locked=String(!record.input_current||item.new_generation_budget_blocked?.includes(item.strategy)||item.strategy==='ai_video'&&item.duration_seconds>30);
    }else{input=el('select',null,parent,{'aria-label':`Nhà cung cấp stock shot ${item.ordinal}`});for(const provider of getPlanPage()?.input?.provider_availability.stock.items??[])if(provider.status==='CONFIGURED')el('option',`${provider.provider}${provider.mode==='fixture'?' · MÔ PHỎNG':''}`,input,{value:provider.provider});
      input.dataset.manage=ack.dataset.manage='true';button=el('button','Tìm stock theo shot',parent,{type:'button'});button.dataset.manage='true';button.dataset.locked=String(!record.input_current);button.addEventListener('click',()=>submit('search',{...args,provider:input.value,acknowledged:ack.checked}));}
    sceneControls.push(ack,input,button);controls();}
  read.addEventListener('click',load);retry.addEventListener('click',()=>{if(pending&&!blocked())send(pending);});sync();
  return {sync,controls,load,scene,refresh:show,clearSceneControls:()=>{sceneControls.length=0;},isWorking:()=>working};
}
