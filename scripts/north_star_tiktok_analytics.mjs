// Actual signed loopback HTTP through real Studio controllers and an explicit fake DOM.
import assert from 'node:assert/strict';
import {initializeNativeOfficialAnalytics} from '../apps/studio-web/native-official-analytics.mjs';
import {initializeNativeOfficialRefresh} from '../apps/studio-web/native-official-refresh.mjs';
import {initializeNativeOfficialWinners} from '../apps/studio-web/native-official-winners.mjs';
import {initializeNativeOfficialLearning} from '../apps/studio-web/native-official-learning.mjs';
let raw='';for await(const part of process.stdin)raw+=part;const input=JSON.parse(raw);assert.match(input.origin,/^http:\/\/127\.0\.0\.1:[0-9]+$/);
const calls=[],messages=[],headers={Cookie:'vf_native_session='+input.cookie,'X-VF-CSRF':input.csrf,Origin:input.origin,'Content-Type':'application/json',Connection:'close'};
const api=async(path,body)=>{assert.ok(path.startsWith('/api/'));const r=await fetch(input.origin+path,{method:body?'POST':'GET',headers,...(body?{body:JSON.stringify(body)}:{})}),v=await r.json();calls.push({path,method:body?'POST':'GET',status:r.status,schema_version:v.schema_version??null});if(!r.ok)throw Error('Owned HTTP '+r.status+' '+v.code);return v;};
const nodes=new Map();class Node{constructor(){this.value='';this.checked=false;this.dataset={};this.listeners={};this.children=[];}set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,v){this.listeners[k]=v;}}
const root={createElement:()=>new Node(),getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);}},get=(prefix,name)=>root.getElementById(prefix+name),state={workspace_id:input.workspace_id,project:input.project,canManage:!input.read_only,dirty:false,busy:false,active:false};
const common={api,root,getState:()=>state,onMessage:(...v)=>messages.push(v),onWorking:v=>{state.busy=v;}},parent=()=>({publication:input.publication});
const analytics=initializeNativeOfficialAnalytics({...common,getBinding:parent}),refresh=initializeNativeOfficialRefresh({...common,getBinding:parent});assert.equal(calls.length,0);
if(input.mode==='create_manual'){
  await analytics.readSource();await analytics.readConfig();get('native-official-analytics-','post').value=input.remote_post_id;get('native-official-analytics-','ack').checked=get('native-official-analytics-','mock-ack').checked=true;await analytics.createRead();assert.equal(analytics.currentBinding().sync.status,'queued');
}else if(input.mode==='create_plan'){
  await refresh.readSource();await refresh.readConfig();for(const[k,v]of Object.entries({post:input.remote_post_id,start:input.start_at,deadline:input.deadline,runs:'1',interval:'60',valid:'900'}))get('native-official-refresh-',k).value=v;
  for(const k of['ack','background','mock-ack'])get('native-official-refresh-',k).checked=true;await refresh.createPlan();assert.ok(get('native-official-refresh-','detail').textContent);
}else{
  await analytics.readSource();await analytics.readHistory();await analytics.readStored();assert.equal(analytics.currentBinding().sync.status,'succeeded');
  await refresh.readSource();await refresh.readHistory();await refresh.readStored();assert.ok(get('native-official-refresh-','detail').textContent);
}
const selected=analytics.currentBinding().sync,planText=get('native-official-refresh-','detail').textContent,plan=planText?JSON.parse(planText):null;
let winner=null,learning=null;if(input.assess){
  const winners=initializeNativeOfficialWinners({...common,getBinding:()=>analytics.currentBinding()});await winners.readSource();await winners.readConfig();get('native-official-winners-','ack').checked=get('native-official-winners-','mock-ack').checked=true;await winners.createAssessment();assert.equal(messages.length,0,JSON.stringify(messages));winner=winners.currentBinding().assessment;assert.ok(winner);assert.equal(winner.assessment.state,'insufficient_data');await winners.readStored();winner=winners.currentBinding().assessment;assert.ok(winner);
  const learn=initializeNativeOfficialLearning({...common,getBinding:()=>winners.currentBinding()});await learn.readSource();await learn.readConfig();get('native-official-learning-','ack').checked=get('native-official-learning-','mock-ack').checked=true;await learn.createLearning();assert.equal(messages.length,0,JSON.stringify(messages));learning=learn.currentBinding().learning;assert.ok(learning);await learn.readStored();learning=learn.currentBinding().learning;assert.ok(learning);
}
assert.equal(messages.length,0,JSON.stringify(messages));if(input.read_only)assert.ok(calls.every(x=>x.method==='GET'));
process.stdout.write(JSON.stringify({status:'PASS',mode:input.mode,calls,selected_sync:selected,plan,winner,learning,browser_rendered:false,owner_uat:false,real_provider_acceptance:false}));
