import test from 'node:test';import assert from 'node:assert/strict';
import {initializeNativeOfficialPublicationQueue}from'../native-official-publication-queue.mjs';
const workspace='wsp_queue_fixture',project='a'.repeat(32),pub='nopu_'+'b'.repeat(32),planId='nopq_'+'c'.repeat(32),sha='d'.repeat(64);
const publication=()=>({publication_id:pub,status:'queued',approval_id:'nopa_'+'e'.repeat(32),snapshot_sha256:sha,mock:true,snapshot:{project_revision:1}});
const runtime=enabled=>({schema_version:'native-official-publish-queue-runtime-v1',workspace_id:workspace,enabled,default_enabled:false,separate_owner_plan_approval_required:true,
  automatic_consent_renewal:false,remote_deletion_enabled:false,token_returned:false,session_uri_returned:false});
const row=(status='queued',request=null)=>({schema_version:'native-official-publish-queue-plan-v1',plan_id:planId,publication_id:pub,workspace_id:workspace,project_id:project,policy_sha256:sha,
  status,version:1,step_count:0,mock:true,token_returned:false,session_uri_returned:false,steps:[],policy:{schema_version:'native-official-publish-queue-policy-v1',plan_id:planId,
    workspace_id:workspace,project_id:project,publication_id:pub,mock:true,automatic_consent_renewal:false,remote_deletion_enabled:false,
    request:request??{expected_snapshot_sha256:sha,expected_dispatch_version:3,acknowledged_background_steps:true,max_steps:10,interval_seconds:30}}});
const page=items=>({schema_version:'native-official-publish-queue-page-v1',workspace_id:workspace,project_id:project,publication_id:pub,items,next_cursor:null,token_returned:false,session_uri_returned:false});
function harness(){const nodes=new Map();class Node{constructor(){this.children=[];this.value='';this.checked=false;this.dataset={};this.listeners={};}set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}
  append(...v){this.children.push(...v);}replaceChildren(...v){this.children=[...v];}addEventListener(k,v){this.listeners[k]=v;}}
  const root={createElement:()=>new Node(),getElementById(v){if(!nodes.has(v))nodes.set(v,new Node());return nodes.get(v);}},get=id=>root.getElementById('native-official-queue-'+id),
    state={workspace_id:workspace,project:{id:project,revision:1},canManage:true,dirty:false,busy:false,active:false},calls=[],messages=[];let binding={publication:publication(),dispatch:{dispatch:{version:3,phase:'uploading'}}},current=row(),enabled=true,handler,count=0;
  const defaultHandler=async(path,body)=>{if(path.includes('/connections/'))return runtime(enabled);if(body){if(path.endsWith('/cancel'))current={...current,status:'cancelled'};else current=row('queued',body);return current;}
    if(path.includes('?'))return page([current]);return current;};handler=defaultHandler;
  const controller=initializeNativeOfficialPublicationQueue({api:async(...args)=>{calls.push(args);return handler(...args);},root,getState:()=>({...state}),getBinding:()=>binding,onMessage:(...v)=>messages.push(v),onWorking:v=>{state.busy=v;},uuid:()=> 'explicit-queue-key-'+(++count)});
  return{controller,state,calls,get,messages,defaultHandler,handler:v=>{handler=v;},binding:v=>{binding=v;},current:v=>{current=v;},enabled:v=>{enabled=v;}};
}
function times(h){const pad=v=>String(v).padStart(2,'0'),format=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  h.get('start').value=format(new Date(Date.now()+120000));h.get('deadline').value=format(new Date(Date.now()+600000));h.get('ack').checked=true;}
test('initialization makes no request and default-off runtime cannot create a plan',async()=>{const h=harness();assert.equal(h.calls.length,0);h.enabled(false);await h.controller.readConfig();times(h);const count=h.calls.length;
  await h.controller.createPlan();assert.equal(h.calls.length,count);assert.equal(h.get('create').disabled,true);assert.match(h.get('status').textContent,/đang tắt/);});
test('separate finite approval freezes snapshot version limits and UTC window without sending or polling',async()=>{const h=harness();await h.controller.readConfig();times(h);const start=new Date(h.get('start').value).toISOString(),deadline=new Date(h.get('deadline').value).toISOString();
  await h.controller.createPlan();assert.deepEqual(h.calls.at(-1),[`/api/projects/${project}/official-publications/${pub}/queue`,{expected_snapshot_sha256:sha,expected_dispatch_version:3,
    acknowledged_background_steps:true,max_steps:10,interval_seconds:30,start_at:start,deadline,request_key:'explicit-queue-key-1'}]);assert.equal(h.calls.length,2);assert.equal(h.get('ack').checked,false);assert.match(h.messages.at(-1)[0],/mô phỏng/);});
