// Actual Source media controller against owned signed local HTTP; fake DOM only.
import assert from'node:assert/strict';import{readFileSync}from'node:fs';import{randomUUID}from'node:crypto';
import{initializeSourceMediaTracks}from'../apps/studio-web/native-source-media-tracks.mjs';
const input=JSON.parse(readFileSync(process.argv[2],'utf8'));assert.equal(input.fixture_human,true);assert.match(input.origin,/^http:\/\/127\.0\.0\.1:\d+$/);
class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.value='';this.checked=false;}
  append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,fn){(this.listeners[k]??=[]).push(fn);}}
const card=new Node('details');card.id='native-source-media-tracks-card';const walk=(n,id)=>n.id===id?n:n.children.map(c=>walk(c,id)).find(Boolean);
const root={getElementById:id=>walk(card,id),createElement:t=>new Node(t)},state={workspace_id:input.workspace_id,project:input.project,canEdit:true,busy:false,dirty:false,dirtyPart:null,active:false};
const requests=[],saved=[],messages=[];
const controller=initializeSourceMediaTracks({root,getState:()=>state,requestKey:()=>randomUUID(),
  api:async(path,body)=>{assert.match(path,/^\/api\/projects\/[a-f0-9]{32}\/auto-edit\/media-tracks(?:\/(?:audio|subtitles|captions))?(?:\?caption_page=\d+)?$/);
    const r=await fetch(input.origin+path,{method:body?'POST':'GET',headers:{Cookie:'vf_native_session='+input.cookie,'X-VF-CSRF':input.csrf,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
    const value=await r.json();requests.push({method:body?'POST':'GET',path,status:r.status,revision:value.revision,timeline_version:value.timeline_version});assert.equal(r.status,200,JSON.stringify(value));assert.equal(r.headers.get('Cache-Control'),'no-store');return value;},
  onWorking:v=>{state.busy=v;},onDirty:v=>{state.dirty=v;state.dirtyPart=v?'source_media_tracks':null;},onSaved:async v=>{saved.push(v);state.project.revision=v.revision;},onMessage:(...v)=>messages.push(v)});
const node=n=>root.getElementById('native-source-media-tracks-'+n),emit=(n,event)=>{for(const f of n.listeners[event]??[])f();};
assert.equal(requests.length,0);await controller.load();assert.equal(controller.currentBinding().assets.length,3,JSON.stringify(messages));
const initial=structuredClone(controller.currentBinding()),narrated=initial.timeline_mode==='narrated',mapped=Boolean(input.source_video_asset_id);
if(narrated){assert.equal(initial.pending_generated_tracks,true);assert.equal(node('timebase').disabled,!initial.source_video_mapping_available);assert.equal(node('timebase').value,'timeline');}
if(mapped){assert.equal(initial.source_video_mapping_available,true);assert.equal(initial.source_video_assets.find(a=>a.asset_id===input.source_video_asset_id)?.asset_sha256,input.source_video_asset_sha256);}
node('timeline-start').value='.5';emit(node('timeline-start'),'input');await controller.applyAudio();assert.equal(saved.length,1,JSON.stringify(messages));
const music=controller.currentBinding().assets.find(a=>a.role==='music');node('audio').value=music.asset_id;emit(node('audio'),'change');node('role').value='music';emit(node('role'),'change');
node('loop').checked=true;emit(node('loop'),'change');node('repeat-until').value='3';node('crossfade').value='.2';node('fade-in').value='.1';node('fade-out').value='.1';
await controller.applyAudio();assert.equal(saved.length,2,JSON.stringify(messages));assert.equal(saved[1].mutation.clip_ids.length,2);
if(mapped){node('timebase').value='source';emit(node('timebase'),'change');assert.equal(node('source-video').hidden,false);assert.equal(node('save-subtitle').disabled,true);node('source-video').value=input.source_video_asset_id;emit(node('source-video'),'change');}
await controller.applySubtitles();assert.equal(saved.length,3,JSON.stringify(messages));assert.equal(controller.currentBinding().captions_total,mapped&&narrated?4:2);
if(mapped){assert.equal(saved[2].mutation.source_video_asset_id,input.source_video_asset_id);assert.equal(saved[2].mutation.source_video_asset_sha256,input.source_video_asset_sha256);assert.ok(saved[2].captions.every(c=>c.source_video_mapping_mode==='follow_video'));}
const caption=[...controller.fields.values()][0];caption.text.value='Vinhomes Cần Giờ · chữ Việt đã chỉnh qua Studio';caption.start.value='.2';caption.duration.value='.7';emit(caption.text,'input');
await controller.saveCaptionEdits();assert.equal(saved.length,4,JSON.stringify(messages));assert.equal(state.dirty,false);assert.equal(controller.currentBinding().captions[0].text,caption.text.value);
await controller.load();assert.equal(requests.length,6);assert.equal(controller.currentBinding().imports_total,3);
if(mapped)assert.ok(controller.currentBinding().captions.every(c=>c.source_video_mapping_mode==='human_layout'));
process.stdout.write(JSON.stringify({schema_version:'native-source-media-tracks-signed-controller-proof-v1',requests,
  revision:controller.currentBinding().revision,timeline_version:controller.currentBinding().timeline_version,imports:controller.currentBinding().imports,
  captions:controller.currentBinding().captions,fixture_human:true,fake_DOM:true,saved_ASR_fixture:!narrated,actual_local_media_and_HTTP:true,
  ...(narrated?{timeline_mode:'narrated',synthetic_measured_narration_fixture:true,genuine_speech_quality_accepted:false}:{}),
  ...(mapped?{source_video_mapping:true,source_video_asset_id:input.source_video_asset_id,source_video_asset_sha256:input.source_video_asset_sha256,
    initial,audio:saved[0],music:saved[1],subtitles:saved[2],edited:saved[3],reopened:controller.currentBinding()}:{}),
  original_sources_preserved:true,ASR_or_TTS_dispatch_from_controller:0,real_provider_calls:0,paid_calls:0,browser_rendered:false,owner_UAT:false,publishing_enabled:false})+'\n');
