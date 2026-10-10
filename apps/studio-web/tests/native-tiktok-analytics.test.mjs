import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {initializeNativeOfficialAnalytics} from '../native-official-analytics.mjs';
import {initializeNativeOfficialRefresh,validateOfficialRefreshPlan} from '../native-official-refresh.mjs';
import {initializeNativeOfficialWinners} from '../native-official-winners.mjs';
import {analyticsCounterBinding,analyticsCounterResult,analyticsPublic,analyticsReportLabel} from '../native-platform-analytics.mjs';

// Public DTOs captured from signed loopback HTTP; provider and media are explicit fixtures.
const F=JSON.parse(readFileSync(new URL('./fixtures/native-tiktok-analytics-v2.json',import.meta.url),'utf8'));
const clone=v=>structuredClone(v),post=F.source.remote_post_ids[0],other=F.source.remote_post_ids[1];
function page(kind,items){return {schema_version:'native-official-analytics-'+(kind==='refresh'?'refresh-':'')+'page-v1',
  workspace_id:F.workspace_id,project_id:F.project.id,publication_id:F.publication.publication_id,
  items,next_cursor:null,truncated:false,publishing_enabled:false,token_returned:false};}
function harness(kind='analytics'){
  const nodes=new Map();class Node{constructor(){this.children=[];this.value='';this.checked=false;this.dataset={};this.listeners={};this.textContent='';}
    set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,v){this.listeners[k]=v;}}
  const root={createElement:()=>new Node(),getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);}},
    prefix=kind==='refresh'?'native-official-refresh-':'native-official-analytics-',get=id=>{assert.ok(nodes.has(prefix+id),id);return nodes.get(prefix+id);},
    state={workspace_id:F.workspace_id,project:clone(F.project),canManage:true,dirty:false,busy:false,active:false},calls=[],messages=[];
  let current=clone(kind==='refresh'?F.plan_done:F.manual_done),binding={publication:clone(F.publication)},handler,count=0;
  const defaultHandler=async(path,body)=>{
    if(path==='/api/connections/official-analytics-refresh')return clone(F.refresh_runtime);
    if(path==='/api/connections/official-analytics')return clone(F.runtime);
    if(path.includes('/source/'))return clone(F.source);
    if(body){current=clone(kind==='refresh'?F.plan_created:F.manual_created);return current;}
    if(path.includes('?'))return page(kind,[current]);return current;
  };handler=defaultHandler;
  const common={root,getState:()=>state,getBinding:()=>binding,api:async(...v)=>{calls.push(v);return handler(...v);},onMessage:(...v)=>messages.push(v),
    onWorking:v=>{state.busy=v;},uuid:()=> 'explicit-tiktok-test-key-'+(++count),now:()=>Date.parse(F.plan_created.policy.request.start_at)-1000};
  const controller=kind==='refresh'?initializeNativeOfficialRefresh(common):initializeNativeOfficialAnalytics(common);
  return {controller,state,calls,messages,get,nodes,root,common,defaultHandler,handler:v=>{handler=v;},current:v=>{current=clone(v);},binding:v=>{binding=v;}};
}
function acknowledge(h){h.get('ack').checked=h.get('mock-ack').checked=true;}
async function ready(h){await h.controller.readSource();await h.controller.readConfig();acknowledge(h);}
function planInputs(h){const r=F.plan_created.policy.request;h.get('post').value=r.remote_post_id;
  for(const[k,v]of Object.entries({start:r.start_at,deadline:r.deadline,runs:r.max_runs,interval:r.interval_seconds,valid:r.valid_for_seconds}))h.get(k).value=String(v);
  h.get('background').checked=true;acknowledge(h);}
const text=n=>[n.textContent??'',...n.children.map(text)].join(' ');

