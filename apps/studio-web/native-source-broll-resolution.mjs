// Explicit resumable B-roll choices over one canonical Source timeline.
const id=/^[a-f0-9]{32}$/, rid=/^nbr_[a-f0-9]{32}$/, sha=/^[a-f0-9]{64}$/;
const positive=n=>Number.isSafeInteger(n)&&n>0;
const object=v=>v&&typeof v==='object'&&!Array.isArray(v);
const labels={queued:'Sẵn sàng xử lý bước tiếp theo',waiting_provider:'Đang chờ dịch vụ',
  recovery_required:'Cần kiểm tra kết quả chưa rõ',needs_approval:'Cần duyệt ngân sách hoặc dịch vụ',
  needs_rights_review:'Cần kiểm tra quyền sử dụng',ready:'Đã chọn tư liệu, chưa đặt vào bản dựng',
  unresolved:'Chưa tìm được tư liệu phù hợp',applied_review_required:'Đã đặt vào bản dựng, cần preview và duyệt lại'};
const tierLabels={user_asset:'Tư liệu đã tải lên',licensed_stock:'Stock có giấy phép',
  internal_library:'Thư viện nội bộ',ai_image:'Ảnh AI',ai_video:'Video AI'};
const scope=s=>JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,
  s.project?.document?.canonical_timeline?.sha256,s.canEdit,s.canManage,s.dirty,s.active,s.project?.archived]);
const source=s=>s.project?.document?.canonical_timeline?.snapshot?.metadata?.native_auto_edit_schema==='native-auto-edit-timeline-v1';
const eligible=s=>source(s)&&s.canEdit===true&&!s.dirty&&!s.busy&&!s.active&&!s.project?.archived;

export function validateSourceResolution(value,state){
  const snapshot=value?.snapshot,current=value?.state;
  if(value?.schema_version!=='native-source-broll-resolution.v1'||!rid.test(value.resolution_id)
    ||value.project_id!==state.project?.id||value.workspace_id!==state.workspace_id||!positive(value.version)
    ||!sha.test(value.snapshot_sha256)||!sha.test(value.state_sha256)||!object(snapshot)||!object(current)
    ||snapshot.resolution_id!==value.resolution_id||snapshot.project_id!==value.project_id||snapshot.workspace_id!==value.workspace_id
    ||!sha.test(snapshot.plan_sha256)||!positive(snapshot.source_revision)||!sha.test(snapshot.source?.canonical_sha256)
    ||!positive(snapshot.source?.canonical_version)||!Array.isArray(snapshot.priority)
    ||snapshot.priority.length!==5||new Set(snapshot.priority).size!==5
    ||snapshot.priority.some(tier=>!Object.hasOwn(tierLabels,tier))
    ||!object(snapshot.items)||!object(current.items)||Object.keys(current.items).length>20
    ||JSON.stringify(Object.keys(snapshot.items).sort())!==JSON.stringify(Object.keys(current.items).sort())
    ||!positive(current.expected?.revision)||!positive(current.expected?.plan_version)||!sha.test(current.expected?.plan_sha256)
    ||!sha.test(current.expected?.document_sha256)||!labels[current.status]
    ||value.automatic_video_approval!==false||value.publishing_enabled!==false||value.provider_calls_at_creation!==0)
    throw Error('Biên nhận B-roll không khớp dự án hoặc thiếu nguồn gốc.');
  return value;
}

export function validateSourceResolutionPage(value,state){
  if(value?.schema_version!=='native-source-broll-resolution-page.v1'||value.project_id!==state.project?.id
    ||value.workspace_id!==state.workspace_id||!Array.isArray(value.items)||value.items.length>100
    ||value.provider_calls!==0||value.publishing_enabled!==false)throw Error('Danh sách B-roll không khớp dự án.');
  const seen=new Set();
  for(const item of value.items){validateSourceResolution(item,state);
    if(seen.has(item.resolution_id))throw Error('Biên nhận B-roll bị trùng.');seen.add(item.resolution_id);}
  return value;
}

