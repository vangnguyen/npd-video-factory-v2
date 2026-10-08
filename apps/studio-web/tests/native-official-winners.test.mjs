import test from 'node:test';import assert from 'node:assert/strict';
import {initializeNativeOfficialWinners}from'../native-official-winners.mjs';
const workspace='wsp_official_winner_fixture',project='a'.repeat(32),pub='nopu_'+'b'.repeat(32),syncId='noas_'+'c'.repeat(32),resultId='noam_'+'d'.repeat(32),
  consentSha='e'.repeat(64),resultSha='f'.repeat(64),receiptSha='1'.repeat(64),policySha='2'.repeat(64),targetSha='3'.repeat(64),assessmentId='nowa_'+'4'.repeat(32);
const weights={view_velocity:.18,retention:.16,completion:.16,engagement:.13,shares:.08,saves:.07,ctr:.08,follower_conversion:.06,revenue_efficiency:.05,production_cost_efficiency:.03};
const policy=()=>({schema_version:'winner-channel-policy-v1',minimum_peer_posts:5,maximum_peer_posts:100,minimum_views:500,minimum_counter_interval_hours:6,minimum_weight_coverage:.4,winner_threshold:72,underperforming_threshold:38,weights:{...weights}});
const query=()=>({start_date:'2026-10-01',end_date:'2026-10-02',include_revenue:false});
const scope=()=>({workspace_id:workspace,target_binding_sha256:targetSha,platform:'youtube',provider_key:'youtube-analytics-api',mock:true,source_kind:'official_protocol_mock',source_external_call:false,query:query()});
const observation=()=>({status:'succeeded',sync_id:syncId,publication_id:pub,result_snapshot_id:resultId,snapshot_sha256:consentSha,
  result:{mock:true,source_kind:'official_protocol_mock',external_call:false,publication_receipt_sha256:receiptSha,evidence:{query:query()}}});
const source=()=>({schema_version:'native-official-winner-source-binding-v1',workspace_id:workspace,project_id:project,sync_id:syncId,publication_id:pub,result_snapshot_id:resultId,result_sha256:resultSha,
  consent_sha256:consentSha,publication_receipt_sha256:receiptSha,scope:scope(),mock:true,real_audience_observation:false,qualified:true,recommendation_only:true,automatic_action:false,publishing_enabled:false,token_returned:false});
const config=()=>({schema_version:'native-official-winner-capabilities-v1',workspace_id:workspace,default_policy:policy(),default_policy_sha256:policySha,maximum_candidate_rows:500,
  automatic_assessment:false,provider_calls_enabled:false,recommendation_only:true,automatic_action:false,publishing_enabled:false,token_returned:false});