test('captured public counter DTO has two actual post choices and no provider or audience acceptance',async()=>{
  assert.equal(F.real_provider_acceptance,false);assert.equal(F.owner_uat,false);assert.equal(F.source.metric_scope,'cumulative_video_counters');
  const h=harness();assert.equal(h.calls.length,0);await h.controller.readSource();assert.equal(h.get('post').value,'');
  assert.deepEqual(h.get('post').children.map(n=>n.value),['',post,other]);assert.match(h.get('status').textContent,/Bộ đếm lũy kế/);
  assert.equal(h.controller.currentBinding().sync,null);assert.equal(h.get('create').disabled,true);
});
test('multiple IDs require explicit receipt selection; provider job and foreign post never dispatch',async()=>{
  const h=harness();await ready(h);for(const value of['',F.publication.receipt.provider_job_id,'7391000000000000003']){
    h.get('post').value=value;const before=h.calls.length;await h.controller.createRead();assert.equal(h.calls.length,before);}
  h.get('post').value=post;await h.controller.createRead();assert.equal(h.controller.currentBinding().sync.sync_id,F.manual_created.sync_id);
  const sent=h.calls.at(-1)[1];assert.equal(sent.query,null);assert.equal(sent.metric_scope,'cumulative_video_counters');assert.equal(sent.remote_post_id,post);
  assert.equal(sent.schema_version,'native-official-analytics-request-v2');assert.equal(sent.acknowledged_read_only,true);
});
test('hidden dates and revenue do not become counter report authority and unknown outcome retains its key',async()=>{
  const h=harness();await ready(h);h.get('post').value=post;h.get('start').value='2020-01-01';h.get('end').value='2030-01-01';h.get('revenue').checked=true;
  h.handler(async()=>{throw Error('Explicit unknown fixture response');});await h.controller.createRead();const sent=h.calls.at(-1)[1];
  assert.equal(sent.query,null);assert.equal(Object.hasOwn(sent,'include_revenue'),false);h.controller.prepareNew();acknowledge(h);h.handler(h.defaultHandler);
  await h.controller.createRead();assert.equal(h.calls.at(-1)[1].request_key,sent.request_key);assert.ok(h.controller.currentBinding().sync);
});
test('immutable counter history displays zero and missing values separately without a date window',async()=>{
  const h=harness();await h.controller.readSource();await h.controller.readHistory();await h.controller.readStored();assert.equal(h.messages.length,0);
  assert.equal(h.controller.currentBinding().sync.result.metrics.views,0);assert.equal(h.controller.currentBinding().sync.result.metrics.watch_time,null);
  assert.match(text(h.get('metrics')),/Chưa có/);assert.match(h.get('status').textContent,/lũy kế/);
  assert.match(analyticsReportLabel(F.manual_done.result),/không phải báo cáo theo khoảng ngày/);
});
test('receipt list substitutions, private fields and unknown source schemas never establish a binding',async()=>{
  for(const mutate of[v=>{v.remote_post_ids=[post];},v=>{v.remote_post_ids=[post,post];},v=>{v.schema_version='native-official-analytics-publication-binding-v1';},v=>{v.token_path='EXPLICIT PRIVATE FIXTURE';}]){
    const h=harness(),source=clone(F.source);mutate(source);h.handler(async()=>source);await h.controller.readSource();
    assert.equal(h.get('history-read').disabled,true);assert.equal(h.messages.length,1);
  }
  assert.throws(()=>analyticsPublic({evidence:{access_token:'EXPLICIT FIXTURE'}}));
  assert.doesNotThrow(()=>analyticsPublic({actor:{token_id:'opaque-reference'},credential_alias:'read-alias',token_returned:false}));
});
test('counter snapshots reject invented retention, report dates, numeric strings and foreign post evidence',async()=>{
  for(const mutate of[v=>{v.result.metrics.completion_rate=.9;},v=>{v.result.metrics.views='0';},v=>{v.result.evidence.query={start_date:'2026-10-01'};},
    v=>{v.result.evidence.owned_video_returned=false;},v=>{v.result.remote_post_id=other;},v=>{v.result.provider_key='youtube-analytics-api';}]){
    const h=harness(),row=clone(F.manual_done);mutate(row);await h.controller.readSource();h.current(row);await h.controller.readHistory();
    assert.equal(h.controller.currentBinding().sync,null);assert.equal(h.messages.length,1);
  }
  assert.doesNotThrow(()=>analyticsCounterResult(F.manual_done.result,F.manual_done.snapshot.request));
});
test('viewer reads stored counters while create, config and cancel stay local and disabled',async()=>{
  const h=harness();h.state.canManage=false;h.controller.sync();await h.controller.readSource();await h.controller.readHistory();await h.controller.readStored();
  const count=h.calls.length;await h.controller.readConfig();await h.controller.createRead();await h.controller.cancelRead();assert.equal(h.calls.length,count);
  assert.ok(h.calls.every(([,body])=>!body));assert.equal(h.controller.currentBinding().sync.result.metrics.views,0);
});
test('late source responses cannot cross workspace, project or role',async()=>{
  for(const change of[h=>{h.state.workspace_id='wsp_foreign';},h=>{h.state.project.id='9'.repeat(32);},h=>{h.state.canManage=false;}]){
    const h=harness();let release;h.handler(()=>new Promise(resolve=>{release=resolve;}));const pending=h.controller.readSource();change(h);h.controller.sync();release(clone(F.source));await pending;
    assert.equal(h.get('detail').textContent,'');assert.equal(h.controller.currentBinding().sync,null);assert.equal(h.messages.length,0);
  }
});
test('finite refresh requires separate background acknowledgement and selected actual post',async()=>{
  const h=harness('refresh');await ready(h);planInputs(h);h.get('background').checked=false;const count=h.calls.length;
  await h.controller.createPlan();assert.equal(h.calls.length,count);h.get('background').checked=true;h.get('post').value='';await h.controller.createPlan();assert.equal(h.calls.length,count);
  h.get('post').value=other;await h.controller.createPlan();const sent=h.calls.at(-1)[1];assert.equal(sent.query,null);assert.equal(sent.remote_post_id,other);
  assert.equal(sent.acknowledged_background_reads,true);assert.equal(sent.max_runs,1);assert.ok(h.controller.currentBinding().plan);
});
test('restored finite history retains selected post, child read and two provider response references',async()=>{
  const h=harness('refresh');h.state.canManage=false;h.controller.sync();await h.controller.readSource();await h.controller.readHistory();await h.controller.readStored();
  assert.equal(h.messages.length,0);assert.equal(h.controller.currentBinding().plan.status,'completed');const child=h.controller.currentBinding().plan.occurrences[0].sync;
  assert.equal(child.result.response_refs.length,2);assert.equal(child.result.remote_post_id,other);assert.equal(child.result.evidence.query,null);
  assert.equal(h.get('observations').children.length,1);assert.ok(h.calls.every(([,body])=>!body));
});
test('finite plan rejects relabeled child counters, made up intervals and extra response operations',()=>{
  const binding={...F.source,target_binding_sha256:F.publication.snapshot.target_binding_sha256};assert.doesNotThrow(()=>validateOfficialRefreshPlan(F.plan_done,binding));
  for(const mutate of[v=>{v.occurrences[0].sync.result.metrics.watch_time=42;},v=>{v.occurrences[0].sync.snapshot.request.remote_post_id=post;},
    v=>{v.policy.request.query={start_date:'2026-10-01',end_date:'2026-10-02',include_revenue:false};},v=>{v.occurrences[0].sync.result.response_refs.push(clone(v.occurrences[0].sync.result.response_refs[0]));}]){
    const value=clone(F.plan_done);mutate(value);assert.throws(()=>validateOfficialRefreshPlan(value,binding));
  }
  assert.deepEqual(analyticsCounterBinding(F.source,F.publication),[post,other]);
});
test('counter winner can save only a scoped recommendation and honestly remains insufficient',async()=>{
  const h=harness();h.current(F.latest);await h.controller.readSource();await h.controller.readHistory();
  h.handler(async(path)=>path.includes('/connections/')?clone(F.winner_runtime):path.includes('/source/')?clone(F.winner_source):clone(F.winner));
  const w=initializeNativeOfficialWinners({...h.common,getBinding:()=>h.controller.currentBinding()});await w.readSource();await w.readConfig();
  h.root.getElementById('native-official-winners-ack').checked=h.root.getElementById('native-official-winners-mock-ack').checked=true;await w.createAssessment();
  assert.equal(h.messages.length,0);assert.equal(w.currentBinding().assessment.assessment.state,'insufficient_data');
  assert.equal(w.currentBinding().assessment.assessment.basis,'matching_native_official_cumulative_counter_scope');
  assert.equal(w.currentBinding().assessment.snapshot.candidate.scope.query,null);assert.equal(w.currentBinding().assessment.automatic_action,false);
  assert.equal(F.learning.observation_count,0);assert.equal(F.learning.status,'insufficient_data');
});
