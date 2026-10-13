import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {stockPlanningRole,stockPlanningPlans,validateStockPlanning,validateStockPlan,validateStockHistory,stockDeadline,
  stockPlanningPayload,stockTransitionMatches,initializeStockPlanningReview} from '../stock-planning-review.mjs';

// Captured authenticated ASGI + isolated SQLite + explicit MockTransport. The
// planner's fake source metadata and contract ASR/Vision are not real acceptance.
const captured=JSON.parse(readFileSync(new URL('./fixtures/sql-stock-planner/read.json',import.meta.url),'utf8'));
const clone=structuredClone;
const scope=state=>JSON.stringify([state.workspaceId,state.projectId,state.principal.subject,state.principal.token_id,
  state.principal.expires_at,stockPlanningRole(state)]);
function operation(state,record,kind='retry'){return {schema_version:'stock-planning-pending.v1',scope:scope(state),planId:record.plan.media_plan_id,kind,
  body:{expected_version:record.plan.version,binding_sha256:record.status.binding_sha256},before:clone(record.status)};}
function harness({record=captured.waiting,transport,storageMap=new Map(),storageImpl}={}){
  class Element{
    constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.listeners={};this.value='';this.checked=false;this.disabled=false;}
    append(...nodes){this.children.push(...nodes);}prepend(...nodes){this.children.unshift(...nodes);}replaceChildren(...nodes){this.children=nodes;}
    setAttribute(k,v){this.attributes[k]=String(v);}addEventListener(k,v){this.listeners[k]=v;}
    get disabled(){return this._disabled;}set disabled(v){this._disabled=Boolean(v);}
  }
  const all=node=>[node,...node.children.flatMap(all)],dom={createElement:tag=>new Element(tag)},root=dom.createElement('details');
  const state=clone(captured.state);state.mediaPlans=[clone(record.plan)];let server=clone(record),now=captured.clock;
  const calls=[],messages=[],adopted=[],memory=storageImpl??{getItem:k=>storageMap.get(k)??null,setItem:(k,v)=>storageMap.set(k,v),removeItem:k=>storageMap.delete(k)};
  const api=async(path,options)=>{
    const body=options?.body?JSON.parse(options.body):null;calls.push({path,body,method:options?.method??'GET'});
    if(transport){const value=await transport(path,body,{state,server,setServer:v=>server=clone(v)});if(value!==undefined)return value;}
    if(path==='/api/v1/capabilities')return clone(captured.capabilities);
    if(path.endsWith('/stock-search/history'))return clone(server.history);
    if(path.endsWith('/stock-search'))return clone(server.status);
    if(body){server=clone(path.endsWith('/cancel')?captured.cancelled:captured.succeeded);return clone(server.plan);}
    return clone(server.plan);
  };
  const controller=initializeStockPlanningReview({root,dom,api,getState:()=>state,storage:memory,clock:()=>now,
    onMessage:(...args)=>messages.push(args),onPlanUpdated:async plan=>{adopted.push(plan.media_plan_id);state.mediaPlans=[clone(plan)];}});
  const get=name=>all(root).find(n=>Object.hasOwn(n.attributes,'data-stock-planning-'+name));
  const click=async name=>get(name).listeners.click();
  const ack=()=>{get('ack').checked=true;get('ack').listeners.change();};
  return {state,controller,root,calls,messages,adopted,storageMap,get,click,ack,all:()=>all(root),setNow:n=>now=n,setServer:v=>server=clone(v)};
}

