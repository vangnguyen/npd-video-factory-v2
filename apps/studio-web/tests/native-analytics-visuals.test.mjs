import test from 'node:test';import assert from 'node:assert/strict';
import {nativeAnalyticsChart,nativeAnalyticsValue,nativeAnalyticsMetrics,renderNativeAnalyticsChart,initializeNativeAnalytics} from '../native-analytics.mjs';
const pub='npub_'+'a'.repeat(32),project='b'.repeat(32),workspace='wsp_native_chart_fixture';
function row(index,value,{publication=pub,day=index+1,platform='youtube',metric='views',mock=true}={}){return {snapshot:{
  snapshot_id:'nams_'+index.toString(16).padStart(32,'0'),publication_id:publication,platform,
  collected_at:`2026-10-${String(day).padStart(2,'0')}T00:00:00Z`,mock,external_call:false,source_kind:mock?'fixture':'official_api',
  metrics:{[metric]:value},evidence:{real_audience_observation:false}}};}
class Node{constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.listeners={};this.dataset={};this.value='';this.checked=false;}
  append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}setAttribute(k,v){this.attributes[k]=v;}addEventListener(k,fn){this.listeners[k]=fn;}}
function dom(){const nodes=new Map();return {nodes,getElementById(id){if(!nodes.has(id))nodes.set(id,new Node('div'));return nodes.get(id);},
  createElement:tag=>new Node(tag),createElementNS:(_,tag)=>new Node(tag)};}
