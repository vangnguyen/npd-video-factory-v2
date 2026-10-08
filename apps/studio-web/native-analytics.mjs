import {initializeNativeAnalyticsRefresh} from './native-analytics-refresh.mjs';
export const supportsNativeAnalytics=session=>session?.capabilities?.native_analytics_review===true;
const metricNames=['views','impressions','reach','watch_time','average_view_duration','completion_rate','likes','comments','shares','saves','followers_gained','clicks','ctr','revenue','rpm'];
export const nativeAnalyticsMetrics=Object.freeze([
  ['views','Lượt xem','count'],['impressions','Lượt hiển thị','count'],['reach','Tiếp cận','count'],
  ['watch_time','Tổng thời gian xem','seconds'],['average_view_duration','Thời gian xem trung bình','seconds'],
  ['completion_rate','Tỷ lệ xem hết','ratio'],['likes','Lượt thích','count'],['comments','Bình luận','count'],
  ['shares','Chia sẻ','count'],['saves','Lượt lưu','count'],['followers_gained','Người theo dõi tăng','count'],
  ['clicks','Lượt nhấp','count'],['ctr','CTR','ratio'],['revenue','Doanh thu','vnd'],['rpm','RPM','vnd_per_1000_views']
].map(([id,label,unit])=>Object.freeze({id,label,unit})));
function analyticsMetric(metric){const found=nativeAnalyticsMetrics.find(v=>v.id===metric);if(!found)throw new Error('Chỉ số không hợp lệ.');return found;}
export function nativeAnalyticsValue(value,metric='views',difference=false){
  const {unit}=analyticsMetric(metric);if(value===null||value===undefined)return 'Chưa có';
  if(typeof value!=='number'||!Number.isFinite(value))throw new Error('Giá trị analytics không hợp lệ.');
  const n=unit==='ratio'?value*100:value;
  const text=n!==0&&(Math.abs(n)>=1e15||Math.abs(n)<1e-5)?n.toExponential(3):n.toLocaleString('vi-VN',{maximumSignificantDigits:8});
  return text+({count:'',seconds:' giây',ratio:difference?' điểm phần trăm':'%',vnd:' VND',vnd_per_1000_views:' VND / 1.000 lượt xem'}[unit]);
}
export function nativeAnalyticsChart(rows,metric='views',{limit=1000}={}){
  const definition=analyticsMetric(metric);
  if(!Array.isArray(rows)||rows.length>10000||!Number.isInteger(limit)||limit<1||limit>1000)throw new Error('Phạm vi lịch sử analytics không hợp lệ.');
  const seen=new Map(),points=[];
  for(const row of rows){const s=row?.snapshot;if(!s)continue;
    const time=Date.parse(s.collected_at),raw=s.metrics?.[metric];
    if(!/^nams_[a-f0-9]{32}$/.test(s.snapshot_id??'')||!/^npub_[a-f0-9]{32}$/.test(s.publication_id??'')||!Number.isFinite(time)
      ||typeof s.collected_at!=='string'||!/(?:Z|[+-]\d\d:\d\d)$/.test(s.collected_at)||!['youtube','tiktok','instagram_reels','facebook'].includes(s.platform)
      ||typeof s.mock!=='boolean'||!['fixture','official_api'].includes(s.source_kind)||s.mock!==(s.source_kind==='fixture')||!s.metrics||typeof s.metrics!=='object'||Array.isArray(s.metrics)
      ||(raw!==null&&raw!==undefined&&(typeof raw!=='number'||!Number.isFinite(raw)||raw<0||(definition.unit==='ratio'&&raw>1))))throw new Error('Bằng chứng chuỗi thời gian không hợp lệ.');
    const point={snapshot_id:s.snapshot_id,publication_id:s.publication_id,platform:s.platform,collected_at:s.collected_at,time,
      value:raw??null,mock:s.mock,source_kind:s.source_kind,real_audience_observation:s.evidence?.real_audience_observation===true};
    const fingerprint=JSON.stringify(point);if(seen.has(s.snapshot_id)){if(seen.get(s.snapshot_id)!==fingerprint)throw new Error('Quan sát trùng có bằng chứng khác nhau.');continue;}
    seen.set(s.snapshot_id,fingerprint);points.push(point);
  }
  points.sort((a,b)=>a.time-b.time||a.snapshot_id.localeCompare(b.snapshot_id));
  const loaded=points.length,visible=points.slice(-limit),groups=new Map();
  for(const point of visible){const key=JSON.stringify([point.publication_id,point.platform,point.source_kind]);
    if(!groups.has(key))groups.set(key,{key,publication_id:point.publication_id,platform:point.platform,mock:point.mock,points:[]});groups.get(key).points.push(point);}
  const all=[...groups.values()].sort((a,b)=>b.points.at(-1).time-a.points.at(-1).time||a.key.localeCompare(b.key));
  const comparisons=all.map(group=>{const latest=group.points.at(-1),previous=group.points.at(-2)??null;
    const comparable=Boolean(previous&&previous.time<latest.time&&previous.value!==null&&latest.value!==null);
    const delta=comparable?latest.value-previous.value:null,relative=comparable&&previous.value>0?delta/previous.value*100:null;
    return {...group,latest,previous,delta,relative_change_percent:relative!==null&&Number.isFinite(relative)?relative:null,
      comparison_basis:comparable?'two_latest_distinct_collection_times':'insufficient_comparable_observations',automatic_action:false};});
  const series=all.slice(0,12),plotted=series.flatMap(g=>g.points),known=plotted.filter(p=>p.value!==null);
  const minimum=plotted.length?Math.min(...plotted.map(p=>p.time)):null,maximum=plotted.length?Math.max(...plotted.map(p=>p.time)):null;
  const scale=known.length?Math.max(1,...known.map(p=>p.value)):1;
  for(const group of series){let segment=[];group.segments=[];
    for(const point of group.points){if(point.value===null){if(segment.length)group.segments.push(segment);segment=[];continue;}
      segment.push({...point,x:minimum===maximum?365:110+(point.time-minimum)/(maximum-minimum)*510,y:226-point.value/scale*190});}
    if(segment.length)group.segments.push(segment);
  }
  return {metric:definition,points:visible,series,comparisons,loaded_count:loaded,shown_count:visible.length,plotted_known_count:known.length,
    observation_limit_applied:loaded>limit,series_limit_applied:all.length>12,domain:{minimum,maximum,maximum_value:scale},
    sums_performed:false,channel_baseline_established:false,automatic_action:false};
}
export function renderNativeAnalyticsChart(root,container,model,{hasMore=false}={}){
  container.replaceChildren();const add=(tag,text)=>{const node=root.createElement(tag);node.textContent=text;return node;};
  const prefix=model.points.every(p=>p.mock)?'Dữ liệu mẫu · chưa quan sát khán giả thật.':'Bằng chứng đã lưu theo từng nguồn; cần xem phạm vi xác minh.';
  container.append(add('p',`${prefix} ${model.shown_count}/${model.loaded_count} quan sát đã tải. Không cộng thành tổng tài khoản.`));
  if(hasMore||model.observation_limit_applied||model.series_limit_applied)container.append(add('p','Phạm vi đang hiển thị có giới hạn; đọc các trang tiếp để xem lịch sử khác. Biểu đồ vẽ tối đa 12 video mới nhất.'));
  container.append(add('p','Thời điểm trên trục là lúc thu thập (UTC), không phải tuổi video. Nền tảng có thể đo khác nhau; thay đổi giữa hai quan sát không phải mức tăng theo giờ hay đánh giá winner.'));
  if(!model.points.length){container.append(add('p','Chưa có quan sát đã lưu cho biểu đồ.'));return;}
  if(!model.plotted_known_count)container.append(add('p','Chỉ số này chưa có giá trị trong các video đang vẽ; các khoảng thiếu giữ nguyên trạng thái chưa có.'));
  if(model.plotted_known_count&&root.createElementNS){const svg=(tag,attrs={},text)=>{const n=root.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;return n;};
    const graph=svg('svg',{viewBox:'0 0 680 280',role:'img','aria-label':`${model.metric.label}: quan sát đã lưu theo thời gian UTC; điểm thiếu không được nối qua.`});
    const unitLabel={count:'',seconds:' (giây)',ratio:' (%)',vnd:' (VND)',vnd_per_1000_views:' (VND / 1.000 lượt xem)'}[model.metric.unit];
    graph.append(svg('text',{x:110,y:20,'font-size':14,'font-weight':600,fill:'#244a36'},model.metric.label+unitLabel),
      svg('text',{x:620,y:20,'font-size':11,'text-anchor':'end',fill:'#365747'},model.points.every(p=>p.mock)?'Mẫu · UTC':'Nguồn đã lưu · UTC'));
    graph.append(svg('title',{},`${model.metric.label} · dữ liệu đã tải, giữ các khoảng thiếu`),svg('line',{x1:110,y1:36,x2:110,y2:226,stroke:'#708878'}),svg('line',{x1:110,y1:226,x2:620,y2:226,stroke:'#708878'}));
    for(const value of [0,model.domain.maximum_value/2,model.domain.maximum_value]){const y=226-value/model.domain.maximum_value*190;
      graph.append(svg('line',{x1:110,y1:y,x2:620,y2:y,stroke:'#dce5dd'}),svg('text',{x:105,y:y+4,'text-anchor':'end','font-size':10,fill:'#365747'},nativeAnalyticsValue(value,model.metric.unit==='ratio'?model.metric.id:'views')));}
    if(model.domain.minimum!==null){for(const [stamp,x,anchor] of [[model.domain.minimum,110,'start'],[model.domain.maximum,620,'end']])graph.append(svg('text',{x,y:252,'text-anchor':anchor,'font-size':11,fill:'#365747'},new Date(stamp).toISOString().slice(0,19)+'Z'));}
    const colors=['#185a44','#3267a3','#8a4a92','#a26015','#9f4351','#457678'];
    model.series.forEach((series,index)=>{const color=colors[index%colors.length];for(const segment of series.segments){
      if(segment.length>1)graph.append(svg('polyline',{points:segment.map(p=>`${p.x.toFixed(3)},${p.y.toFixed(3)}`).join(' '),fill:'none',stroke:color,'stroke-width':2,'stroke-dasharray':index>=colors.length?'6 3':'none'}));
      for(const p of segment){const dot=svg('circle',{cx:p.x,cy:p.y,r:4,fill:color});dot.append(svg('title',{},`${p.publication_id} · ${p.collected_at} · ${nativeAnalyticsValue(p.value,model.metric.id)} · ${p.snapshot_id}`));graph.append(dot);}
    }});
    const wrap=add('div','');wrap.className='native-analytics-chart';wrap.append(graph);container.append(wrap);
    const legend=add('ul','');model.series.forEach((series,index)=>{const entry=add('li',`${series.mock?'Mẫu':'API'} · ${series.platform} · ${series.publication_id} · ${series.points.filter(p=>p.value!==null).length}/${series.points.length} điểm có giá trị`);
      entry.setAttribute('style',`border-left:4px solid ${colors[index%colors.length]};padding-left:8px`);legend.append(entry);});container.append(legend);
  }
  const table=add('table','');table.append(add('caption',`${model.metric.label} · so sánh từng video trên lịch sử đã tải; không xếp hạng`));
  const head=add('thead',''),labels=add('tr','');for(const name of ['Video / nguồn','Thu thập UTC','Mới nhất','Trước đó','Chênh lệch','Thay đổi tương đối'])labels.append(add('th',name));head.append(labels);table.append(head);
  const body=add('tbody','');for(const item of model.comparisons){const line=add('tr','');const relative=item.relative_change_percent===null?'Chưa có':nativeAnalyticsValue(item.relative_change_percent/100,'ctr');
    for(const value of [`${item.mock?'Mẫu':'API'} · ${item.platform} · ${item.publication_id}`,item.latest.collected_at,nativeAnalyticsValue(item.latest.value,model.metric.id),
      nativeAnalyticsValue(item.previous?.value,model.metric.id),nativeAnalyticsValue(item.delta,model.metric.id,true),relative])line.append(add('td',value));body.append(line);}table.append(body);
  const wrapper=add('div','');wrapper.className='native-analytics-comparison';wrapper.append(table);container.append(wrapper);
  const detail=add('details','');detail.append(add('summary','Giá trị, thời điểm và ID từng quan sát'));
  for(const point of model.points){const line=add('p',`${point.collected_at} · ${point.publication_id} · ${point.snapshot_id} · ${nativeAnalyticsValue(point.value,model.metric.id)}`);detail.append(line);}container.append(detail);
}
export function nativeMetricValue(value){return typeof value==='number'&&Number.isFinite(value)?String(value):'Chưa có';}
export function nativeMetricSeries(rows,metric='views'){
  if(!metricNames.includes(metric))throw new Error('Chỉ số không hợp lệ.');
  return rows.filter(row=>row.snapshot).map(row=>({snapshot_id:row.snapshot.snapshot_id,publication_id:row.snapshot.publication_id,
    collected_at:row.snapshot.collected_at,value:typeof row.snapshot.metrics?.[metric]==='number'&&Number.isFinite(row.snapshot.metrics[metric])?row.snapshot.metrics[metric]:null,mock:row.snapshot.mock===true}))
    .sort((a,b)=>Date.parse(a.collected_at)-Date.parse(b.collected_at)||a.snapshot_id.localeCompare(b.snapshot_id));
}

