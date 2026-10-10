// Actual shipped Source drag/drop and caption controllers through signed HTTP.
// Event elements are fixtures; whole Source parent DOM/browser UAT are not run.
import assert from'node:assert/strict';import{readFileSync}from'node:fs';import{randomUUID}from'node:crypto';
import{initializeSourceDragDrop}from'../apps/studio-web/native-source-drag-drop.mjs';
import{initializeSourceMediaTracks}from'../apps/studio-web/native-source-media-tracks.mjs';
import{sourceClipAction,sourceRequest}from'../apps/studio-web/native-source-editor.mjs';import{pixelsPerSecond}from'../apps/studio-web/studio-utils.mjs';
const input=JSON.parse(readFileSync(process.argv[2],'utf8'));assert.equal(input.fixture_human,true);assert.match(input.origin,/^http:\/\/127\.0\.0\.1:\d+$/);
const base='/api/projects/'+input.project.id+'/auto-edit',requests=[],messages=[];
async function api(path,body){assert.ok(path===base+'/timeline'||path.startsWith(base+'/media-tracks'));const r=await fetch(input.origin+path,{method:body?'POST':'GET',
  headers:{Cookie:'vf_native_session='+input.cookie,'X-VF-CSRF':input.csrf,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
  const p=await r.json();requests.push({path,body:body??null,status:r.status});assert.equal(r.status,200,JSON.stringify(p));return p;}
let project=await api(base+'/timeline');const snapshot=()=>project.document.canonical_timeline.snapshot,primary=()=>snapshot().tracks.find(t=>t.kind==='source'),copy=v=>structuredClone(v);
class Node{constructor(t){this.tagName=t.toUpperCase();this.children=[];this.listeners={};this.value='';this.checked=false;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,f){(this.listeners[k]??=[]).push(f);}}
const card=new Node('details');card.id='native-source-media-tracks-card';const walk=(n,id)=>n.id===id?n:n.children.map(c=>walk(c,id)).find(Boolean);
const dom={getElementById:id=>walk(card,id),createElement:t=>new Node(t)},state=()=>({workspace_id:input.workspace_id,project,canEdit:true,busy:false,dirty:false,active:false});
const captions=initializeSourceMediaTracks({root:dom,getState:state,api,requestKey:()=>randomUUID(),onSaved:async()=>{project=await api(base+'/timeline');},onMessage:(...v)=>messages.push(v)});
await captions.load();const field=id=>dom.getElementById('native-source-media-tracks-'+id),emit=(n,k)=>{for(const f of n.listeners[k]??[])f();};
field('timebase').value='source';emit(field('timebase'),'change');field('source-video').value=input.source_video_asset_id;emit(field('source-video'),'change');
await captions.applySubtitles();assert.ok(captions.currentBinding(),JSON.stringify(messages));const remapped=copy(project);
assert.ok(captions.currentBinding().captions.every(c=>c.source_video_mapping_mode==='follow_video'));
const first=primary().clips[0].clip_id;project=await api(base+'/timeline',sourceClipAction(project,first,'split',{at_seconds:1.5}));const split=copy(project);assert.equal(primary().clips.length,2);
const listeners={},root={addEventListener:(k,f)=>{listeners[k]=f;},querySelectorAll:()=>[]},zoom=2;
const drag=initializeSourceDragDrop({root,getState:()=>({...state(),timeline:project.document.canonical_timeline,zoom,snapping:true}),onMessage:(...v)=>messages.push(v),
  onMove:async(at,binding)=>{assert.equal(binding.timeline_sha256,project.document.canonical_timeline.sha256);project=await api(base+'/timeline',sourceClipAction(project,binding.clip_id,'move',{timeline_start:at}));
    return project.id===binding.project_id&&project.revision===binding.revision+1&&project.document.canonical_timeline.version===binding.timeline_version+1;}});
async function move(clip,track,at){const lane={dataset:{sourceLane:track.track_id},closest:()=>lane,getBoundingClientRect:()=>({left:-10})},
  target={dataset:{sourceClip:clip.clip_id},closest:()=>target,getBoundingClientRect:()=>({left:30})};
  listeners.dragstart({target,clientX:36,preventDefault(){},dataTransfer:{setData(){},getData(){throw Error('Foreign drag payload used');}}});
  await listeners.drop({target:lane,clientX:-10+6+at*pixelsPerSecond(zoom),preventDefault(){}});assert.ok(!drag.isWorking());}
await move(primary().clips[0],primary(),1.73);const moved=copy(project);assert.deepEqual(primary().clips.map(c=>[c.source_start,c.source_end,c.timeline_start,c.duration]),[[1.5,3,0,1.5],[0,1.5,1.5,1.5]]);
assert.equal(requests.at(-1).body.action,'linked_edit');assert.equal(requests.at(-1).body.payload.operation.timeline_start,1.75);
const windows=t=>t.clips.map(c=>[c.source_start,c.source_end,c.timeline_start,c.duration,c.speed,c.disabled]);assert.deepEqual(windows(primary()),windows(snapshot().tracks.find(t=>t.kind==='original_audio')));
captions.sync();await captions.load();const followed=copy(captions.currentBinding());assert.ok(followed.captions.every(c=>c.source_video_mapping_mode==='follow_video'));
assert.deepEqual(followed.captions.map(c=>[c.timeline_start,c.duration]),[[0,.7],[1.6,.9],[2.8,.2]]);
const importedVoice=snapshot().tracks.find(t=>t.kind==='voice'&&t.clips.some(c=>c.metadata.native_media_import_id)),videoBefore=copy(primary());
await move(importedVoice.clips[0],importedVoice,.37);const final=copy(project);assert.equal(requests.at(-1).body.action,'edit');assert.deepEqual(primary(),videoBefore);
assert.equal(snapshot().tracks.find(t=>t.track_id===importedVoice.track_id).clips[0].timeline_start,.25);
project=await api(base+'/timeline',sourceRequest(project,'restore',{restore_revision:split.revision}));const undo=copy(project);assert.equal(project.document.canonical_timeline.sha256,split.document.canonical_timeline.sha256);
project=await api(base+'/timeline',sourceRequest(project,'restore',{restore_revision:final.revision}));const redo=copy(project);assert.equal(project.document.canonical_timeline.sha256,final.document.canonical_timeline.sha256);
project=await api(base+'/timeline');assert.deepEqual(project,redo);
console.log(JSON.stringify({schema_version:'native-source-drag-drop-controller-proof-v1',fixture_human:true,fake_DOM:true,actual_signed_HTTP:true,
  actual_shipped_drag_drop_controller:true,actual_shipped_caption_import_controller:true,whole_source_editor_DOM_exercised:false,browser_rendered:false,owner_UAT:false,
  source_ripple_order_and_original_audio_windows_equal:true,source_SRT_follow_reflow:true,independent_voice_placement_preserves_primary:true,
  undo_redo_exact_snapshot:true,source_duration_seconds:3,provider_calls:0,paid_calls:0,saved_ASR_fixture:true,synthetic_moving_video_and_tones:true,
  requests,messages,remapped,split,moved,followed,final,undo,redo,reopened:project}));
