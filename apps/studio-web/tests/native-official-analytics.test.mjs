import test from 'node:test';import assert from 'node:assert/strict';
import {initializeNativeOfficialAnalytics}from'../native-official-analytics.mjs';
import {nativeAnalyticsMetrics}from'../native-analytics.mjs';
const workspace='wsp_official_analytics_fixture',project='a'.repeat(32),pub='nopu_'+'b'.repeat(32),syncId='noas_'+'c'.repeat(32),sha='d'.repeat(64),receiptSha='e'.repeat(64),configSha='f'.repeat(64),accountId='npac_'+'1'.repeat(32);
const target={workspace_id:workspace,profile_id:'nppf_'+'2'.repeat(32),profile_version:1,platform:'youtube',provider_key:'youtube-data-api-publishing',target_account_id:'UC'+'3'.repeat(22),credential_binding_sha256:'4'.repeat(64)};
const publication=()=>({publication_id:pub,status:'completed',snapshot_sha256:sha,mock:true,snapshot:{target}});
const source=()=>({schema_version:'native-official-analytics-publication-binding-v1',workspace_id:workspace,project_id:project,publication_id:pub,publication_snapshot_sha256:sha,
  receipt_sha256:receiptSha,target,mock:true,remote_post_id:'dQw4w9WgXcQ',receipt_qualified:true,published:false,publishing_enabled:false,token_returned:false,real_provider_tested:false});
const runtime=(enabled=true)=>({schema_version:'native-official-analytics-capabilities-v1',workspace_id:workspace,enabled,default_enabled:false,publishing_enabled:false,token_returned:false,fixture_fallback:false,
  accounts:[{account_ref:accountId,configuration_sha256:configSha,target,credential_alias:'explicit-read-fixture',status:'CONFIGURED',mode:'fixture',token_returned:false,publishing_enabled:false}]});
const query=()=>({start_date:'2026-10-01',end_date:'2026-10-02',include_revenue:false});
const request=()=>({schema_version:'native-official-analytics-request-v1',publication_id:pub,expected_publication_snapshot_sha256:sha,expected_receipt_sha256:receiptSha,account_ref:accountId,
  expected_configuration_sha256:configSha,query:query(),acknowledged_read_only:true,acknowledged_protocol_mock:true,acknowledged_bounded_retries:false,max_attempts:1,valid_for_seconds:900});
function row(status='queued',body=request()){
  const value={schema_version:'native-official-analytics-sync-v1',sync_id:syncId,workspace_id:workspace,project_id:project,publication_id:pub,snapshot_sha256:sha,mock:true,status,
    publishing_enabled:false,token_returned:false,result_snapshot_id:null,result:null,snapshot:{schema_version:'native-official-analytics-consent-v1',mock:true,target,request:body,
      publishing_authority:false,recurring_authority:false,source:{receipt_sha256:receiptSha,publication_snapshot_sha256:sha,receipt_mock:true,remote_post_id:'dQw4w9WgXcQ'}}};
  if(status==='succeeded'){
    value.result_snapshot_id='noam_'+'5'.repeat(32);value.result={schema_version:'native-official-analytics-snapshot-v1',workspace_id:workspace,project_id:project,publication_id:pub,sync_id:syncId,
      snapshot_sha256:sha,result_snapshot_id:value.result_snapshot_id,mock:true,external_call:false,real_audience_observation:false,source_kind:'official_protocol_mock',automatic_action:false,
      publishing_time:null,publication_receipt_sha256:receiptSha,remote_post_id:'dQw4w9WgXcQ',collected_at:'2026-10-08T12:00:00+00:00',evidence:{query:body.query},
      metrics:{...Object.fromEntries(nativeAnalyticsMetrics.map(m=>[m.id,null])),views:0,watch_time:150}};
  }return value;
}
const page=(items,cursor=null)=>({schema_version:'native-official-analytics-page-v1',workspace_id:workspace,project_id:project,publication_id:pub,items,next_cursor:cursor,publishing_enabled:false,token_returned:false});
function harness(){const nodes=new Map();class Node{constructor(){this.children=[];this.value='';this.checked=false;this.dataset={};this.listeners={};}set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}
  append(...v){this.children.push(...v);}replaceChildren(...v){this.children=[...v];}addEventListener(k,v){this.listeners[k]=v;}}
  const root={createElement:()=>new Node(),getElementById(v){if(!nodes.has(v))nodes.set(v,new Node());return nodes.get(v);}},get=id=>root.getElementById('native-official-analytics-'+id),
    state={workspace_id:workspace,project:{id:project,revision:1},canManage:true,dirty:false,busy:false,active:false},calls=[],messages=[];let pubBinding={publication:publication()},current=row(),enabled=true,handler,count=0;
  const defaultHandler=async(path,body)=>{if(path.includes('/connections/'))return runtime(enabled);if(path.includes('/source/'))return source();
    if(body){current=path.endsWith('/cancel')?{...current,status:'cancelled'}:row('queued',body);return current;}if(path.includes('?'))return page([current]);return current;};handler=defaultHandler;
  const controller=initializeNativeOfficialAnalytics({api:async(...args)=>{calls.push(args);return handler(...args);},root,getState:()=>({...state}),getBinding:()=>pubBinding,
    onMessage:(...v)=>messages.push(v),onWorking:v=>{state.busy=v;},uuid:()=> 'explicit-read-key-'+(++count)});
  return{controller,state,calls,get,messages,defaultHandler,handler:v=>{handler=v;},binding:v=>{pubBinding=v;},current:v=>{current=v;},enabled:v=>{enabled=v;}};
}
function inputs(h){h.get('start').value='2026-10-01';h.get('end').value='2026-10-02';h.get('ack').checked=h.get('mock-ack').checked=true;}
async function ready(h){await h.controller.readSource();await h.controller.readConfig();inputs(h);h.controller.controls();}