export function sourceResolutionCreate(state,record,itemIds,{requestKey,fixture=false,external=false}={}){
  if(!eligible(state)||!id.test(state.project?.id)||!record||!sha.test(record.sha256)
    ||!positive(record.plan?.version)||!/^mpl_[a-f0-9]{24}$/.test(record.plan.media_plan_id)
    ||!Array.isArray(itemIds)||!itemIds.length||itemIds.length>20||new Set(itemIds).size!==itemIds.length
    ||itemIds.some(item=>!record.plan.items.some(value=>value.media_plan_item_id===item)))
    throw Error('Chọn gợi ý từ kế hoạch hiện tại sau khi lưu các chỉnh sửa.');
  if(!/^[A-Za-z0-9_-]{16,100}$/.test(requestKey??'')||typeof fixture!=='boolean'||typeof external!=='boolean')
    throw Error('Xác nhận và mã yêu cầu B-roll không hợp lệ.');
  return {revision:state.project.revision,expected_timeline_version:state.project.document.canonical_timeline.version,
    media_plan_id:record.plan.media_plan_id,expected_plan_version:record.plan.version,expected_plan_sha256:record.sha256,
    item_ids:[...itemIds],fixture_acknowledged:fixture,external_acknowledged:external,request_key:requestKey};
}

export function sourceResolutionAction(state,session,action,{requestKey,acknowledged=false,replace=false}={}){
  validateSourceResolution(session,state);
  if(!eligible(state)||session.state.expected.revision!==state.project.revision
    ||session.snapshot.source.canonical_sha256!==state.project.document.canonical_timeline.sha256
    ||!['step','apply'].includes(action)||!/^[A-Za-z0-9_-]{16,100}$/.test(requestKey??''))
    throw Error('Dự án hoặc bản dựng đã thay đổi. Đọc lại trạng thái B-roll.');
  if(action==='step'&&(state.canManage!==true||['ready','applied_review_required','unresolved'].includes(session.state.status)))
    throw Error('Cần quyền quản lý để xử lý dịch vụ; kết quả chưa rõ cần kiểm tra riêng.');
  const body={revision:state.project.revision,expected_resolution_version:session.version,request_key:requestKey};
  if(action==='apply'){
    if(session.state.status!=='ready'||acknowledged!==true||typeof replace!=='boolean')throw Error('Xem tư liệu và xác nhận trước khi đặt B-roll.');
    Object.assign(body,{expected_timeline_version:state.project.document.canonical_timeline.version,acknowledged:true,replace_plan_clips:replace});
  }
  return body;
}