test('actual captured SQL DTOs retain null cost and structural version/binding lineage',()=>{
  assert.match(captured.fixture_notice,/MockTransport.*No real provider/);assert.equal(captured.real_provider_calls,0);
  for(const key of ['waiting','succeeded','before_cancel','cancelled']){
    const record=captured[key];assert.equal(validateStockPlan(record.plan,captured.state),record.plan);
    assert.equal(validateStockPlanning(record.status),record.status);assert.equal(validateStockHistory(record.history,record.plan,captured.state),record.history);
    assert.equal(record.status.actual_cost_vnd,null);assert.equal(record.status.owner_approval_inferred,false);
    assert.equal(record.status.publishing_enabled,false);
  }
});
test('constructor and sync issue no reads, provider calls or writes',()=>{
  const h=harness();h.controller.sync();assert.deepEqual(h.calls,[]);assert.equal(h.get('retry').disabled,true);
  assert.equal(h.get('cancel').disabled,true);assert.equal(h.controller.isPending(),false);
});
test('scoped plan picker ignores foreign workspace/project and unmanaged plans',()=>{
  const state=clone(captured.state),good=state.mediaPlans[0];state.mediaPlans.push({...good,workspace_id:'wsp_foreign'},
    {...good,project_id:'prj_foreign'},{...good,stock_planning:null});assert.equal(stockPlanningPlans(state).length,1);
});
test('role hierarchy includes workspace, wildcard and slug while writes reject viewer/dirty/busy',()=>{
  const state=clone(captured.state);state.principal.platform_role=null;state.principal.workspace_roles={'*':'viewer',[state.workspaceId]:'editor'};
  assert.equal(stockPlanningRole(state),'editor');state.workspaceSlug='explicit-fixture';state.principal.workspace_roles['slug:explicit-fixture']='reviewer';
  assert.equal(stockPlanningRole(state),'reviewer');
  for(const change of [s=>{s.principal.platform_role='viewer';s.principal.workspace_roles={};},s=>s.busy=true,s=>s.dirty=true]){
    const v=clone(captured.state);change(v);assert.throws(()=>stockPlanningPayload(v,captured.waiting.plan,'retry',true,captured.clock+61));
  }
});
test('UTC and Vietnam timezone are explicit; missing dates remain unknown',()=>{
  assert.match(stockDeadline(1800000060),/Z \(UTC\)/);assert.match(stockDeadline(1800000060),/Việt Nam, UTC\+07:00/);
  assert.equal(stockDeadline(null),'Chưa có mốc thời gian');assert.throws(()=>stockDeadline(NaN));
});
test('future waiting/running/terminal cannot restart and cancel requires acknowledgement',()=>{
  assert.throws(()=>stockPlanningPayload(captured.state,captured.waiting.plan,'retry',true,captured.clock));
  assert.throws(()=>stockPlanningPayload(captured.state,captured.succeeded.plan,'retry',true,captured.clock+100));
  assert.throws(()=>stockPlanningPayload(captured.state,captured.cancelled.plan,'cancel',true,captured.clock+200));
  assert.throws(()=>stockPlanningPayload(captured.state,captured.waiting.plan,'cancel',false,captured.clock));
  const running=clone(captured.waiting.plan);const raw=running.provenance.stock_planner_execution;
  raw.status='running';raw.next_at=null;raw.lease_until=captured.clock+300;
  Object.assign(running.stock_planning,{status:'running',next_at:null,lease_until:raw.lease_until,retryable:false});
  assert.throws(()=>stockPlanningPayload(captured.state,running,'retry',true,captured.clock+400));
  assert.deepEqual(stockPlanningPayload(captured.state,captured.waiting.plan,'cancel',true,captured.clock),{
    expected_version:captured.waiting.plan.version,binding_sha256:captured.waiting.status.binding_sha256});
});
test('paid/publishing/foreign/history promotions and inconsistent counts are rejected',()=>{
  for(const mutate of [p=>p.stock_planning.actual_cost_vnd='0',p=>p.stock_planning.paid_operations=1,
    p=>p.stock_planning.completed_searches=p.stock_planning.total_searches+1,p=>p.workspace_id='wsp_foreign',
    p=>p.provenance.stock_planner_execution.binding.provider.mode='invented',p=>p.publishing_blocked=false]){
    const p=clone(captured.waiting.plan);mutate(p);assert.throws(()=>validateStockPlan(p,captured.state));
  }
  for(const mutate of [h=>h[1].evidence.before.project_id='prj_foreign',h=>h[1].evidence.owner_approval_inferred=true,
    h=>h[1].version++,h=>h[1].evidence.after.stock_planning.binding.provider.paid=true,h=>h[1].action='<script>']){
    const h=clone(captured.waiting.history);mutate(h);assert.throws(()=>validateStockHistory(h,captured.waiting.plan,captured.state));
  }
});
test('explicit read renders safe counts and fixture notice without private query/source content',async()=>{
  const h=harness();await h.click('read');assert.equal(h.calls.length,4);assert.equal(h.calls.every(c=>c.method==='GET'),true);
  assert.match(h.get('origin').textContent,/FIXTURE/);assert.match(h.get('cost').textContent,/chưa có dữ liệu/);
  assert.match(h.get('facts').textContent,/1\/4/);assert.match(h.get('deadline').textContent,/UTC\+07:00/);
  const text=h.all().map(n=>n.textContent??'').join('\n');
  for(const request of captured.waiting.plan.provenance.stock_planner_execution.binding.searches)assert.equal(text.includes(request.query),false);
  assert.equal(text.includes(captured.waiting.plan.provenance.stock_planner_execution.binding.inputs.source_asset.object_key),false);
  assert.equal(h.get('retry').disabled,true);assert.equal(h.get('cancel').disabled,true);
});
test('due acknowledged retry sends only frozen CAS and adopts verified history transition',async()=>{
  const h=harness();await h.click('read');h.setNow(captured.clock+61);h.ack();await h.click('retry');
  const writes=h.calls.filter(c=>c.method==='POST');assert.equal(writes.length,1);
  assert.deepEqual(writes[0].body,{expected_version:captured.waiting.plan.version,binding_sha256:captured.waiting.status.binding_sha256});
  assert.equal(h.controller.isPending(),false);assert.equal(h.state.mediaPlans[0].stock_planning.status,'succeeded');assert.equal(h.get('retry').disabled,true);
});
test('explicit cancellation uses current read and cannot claim remote provider cancellation or rights approval',async()=>{
  const h=harness({record:captured.before_cancel});await h.click('read');h.ack();await h.click('cancel');
  assert.equal(h.calls.filter(c=>c.method==='POST').length,1);assert.equal(h.controller.isPending(),false);
  assert.match(h.get('facts').textContent,/Đã hủy lịch/);assert.equal(h.get('cancel').disabled,true);
  assert.equal(h.state.mediaPlans[0].stock_planning.owner_approval_inferred,false);
});
test('unconfigured/404/invalid history stays read-only and never dispatches retry',async()=>{
  for(const failure of [Object.assign(Error('private-source-path'),{status:503,detail:{error:{code:'STOCK_PLANNER_NOT_CONFIGURED'}}}),null]){
    const h=harness({transport:(path)=>{if(path.endsWith('/stock-search/history')){if(failure)throw failure;return [];}}});
    await h.click('read');h.ack();h.setNow(captured.clock+61);await h.click('retry');assert.equal(h.calls.some(c=>c.method==='POST'),false);
    assert.equal(h.get('retry').disabled,true);assert.equal(h.messages.some(m=>m[0].includes('private-source-path')),false);
  }
});
test('lost retry response retains same CAS through unchanged read and explicit resubmit',async()=>{
  let attempts=0;const h=harness({transport:(path,body,ctx)=>{if(body&&path.endsWith('/retry')){
    if(++attempts===1)throw Error('EXPLICIT LOST RESPONSE');ctx.setServer(captured.succeeded);return clone(captured.succeeded.plan);
  }}});
  await h.click('read');h.setNow(captured.clock+61);h.ack();await h.click('retry');assert.equal(h.controller.isPending(),true);
  await h.click('reconcile');assert.equal(h.controller.isPending(),true);await h.click('retry');
  const writes=h.calls.filter(c=>c.method==='POST');assert.equal(writes.length,2);assert.deepEqual(writes[0],writes[1]);assert.equal(h.controller.isPending(),false);
});
test('reply lost after actual captured transition is reconciled by GET without another POST',async()=>{
  const h=harness({transport:(path,body,ctx)=>{if(body){ctx.setServer(captured.succeeded);throw Error('EXPLICIT LOST SUCCESS');}}});
  await h.click('read');h.setNow(captured.clock+61);h.ack();await h.click('retry');assert.equal(h.controller.isPending(),true);
  await h.click('reconcile');assert.equal(h.controller.isPending(),false);assert.equal(h.calls.filter(c=>c.method==='POST').length,1);
});
test('mere version advancement or another actor/binding cannot prove this pending action',()=>{
  const pending=operation(captured.state,captured.waiting);assert.equal(stockTransitionMatches(pending,captured.succeeded.plan,captured.succeeded.history,captured.state),true);
  assert.equal(stockTransitionMatches({...pending,scope:'other-actor'},captured.succeeded.plan,captured.succeeded.history,captured.state),false);
  const changed=clone(captured.succeeded.history);changed.find(e=>e.version===pending.body.expected_version+1).action='deferred';
  assert.equal(stockTransitionMatches(pending,captured.succeeded.plan,changed,captured.state),false);
  assert.equal(stockTransitionMatches({...pending,body:{...pending.body,binding_sha256:'b'.repeat(64)}},captured.succeeded.plan,captured.succeeded.history,captured.state),false);
});
test('pending survives panel reconstruction without inventing a new request body',async()=>{
  const memory=new Map();const h=harness({storageMap:memory,transport:(_path,body)=>{if(body)throw Error('EXPLICIT LOST RESPONSE');}});
  await h.click('read');h.setNow(captured.clock+61);h.ack();await h.click('retry');assert.equal(memory.size,1);
  const serialized=[...memory.values()][0];assert.equal(serialized.includes('query'),false);assert.equal(serialized.includes('source_asset'),false);
  h.controller.dispose();const restored=harness({storageMap:memory});await restored.click('read');assert.equal(restored.controller.isPending(),true);
  restored.setNow(captured.clock+61);restored.ack();await restored.click('retry');
  assert.deepEqual(restored.calls.find(c=>c.method==='POST').body,h.calls.find(c=>c.method==='POST').body);assert.equal(memory.size,0);
});
test('storage failure prevents dispatch, preserving safety without logging private error content',async()=>{
  const h=harness({storageImpl:{getItem:()=>null,setItem:()=>{throw Error('PRIVATE PATH OR TOKEN');},removeItem(){}}});
  await h.click('read');h.setNow(captured.clock+61);h.ack();await h.click('retry');assert.equal(h.calls.some(c=>c.method==='POST'),false);
  assert.equal(h.messages.some(m=>m[0].includes('PRIVATE PATH OR TOKEN')),false);
});
test('late read/write after project or role/source-plan drift cannot authorize controls or adopt old results',async()=>{
  let finish;const h=harness({transport:path=>path.endsWith('/stock-search/history')?new Promise(resolve=>finish=resolve):undefined});
  const reading=h.click('read');h.state.projectId='prj_foreign';h.controller.sync();finish(clone(captured.waiting.history));await reading;
  assert.equal(h.adopted.length,0);assert.equal(h.get('history').children.length,0);assert.equal(h.get('retry').disabled,true);
  let completed;const other=harness({transport:(_path,body)=>body?new Promise(resolve=>completed=resolve):undefined});
  await other.click('read');other.setNow(captured.clock+61);other.ack();const writing=other.click('retry');
  other.state.principal.platform_role='viewer';other.state.principal.workspace_roles={};other.controller.sync();completed(clone(captured.succeeded.plan));await writing;
  assert.equal(other.get('retry').disabled,true);assert.equal(other.state.mediaPlans[0].version,captured.waiting.plan.version);
});
test('dirty state, missing acknowledgement, future wait and concurrent clicks are guarded inside handlers',async()=>{
  const h=harness();await h.click('read');await h.click('cancel');assert.equal(h.calls.some(c=>c.method==='POST'),false);
  h.ack();await h.click('retry');assert.equal(h.calls.some(c=>c.method==='POST'),false);
  h.state.dirty=true;h.setNow(captured.clock+61);await h.click('retry');assert.equal(h.calls.some(c=>c.method==='POST'),false);
  h.state.dirty=false;let finish;const running=harness({transport:(_path,body)=>body?new Promise(resolve=>finish=resolve):undefined});
  await running.click('read');running.setNow(captured.clock+61);running.ack();const first=running.click('retry');await running.click('retry');
  assert.equal(running.calls.filter(c=>c.method==='POST').length,1);finish(clone(captured.succeeded.plan));await first;
});

