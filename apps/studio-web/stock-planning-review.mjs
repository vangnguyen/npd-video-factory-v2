// Explicit review of an existing unpaid stock schedule; never starts a plan.
const hash=/^[a-f0-9]{64}$/, id=/^[A-Za-z][A-Za-z0-9_-]{3,80}$/;
const planId=/^mpl_[A-Za-z0-9_-]{4,60}$/;
const ranks={viewer:10,editor:20,reviewer:30,owner:40};
const statuses={waiting:'Đang chờ',running:'Đang tìm stock',succeeded:'Đã tìm xong',failed:'Đã dừng vì lỗi',cancelled:'Đã hủy lịch'};
const actions={scheduled:'Lưu lịch',claimed:'Nhận bước tìm kiếm',search_checkpointed:'Lưu kết quả tìm kiếm',deferred:'Lưu thời gian chờ',
  completed:'Hoàn tất tìm kiếm',failed:'Dừng vì lỗi',retry_exhausted:'Hết số lần thử',cancelled:'Hủy lịch'};
const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const integer=v=>Number.isSafeInteger(v)&&v>=0;
const epoch=v=>v===null||typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=253402300799;
const safeMessage=Symbol('stock-panel-validation');
const demand=(v,m)=>{if(!v){const error=Error(m);error[safeMessage]=true;throw error;}};
const copy=v=>structuredClone(v);
const stable=v=>JSON.stringify(v,(_key,item)=>object(item)?Object.fromEntries(Object.keys(item).sort().map(k=>[k,item[k]])):item);
const same=(a,b)=>stable(a)===stable(b);
const code=v=>v===null||typeof v==='string'&&/^[A-Z0-9_]{1,120}$/.test(v);

