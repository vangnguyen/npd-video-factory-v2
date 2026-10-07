/* Explicit human bridge review. No keys, enablement or service signing in browser. */
const TYPES=new Set(['trend.opportunity.detected','idea.shortlist.ready','video.project.created','video.analysis.completed','video.preview.ready',
  'video.approval.required','video.approved','video.render.completed','video.render.failed','video.publish.completed','video.publish.failed','video.analytics.updated','video.winner.detected']);
const STATUSES=new Set(['disabled','queued','running','retry_scheduled','succeeded','failed','cancelled']);
const HASH=/^[a-f0-9]{64}$/;const ID=/^bevt_[a-f0-9]{48}$/;

export function initializeNativeBridge({api,getState,onMessage,dom=document,uuid=()=>crypto.randomUUID()}){
  const root=dom.getElementById('native-bridge-card');if(!root)return null;
  const node=(tag,text)=>{const value=dom.createElement(tag);if(text!==undefined)value.textContent=text;return value;};
  const status=node('p','Chưa đọc trạng thái Agent Hub. Gửi thông báo tắt theo mặc định.');status.className='hint';
  const read=node('button','Đọc thông báo'),more=node('button','Trang tiếp'),choices=node('select'),detail=node('pre'),ack=node('input');ack.type='checkbox';
  const label=node('label');label.append(ack,node('span','Tôi chọn gửi đúng thông báo này tới đích đã hiển thị.'));
  const send=node('button','Xếp hàng thông báo đã chọn'),cancel=node('button','Dừng thông báo đang chờ'),audit=node('button','Đọc lịch sử gửi');
  for(const control of [read,more,choices,ack,send,cancel,audit]){control.dataset.workspaceControl='';if(control.tagName==='BUTTON')control.type='button';}
  root.append(status,read,choices,detail,label,send,cancel,audit,more);
  let scope='',serial=0,working=false,contract=null,rows=[],cursor=null,selected=null,selectedAudit=null;const keys=new Map();
  const current=()=>getState().workspace_id??'wsp_native_local';
  const lock=()=>working||getState().busy===true;
  function validateContract(value){if(value?.contract_version!=='agent-hub-bridge.v1'||value?.native_dto_version!=='native-bridge-operator-v1'
    ||value.workspace_id!==scope||value.live_publishing_enabled!==false||value.http_enablement_from_ui!==false
    ||typeof value.webhook_delivery_enabled!=='boolean'||!['disabled','fixture','http'].includes(value.webhook_mode)
    ||(value.webhook_delivery_enabled&&(!HASH.test(value.destination_sha256)||value.webhook_mode==='disabled')))throw new Error('Trạng thái tích hợp không hợp lệ.');return value;}
  function validateRow(row){const envelope=row?.envelope,delivery=row?.delivery;
    if(envelope?.contract_version!=='agent-hub-bridge.v1'||!ID.test(envelope?.event_id)||!TYPES.has(envelope?.event_type)
      ||envelope.payload?.workspace_id!==scope||!HASH.test(row.envelope_sha256)||delivery?.workspace_id!==scope
      ||delivery.event_id!==envelope.event_id||!STATUSES.has(delivery.status)||!['disabled','fixture','http'].includes(delivery.mode))throw new Error('Thông báo không thuộc không gian hiện tại.');return row;}
  function render(){status.textContent=!contract?'Chưa đọc trạng thái Agent Hub. Gửi thông báo tắt theo mặc định.':
    contract.webhook_delivery_enabled?`${contract.webhook_mode==='fixture'?'MÔ PHỎNG trên máy':'Gửi HTTPS đã được bật trong cấu hình'} · ${contract.destination_label??''}`:
    'Gửi thông báo đang tắt. Cấu hình và quyền bật gửi được quản lý ngoài trang này.';
    choices.replaceChildren();for(const row of rows){const option=node('option',`${row.envelope.event_type} · ${row.delivery.status} · ${row.envelope.payload.project_id??row.envelope.payload.record_id??''}`);
      option.value=row.envelope.event_id;choices.append(option);}
    choices.value=selected?.envelope.event_id??'';
    detail.textContent=selectedAudit&&selectedAudit.event_id===selected?.envelope.event_id?JSON.stringify({status:selectedAudit.delivery.status,
      attempts:selectedAudit.attempts.map(row=>({attempt:row.attempt,response_status:row.response_status,failure_code:row.failure_code,external_call:row.external_call})),
      operator_receipts:selectedAudit.operator_receipts?.length??0},null,2):selected?JSON.stringify({type:selected.envelope.event_type,occurred_at:selected.envelope.occurred_at,delivery:selected.delivery.status,
      project_id:selected.envelope.payload.project_id??null,revision:selected.envelope.payload.project_revision??null,
      mock:selected.envelope.payload.mock??null,real_audience_observation:selected.envelope.payload.real_audience_observation??null,
      actual_external_publication:selected.envelope.payload.actual_external_publication??null},null,2):'Chọn thông báo để xem trước.';
    controls();}
  function controls(){const state=getState(),blocked=lock();read.disabled=blocked;more.disabled=blocked||!cursor;choices.disabled=blocked||!rows.length;
    audit.disabled=blocked||!selected;ack.disabled=blocked||!state.canManage;
    send.disabled=blocked||!state.canManage||!contract?.webhook_delivery_enabled||!selected||selected.delivery.status!=='disabled'||!ack.checked;
    cancel.disabled=blocked||!state.canManage||!selected||!['queued','retry_scheduled'].includes(selected.delivery.status);}
  function sync(){if(current()!==scope){scope=current();serial++;contract=null;rows=[];cursor=null;selected=null;selectedAudit=null;ack.checked=false;}render();}
  async function perform(fn){sync();if(lock())return;const expected=scope,token=++serial;working=true;controls();
    try{const apply=await fn();if(token!==serial||expected!==current())return;apply?.();}
    catch(error){if(token===serial&&expected===current())onMessage(error.message,true);}
    finally{if(token===serial){working=false;render();}else{working=false;sync();}}}
  async function load(append=false){return perform(async()=>{const configuration=validateContract(await api('/api/bridge/state'));
    const page=await api(`/api/bridge/events?limit=25${append&&cursor?`&cursor=${encodeURIComponent(cursor)}`:''}`);
    if(page?.contract_version!=='agent-hub-bridge.v1'||page.workspace_id!==scope||!Array.isArray(page.items)||page.items.length>25
      ||(page.next_cursor!==null&&typeof page.next_cursor!=='string'))throw new Error('Trang thông báo không hợp lệ.');
    const values=page.items.map(validateRow);return()=>{contract=configuration;rows=append?[...rows,...values.filter(row=>!rows.some(old=>old.envelope.event_id===row.envelope.event_id))]:values;
      selected=rows.find(row=>row.envelope.event_id===selected?.envelope.event_id)??rows[0]??null;selectedAudit=null;cursor=page.next_cursor;ack.checked=false;};});}
  async function select(action){const state=getState();if(!state.canManage||!selected||lock())return;
    const row=selected,configuration=contract;if(action==='enqueue'&&(!configuration?.webhook_delivery_enabled||!ack.checked||row.delivery.status!=='disabled'))return;
    if(action==='cancel'&&!['queued','retry_scheduled'].includes(row.delivery.status))return;
    return perform(async()=>{const mode=action==='enqueue'?configuration.webhook_mode:row.delivery.mode;
      const destination=action==='enqueue'?configuration.destination_sha256:row.delivery.destination_sha256;
      if(!HASH.test(destination)||!['fixture','http'].includes(mode))throw new Error('Đích thông báo không hợp lệ.');
      const request={expected_envelope_sha256:row.envelope_sha256,expected_destination_sha256:destination,expected_mode:mode,
        fixture_acknowledged:action==='enqueue'&&mode==='fixture',http_acknowledged:action==='enqueue'&&mode==='http'};
      const signature=scope+row.envelope.event_id+action+JSON.stringify(request),key=keys.get(signature)??`native-bridge-${uuid()}`;keys.set(signature,key);
      const result=await api(`/api/bridge/events/${row.envelope.event_id}/${action}`,{...request,request_key:key});
      if(result?.contract_version!=='agent-hub-bridge.v1'||result.workspace_id!==scope||result.event_id!==row.envelope.event_id
        ||result.action!==action||result.external_call_performed!==false||result.selected_status!==(action==='enqueue'?'queued':'cancelled'))throw new Error('Biên nhận chọn thông báo không hợp lệ.');
      return()=>{ack.checked=false;contract=null;rows=[];selected=null;selectedAudit=null;cursor=null;
        onMessage(action==='cancel'?'Đã dừng thông báo đang chờ.':'Đã lưu lựa chọn. Đọc lịch sử để kiểm tra tiến trình gửi.');};});}
  async function history(){if(!selected||lock())return;const identity=selected.envelope.event_id;
    return perform(async()=>{const value=await api(`/api/bridge/events/${identity}/delivery`);
      if(value?.contract_version!=='agent-hub-bridge.v1'||value.workspace_id!==scope||value.event_id!==identity||!Array.isArray(value.attempts)
        ||value.attempts.length>5||value.real_hub_receipt_verified!==false)throw new Error('Lịch sử gửi không hợp lệ.');
      return()=>{selectedAudit=value;onMessage(value.fixture?'Lịch sử gửi mô phỏng; không phải biên nhận Agent Hub thật.':'Đã đọc lịch sử gửi. Biên nhận Hub thật chưa được chứng nhận.');};});}
  read.addEventListener('click',()=>load());more.addEventListener('click',()=>load(true));send.addEventListener('click',()=>select('enqueue'));
  cancel.addEventListener('click',()=>select('cancel'));audit.addEventListener('click',history);ack.addEventListener('change',controls);
  choices.addEventListener('change',()=>{selected=rows.find(row=>row.envelope.event_id===choices.value)??null;selectedAudit=null;ack.checked=false;render();});
  sync();return {controls,sync,load,history};
}
