// Human-reviewed storyboard decisions. This panel never submits provider jobs.
const HASH=/^[a-f0-9]{64}$/,ID=/^[a-f0-9]{32}$/,PLAN=/^nmp_[a-f0-9]{32}$/,SHOT=/^shot_[a-f0-9]{32}$/,ASSET=/^[a-f0-9]{32}\.(jpg|png|mp4|mov)$/;
const STRATEGIES={user_asset:'Tư liệu dự án',stock_video:'Video stock',stock_image:'Ảnh stock',ai_image:'Ảnh AI',ai_video:'Video AI',motion_graphic:'Đồ họa chuyển động'};
const sourceProject=project=>Boolean(project?.document?.canonical_timeline?.snapshot?.metadata?.native_auto_edit_schema);
export function validateMediaPlanPage(page,state){
  const project=state.project;
  if(page?.schema_version!=='native-storyboard-media-page-v1'||page.workspace_id!==state.workspace_id||page.project_id!==project?.id||page.revision!==project?.revision
    ||!ID.test(page.project_id)||page.external_dispatches!==0||page.paid_operations!==0||page.publishing_enabled!==false||page.real_provider_tested!==false
    ||!Array.isArray(page.items)||page.items.length>100||!Number.isInteger(page.history_versions)||page.history_versions>100||page.history_versions<page.items.length)throw new Error('Kế hoạch không khớp phiên bản dự án. Tải lại để kiểm tra.');
  for(const record of page.items){const plan=record?.plan;
    if(!HASH.test(record?.sha256??'')||typeof record.input_current!=='boolean'||plan?.schema_version!=='native-storyboard-media-plan-v1'||plan.algorithm!=='native-storyboard-media-planner-v1'
      ||plan.workspace_id!==state.workspace_id||plan.project_id!==project.id||!PLAN.test(plan.media_plan_id??'')||!Number.isInteger(plan.version)||plan.version<1
      ||!HASH.test(plan.input_sha256??'')||!HASH.test(plan.fingerprint??'')||plan.external_dispatches!==0||plan.paid_operations!==0||plan.publishing_enabled!==false
      ||plan.semantic_vision_used!==false||plan.real_provider_tested!==false||plan.recommendation_only!==true||!Array.isArray(plan.items)||plan.items.length<1||plan.items.length>20
      ||new Set(plan.items.map(item=>item.shot_id)).size!==plan.items.length)throw new Error('Bằng chứng kế hoạch chưa hợp lệ.');
    for(const item of plan.items){if(!SHOT.test(item.shot_id??'')||!Object.hasOwn(STRATEGIES,item.strategy)||!['9:16','16:9','1:1','4:5'].includes(item.target_aspect_ratio)
      ||!Number.isFinite(item.duration_seconds)||item.duration_seconds<=0||item.duration_seconds>180||item.estimated_cost_vnd!==null||item.needs_attention!==true||!Array.isArray(item.candidates)||item.candidates.length>50
      ||item.candidates.some(candidate=>!ASSET.test(candidate.asset_id??'')||!HASH.test(candidate.sha256??'')||typeof candidate.selectable!=='boolean'||candidate.confidence!==null))throw new Error('Tư liệu hoặc ước tính cần được kiểm tra.');
      if(item.selected_asset_id&&!item.candidates.some(candidate=>candidate.asset_id===item.selected_asset_id&&candidate.sha256===item.selected_asset_sha256&&candidate.selectable))throw new Error('Lựa chọn tư liệu đã thay đổi.');}
  }
  return page;
}
export function mediaPlanRequest(state,page,action,{planId,shotId,assetId,strategy,query,prompt,acknowledged=false,options={}}={}){
  if(!state.project||state.dirty||state.busy||state.active||state.project.archived||!state.canEdit||sourceProject(state.project))throw new Error('Mở dự án storyboard và lưu chỉnh sửa trước khi đổi kế hoạch.');
  validateMediaPlanPage(page,state);const base=`/api/projects/${state.project.id}/media-plans`;
  if(action==='create'){
    if(!Number.isInteger(page.timeline_version)||page.timeline_version<0||!page.input)throw new Error('Lưu lời đọc và storyboard trước khi tạo kế hoạch.');
    return {path:base,body:{revision:state.project.revision,expected_timeline_version:page.timeline_version,options}};
  }
  const record=page.items.find(value=>value.plan.media_plan_id===planId),item=record?.plan.items.find(value=>value.shot_id===shotId);
  if(!record?.input_current||!item)throw new Error('Đầu vào đã thay đổi. Tạo kế hoạch mới trước khi áp dụng.');
  const body={revision:state.project.revision,expected_plan_version:record.plan.version,expected_plan_sha256:record.sha256};
  if(action==='select'){const candidate=item.candidates.find(value=>value.asset_id===assetId);
    if(!candidate?.selectable)throw new Error('Kiểm tra quyền sử dụng tại Assets trước khi chọn tư liệu.');
    Object.assign(body,{shot_id:shotId,asset_id:assetId,expected_asset_sha256:candidate.sha256});
  }else if(action==='revise'){
    if(!Object.hasOwn(STRATEGIES,strategy)||!String(query??'').trim()||String(query).length>500||!String(prompt??'').trim()||String(prompt).length>4000)throw new Error('Nhập mô tả tìm kiếm và prompt hợp lệ.');
    Object.assign(body,{shot_id:shotId,strategy,query,generation_prompt:prompt});
  }else if(action==='apply'){
    if(!acknowledged||item.status!=='selected'||!item.selected_asset_id)throw new Error('Xem tư liệu, lưu lựa chọn và xác nhận trước khi đổi shot.');
    Object.assign(body,{acknowledged:true,shot_ids:[shotId]});
  }else throw new Error('Thao tác kế hoạch chưa được hỗ trợ.');
  return {path:`${base}/${record.plan.media_plan_id}/${action}`,body};
}

