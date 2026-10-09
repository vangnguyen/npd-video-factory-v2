// Shipped Vision/scene controls over signed HTTP; DOM harness, not browser/UAT.
import assert from 'node:assert/strict';
import {initializeNativeOfficialVision}from'../apps/studio-web/native-official-vision.mjs';
import {initializeSceneReview}from'../apps/studio-web/native-scene-review.mjs';
let input='';for await(const chunk of process.stdin)input+=chunk;const config=JSON.parse(input);
assert.match(config.origin,/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/);const calls=[],messages=[];let shortsReply;
const response=await fetch(config.origin+'/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:config.token}),signal:AbortSignal.timeout(10000)});
assert.equal(response.status,200);const login=await response.json(),cookie=response.headers.getSetCookie()[0].split(';')[0];
async function api(path,body){const reply=await fetch(config.origin+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json',Cookie:cookie,'X-VF-CSRF':login.csrf},
  body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(10000)});const value=await reply.json();calls.push({method:body?'POST':'GET',route:path,status:reply.status});
  assert.equal(reply.status,200,JSON.stringify(value));if(body&&path.endsWith('/shorts'))shortsReply=value;return value;}
const session=await api('/api/session'),runtime=await api('/api/connections/official-vision');assert.equal(runtime.enabled,false);assert.deepEqual(runtime.profiles,[]);
for(const route of['/native.mjs','/shot-studio.mjs','/native-source-editor.mjs','/native-scene-review.mjs']){
  const reply=await fetch(config.origin+route,{headers:{Cookie:cookie},signal:AbortSignal.timeout(10000)});assert.equal(reply.status,200);await reply.text();calls.push({method:'GET',route,status:200});}
const nodes=new Map();class Node{constructor(tag='details'){this.tagName=tag.toUpperCase();this.children=[];this.value='';this.checked=false;this.dataset={};this.listeners={};this.textContent='';this.attributes={};this.style={};}
  set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=[...v];}
  setAttribute(k,v){this[k]=v;this.attributes[k]=v;}addEventListener(k,v){this.listeners[k]=v;}
  querySelectorAll(selector){return this.children.flatMap(n=>[...(selector.split(',').includes(n.tagName.toLowerCase())?[n]:[]),...n.querySelectorAll(selector)]);}}
const dom={createElement:tag=>new Node(tag),getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);}};
const base='/api/projects/'+config.project,state={workspace_id:session.access.workspace_id,project:await api(base+'/auto-edit/timeline'),canManage:true,canEdit:true,dirty:false,busy:false,active:false};
const original=structuredClone(state.project),vision=initializeNativeOfficialVision({root:dom,api,getState:()=>({...state}),onMessage:(...v)=>messages.push(v)});
const root=dom.createElement('section'),review=initializeSceneReview({root,dom,api,getState:()=>({...state}),getReviewedVision:()=>vision.currentBinding(),
  onProject:value=>{state.project=value;},onMessage:(...v)=>messages.push(v),onDraftsCreated:()=>api('/api/projects')});
const find=key=>root.querySelectorAll('input,select,button').find(n=>Object.hasOwn(n.attributes,key));
const count=calls.length;vision.sync();review.sync();assert.equal(calls.length,count);await vision.readHistory();
const row=structuredClone(vision.currentBinding());assert.equal(row.snapshot.source.asset.id,original.document.source_scene_recommendations[0].recommendation.source.asset.id);
const local=calls.length;review.choose();assert.equal(calls.length,local);await review.perform('save');assert.equal(calls.length,local);
find('data-scene-review-ack').checked=true;await review.perform('save');assert.equal(calls.length,local);
find('data-scene-review-mock').checked=true;await review.perform('save');assert.deepEqual(state.project,original);
assert.equal(find('data-scene-review-ack').checked,false);assert.equal(find('data-scene-review-mock').checked,false);
const rec=original.document.source_scene_recommendations[0];function choose(){find('data-scene-choice').value=rec.recommendation.recommendation_id;find('data-scene-choice').listeners.change();
  find('data-scene-selection-ack').checked=find('data-scene-selection-mock').checked=true;}
choose();find('data-scene-shorts-duration').value='3';await review.perform('shorts');assert.ok(shortsReply?.batch.generated_count>0);
assert.deepEqual(await api(base+'/auto-edit/timeline'),original);assert.equal(shortsReply.batch.parent_document_mutated,false);
const before=structuredClone(state.project);choose();await review.perform('apply');assert.equal(state.project.shot_timeline.version,before.shot_timeline.version+1);
const metadata=state.project.shot_timeline.snapshot.metadata;assert.equal(metadata.reviewed_scene_selection.recommendation_sha256,rec.sha256);
assert.equal(metadata.reviewed_scene_selection.mock_original_result,true);assert.equal(metadata.reviewed_scene_selection.semantic_vision_used,false);
assert.deepEqual(metadata.source_selection.silence_decision_ids,[]);assert.equal(state.project.approval,null);
assert.deepEqual(state.project.document.source_scene_recommendations,original.document.source_scene_recommendations);
assert.deepEqual(await api(base+'/official-vision/'+row.vision_id),row);assert.deepEqual(await api(base+'/auto-edit/timeline'),state.project);
assert.equal(messages.filter(v=>v[1]).length,2);assert.ok(!calls.some(v=>v.route.endsWith('/process')||v.route.endsWith('/jobs')));
process.stdout.write(JSON.stringify({schema_version:'native-reviewed-scene-controller-proof-v1',original_project:original,project:state.project,original_vision:row,shorts:shortsReply,calls,
  signed_http:true,local_choices_without_dispatch:true,deduplicated_recommendation_save_exact:true,explicit_reviewed_highlight_and_independent_shorts:true,
  new_external_dispatches:0,new_paid_operations:0,new_mock_requests:0,actual_parent_browser_executed:false,real_provider_tested:false,owner_uat_accepted:false})+'\n');