test('initialization does not request or invent dates and default-off runtime cannot collect',async()=>{const h=harness();assert.equal(h.calls.length,0);assert.equal(h.get('start').value,'');h.enabled(false);await ready(h);
  const count=h.calls.length;await h.controller.createRead();assert.equal(h.calls.length,count);assert.equal(h.get('create').disabled,true);assert.match(h.get('status').textContent,/đang tắt/);});
test('explicit read freezes server receipt digest account dates and finite consent without publishing or polling',async()=>{const h=harness();await ready(h);assert.equal(h.get('create').disabled,false);await h.controller.createRead();
  assert.deepEqual(h.calls.at(-1),[`/api/projects/${project}/official-analytics`,{...request(),request_key:'native-official-analytics-explicit-read-key-1'}]);
  assert.equal(h.calls.length,3);assert.equal(h.get('ack').checked,false);assert.equal(h.get('mock-ack').checked,false);assert.equal(h.get('detail').textContent.includes('queued'),true);});
test('uncertain creation retains exact key even with old selected history and new-read preparation',async()=>{const h=harness();await ready(h);await h.controller.readHistory();let count=0;
  h.handler(async(path,body)=>{if(body&&!count++)throw new Error('Explicit unknown reply');return h.defaultHandler(path,body);});await h.controller.createRead();const key=h.calls.at(-1)[1].request_key;
  h.controller.prepareNew();inputs(h);await h.controller.createRead();assert.equal(h.calls.at(-1)[1].request_key,key);assert.equal(h.get('ack').checked,false);});
test('foreign source target raw mock and disabled fixture fallback configurations cannot enable collection',async()=>{for(const mutate of[v=>({...v,workspace_id:'wsp_foreign'}),v=>({...v,mock:1}),v=>({...v,target:{...target,target_account_id:'UC'+'6'.repeat(22)}}),v=>({...v,published:true})]){
  const h=harness();h.handler(async()=>mutate(source()));await h.controller.readSource();assert.equal(h.get('create').disabled,true);assert.match(h.messages.at(-1)[0],/phạm vi/);}
  const h=harness();await h.controller.readSource();h.handler(async()=>({...runtime(),fixture_fallback:true}));await h.controller.readConfig();assert.equal(h.get('account').children.length,0);});
test('viewer and busy context cannot create or cancel while scoped viewer history stays readable',async()=>{const h=harness();await ready(h);await h.controller.readHistory();h.state.canManage=false;h.controller.sync();await h.controller.readSource();await h.controller.readHistory();
  const count=h.calls.length;await h.controller.readConfig();await h.controller.createRead();await h.controller.cancelRead();assert.equal(h.calls.length,count);assert.equal(h.get('cancel').disabled,true);
  h.state.canManage=true;h.state.busy=true;await h.controller.readSource();assert.equal(h.calls.length,count);});
test('late responses cannot cross project workspace role or selected publication boundaries',async()=>{for(const change of[h=>h.state.project.id='7'.repeat(32),h=>h.state.workspace_id='wsp_foreign',h=>h.state.canManage=false,
  h=>h.binding({publication:{...publication(),publication_id:'nopu_'+'8'.repeat(32)}})]){const h=harness();let release;h.handler(()=>new Promise(resolve=>{release=resolve;}));const pending=h.controller.readSource();change(h);h.controller.sync();release(source());await pending;
  assert.equal(h.get('create').disabled,true);assert.equal(h.messages.length,0);assert.equal(h.state.busy,false);assert.equal(h.get('detail').textContent,'');}});
