// Shipped reviewed-crop controller over signed HTTP; synthetic DOM, not UAT.
import assert from 'node:assert/strict';
import {initializeNativeOfficialVision}from'../apps/studio-web/native-official-vision.mjs';
import {initializeSourceCropReview}from'../apps/studio-web/native-source-crop-review.mjs';
let input='';for await(const chunk of process.stdin)input+=chunk;const config=JSON.parse(input);
assert.match(config.origin,/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/);const calls=[],messages=[];
const reply=await fetch(config.origin+'/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:config.token}),signal:AbortSignal.timeout(10000)});
assert.equal(reply.status,200);const login=await reply.json(),cookie=reply.headers.getSetCookie()[0].split(';')[0];
async function api(path,body){const response=await fetch(config.origin+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json',Cookie:cookie,'X-VF-CSRF':login.csrf},
  body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(10000)});const value=await response.json();calls.push({method:body?'POST':'GET',route:path,status:response.status});
  assert.equal(response.status,200,JSON.stringify(value));return value;}
const session=await api('/api/session'),runtime=await api('/api/connections/official-vision');assert.equal(runtime.enabled,false);assert.deepEqual(runtime.profiles,[]);
for(const route of ['/native-source-editor.mjs','/native-source-crop-review.mjs']){const response=await fetch(config.origin+route,{headers:{Cookie:cookie},signal:AbortSignal.timeout(10000)});
  assert.equal(response.status,200);await response.text();calls.push({method:'GET',route,status:200});}
const nodes=new Map();class Node{constructor(tag='details'){this.tagName=tag.toUpperCase();this.children=[];this.value='';this.checked=false;this.dataset={};this.listeners={};this.textContent='';this.attributes={};this.style={};}
  set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=[...v];}
  setAttribute(k,v){this[k]=v;this.attributes[k]=v;}addEventListener(k,v){this.listeners[k]=v;}
  querySelectorAll(selector){return this.children.flatMap(n=>[...(selector.split(',').includes(n.tagName.toLowerCase())?[n]:[]),...n.querySelectorAll(selector)]);}}
const dom={createElement:tag=>new Node(tag),getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);}};
const base='/api/projects/'+config.project,state={workspace_id:session.access.workspace_id,project:await api(base+'/auto-edit/timeline'),canManage:true,canEdit:true,dirty:false,busy:false,active:false};
const original=structuredClone(state.project),vision=initializeNativeOfficialVision({root:dom,api,getState:()=>({...state}),onMessage:(...v)=>messages.push(v)});
const root=dom.createElement('section'),crop=initializeSourceCropReview({root,dom,getState:()=>({...state}),getReviewedVision:()=>vision.currentBinding(),onMessage:(...v)=>messages.push(v)});
const find=key=>root.querySelectorAll('input,select,button').find(n=>Object.hasOwn(n.attributes,key));
await vision.readHistory();const row=structuredClone(vision.currentBinding());assert.equal(row.snapshot.source.asset.id,original.document.source_scene_recommendations[0].recommendation.source.asset.id);
const audio=original.shot_timeline.snapshot.tracks.filter(v=>v.type!=='video');
for(const ratio of ['9:16','16:9','1:1','4:5']){
  const before=calls.length;crop.choose();assert.equal(calls.length,before);assert.throws(()=>crop.request());
  find('data-crop-review-ack').checked=true;assert.throws(()=>crop.request());find('data-crop-review-mock').checked=true;find('data-crop-review-ratio').value=ratio;
  const body=crop.request();state.project=await api(base+'/auto-edit/timeline',body);crop.sync();
  assert.equal(find('data-crop-review-ack').checked,false);assert.equal(find('data-crop-review-mock').checked,false);
  const metadata=state.project.shot_timeline.snapshot.metadata;assert.equal(metadata.source_reframe_plan.plan.strategy,'center_crop');
  assert.equal(metadata.source_reframe_plan.plan.fallback,'center_crop');assert.equal(metadata.reframe_review.tracking_confidence,null);assert.equal(metadata.reframe_review.needs_attention,true);
  assert.equal(metadata.reviewed_reframe_selection.mock_original_result,true);assert.equal(metadata.reviewed_reframe_selection.original_response_sha256,row.response.response_sha256);
  assert.equal(state.project.shot_timeline.snapshot.aspect_ratio,ratio);assert.equal(state.project.approval,null);
  assert.deepEqual(state.project.shot_timeline.snapshot.tracks.filter(v=>v.type!=='video'),audio);assert.deepEqual(await api(base+'/auto-edit/timeline'),state.project);
}
assert.deepEqual(state.project.document.source_scene_recommendations,original.document.source_scene_recommendations);
assert.deepEqual(state.project.document.source_broll_plans,original.document.source_broll_plans);assert.deepEqual(state.project.document.auto_edit_analyses,original.document.auto_edit_analyses);
assert.deepEqual(await api(base+'/official-vision/'+row.vision_id),row);assert.equal(state.project.document.source_reframe_reviews.length,4);
assert.ok(!calls.some(v=>v.route.endsWith('/process')||v.route.endsWith('/jobs')));
process.stdout.write(JSON.stringify({original_project:original,project:state.project,original_vision:row,calls,
  signed_http:true,new_external_dispatches:0,new_paid_operations:0,new_mock_requests:0,actual_parent_browser_executed:false,real_provider_tested:false,owner_uat_accepted:false})+'\n');