test('a 4xx history read after accepted POST cannot discard its unknown-result request',async()=>{
  let accepted=false,failRead=true;
  const h=harness({transport:(path,body,ctx)=>{
    if(body){accepted=true;ctx.setServer(captured.succeeded);return clone(captured.succeeded.plan);}
    if(accepted&&failRead&&path.endsWith('/stock-search/history'))throw Object.assign(Error('PRIVATE PROVIDER DATA'),{status:429});
  }});
  await h.click('read');h.setNow(captured.clock+61);h.ack();await h.click('retry');
  assert.equal(h.controller.isPending(),true);assert.equal(h.storageMap.size,1);
  assert.equal(h.calls.filter(c=>c.method==='POST').length,1);assert.equal(h.messages.some(m=>m[0].includes('PRIVATE PROVIDER DATA')),false);
  failRead=false;await h.click('reconcile');assert.equal(h.controller.isPending(),false);
  assert.equal(h.calls.filter(c=>c.method==='POST').length,1);
});

test('a direct CAS rejection clears the pending request without automatically sending another',async()=>{
  const h=harness({transport:(_path,body)=>{if(body)throw Object.assign(Error('PRIVATE REJECTION DATA'),{status:409});}});
  await h.click('read');h.setNow(captured.clock+61);h.ack();await h.click('retry');
  assert.equal(h.controller.isPending(),false);assert.equal(h.storageMap.size,0);
  assert.equal(h.calls.filter(c=>c.method==='POST').length,1);assert.equal(h.get('retry').disabled,true);
});