test('malformed reversed or unbounded dates and retries without separate acknowledgement never create',async()=>{const h=harness();await ready(h);const count=h.calls.length;
  for(const[field,value]of[['start','2026-02-30'],['start','not-a-date'],['end','2026-09-30'],['end','2027-10-03'],['attempts','0'],['attempts','4'],['attempts','2']]){
    inputs(h);h.get('attempts').value='1';h.get(field).value=value;await h.controller.createRead();assert.equal(h.calls.length,count);}
  inputs(h);h.get('attempts').value='2';h.get('retry-ack').checked=true;await h.controller.createRead();assert.equal(h.calls.at(-1)[1].max_attempts,2);assert.equal(h.calls.at(-1)[1].acknowledged_bounded_retries,true);});
test('qualified protocol history displays zero seconds and missing values without audience claims',async()=>{const h=harness();await h.controller.readSource();h.current(row('succeeded'));await h.controller.readHistory();
  const boxes=h.get('metrics').children;assert.equal(boxes.length,15);assert.equal(boxes[0].children[1].textContent,'0');assert.equal(boxes[1].children[1].textContent,'Chưa có');assert.equal(boxes[3].children[1].textContent,'150 giây');
  assert.match(h.get('status').textContent,/chưa quan sát khán giả thật/);assert.equal(h.calls.length,2);assert.equal(h.get('cancel').disabled,true);});
test('relabeled observations query mismatch receipt drift numeric strings and missing results are rejected',async()=>{for(const mutate of[v=>({...v,result:{...v.result,mock:false,real_audience_observation:true}}),
  v=>({...v,result:{...v.result,evidence:{query:{...query(),end_date:'2026-10-03'}}}}),v=>({...v,snapshot:{...v.snapshot,source:{...v.snapshot.source,receipt_sha256:'9'.repeat(64)}}}),
  v=>({...v,result:{...v.result,metrics:{...v.result.metrics,views:'0'}}}),v=>({...v,result:null})]){const h=harness();await h.controller.readSource();h.handler(async()=>page([mutate(row('succeeded'))]));await h.controller.readHistory();
  assert.equal(h.get('history').children.length,0);assert.equal(h.get('metrics').children.length,0);assert.equal(h.messages.length,1);}});
test('bounded cursor pages reject foreign rows and encode opaque scoped next-page cursor',async()=>{const h=harness();await h.controller.readSource();h.handler(async()=>page([row()],'opaque+/='));await h.controller.readHistory();
  h.handler(async()=>page([]));await h.controller.readHistory(true);assert.match(h.calls.at(-1)[0],/&cursor=opaque%2B%2F%3D$/);assert.equal(h.get('history').children.length,1);
  for(const value of[page([{...row(),project_id:'9'.repeat(32)}]),page([],true),page([],'x'.repeat(2049))]){h.handler(async()=>value);await h.controller.readHistory();assert.equal(h.get('history').children.length,1);}assert.equal(h.messages.length,3);});
test('historical read can be stopped after current project edits archive or active work without a provider call',async()=>{const h=harness();await h.controller.readSource();await h.controller.readHistory();h.state.project.revision=2;h.state.project.archived=true;h.state.dirty=true;h.state.active=true;h.controller.sync();
  await h.controller.readSource();await h.controller.readHistory();assert.equal(h.get('cancel').disabled,false);await h.controller.cancelRead();assert.deepEqual(h.calls.at(-1),[`/api/projects/${project}/official-analytics/${syncId}/cancel`,{expected_snapshot_sha256:sha}]);
  assert.equal(h.get('cancel').disabled,true);assert.match(h.get('detail').textContent,/cancelled/);});
test('completed exact-key replay uses qualified stored result and known new-read preparation chooses a new key',async()=>{const h=harness();await ready(h);let attempts=0;h.handler(async(path,body)=>{
  if(body&&!attempts++)throw new Error('Explicit lost result');if(body)return{...row('succeeded',body),idempotent_replay:true};return h.defaultHandler(path,body);});
  await h.controller.createRead();await h.controller.createRead();assert.equal(h.calls.at(-2)[1].request_key,h.calls.at(-1)[1].request_key);assert.equal(h.get('metrics').children.length,15);
  const oldKey=h.calls.at(-1)[1].request_key;h.controller.prepareNew();inputs(h);await h.controller.createRead();assert.notEqual(h.calls.at(-1)[1].request_key,oldKey);assert.equal(h.get('ack').checked,false);});