const request=()=>({schema_version:'native-official-winner-request-v1',sync_id:syncId,expected_result_sha256:resultSha,policy:policy(),acknowledged_recommendation_only:true,acknowledged_protocol_mock:true});
function row(body=request()){
  const assessment={state:'insufficient_data',score:null,data_coverage:0,algorithm_version:'winner-channel-assessment-v1',basis:'matching_native_official_channel_report_scope',mock:true,
    source_kind:'official_protocol_mock',real_audience_observation:false,external_call:false,automatic_action:false,publishing_enabled:false,channel_baseline_verified:false,
    view_velocity_supported:false,publishing_age_hours:null,actual_publication_time:null,recommendations:['Review'],limitations:['Mock'],
    factors:Object.entries(weights).map(([factor,weight])=>({factor,weight,score:null,evidence:{raw_value:null,peer_median:null,peer_count:0,peer_snapshot_ids:[],policy_sha256:policySha}}))};
  return{schema_version:'native-official-winner-assessment-v1',assessment_id:assessmentId,workspace_id:workspace,project_id:project,publication_id:pub,sync_id:syncId,result_snapshot_id:resultId,
    snapshot_sha256:'5'.repeat(64),mock:true,real_audience_observation:false,recommendation_only:true,automatic_action:false,external_call:false,publishing_enabled:false,token_returned:false,peer_count:0,assessment,
    snapshot:{schema_version:'native-official-winner-snapshot-v1',workspace_id:workspace,project_id:project,publication_id:pub,sync_id:syncId,result_snapshot_id:resultId,recommendation_only:true,automatic_action:false,publishing_enabled:false,
      request:body,policy_sha256:policySha,candidate_rows_truncated:false,peers:[],candidate:{project_id:project,publication_id:pub,sync_id:syncId,result_snapshot_id:resultId,result_sha256:resultSha,consent_sha256:consentSha,publication_receipt_sha256:receiptSha,scope:scope()},assessment:structuredClone(assessment)}};
}
const page=(items,cursor=null)=>({schema_version:'native-official-winner-page-v1',workspace_id:workspace,project_id:project,publication_id:pub,items,next_cursor:cursor,recommendation_only:true,automatic_action:false,external_call:false,publishing_enabled:false,token_returned:false});
function harness(){const nodes=new Map();class Node{constructor(){this.children=[];this.value='';this.checked=false;this.dataset={};this.listeners={};this.max='';}set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}
  append(...v){this.children.push(...v);}replaceChildren(...v){this.children=[...v];}addEventListener(k,v){this.listeners[k]=v;}}
  const root={createElement:()=>new Node(),getElementById(v){if(!nodes.has(v))nodes.set(v,new Node());return nodes.get(v);}},get=id=>root.getElementById('native-official-winners-'+id),
    state={workspace_id:workspace,project:{id:project,revision:1},canManage:true,dirty:false,busy:false,active:false},calls=[],messages=[];let binding={sync:observation()},current=row(),handler,count=0;
  const defaultHandler=async(path,body)=>{if(path.includes('/connections/'))return config();if(path.includes('/source/'))return source();if(body){current=row(body);return current;}if(path.includes('?'))return page([current]);return current;};handler=defaultHandler;
  const controller=initializeNativeOfficialWinners({api:async(...args)=>{calls.push(args);return handler(...args);},root,getState:()=>({...state}),getBinding:()=>binding,
    onMessage:(...v)=>messages.push(v),onWorking:v=>{state.busy=v;},uuid:()=> 'explicit-winner-key-'+(++count)});
  return{controller,state,calls,get,messages,defaultHandler,handler:v=>{handler=v;},binding:v=>{binding=v;},current:v=>{current=v;}};
}
function ack(h){h.get('ack').checked=h.get('mock-ack').checked=true;}
async function ready(h){await h.controller.readSource();await h.controller.readConfig();ack(h);h.controller.controls();}

test('initialization makes no requests and assessment requires selected successful observation',async()=>{const h=harness();assert.equal(h.calls.length,0);assert.equal(h.get('minimum-views').value,'');assert.equal(h.get('create').disabled,true);
  h.binding({sync:{...observation(),status:'queued',result:null}});h.controller.sync();await h.controller.readSource();assert.equal(h.calls.length,0);assert.equal(h.get('source').disabled,true);});
test('explicit owner assessment uses server canonical result hash and policy with no provider polling',async()=>{const h=harness();await ready(h);assert.equal(h.get('create').disabled,false);await h.controller.createAssessment();
  assert.deepEqual(h.calls.at(-1),[`/api/projects/${project}/official-winners`,{...request(),request_key:'native-official-winner-explicit-winner-key-1'}]);assert.equal(h.calls.length,3);
  assert.equal(h.get('ack').checked,false);assert.equal(h.get('mock-ack').checked,false);assert.equal(h.get('factors').children.length,10);assert.match(h.get('status').textContent,/Chưa đủ dữ liệu/);assert.match(h.get('status').textContent,/chưa có phản hồi khán giả thật/);
  assert.match(h.get('factors').children[0].children[1].textContent,/Chưa có/);});
test('unknown creation retains exact key through new preparation even with an older selected assessment',async()=>{const h=harness();await ready(h);await h.controller.readHistory();let count=0;
  h.handler(async(path,body)=>{if(body&&!count++)throw new Error('Explicit unknown reply');return h.defaultHandler(path,body);});await h.controller.createAssessment();const key=h.calls.at(-1)[1].request_key;
  h.controller.prepareNew();ack(h);await h.controller.createAssessment();assert.equal(h.calls.at(-1)[1].request_key,key);assert.equal(h.get('ack').checked,false);
  h.controller.prepareNew();ack(h);await h.controller.createAssessment();assert.notEqual(h.calls.at(-1)[1].request_key,key);});
test('foreign source raw mock relabel report mismatch and automatic configuration are rejected',async()=>{for(const mutate of[v=>({...v,workspace_id:'wsp_foreign'}),v=>({...v,mock:1}),v=>({...v,real_audience_observation:true}),
  v=>({...v,scope:{...scope(),query:{...query(),end_date:'2026-10-03'}}}),v=>({...v,consent_sha256:'9'.repeat(64)})]){const h=harness();h.handler(async()=>mutate(source()));await h.controller.readSource();assert.equal(h.get('create').disabled,true);assert.equal(h.messages.length,1);}
  const h=harness();await h.controller.readSource();h.handler(async()=>({...config(),automatic_assessment:true}));await h.controller.readConfig();assert.equal(h.get('minimum-views').value,'');});
