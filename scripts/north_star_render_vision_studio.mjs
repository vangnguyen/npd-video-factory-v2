// Shipped Studio controller over signed loopback HTTP; synthetic DOM, no Owner UAT.
import assert from 'node:assert/strict';import{createHash}from'node:crypto';
import{initializeNativeRenderVision,renderVisionFrameUrl}from'../apps/studio-web/native-render-vision.mjs';
let stdin='';for await(const chunk of process.stdin)stdin+=chunk;const config=JSON.parse(stdin);
assert.match(config.origin,/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/);const calls=[],messages=[],received=new Map();
const loginResponse=await fetch(config.origin+'/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:config.token}),signal:AbortSignal.timeout(10000)});
assert.equal(loginResponse.status,200);const login=await loginResponse.json(),cookie=loginResponse.headers.getSetCookie()[0].split(';')[0];
async function api(path,body){const response=await fetch(config.origin+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json',Cookie:cookie,'X-VF-CSRF':login.csrf},
  body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(125000)});const value=await response.json();calls.push({method:body?'POST':'GET',path,status:response.status});
  assert.equal(response.status,200,JSON.stringify(value));received.set(path,structuredClone(value));return value;}
const session=await api('/api/session');assert.equal(session.capabilities.native_render_vision_review,true);assert.equal(session.capabilities.native_official_vision,false);
for(const path of['/native-render-vision.mjs','/native.mjs','/shot-studio.mjs']){const response=await fetch(config.origin+path,{headers:{Cookie:cookie},signal:AbortSignal.timeout(10000)});
  assert.equal(response.status,200);await response.text();calls.push({method:'GET',path,status:200});}
const nodes=new Map();class Node{constructor(tag='details'){this.tagName=tag.toUpperCase();this.children=[];this.value='';this.checked=false;this.dataset={};this.listeners={};this.textContent='';this.style={};}
  set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=[...v];}addEventListener(k,v){this.listeners[k]=v;}}
const dom={createElement:tag=>new Node(tag),getElementById:id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);}},get=k=>dom.getElementById('native-render-vision-'+k);
const base='/api/projects/'+config.project+'/render-vision',state={project:await api('/api/projects/'+config.project),workspace_id:session.access.workspace_id,canManage:true,dirty:false,busy:false,active:false};
const original=structuredClone(state.project),controller=initializeNativeRenderVision({root:dom,api,getState:()=>({...state}),onMessage:(...v)=>messages.push(v)});
const initial=calls.length;controller.sync();controller.controls();assert.equal(calls.length,initial);assert.equal(get('process').disabled,true);
await controller.readConfig();const runtime=received.get('/api/connections/render-vision');assert.equal(runtime.enabled,true);assert.equal(runtime.profiles[0].mock,true);
get('profile').value=runtime.profiles[0].profile.profile_id;get('profile').listeners.change();get('video').value=config.job;get('video').listeners.change();await controller.readInput();
const input=received.get(base+'/input/'+config.job);assert.equal(input.binding.matches_current_project_document,true);
assert.equal(get('input-frames').children.length,8);const frameProofs=[];
for(const[index,frame]of input.binding.record.observation.frames.entries()){
  const path=renderVisionFrameUrl(config.project,config.job,index),response=await fetch(config.origin+path,{headers:{Cookie:cookie},signal:AbortSignal.timeout(30000)});
  assert.equal(response.status,200);assert.equal(response.headers.get('content-type'),'image/png');assert.equal(response.headers.get('cache-control'),'no-store');
  const bytes=Buffer.from(await response.arrayBuffer());assert.equal(createHash('sha256').update(bytes).digest('hex'),frame.sha256);assert.equal(bytes.length,frame.size_bytes);
  calls.push({method:'GET',path,status:200});frameProofs.push({index,sha256:frame.sha256,bytes:bytes.length});
}
get('ceiling').value='500';get('duration').value='600';let count=calls.length;await controller.createIntent();assert.equal(calls.length,count);
get('ack').checked=true;await controller.createIntent();assert.equal(calls.length,count);
get('mock-ack').checked=true;await controller.createIntent();const pending=structuredClone(controller.currentBinding());
assert.equal(pending.status,'approved');assert.equal(get('ack').checked,false);assert.equal(get('mock-ack').checked,false);
assert.ok(!calls.some(v=>v.path.endsWith('/process')));await controller.processSelected();const done=structuredClone(controller.currentBinding());
assert.equal(done.status,'succeeded');assert.equal(done.result.frames.length,8);assert.equal(done.result.mock,true);assert.equal(done.result.semantic_inference_performed,false);
assert.equal(done.result.hard_qc_replaced,false);assert.equal(done.result.owner_uat_accepted,false);assert.equal(get('results').children.filter(v=>v.tagName==='FIGURE').length,8);
count=calls.length;await controller.processSelected();assert.equal(calls.length,count);await controller.readSelected();assert.deepEqual(controller.currentBinding(),done);
controller.prepareNew();get('ack').checked=get('mock-ack').checked=true;await controller.createIntent();const cancellable=structuredClone(controller.currentBinding());
assert.notEqual(cancellable.vision_id,done.vision_id);await controller.cancelSelected();assert.equal(controller.currentBinding().status,'cancelled');
const cancelled=structuredClone(controller.currentBinding());state.canManage=false;controller.sync();await controller.readHistory();
assert.equal(get('config').disabled,true);assert.equal(get('create').disabled,true);assert.equal(get('process').disabled,true);assert.ok(get('history-list').children.length>=2);
assert.deepEqual(await api('/api/projects/'+config.project),original);assert.deepEqual(await api('/api/session'),session);
assert.equal(messages.length,3);assert.ok(!calls.some(v=>v.path.endsWith('/jobs')||v.path.includes('official-vision')));
process.stdout.write(JSON.stringify({status:'PASS',runtime,input,original_project:original,done,cancelled,frame_proofs:frameProofs,calls,
  signed_http:true,dom_controller_tested:true,actual_parent_browser_executed:false,external_dispatches:0,paid_operations:0,real_provider_tested:false,owner_uat_accepted:false})+'\n');
