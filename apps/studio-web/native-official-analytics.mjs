// Explicit receipt-bound read consent. Initialization and rendering make no requests.
import {nativeAnalyticsMetrics,nativeAnalyticsValue} from './native-analytics.mjs';
export function initializeNativeOfficialAnalytics({api,getState,getBinding,root=document,onMessage=()=>{},onWorking=()=>{},uuid=()=>crypto.randomUUID()}){
  const card=root.getElementById('native-official-analytics-card');card.replaceChildren();
  const node=(tag,text,id)=>{const n=root.createElement(tag);if(text)n.textContent=text;if(id)n.id='native-official-analytics-'+id;return n;};
  const button=(text,id,permission='read')=>{const n=node('button',text,id);n.type='button';n.className='secondary';n.dataset.vfPermission=permission;return n;};
  const labeled=(text,control)=>{const n=node('label',text);n.append(control);return n;};
  const check=(text,id)=>{const n=node('input',null,id);n.type='checkbox';n.dataset.vfPermission='manage';return[n,labeled(text,n)];};
  const config=button('Đọc cấu hình analytics','config','manage'),source=button('Đọc bằng chứng video đã chọn','source'),history=button('Đọc lịch sử analytics','history-read'),
    more=button('Đọc trang tiếp','more'),read=button('Đọc yêu cầu đã lưu','read'),create=button('Lưu lần đọc analytics','create','manage'),cancel=button('Dừng yêu cầu đọc','cancel','manage'),fresh=button('Chuẩn bị lần đọc mới','new','manage'),
    account=node('select',null,'account'),start=node('input',null,'start'),end=node('input',null,'end'),attempts=node('select',null,'attempts'),
    status=node('p','Chọn video đã có biên nhận hoàn tất trong mục xuất bản, rồi đọc bằng chứng.','status'),list=node('div',null,'history'),metrics=node('div',null,'metrics'),detail=node('pre',null,'detail');
  start.type=end.type='date';metrics.className='native-analytics-metrics';detail.className='native-publication-evidence';
  for(const count of [1,2,3]){const option=node('option',String(count));option.value=String(count);attempts.append(option);}attempts.value='1';
  const[ack,ackLabel]=check('Tôi cho phép đọc analytics của đúng video và tài khoản này; không cấp quyền xuất bản.','ack'),
    [mockAck,mockLabel]=check('Tôi hiểu đây là mô phỏng giao thức API, không phải dữ liệu khán giả thật.','mock-ack'),
    [retryAck,retryLabel]=check('Tôi cho phép số lần thử hữu hạn đã chọn khi API trả giới hạn hoặc lỗi máy chủ.','retry-ack'),
    [revenue,revenueLabel]=check('Đọc doanh thu ước tính nếu tài khoản có quyền OAuth phù hợp.','revenue');
  card.append(node('summary','Analytics từ biên nhận nền tảng'),node('p','Đọc tự động mặc định tắt. Mỗi yêu cầu có thời hạn tối đa 15 phút hoặc đến khi quyền hiện tại hết hạn. Chỉ số không có dữ liệu sẽ để trống.'),
    config,source,status,labeled('Tài khoản đọc đã cấu hình',account),labeled('Ngày đầu của báo cáo',start),labeled('Ngày cuối của báo cáo',end),revenueLabel,
    labeled('Số lần thử tối đa',attempts),ackLabel,mockLabel,retryLabel,create,history,list,more,read,cancel,fresh,metrics,detail);
  let scope='',generation=0,working=false,runtime=null,accounts=[],binding=null,rows=[],cursor=null,selected=null;const keys=new Map(),unknownKeys=new Set();
  const sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v),pubId=v=>typeof v==='string'&&/^nopu_[a-f0-9]{32}$/.test(v),syncId=v=>typeof v==='string'&&/^noas_[a-f0-9]{32}$/.test(v);
  const publication=()=>getBinding()?.publication??null;
  const context=()=>{const s=getState(),p=publication();return JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.project?.archived,s.dirty,s.active,s.canManage,p?.publication_id,p?.snapshot_sha256,p?.status]);};
  const endpoint=s=>'/api/projects/'+s.project.id+'/official-analytics';
  const sameTarget=(a,b)=>['workspace_id','profile_id','profile_version','platform','provider_key','target_account_id','credential_binding_sha256'].every(k=>a?.[k]===b?.[k]);
  const sameQuery=(a,b)=>a&&b&&Object.keys(a).length===3&&Object.keys(b).length===3&&['start_date','end_date','include_revenue'].every(k=>a[k]===b[k]);
  const chosen=()=>accounts.find(a=>a.account_ref===account.value);
  const validSource=()=>{const s=getState(),p=publication();return p&&p.status==='completed'&&pubId(p.publication_id)&&sha(p.snapshot_sha256)&&binding?.publication_id===p.publication_id
    &&binding.publication_snapshot_sha256===p.snapshot_sha256&&binding.workspace_id===s.workspace_id&&binding.project_id===s.project?.id;};
  function date(value){if(typeof value!=='string'||!/^\d{4}-\d\d-\d\d$/.test(value))throw new Error('Chọn đủ ngày báo cáo.');const time=Date.parse(value+'T00:00:00Z');
    if(!Number.isFinite(time)||new Date(time).toISOString().slice(0,10)!==value)throw new Error('Ngày báo cáo không hợp lệ.');return time;}
  function request(){const s=getState(),a=chosen(),count=Number(attempts.value),from=date(start.value),to=date(end.value);
    if(!s.canManage||!validSource()||runtime?.enabled!==true||a?.status!=='CONFIGURED'||!sameTarget(a.target,binding.target)
      ||(a.mode==='fixture')!==binding.mock||!sha(a.configuration_sha256)||ack.checked!==true||binding.mock&&mockAck.checked!==true
      ||!Number.isInteger(count)||count<1||count>3||count>1&&retryAck.checked!==true||to<from||(to-from)/86400000>365)throw new Error('Kiểm tra bằng chứng, cấu hình, ngày và xác nhận quyền đọc.');
    return{schema_version:'native-official-analytics-request-v1',publication_id:binding.publication_id,expected_publication_snapshot_sha256:binding.publication_snapshot_sha256,
      expected_receipt_sha256:binding.receipt_sha256,account_ref:a.account_ref,expected_configuration_sha256:a.configuration_sha256,
      query:{start_date:start.value,end_date:end.value,include_revenue:revenue.checked===true},acknowledged_read_only:true,
      acknowledged_protocol_mock:binding.mock,acknowledged_bounded_retries:count>1&&retryAck.checked===true,max_attempts:count,valid_for_seconds:900};}
  function controls(){const s=getState(),blocked=working||s.busy,p=publication();config.disabled=blocked||!s.canManage;source.disabled=blocked||!s.project||p?.status!=='completed';
    history.disabled=blocked||!validSource();more.disabled=blocked||!cursor||rows.length>=500;read.disabled=blocked||!selected;
    cancel.disabled=blocked||!s.canManage||!selected||['succeeded','cancelled'].includes(selected.status);fresh.disabled=blocked||!s.canManage;
    for(const input of[account,start,end,attempts,ack,mockAck,retryAck,revenue])input.disabled=blocked||!s.canManage;
    let ready=false;try{request();ready=true;}catch{}create.disabled=blocked||!ready;mockLabel.hidden=binding?.mock!==true;retryLabel.hidden=Number(attempts.value)<=1;}
  function sync(){const next=context();if(next!==scope){scope=next;generation++;runtime=null;accounts=[];binding=null;rows=[];cursor=null;selected=null;keys.clear();
      unknownKeys.clear();account.replaceChildren();list.replaceChildren();metrics.replaceChildren();detail.textContent='';for(const input of[ack,mockAck,retryAck])input.checked=false;
      status.textContent='Đọc bằng chứng của video đã chọn và cấu hình trước khi cho phép analytics.';}controls();}
  async function run(fn){sync();const s=getState();if(working||s.busy||!s.project)return;const current=context(),ticket=++generation;working=true;onWorking(true);controls();
    const accept=()=>ticket===generation&&current===context();try{await fn(s,accept);}catch(error){if(accept())onMessage(error.message,true);}finally{working=false;onWorking(false);sync();}}
  function validateSource(value,s){if(value?.schema_version!=='native-official-analytics-publication-binding-v1'||value.workspace_id!==s.workspace_id||value.project_id!==s.project.id
    ||value.publication_id!==publication()?.publication_id||value.publication_snapshot_sha256!==publication()?.snapshot_sha256||!sha(value.receipt_sha256)||typeof value.mock!=='boolean'
    ||value.mock!==publication()?.mock||value.published!==!value.mock||value.receipt_qualified!==true||value.publishing_enabled!==false||value.token_returned!==false
    ||value.target?.platform!=='youtube'||value.target?.workspace_id!==s.workspace_id||!sameTarget(value.target,publication()?.snapshot?.target)
    ||typeof value.remote_post_id!=='string'||!/^[A-Za-z0-9_-]{11}$/.test(value.remote_post_id))throw new Error('Bằng chứng video không đúng phạm vi.');return value;}
  function validateRow(value,s){if(value?.schema_version!=='native-official-analytics-sync-v1'||!syncId(value.sync_id)||value.workspace_id!==s.workspace_id||value.project_id!==s.project.id
    ||value.publication_id!==binding?.publication_id||!sha(value.snapshot_sha256)||typeof value.mock!=='boolean'||value.mock!==binding.mock||value.token_returned!==false||value.publishing_enabled!==false
    ||value.snapshot?.schema_version!=='native-official-analytics-consent-v1'||value.snapshot?.mock!==value.mock||value.snapshot?.request?.publication_id!==binding.publication_id
    ||value.snapshot?.request?.expected_publication_snapshot_sha256!==binding.publication_snapshot_sha256||value.snapshot?.request?.expected_receipt_sha256!==binding.receipt_sha256
    ||value.snapshot?.source?.receipt_sha256!==binding.receipt_sha256||value.snapshot?.source?.publication_snapshot_sha256!==binding.publication_snapshot_sha256
    ||value.snapshot?.source?.receipt_mock!==binding.mock||value.snapshot?.source?.remote_post_id!==binding.remote_post_id||!sameTarget(value.snapshot?.target,binding.target)
    ||value.snapshot?.publishing_authority!==false||value.snapshot?.recurring_authority!==false
    ||!['queued','running','retry_scheduled','succeeded','not_configured','failed','cancelled','outcome_unknown'].includes(value.status))throw new Error('Lịch sử analytics không đúng phạm vi.');
    if(value.result){const r=value.result;if(r.schema_version!=='native-official-analytics-snapshot-v1'||r.workspace_id!==s.workspace_id||r.project_id!==s.project.id||r.publication_id!==binding.publication_id
      ||r.sync_id!==value.sync_id||r.mock!==value.mock||r.external_call!==!value.mock||r.real_audience_observation!==!value.mock||r.source_kind!==(value.mock?'official_protocol_mock':'official_provider')
      ||r.snapshot_sha256!==value.snapshot_sha256||r.result_snapshot_id!==value.result_snapshot_id||r.remote_post_id!==binding.remote_post_id
      ||!sameQuery(r.evidence?.query,value.snapshot.request.query)||typeof r.collected_at!=='string'||!Number.isFinite(Date.parse(r.collected_at))
      ||r.automatic_action!==false||r.publishing_time!==null||r.publication_receipt_sha256!==binding.receipt_sha256||!r.metrics||typeof r.metrics!=='object'||Array.isArray(r.metrics))throw new Error('Quan sát không đúng phạm vi hoặc nguồn.');
      for(const metric of nativeAnalyticsMetrics){const raw=r.metrics[metric.id];if(raw!==null&&(typeof raw!=='number'||!Number.isFinite(raw)||raw<0||metric.unit==='ratio'&&raw>1))throw new Error('Chỉ số analytics không hợp lệ.');}}
    if((value.status==='succeeded')!==Boolean(value.result))throw new Error('Thiếu bằng chứng quan sát.');return value;}
  function render(){list.replaceChildren();for(const value of rows){const b=button(value.sync_id+' · '+value.status+(value.mock?' · mô phỏng API':''),'entry-'+value.sync_id);b.addEventListener('click',()=>{selected=value;render();controls();});list.append(b);}
    metrics.replaceChildren();detail.textContent=selected?JSON.stringify(selected,null,2):'';
    if(selected?.result){const r=selected.result;status.textContent=(r.mock?'Mô phỏng giao thức API · chưa quan sát khán giả thật.':'Quan sát từ API nền tảng · kiểm tra phạm vi bằng chứng.')+' Khoảng báo cáo: '+r.evidence.query.start_date+' → '+r.evidence.query.end_date+'. Thu thập: '+r.collected_at+'.';
      for(const metric of nativeAnalyticsMetrics){const box=node('div');box.append(node('strong',metric.label),node('p',nativeAnalyticsValue(r.metrics[metric.id],metric.id)));metrics.append(box);}
    }else if(selected)status.textContent=selected.status+(selected.failure_code?' · '+selected.failure_code:'')+'. Không tạo dữ liệu thay thế.';controls();}
  async function readConfig(){if(!getState().canManage)return;await run(async(s,accept)=>{const value=await api('/api/connections/official-analytics');if(!accept())return;
    if(value?.schema_version!=='native-official-analytics-capabilities-v1'||value.workspace_id!==s.workspace_id||typeof value.enabled!=='boolean'||value.default_enabled!==false||value.publishing_enabled!==false||value.token_returned!==false||value.fixture_fallback!==false||!Array.isArray(value.accounts)||value.accounts.length>50)throw new Error('Cấu hình analytics không hợp lệ.');
    for(const a of value.accounts)if(!/^npac_[a-f0-9]{32}$/.test(a.account_ref??'')||!sha(a.configuration_sha256)||a.target?.workspace_id!==s.workspace_id||a.target?.platform!=='youtube'||!['official','fixture'].includes(a.mode)||a.token_returned!==false||a.publishing_enabled!==false)throw new Error('Tài khoản analytics không hợp lệ.');
    runtime=value;accounts=value.accounts;account.replaceChildren();for(const a of accounts){const option=node('option',a.credential_alias+' · '+a.status+(a.mode==='fixture'?' · mô phỏng':''));option.value=a.account_ref;account.append(option);}
    if(accounts.length)account.value=accounts[0].account_ref;status.textContent=value.enabled?'Runtime đã cho phép đọc; cần quyền riêng cho từng yêu cầu.':'Đọc analytics tự động đang tắt.';});}
  async function readSource(){await run(async(s,accept)=>{const p=publication();if(p?.status!=='completed')throw new Error('Chọn biên nhận xuất bản hoàn tất trước.');const value=await api(endpoint(s)+'/source/'+p.publication_id);if(!accept())return;
    binding=validateSource(value,s);selected=null;rows=[];cursor=null;for(const input of[ack,mockAck,retryAck])input.checked=false;status.textContent=binding.mock?'Biên nhận mô phỏng API · chưa xuất bản thật hoặc quan sát khán giả.':'Biên nhận nền tảng đã xác nhận; chưa đọc dữ liệu khán giả.';render();});}
  async function readHistory(append=false){await run(async(s,accept)=>{if(!validSource())throw new Error('Đọc bằng chứng video trước.');const value=await api(endpoint(s)+'?limit=25&publication='+binding.publication_id+(append&&cursor?'&cursor='+encodeURIComponent(cursor):''));if(!accept())return;
    if(value?.schema_version!=='native-official-analytics-page-v1'||value.workspace_id!==s.workspace_id||value.project_id!==s.project.id||value.publication_id!==binding.publication_id||value.publishing_enabled!==false||value.token_returned!==false||!Array.isArray(value.items)||value.items.length>25||value.next_cursor!==null&&(typeof value.next_cursor!=='string'||value.next_cursor.length>2048))throw new Error('Trang lịch sử không đúng phạm vi.');
    const incoming=value.items.map(r=>validateRow(r,s));rows=append?[...rows,...incoming].slice(0,500):incoming;cursor=value.next_cursor;selected=rows.find(r=>r.sync_id===selected?.sync_id)??rows[0]??null;render();});}
  async function readStored(){await run(async(s,accept)=>{if(!selected)return;const value=await api(endpoint(s)+'/'+selected.sync_id);if(!accept())return;selected=validateRow(value,s);rows=rows.map(r=>r.sync_id===selected.sync_id?selected:r);render();});}
  async function createRead(){await run(async(s,accept)=>{const body=request(),fingerprint=JSON.stringify(body);if(!keys.has(fingerprint))keys.set(fingerprint,'native-official-analytics-'+uuid());
    unknownKeys.add(fingerprint);const value=await api(endpoint(s),{...body,request_key:keys.get(fingerprint)});if(!accept())return;selected=validateRow(value,s);unknownKeys.delete(fingerprint);rows=[selected,...rows.filter(r=>r.sync_id!==selected.sync_id)].slice(0,500);
    ack.checked=mockAck.checked=retryAck.checked=false;render();});}
  async function cancelRead(){if(!getState().canManage)return;await run(async(s,accept)=>{if(!selected)return;const value=await api(endpoint(s)+'/'+selected.sync_id+'/cancel',{expected_snapshot_sha256:selected.snapshot_sha256});if(!accept())return;
    selected=validateRow(value,s);rows=rows.map(r=>r.sync_id===selected.sync_id?selected:r);render();});}
  function prepareNew(){if(working||getState().busy||!getState().canManage)return;if(selected&&!unknownKeys.size)keys.clear();selected=null;ack.checked=mockAck.checked=retryAck.checked=false;metrics.replaceChildren();detail.textContent='';controls();}
  for(const[b,fn]of[[config,readConfig],[source,readSource],[history,()=>readHistory()],[more,()=>readHistory(true)],[read,readStored],[create,createRead],[cancel,cancelRead],[fresh,prepareNew]])b.addEventListener('click',fn);
  for(const input of[account,start,end,attempts,ack,mockAck,retryAck,revenue])input.addEventListener('change',controls);
  sync();return{readConfig,readSource,readHistory,readStored,createRead,cancelRead,prepareNew,sync,controls,isWorking:()=>working};
}
