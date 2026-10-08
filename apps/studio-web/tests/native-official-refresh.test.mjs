// DOM tests over retained explicit nonplayable protocol fixtures; no browser UAT.
import test from 'node:test';import assert from 'node:assert/strict';import{readFileSync}from'node:fs';
import{initializeNativeOfficialPublications}from'../native-official-publications.mjs';
import{initializeNativeOfficialRefresh,validateOfficialRefreshPlan,validateOfficialRefreshRequest}from'../native-official-refresh.mjs';
const fixture=JSON.parse(readFileSync(new URL('./fixtures/native-official-refresh-v1.json',import.meta.url)));
assert.equal(fixture.fixture_kind,'explicit_nonplayable_protocol_mock_not_provider_or_owner_acceptance');
const seed=fixture.plan,publication=fixture.publication,stamp=Date.parse(seed.policy.approved_at),r=seed.policy.request;
const binding=()=>({schema_version:'native-official-analytics-publication-binding-v1',workspace_id:seed.workspace_id,project_id:seed.project_id,publication_id:seed.publication_id,
  publication_snapshot_sha256:r.expected_publication_snapshot_sha256,receipt_sha256:r.expected_receipt_sha256,target:publication.snapshot.target,mock:true,remote_post_id:seed.policy.source.remote_post_id,
  receipt_qualified:true,published:false,publishing_enabled:false,token_returned:false,real_provider_tested:false,target_binding_sha256:seed.policy.target_binding_sha256});
const runtime=(enabled=true)=>({schema_version:'native-official-analytics-refresh-runtime-v1',workspace_id:seed.workspace_id,enabled,default_enabled:false,separate_owner_background_read_consent_required:true,fixed_report_query:true,
  automatic_consent_renewal:false,publishing_enabled:false,token_returned:false,real_provider_tested:false});
const collector=()=>({schema_version:'native-official-analytics-capabilities-v1',workspace_id:seed.workspace_id,enabled:true,default_enabled:false,fixture_fallback:false,automatic_refresh:false,separate_read_consent_required:true,
  publishing_enabled:false,token_returned:false,accounts:[{account_ref:r.account_ref,configuration_sha256:r.expected_configuration_sha256,target_binding_sha256:seed.policy.target_binding_sha256,target:publication.snapshot.target,
    credential_alias:'explicit-finite-read-fixture',status:'CONFIGURED',mode:'fixture',publishing_enabled:false,token_returned:false}]});
const page=(items,cursor=null)=>({schema_version:'native-official-analytics-refresh-page-v1',workspace_id:seed.workspace_id,project_id:seed.project_id,publication_id:seed.publication_id,items,
  next_cursor:cursor,truncated:cursor!==null,publishing_enabled:false,token_returned:false});
