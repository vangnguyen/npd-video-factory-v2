// Explicit local assessments of qualified immutable observations; no provider work.
const names={view_velocity:'Tốc độ xem',retention:'Giữ chân',completion:'Hoàn thành',engagement:'Tương tác',shares:'Chia sẻ',saves:'Lưu',ctr:'CTR',follower_conversion:'Chuyển đổi người theo dõi',revenue_efficiency:'Hiệu quả doanh thu',production_cost_efficiency:'Hiệu quả chi phí'};
const labels={winner_candidate:'Ứng viên nổi bật',normal:'Thông thường',underperforming:'Hiệu quả thấp',insufficient_data:'Chưa đủ dữ liệu'};
export function initializeNativeOfficialWinners({api,getState,getBinding,root=document,onMessage=()=>{},onWorking=()=>{},uuid=()=>crypto.randomUUID()}){
  const card=root.getElementById('native-official-winners-card');card.replaceChildren();
  const node=(tag,text,id)=>{const n=root.createElement(tag);if(text)n.textContent=text;if(id)n.id='native-official-winners-'+id;return n;};
  const button=(text,id,permission='read')=>{const n=node('button',text,id);n.type='button';n.className='secondary';n.dataset.vfPermission=permission;return n;};
  const labeled=(text,n)=>{const label=node('label',text);label.append(n);return label;};
  const input=(id,min,max,step)=>{const n=node('input',null,id);n.type='number';n.min=String(min);if(max!==null)n.max=String(max);n.step=String(step);n.dataset.vfPermission='manage';return n;};
  const check=(text,id)=>{const n=node('input',null,id);n.type='checkbox';n.dataset.vfPermission='manage';return[n,labeled(text,n)];};
  const config=button('Đọc chính sách mặc định','config','manage'),source=button('Đọc bằng chứng quan sát đã chọn','source'),create=button('Lưu đánh giá','create','manage'),
    history=button('Đọc lịch sử đánh giá','history-read'),more=button('Đọc trang tiếp','more'),read=button('Đọc đánh giá đã lưu','read'),fresh=button('Chuẩn bị đánh giá mới','new','manage'),
    status=node('p','Chọn một lần đọc analytics đã hoàn tất rồi đọc bằng chứng quan sát.','status'),list=node('div',null,'history'),factors=node('div',null,'factors'),detail=node('pre',null,'detail');
  factors.className='native-analytics-metrics';detail.className='native-publication-evidence';
  const fields={minimum_peer_posts:input('minimum-peer-posts',3,100,1),maximum_peer_posts:input('maximum-peer-posts',3,100,1),minimum_views:input('minimum-views',1,null,1),
    minimum_counter_interval_hours:input('minimum-counter-interval-hours',1,720,.1),minimum_weight_coverage:input('minimum-weight-coverage',.1,1,.01),winner_threshold:input('winner-threshold',0,100,1),underperforming_threshold:input('underperforming-threshold',0,100,1)};
  const fieldNames={minimum_peer_posts:'Số video đối chiếu tối thiểu',maximum_peer_posts:'Số video đối chiếu tối đa',minimum_views:'Lượt xem tối thiểu',minimum_counter_interval_hours:'Khoảng đo bộ đếm tối thiểu (giờ)',minimum_weight_coverage:'Tỷ trọng có dữ liệu tối thiểu',winner_threshold:'Ngưỡng nổi bật',underperforming_threshold:'Ngưỡng hiệu quả thấp'};
  const weights=Object.fromEntries(Object.keys(names).map(k=>[k,input('weight-'+k,0,1,.01)])),policyBox=node('details');policyBox.append(node('summary','Chính sách và trọng số'));
  for(const[k,n]of Object.entries(fields))policyBox.append(labeled(fieldNames[k],n));for(const[k,n]of Object.entries(weights))policyBox.append(labeled(names[k],n));
  const[ack,ackLabel]=check('Tôi hiểu đây là khuyến nghị; đánh giá không thay đổi video, ngân sách hoặc xuất bản.','ack'),
    [mockAck,mockLabel]=check('Tôi hiểu dữ liệu mô phỏng API không phải phản hồi khán giả thật.','mock-ack');
  card.append(node('summary','Đánh giá video nổi bật'),node('p','Đối chiếu các video khác trong cùng phạm vi báo cáo, kênh, định dạng và ngách. Chỉ số thiếu để trống; không tự đọc API hoặc thay đổi nội dung.'),
    config,source,status,policyBox,ackLabel,mockLabel,create,history,list,more,read,fresh,factors,detail);
  let scope='',generation=0,working=false,runtime=null,binding=null,rows=[],cursor=null,selected=null;const keys=new Map(),unknownKeys=new Set();
  const sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v),id=(v,prefix)=>typeof v==='string'&&new RegExp('^'+prefix+'_[a-f0-9]{32}$').test(v),finite=v=>typeof v==='number'&&Number.isFinite(v);
  const observation=()=>getBinding()?.sync??null,endpoint=s=>'/api/projects/'+s.project.id+'/official-winners';
  const context=()=>{const s=getState(),a=observation();return JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.project?.archived,s.dirty,s.active,s.canManage,a?.sync_id,a?.snapshot_sha256,a?.result_snapshot_id,a?.status]);};
  const sameQuery=(a,b)=>a&&b&&['start_date','end_date','include_revenue'].every(k=>a[k]===b[k])&&Object.keys(a).length===3&&Object.keys(b).length===3;
  const validSource=()=>{const s=getState(),a=observation();return a?.status==='succeeded'&&id(a.sync_id,'noas')&&binding?.sync_id===a.sync_id&&binding.result_snapshot_id===a.result_snapshot_id
    &&binding.consent_sha256===a.snapshot_sha256&&binding.workspace_id===s.workspace_id&&binding.project_id===s.project?.id;};
  function validatePolicy(p){if(p?.schema_version!=='winner-channel-policy-v1'||Object.keys(p).length!==9||!p.weights||Object.keys(p.weights).length!==10)throw new Error('Chính sách không hợp lệ.');
    for(const[k,n]of Object.entries(fields)){const v=p[k];if(!finite(v)||v<Number(n.min)||n.max!==undefined&&n.max!==''&&v>Number(n.max)||['minimum_peer_posts','maximum_peer_posts','minimum_views'].includes(k)&&!Number.isSafeInteger(v))throw new Error('Chính sách không hợp lệ.');}
    if(p.minimum_peer_posts>p.maximum_peer_posts||p.underperforming_threshold>=p.winner_threshold||Object.keys(names).some(k=>!finite(p.weights[k])||p.weights[k]<0||p.weights[k]>1)||Object.values(p.weights).reduce((a,b)=>a+b,0)<=0)throw new Error('Chính sách không hợp lệ.');return p;}
  function policy(){return validatePolicy({schema_version:'winner-channel-policy-v1',...Object.fromEntries(Object.entries(fields).map(([k,n])=>[k,n.value.trim()===''?null:Number(n.value)])),weights:Object.fromEntries(Object.entries(weights).map(([k,n])=>[k,n.value.trim()===''?null:Number(n.value)]))});}
  function request(){const s=getState();if(!s.canManage||!validSource()||!runtime||ack.checked!==true||binding.mock&&mockAck.checked!==true)throw new Error('Đọc bằng chứng, chính sách và xác nhận đánh giá trước.');
    return{schema_version:'native-official-winner-request-v1',sync_id:binding.sync_id,expected_result_sha256:binding.result_sha256,policy:policy(),acknowledged_recommendation_only:true,acknowledged_protocol_mock:binding.mock};}
  function controls(){const s=getState(),blocked=working||s.busy;config.disabled=blocked||!s.canManage;source.disabled=blocked||!s.project||observation()?.status!=='succeeded';history.disabled=blocked||!validSource();
    more.disabled=blocked||!cursor||rows.length>=500;read.disabled=blocked||!selected;fresh.disabled=blocked||!s.canManage;for(const n of[...Object.values(fields),...Object.values(weights),ack,mockAck])n.disabled=blocked||!s.canManage;
    let ready=false;try{request();ready=true;}catch{}create.disabled=blocked||!ready;mockLabel.hidden=binding?.mock!==true;}
  function sync(){const next=context();if(next!==scope){scope=next;generation++;runtime=null;binding=null;rows=[];cursor=null;selected=null;keys.clear();unknownKeys.clear();list.replaceChildren();factors.replaceChildren();detail.textContent='';
    ack.checked=mockAck.checked=false;for(const n of[...Object.values(fields),...Object.values(weights)])n.value='';status.textContent='Đọc bằng chứng của quan sát đã chọn và chính sách trước khi đánh giá.';}controls();}
  async function run(fn){sync();const s=getState();if(working||s.busy||!s.project)return;const current=context(),ticket=++generation;working=true;onWorking(true);controls();const accept=()=>ticket===generation&&current===context();
    try{await fn(s,accept);}catch(error){if(accept())onMessage(error.message,true);}finally{working=false;onWorking(false);sync();}}
  function validateSource(value,s){const a=observation(),r=a?.result;if(value?.schema_version!=='native-official-winner-source-binding-v1'||value.workspace_id!==s.workspace_id||value.project_id!==s.project.id
    ||value.sync_id!==a?.sync_id||value.publication_id!==a.publication_id||value.result_snapshot_id!==a.result_snapshot_id||!sha(value.result_sha256)||value.consent_sha256!==a.snapshot_sha256
    ||value.publication_receipt_sha256!==r?.publication_receipt_sha256||value.mock!==r?.mock||typeof value.mock!=='boolean'||value.real_audience_observation!==!value.mock||value.qualified!==true
    ||value.recommendation_only!==true||value.automatic_action!==false||value.publishing_enabled!==false||value.token_returned!==false||value.scope?.workspace_id!==s.workspace_id
    ||value.scope.mock!==value.mock||value.scope.source_kind!==r.source_kind||value.scope.source_external_call!==r.external_call||!sha(value.scope.target_binding_sha256)||value.scope.platform!=='youtube'
    ||!sameQuery(value.scope.query,r.evidence?.query))throw new Error('Bằng chứng quan sát không đúng phạm vi.');return value;}
  function validateRow(value,s){const snap=value?.snapshot,a=value?.assessment,c=snap?.candidate;if(value?.schema_version!=='native-official-winner-assessment-v1'||!id(value.assessment_id,'nowa')
    ||value.workspace_id!==s.workspace_id||value.project_id!==s.project.id||value.publication_id!==binding?.publication_id||!sha(value.snapshot_sha256)||!id(value.sync_id,'noas')||!id(value.result_snapshot_id,'noam')
    ||value.mock!==binding.mock||value.real_audience_observation!==!value.mock||value.recommendation_only!==true||value.automatic_action!==false||value.external_call!==false||value.publishing_enabled!==false||value.token_returned!==false
    ||snap?.schema_version!=='native-official-winner-snapshot-v1'||snap.workspace_id!==s.workspace_id||snap.project_id!==s.project.id||snap.publication_id!==binding.publication_id||snap.sync_id!==value.sync_id||snap.result_snapshot_id!==value.result_snapshot_id
    ||snap.recommendation_only!==true||snap.automatic_action!==false||snap.publishing_enabled!==false||!sha(snap.policy_sha256)||c?.scope?.workspace_id!==s.workspace_id||c.project_id!==s.project.id||c.publication_id!==binding.publication_id
    ||c.sync_id!==value.sync_id||c.result_snapshot_id!==value.result_snapshot_id||!sha(c.result_sha256)||c.publication_receipt_sha256!==binding.publication_receipt_sha256||c.scope?.mock!==binding.mock||c.scope?.source_kind!==binding.scope.source_kind
    ||c.scope.target_binding_sha256!==binding.scope.target_binding_sha256||!sameQuery(c.scope.query,binding.scope.query)||snap.request?.sync_id!==value.sync_id||snap.request.expected_result_sha256!==c.result_sha256
    ||snap.request.acknowledged_recommendation_only!==true||snap.request.acknowledged_protocol_mock!==value.mock||!Array.isArray(snap.peers)||!Number.isInteger(value.peer_count)||value.peer_count!==snap.peers.length||value.peer_count>100
    ||typeof snap.candidate_rows_truncated!=='boolean'||!a||JSON.stringify(snap.assessment)!==JSON.stringify(a)||!Object.hasOwn(labels,a.state)||a.algorithm_version!=='winner-channel-assessment-v1'
    ||a.basis!=='matching_native_official_channel_report_scope'||a.mock!==value.mock||a.source_kind!==c.scope.source_kind||a.real_audience_observation!==!value.mock||a.external_call!==false||a.automatic_action!==false||a.publishing_enabled!==false
    ||typeof a.channel_baseline_verified!=='boolean'||value.mock&&a.channel_baseline_verified!==false||a.view_velocity_supported!==false||a.publishing_age_hours!==null||a.actual_publication_time!==null
    ||!finite(a.data_coverage)||a.data_coverage<0||a.data_coverage>1||a.state==='insufficient_data'&&a.score!==null||a.state!=='insufficient_data'&&(!finite(a.score)||a.score<0||a.score>100)
    ||!Array.isArray(a.factors)||a.factors.length!==10||new Set(a.factors.map(f=>f.factor)).size!==10||!Array.isArray(a.limitations)||!Array.isArray(a.recommendations))throw new Error('Đánh giá không đúng phạm vi hoặc nguồn.');
    validatePolicy(snap.request.policy);for(const f of a.factors){if(!Object.hasOwn(names,f.factor)||!finite(f.weight)||f.weight<0||f.weight>1||f.score!==null&&(!finite(f.score)||f.score<0||f.score>100)
      ||!f.evidence||f.evidence.policy_sha256!==snap.policy_sha256||!Number.isInteger(f.evidence.peer_count)||f.evidence.peer_count<0||f.evidence.peer_count>100
      ||!Array.isArray(f.evidence.peer_snapshot_ids)||f.evidence.peer_snapshot_ids.length!==f.evidence.peer_count||['raw_value','peer_median'].some(k=>f.evidence[k]!==null&&(!finite(f.evidence[k])||f.evidence[k]<0)))throw new Error('Yếu tố đánh giá không hợp lệ.');}
    if(value.sync_id===binding.sync_id&&(c.result_sha256!==binding.result_sha256||c.result_snapshot_id!==binding.result_snapshot_id||c.consent_sha256!==binding.consent_sha256))throw new Error('Quan sát đã thay đổi.');return value;}
  const display=v=>v===null?'Chưa có':String(v);
  function render(){list.replaceChildren();for(const value of rows){const b=button(value.assessment_id+' · '+labels[value.assessment.state]+(value.mock?' · mô phỏng API':''),'entry-'+value.assessment_id);b.addEventListener('click',()=>{selected=value;render();});list.append(b);}
    factors.replaceChildren();detail.textContent=selected?JSON.stringify(selected,null,2):'';if(selected){const a=selected.assessment;status.textContent=labels[a.state]+' · Điểm: '+display(a.score)+' · Video đối chiếu: '+selected.peer_count+' · Tỷ trọng có dữ liệu: '+a.data_coverage+
      (selected.mock?' · Mô phỏng API; chưa có phản hồi khán giả thật.':' · Quan sát từ API nền tảng.')+' Chỉ khuyến nghị.';
      for(const f of a.factors){const box=node('div');box.append(node('strong',names[f.factor]),node('p','Điểm: '+display(f.score)),node('p','Giá trị: '+display(f.evidence.raw_value)+' · Trung vị: '+display(f.evidence.peer_median)),node('p','Trọng số: '+f.weight+' · Đối chiếu: '+f.evidence.peer_count));factors.append(box);}}
    controls();}
  async function readConfig(){if(!getState().canManage)return;await run(async(s,accept)=>{const value=await api('/api/connections/official-winners');if(!accept())return;
    if(value?.schema_version!=='native-official-winner-capabilities-v1'||value.workspace_id!==s.workspace_id||!sha(value.default_policy_sha256)||value.maximum_candidate_rows!==500||value.automatic_assessment!==false||value.provider_calls_enabled!==false
      ||value.recommendation_only!==true||value.automatic_action!==false||value.publishing_enabled!==false||value.token_returned!==false)throw new Error('Cấu hình đánh giá không hợp lệ.');validatePolicy(value.default_policy);runtime=value;
    for(const[k,n]of Object.entries(fields))n.value=String(value.default_policy[k]);for(const[k,n]of Object.entries(weights))n.value=String(value.default_policy.weights[k]);});}
  async function readSource(){await run(async(s,accept)=>{if(observation()?.status!=='succeeded')throw new Error('Chọn một quan sát analytics hoàn tất trước.');const value=await api(endpoint(s)+'/source/'+observation().sync_id);if(!accept())return;
    binding=validateSource(value,s);rows=[];selected=null;cursor=null;ack.checked=mockAck.checked=false;status.textContent=binding.mock?'Quan sát mô phỏng API; không dùng làm phản hồi khán giả thật.':'Quan sát nền tảng đã xác nhận.';render();});}
  async function readHistory(append=false){await run(async(s,accept)=>{if(!validSource())throw new Error('Đọc bằng chứng quan sát trước.');const value=await api(endpoint(s)+'?limit=25&publication='+binding.publication_id+(append&&cursor?'&cursor='+encodeURIComponent(cursor):''));if(!accept())return;
    if(value?.schema_version!=='native-official-winner-page-v1'||value.workspace_id!==s.workspace_id||value.project_id!==s.project.id||value.publication_id!==binding.publication_id||value.recommendation_only!==true||value.automatic_action!==false||value.external_call!==false||value.publishing_enabled!==false||value.token_returned!==false
      ||!Array.isArray(value.items)||value.items.length>25||value.next_cursor!==null&&(typeof value.next_cursor!=='string'||value.next_cursor.length>2048))throw new Error('Trang đánh giá không đúng phạm vi.');
    const incoming=value.items.map(v=>validateRow(v,s));rows=append?[...rows,...incoming].slice(0,500):incoming;cursor=value.next_cursor;selected=rows.find(v=>v.assessment_id===selected?.assessment_id)??rows[0]??null;render();});}
  async function readStored(){await run(async(s,accept)=>{if(!selected)return;const value=await api(endpoint(s)+'/'+selected.assessment_id);if(!accept())return;selected=validateRow(value,s);rows=rows.map(v=>v.assessment_id===selected.assessment_id?selected:v);render();});}
  async function createAssessment(){await run(async(s,accept)=>{const body=request(),fingerprint=JSON.stringify(body);if(!keys.has(fingerprint))keys.set(fingerprint,'native-official-winner-'+uuid());unknownKeys.add(fingerprint);
    const value=await api(endpoint(s),{...body,request_key:keys.get(fingerprint)});if(!accept())return;selected=validateRow(value,s);unknownKeys.delete(fingerprint);rows=[selected,...rows.filter(v=>v.assessment_id!==selected.assessment_id)].slice(0,500);ack.checked=mockAck.checked=false;render();});}
  function prepareNew(){if(working||getState().busy||!getState().canManage)return;if(selected&&!unknownKeys.size)keys.clear();selected=null;ack.checked=mockAck.checked=false;factors.replaceChildren();detail.textContent='';controls();}
  for(const[b,fn]of[[config,readConfig],[source,readSource],[create,createAssessment],[history,()=>readHistory()],[more,()=>readHistory(true)],[read,readStored],[fresh,prepareNew]])b.addEventListener('click',fn);
  for(const n of[...Object.values(fields),...Object.values(weights),ack,mockAck])n.addEventListener('change',controls);
  sync();return{readConfig,readSource,createAssessment,readHistory,readStored,prepareNew,sync,controls,isWorking:()=>working};
}
