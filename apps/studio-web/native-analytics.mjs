export const supportsNativeAnalytics=session=>session?.capabilities?.native_analytics_review===true;
const metricNames=['views','impressions','reach','watch_time','average_view_duration','completion_rate','likes','comments','shares','saves','followers_gained','clicks','ctr','revenue','rpm'];
export function nativeMetricValue(value){return typeof value==='number'&&Number.isFinite(value)?String(value):'Chưa có';}
export function nativeMetricSeries(rows,metric='views'){
  if(!metricNames.includes(metric))throw new Error('Chỉ số không hợp lệ.');
  return rows.filter(row=>row.snapshot).map(row=>({snapshot_id:row.snapshot.snapshot_id,publication_id:row.snapshot.publication_id,
    collected_at:row.snapshot.collected_at,value:typeof row.snapshot.metrics?.[metric]==='number'&&Number.isFinite(row.snapshot.metrics[metric])?row.snapshot.metrics[metric]:null,mock:row.snapshot.mock===true}))
    .sort((a,b)=>Date.parse(a.collected_at)-Date.parse(b.collected_at)||a.snapshot_id.localeCompare(b.snapshot_id));
}

export function initializeNativeAnalytics({api,getState,root=document,onMessage=()=>{},uuid=()=>crypto.randomUUID()}){
  const $=id=>root.getElementById(id);let scope='',revision=0,working=false,rows=[],selected=null,cursor=null,view='project';const keys=new Map();
  const context=()=>JSON.stringify([getState().project?.id,getState().project?.revision,$('native-analytics-publication').value]);
  const base=()=>`/api/projects/${getState().project.id}/analytics`;
  const element=(tag,text)=>{const node=root.createElement(tag);node.textContent=text;return node;};
  function controls(){const state=getState(),blocked=working||state.busy;
    for(const id of ['native-analytics-publications','native-analytics-read'])$(id).disabled=blocked||!state.project;
    $('native-analytics-overview').disabled=blocked;$('native-analytics-more').disabled=blocked||!cursor;
    const fixture=$('native-analytics-mode').value==='fixture';
    $('native-analytics-create').disabled=blocked||state.dirty||!state.canManage||!state.project||!$('native-analytics-publication').value||(fixture&&!$('native-analytics-ack').checked);
    $('native-analytics-process').disabled=blocked||!state.canManage||!selected||!['queued','scheduled','retry_scheduled'].includes(selected.status)||view!=='project';
    $('native-analytics-cancel').disabled=blocked||!state.canManage||!selected||['succeeded','cancelled'].includes(selected.status)||view!=='project';
    $('native-analytics-new').disabled=blocked||!state.canManage||!selected||!['succeeded','cancelled','failed','not_configured'].includes(selected.status)||view!=='project';
    $('native-analytics-ack').disabled=blocked||!state.canManage||!fixture;$('native-analytics-profile').disabled=blocked||!fixture;
  }
  function render(){const history=$('native-analytics-history');history.replaceChildren();
    for(const row of rows){const snapshot=row.snapshot;const label=snapshot?`Mẫu · ${snapshot.platform} · ${snapshot.collected_at} · views ${nativeMetricValue(snapshot.metrics.views)}`:`${row.status==='not_configured'?'Chưa cấu hình API thật':'Mẫu · '+row.status} · ${row.created_at??''}`;
      const button=element('button',label);button.type='button';button.className='secondary full';button.dataset.vfPermission='read';
      button.addEventListener('click',()=>{selected=row;render();});history.append(button);}
    const table=$('native-analytics-metrics');table.replaceChildren();const snapshot=selected?.snapshot;
    for(const name of metricNames){const line=element('p',`${name}: ${nativeMetricValue(snapshot?.metrics?.[name])}`);table.append(line);}
    $('native-analytics-detail').textContent=selected?JSON.stringify(snapshot?{mock:true,real_audience_observation:false,
      metrics:snapshot.metrics,features:snapshot.features,assessment:snapshot.assessment,insights:snapshot.insights,
      collected_at:snapshot.collected_at,source:snapshot.source,snapshot_id:snapshot.snapshot_id}:selected,null,2):'Chọn quan sát đã lưu. Chưa có dữ liệu khán giả thật.';
    const series=$('native-analytics-series');series.replaceChildren();
    for(const point of nativeMetricSeries(rows))series.append(element('p',`${point.collected_at} · ${point.publication_id} · Mẫu views: ${nativeMetricValue(point.value)}`));
    $('native-analytics-status').textContent=view==='overview'?'Quan sát mẫu mới nhất cho các video đã ghi trong workspace; chưa xác minh tài khoản kênh, không phải tổng tài khoản.':
      snapshot?'Dữ liệu mẫu · chưa quan sát khán giả thật. Đánh giá dùng ngưỡng tham chiếu mẫu; chưa có baseline kênh.':'API thật chưa cấu hình. Chỉ số chưa có giữ nguyên trạng thái chưa có.';controls();
  }
  function sync(){const next=context();if(next!==scope){const old=JSON.parse(scope||'[]')[0];scope=next;revision++;working=false;rows=[];selected=null;cursor=null;view='project';$('native-analytics-ack').checked=false;
    if(old!==getState().project?.id){$('native-analytics-publication').replaceChildren();$('native-analytics-publication').value='';scope=context();}}render();}
  function validateSnapshot(snapshot,overview=false){const state=getState();
    if(snapshot?.schema_version!=='native-analytics-snapshot-v1'||snapshot.mock!==true||snapshot.external_call!==false||snapshot.source_kind!=='fixture'
      ||snapshot.workspace_id!==state.workspace_id||(!overview&&snapshot.project_id!==state.project?.id)
      ||snapshot.evidence?.real_audience_observation!==false||!/^nams_[a-f0-9]{32}$/.test(snapshot.snapshot_id??''))throw new Error('Bằng chứng analytics không khớp phạm vi mẫu.');
    return snapshot;
  }
  function validateRow(row){if(row?.schema_version!=='native-analytics-sync-v1'||row.project_id!==getState().project?.id||row.workspace_id!==getState().workspace_id
      ||row.external_call!==false||!/^nasy_[a-f0-9]{32}$/.test(row.sync_id??'')||!/^[a-f0-9]{64}$/.test(row.request_fingerprint??'')
      ||!['fixture','official'].includes(row.request?.provider_mode)||row.mock!==(row.request.provider_mode==='fixture'))throw new Error('Yêu cầu analytics không khớp phạm vi.');
    if(row.snapshot)validateSnapshot(row.snapshot);return row;}
  async function perform(fn){sync();if(working||getState().busy)return;const captured=context(),own=revision;working=true;controls();
    try{const result=await fn();if(captured!==context()||own!==revision)return;result();}
    catch(error){if(captured===context()&&own===revision)onMessage(error.message,true);}
    finally{if(captured===context()&&own===revision){working=false;render();}}
  }
  async function publications(){if(!getState().project)return;return perform(async()=>{const result=await api(`/api/projects/${getState().project.id}/publications?limit=100`);
    if(result?.schema_version!=='native-publication-page-v1'||result.workspace_id!==getState().workspace_id||result.project_id!==getState().project?.id||!Array.isArray(result.items)||result.items.length>100)throw new Error('Lịch sử phân phối không hợp lệ.');
    return()=>{const select=$('native-analytics-publication');select.replaceChildren();const blank=element('option','Chọn yêu cầu phân phối');blank.value='';select.append(blank);
      for(const row of result.items){if(!/^npub_[a-f0-9]{32}$/.test(row.publication_id??'')||row.project_id!==getState().project?.id)throw new Error('Yêu cầu phân phối ngoài phạm vi.');
        const option=element('option',`${row.snapshot.request.platform} · ${row.snapshot.request.metadata.title} · ${row.status}`);option.value=row.publication_id;select.append(option);}
      if(result.next_cursor)onMessage('Đang hiển thị 100 yêu cầu mới nhất; lịch sử phân phối có trang tiếp.');};});}
  async function read(kind='project',more=false){if(kind==='project'&&!getState().project)return;
    return perform(async()=>{const before=more?cursor:null,pub=$('native-analytics-publication').value;
      const path=kind==='overview'?'/api/analytics/overview':base();
      const value=await api(`${path}?limit=25${pub&&kind==='project'?`&publication_id=${encodeURIComponent(pub)}`:''}${before?`&cursor=${encodeURIComponent(before)}`:''}`);
      if(value?.workspace_id!==getState().workspace_id||!Array.isArray(value.items)||value.items.length>25||value.external_call!==false
          ||(value.next_cursor!==null&&typeof value.next_cursor!=='string')||value.schema_version!==(kind==='overview'?'native-analytics-overview-v1':'native-analytics-page-v1')
          ||(kind==='project'&&(value.project_id!==getState().project?.id||value.publication_id!==(pub||null))))throw new Error('Trang analytics không hợp lệ.');
      const incoming=kind==='overview'?value.items.map(snapshot=>({sync_id:snapshot.sync_id,status:'succeeded',snapshot:validateSnapshot(snapshot,true)})):value.items.map(validateRow);
      return()=>{rows=more?[...rows,...incoming.filter(row=>!rows.some(old=>old.sync_id===row.sync_id))]:incoming;view=kind;cursor=value.next_cursor;
        selected=rows.find(row=>row.sync_id===selected?.sync_id)??rows[0]??null;};});
  }
  async function execute(action){const state=getState();if(!state.canManage||!state.project||state.dirty)return onMessage('Cần quyền chủ không gian và lưu thay đổi trước.',true);
    return perform(async()=>{let path=base(),body;
      if(action==='create'){const pub=$('native-analytics-publication').value,mode=$('native-analytics-mode').value;
        if(!/^npub_[a-f0-9]{32}$/.test(pub)||!['fixture','official'].includes(mode))throw new Error('Chọn yêu cầu phân phối và nguồn analytics.');
        if(mode==='fixture'&&!$('native-analytics-ack').checked)throw new Error('Xác nhận dữ liệu mẫu; đây không phải analytics thật.');
        const intent={publication_id:pub,provider_mode:mode,trigger:$('native-analytics-trigger').value,
          fixture_profile:mode==='fixture'?$('native-analytics-profile').value:null,fixture_acknowledged:mode==='fixture'};
        const signature=scope+JSON.stringify(intent),key=keys.get(signature)??`native-analytics-${uuid()}`;keys.set(signature,key);body={...intent,request_key:key};
      }else{if(!selected||view!=='project')throw new Error('Chọn yêu cầu analytics của dự án.');path+=`/${selected.sync_id}/${action}`;body={expected_fingerprint:selected.request_fingerprint};}
      const result=await api(path,body);const row=validateRow(result);return()=>{selected=row;rows=[row,...rows.filter(old=>old.sync_id!==row.sync_id)];view='project';cursor=null;$('native-analytics-ack').checked=false;
        onMessage(row.status==='not_configured'?'Chưa cấu hình API analytics thật; không tạo chỉ số thay thế.':'Đã lưu dữ liệu mẫu/tiến trình. Chưa có quan sát khán giả thật.');};});
  }
  $('native-analytics-publications').addEventListener('click',publications);$('native-analytics-read').addEventListener('click',()=>read());
  $('native-analytics-overview').addEventListener('click',()=>read('overview'));$('native-analytics-more').addEventListener('click',()=>read(view,true));
  $('native-analytics-create').addEventListener('click',()=>execute('create'));$('native-analytics-process').addEventListener('click',()=>execute('process'));
  $('native-analytics-cancel').addEventListener('click',()=>execute('cancel'));$('native-analytics-publication').addEventListener('change',sync);
  $('native-analytics-new').addEventListener('click',()=>{if($('native-analytics-new').disabled)return;keys.clear();$('native-analytics-trigger').value='manual_refresh';$('native-analytics-ack').checked=false;
    onMessage('Đã chuẩn bị ý định mới. Kiểm tra nguồn và xác nhận trước khi lưu yêu cầu; chưa gọi provider.');controls();});
  for(const id of ['native-analytics-mode','native-analytics-ack'])$(id).addEventListener('change',controls);
  sync();return{sync,controls,read,execute,publications};
}