test('missing mock acknowledgement blank values unsafe thresholds peer bounds and invalid weights do not create',async()=>{const h=harness();await ready(h);const count=h.calls.length;h.get('mock-ack').checked=false;await h.controller.createAssessment();assert.equal(h.calls.length,count);ack(h);
  for(const[field,value]of[['minimum-peer-posts','2'],['minimum-peer-posts','5.5'],['maximum-peer-posts','101'],['minimum-views',''],['minimum-views','Infinity'],['minimum-weight-coverage','.09'],['underperforming-threshold','72'],['weight-ctr','1.1']]){
    await h.controller.readConfig();h.get(field).value=value;const before=h.calls.length;await h.controller.createAssessment();assert.equal(h.calls.length,before);}
  await h.controller.readConfig();for(const k of Object.keys(weights))h.get('weight-'+k).value='0';const before=h.calls.length;await h.controller.createAssessment();assert.equal(h.calls.length,before);});
test('viewer history stays readable while manage actions and busy work are refused',async()=>{const h=harness();h.state.canManage=false;h.controller.sync();await h.controller.readSource();await h.controller.readHistory();assert.equal(h.get('factors').children.length,10);
  const count=h.calls.length;await h.controller.readConfig();await h.controller.createAssessment();h.controller.prepareNew();assert.equal(h.calls.length,count);assert.equal(h.get('new').disabled,true);
  h.state.busy=true;await h.controller.readStored();assert.equal(h.calls.length,count);});
test('late source replies cannot cross project role workspace or selected observation',async()=>{for(const change of[h=>h.state.project.id='6'.repeat(32),h=>h.state.workspace_id='wsp_foreign',h=>h.state.canManage=false,
  h=>h.binding({sync:{...observation(),sync_id:'noas_'+'7'.repeat(32)}})]){const h=harness();let release;h.handler(()=>new Promise(resolve=>{release=resolve;}));const pending=h.controller.readSource();change(h);h.controller.sync();release(source());await pending;
  assert.equal(h.get('create').disabled,true);assert.equal(h.get('detail').textContent,'');assert.equal(h.messages.length,0);assert.equal(h.state.busy,false);}});
test('history rejects audience relabel hash drift numeric strings factor drift and automatic actions',async()=>{for(const mutate of[v=>({...v,real_audience_observation:true}),v=>({...v,snapshot:{...v.snapshot,candidate:{...v.snapshot.candidate,result_sha256:'9'.repeat(64)}}}),
  v=>({...v,assessment:{...v.assessment,score:'100'}}),v=>({...v,snapshot:{...v.snapshot,assessment:{...v.assessment,state:'winner_candidate'}}}),v=>({...v,automatic_action:true}),
  v=>({...v,assessment:{...v.assessment,channel_baseline_verified:true}})]){const h=harness();await h.controller.readSource();h.handler(async()=>page([mutate(row())]));await h.controller.readHistory();assert.equal(h.get('factors').children.length,0);assert.equal(h.messages.length,1);}});
test('history preserves null and zero factors and scoped cursor pagination stays bounded',async()=>{const h=harness();await h.controller.readSource();const value=row();value.assessment.factors[0].evidence.raw_value=0;value.snapshot.assessment=structuredClone(value.assessment);
  h.handler(async()=>page([value],'opaque+/='));await h.controller.readHistory();assert.match(h.get('factors').children[0].children[2].textContent,/Giá trị: 0 · Trung vị: Chưa có/);
  h.handler(async()=>page([]));await h.controller.readHistory(true);assert.match(h.calls.at(-1)[0],/&cursor=opaque%2B%2F%3D$/);assert.equal(h.get('history').children.length,1);
  for(const bad of[page([],'x'.repeat(2049)),page([{...row(),project_id:'9'.repeat(32)}]),page([],true)]){h.handler(async()=>bad);await h.controller.readHistory();assert.equal(h.get('history').children.length,1);}assert.equal(h.messages.length,3);});
test('immutable saved history remains readable after current project edits archive or active work',async()=>{const h=harness();await h.controller.readSource();await h.controller.readHistory();h.state.project.revision=2;h.state.project.archived=true;h.state.dirty=true;h.state.active=true;h.controller.sync();
  await h.controller.readSource();await h.controller.readHistory();await h.controller.readStored();assert.equal(h.get('factors').children.length,10);assert.match(h.get('status').textContent,/Chưa đủ dữ liệu/);});