function active(body){const value=structuredClone(seed),request={...body};delete request.request_key;value.policy.request=request;value.status='active';value.run_count=0;value.occurrences=[];value.pending_sync_id=null;value.next_due_at=request.start_at;return value;}
function harness(){const nodes=new Map();class Node{constructor(){this.children=[];this.value='';this.checked=false;this.dataset={};this.listeners={};this.textContent='';}set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}
  append(...v){this.children.push(...v);}replaceChildren(...v){this.children=[...v];}addEventListener(k,v){this.listeners[k]=v;}}
  const root={createElement:()=>new Node(),getElementById(v){if(!nodes.has(v))nodes.set(v,new Node());return nodes.get(v);}},get=id=>root.getElementById('native-official-refresh-'+id),
    state={workspace_id:seed.workspace_id,project:{id:seed.project_id,revision:1},canManage:true,dirty:false,busy:false,active:false},calls=[],messages=[];let parent={publication:structuredClone(publication)},getParent=()=>parent,current=structuredClone(seed),enabled=true,handler,count=0,time=stamp;
  const defaultHandler=async(path,body)=>{if(path==='/api/connections/official-analytics-refresh')return runtime(enabled);if(path==='/api/connections/official-analytics')return collector();if(path.includes('/source/'))return binding();
    if(body){current=path.endsWith('/cancel')?{...current,status:'cancelled',version:current.version+1}:active(body);return current;}if(path.includes('?'))return page([current]);return current;};handler=defaultHandler;
  const controller=initializeNativeOfficialRefresh({root,api:async(...args)=>{calls.push(args);return handler(...args);},getState:()=>({...state}),getBinding:()=>getParent(),
    onWorking:v=>{state.busy=v;},onMessage:(...v)=>messages.push(v),uuid:()=> 'explicit-fixture-key-'+(++count),now:()=>time});
  return{controller,state,calls,get,root,messages,defaultHandler,bindingGetter:v=>{getParent=v;},handler:v=>{handler=v;},binding:v=>{parent=v;},current:v=>{current=v;},enabled:v=>{enabled=v;},time:v=>{time=v;}};
}
function inputs(h){h.get('from').value=r.query.start_date;h.get('to').value=r.query.end_date;h.get('start').value=new Date(stamp+60000).toISOString();h.get('deadline').value=new Date(stamp+900000).toISOString();
  h.get('runs').value='3';h.get('interval').value='60';h.get('valid').value='900';h.get('attempts').value='1';h.get('ack').checked=h.get('background').checked=h.get('mock-ack').checked=true;h.get('retry-ack').checked=false;}
async function ready(h){await h.controller.readSource();await h.controller.readConfig();inputs(h);h.controller.controls();}
test('initialization selection rendering and default-off discovery remain inert',async()=>{const h=harness();assert.equal(h.calls.length,0);assert.equal(h.get('start').value,'');h.controller.sync();h.controller.controls();assert.equal(h.calls.length,0);
  h.enabled(false);await ready(h);const count=h.calls.length;await h.controller.createPlan();assert.equal(h.calls.length,count);assert.equal(h.get('create').disabled,true);assert.equal(h.controller.currentBinding().plan,null);});
test('explicit plan binds source account aware fixed query finite limits and separate raw consent',async()=>{const h=harness();await ready(h);assert.equal(h.get('create').disabled,false);await h.controller.createPlan();const[path,body]=h.calls.at(-1);
  assert.equal(path,`/api/projects/${seed.project_id}/official-analytics-refresh`);assert.equal(body.expected_publication_snapshot_sha256,r.expected_publication_snapshot_sha256);assert.equal(body.expected_receipt_sha256,r.expected_receipt_sha256);
  assert.equal(body.account_ref,r.account_ref);assert.equal(body.max_runs,3);assert.equal(body.interval_seconds,60);assert.equal(body.acknowledged_background_reads,true);assert.equal(body.acknowledged_read_only,true);assert.equal(body.acknowledged_protocol_mock,true);
  assert.equal(body.start_at,new Date(stamp+60000).toISOString());assert.equal(h.calls.length,4);assert.equal(h.get('ack').checked,false);assert.equal(h.get('background').checked,false);assert.equal(h.controller.currentBinding().plan.status,'active');});
test('expired historical windows remain readable without configuration or new consent',async()=>{const h=harness();h.state.canManage=false;h.time(stamp+86400000);h.controller.sync();await h.controller.readSource();await h.controller.readHistory();
  assert.equal(h.calls.length,2);assert.deepEqual(h.controller.currentBinding().plan,seed);assert.equal(h.get('cancel').disabled,true);assert.match(h.get('status').textContent,/chưa có phản hồi khán giả thật/);
  assert.match(h.get('observations').children[0].children[2].textContent,/0$/);assert.match(h.get('observations').children[0].children[3].textContent,/Chưa có/);});
