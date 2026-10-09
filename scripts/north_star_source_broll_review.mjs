// Actual signed HTTP and shipped review/request modules; DOM harness, not browser/UAT.
import assert from 'node:assert/strict';
import {initializeNativeOfficialVision} from '../apps/studio-web/native-official-vision.mjs';
import {initializeSourceBrollReview} from '../apps/studio-web/native-source-broll-review.mjs';
import {sourceBrollRequest,sourceBrollMarkup} from '../apps/studio-web/native-source-broll.mjs';
let input='';for await(const chunk of process.stdin)input+=chunk;const config=JSON.parse(input);
assert.match(config.origin,/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/);const calls=[],messages=[];
const reply=await fetch(config.origin+'/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:config.token}),signal:AbortSignal.timeout(10000)});
assert.equal(reply.status,200);const login=await reply.json(),cookie=reply.headers.getSetCookie()[0].split(';')[0];
async function api(path,body){const response=await fetch(config.origin+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json',Cookie:cookie,'X-VF-CSRF':login.csrf},
  body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(10000)});const value=await response.json();calls.push({method:body?'POST':'GET',route:path.split('?')[0],status:response.status});assert.equal(response.status,200,JSON.stringify(value));return value;}
const session=await api('/api/session'),runtime=await api('/api/connections/official-vision');assert.equal(runtime.enabled,false);assert.deepEqual(runtime.profiles,[]);
for(const route of['/native.mjs','/shot-studio.mjs','/native-source-editor.mjs','/native-source-broll.mjs','/native-source-broll-review.mjs']){
  const response=await fetch(config.origin+route,{headers:{Cookie:cookie},signal:AbortSignal.timeout(10000)});assert.equal(response.status,200);await response.text();calls.push({method:'GET',route,status:200});}
const nodes=new Map();class Node{constructor(tag='details'){this.tagName=tag.toUpperCase();this.children=[];this.value='';this.checked=false;this.dataset={};this.listeners={};this.textContent='';this.attributes={};this.style={};}
  set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=[...v];}
  setAttribute(k,v){this[k]=v;this.attributes[k]=v;}addEventListener(k,v){this.listeners[k]=v;}
  querySelectorAll(selector){return this.children.flatMap(n=>[...(selector.split(',').includes(n.tagName.toLowerCase())?[n]:[]),...n.querySelectorAll(selector)]);}}
const dom={createElement:tag=>new Node(tag),getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);}};
const base='/api/projects/'+config.project,state={workspace_id:session.access.workspace_id,project:await api(base+'/auto-edit/timeline'),canManage:true,canEdit:true,dirty:false,busy:false,active:false};
const originalProject=structuredClone(state.project),vision=initializeNativeOfficialVision({root:dom,api,getState:()=>({...state}),onMessage:(...v)=>messages.push(v)});
const root=dom.createElement('section'),review=initializeSourceBrollReview({root,dom,getState:()=>({...state}),getReviewedVision:()=>vision.currentBinding(),onMessage:(...v)=>messages.push(v)});
const find=attr=>root.querySelectorAll('input').find(n=>Object.hasOwn(n.attributes,attr));
const count=calls.length;vision.sync();review.sync();assert.equal(calls.length,count);assert.deepEqual(review.references(),[]);
await vision.readHistory();const original=structuredClone(vision.currentBinding());assert.equal(original.status,'succeeded');assert.equal(original.result.mock,true);
const local=calls.length;review.choose();assert.equal(calls.length,local);assert.throws(()=>review.references());
find('data-broll-review-ack').checked=true;assert.throws(()=>review.references());find('data-broll-review-mock').checked=true;
state.project=await api(base+'/auto-edit/broll',sourceBrollRequest(state.project,'create',{reviewedVision:review.references(),workspaceId:state.workspace_id}));
// Exact identical input deduplicates to the already saved reviewed plan.
assert.deepEqual(state.project,originalProject);let plan=state.project.document.source_broll_plans.at(-1).plan;
assert.equal(plan.provenance.semantic_vision_used,false);assert.equal(plan.provenance.reviewed_vision.items[0].response_sha256,original.response.response_sha256);
const item=plan.items[0],asset=item.provenance.supporting_candidates[0].asset_id;
state.project=await api(base+'/auto-edit/broll',sourceBrollRequest(state.project,'select',{planId:plan.media_plan_id,itemId:item.media_plan_item_id,assetId:asset,workspaceId:state.workspace_id}));
review.sync();assert.equal(find('data-broll-review-ack').checked,false);assert.equal(find('data-broll-review-mock').checked,false);
plan=state.project.document.source_broll_plans.at(-1).plan;assert.equal(plan.version,3);
const before=structuredClone(originalProject.shot_timeline.snapshot);
state.project=await api(base+'/auto-edit/broll',sourceBrollRequest(state.project,'apply',{planId:plan.media_plan_id,itemId:item.media_plan_item_id,replace:true,workspaceId:state.workspace_id}));
const after=state.project.shot_timeline.snapshot;assert.equal(after.duration_seconds,before.duration_seconds);
for(const track of before.tracks)if(track.kind!=='broll')assert.deepEqual(track,after.tracks.find(t=>t.track_id===track.track_id));
assert.equal(state.project.approval,null);assert.equal(state.project.document.source_broll_plans.length,4);
assert.deepEqual(await api(base+'/official-vision/'+original.vision_id),original);assert.deepEqual(await api(base+'/auto-edit/timeline'),state.project);
const markup=sourceBrollMarkup(state.project,{workspaceId:state.workspace_id});assert.match(markup,/Mô phỏng đã xem/);assert.match(markup,/chưa có hóa đơn thực tế/);
assert.equal(messages.length,0);assert.ok(!calls.some(v=>v.route.endsWith('/process')||v.route.endsWith('/jobs')));
process.stdout.write(JSON.stringify({schema_version:'native-source-broll-review-controller-proof-v1',original_vision:original,original_project:originalProject,project:state.project,
  calls,signed_http:true,explicit_local_selection_no_dispatch:true,deduplicated_create_preserves_original_plan:true,explicit_select_and_replace_apply:true,
  source_audio_tracks_and_duration_exact:true,new_external_dispatches:0,new_paid_operations:0,actual_parent_browser_executed:false,real_provider_tested:false,owner_uat_accepted:false,publishing_enabled:false})+'\n');
