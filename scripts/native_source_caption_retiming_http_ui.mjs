// Actual shipped caption controller plus signed source timeline API, fake DOM.
import assert from'node:assert/strict';import{readFileSync}from'node:fs';import{randomUUID}from'node:crypto';
import{initializeSourceMediaTracks}from'../apps/studio-web/native-source-media-tracks.mjs';
const input=JSON.parse(readFileSync(process.argv[2],'utf8'));assert.equal(input.fixture_human,true);assert.match(input.origin,/^http:\/\/127\.0\.0\.1:\d+$/);
class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.value='';this.checked=false;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,f){(this.listeners[k]??=[]).push(f);}}
const card=new Node('details');card.id='native-source-media-tracks-card';const walk=(n,id)=>n.id===id?n:n.children.map(c=>walk(c,id)).find(Boolean);
const root={getElementById:id=>walk(card,id),createElement:t=>new Node(t)},state={workspace_id:input.workspace_id,project:input.project,canEdit:true,busy:false,dirty:false,dirtyPart:null,active:false};
const requests=[],messages=[],base='/api/projects/'+input.project.id+'/auto-edit',api=async(path,body)=>{
  assert.ok(path===base+'/timeline'||path.startsWith(base+'/media-tracks'));const r=await fetch(input.origin+path,{method:body?'POST':'GET',
    headers:{Cookie:'vf_native_session='+input.cookie,'X-VF-CSRF':input.csrf,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
  const v=await r.json();requests.push({path,method:body?'POST':'GET',status:r.status,revision:v.revision,timeline_version:v.timeline_version??v.shot_timeline?.version});
  assert.equal(r.status,200,JSON.stringify(v));return v;};
const controller=initializeSourceMediaTracks({root,getState:()=>state,api,requestKey:()=>randomUUID(),onWorking:v=>{state.busy=v;},onDirty:v=>{state.dirty=v;state.dirtyPart=v?'source_media_tracks':null;},
  onSaved:async v=>{state.project.revision=v.revision;},onMessage:(...v)=>messages.push(v)});
const node=id=>root.getElementById('native-source-media-tracks-'+id),emit=(n,event)=>{for(const f of n.listeners[event]??[])f();};
async function map(){node('timebase').value='source';emit(node('timebase'),'change');assert.equal(node('source-video').hidden,false);assert.equal(node('save-subtitle').disabled,true);
  node('source-video').value=input.source_video_asset_id;emit(node('source-video'),'change');await controller.applySubtitles();assert.ok(controller.currentBinding(),JSON.stringify(messages));
  assert.ok(controller.currentBinding().captions.every(c=>c.source_video_mapping_mode==='follow_video'&&!c.has_word_timing));}
async function video(operation){const page=await api(base+'/timeline');const clip=page.shot_timeline.snapshot.tracks.find(t=>t.type==='video'&&t.kind==='source').clips[0];
  const changed=await api(base+'/timeline',{revision:page.revision,action:'linked_edit',payload:{expected_version:page.shot_timeline.version,operation:{clip_id:clip.clip_id,...operation}}});
  state.project.revision=changed.revision;controller.sync();await controller.load();return changed;}
assert.equal(requests.length,0);await controller.load();const initial=structuredClone(controller.currentBinding());assert.equal(initial.timeline_mode,'source');
assert.equal(initial.source_video_assets[0].asset_sha256,input.source_video_asset_sha256);await map();const imported=structuredClone(controller.currentBinding());assert.equal(imported.captions_total,2);
await video({type:'split',at_seconds:1.5});const split=structuredClone(controller.currentBinding());assert.equal(split.captions_total,3);
await video({type:'duplicate',timeline_start:3});const duplicate=structuredClone(controller.currentBinding());assert.equal(duplicate.captions_total,5);assert.equal(duplicate.duration_seconds,4.5);
await video({type:'reorder',target_index:2});const reordered=structuredClone(controller.currentBinding());assert.equal(reordered.captions_total,5);
const first=[...controller.fields.values()][0];first.text.value='Chữ Việt đã sửa · giữ vị trí thủ công';emit(first.text,'input');await controller.saveCaptionEdits();const edited=structuredClone(controller.currentBinding());
assert.ok(edited.captions.every(c=>c.source_video_mapping_mode==='human_layout'));await video({type:'set_clip_properties',speed:2});const manual=structuredClone(controller.currentBinding());
assert.deepEqual(manual.captions,edited.captions);await map();const remapped=structuredClone(controller.currentBinding());assert.equal(remapped.duration_seconds,3.75);assert.equal(remapped.imports_total,2);
assert.ok(remapped.captions.every(c=>c.source_video_mapping_mode==='follow_video'));await controller.load();const reopened=structuredClone(controller.currentBinding());const {mutation:remapReceipt,...savedCatalog}=remapped;assert.deepEqual(reopened,savedCatalog);
process.stdout.write(JSON.stringify({schema_version:'native-source-caption-retiming-controller-proof-v1',fixture_human:true,fake_DOM:true,actual_signed_HTTP:true,
  caption_mutations_use_shipped_Studio_controller:true,source_video_mutations_use_API_not_shot_UI:true,saved_ASR_fixture:true,synthetic_moving_video_and_tones:true,
  real_provider_calls:0,paid_calls:0,browser_rendered:false,owner_UAT:false,publishing_enabled:false,requests,initial,imported,split,duplicate,reordered,edited,manual,remapped,reopened,messages})+'\n');