test('uncertain create key survives new preparation and a passed start time',async()=>{const h=harness();await ready(h);let first=true;h.handler(async(path,body)=>{if(body&&first){first=false;throw new Error('EXPLICIT UNKNOWN REPLY');}return h.defaultHandler(path,body);});
  await h.controller.createPlan();const key=h.calls.at(-1)[1].request_key;h.time(stamp+120000);h.controller.prepareNew();inputs(h);h.controller.controls();assert.equal(h.get('create').disabled,false);await h.controller.createPlan();
  assert.equal(h.calls.at(-1)[1].request_key,key);assert.equal(h.controller.currentBinding().plan.status,'active');});
test('successful keys are retained and different finite requests use different keys',async()=>{const h=harness();await ready(h);await h.controller.createPlan();const first=h.calls.at(-1)[1].request_key;h.controller.prepareNew();inputs(h);await h.controller.createPlan();assert.equal(h.calls.at(-1)[1].request_key,first);
  h.controller.prepareNew();inputs(h);h.get('runs').value='4';await h.controller.createPlan();assert.notEqual(h.calls.at(-1)[1].request_key,first);});
test('uncertain keys survive revision role and selected source changes within the project',async()=>{const h=harness();await ready(h);let first=true;h.handler(async(path,body)=>{if(body&&first){first=false;throw new Error('EXPLICIT UNKNOWN');}return h.defaultHandler(path,body);});
  await h.controller.createPlan();const key=h.calls.at(-1)[1].request_key;h.state.project.revision=2;h.controller.sync();h.state.canManage=false;h.controller.sync();h.state.canManage=true;h.binding({publication:{...publication,publication_id:'nopu_'+'b'.repeat(32)}});h.controller.sync();h.binding({publication:structuredClone(publication)});h.controller.sync();
  await ready(h);await h.controller.createPlan();assert.equal(h.calls.at(-1)[1].request_key,key);});
test('workspace or project namespace changes reset creation keys',async()=>{const h=harness();await ready(h);await h.controller.createPlan();const key=h.calls.at(-1)[1].request_key;
  h.state.project.id='a'.repeat(32);h.controller.sync();h.state.project.id=seed.project_id;h.controller.sync();await ready(h);await h.controller.createPlan();assert.notEqual(h.calls.at(-1)[1].request_key,key);});
test('viewer busy and missing background consent cannot create or cancel',async()=>{const h=harness();await ready(h);h.get('background').checked=false;const before=h.calls.length;await h.controller.createPlan();assert.equal(h.calls.length,before);
  h.state.canManage=false;h.controller.sync();await h.controller.readSource();await h.controller.readHistory();const count=h.calls.length;await h.controller.readConfig();await h.controller.createPlan();await h.controller.cancelPlan();assert.equal(h.calls.length,count);
  h.state.canManage=true;h.state.busy=true;await h.controller.readSource();assert.equal(h.calls.length,count);});
test('late source responses cannot cross workspace project revision archive dirty work role or selection',async()=>{for(const change of[h=>h.state.workspace_id='wsp_foreign',h=>h.state.project.id='c'.repeat(32),h=>h.state.project.revision=2,h=>h.state.project.archived=true,h=>h.state.dirty=true,h=>h.state.active=true,h=>h.state.canManage=false,h=>h.binding({publication:{...publication,snapshot_sha256:'c'.repeat(64)}})]){
  const h=harness();let release;h.handler(()=>new Promise(resolve=>{release=resolve;}));const pending=h.controller.readSource();change(h);h.controller.sync();release(binding());await pending;assert.equal(h.controller.currentBinding().plan,null);assert.equal(h.get('detail').textContent,'');assert.equal(h.messages.length,0);assert.equal(h.state.busy,false);}});