export function initializeNativeMediaPlanner({api,getState,onMessage,onWorking=()=>{},onSaved=async()=>{},dom=globalThis.document}){
  const root=dom.getElementById('native-media-planner-panel');let page=null,working=false,serial=0,binding=null;
  const context=()=>{const state=getState();return `${state.workspace_id}:${state.project?.id}:${state.project?.revision}:${sourceProject(state.project)}`;};
  const blocked=()=>{const state=getState();return working||state.busy||state.dirty||state.active||state.project?.archived;};
  function element(tag,text,parent,attributes={}){const node=dom.createElement(tag);if(text!==null)node.textContent=text;for(const [name,value] of Object.entries(attributes))node.setAttribute(name,String(value));parent.append(node);return node;}
  const summary=element('summary','Kế hoạch tư liệu theo shot',root);
  const hint=element('p','Tạo kế hoạch từ lời đọc và storyboard đã lưu. Xem lựa chọn, nguồn và quyền sử dụng trước khi áp dụng vào shot. Stock/AI được tìm hoặc tạo riêng tại Assets. Tỷ lệ chọn ở đây dành cho tư liệu; định dạng bản dựng theo template dự án.',root,{class:'hint'});
  const tools=element('div',null,root,{class:'planner-tools'});
  const refresh=element('button','Tải kế hoạch',tools,{type:'button'});
  const platform=element('select',null,tools,{'aria-label':'Nền tảng kế hoạch'});
  for(const [value,label] of Object.entries({youtube_shorts:'YouTube Shorts',youtube:'YouTube',tiktok:'TikTok',instagram_reels:'Reels Instagram',facebook_reels:'Reels Facebook',social_feed:'Bài đăng vuông'})){const option=element('option',label,platform,{value});}
  const aspect=element('select',null,tools,{'aria-label':'Tỷ lệ tư liệu'});for(const value of ['','9:16','16:9','1:1','4:5'])element('option',value||'Theo nền tảng',aspect,{value});
  const create=element('button','Tạo kế hoạch mới',tools,{type:'button'});const status=element('p','',root,{role:'status'}),body=element('div',null,root);
  function controls(){const state=getState();root.hidden=!state.project||sourceProject(state.project);refresh.disabled=blocked()||!state.project;
    create.disabled=blocked()||!state.canEdit||!page?.input;platform.disabled=aspect.disabled=blocked()||!state.canEdit;
    body.querySelectorAll('button,input,select,textarea').forEach(node=>node.disabled=blocked()||!state.canEdit||node.dataset.locked==='true');}
  function render(){body.replaceChildren();status.textContent=page?`${page.history_versions} bản lưu · ${page.items.length} kế hoạch. Chi phí thực tế và ước tính chưa rõ giữ trạng thái chưa rõ.`:'Tải kế hoạch để xem đầu vào hiện tại.';
    if(page?.unavailable_reason)status.textContent='Cần lời đọc, storyboard và tư liệu không bị thay đổi trước khi lập kế hoạch.';
    if(page?.input){const budget=page.input.budget;const config=page.input.provider_availability;
      element('p',`Ngân sách AI: ${budget.max_ai_cost_vnd??'chưa đặt'} VND · đã ghi nhận ${budget.known_paid_exposure_vnd} VND · ${budget.unknown_paid_actual_costs} khoản chưa có chi phí thực tế.`,body,{class:'hint'});
      element('p',`Stock: ${config.stock.items.filter(item=>item.status==='CONFIGURED').map(item=>`${item.provider}${item.mode==='fixture'?' · MÔ PHỎNG':''}`).join(', ')||'chưa cấu hình'} · AI: ${config.generation.items.filter(item=>item.status==='CONFIGURED').map(item=>`${item.operation}${item.mode==='fixture'?' · MÔ PHỎNG':''}`).join(', ')||'chưa cấu hình'}. Kế hoạch không thực hiện yêu cầu nhà cung cấp.`,body,{class:'hint'});}
    for(const record of page?.items??[]){const plan=record.plan,section=element('section',null,body);
      element('p',`Kế hoạch v${plan.version} · ${record.input_current?'đầu vào hiện tại':'đã áp dụng hoặc đầu vào đã đổi; cần kế hoạch mới'}`,section);
      for(const item of plan.items){const row=element('article',null,section),locked=!record.input_current;
        element('strong',`Shot ${item.ordinal} · ${STRATEGIES[item.strategy]} · ${item.target_aspect_ratio}`,row);element('p',item.visual_brief,row);
        element('p',`${item.duration_seconds.toFixed(2)} giây dự kiến; thời lượng chốt theo lời đọc đo được. Fallback: ${item.fallback.map(value=>STRATEGIES[value]).join(', ')||'cần thêm tư liệu'}.`,row,{class:'hint'});
        element('p',`Chi phí mới: chưa biết · ${item.needs_approval?'cần duyệt chi phí trước khi tạo AI':'cần xem lại tư liệu'} · ${item.status==='requires_implementation'?'cách tạo này chưa thực thi':'xếp hạng theo tên, mô tả, tag; chưa có Vision ngữ nghĩa'}`,row,{class:'hint'});
        const strategy=element('select',null,row,{'aria-label':`Chiến lược shot ${item.ordinal}`});for(const [value,label] of Object.entries(STRATEGIES))element('option',label,strategy,{value});strategy.value=item.strategy;
        const query=element('textarea',null,row,{'aria-label':`Tìm kiếm shot ${item.ordinal}`,maxlength:500});query.value=item.query;
        const prompt=element('textarea',null,row,{'aria-label':`Prompt shot ${item.ordinal}`,maxlength:4000});prompt.value=item.generation_prompt;
        const revise=element('button','Lưu cách tìm / tạo tư liệu',row,{type:'button'});revise.addEventListener('click',()=>change('revise',{planId:plan.media_plan_id,shotId:item.shot_id,strategy:strategy.value,query:query.value,prompt:prompt.value}));
        const asset=element('select',null,row,{'aria-label':`Tư liệu shot ${item.ordinal}`});element('option','Chọn tư liệu dự án',asset,{value:''});
        for(const candidate of item.candidates){const option=element('option',`${candidate.filename} · ${candidate.provenance.license??'chưa rõ quyền'}${candidate.fixture?' · fixture':''}`,asset,{value:candidate.asset_id});option.disabled=!candidate.selectable;}
        asset.value=item.selected_asset_id??'';const select=element('button','Lưu lựa chọn tư liệu',row,{type:'button'});select.addEventListener('click',()=>change('select',{planId:plan.media_plan_id,shotId:item.shot_id,assetId:asset.value}));
        const selected=item.candidates.find(value=>value.asset_id===item.selected_asset_id);if(selected){element('p',`Nguồn: ${selected.provenance.provider} · ${selected.provenance.source_reference} · quyền ${selected.provenance.actual_native_rights_status}; ${selected.provenance.rights_verification_basis}.`,row,{class:'hint'});
          const link=element('a','Xem tư liệu',row,{href:`/api/projects/${plan.project_id}/media/${selected.asset_id}`,target:'_blank',rel:'noopener'});}
        const label=element('label','Tôi đã xem tư liệu và muốn thay hình của shot này.',row,{class:'check'}),ack=element('input',null,label,{type:'checkbox'});
        const apply=element('button','Áp dụng vào shot',row,{type:'button'});apply.dataset.locked=String(locked||item.status!=='selected');apply.addEventListener('click',()=>change('apply',{planId:plan.media_plan_id,shotId:item.shot_id,acknowledged:ack.checked}));
        row.querySelectorAll('input,select,textarea,button').forEach(node=>{if(locked)node.dataset.locked='true';});
      }
    }
    controls();
  }
  function sync(){if(binding!==context()){binding=context();serial++;page=null;render();}else controls();}
  async function perform(fn){sync();if(blocked())return;working=true;onWorking();controls();try{await fn();}catch(error){onMessage(error.message,true);}finally{working=false;sync();render();onWorking();}}
  async function load(){return perform(async()=>{const state=getState(),expected=context(),token=++serial;
    const value=await api(`/api/projects/${state.project.id}/media-plans`);if(token!==serial||expected!==context())return;page=validateMediaPlanPage(value,state);});}
  async function change(action,args){const state=getState();let request;try{request=mediaPlanRequest(state,page,action,args);}catch(error){onMessage(error.message,true);return;}
    return perform(async()=>{const expected=context(),token=++serial,value=await api(request.path,{method:'POST',body:JSON.stringify(request.body)});if(expected!==context()||token!==serial)return;
      await onSaved();const current=getState();if(current.project?.id===value.project_id&&current.workspace_id===value.workspace_id&&current.project.revision===value.revision){binding=context();page=validateMediaPlanPage(value,current);onMessage(action==='apply'?'Đã đổi shot. Tạo preview và duyệt lại trước khi render.':'Đã lưu kế hoạch tư liệu.');}});}
  refresh.addEventListener('click',load);create.addEventListener('click',()=>change('create',{options:{platform:platform.value||'youtube_shorts',aspect_ratio:aspect.value||null}}));
  root.addEventListener('toggle',()=>{if(root.open&&!page&&!blocked()&&getState().project&&!sourceProject(getState().project))load();});sync();
  return {sync,controls,load,isWorking:()=>working};
}
