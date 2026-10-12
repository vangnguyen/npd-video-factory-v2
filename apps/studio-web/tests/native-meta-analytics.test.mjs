import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {initializeNativeOfficialAnalytics} from '../native-official-analytics.mjs';
import {initializeNativeOfficialRefresh,validateOfficialRefreshPlan} from '../native-official-refresh.mjs';
import {analyticsCounterResult,analyticsCounterBinding,analyticsMetaProfile} from '../native-platform-analytics.mjs';
const fixtures=JSON.parse(fs.readFileSync(new URL('./fixtures/native-meta-analytics-v1.json',import.meta.url),'utf8'));
const clone=v=>structuredClone(v);

function harness(F,kind='analytics'){
  const nodes=new Map();class Node{constructor(){this.children=[];this.value='';this.checked=false;this.dataset={};this.listeners={};this.textContent='';}
    set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,v){this.listeners[k]=v;}}
  const root={createElement:()=>new Node(),getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);}},
    prefix=kind==='refresh'?'native-official-refresh-':'native-official-analytics-',get=id=>{assert.ok(nodes.has(prefix+id),id);return nodes.get(prefix+id);},
    state={workspace_id:F.workspace_id,project:clone(F.project),canManage:true,dirty:false,busy:false,active:false},calls=[],messages=[];
  let current=clone(kind==='refresh'?F.plan_done:F.manual_done),handler,count=0;
  const defaultHandler=async(path,body)=>{
    if(path==='/api/connections/official-analytics-refresh')return clone(F.refresh_runtime);
    if(path==='/api/connections/official-analytics')return clone(F.runtime);
    if(path.includes('/source/'))return clone(F.source);
    if(body){current=clone(kind==='refresh'?F.plan_created:F.manual_created);return current;}
    if(path.includes('?'))return {schema_version:kind==='refresh'?'native-official-analytics-refresh-page-v1':'native-official-analytics-page-v1',workspace_id:F.workspace_id,
      project_id:F.project.id,publication_id:F.publication.publication_id,items:[current],next_cursor:null,truncated:false,publishing_enabled:false,token_returned:false};
    return current;
  };handler=defaultHandler;
  const common={root,getState:()=>state,getBinding:()=>({publication:clone(F.publication)}),api:async(...v)=>{calls.push(v);return handler(...v);},onMessage:(...v)=>messages.push(v),
    onWorking:v=>{state.busy=v;},uuid:()=> 'explicit-meta-test-key-'+(++count),now:()=>Date.parse(F.plan_created.policy.request.start_at)-1000};
  const controller=kind==='refresh'?initializeNativeOfficialRefresh(common):initializeNativeOfficialAnalytics(common);
  return {controller,state,calls,messages,get,handler:v=>{handler=v;},defaultHandler,current:v=>{current=clone(v);}};
}

for(const[platform,F]of Object.entries(fixtures)){
  test(platform+' captured domain DTO drives manual read with null reporting dates and explicit mock consent',async()=>{
    assert.equal(F.actual_HTTP_tested,false);assert.equal(F.owner_uat,false);
    const h=harness(F);assert.equal(h.calls.length,0);await h.controller.readSource();await h.controller.readConfig();
    h.get('ack').checked=h.get('mock-ack').checked=true;h.get('start').value='2020-01-01';h.get('end').value='2030-01-01';h.get('revenue').checked=true;
    await h.controller.createRead();assert.equal(h.messages.length,0,JSON.stringify(h.messages));
    const sent=h.calls.at(-1)[1];assert.equal(sent.schema_version,'native-official-analytics-request-v3');assert.equal(sent.platform,platform);
    assert.equal(sent.query,null);assert.equal(sent.remote_post_id,F.source.remote_post_id);assert.equal(sent.acknowledged_protocol_mock,true);
    assert.equal(h.controller.currentBinding().sync.sync_id,F.manual_created.sync_id);
  });
  test(platform+' scoped stored history renders counts without invented time or revenue',async()=>{
    const h=harness(F);await h.controller.readSource();await h.controller.readHistory();assert.equal(h.messages.length,0,JSON.stringify(h.messages));
    assert.equal(h.controller.currentBinding().sync.result.metrics.views,123);assert.equal(h.controller.currentBinding().sync.result.metrics.watch_time,null);
    assert.match(h.get('status').textContent,/chưa quan sát khán giả thật/);assert.doesNotMatch(h.get('status').textContent,/Khoảng báo cáo/);
    h.state.canManage=false;h.controller.sync();await h.controller.readSource();await h.controller.readHistory();assert.equal(h.get('create').disabled,true);
    const before=h.calls.length;await h.controller.createRead();assert.equal(h.calls.length,before);
  });
  test(platform+' receipt substitution and relabeled metric evidence are rejected',()=>{
    assert.deepEqual(analyticsCounterBinding(F.source,F.publication),[F.source.remote_post_id]);
    const profile=F.manual_done.snapshot.meta_read_profile;analyticsMetaProfile(profile,F.source.target);
    analyticsCounterResult(F.manual_done.result,F.manual_done.snapshot.request,profile);
    for(const change of [v=>{v.evidence.api_version='v999.0';},v=>{v.metrics.watch_time=1;},v=>{v.metrics.views='123';},v=>{v.evidence.query={start_date:'2026-01-01'};},v=>{v.evidence.returned_metrics=[];}]){
      const result=clone(F.manual_done.result);change(result);assert.throws(()=>analyticsCounterResult(result,F.manual_done.snapshot.request,profile));}
    const bad=clone(F.source);bad.remote_post_ids=['99999'];assert.throws(()=>analyticsCounterBinding(bad,F.publication));
  });
  test(platform+' finite refresh validates real exported child history and never grants publishing',async()=>{
    validateOfficialRefreshPlan(F.plan_done,F.source);
    const h=harness(F,'refresh');await h.controller.readSource();await h.controller.readConfig();
    const r=F.plan_created.policy.request;
    for(const[k,v]of Object.entries({start:r.start_at,deadline:r.deadline,runs:r.max_runs,interval:r.interval_seconds,valid:r.valid_for_seconds}))h.get(k).value=String(v);
    h.get('background').checked=h.get('ack').checked=h.get('mock-ack').checked=true;
    await h.controller.createPlan();assert.equal(h.messages.length,0,JSON.stringify(h.messages));
    assert.equal(h.calls.at(-1)[1].platform,platform);assert.equal(h.calls.at(-1)[1].query,null);
    const changed=clone(F.plan_done);changed.occurrences[0].sync.result.metrics.revenue=10;assert.throws(()=>validateOfficialRefreshPlan(changed,F.source));
  });
}
