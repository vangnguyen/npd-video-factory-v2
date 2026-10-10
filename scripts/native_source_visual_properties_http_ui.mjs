// Shipped shared visual widget + Source request helpers, signed owned HTTP.
// The whole Source editor DOM and browser/human review are not exercised here.
import assert from 'node:assert/strict';import{readFileSync}from'node:fs';
import{initializeVisualProperties}from'../apps/studio-web/native-visual-properties.mjs';
import{sourceClipAction,sourceRequest,sourceReframeRequest}from'../apps/studio-web/native-source-editor.mjs';
const input=JSON.parse(readFileSync(process.argv[2],'utf8'));assert.equal(input.fixture_human,true);assert.match(input.origin,/^http:\/\/127\.0\.0\.1:\d+$/);
class Node{constructor(t){this.tagName=t.toUpperCase();this.children=[];this.listeners={};this.value='';}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,f){(this.listeners[k]??=[]).push(f);}}
const root=new Node('section');root.id='native-source-visual';const dom={createElement:t=>new Node(t)},requests=[],messages=[],base='/api/projects/'+input.project.id+'/auto-edit/timeline';
async function api(body){const r=await fetch(input.origin+base,{method:body?'POST':'GET',headers:{Cookie:'vf_native_session='+input.cookie,'X-VF-CSRF':input.csrf,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
  const value=await r.json();requests.push({body:body??null,status:r.status,revision:value.revision});assert.equal(r.status,200,JSON.stringify(value));return value;}
let project=await api(),dirty=false;const state=()=>project.document.canonical_timeline;
const selected=()=>{const track=state().snapshot.tracks.find(t=>t.type==='video'&&t.kind==='source');return{track,clip:track.clips[0]};};
project=await api(sourceReframeRequest(project,{aspect_ratio:state().snapshot.aspect_ratio,mode:'center_crop',points:[]}));
assert.ok(selected().clip.metadata.reframe,'An actual fallback crop path is required to test preservation/replacement');
const before=structuredClone(project),beforeOther=before.document.canonical_timeline.snapshot.tracks.filter(t=>t.type!=='video'),window=c=>[c.asset_id,c.source_start,c.source_end,c.timeline_start,c.duration,c.speed];
const v=initializeVisualProperties({root,dom,getState:()=>({workspace_id:input.workspace_id,project,timeline:state(),selected:selected(),canEdit:true,dirty,dirtyPart:dirty?'visual':null}),
  onDirty:b=>{dirty=b;},onMessage:(...args)=>messages.push(args),onSave:async(values,binding)=>{assert.equal(binding.timeline_sha256,state().sha256);project=await api(sourceClipAction(project,binding.clip_id,'set_clip_properties',values));return project.revision===binding.revision+1&&state().version===binding.timeline_version+1;}});
async function change(values){for(const [key,value]of Object.entries(values)){v.controls[key].value=String(value);v.controls[key].listeners.input[0]();}await v.save();assert.equal(dirty,false,JSON.stringify(messages));}
await change({scale:110,rotation_degrees:8,opacity:92});const transformed=structuredClone(project);
assert.deepEqual(selected().clip.metadata.reframe,before.document.canonical_timeline.snapshot.tracks.find(t=>t.kind==='source').clips[0].metadata.reframe);
assert.ok(!('crop' in requests.at(-1).body.payload.operation),'Transform-only save must preserve the automatic crop path');
await change({crop_x:10,crop_y:10,crop_width:80,crop_height:80,x:2});const changed=structuredClone(project),actual=selected().clip;
assert.deepEqual(actual.crop,{x:.1,y:.1,width:.8,height:.8});assert.deepEqual(actual.transform,{x:.02,y:0,scale:1.1,rotation_degrees:8});assert.equal(actual.opacity,.92);
assert.equal(actual.metadata.reframe,undefined);assert.equal(actual.metadata.reframe_manual_override,true);
assert.deepEqual(window(actual),window(before.document.canonical_timeline.snapshot.tracks.find(t=>t.kind==='source').clips[0]));
assert.deepEqual(state().snapshot.tracks.filter(t=>t.type!=='video'),beforeOther);
project=await api(sourceRequest(project,'restore',{restore_revision:before.revision}));const undo=structuredClone(project);assert.equal(state().sha256,before.document.canonical_timeline.sha256);
project=await api(sourceRequest(project,'restore',{restore_revision:changed.revision}));const redo=structuredClone(project);assert.equal(state().sha256,changed.document.canonical_timeline.sha256);v.sync();
project=await api();assert.deepEqual(project,redo);
console.log(JSON.stringify({schema_version:'native-source-visual-properties-controller-proof-v1',fixture_human:true,fake_DOM:true,actual_signed_HTTP:true,
  actual_shared_visual_widget:true,source_request_helpers:true,source_parent_controller_initialized:false,browser_rendered:false,owner_UAT:false,
  saved_ASR_fixture:true,synthetic_moving_video_and_tones:true,provider_calls:0,paid_calls:0,publishing_enabled:false,
  transform_only_preserves_crop_path:true,manual_crop_replaces_only_selected_clip_path:true,source_windows_unchanged:true,other_tracks_unchanged:true,
  undo_redo_exact_snapshot:true,requests,messages,before,transformed,changed,undo,redo,reopened:project}));
