// Actual shipped controller, signed local HTTP; DOM/human/speech are fixtures.
import assert from'node:assert/strict';import{readFileSync}from'node:fs';import{initializeNarratedTimeline}from'../apps/studio-web/native-narrated-timeline.mjs';
import{pixelsPerSecond}from'../apps/studio-web/studio-utils.mjs';
const context=JSON.parse(readFileSync(process.argv[2],'utf8'));assert.equal(context.fixture_human,true);assert.match(context.origin,/^http:\/\/127\.0\.0\.1:\d+$/);
class Node{constructor(t){this.tagName=t.toUpperCase();this.children=[];this.listeners={};this.value='';this.checked=false;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,f){(this.listeners[k]??=[]).push(f);}}
const card=new Node('details');card.id='native-narrated-timeline-card';const walk=(n,id)=>n.id===id?n:n.children.map(c=>walk(c,id)).find(Boolean),root={getElementById:id=>walk(card,id),createElement:t=>new Node(t)};
const state={workspace_id:context.workspace_id,project:context.project,canEdit:true,busy:false,dirty:false,dirtyPart:null,active:false},requests=[],messages=[];
const controller=initializeNarratedTimeline({root,getState:()=>state,onWorking:v=>{state.busy=v;},onDirty:v=>{state.dirty=v;state.dirtyPart=v?'narrated_timeline':null;},onMessage:(...v)=>messages.push(v),onSaved:async v=>{state.project.revision=v.revision;},
  api:async(path,body)=>{assert.ok(path.startsWith('/api/projects/'+context.project.id+'/narrated-timeline'));const r=await fetch(context.origin+path,{method:body?'POST':'GET',headers:{Cookie:'vf_native_session='+context.cookie,'X-VF-CSRF':context.csrf,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const p=await r.json();requests.push({path,body:body??null,status:r.status});assert.equal(r.status,200,JSON.stringify(p));return p;}});
const field=id=>root.getElementById('native-narrated-timeline-'+id),saved=()=>{const p=structuredClone(controller.currentBinding());assert.ok(p,JSON.stringify(messages));return p;},primary=p=>p.snapshot.tracks.find(t=>t.track_id==='trk_native_video');
async function edit(id,type,values={}){field('clip').value=id;field('operation').value=type;for(const[k,v]of Object.entries(values))field(k).value=String(v);field('snap').checked=false;await controller.editClip();return saved();}
await controller.load();const initial=saved();assert.equal(initial.video_editing_available,true);assert.ok(field('clip').children.some(o=>o.value===primary(initial).clips[0].clip_id));
const source=primary(initial).clips[0],point=source.timeline_start+source.duration/2;const split=await edit(source.clip_id,'split',{playhead:point});assert.equal(primary(split).clips.length,primary(initial).clips.length+1);
const graph=field('graph'),target={dataset:{clip:source.clip_id},closest:()=>target,getBoundingClientRect:()=>({left:10})},lane={dataset:{track:'trk_native_video'},closest:()=>lane,getBoundingClientRect:()=>({left:10})};
await graph.listeners.dragstart[0]({target,clientX:10,preventDefault(){},dataTransfer:{setData(){}}});
await graph.listeners.drop[0]({target:lane,clientX:10+.2*pixelsPerSecond(1),preventDefault(){}});const dragged=saved();assert.equal(primary(dragged).clips.find(c=>c.clip_id===source.clip_id).timeline_start,.2);
const speed=await edit(source.clip_id,'set_clip_properties',{speed:2});const shortened=primary(speed).clips.find(c=>c.clip_id===source.clip_id);assert.ok(shortened.duration<source.duration/2);
const duplicate=await edit(source.clip_id,'duplicate',{start:source.timeline_start+shortened.duration});const added=primary(duplicate).clips.at(-1);assert.notEqual(added.clip_id,source.clip_id);
const reordered=await edit(added.clip_id,'reorder',{index:1});assert.equal(primary(reordered).clips[1].clip_id,added.clip_id);
const deleted=await edit(added.clip_id,'delete');assert.equal(primary(deleted).clips.length,primary(reordered).clips.length-1);await controller.restore('undo');const undo=saved();assert.equal(undo.timeline_sha256,reordered.timeline_sha256);
await controller.restore('redo');const redo=saved();assert.equal(redo.timeline_sha256,deleted.timeline_sha256);await controller.restore('undo');let final=saved();assert.equal(final.timeline_sha256,reordered.timeline_sha256);
let layout=null;
if(context.visual_properties===true){
  const before=saved();field('clip').value=source.clip_id;field('clip').listeners.change[0]();const v=controller.visualProperties;
  for(const [key,value] of [['crop_x',10],['crop_y',10],['crop_width',80],['crop_height',80],['x',2],['scale',110],['rotation_degrees',8],['opacity',92]]){v.controls[key].value=String(value);v.controls[key].listeners.input[0]();}
  await v.save();const changed=saved(),actual=primary(changed).clips.find(c=>c.clip_id===source.clip_id);
  assert.equal(changed.timeline_version,before.timeline_version+1,JSON.stringify(messages));assert.deepEqual(actual.crop,{x:.1,y:.1,width:.8,height:.8});
  assert.deepEqual(actual.transform,{x:.02,y:0,scale:1.1,rotation_degrees:8});assert.equal(actual.opacity,.92);
  await controller.restore('undo');const layoutUndo=saved();assert.equal(layoutUndo.timeline_sha256,before.timeline_sha256);
  await controller.restore('redo');final=saved();assert.equal(final.timeline_sha256,changed.timeline_sha256);
  assert.deepEqual(final.snapshot.tracks.filter(t=>t.type!=='video'),before.snapshot.tracks.filter(t=>t.type!=='video'));
  layout={before,changed,undo:layoutUndo,redo:final,clip_id:source.clip_id,actual_shared_visual_widget:true,other_tracks_unchanged:true};
}
const initialVoice=initial.snapshot.tracks.filter(t=>t.type==='audio');assert.deepEqual(final.snapshot.tracks.filter(t=>t.type==='audio'),initialVoice);assert.equal(final.duration_seconds,initial.duration_seconds);
await controller.load();const reopened=saved();assert.deepEqual(reopened,final);
console.log(JSON.stringify({schema_version:'native-narrated-video-controller-proof-v1',fixture_human:true,fake_DOM:true,actual_signed_HTTP:true,
  synthetic_tones_not_speech:true,browser_rendered:false,owner_UAT:false,provider_calls:0,paid_calls:0,actual_video_UI_operations:true,
  undo_redo_exact_snapshot:true,measured_audio_tracks_unchanged:true,actual_graph_drag_controller:true,...(layout?{visual_properties:layout}:{}),requests,messages,initial,split,dragged,speed,duplicate,reordered,deleted,undo,redo,final,reopened}));