test('unknown creation outcome retains exact request key and success resets acknowledgement',async()=>{const h=harness();await h.controller.readConfig();times(h);let attempts=0;h.handler(async(path,body)=>{if(body&&!attempts++)throw new Error('Explicit unknown response');return h.defaultHandler(path,body);});
  await h.controller.createPlan();await h.controller.createPlan();assert.equal(h.calls.at(-2)[1].request_key,h.calls.at(-1)[1].request_key);assert.equal(h.get('ack').checked,false);});
test('viewer and stale dirty active archived or missing dispatch states cannot authorize background steps',async()=>{const h=harness();await h.controller.readConfig();times(h);for(const flag of ['dirty','active','busy']){h.state[flag]=true;const count=h.calls.length;await h.controller.createPlan();assert.equal(h.calls.length,count);h.state[flag]=false;}
  h.state.project.archived=true;let count=h.calls.length;await h.controller.createPlan();assert.equal(h.calls.length,count);h.state.project.archived=false;h.state.project.revision=2;await h.controller.createPlan();assert.equal(h.calls.length,count);
  h.state.project.revision=1;h.binding({publication:publication(),dispatch:null});await h.controller.createPlan();assert.equal(h.calls.length,count);h.state.canManage=false;await h.controller.readConfig();assert.equal(h.calls.length,count);});
test('history reads never send and historical plan can be cancelled after edits or archive',async()=>{const h=harness();await h.controller.readHistory();h.state.project.revision=2;h.state.project.archived=true;h.state.dirty=true;h.state.active=true;h.controller.sync();await h.controller.readHistory();
  assert.equal(h.get('cancel').disabled,false);const count=h.calls.length;await h.controller.cancelPlan();assert.equal(h.calls.length,count+1);assert.deepEqual(h.calls.at(-1),
    [`/api/projects/${project}/official-publications/${pub}/queue/${planId}/cancel`,{expected_policy_sha256:sha}]);assert.equal(h.get('cancel').disabled,true);assert.match(h.messages.at(-1)[0],/quyền gửi.*giữ/);});
test('foreign rows runtime malformed pages and relabelled mock outcomes are rejected',async()=>{const h=harness();h.handler(async()=>({...runtime(true),workspace_id:'wsp_foreign'}));await h.controller.readConfig();assert.equal(h.get('create').disabled,true);
  h.handler(async()=>page([{...row(),project_id:'f'.repeat(32)}]));await h.controller.readHistory();assert.equal(h.get('history').children.length,0);
  const bad={...row(),step_count:1,steps:[{plan_id:planId,publication_id:pub,workspace_id:workspace,project_id:project,ordinal:1,result:{mock:false,published:true,mock_publication_complete:false,receipt_sha256:sha}}]};
  h.handler(async()=>page([bad]));await h.controller.readHistory();assert.equal(h.get('history').children.length,0);assert.match(h.messages.at(-1)[0],/chế độ/);});
test('late response cannot cross publication grant project workspace or role changes',async()=>{for(const change of [h=>h.state.project.id='f'.repeat(32),h=>h.state.workspace_id='wsp_foreign',h=>h.state.canManage=false,h=>h.binding({publication:{...publication(),approval_id:'nopa_'+'f'.repeat(32)},dispatch:null})]){
  const h=harness();let release;h.handler(()=>new Promise(resolve=>{release=resolve;}));const pending=h.controller.readConfig();change(h);h.controller.sync();release(runtime(true));await pending;
  assert.equal(h.get('create').disabled,true);assert.equal(h.messages.length,0);assert.equal(h.state.busy,false);}});
test('past malformed unbounded or absent acknowledgement cannot create a request',async()=>{const h=harness();await h.controller.readConfig();times(h);const count=h.calls.length;
  for(const [field,value]of [['max','0'],['max','101'],['interval','0'],['interval','3601'],['start','2020-01-01T12:00:00'],['start','not-a-date']]){times(h);h.get('max').value='10';h.get('interval').value='30';h.get(field).value=value;await h.controller.createPlan();assert.equal(h.calls.length,count);}
  times(h);h.get('max').value='10';h.get('interval').value='30';h.get('ack').checked=false;await h.controller.createPlan();assert.equal(h.calls.length,count);});
