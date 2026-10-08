// Owner-controlled recurring collection; saved policies confer no publishing authority.
export function nativeRefreshIntent({publication,mode,profile,firstRun,interval,maxRuns,fixtureAck,readOnlyAck,enabled}){
  if(!/^npub_[a-f0-9]{32}$/.test(publication??'')||!['fixture','official'].includes(mode))throw new Error('Chọn video đã phân phối và nguồn analytics.');
  if(typeof firstRun!=='string'||!firstRun.trim()||!Number.isFinite(Date.parse(firstRun)))throw new Error('Nhập thời điểm chạy đầu tiên.');
  const integer=(value,min,max)=>{if(typeof value!=='string'||!/^\d+$/.test(value)||!Number.isSafeInteger(Number(value))||Number(value)<min||Number(value)>max)throw new Error('Nhập chu kỳ 1–168 giờ và giới hạn 1–365 lần.');return Number(value);};
  if(typeof enabled!=='boolean'||typeof fixtureAck!=='boolean'||typeof readOnlyAck!=='boolean')throw new Error('Xác nhận chính sách analytics.');
  if(mode==='fixture'&&!fixtureAck)throw new Error('Xác nhận đây là mẫu kiểm tra, không phải analytics thật.');
  if(enabled&&(!readOnlyAck||mode!=='fixture'))throw new Error('Chỉ bật lịch mẫu đã xác nhận; API thật chưa cấu hình.');
  if(mode==='fixture'&&!['normal','winner_candidate','underperforming','insufficient_data','rate_limited'].includes(profile))throw new Error('Chọn mẫu kiểm tra hợp lệ.');
  return {schema_version:'native-analytics-refresh-plan-v1',publication_id:publication,provider_mode:mode,
    fixture_profile:mode==='fixture'?profile:'normal',fixture_acknowledged:mode==='fixture',
    first_run_at:new Date(firstRun).toISOString(),interval_hours:integer(interval,1,168),max_runs:integer(maxRuns,1,365),
    enabled,acknowledged_read_only:readOnlyAck,query_policy:'cumulative'};
}
export function initializeNativeAnalyticsRefresh({api,getState,root=document,onMessage=()=>{},uuid=()=>crypto.randomUUID()}){
  const $=id=>root.getElementById('native-refresh-'+id),publication=()=>root.getElementById('native-analytics-publication').value;
  let scope='',generation=0,working=false,rows=[],selected=null,cursor=null;const keys=new Map();
  const context=()=>JSON.stringify([getState().project?.id,getState().project?.revision,publication()]);
  const base=()=>`/api/projects/${getState().project.id}/analytics-refresh`;
  const node=(tag,text)=>{const n=root.createElement(tag);n.textContent=text;return n;};
  function controls(){const s=getState(),blocked=working||s.busy;
    $('read').disabled=blocked||!s.project;$('more').disabled=blocked||!cursor;
    const manage=!blocked&&s.canManage&&s.project&&!s.dirty,fixture=$('mode').value==='fixture';
    $('create').disabled=!manage||!publication()||(fixture&&!$('fixture-ack').checked);
    $('tick').disabled=!manage;
    $('enable').disabled=!manage||!selected||selected.config.provider_mode!=='fixture'||selected.enabled||selected.run_count>=selected.max_runs||!$('fixture-ack').checked||!$('read-only-ack').checked;
    $('disable').disabled=!manage||!selected||!selected.enabled;
    $('fixture-ack').disabled=blocked||!s.canManage;$('read-only-ack').disabled=blocked||!s.canManage;
    $('enabled').disabled=!manage||!fixture;$('profile').disabled=blocked||!fixture;
    for(const id of ['mode','first','interval','runs'])$(id).disabled=blocked||!s.canManage;
  }
  function render(){const list=$('history');list.replaceChildren();
    for(const row of rows){const button=node('button',`${row.config.provider_mode==='fixture'?'Mẫu':'API chưa cấu hình'} · ${row.status} · ${row.run_count}/${row.max_runs} lần · ${row.next_due_at}`);
      button.type='button';button.className='secondary full';button.dataset.vfPermission='read';button.addEventListener('click',()=>detail(row.plan_id));list.append(button);}
    $('detail').textContent=selected?JSON.stringify(selected,null,2):'Chọn chính sách để xem phiên bản, profile và các lần đồng bộ đã lưu.';
    $('status').textContent=selected?`${selected.config.provider_mode==='fixture'?'Dữ liệu mẫu, chưa có khán giả thật':'API thật chưa cấu hình'} · ${selected.status} · ${selected.run_count}/${selected.max_runs} lần đã lên hàng đợi. Tắt lịch hủy các lần còn chờ; lịch sử vẫn giữ nguyên.`:
      'Lịch mặc định tắt. API thật chưa cấu hình. Lịch mẫu cần chủ không gian xác nhận; không tạo quyền xuất bản.';controls();
  }
  function sync(){const next=context();if(next!==scope){scope=next;generation++;working=false;rows=[];selected=null;cursor=null;
    $('fixture-ack').checked=false;$('read-only-ack').checked=false;$('enabled').checked=false;}render();}
  function validate(row){const s=getState(),p=row?.analytics_profile;
    if(row?.schema_version!=='native-analytics-refresh-plan-v1'||row.workspace_id!==s.workspace_id||row.project_id!==s.project?.id
      ||!/^narp_[a-f0-9]{32}$/.test(row.plan_id??'')||!/^[a-f0-9]{64}$/.test(row.request_fingerprint??'')||row.external_call!==false
      ||row.publishing_enabled_by_plan!==false||row.recommendation_only!==true||!row.config||!['fixture','official'].includes(row.config.provider_mode)
      ||p?.schema_version!=='native-runtime-analytics-profile-v1'||p.provider_mode!==row.config.provider_mode||p.external_calls_enabled!==false||p.publishing_enabled!==false
      ||p.provider_status!==(row.config.provider_mode==='fixture'?'EXPLICIT_FIXTURE':'NOT_CONFIGURED')||typeof row.enabled!=='boolean'
      ||!Number.isInteger(row.revision)||row.revision<1||!Number.isInteger(row.run_count)||row.run_count<0||!Number.isInteger(row.max_runs)||row.max_runs<1||row.run_count>row.max_runs
      ||(row.enabled&&row.config.provider_mode!=='fixture'))throw new Error('Bằng chứng lịch analytics không khớp phạm vi.');return row;
  }
  async function perform(fn){sync();if(working||getState().busy)return;const g=generation,c=scope;working=true;controls();
    try{const apply=await fn();if(g===generation&&c===context())apply();}
    catch(error){if(g===generation&&c===context())onMessage(error.message,true);}
    finally{if(g===generation){working=false;render();}}
  }
  async function read(more=false){if(!getState().project)return;return perform(async()=>{const result=await api(`${base()}?limit=25${more&&cursor?`&cursor=${encodeURIComponent(cursor)}`:''}`);
    if(result?.schema_version!=='native-analytics-refresh-page-v1'||result.workspace_id!==getState().workspace_id||result.project_id!==getState().project?.id||result.external_call!==false
      ||!Array.isArray(result.items)||result.items.length>25||(result.next_cursor!==null&&typeof result.next_cursor!=='string'))throw new Error('Trang lịch analytics không hợp lệ.');
    const incoming=result.items.map(validate);return()=>{rows=more?[...rows,...incoming.filter(r=>!rows.some(old=>old.plan_id===r.plan_id))]:incoming;cursor=result.next_cursor;selected=rows.find(r=>r.plan_id===selected?.plan_id)??null;};});}
  async function detail(id){return perform(async()=>{const result=validate(await api(base()+'/'+id));return()=>{selected=result;};});}
  async function execute(action){const s=getState();if(!s.canManage||!s.project||s.dirty)return onMessage('Cần quyền chủ không gian và lưu thay đổi trước.',true);
    return perform(async()=>{let path=base(),body;
      if(action==='create'){const intent=nativeRefreshIntent({publication:publication(),mode:$('mode').value,profile:$('profile').value,firstRun:$('first').value,
        interval:$('interval').value,maxRuns:$('runs').value,fixtureAck:$('fixture-ack').checked,readOnlyAck:$('read-only-ack').checked,enabled:$('enabled').checked});
        const signature=scope+JSON.stringify(intent),key=keys.get(signature)??`native-analytics-refresh-${uuid()}`;keys.set(signature,key);body={...intent,request_key:key};
      }else if(action==='tick'){path+='/tick';body={schema_version:'native-analytics-refresh-tick-v1'};}
      else{if(!selected||!['enable','disable'].includes(action))throw new Error('Chọn chính sách analytics.');const enabled=action==='enable';
        if(enabled&&(!$('fixture-ack').checked||!$('read-only-ack').checked||selected.config.provider_mode!=='fixture'))throw new Error('Xác nhận lịch mẫu chỉ đọc trước khi bật.');
        path+=`/${selected.plan_id}/state`;body={expected_revision:selected.revision,enabled,acknowledged_read_only:enabled,fixture_acknowledged:enabled};}
      const result=await api(path,body);
      if(action==='tick'){if(result?.schema_version!=='native-analytics-refresh-tick-v1'||result.workspace_id!==s.workspace_id||result.project_id!==s.project.id||result.external_call!==false
        ||result.provider_calls!==0||result.publishing_enabled!==false||!Array.isArray(result.created_sync_ids))throw new Error('Biên nhận lịch không hợp lệ.');return()=>onMessage(`Đã lên hàng đợi ${result.created_sync_ids.length} lần mẫu đến hạn. Đọc lịch sử analytics để xem worker; chưa gọi API thật.`);}
      const row=validate(result);return()=>{selected=row;rows=[row,...rows.filter(r=>r.plan_id!==row.plan_id)];cursor=null;
        $('fixture-ack').checked=false;$('read-only-ack').checked=false;$('enabled').checked=false;
        onMessage(row.config.provider_mode==='official'?'Đã lưu ý định; API thật chưa cấu hình, lịch không chạy.':'Đã lưu chính sách mẫu. Chỉ số mẫu không phải phản hồi khán giả.');};});
  }
  $('read').addEventListener('click',()=>read());$('more').addEventListener('click',()=>read(true));
  for(const action of ['create','enable','disable','tick'])$(action).addEventListener('click',()=>execute(action));
  for(const id of ['mode','fixture-ack','read-only-ack','enabled'])$(id).addEventListener('change',controls);
  root.getElementById('native-analytics-publication').addEventListener('change',sync);
  sync();return{sync,controls,read,detail,execute};
}