export function stockPlanningRole(state){
  const p=state.principal,values=[p?.platform_role,p?.workspace_roles?.['*'],p?.workspace_roles?.[state.workspaceId],
    state.workspaceSlug?p?.workspace_roles?.[`slug:${state.workspaceSlug}`]:null];
  return values.filter(v=>ranks[v]).sort((a,b)=>ranks[b]-ranks[a])[0]??null;
}
export function stockPlanningPlans(state){
  return (state.mediaPlans??[]).filter(p=>p.project_id===state.projectId&&p.workspace_id===state.workspaceId&&planId.test(p.media_plan_id)&&p.stock_planning);
}
export function validateStockPlanning(value){
  demand(object(value)&&value.schema_version==='sql-stock-planner.v1'&&Object.hasOwn(statuses,value.status)&&hash.test(value.binding_sha256)
    &&epoch(value.next_at)&&epoch(value.lease_until)&&integer(value.completed_searches)&&integer(value.total_searches)
    &&value.total_searches>0&&value.total_searches<=1000&&value.completed_searches<=value.total_searches
    &&object(value.failed_wire_cycles)&&Object.keys(value.failed_wire_cycles).length<=value.total_searches
    &&Object.values(value.failed_wire_cycles).every(v=>integer(v)&&v<=3)&&code(value.error_code)
    &&value.retryable===(value.status==='waiting')&&integer(value.provider_calls)&&value.paid_operations===0
    &&value.actual_cost_vnd===null&&value.owner_approval_inferred===false&&value.publishing_enabled===false,
  'Lịch stock thiếu dữ liệu hoặc sai giới hạn chỉ đọc.');
  return value;
}
function readFromExecution(value){
  return {schema_version:'sql-stock-planner.v1',status:value.status,binding_sha256:value.binding_sha256,
    next_at:value.next_at,lease_until:value.lease_until,completed_searches:Object.keys(value.results??{}).length,
    total_searches:value.binding?.searches?.length,failed_wire_cycles:value.failed_wire_cycles,error_code:value.error_code,
    retryable:value.status==='waiting',provider_calls:value.provider_calls,paid_operations:0,actual_cost_vnd:null,
    owner_approval_inferred:false,publishing_enabled:false};
}
export function validateStockPlan(plan,state){
  demand(object(plan)&&planId.test(plan.media_plan_id)&&plan.project_id===state.projectId&&plan.workspace_id===state.workspaceId
    &&integer(plan.version)&&plan.version>0&&hash.test(plan.fingerprint)&&plan.source_media_mutated===false
    &&plan.publish_requested===false&&plan.paid_external_call===false&&plan.publishing_blocked===true,
  'Media Plan không thuộc dự án hoặc có quyền thực thi khác.');
  validateStockPlanning(plan.stock_planning);
  const value=plan.provenance?.stock_planner_execution,provider=value?.binding?.provider;
  demand(object(value)&&value.schema_version==='sql-stock-planner.v1'&&value.binding_sha256===plan.stock_planning.binding_sha256
    &&value.binding?.schema_version==='sql-stock-planner-binding.v1'&&value.binding.paid===false
    &&object(provider)&&typeof provider.provider==='string'&&['fixture','official'].includes(provider.mode)
    &&provider.paid===false&&hash.test(provider.configuration_sha256)&&same(readFromExecution(value),plan.stock_planning),
  'Lịch stock không giữ đúng nguồn cấu hình chỉ đọc.');
  return plan;
}
function historySnapshot(value,plan){
  demand(object(value)&&value.media_plan_id===plan.media_plan_id&&value.project_id===plan.project_id&&value.workspace_id===plan.workspace_id
    &&integer(value.version)&&value.version>0&&value.fingerprint===plan.fingerprint
    &&value.paid_replay_authorized===false&&value.publishing_authorized===false,
  'Lịch sử stock thuộc nguồn khác hoặc sai quyền.');
  if(value.stock_planning!==null){
    demand(value.stock_planning?.binding_sha256===plan.stock_planning.binding_sha256
      &&same(value.stock_planning.binding,plan.provenance.stock_planner_execution.binding),'Binding trong lịch sử đã đổi.');
    validateStockPlanning(readFromExecution(value.stock_planning));
  }
}
export function validateStockHistory(history,plan,state){
  validateStockPlan(plan,state);
  demand(Array.isArray(history)&&history.length>0&&history.length<=10000,'Lịch sử stock trống hoặc vượt giới hạn xem.');
  const seen=new Set();let previous=null;
  for(const item of history){
    const evidence=item?.evidence;
    demand(object(item)&&/^spe_[a-f0-9]{32}$/.test(item.event_id)&&!seen.has(item.event_id)&&item.media_plan_id===plan.media_plan_id
      &&integer(item.version)&&item.version>1&&Object.hasOwn(actions,item.action)&&hash.test(item.sha256)
      &&evidence?.schema_version==='sql-stock-planner-event.v1'&&evidence.owner_approval_inferred===false,
    'Lịch sử stock mất phiên bản hoặc giới hạn kiểm tra.');
    historySnapshot(evidence.before,plan);historySnapshot(evidence.after,plan);
    demand(evidence.after.version===item.version&&evidence.before.version===item.version-1
      &&(!previous||item.version===previous.version+1&&same(previous.evidence.after,evidence.before)),
    'Chuỗi phiên bản stock không liền mạch.');
    seen.add(item.event_id);previous=item;
  }
  demand(previous.version===plan.version&&same(readFromExecution(previous.evidence.after.stock_planning),plan.stock_planning),
    'Các bản đọc chưa cùng phiên bản. Đọc lại trước khi thao tác.');
  return history;
}
export function stockDeadline(value){
  if(value===null)return 'Chưa có mốc thời gian';
  demand(epoch(value),'Mốc thời gian không hợp lệ.');
  const date=new Date(value*1000);
  return `${date.toISOString()} (UTC) · ${new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'short',timeStyle:'medium',hour12:false}).format(date)} (Việt Nam, UTC+07:00)`;
}
export function stockPlanningPayload(state,plan,kind,acknowledged,now){
  validateStockPlan(plan,state);
  demand(ranks[stockPlanningRole(state)]>=ranks.editor&&!state.dirty&&!state.busy,'Cần quyền biên tập; lưu bản đang sửa và chờ Studio tải xong.');
  demand(acknowledged===true,'Xác nhận thao tác cho đúng lịch đã đọc.');
  demand(kind==='retry'||kind==='cancel','Thao tác stock không hợp lệ.');
  const status=plan.stock_planning;
  if(kind==='retry')demand(status.status==='waiting'&&status.next_at!==null&&epoch(now)&&now>=status.next_at,'Lịch chưa đến mốc thử lại hoặc đang chạy/đã kết thúc.');
  else demand(['waiting','running'].includes(status.status),'Lịch đã kết thúc; không gửi yêu cầu hủy mới.');
  return {expected_version:plan.version,binding_sha256:status.binding_sha256};
}
export function stockTransitionMatches(pending,plan,history,state){
  try{
    validateStockHistory(history,plan,state);
    if(pending.scope!==scope(state)||pending.planId!==plan.media_plan_id||pending.body.binding_sha256!==plan.stock_planning.binding_sha256
      ||!same(Object.keys(pending.body).sort(),['binding_sha256','expected_version']))return false;
    const event=history.find(v=>v.version===pending.body.expected_version+1);
    return !!event&&event.action===(pending.kind==='retry'?'claimed':'cancelled')
      &&event.evidence.before.version===pending.body.expected_version
      &&event.evidence.before.stock_planning?.binding_sha256===pending.body.binding_sha256
      &&same(readFromExecution(event.evidence.before.stock_planning),pending.before)
      &&(pending.kind!=='cancel'||plan.stock_planning.status==='cancelled');
  }catch{return false;}
}
const scope=state=>JSON.stringify([state.workspaceId,state.projectId,state.principal?.subject,state.principal?.token_id,
  state.principal?.expires_at,stockPlanningRole(state)]);
