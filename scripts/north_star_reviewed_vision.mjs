// Actual signed loopback HTTP through the two shipped Studio controllers.
// DOM harness only; no real provider, browser/UAT or final-video certification.
import assert from 'node:assert/strict';
import {initializeNativeOfficialVision} from '../apps/studio-web/native-official-vision.mjs';
import {initializeNativeMediaPlanner} from '../apps/studio-web/native-media-planner.mjs';
let input='';for await(const chunk of process.stdin)input+=chunk;const config=JSON.parse(input);
assert.match(config.origin,/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/);const calls=[],messages=[];
const response=await fetch(config.origin+'/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:config.token}),signal:AbortSignal.timeout(10000)});
assert.equal(response.status,200);const login=await response.json(),cookie=response.headers.getSetCookie()[0].split(';')[0];
async function api(path,body){const reply=await fetch(config.origin+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json',Cookie:cookie,'X-VF-CSRF':login.csrf},
  body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(10000)});const value=await reply.json();calls.push({method:body?'POST':'GET',route:path.split('?')[0],status:reply.status});assert.equal(reply.status,200,JSON.stringify(value));return value;}
const session=await api('/api/session');assert.equal(session.access.mode,'registry');assert.equal(session.capabilities.native_official_vision,false);
for(const route of ['/native.html','/native.mjs','/native-official-vision.mjs','/native-media-planner.mjs']){
  const reply=await fetch(config.origin+route,{headers:{Cookie:cookie},signal:AbortSignal.timeout(10000)});assert.equal(reply.status,200);await reply.text();calls.push({method:'GET',route,status:200});}
const nodes=new Map();class Node{
  constructor(tag='details'){this.tagName=tag.toUpperCase();this.children=[];this.value='';this.checked=false;this.dataset={};this.listeners={};this.textContent='';this.style={};}
  set id(value){this._id=value;nodes.set(value,this);}get id(){return this._id;}
  append(...values){this.children.push(...values);}replaceChildren(...values){this.children=[...values];}setAttribute(name,value){this[name]=value;}
  addEventListener(name,fn){this.listeners[name]=fn;}
  querySelectorAll(selector){return this.children.flatMap(child=>[...(selector.split(',').includes(child.tagName.toLowerCase())?[child]:[]),...child.querySelectorAll(selector)]);}
}
const dom={createElement:tag=>new Node(tag),getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);}},get=id=>dom.getElementById('native-official-vision-'+id);
const state={workspace_id:session.access.workspace_id,project:await api('/api/projects/'+config.project),canManage:true,canEdit:true,dirty:false,busy:false,active:false};
const vision=initializeNativeOfficialVision({root:dom,api,getState:()=>({...state}),onMessage:(...args)=>messages.push(args)});
const planner=initializeNativeMediaPlanner({dom,api:(path,options)=>api(path,options?JSON.parse(options.body):undefined),getState:()=>({...state}),
  getReviewedVision:()=>vision.currentBinding(),onMessage:(message,error)=>{if(error)messages.push([message,error]);},onSaved:async()=>{state.project=await api('/api/projects/'+config.project);vision.sync();}});
const panel=dom.getElementById('native-media-planner-panel'),button=text=>panel.querySelectorAll('button').find(node=>node.textContent===text),check=text=>panel.querySelectorAll('label').find(node=>node.textContent===text).querySelectorAll('input')[0];
const before=calls.length;vision.sync();planner.sync();assert.equal(calls.length,before);
await planner.load();await button('Tạo kế hoạch mới').listeners.click();
const baseline=await api('/api/projects/'+config.project+'/media-plans');assert.equal(baseline.items.at(-1).plan.algorithm,'native-storyboard-media-planner-v2');
await vision.readConfig();await vision.readSources();get('profile').value=get('profile').children[1].value;get('observation').value=get('observation').children[1].value;
get('ceiling').value='500';get('duration').value='600';get('ack').checked=get('mock-ack').checked=true;await vision.createIntent();await vision.processSelected();
const original=structuredClone(vision.currentBinding());assert.equal(original.status,'succeeded');assert.equal(original.result.mock,true);
await planner.load();const localCount=calls.length;await button('Chọn kết quả Vision đang xem').listeners.click();assert.equal(calls.length,localCount);
check('Tôi đã xem kết quả Vision và muốn dùng cho kế hoạch mới.').checked=true;
check('Tôi hiểu mô phỏng không bổ sung điểm nhận diện hoặc chất lượng thật.').checked=true;
await button('Tạo kế hoạch mới').listeners.click();let page=await api('/api/projects/'+config.project+'/media-plans'),record=page.items.find(row=>row.plan.algorithm==='native-storyboard-media-planner-v3');
assert.ok(record);assert.equal(record.input_current,true);assert.equal(record.plan.semantic_vision_used,false);assert.equal(record.plan.input.reviewed_vision.mock_present,true);
assert.equal(record.plan.input.reviewed_vision.items[0].response_sha256,original.response.response_sha256);const created=structuredClone(page);
// First plan is baseline, second plan carries explicit reviewed original lineage.
const selects=panel.querySelectorAll('select').filter(node=>String(node['aria-label']).startsWith('Tư liệu shot'));
assert.equal(selects.length,6);
const v3Section=panel.querySelectorAll('section').at(-1),apply=v3Section.querySelectorAll('button').find(node=>node.textContent==='Áp dụng vào shot');
v3Section.querySelectorAll('label').find(node=>node.textContent==='Tôi đã xem tư liệu và muốn thay hình của shot này.').querySelectorAll('input')[0].checked=true;
await apply.listeners.click();page=await api('/api/projects/'+config.project+'/media-plans');record=page.items.find(row=>row.plan.algorithm==='native-storyboard-media-planner-v3');
assert.equal(record.input_current,false);assert.equal(record.plan.application.acknowledged,true);assert.equal(record.plan.application.automatic_render,false);
assert.deepEqual(await api('/api/projects/'+config.project+'/official-vision/'+original.vision_id),original);
assert.equal(calls.filter(row=>row.route.endsWith('/process')).length,1);assert.equal(messages.length,0);
process.stdout.write(JSON.stringify({schema_version:'native-reviewed-vision-controller-proof-v1',original_vision:original,created_page:created,applied_page:page,project:state.project,
  calls,signed_http:true,explicit_local_selection_no_dispatch:true,mock_semantic_ranking:false,actual_parent_browser_executed:false,real_provider_tested:false,owner_uat_accepted:false,publishing_enabled:false})+'\n');