test('same subject with rotated token or expiry cannot inherit pending authority',async()=>{
  for(const field of ['token_id','expires_at']){
    const h=harness({transport:(_path,body)=>{if(body)throw Error('EXPLICIT LOST RESPONSE');}});
    await h.click('read');h.setNow(captured.clock+61);h.ack();await h.click('retry');assert.equal(h.controller.isPending(),true);
    h.state.principal[field]=field==='token_id'?'rotated-fixture-token':1234567890;h.controller.sync();await h.click('read');h.ack();await h.click('retry');
    assert.equal(h.calls.filter(c=>c.method==='POST').length,1);assert.equal(h.get('retry').disabled,true);
    assert.equal(h.storageMap.size,1);
  }
});

test('locally changed plan revision during a read is never adopted or used for a write',async()=>{
  let finish;const h=harness({transport:path=>path.endsWith('/stock-search/history')?new Promise(resolve=>finish=resolve):undefined});
  const reading=h.click('read');h.state.mediaPlans[0].version++;h.controller.sync();finish(clone(captured.waiting.history));await reading;
  assert.equal(h.adopted.length,0);assert.equal(h.get('retry').disabled,true);h.setNow(captured.clock+61);h.ack();await h.click('retry');
  assert.equal(h.calls.some(c=>c.method==='POST'),false);
});

test('saved pending before-state must equal the exact claimed history boundary',()=>{
  const pending=operation(captured.state,captured.waiting);pending.before.provider_calls++;
  assert.equal(stockTransitionMatches(pending,captured.succeeded.plan,captured.succeeded.history,captured.state),false);
});

test('server human-write disabled permits explicit read but no retry or cancel',async()=>{
  const h=harness({transport:path=>path==='/api/v1/capabilities'?{...captured.capabilities,human_write_enabled:false}:undefined});
  await h.click('read');h.setNow(captured.clock+61);h.ack();await h.click('retry');await h.click('cancel');
  assert.equal(h.calls.filter(c=>c.method==='GET').length,4);assert.equal(h.calls.some(c=>c.method==='POST'),false);
  assert.equal(h.get('retry').disabled,true);assert.equal(h.get('cancel').disabled,true);
});