export function initializeSourceBrollResolution({root,api,getState,onProject,onMessage=()=>{},onWorking=()=>{},
  dom=globalThis.document,newKey=()=>globalThis.crypto.randomUUID().replaceAll('-','')}){
  let working=false,binding='',selected=null,records=[],pending=null,generation=0;
  const node=(tag,text,name)=>{const n=dom.createElement(tag);if(text)n.textContent=text;if(name)n.setAttribute('data-broll-resolution-'+name,'');return n;};
  const label=(text,input)=>{const n=node('label',text);n.append(input);return n;};
  const button=(text,name)=>{const n=node('button',text,name);n.type='button';return n;};
  const read=button('Đọc trạng thái B-roll','read'),plan=node('select',null,'plan'),items=node('div',null,'items');
  const fixture=node('input',null,'fixture'),external=node('input',null,'external'),applyAck=node('input',null,'ack'),replace=node('input',null,'replace');
  for(const n of [fixture,external,applyAck,replace])n.type='checkbox';
  const create=button('Bắt đầu tìm tư liệu cho gợi ý đã chọn','create'),choice=node('select',null,'choice');
  const step=button('Xử lý một bước / kiểm tra lại dịch vụ','step'),apply=button('Đặt tư liệu đã chọn vào bản dựng','apply');
  const status=node('p','Đọc trạng thái hoặc chọn kế hoạch B-roll đã lưu.','status'),details=node('div',null,'details');
  status.setAttribute('role','status');
  root.append(node('summary','Tìm tư liệu B-roll'),node('p','Chọn gợi ý rồi xử lý từng bước. Hệ thống ưu tiên tư liệu đã tải lên, stock có giấy phép, thư viện, ảnh AI và video AI. Tư liệu thiếu quyền sử dụng cần được kiểm tra trước khi đặt. Mỗi lần đặt cần tạo preview và duyệt bản mới.'),read,
    label('Kế hoạch đã lưu',plan),items,label('Tôi đồng ý dùng dữ liệu mô phỏng khi dịch vụ đang ở chế độ thử.',fixture),
    label('Tôi đồng ý tìm/tải stock từ dịch vụ đã cấu hình. Việc này không cấp thêm ngân sách AI.',external),create,
    label('Phiên tìm tư liệu',choice),status,details,step,
    label('Tôi đã xem tư liệu và muốn đặt vào bản dựng; sẽ xem preview và duyệt lại.',applyAck),
    label('Thay B-roll đã đặt từ các gợi ý này.',replace),apply);
  function current(){return selected&&selected.project_id===getState().project?.id&&selected.workspace_id===getState().workspace_id
    &&selected.state.expected.revision===getState().project?.revision
    &&(selected.state.status==='applied_review_required'?selected.state.applied_receipt?.canonical_sha256:selected.snapshot.source.canonical_sha256)
      ===getState().project?.document?.canonical_timeline?.sha256;}
  function show(){
    details.replaceChildren();
    status.textContent=selected?(labels[selected.state.status]+(current()?'':' · phiên cũ, đọc lại hoặc bắt đầu từ kế hoạch hiện tại')):'Chưa chọn phiên tìm tư liệu.';
    step.textContent=selected?.state.status==='recovery_required'?'Kiểm tra lại kết quả đã xử lý tại Assets':'Xử lý một bước / kiểm tra lại dịch vụ';
    if(selected?.state.status==='recovery_required')details.append(node('p','Kiểm tra và xử lý tác vụ chưa rõ trong Assets trước, rồi đọc lại kết quả tại đây. Bước kiểm tra này không gửi lại yêu cầu tạo tư liệu.'));
    if(selected)for(const [identity,item] of Object.entries(selected.state.items)){
      const frozen=selected.snapshot.items[identity],row=node('p');
      const phase=labels[item.phase]??({choose:'Chờ lựa chọn',resolved:'Đã chọn',stock_search:'Chờ tìm stock',stock_download:'Chờ tải stock',generation:'Chờ tạo tư liệu'}[item.phase]??'Xem bằng chứng chi tiết');
      row.textContent=(frozen.broll?.broll_intent??frozen.label??'Gợi ý B-roll')+' · '+phase;
      if(item.selected_asset_id)row.append(node('span',' · '+item.selected_asset_id));
      for(const attempt of item.attempts??[])row.append(node('span',' · '+(tierLabels[attempt.tier]??'Dịch vụ')+': '+(attempt.status==='NOT_CONFIGURED'?'chưa cấu hình':'đã ghi nhận trong bằng chứng')));
      details.append(row);
    }
  }
  function planItems(){items.replaceChildren();const record=records.find(r=>r.plan.media_plan_id===plan.value);
    for(const item of record?.plan.items??[]){const check=node('input',null,'item');check.type='checkbox';check.value=item.media_plan_item_id;
      items.append(label((item.broll?.broll_intent??'Gợi ý')+' · '+(item.broll?.search_query??''),check));}
    fixture.checked=external.checked=false;controls();}
  function controls(){const s=getState(),can=eligible(s)&&!working;
    root.hidden=!source(s);read.disabled=!s.project||s.dirty||s.busy||working;
    for(const el of [plan,fixture,external,create])el.disabled=!can||!records.length;
    items.querySelectorAll('input').forEach(el=>el.disabled=!can);
    choice.disabled=working||s.busy||pending!==null;applyAck.disabled=replace.disabled=!can||!current()||selected?.state.status!=='ready';
    step.disabled=!can||!current()||s.canManage!==true||['ready','applied_review_required','unresolved'].includes(selected?.state.status);
    apply.disabled=!can||!current()||selected?.state.status!=='ready'||!applyAck.checked;
  }
  function sync(){const next=scope(getState());if(next!==binding){binding=next;generation++;
    selected=null;pending=null;choice.replaceChildren();applyAck.checked=replace.checked=fixture.checked=external.checked=false;
    records=[];plan.replaceChildren();items.replaceChildren();
    const latest=new Map();for(const record of getState().project?.document?.source_broll_plans??[])
      if(!latest.has(record.plan.media_plan_id)||record.plan.version>latest.get(record.plan.media_plan_id).plan.version)latest.set(record.plan.media_plan_id,record);
    records=[...latest.values()];for(const record of records){const option=node('option','Kế hoạch v'+record.plan.version);option.value=record.plan.media_plan_id;plan.append(option);}
    if(records.length)plan.value=records[0].plan.media_plan_id;planItems();show();}
    controls();}
  function install(page){validateSourceResolutionPage(page,getState());choice.replaceChildren();
    for(const session of page.items){const option=node('option',session.resolution_id.slice(0,12)+' · '+labels[session.state.status]);option.value=session.resolution_id;choice.append(option);}
    const values=page.items;selected=values.find(v=>v.resolution_id===selected?.resolution_id)??values.at(-1)??null;
    if(selected)choice.value=selected.resolution_id;
    choice.onchange=()=>{if(pending){choice.value=selected?.resolution_id??'';onMessage('Thử lại yêu cầu đang chờ trong phiên đã chọn trước khi đổi phiên.',true);return;}
      selected=values.find(v=>v.resolution_id===choice.value)??null;applyAck.checked=replace.checked=false;show();controls();};show();}
  async function run(action){sync();const s=getState();if(working||s.busy||s.dirty||!s.project) return;
    const expected=scope(s),token=++generation;working=true;controls();onWorking(true);
    const accept=()=>token===generation&&scope(getState())===expected;
    try{await action(s,accept);}catch(error){if(accept())onMessage(error.message,true);}
    finally{working=false;controls();onWorking(false);}
  }
  async function write(s,accept,action,body){const project=s.project,base='/api/projects/'+project.id+'/auto-edit/broll-resolutions';
    const identity=action==='create'?null:selected.resolution_id;
    if(!pending)pending={action,resolution_id:identity,path:action==='create'?base:base+'/'+identity+'/'+action,body};
    if(pending.action!==action||pending.resolution_id!==identity)throw Error('Thử lại thao tác đang chờ trong đúng phiên trước khi bắt đầu thao tác khác.');
    const response=await api(pending.path,pending.body);if(!accept())return;
    if(action==='create')validateSourceResolution(response,s);
    else if(response.schema_version!=='native-source-broll-resolution-transition.v1'||response.project_id!==project.id
      ||response.workspace_id!==s.workspace_id||response.resolution_id!==selected.resolution_id
      ||!positive(response.version)||!sha.test(response.state_sha256)||response.automatic_video_approval!==false
      ||response.publishing_enabled!==false||response.source_media_mutated!==false||!positive(response.expected?.revision))throw Error('Biên nhận thao tác B-roll không hợp lệ.');
    const fresh=await api('/api/projects/'+project.id);if(!accept())return;
    const expectedRevision=action==='create'?response.state.expected.revision:response.expected.revision;
    if(fresh.id!==project.id||fresh.revision!==expectedRevision
      ||(action==='apply'?fresh.document?.canonical_timeline?.sha256!==response.canonical_sha256
        :fresh.document?.canonical_timeline?.sha256!==project.document.canonical_timeline.sha256))throw Error('Biên nhận và phiên bản dự án không khớp. Đọc lại dự án.');
    pending=null;onProject(fresh,true);sync();
    const latestScope=scope(getState()),page=await api(base);
    if(scope(getState())===latestScope)install(page);
    onMessage(action==='apply'?'Đã đặt B-roll. Tạo preview, kiểm tra tư liệu và duyệt bản mới.':'Đã ghi nhận bước B-roll; tiếp tục hoặc đọc trạng thái dịch vụ.');
  }
  read.addEventListener('click',()=>void run(async(s,accept)=>{const page=await api('/api/projects/'+s.project.id+'/auto-edit/broll-resolutions');if(accept())install(page);}));
  create.addEventListener('click',()=>void run(async(s,accept)=>{const record=records.find(r=>r.plan.media_plan_id===plan.value);
    const selectedIds=[...items.querySelectorAll('input')].filter(el=>el.checked).map(el=>el.value);
    const body=pending?.action==='create'?pending.body:sourceResolutionCreate(s,record,selectedIds,{requestKey:newKey(),fixture:fixture.checked,external:external.checked});
    await write(s,accept,'create',body);}));
  for(const [button,action] of [[step,'step'],[apply,'apply']])button.addEventListener('click',()=>void run(async(s,accept)=>{
    const body=pending?.action===action?pending.body:sourceResolutionAction(s,selected,action,{requestKey:newKey(),acknowledged:applyAck.checked,replace:replace.checked});
    await write(s,accept,action,body);}));
  plan.addEventListener('change',planItems);applyAck.addEventListener('change',controls);sync();
  return {sync,controls,isWorking:()=>working};
}
