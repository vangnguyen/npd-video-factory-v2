// Shipped thumbnail controller over signed local HTTP; explicit synthetic review.
import assert from'node:assert/strict';import{createHash}from'node:crypto';
import{initializeNativeRenderThumbnail,renderThumbnailImageUrl}from'../apps/studio-web/native-render-thumbnail.mjs';
import{renderVisionFrameUrl}from'../apps/studio-web/native-render-vision.mjs';
let stdin='';for await(const chunk of process.stdin)stdin+=chunk;const config=JSON.parse(stdin);assert.match(config.origin,/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/);
const calls=[],messages=[],received=new Map();
const auth=await fetch(config.origin+'/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:config.token}),signal:AbortSignal.timeout(10000)});
assert.equal(auth.status,200);const login=await auth.json(),cookie=auth.headers.getSetCookie()[0].split(';')[0];
async function api(path,body){const response=await fetch(config.origin+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json',Cookie:cookie,'X-VF-CSRF':login.csrf},
 body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(30000)});const value=await response.json();calls.push({method:body?'POST':'GET',path,status:response.status});assert.equal(response.status,200,JSON.stringify(value));received.set(path,structuredClone(value));return value;}
const session=await api('/api/session');assert.equal(session.capabilities.native_render_thumbnail_review,true);assert.equal(session.capabilities.native_official_vision,false);
for(const path of['/native-render-thumbnail.mjs','/native.mjs','/shot-studio.mjs']){const response=await fetch(config.origin+path,{headers:{Cookie:cookie},signal:AbortSignal.timeout(10000)});assert.equal(response.status,200);await response.text();calls.push({method:'GET',path,status:200});}
const nodes=new Map();class Node{constructor(tag='details'){this.tagName=tag.toUpperCase();this.children=[];this.value='';this.checked=false;this.dataset={};this.listeners={};this.textContent='';this.style={};}
 set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=[...v];}addEventListener(k,v){this.listeners[k]=v;}}
const dom={createElement:tag=>new Node(tag),getElementById:id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);}},get=k=>dom.getElementById('native-render-thumbnail-'+k);
const state={project:await api('/api/projects/'+config.project),workspace_id:session.access.workspace_id,canEdit:true,dirty:false,busy:true,active:false},original=structuredClone(state.project);let reviewed=null;
const controller=initializeNativeRenderThumbnail({root:dom,api,getState:()=>({...state}),getReviewedVision:()=>reviewed,onMessage:(...v)=>messages.push(v)});
const count=calls.length;controller.sync();state.busy=false;controller.controls();assert.equal(calls.length,count);assert.equal(get('save').disabled,true);
get('video').value=config.job;get('video').listeners.change();await controller.readInput();const input=received.get('/api/projects/'+config.project+'/render-vision/input/'+config.job);
assert.equal(input.binding.matches_current_project_document,true);assert.equal(get('frames').children.length,8);
async function pixels(path,frame,thumbnail=false){const response=await fetch(config.origin+path,{headers:{Cookie:cookie},signal:AbortSignal.timeout(30000)});assert.equal(response.status,200);
 assert.equal(response.headers.get('content-type'),'image/png');assert.equal(response.headers.get('cache-control'),'no-store');assert.equal(response.headers.get('x-content-type-options'),'nosniff');
 if(thumbnail){assert.equal(response.headers.get('x-vf-thumbnail-basis'),'explicit_reviewed_render_frame');assert.equal(response.headers.get('x-vf-thumbnail-sha256'),frame.sha256);}
 const bytes=Buffer.from(await response.arrayBuffer());assert.equal(createHash('sha256').update(bytes).digest('hex'),frame.sha256);assert.equal(bytes.length,frame.size_bytes);
 calls.push({method:'GET',path,status:200});return{sha256:frame.sha256,bytes:bytes.length,path};}
const frameProofs=[];for(const[index,frame]of input.binding.record.observation.frames.entries())frameProofs.push(await pixels(renderVisionFrameUrl(config.project,config.job,index),frame));
const frames=input.binding.record.observation.frames.filter(f=>!f.pixel_facts.black_sample),selected=[],imageProofs=[];
for(const[index,frame]of[frames[0],frames.at(-1),frames[0]].entries()){
 get('frame').value=frame.frame_id;get('frame').listeners.change();const prior=calls.length;await controller.create();assert.equal(calls.length,prior);get('ack').checked=true;
 if(index===2){reviewed=await api('/api/projects/'+config.project+'/render-vision/'+config.vision);assert.equal(reviewed.status,'succeeded');assert.equal(reviewed.result.mock,true);
  get('vision').checked=true;const before=calls.length;await controller.create();assert.equal(calls.length,before);get('mock').checked=true;}
 await controller.create();const row=structuredClone(controller.currentSelection());assert.equal(row.snapshot.frame.frame_id,frame.frame_id);assert.equal(row.snapshot.image.rights_status,'unknown');
 assert.equal(row.snapshot.image.license,null);assert.equal(row.publishing_authorized,false);assert.equal(row.snapshot.final_video_approved,false);assert.equal(row.owner_uat_accepted,false);
 assert.equal(get('ack').checked,false);assert.equal(get('vision').checked,false);assert.equal(get('mock').checked,false);assert.equal(row.idempotent_replay,false);delete row.idempotent_replay;selected.push(row);
 imageProofs.push(await pixels(renderThumbnailImageUrl(config.project,row.thumbnail_asset_id),frame,true));
 assert.equal(get('selected').children[0].children[0].src,renderThumbnailImageUrl(config.project,row.thumbnail_asset_id));
}
state.canEdit=false;controller.sync();await controller.readHistory();assert.equal(get('save').disabled,true);assert.equal(get('ack').disabled,true);assert.equal(get('history').disabled,false);
assert.equal(get('list').children.length,config.inherited_selections+3);get('list').children.at(-1).listeners.click();assert.ok(controller.currentSelection());
assert.deepEqual(await api('/api/projects/'+config.project),original);assert.deepEqual(await api('/api/session'),session);assert.equal(messages.length,4);
assert.ok(!calls.some(v=>v.path.endsWith('/process')||v.path.endsWith('/jobs')||v.path.includes('publication')));
process.stdout.write(JSON.stringify({status:'PASS',input,original_project:original,new_selections:selected,frame_proofs:frameProofs,selected_image_proofs:imageProofs,calls,
 signed_http:true,dom_controller_tested:true,actual_parent_browser_executed:false,external_dispatches:0,paid_operations:0,rights_status:'unknown',real_provider_tested:false,owner_uat_accepted:false})+'\n');
