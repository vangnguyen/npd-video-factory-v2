// DOM controller through actual signed local HTTP; no browser/provider/UAT acceptance.
import assert from 'node:assert/strict';import{initializeNativeOfficialVision}from'../apps/studio-web/native-official-vision.mjs';
let input='';for await(const chunk of process.stdin)input+=chunk;const config=JSON.parse(input);
assert.match(config.origin,/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/);const calls=[],messages=[];
const reply=await fetch(config.origin+'/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:config.token}),signal:AbortSignal.timeout(10000)});assert.equal(reply.status,200);const login=await reply.json(),cookie=reply.headers.getSetCookie()[0].split(';')[0];
async function api(path,body){assert.match(path,/^\/api\//);const r=await fetch(config.origin+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json','Cookie':cookie,'X-VF-CSRF':login.csrf},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(10000)});const value=await r.json();calls.push({method:body?'POST':'GET',route:path.split('?')[0],status:r.status});assert.equal(r.status,200);return value;}
const session=await api('/api/session');assert.equal(session.access.mode,'registry');assert.equal(session.capabilities.native_official_vision,false);
for(const[path,pattern]of[['/native.html',/id="native-official-vision-card" hidden/],['/native.mjs',/initializeNativeOfficialVision/],['/native-official-vision.mjs',/validateOfficialVisionHistory/]]){
 const r=await fetch(config.origin+path,{headers:{Cookie:cookie},signal:AbortSignal.timeout(10000)});assert.equal(r.status,200);assert.match(await r.text(),pattern);calls.push({method:'GET',route:path,status:r.status});}
const nodes=new Map();class Node{constructor(){this.children=[];this.value='';this.checked=false;this.dataset={};this.listeners={};this.textContent='';this.style={};}set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=[...v];}addEventListener(k,v){this.listeners[k]=v;}}
const root={createElement:()=>new Node(),getElementById(v){if(!nodes.has(v))nodes.set(v,new Node());return nodes.get(v);}},get=id=>root.getElementById('native-official-vision-'+id);
const state={workspace_id:session.access.workspace_id,project:null,canManage:true,dirty:false,busy:false,active:false};
const controller=initializeNativeOfficialVision({root,api,getState:()=>({...state}),onMessage:(...v)=>messages.push(v)});assert.equal(calls.length,4);
async function ready(project){state.project=await api('/api/projects/'+project);controller.sync();await controller.readConfig();await controller.readSources();
 get('profile').value=get('profile').children[1].value;get('observation').value=get('observation').children[1].value;get('ceiling').value='500';get('duration').value='600';get('ack').checked=get('mock-ack').checked=true;controller.controls();}
const rows=[];
for(const[index,project]of[config.projects[0],config.projects[1],config.projects[0],config.projects[1]].entries()){
 await ready(project);const before=calls.length;await controller.createIntent();assert.equal(calls.length,before+1);assert.equal(controller.currentBinding().status,'approved');assert.equal(get('ack').checked,false);
 if(index===3)await controller.cancelSelected();else await controller.processSelected();
 const row=structuredClone(controller.currentBinding());assert.equal(row.status,index<2?'succeeded':index===2?'review_required':'cancelled');
 if(index<2){assert.equal(row.result.mock,true);assert.equal(row.result.semantic_inference_performed,false);assert.equal(row.result.frames.length,index===0?1:8);assert.equal(row.result.automatic_planning_eligible,false);}
 await controller.readSelected();assert.deepEqual(controller.currentBinding(),row);await controller.readHistory();rows.push(row);
}
assert.equal(messages.length,0);const count=calls.length;controller.sync();controller.controls();assert.equal(calls.length,count);
assert.equal((await api('/api/session')).capabilities.native_official_vision,false);
process.stdout.write(JSON.stringify({schema_version:'native-official-vision-studio-controller-proof-v1',rows,calls,messages:[],
 signed_http:true,actual_parent_browser_executed:false,no_browser_automation:true,real_provider_tested:false,owner_uat_accepted:false,canonical_timeline_mutated:false,publishing_enabled:false})+'\n');
