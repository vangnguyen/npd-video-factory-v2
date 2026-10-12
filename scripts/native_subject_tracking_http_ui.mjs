import assert from'node:assert/strict';import{readFileSync}from'node:fs';
import{initializeSubjectTracking}from'../apps/studio-web/native-subject-tracking.mjs';
const input=JSON.parse(readFileSync(process.argv[2],'utf8'));assert.equal(input.fixture_human,true);assert.match(input.origin,/^http:\/\/127\.0\.0\.1:\d+$/);
const requests=[],messages=[];async function api(path,body){const r=await fetch(input.origin+path,{method:body?'POST':'GET',headers:{Cookie:'vf_native_session='+input.cookie,'X-VF-CSRF':input.csrf,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const v=await r.json();requests.push({path,status:r.status,body:body??null});assert.equal(r.status,200,JSON.stringify(v));return v;}
class Node{constructor(){this.children=[];this.listeners={};this.attrs={};this.value='';this.checked=false;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}setAttribute(k,v){this.attrs[k]=v;}getAttribute(k){return this.attrs[k]??null;}removeAttribute(k){delete this.attrs[k];}addEventListener(k,f){this.listeners[k]=f;}}
let project=await api('/api/projects/'+input.project_id),dirty=false;
const ui=initializeSubjectTracking({root:new Node(),dom:{createElement:()=>new Node()},api,getState:()=>({workspace_id:input.workspace_id,project,canEdit:true,canTrack:true,busy:false,dirty,dirtyPart:dirty?'tracking':null,active:project.jobs.some(v=>['queued','running','retrying'].includes(v.status))}),
 onProject:v=>project=v,onDirty:v=>dirty=v,onMessage:(...v)=>messages.push(v),newKey:()=>input.request_key});
for(const[k,v]of Object.entries({x:12.5,y:30,width:12.5,height:100/6})){ui.fields[k].value=String(v);ui.fields[k].listeners.input();}
await ui.run('job');const deadline=Date.now()+60000;let job;
while(Date.now()<deadline){project=await api('/api/projects/'+input.project_id);job=project.jobs.find(v=>v.kind==='source_tracking');if(job&&!['queued','running','retrying'].includes(job.status))break;await new Promise(done=>setTimeout(done,100));}
assert.equal(job?.status,'succeeded',JSON.stringify(job?.error));const record=project.document.source_tracking_analyses[0];assert.equal(record.analysis.status,input.expected_status);
assert.equal(record.analysis.confidence,null);assert.equal(record.analysis.semantic_inference_performed,false);assert.equal(record.analysis.decoded_pts_verified,true);assert.equal(record.analysis.external_provider_calls,0);
ui.controls();ui.ack.checked=true;ui.ratios.value='9:16';await ui.run('crop');assert.equal(project.document.canonical_timeline.snapshot.metadata.local_tracking_selection.record_sha256,record.sha256);
const plan=project.document.canonical_timeline.snapshot.metadata.source_reframe_plan.plan;assert.equal(plan.fallback,input.expected_status==='tracked'?'none':'center_crop');assert.equal(plan.needs_attention,true);
process.stdout.write(JSON.stringify({actual_shipped_controller:true,actual_signed_HTTP:true,fake_DOM:true,browser_rendered:false,owner_UAT:false,requests,messages,tracking_job:job,record,project,source_crop_plan:plan,provider_calls:0,paid_calls:0})+'\n');