export function initializeNativeAnalytics({api,getState,root=document,onMessage=()=>{},uuid=()=>crypto.randomUUID(),enableRefresh=false}){
  const $=id=>root.getElementById(id);let scope='',revision=0,working=false,rows=[],selected=null,cursor=null,view='project';const keys=new Map();
  const context=()=>JSON.stringify([getState().project?.id,getState().project?.revision,$('native-analytics-publication').value]);
  const base=()=>`/api/projects/${getState().project.id}/analytics`;
  const element=(tag,text)=>{const node=root.createElement(tag);node.textContent=text;return node;};
  const metricSelect=$('native-analytics-metric');metricSelect.replaceChildren();
  for(const metric of nativeAnalyticsMetrics){const option=element('option',metric.label);option.value=metric.id;metricSelect.append(option);}metricSelect.value='views';
  function controls(){const state=getState(),blocked=working||state.busy;
    for(const id of ['native-analytics-publications','native-analytics-read'])$(id).disabled=blocked||!state.project;
    $('native-analytics-overview').disabled=blocked;$('native-analytics-more').disabled=blocked||!cursor;
    metricSelect.disabled=blocked;
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
    try{renderNativeAnalyticsChart(root,series,nativeAnalyticsChart(rows,metricSelect.value),{hasMore:Boolean(cursor)});}
    catch(error){series.replaceChildren(element('p','Không thể xác minh dữ liệu biểu đồ.'));onMessage(error.message,true);}
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
  metricSelect.addEventListener('change',render);
  const refreshUI=enableRefresh?initializeNativeAnalyticsRefresh({api,getState,root,onMessage,uuid}):null;
  if(enableRefresh)$('native-refresh-section').hidden=false;
  sync();return{sync(){sync();refreshUI?.sync();},controls(){controls();refreshUI?.controls();},read,execute,publications,refreshUI};
}
