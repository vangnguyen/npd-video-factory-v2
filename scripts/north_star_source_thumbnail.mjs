// Shipped thumbnail controller over signed HTTP; synthetic DOM, no Owner UAT.
import assert from 'node:assert/strict';import {createHash}from'node:crypto';
import {initializeNativeOfficialVision}from'../apps/studio-web/native-official-vision.mjs';
import {initializeSourceThumbnailReview}from'../apps/studio-web/native-source-thumbnail-review.mjs';
let input='';for await(const chunk of process.stdin)input+=chunk;const config=JSON.parse(input);
assert.match(config.origin,/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/);const calls=[],messages=[];
const reply=await fetch(config.origin+'/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:config.token}),signal:AbortSignal.timeout(10000)});
assert.equal(reply.status,200);const login=await reply.json(),cookie=reply.headers.getSetCookie()[0].split(';')[0];
async function api(path,body){const response=await fetch(config.origin+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json',Cookie:cookie,'X-VF-CSRF':login.csrf},
  body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(10000)});const value=await response.json();calls.push({method:body?'POST':'GET',route:path,status:response.status});
  assert.equal(response.status,200,JSON.stringify(value));return value;}
const session=await api('/api/session'),runtime=await api('/api/connections/official-vision');assert.equal(runtime.enabled,false);assert.deepEqual(runtime.profiles,[]);
for(const route of ['/native-source-editor.mjs','/native-source-thumbnail-review.mjs']){const response=await fetch(config.origin+route,{headers:{Cookie:cookie},signal:AbortSignal.timeout(10000)});
  assert.equal(response.status,200);await response.text();calls.push({method:'GET',route,status:200});}
const nodes=new Map();class Node{constructor(tag='details'){this.tagName=tag.toUpperCase();this.children=[];this.value='';this.checked=false;this.dataset={};this.listeners={};this.textContent='';this.attributes={};this.style={};}
  set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=[...v];}
  setAttribute(k,v){this[k]=v;this.attributes[k]=v;}addEventListener(k,v){this.listeners[k]=v;}
  querySelectorAll(selector){return this.children.flatMap(n=>[...(selector.split(',').includes(n.tagName.toLowerCase())?[n]:[]),...n.querySelectorAll(selector)]);}}
const dom={createElement:tag=>new Node(tag),getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);}};
const base='/api/projects/'+config.project,state={workspace_id:session.access.workspace_id,project:await api(base+'/auto-edit/timeline'),canManage:true,canEdit:true,dirty:false,busy:false,active:false};
const original=structuredClone(state.project),vision=initializeNativeOfficialVision({root:dom,api,getState:()=>({...state}),onMessage:(...v)=>messages.push(v)});
const root=dom.createElement('section'),controller=initializeSourceThumbnailReview({root,dom,api,getState:()=>({...state}),getReviewedVision:()=>vision.currentBinding(),
  onProject:p=>{state.project=p;},onMessage:(...v)=>messages.push(v)});
const find=key=>root.querySelectorAll('input,select,button').find(n=>Object.hasOwn(n.attributes,key));
await vision.readHistory();const row=structuredClone(vision.currentBinding());
const before=calls.length;controller.choose();assert.equal(calls.length,before);await controller.perform('save');assert.equal(calls.length,before);
find('data-thumbnail-review-ack').checked=true;await controller.perform('save');assert.equal(calls.length,before);
find('data-thumbnail-review-mock').checked=true;await controller.perform('save');
assert.equal(state.project.document.source_thumbnail_reviews.length,1);const saved=structuredClone(state.project.document.source_thumbnail_reviews[0]);
assert.equal(find('data-thumbnail-review-ack').checked,false);assert.equal(find('data-thumbnail-review-mock').checked,false);
const unchanged=structuredClone(state.project);controller.choose();find('data-thumbnail-review-ack').checked=find('data-thumbnail-review-mock').checked=true;
await controller.perform('save');assert.deepEqual(state.project,unchanged);
const image_proofs=[];
for(const candidate of [saved.recommendation.candidates[0],saved.recommendation.candidates.at(-1)]){
  find('data-thumbnail-choice').value=saved.recommendation.recommendation_id;find('data-thumbnail-choice').listeners.change();
  find('data-thumbnail-frame').value=candidate.frame_id;find('data-thumbnail-frame').listeners.change();
  const count=calls.length;find('data-thumbnail-selection-ack').checked=true;await controller.perform('select');assert.equal(calls.length,count);
  find('data-thumbnail-selection-mock').checked=true;await controller.perform('select');
  assert.equal(state.project.document.source_thumbnail_selection.frame_id,candidate.frame_id);assert.equal(state.project.approval,null);
  assert.equal(find('data-thumbnail-selection-ack').checked,false);assert.equal(find('data-thumbnail-selection-mock').checked,false);
  const route=base+'/media/'+saved.recommendation.source.asset.id+'/thumbnail',response=await fetch(config.origin+route,{headers:{Cookie:cookie},signal:AbortSignal.timeout(10000)});
  assert.equal(response.status,200);assert.equal(response.headers.get('content-type'),'image/png');assert.equal(response.headers.get('x-vf-thumbnail-basis'),'explicit_reviewed_source_frame');
  const sha=createHash('sha256').update(Buffer.from(await response.arrayBuffer())).digest('hex');assert.equal(sha,candidate.source_frame.sha256);
  calls.push({method:'GET',route,status:200});image_proofs.push({frame_id:candidate.frame_id,sha256:sha});
}
assert.deepEqual(state.project.document.canonical_timeline,original.document.canonical_timeline);
for(const name of ['source_reframe_reviews','source_scene_recommendations','source_broll_plans','auto_edit_analyses','auto_edit_transcripts'])assert.deepEqual(state.project.document[name],original.document[name]);
assert.deepEqual(await api(base+'/official-vision/'+row.vision_id),row);
assert.ok(!calls.some(v=>v.route.endsWith('/process')||v.route.endsWith('/jobs')));
process.stdout.write(JSON.stringify({original_project:original,project:state.project,original_vision:row,calls,image_proofs,
  signed_http:true,new_external_dispatches:0,new_paid_operations:0,new_mock_requests:0,actual_parent_browser_executed:false,real_provider_tested:false,owner_uat_accepted:false})+'\n');
