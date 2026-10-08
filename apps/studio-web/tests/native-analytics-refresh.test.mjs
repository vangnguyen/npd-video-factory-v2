import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeRefreshIntent,initializeNativeAnalyticsRefresh} from '../native-analytics-refresh.mjs';
const id='a'.repeat(32),pub='npub_'+'b'.repeat(32),plan='narp_'+'c'.repeat(32),workspace='wsp_native_fixture';
const intent=()=>({publication:pub,mode:'fixture',profile:'normal',firstRun:'2026-10-08T00:00:00Z',interval:'24',maxRuns:'7',fixtureAck:true,readOnlyAck:false,enabled:false});
const row=()=>({schema_version:'native-analytics-refresh-plan-v1',plan_id:plan,workspace_id:workspace,project_id:id,request_fingerprint:'d'.repeat(64),
  external_call:false,recommendation_only:true,publishing_enabled_by_plan:false,enabled:false,revision:1,run_count:0,max_runs:7,status:'paused',next_due_at:'2026-10-08T00:00:00Z',
  config:{provider_mode:'fixture'},analytics_profile:{schema_version:'native-runtime-analytics-profile-v1',provider_mode:'fixture',provider_status:'EXPLICIT_FIXTURE',external_calls_enabled:false,publishing_enabled:false}});
function harness(){const nodes=new Map();class Node{constructor(){this.value='';this.checked=false;this.children=[];this.listeners={};this.dataset={};}
  addEventListener(name,fn){this.listeners[name]=fn;}replaceChildren(){this.children=[];}append(n){this.children.push(n);}}
  const root={getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);},createElement(){return new Node();}},get=id=>root.getElementById('native-refresh-'+id);
  const state={project:{id,revision:1},workspace_id:workspace,canManage:true,dirty:false,busy:false},calls=[],messages=[];let handler=async(path,body)=>body?row():{schema_version:'native-analytics-refresh-page-v1',workspace_id:workspace,project_id:id,external_call:false,items:[row()],next_cursor:null};
  root.getElementById('native-analytics-publication').value=pub;get('mode').value='fixture';get('profile').value='normal';get('first').value='2026-10-08T00:00:00Z';get('interval').value='24';get('runs').value='7';
  const controller=initializeNativeAnalyticsRefresh({root,getState:()=>state,api:async(...args)=>{calls.push(args);return handler(...args);},onMessage:(...args)=>messages.push(args),uuid:()=> 'fixture-key'});
  return{get,root,state,calls,messages,controller,handler(fn){handler=fn;}};
}
test('explicit policy keeps disabled default and validates strict schedule limits and source acknowledgment',()=>{
  const value=nativeRefreshIntent(intent());assert.equal(value.enabled,false);assert.equal(value.first_run_at,'2026-10-08T00:00:00.000Z');assert.equal(value.max_runs,7);
  for(const change of [{enabled:true},{fixtureAck:false},{interval:'0'},{interval:'1.5'},{interval:'1e2'},{maxRuns:'366'},{firstRun:''},{firstRun:'bad'},{profile:'live'}])assert.throws(()=>nativeRefreshIntent({...intent(),...change}));
  assert.throws(()=>nativeRefreshIntent({...intent(),mode:'official',enabled:true,readOnlyAck:true}));
});
test('saved policy reads do not create work and invalid external or wrong-workspace evidence rejects',async()=>{
  const h=harness();assert.equal(h.calls.length,0);await h.controller.read();assert.equal(h.calls.length,1);assert.equal(h.calls[0][1],undefined);
  assert.ok(h.get('history').children[0].textContent.startsWith('Mẫu'));assert.equal(h.get('enable').disabled,true);
  const bad=harness();bad.handler(async()=>({schema_version:'native-analytics-refresh-page-v1',workspace_id:workspace,project_id:id,external_call:false,
    items:[{...row(),analytics_profile:{...row().analytics_profile,external_calls_enabled:true}}],next_cursor:null}));await bad.controller.read();assert.equal(bad.get('history').children.length,0);assert.ok(bad.messages.length);
});
test('same create intent retains key while checks and Owner role gate writes',async()=>{
  const h=harness();await h.controller.execute('create');assert.equal(h.calls.length,0);h.get('fixture-ack').checked=true;
  await h.controller.execute('create');assert.equal(h.calls[0][1].enabled,false);assert.equal(h.get('fixture-ack').checked,false);
  h.get('fixture-ack').checked=true;await h.controller.execute('create');assert.equal(h.calls[1][1].request_key,h.calls[0][1].request_key);
  h.state.canManage=false;h.get('fixture-ack').checked=true;await h.controller.execute('create');assert.equal(h.calls.length,2);
});
test('enable binds exact revision and requires both explicit fixture and read-only acknowledgments',async()=>{
  const h=harness();h.handler(async()=>row());await h.controller.detail(plan);await h.controller.execute('enable');assert.equal(h.calls.length,1);
  h.get('fixture-ack').checked=true;h.get('read-only-ack').checked=true;await h.controller.execute('enable');
  assert.ok(h.calls[1][0].endsWith('/'+plan+'/state'));assert.deepEqual(h.calls[1][1],{expected_revision:1,enabled:true,acknowledged_read_only:true,fixture_acknowledged:true});
  assert.equal(h.get('read-only-ack').checked,false);
});
test('tick only admits due queue work and stale project results are discarded',async()=>{
  const h=harness();h.handler(async()=>({schema_version:'native-analytics-refresh-tick-v1',workspace_id:workspace,project_id:id,external_call:false,provider_calls:0,publishing_enabled:false,created_sync_ids:[]}));
  await h.controller.execute('tick');assert.ok(h.calls[0][0].endsWith('/tick'));assert.ok(h.messages[0][0].includes('chưa gọi API thật'));
  const stale=harness();let release;stale.handler(()=>new Promise(resolve=>{release=resolve;}));const pending=stale.controller.read();stale.state.project={id:'f'.repeat(32),revision:1};stale.controller.sync();
  release({schema_version:'native-analytics-refresh-page-v1',workspace_id:workspace,project_id:id,external_call:false,items:[row()],next_cursor:null});await pending;assert.equal(stale.get('history').children.length,0);
});
