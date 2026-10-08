// Separately approved finite queue plans; no auto-load, auto-approval or secret inputs.
export function initializeNativeOfficialPublicationQueue({api,getState,getBinding,root=document,onMessage=()=>{},onWorking=()=>{},uuid=()=>crypto.randomUUID()}){
  const card=root.getElementById('native-official-publication-queue-card');card.replaceChildren();
  const node=(tag,text,id)=>{const n=root.createElement(tag);if(text)n.textContent=text;if(id)n.id='native-official-queue-'+id;return n;};
  const button=(text,id)=>{const b=node('button',text,id);b.type='button';return b;},label=(text,n)=>{const l=node('label',text);l.append(n);return l;};
  const config=button('Đọc trạng thái hàng đợi','config'),history=button('Đọc lịch sử kế hoạch','history-read'),more=button('Đọc trang tiếp','more'),read=button('Đọc kế hoạch đã lưu','read'),
    start=node('input',null,'start'),deadline=node('input',null,'deadline'),max=node('input',null,'max'),interval=node('input',null,'interval'),ack=node('input',null,'ack'),
    create=button('Duyệt kế hoạch gửi hữu hạn','create'),cancel=button('Dừng các bước còn lại của kế hoạch','cancel'),status=node('p',null,'status'),list=node('div',null,'history'),detail=node('pre',null,'detail');
  start.type=deadline.type='datetime-local';start.step=deadline.step='1';max.type=interval.type='number';max.min='1';max.max='100';max.value='10';interval.min='30';interval.max='3600';interval.value='30';ack.type='checkbox';
  card.append(node('summary','Kế hoạch gửi qua API'),node('p','Cần bật hàng đợi ở runtime và duyệt riêng kế hoạch cho yêu cầu xuất bản đã chọn. Hàng đợi không tự gia hạn quyền gửi.'),config,
    node('p','Giờ theo thiết bị: '+Intl.DateTimeFormat().resolvedOptions().timeZone),label('Bắt đầu',start),label('Dừng trước thời điểm',deadline),label('Số bước tối đa',max),label('Khoảng cách tối thiểu giữa các bước (giây)',interval),
    label('Tôi cho phép các bước nền trong giới hạn này, riêng cho yêu cầu đã chọn.',ack),create,history,list,more,read,cancel,
    node('p','Dừng kế hoạch giữ lịch sử và các phản hồi đã biết. Dùng “Dừng quyền gửi” của yêu cầu để thu hồi toàn bộ quyền gửi. Thao tác dừng không xóa bài tại nền tảng.'),status,detail);
  const keys=new Map(),sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v),id=v=>typeof v==='string'&&/^nopq_[a-f0-9]{32}$/.test(v);
  let generation=0,scope='',working=false,runtime=null,rows=[],selected=null,cursor=null;
  const context=()=>{const s=getState(),b=getBinding();return JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.canManage,s.dirty,s.active,s.project?.archived,
    b.publication?.publication_id,b.publication?.snapshot_sha256,b.publication?.approval_id]);};
  const base=s=>'/api/projects/'+s.project.id+'/official-publications/'+getBinding().publication.publication_id+'/queue';
  const ready=s=>s.canManage&&s.project&&!s.dirty&&!s.busy&&!s.active&&!s.project.archived;
  function controls(){const s=getState(),b=getBinding(),blocked=working||s.busy,p=b.publication,d=b.dispatch?.dispatch;
    config.disabled=blocked||!s.canManage;history.disabled=blocked||!s.project||!p;more.disabled=blocked||!cursor||rows.length>=500;read.disabled=blocked||!selected;
    for(const n of [start,deadline,max,interval,ack])n.disabled=blocked||!ready({...s,busy:false})||!p;
    create.disabled=blocked||!ready({...s,busy:false})||!runtime?.enabled||p?.status!=='queued'||p?.snapshot.project_revision!==s.project?.revision||!p?.approval_id||!d||!ack.checked;
    cancel.disabled=blocked||!s.canManage||!s.project||!selected||['completed','cancelled'].includes(selected.status);
  }
  function render(){const p=getBinding().publication;list.replaceChildren();for(const r of rows){const b=button(`${r.mock?'Mô phỏng':'API thật'} · ${r.status} · ${r.step_count}/${r.policy.request.max_steps}`,'row-'+r.plan_id);
    b.disabled=working||getState().busy;b.addEventListener('click',()=>{if(working||getState().busy)return;selected=r;render();});list.append(b);}
    status.textContent=selected?`${selected.mock?'Mô phỏng; chưa đăng thật':'API thật'} · ${selected.status} · ${selected.step_count}/${selected.policy.request.max_steps} bước · ${selected.failure_code??''}`:
      runtime?(runtime.enabled?'Runtime cho phép kế hoạch đã được duyệt riêng.':'Hàng đợi đang tắt ở runtime.'):'Chọn yêu cầu xuất bản và đọc trạng thái hàng đợi.';
    if(p)status.textContent+=' · '+p.publication_id;detail.textContent=selected?JSON.stringify(selected,null,2):'';controls();}
  function sync(){const next=context();if(next!==scope){scope=next;generation++;runtime=null;rows=[];selected=null;cursor=null;ack.checked=false;start.value='';deadline.value='';}render();}
  function validate(r){const s=getState(),p=getBinding().publication,q=r?.policy,x=q?.request;
    if(r?.schema_version!=='native-official-publish-queue-plan-v1'||!id(r.plan_id)||r.workspace_id!==s.workspace_id||r.project_id!==s.project?.id||r.publication_id!==p?.publication_id
      ||!sha(r.policy_sha256)||typeof r.mock!=='boolean'||r.mock!==p.mock||r.token_returned!==false||r.session_uri_returned!==false||q?.mock!==r.mock||q.plan_id!==r.plan_id
      ||q.workspace_id!==r.workspace_id||q.project_id!==r.project_id||q.publication_id!==r.publication_id||q.automatic_consent_renewal!==false||q.remote_deletion_enabled!==false
      ||x?.acknowledged_background_steps!==true||x.expected_snapshot_sha256!==p.snapshot_sha256||!Number.isInteger(x.expected_dispatch_version)||x.expected_dispatch_version<1||!Number.isInteger(x.max_steps)||x.max_steps<1||x.max_steps>100
      ||!Number.isInteger(x.interval_seconds)||x.interval_seconds<30||x.interval_seconds>3600||!Number.isInteger(r.step_count)||r.step_count<0||r.step_count>x.max_steps
      ||!['queued','running','completed','cancelled','needs_attention','exhausted','expired'].includes(r.status)||!Number.isInteger(r.version)||r.version<1)throw new Error('Kế hoạch không khớp yêu cầu hoặc phạm vi.');
    if(r.steps){if(!Array.isArray(r.steps)||r.steps.length!==r.step_count)throw new Error('Lịch sử bước không hợp lệ.');
      for(const [i,step]of r.steps.entries()){const outcome=step.result;
        if(step.plan_id!==r.plan_id||step.publication_id!==r.publication_id||step.workspace_id!==r.workspace_id||step.project_id!==r.project_id||step.ordinal!==i+1
          ||outcome&&(outcome.mock!==r.mock||typeof outcome.published!=='boolean'||typeof outcome.mock_publication_complete!=='boolean'||outcome.published!==false&&r.mock||outcome.mock_publication_complete!==false&&!r.mock
            ||Boolean(outcome.receipt_sha256)!==(outcome.published||outcome.mock_publication_complete)||outcome.receipt_sha256&&(!sha(outcome.receipt_sha256)||outcome.dispatch?.phase!=='uploaded'||outcome.dispatch.acknowledged_bytes!==outcome.dispatch.total_bytes)))throw new Error('Lịch sử bước không khớp phạm vi hoặc chế độ.');}}
    return r;
  }
  async function invoke(fn){if(working)return;const s=getState();if(s.busy)return onMessage('Chờ thao tác hiện tại hoàn tất.',true);const before=context(),version=generation;working=true;onWorking(true);controls();
    try{const apply=await fn(s);if(before===context()&&version===generation)apply();}catch(error){if(before===context()&&version===generation)onMessage(error.message,true);}finally{working=false;onWorking(false);render();}}
  const readConfig=()=>invoke(async s=>{if(!s.canManage)throw new Error('Cần quyền chủ không gian.');const r=await api('/api/connections/official-publish-queue');
    if(r?.schema_version!=='native-official-publish-queue-runtime-v1'||r.workspace_id!==s.workspace_id||typeof r.enabled!=='boolean'||r.default_enabled!==false||r.separate_owner_plan_approval_required!==true
      ||r.automatic_consent_renewal!==false||r.remote_deletion_enabled!==false||r.token_returned!==false||r.session_uri_returned!==false)throw new Error('Trạng thái runtime không hợp lệ.');return()=>{runtime=r;};});
  const readHistory=(next=false)=>invoke(async s=>{if(!s.project||!getBinding().publication)throw new Error('Chọn yêu cầu xuất bản.');if(next&&!cursor)return()=>{};
    const r=await api(base(s)+'?limit=25'+(next?'&cursor='+encodeURIComponent(cursor):'')),p=getBinding().publication;
    if(r?.schema_version!=='native-official-publish-queue-page-v1'||r.workspace_id!==s.workspace_id||r.project_id!==s.project.id||r.publication_id!==p.publication_id||r.token_returned!==false||r.session_uri_returned!==false
      ||!Array.isArray(r.items)||r.items.length>25||r.next_cursor!==null&&(typeof r.next_cursor!=='string'||r.next_cursor.length>2048))throw new Error('Lịch sử kế hoạch không hợp lệ.');const values=r.items.map(validate);
    return()=>{rows=[...new Map([...(next?rows:[]),...values].map(v=>[v.plan_id,v])).values()].slice(0,500);selected=values[0]??null;cursor=r.next_cursor;};});
  const readState=()=>invoke(async s=>{if(!selected)throw new Error('Chọn kế hoạch.');const r=validate(await api(base(s)+'/'+selected.plan_id));return()=>{selected=r;rows=rows.map(v=>v.plan_id===r.plan_id?r:v);};});
  const createPlan=()=>invoke(async s=>{const b=getBinding(),p=b.publication,d=b.dispatch?.dispatch;
    if(!ready(s)||!runtime?.enabled||!p||p.status!=='queued'||p.snapshot.project_revision!==s.project.revision||!p.approval_id||!d||!ack.checked)throw new Error('Lưu dự án, đọc trạng thái yêu cầu có quyền gửi và xác nhận kế hoạch riêng.');
    const date=v=>{if(!/^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?$/.test(v))throw new Error('Chọn giờ theo thiết bị.');const x=new Date(v);if(!Number.isFinite(x.getTime()))throw new Error('Giờ không hợp lệ.');return x;},at=date(start.value),end=date(deadline.value),count=Number(max.value),delay=Number(interval.value);
    if(at.getTime()<Date.now()||end<=at||!Number.isInteger(count)||count<1||count>100||!Number.isInteger(delay)||delay<30||delay>3600)throw new Error('Chọn thời gian tương lai và giới hạn hợp lệ trong thời hạn quyền gửi.');
    const body={expected_snapshot_sha256:p.snapshot_sha256,expected_dispatch_version:d.version,acknowledged_background_steps:true,max_steps:count,interval_seconds:delay,start_at:at.toISOString(),deadline:end.toISOString()},key=JSON.stringify([s.workspace_id,s.project.id,p.publication_id,body]);
    if(!keys.has(key))keys.set(key,uuid());body.request_key=keys.get(key);const r=validate(await api(base(s),body));keys.delete(key);
    return()=>{selected=r;rows=[r,...rows.filter(v=>v.plan_id!==r.plan_id)].slice(0,500);cursor=null;ack.checked=false;onMessage(r.mock?'Đã lưu kế hoạch mô phỏng; chưa đăng thật.':'Đã lưu kế hoạch gửi hữu hạn đã duyệt.');};});
  const cancelPlan=()=>invoke(async s=>{if(!s.canManage||!s.project||!selected||['completed','cancelled'].includes(selected.status))throw new Error('Chọn kế hoạch còn hiệu lực với quyền chủ không gian.');
    const r=validate(await api(base(s)+'/'+selected.plan_id+'/cancel',{expected_policy_sha256:selected.policy_sha256}));return()=>{selected=r;rows=rows.map(v=>v.plan_id===r.plan_id?r:v);ack.checked=false;onMessage('Đã dừng kế hoạch; quyền gửi của yêu cầu và lịch sử vẫn được giữ.');};});
  for(const [b,fn]of [[config,readConfig],[history,readHistory],[more,()=>readHistory(true)],[read,readState],[create,createPlan],[cancel,cancelPlan]])b.addEventListener('click',()=>fn());ack.addEventListener('change',controls);sync();
  return{sync,controls,readConfig,readHistory,readState,createPlan,cancelPlan};
}
