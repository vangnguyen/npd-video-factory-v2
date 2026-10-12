import test from 'node:test';import assert from 'node:assert/strict';
import{trackingJobRequest,trackedCropRequest,initializeSubjectTracking}from'../native-subject-tracking.mjs';
const H='a'.repeat(64),ID='b'.repeat(32),T='ltr_'+'c'.repeat(24);
function state(){return{workspace_id:'wsp_tracking',canEdit:true,canTrack:true,busy:false,active:false,dirty:false,project:{id:ID,revision:4,jobs:[],document:{assets:[],canonical_timeline:{version:2,sha256:H,snapshot:{aspect_ratio:'9:16',metadata:{native_auto_edit_schema:'native-auto-edit-timeline-v1',source_analysis_id:'ana_'+'d'.repeat(24)}}},source_tracking_analyses:[]}}};}
function record(){return{sha256:H,analysis:{project_id:ID,schema_version:'native-local-subject-tracking-v1',tracking_id:T,confidence:null,semantic_inference_performed:false,external_provider_calls:0,status:'tracked',sample_count:15}};}
class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.attrs={};this.value='';this.checked=false;}append(...n){this.children.push(...n);}replaceChildren(...n){this.children=n;}setAttribute(k,v){this.attrs[k]=v;}getAttribute(k){return this.attrs[k]??null;}removeAttribute(k){delete this.attrs[k];}addEventListener(k,f){this.listeners[k]=f;}}
function harness(){const s=state(),root=new Node('section'),calls=[],messages=[];let handler=async(path,body)=>body?{id:'e'.repeat(32),project_id:ID,kind:'source_tracking'}:s.project;
 const ui=initializeSubjectTracking({root,dom:{createElement:t=>new Node(t)},getState:()=>s,api:async(p,b)=>{calls.push({path:p,body:b});return handler(p,b);},onProject:value=>s.project=value,onMessage:(...v)=>messages.push(v),onDirty:v=>{s.dirty=v;s.dirtyPart=v?'tracking':null;},newKey:()=> 'owned-tracking-request-0001'});return{s,ui,calls,messages,root,handler:f=>handler=f};}
test('tracking job uses percent region and exact canonical version without a timeline mutation',()=>{
 const s=state(),before=structuredClone(s),body=trackingJobRequest(s,{x:20,y:25,width:20,height:25},'owned-request');assert.deepEqual(s,before);assert.deepEqual(body.tracking_request.configuration.seed_box,{x:.2,y:.25,width:.2,height:.25});assert.equal(body.tracking_request.expected_version,2);assert.equal(body.kind,'source_tracking');
 for(const region of[{x:90,y:0,width:20,height:20},{x:0,y:0,width:0,height:20},{x:'NaN',y:0,width:20,height:20}])assert.throws(()=>trackingJobRequest(s,region,'key'));
});
test('viewer, unavailable runtime, archived project and foreign dirty editor cannot queue or apply',()=>{
 for(const values of[{canEdit:false},{canTrack:false},{active:true},{busy:true},{dirty:true,dirtyPart:'style'}]){const s={...state(),...values};assert.throws(()=>trackingJobRequest(s,{x:20,y:25,width:20,height:25},'key'));assert.throws(()=>trackedCropRequest(s,record(),'9:16'));}
 const s=state();s.project.archived=true;assert.throws(()=>trackedCropRequest(s,record(),'9:16'));
});
test('crop request refuses foreign, semantic or fabricated-confidence evidence and keeps exact hash',()=>{
 const r=record(),body=trackedCropRequest(state(),r,'4:5');assert.equal(body.payload.mode,'local_tracking');assert.equal(body.payload.tracking_sha256,H);assert.equal(body.revision,4);
 for(const mutate of[v=>v.analysis.project_id='f'.repeat(32),v=>v.analysis.confidence=.9,v=>v.analysis.semantic_inference_performed=true,v=>v.analysis.external_provider_calls=1]){const value=record();mutate(value);assert.throws(()=>trackedCropRequest(state(),value,'9:16'));}
});
test('actual controller queues once and confirms a project refresh with no crop or approval',async()=>{
 const h=harness();h.ui.fields.x.value='30';h.ui.fields.x.listeners.input();await h.ui.run('job');assert.equal(h.calls.filter(v=>v.body).length,1);assert.equal(h.calls[0].body.tracking_request.configuration.seed_box.x,.3);assert.equal(h.ui.isDirty(),false);assert.equal(h.calls[1].path,'/api/projects/'+ID);assert.equal(h.ui.ack.checked,false);
});
test('uncertain queue cannot replay until an explicit project reload',async()=>{
 const h=harness();h.handler(async()=>{throw new Error('Unknown write outcome');});await h.ui.run('job');await h.ui.run('job');assert.equal(h.calls.filter(v=>v.body).length,1);assert.equal(h.ui.analyze.disabled,true);
 h.handler(async()=>h.s.project);await h.ui.reload.listeners.click();assert.equal(h.ui.analyze.disabled,false);
});
test('scope or permission changes clear private selections and ignore a late queued acknowledgement',async()=>{
 const h=harness();let done;h.handler(()=>new Promise(resolve=>{done=resolve;}));const sending=h.ui.run('job');h.s.workspace_id='wsp_next';h.s.canEdit=false;h.ui.controls();done({id:'e'.repeat(32),project_id:ID,kind:'source_tracking'});await sending;assert.equal(h.calls.length,1);assert.equal(h.ui.fields.x.value,'20');assert.equal(h.ui.ack.checked,false);assert.equal(h.ui.analyze.disabled,true);
});
test('crop application requires explicit acknowledgement and verifies the new project revision',async()=>{
 const h=harness();h.s.project.document.source_tracking_analyses=[record()];h.ui.controls();await h.ui.run('crop');assert.equal(h.calls.length,0);
 h.ui.ack.checked=true;h.handler(async()=>({...h.s.project,revision:5}));await h.ui.run('crop');assert.equal(h.calls[0].body.action,'reframe');assert.equal(h.s.project.revision,5);assert.equal(h.ui.ack.checked,false);
});