function all(node){return [node,...node.children.flatMap(all)];}
test('unknown observations break paths, actual zeros remain measured and input history is unchanged',()=>{
  const rows=[row(3,120),row(0,0),row(2,100),row(1,null)],before=JSON.stringify(rows),model=nativeAnalyticsChart(rows);
  assert.equal(JSON.stringify(rows),before);assert.deepEqual(model.points.map(p=>p.value),[0,null,100,120]);
  assert.deepEqual(model.series[0].segments.map(s=>s.map(p=>p.value)),[[0],[100,120]]);assert.equal(model.plotted_known_count,3);
  assert.equal(model.comparisons[0].delta,20);assert.equal(model.comparisons[0].relative_change_percent,20);
  assert.equal(model.sums_performed,false);assert.equal(model.channel_baseline_established,false);assert.equal(model.automatic_action,false);
});
test('latest missing values, zero denominators and simultaneous collection times never produce invented change',()=>{
  for(const rows of [[row(0,100),row(1,null)],[row(0,0),row(1,10)],[row(0,100),row(1,110,{day:1})]]){
    const comparison=nativeAnalyticsChart(rows).comparisons[0];assert.equal(comparison.relative_change_percent,null);
    if(rows[1].snapshot.metrics.views===null||rows[0].snapshot.collected_at===rows[1].snapshot.collected_at)assert.equal(comparison.delta,null);
  }
});
test('each video/platform/evidence mode keeps its own series and history is never summed',()=>{
  const rows=[row(0,100),row(1,900,{publication:'npub_'+'c'.repeat(32),platform:'tiktok'}),row(2,110),row(3,800,{mock:false})];
  const model=nativeAnalyticsChart(rows);assert.equal(model.series.length,3);assert.equal(model.comparisons.length,3);
  assert.deepEqual(model.series.find(g=>g.publication_id===pub&&g.mock).points.map(p=>p.value),[100,110]);
});
test('units preserve normalized seconds, fractions, VND and RPM without converting null to zero',()=>{
  assert.equal(nativeAnalyticsMetrics.length,15);assert.equal(nativeAnalyticsValue(null,'revenue'),'Chưa có');assert.equal(nativeAnalyticsValue(0,'views'),'0');
  assert.match(nativeAnalyticsValue(.25,'completion_rate'),/^25%$/);assert.match(nativeAnalyticsValue(.05,'ctr',true),/^5 điểm phần trăm$/);
  assert.match(nativeAnalyticsValue(42,'watch_time'),/42 giây/);assert.match(nativeAnalyticsValue(1000,'rpm'),/VND \/ 1\.000 lượt xem/);
  assert.match(nativeAnalyticsValue(1e-9,'views'),/e-9/);assert.throws(()=>nativeAnalyticsValue(Infinity));
});
test('bounded history/series expose scope limits without dropping missing values or mutating history',()=>{
  const rows=Array.from({length:20},(_,i)=>row(i,i%2?null:i,{day:1,publication:'npub_'+i.toString(16).padStart(32,'0')}));
  const model=nativeAnalyticsChart(rows);assert.equal(model.series.length,12);assert.equal(model.comparisons.length,20);assert.equal(model.series_limit_applied,true);
  const small=nativeAnalyticsChart(rows,'views',{limit:5});assert.equal(small.loaded_count,20);assert.equal(small.shown_count,5);assert.equal(small.observation_limit_applied,true);
  assert.equal(rows.length,20);assert.throws(()=>nativeAnalyticsChart(rows,'views',{limit:1001}));
});
test('invalid chronology/numbers/provenance and conflicting duplicate snapshot IDs fail closed',()=>{
  for(const mutate of [s=>s.collected_at='invalid',s=>s.collected_at='2026-10-01T00:00:00',s=>s.metrics.views=-1,
    s=>s.metrics.views=Infinity,s=>s.metrics.views='100',s=>s.metrics=[],s=>s.mock=false,s=>s.publication_id='../foreign']){
    const bad=row(0,1);mutate(bad.snapshot);assert.throws(()=>nativeAnalyticsChart([bad]));}
  assert.throws(()=>nativeAnalyticsChart([row(0,1),row(0,2)]));assert.equal(nativeAnalyticsChart([row(0,1),row(0,1)]).shown_count,1);
  assert.throws(()=>nativeAnalyticsChart([row(0,1.5,{metric:'ctr'})],'ctr'));
});
test('very large finite values stay within SVG coordinates and unbounded relative change remains unknown',()=>{
  const model=nativeAnalyticsChart([row(0,1e-300),row(1,1e308)]);
  assert.equal(model.comparisons[0].relative_change_percent,null);
  for(const p of model.series[0].segments[0]){assert.ok(Number.isFinite(p.x)&&p.x>=70&&p.x<=620);assert.ok(Number.isFinite(p.y)&&p.y>=36&&p.y<=226);}
});
test('actual DOM SVG preserves gaps, accessible source labels and literal values without HTML interpretation',()=>{
  const root=dom(),container=new Node('div');renderNativeAnalyticsChart(root,container,nativeAnalyticsChart([row(0,0),row(1,null),row(2,100)]),{hasMore:true});
  const nodes=all(container);assert.equal(nodes.filter(n=>n.tag==='circle').length,2);assert.equal(nodes.filter(n=>n.tag==='polyline').length,0);
  assert.equal(nodes.filter(n=>n.tag==='svg')[0].attributes.role,'img');assert.ok(nodes.some(n=>n.textContent?.includes('có giới hạn')));
  assert.ok(nodes.some(n=>n.textContent?.includes('không phải mức tăng theo giờ')));assert.ok(nodes.some(n=>n.textContent==='Chưa có'));
  assert.ok(nodes.every(n=>n.innerHTML===undefined));
  renderNativeAnalyticsChart(root,container,nativeAnalyticsChart([row(0,null)]));assert.equal(all(container).filter(n=>n.tag==='svg').length,0);
});
test('long currency and RPM units stay in the heading and numeric axes preserve every digit',()=>{
  for(const metric of ['revenue','rpm']){const root=dom(),container=new Node('div');renderNativeAnalyticsChart(root,container,nativeAnalyticsChart([row(0,12000000,{metric})],metric));
    const texts=all(container).filter(n=>n.tag==='text');assert.ok(texts.some(n=>n.textContent.includes('(VND')));
    const ticks=texts.filter(n=>n.attributes['text-anchor']==='end'&&n.attributes['font-size']==='10');
    assert.ok(ticks.some(n=>n.textContent==='12.000.000'));assert.ok(ticks.every(n=>!n.textContent.includes('VND')));
  }
});
test('metric selection redraws validated saved rows without a provider request and project switch clears every plot',async()=>{
  const root=dom(),calls=[],state={project:{id:project,revision:1},workspace_id:workspace,canManage:false,dirty:false,busy:false};
  const saved=row(0,80).snapshot;Object.assign(saved,{schema_version:'native-analytics-snapshot-v1',project_id:project,workspace_id:workspace,sync_id:'nasy_'+'e'.repeat(32)});
  saved.metrics.revenue=null;const sync={schema_version:'native-analytics-sync-v1',sync_id:saved.sync_id,project_id:project,workspace_id:workspace,
    request_fingerprint:'f'.repeat(64),external_call:false,mock:true,status:'succeeded',request:{provider_mode:'fixture'},snapshot:saved};
  const controller=initializeNativeAnalytics({root,getState:()=>state,api:async(path,body)=>{calls.push([path,body]);return{
    schema_version:'native-analytics-page-v1',workspace_id:workspace,project_id:project,publication_id:null,items:[sync],next_cursor:null,external_call:false};}});
  await controller.read();assert.equal(calls.length,1);assert.equal(all(root.getElementById('native-analytics-series')).filter(n=>n.tag==='circle').length,1);
  const metric=root.getElementById('native-analytics-metric');metric.value='revenue';metric.listeners.change();assert.equal(calls.length,1);
  assert.equal(all(root.getElementById('native-analytics-series')).filter(n=>n.tag==='svg').length,0);assert.equal(state.project.revision,1);
  state.project={id:'9'.repeat(32),revision:1};controller.sync();assert.equal(all(root.getElementById('native-analytics-series')).filter(n=>n.tag==='circle').length,0);
});