test('new past start naive invalid calendar unbounded samples and unacknowledged retry never send',async()=>{const h=harness();await ready(h);const count=h.calls.length;
  for(const[field,value]of[['start','2026-10-09T12:00:00'],['start','2026-02-30T12:00:00Z'],['start',new Date(stamp-60000).toISOString()],['deadline',new Date(stamp+60000).toISOString()],['runs','0'],['runs','101'],['runs','NaN'],['interval','59'],['valid','3601'],['attempts','2'],['from','2026-02-30'],['to','2027-11-30']]){
    inputs(h);h.get(field).value=value;await h.controller.createPlan();assert.equal(h.calls.length,count,field+value);}
  inputs(h);h.get('ack').checked=1;await h.controller.createPlan();assert.equal(h.calls.length,count);inputs(h);h.get('attempts').value='2';h.get('retry-ack').checked=true;await h.controller.createPlan();assert.equal(h.calls.at(-1)[1].max_attempts,2);assert.equal(h.calls.at(-1)[1].acknowledged_bounded_retries,true);});
test('foreign receipt raw mock and unsafe configuration never establish ready source',async()=>{for(const mutate of[v=>({...v,workspace_id:'wsp_foreign'}),v=>({...v,mock:1}),v=>({...v,published:true}),v=>({...v,target:{...v.target,target_account_id:'FOREIGN'}})]){
  const h=harness();h.handler(async()=>mutate(binding()));await h.controller.readSource();assert.equal(h.get('create').disabled,true);assert.equal(h.messages.length,1);}
  const h=harness();await h.controller.readSource();h.handler(async path=>path.endsWith('refresh')?runtime():{...collector(),fixture_fallback:true});await h.controller.readConfig();assert.equal(h.get('account').children.length,0);assert.equal(h.get('create').disabled,true);});
test('original plan rejects raw aliases drift false audience unsupported values and wrong occurrences',()=>{
  assert.equal(validateOfficialRefreshPlan(structuredClone(seed),binding()).status,'completed');
  for(const mutate of[v=>v.mock=1,v=>v.publishing_enabled=0,v=>v.policy.fixed_report_query=1,v=>v.policy.request.acknowledged_background_reads=1,v=>v.policy.source.receipt_sha256='f'.repeat(64),
    v=>v.occurrences[0].ordinal=true,v=>v.occurrences[0].sync.result.real_audience_observation=true,v=>v.occurrences[0].sync.result.metrics.views='0',v=>v.occurrences[0].sync.result.metrics.completion_rate=.8,
    v=>v.occurrences[1].sync.result.metrics.views=0,v=>v.occurrences[0].sync.snapshot.request.max_attempts=3,v=>v.occurrences[0].consent_sha256='f'.repeat(64),v=>v.occurrences[1].due_at=v.occurrences[0].due_at,v=>v.pending_sync_id=seed.occurrences[0].sync_id]){
    const v=structuredClone(seed);mutate(v);assert.throws(()=>validateOfficialRefreshPlan(v,binding()));}
  assert.throws(()=>validateOfficialRefreshRequest({...r,acknowledged_background_reads:1}));
});
test('cancellation requires explicit keep or stop choice and exact source hash and version',async()=>{for(const choice of['keep','stop']){const h=harness();await ready(h);await h.controller.createPlan();const prior=h.controller.currentBinding().plan,count=h.calls.length;
  await h.controller.cancelPlan();assert.equal(h.calls.length,count);assert.equal(h.get('cancel').disabled,true);h.get('cancel-choice').value=choice;h.controller.controls();assert.equal(h.get('cancel').disabled,false);await h.controller.cancelPlan();
  assert.deepEqual(h.calls.at(-1),[`/api/projects/${seed.project_id}/official-analytics-refresh/${prior.plan_id}/cancel`,{expected_policy_sha256:prior.policy_sha256,expected_version:prior.version,cancel_pending_read:choice==='stop'}]);assert.equal(h.controller.currentBinding().plan.status,'cancelled');assert.equal(h.get('cancel').disabled,true);}});
test('invalid cancellation reply preserves selected source for explicit status read',async()=>{const h=harness();await ready(h);await h.controller.createPlan();const prior=structuredClone(h.controller.currentBinding().plan);h.get('cancel-choice').value='stop';h.handler(async()=>({...prior,status:'completed'}));await h.controller.cancelPlan();
  assert.deepEqual(h.controller.currentBinding().plan,prior);assert.equal(h.messages.length,1);});