const mark=plan=>JSON.stringify([plan?.media_plan_id,plan?.version,plan?.fingerprint,plan?.stock_planning?.binding_sha256]);

export function initializeStockPlanningReview({root,api,getState,onPlanUpdated=async()=>{},onMessage=()=>{},dom=globalThis.document,
  clock=()=>Date.now()/1000,storage:providedStorage}){
  if(!root)return {sync(){},reload:async()=>{},dispose(){},isPending:()=>false};
  let identity=scope(getState()),epochNumber=0,busy=false,selected='',loaded=null,loadedMark=null,capabilities=null,pending=null,storage=null,storageReady=false;
  const elements={},make=(tag,name,text)=>{const n=dom.createElement(tag);if(name){n.setAttribute('data-stock-planning-'+name,'');elements[name]=n;}if(text!==undefined)n.textContent=text;return n;};
  const label=(text,input)=>{const n=make('label');n.append(make('span',null,text),input);return n;};
  const button=(name,text,fn)=>{const n=make('button',name,text);n.type='button';n.addEventListener('click',()=>run(fn));return n;};
  const heading=make('summary','heading','Lịch tìm stock đã lưu'),body=make('div','body');
  const notice=make('p','notice','Chỉ quản lý lịch stock đã có. Không tạo Media Plan, tạo ảnh/video, duyệt quyền hay publishing ở đây.');
  const picker=make('select','plan');picker.addEventListener('change',()=>{if(busy||pending){picker.value=selected;return;}selected=picker.value;loaded=null;loadedMark=null;sync();});
  const read=button('read','Đọc trạng thái và lịch sử',reload),status=make('p','status','Chọn lịch rồi đọc trạng thái.');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  const facts=make('p','facts'),deadline=make('p','deadline'),origin=make('p','origin'),cost=make('p','cost','Chi phí thực tế: chưa có dữ liệu.');
  const acknowledgement=make('input','ack');acknowledgement.type='checkbox';acknowledgement.addEventListener('change',sync);
  const retry=button('retry','Thử lại lịch đã đến hạn',()=>submit('retry')),cancel=button('cancel','Hủy lịch đã đọc',()=>submit('cancel'));
  const reconcile=button('reconcile','Đối chiếu yêu cầu chưa rõ kết quả',reconcilePending),events=make('ol','history');
  body.append(notice,label('Media Plan có lịch stock',picker),read,origin,facts,deadline,cost,
    label('Tôi đã đọc đúng lịch và muốn thử lại hoặc hủy',acknowledgement),retry,cancel,reconcile,events,status);root.replaceChildren(heading,body);
  const announce=(message,error=false)=>{status.textContent=message;onMessage(message,error);};
  const local=()=>stockPlanningPlans(getState()).find(p=>p.media_plan_id===selected);
  const endpoint=()=>`/api/v1/projects/${getState().projectId}/media-plans/${selected}`;
  const slot=()=>`vf-stock-planning-pending.v1:${JSON.stringify([getState().workspaceId,getState().projectId,getState().principal?.subject])}`;
  function reset(){epochNumber++;selected='';loaded=null;loadedMark=null;capabilities=null;pending=null;storageReady=false;acknowledgement.checked=false;events.replaceChildren();}
  function binding(){return {epoch:epochNumber,identity:scope(getState()),selected,mark:mark(local())};}
  function still(bound){return bound.epoch===epochNumber&&bound.identity===scope(getState())&&bound.selected===selected&&bound.mark===mark(local());}
  function readStorage(){
    try{
      storage=providedStorage??globalThis.sessionStorage;demand(storage,'Bộ nhớ phiên chưa sẵn sàng.');
      const raw=storage.getItem(slot());storageReady=true;
      if(!raw)return;
      demand(raw.length<=65536,'Yêu cầu đối chiếu đã lưu quá lớn.');const value=JSON.parse(raw);
      demand(value.schema_version==='stock-planning-pending.v1'&&value.scope===scope(getState())&&['retry','cancel'].includes(value.kind)
        &&planId.test(value.planId)&&integer(value.body?.expected_version)&&value.body.expected_version>0&&hash.test(value.body.binding_sha256)
        &&same(Object.keys(value.body).sort(),['binding_sha256','expected_version']),
      'Yêu cầu đối chiếu đã lưu không đúng ngữ cảnh.');
      validateStockPlanning(value.before);demand(value.before.binding_sha256===value.body.binding_sha256,'Binding đối chiếu đã đổi.');
      pending=value;selected=value.planId;
    }catch{storageReady=false;announce('Không xác minh được bộ nhớ đối chiếu. Chỉ đọc trạng thái; chưa gửi yêu cầu mới.',true);}
  }
  function keep(value){demand(storageReady&&storage,'Cần bộ nhớ phiên để giữ đúng yêu cầu trước khi gửi.');const raw=JSON.stringify(value);
    demand(raw.length<=65536,'Yêu cầu đối chiếu vượt giới hạn bộ nhớ phiên.');storage.setItem(slot(),raw);pending=value;}
  function clear(){storage?.removeItem(slot());pending=null;acknowledgement.checked=false;}
  function sync(){
    const state=getState(),next=scope(state);if(next!==identity){reset();identity=next;status.textContent='Ngữ cảnh hoặc quyền đã đổi; đọc lại lịch stock.';}
    const plans=stockPlanningPlans(state);if(!plans.some(p=>p.media_plan_id===selected)&&!pending)selected=plans.find(p=>p.media_plan_id===state.selectedBrollPlanId)?.media_plan_id??plans[0]?.media_plan_id??'';
    picker.replaceChildren(...plans.map(p=>{const n=make('option',null,`Plan ${p.media_plan_id.slice(-8)} · bản ${p.version}`);n.value=p.media_plan_id;return n;}));picker.value=selected;
    const fresh=loaded&&loadedMark===mark(local());const enabled=!busy&&!state.busy&&!state.dirty&&ranks[stockPlanningRole(state)]>=ranks.editor&&capabilities?.human_write_enabled===true&&storageReady&&fresh;
    root.setAttribute('aria-busy',String(busy));picker.disabled=busy||!!pending;read.disabled=busy||state.busy||!selected;
    let due=false;try{const now=clock();due=fresh&&loaded.status.status==='waiting'&&loaded.status.next_at!==null&&typeof now==='number'&&epoch(now)&&now>=loaded.status.next_at;}catch{}
    retry.disabled=!enabled||!due||!acknowledgement.checked||pending&&pending.kind!=='retry';
    cancel.disabled=!enabled||!['waiting','running'].includes(loaded?.status.status)||!acknowledgement.checked||pending&&pending.kind!=='cancel';
    retry.textContent=pending?.kind==='retry'?'Gửi lại đúng yêu cầu thử lại trước':'Thử lại lịch đã đến hạn';
    cancel.textContent=pending?.kind==='cancel'?'Gửi lại đúng yêu cầu hủy trước':'Hủy lịch đã đọc';
    acknowledgement.disabled=!enabled;reconcile.hidden=!pending;reconcile.disabled=busy||state.busy||!pending;
    if(!fresh){facts.textContent='Chưa đọc lịch đúng phiên bản hiện tại.';deadline.textContent='Mốc chờ: chưa có dữ liệu.';origin.textContent='Cấu hình dịch vụ: chưa xác minh.';cost.textContent='Chi phí thực tế: chưa có dữ liệu.';events.replaceChildren();}
    if(!plans.length&&!pending)status.textContent='NOT_CONFIGURED · chưa có lịch stock được quản lý trong dự án này.';
  }
  async function run(fn){if(busy)return;sync();busy=true;const start=identity;sync();try{await fn();}catch(error){if(start===scope(getState())){
    const value=error?.detail?.error?.code;const opaque=typeof value==='string'&&/^[A-Z0-9_]{1,120}$/.test(value)?' · '+value:'';
    announce(error?.status?'Không hoàn tất thao tác stock'+opaque+'. Đọc lại hoặc đối chiếu yêu cầu.':error[safeMessage]?error.message:'Chưa xác minh được phản hồi. Giữ đúng yêu cầu và đối chiếu trước khi thao tác tiếp.',true);
  }}finally{busy=false;sync();}}
  async function fetchRead(){
    const state=getState();demand(id.test(state.projectId)&&id.test(state.workspaceId)&&stockPlanningRole(state)&&planId.test(selected),'Ngữ cảnh dự án hoặc quyền đọc chưa hợp lệ.');
    const bound=binding();const [caps,plan,value,history]=await Promise.all([api('/api/v1/capabilities'),api(endpoint()),api(endpoint()+'/stock-search'),api(endpoint()+'/stock-search/history')]);
    if(!still(bound))return null;
    validateStockPlan(plan,state);validateStockPlanning(value);demand(same(plan.stock_planning,value),'Các bản đọc chưa cùng phiên bản. Đọc lại trước khi thao tác.');validateStockHistory(history,plan,state);
    return {plan,status:value,history,capabilities:caps};
  }
  async function adopt(value){
    const start={scope:scope(getState()),epoch:epochNumber,selected};await onPlanUpdated(value.plan);
    if(start.scope!==scope(getState())||start.epoch!==epochNumber||start.selected!==selected)return;
    loaded=value;loadedMark=mark(local());capabilities=value.capabilities;render();
  }
  function render(){
    const value=loaded.status,provider=loaded.plan.provenance.stock_planner_execution.binding.provider;
    origin.textContent=provider.mode==='fixture'?'FIXTURE · phản hồi kiểm thử, chưa nghiệm thu dịch vụ stock thật.':'Cấu hình official đã lưu; chưa phải nghiệm thu nhà cung cấp hoặc quyền tài nguyên.';
    facts.textContent=`${statuses[value.status]} · ${value.completed_searches}/${value.total_searches} lần tìm đã lưu · ${value.provider_calls} wire đã gửi (gồm thử nghiệm nếu có) · ${Object.values(value.failed_wire_cycles).reduce((a,b)=>a+b,0)} vòng lỗi đã tính${value.error_code?' · '+value.error_code:''}`;
    deadline.textContent='Mốc thử lại: '+stockDeadline(value.next_at)+(value.status==='running'?' · Hạn lease: '+stockDeadline(value.lease_until):'');
    cost.textContent='Chi phí thực tế: chưa có dữ liệu · thao tác trả phí trong lịch này: 0 · không suy ra sức khỏe dịch vụ.';
    const visible=loaded.history.slice(-50);events.replaceChildren(...visible.map(e=>{const n=make('li',null,`Bản ${e.version} · ${actions[e.action]}`);return n;}));
    if(loaded.history.length>visible.length)events.prepend?.(make('li',null,`Hiển thị ${visible.length}/${loaded.history.length} mốc gần nhất.`));
  }
  async function reload(){readStorage();const value=await fetchRead();if(!value)return;await adopt(value);announce(pending?'Đã đọc trạng thái. Yêu cầu cũ chưa được xác minh; bấm đối chiếu trước.':'Đã đọc lịch và chuỗi phiên bản; chưa gửi thao tác mới.');}
  async function submit(kind){
    demand(loaded&&loadedMark===mark(local())&&capabilities?.human_write_enabled===true,'Cần đọc đúng lịch và quyền ghi trước khi gửi.');
    const body=stockPlanningPayload(getState(),loaded.plan,kind,acknowledgement.checked,clock());
    if(pending)demand(pending.kind===kind&&pending.planId===selected,'Yêu cầu chưa rõ kết quả phải giữ nguyên.');
    const operation=pending??{schema_version:'stock-planning-pending.v1',scope:scope(getState()),planId:selected,kind,body,before:copy(loaded.status)};
    keep(operation);const bound=binding();let responseReceived=false;sync();
    try{
      const plan=await api(endpoint()+'/stock-search/'+kind,{method:'POST',body:JSON.stringify(operation.body)});responseReceived=true;if(!still(bound))return;
      validateStockPlan(plan,getState());demand(plan.media_plan_id===operation.planId&&plan.stock_planning.binding_sha256===operation.body.binding_sha256,'Media Plan trả về sai yêu cầu.');
      const value=await fetchRead();if(!value)return;
      demand(stockTransitionMatches(operation,value.plan,value.history,getState()),'Yêu cầu chưa có mốc lịch sử đúng phiên bản đã gửi.');
      clear();await adopt(value);announce(kind==='retry'?'Đã đối chiếu bước thử lại; kiểm tra trạng thái đang lưu.':'Đã đối chiếu lịch hủy; không suy ra xóa tài nguyên hoặc hủy provider đang chạy.');
    }catch(error){if(!still(bound))return;if(!responseReceived&&error.status>=400&&error.status<500)clear();throw error;}
  }
  async function reconcilePending(){
    demand(pending,'Yêu cầu đối chiếu không tồn tại.');const operation=pending,value=await fetchRead();if(!value)return;
    if(stockTransitionMatches(operation,value.plan,value.history,getState())){clear();await adopt(value);announce('Đã đối chiếu chuyển trạng thái đúng phiên bản đã gửi. Kiểm tra kết quả hiện tại trước khi thao tác tiếp.');}
    else{await adopt(value);announce('Yêu cầu chưa có bằng chứng chuyển trạng thái đúng phiên bản. Giữ nguyên yêu cầu cũ; không tạo yêu cầu mới.');}
  }
  sync();return {sync,reload:()=>run(reload),dispose:()=>{reset();},isPending:()=>!!pending};
}
