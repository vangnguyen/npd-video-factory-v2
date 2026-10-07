import test from 'node:test';
import assert from 'node:assert/strict';
import {supportsNativeAnalytics,nativeMetricValue,nativeMetricSeries,initializeNativeAnalytics} from '../native-analytics.mjs';
const id='a'.repeat(32),pub='npub_'+'b'.repeat(32),sync='nasy_'+'c'.repeat(32),hash='d'.repeat(64),sid='nams_'+'e'.repeat(32),workspace='wsp_native_fixture';
const snapshot=()=>({schema_version:'native-analytics-snapshot-v1',snapshot_id:sid,sync_id:sync,workspace_id:workspace,project_id:id,publication_id:pub,
  collected_at:'2026-10-07T00:00:00+00:00',platform:'youtube',provider_key:'fixture-analytics-v1',source:'fixture://analytics/youtube/insufficient_data',
  source_kind:'fixture',mock:true,external_call:false,evidence:{real_audience_observation:false},metrics:{views:80,watch_time:null,revenue:null},
  features:{publishing_time:null},assessment:{state:'insufficient_data',automatic_action:false},insights:[]});
const row=()=>({schema_version:'native-analytics-sync-v1',sync_id:sync,project_id:id,workspace_id:workspace,external_call:false,mock:true,
  request_fingerprint:hash,status:'succeeded',request:{provider_mode:'fixture'},snapshot:snapshot()});
function harness(){const nodes=new Map();class Node{constructor(){this.value='';this.checked=false;this.dataset={};this.listeners={};this.children=[];}
  addEventListener(name,fn){this.listeners[name]=fn;}replaceChildren(){this.children=[];this.value='';}append(child){this.children.push(child);}}
  const root={getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);},createElement(){return new Node();}};
  const get=id=>root.getElementById(id),state={project:{id,revision:2},workspace_id:workspace,canManage:true,dirty:false,busy:false},calls=[],messages=[];let n=0;
  get('native-analytics-mode').value='official';get('native-analytics-trigger').value='initial';get('native-analytics-profile').value='insufficient_data';
  let handler=async(path,body)=>body?row():{schema_version:'native-analytics-page-v1',workspace_id:workspace,project_id:id,publication_id:pub,items:[row()],next_cursor:null,external_call:false};
  const controller=initializeNativeAnalytics({root,getState:()=>state,api:async(...args)=>{calls.push(args);return handler(...args);},onMessage:(...args)=>messages.push(args),uuid:()=>`fixture-${++n}`});
  get('native-analytics-publication').value=pub;controller.sync();
  return{get,state,calls,messages,controller,handler(fn){handler=fn;}};
}
test('capability, null metrics and series preserve unknown values without invented zeros',()=>{
  assert.equal(supportsNativeAnalytics({}),false);assert.equal(supportsNativeAnalytics({capabilities:{native_analytics_review:true}}),true);
  for(const value of [null,undefined,NaN,Infinity,'80'])assert.equal(nativeMetricValue(value),'Chưa có');assert.equal(nativeMetricValue(0),'0');
  const rows=[row(),{...row(),snapshot:{...snapshot(),snapshot_id:'nams_'+'f'.repeat(32),collected_at:'2026-10-08T00:00:00Z',metrics:{views:null}}}];
  const points=nativeMetricSeries(rows);assert.deepEqual(points.map(x=>x.value),[80,null]);assert.equal(points[0].mock,true);
});
test('saved reads display explicit sample labels and literal text without mutating project or dispatching',async()=>{
  const h=harness();assert.equal(h.calls.length,0);await h.controller.read();assert.equal(h.calls.length,1);assert.equal(h.calls[0][1],undefined);
  assert.ok(h.get('native-analytics-history').children[0].textContent.startsWith('Mẫu'));
  assert.ok(h.get('native-analytics-metrics').children.some(node=>node.textContent==='revenue: Chưa có'));
  assert.equal(h.state.project.revision,2);assert.equal(h.get('native-analytics-create').disabled,false);
});
test('fixture collection requires Owner and explicit checkbox; same intent replays one key',async()=>{
  const h=harness();h.get('native-analytics-mode').value='fixture';await h.controller.execute('create');assert.equal(h.calls.length,0);
  h.get('native-analytics-ack').checked=true;await h.controller.execute('create');assert.equal(h.calls[0][1].fixture_acknowledged,true);
  assert.equal(h.calls[0][1].fixture_profile,'insufficient_data');const key=h.calls[0][1].request_key;
  h.get('native-analytics-ack').checked=true;await h.controller.execute('create');assert.equal(h.calls[1][1].request_key,key);
  h.state.canManage=false;h.get('native-analytics-ack').checked=true;await h.controller.execute('create');assert.equal(h.calls.length,2);
});
test('new observation prepares a new intent without calling a provider or granting fixture acknowledgment',async()=>{
  const h=harness();h.get('native-analytics-mode').value='fixture';h.get('native-analytics-ack').checked=true;await h.controller.execute('create');
  const key=h.calls[0][1].request_key;h.get('native-analytics-new').listeners.click();assert.equal(h.calls.length,1);assert.equal(h.get('native-analytics-ack').checked,false);
  h.get('native-analytics-ack').checked=true;await h.controller.execute('create');assert.notEqual(h.calls[1][1].request_key,key);assert.equal(h.calls[1][1].trigger,'manual_refresh');
});
test('late project and publication responses are discarded and live sample contradictions reject',async()=>{
  const h=harness();let release;h.handler(()=>new Promise(resolve=>{release=resolve;}));const pending=h.controller.read();
  h.state.project={id:'f'.repeat(32),revision:1};h.controller.sync();release({schema_version:'native-analytics-page-v1',workspace_id:workspace,project_id:id,publication_id:pub,items:[row()],next_cursor:null,external_call:false});
  await pending;assert.equal(h.get('native-analytics-history').children.length,0);
  const other=harness();other.handler(async()=>({schema_version:'native-analytics-page-v1',workspace_id:workspace,project_id:id,publication_id:pub,
    items:[{...row(),snapshot:{...snapshot(),external_call:true}}],next_cursor:null,external_call:false}));await other.controller.read();assert.equal(other.get('native-analytics-history').children.length,0);assert.ok(other.messages.length);
});
test('workspace overview uses bounded explicit recorded scope and cannot process another project',async()=>{
  const h=harness();h.handler(async()=>({schema_version:'native-analytics-overview-v1',workspace_id:workspace,external_call:false,
    items:[{...snapshot(),project_id:'f'.repeat(32)}],next_cursor:'explicit-fixture-cursor'}));await h.controller.read('overview');
  assert.ok(h.calls[0][0].includes('limit=25'));assert.equal(h.get('native-analytics-process').disabled,true);
  assert.ok(h.get('native-analytics-status').textContent.includes('không phải tổng tài khoản'));
});
test('official request retains null fixture evidence and does not synthesize an analytics snapshot',async()=>{
  const h=harness();h.handler(async()=>({...row(),mock:false,status:'not_configured',snapshot:null,request:{provider_mode:'official'}}));
  await h.controller.execute('create');assert.equal(h.calls[0][1].fixture_profile,null);assert.equal(h.calls[0][1].fixture_acknowledged,false);
  assert.ok(h.get('native-analytics-history').children[0].textContent.startsWith('Chưa cấu hình'));assert.ok(h.get('native-analytics-metrics').children.every(node=>node.textContent.endsWith('Chưa có')));
});