test('scoped pages preserve old history after invalid replies and encode bounded opaque cursor',async()=>{const h=harness();await h.controller.readSource();h.handler(async()=>page([structuredClone(seed)],'opaque+/='));await h.controller.readHistory();h.handler(async()=>page([]));await h.controller.readHistory(true);
  assert.match(h.calls.at(-1)[0],/&cursor=opaque%2B%2F%3D$/);assert.equal(h.get('history').children.length,1);
  for(const value of[page([{...seed,project_id:'d'.repeat(32)}]),page([],true),page([],'x'.repeat(2049))]){h.handler(async()=>value);await h.controller.readHistory();assert.equal(h.get('history').children.length,1);}assert.equal(h.messages.length,3);});
test('invalid creation reply keeps exact request key for a verified retry',async()=>{const h=harness();await ready(h);let first=true;h.handler(async(path,body)=>{if(body&&first){first=false;return{...active(body),mock:false};}return h.defaultHandler(path,body);});
  await h.controller.createPlan();assert.equal(h.controller.currentBinding().plan,null);const key=h.calls.at(-1)[1].request_key;h.controller.prepareNew();inputs(h);await h.controller.createPlan();assert.equal(h.calls.at(-1)[1].request_key,key);assert.equal(h.controller.currentBinding().plan.mock,true);});

function actualParent(h){let parent=null;const calls=[],second={...structuredClone(publication),publication_id:'nopu_'+'b'.repeat(32),snapshot_sha256:'c'.repeat(64)};
  h.bindingGetter(()=>parent?.currentBinding()??{publication:null});h.controller.sync();
  parent=initializeNativeOfficialPublications({root:h.root,getState:()=>({...h.state}),api:async path=>{calls.push(path);return{schema_version:'native-official-publication-page-v1',workspace_id:seed.workspace_id,project_id:seed.project_id,
    items:[structuredClone(publication),second],next_cursor:null,automatic_publishing:false,token_returned:false,session_uri_returned:false};},onSelection:()=>h.controller.sync(),onWorking:v=>{h.state.busy=v;}});
  return{parent,calls,select:p=>h.root.getElementById('native-official-publish-row-'+p).listeners.click(),second};
}
test('actual publication selection callback invalidates child consent and history without automatic requests',async()=>{
  const h=harness(),p=actualParent(h);assert.equal(p.calls.length+h.calls.length,0);await p.parent.readHistory();await ready(h);await h.controller.readHistory();
  assert.deepEqual(h.controller.currentBinding().plan,seed);const count=h.calls.length;p.select(p.second.publication_id);
  assert.equal(h.controller.currentBinding().plan,null);assert.equal(h.get('ack').checked,false);assert.equal(h.get('background').checked,false);assert.equal(h.get('history').children.length,0);
  assert.equal(h.get('create').disabled,true);assert.equal(h.get('detail').textContent,'');assert.equal(h.calls.length,count);p.select(publication.publication_id);assert.equal(h.calls.length,count);
  await ready(h);assert.equal(h.get('create').disabled,false);assert.equal(p.calls.length,1);
});
test('actual publication changes preserve an uncertain finite request key in the same project',async()=>{
  const h=harness(),p=actualParent(h);await p.parent.readHistory();await ready(h);let first=true;
  h.handler(async(path,body)=>{if(body&&first){first=false;throw new Error('EXPLICIT LOST CREATION REPLY');}return h.defaultHandler(path,body);});
  await h.controller.createPlan();const key=h.calls.at(-1)[1].request_key,count=h.calls.length;p.select(p.second.publication_id);p.select(publication.publication_id);assert.equal(h.calls.length,count);
  await ready(h);await h.controller.createPlan();assert.equal(h.calls.at(-1)[1].request_key,key);assert.equal(h.controller.currentBinding().plan.status,'active');assert.equal(p.calls.length,1);
});
