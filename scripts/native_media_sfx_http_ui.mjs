// Shipped media card against owned signed HTTP. DOM and speech are fixtures.
import assert from'node:assert/strict';import{readFileSync}from'node:fs';import{randomUUID}from'node:crypto';
import{initializeSourceMediaTracks}from'../apps/studio-web/native-source-media-tracks.mjs';
const input=JSON.parse(readFileSync(process.argv[2],'utf8'));assert.equal(input.fixture_human,true);assert.match(input.origin,/^http:\/\/127\.0\.0\.1:\d+$/);
class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.value='';this.checked=false;}
  append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,fn){(this.listeners[k]??=[]).push(fn);}}
const card=new Node('details');card.id='native-source-media-tracks-card';const walk=(n,id)=>n.id===id?n:n.children.map(c=>walk(c,id)).find(Boolean);
const root={getElementById:id=>walk(card,id),createElement:t=>new Node(t)},state={workspace_id:input.workspace_id,project:input.project,canEdit:true,busy:false,dirty:false,dirtyPart:null,active:false};
const requests=[],saved=[],messages=[];
const controller=initializeSourceMediaTracks({root,getState:()=>state,requestKey:()=>randomUUID(),
  api:async(path,body)=>{assert.match(path,/^\/api\/projects\/[a-f0-9]{32}\/auto-edit\/media-tracks(?:\/audio)?$/);
    const r=await fetch(input.origin+path,{method:body?'POST':'GET',headers:{Cookie:'vf_native_session='+input.cookie,'X-VF-CSRF':input.csrf,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
    const value=await r.json();requests.push({method:body?'POST':'GET',path,status:r.status,...(body?{body}:{}),revision:value.revision,timeline_version:value.timeline_version});assert.equal(r.status,200,JSON.stringify(value));return value;},
  onWorking:v=>{state.busy=v;},onDirty:v=>{state.dirty=v;state.dirtyPart=v?'source_media_tracks':null;},onSaved:async v=>{saved.push(v);state.project.revision=v.revision;},onMessage:(...v)=>messages.push(v)});
const node=n=>root.getElementById('native-source-media-tracks-'+n),emit=(n,event)=>{for(const f of n.listeners[event]??[])f();};
assert.equal(requests.length,0);await controller.load();const initial=structuredClone(controller.currentBinding());
const asset=initial.assets.find(a=>a.asset_id===input.sfx_asset_id);assert.equal(asset?.asset_sha256,input.sfx_asset_sha256);
node('audio').value=asset.asset_id;emit(node('audio'),'change');node('role').value='sfx';emit(node('role'),'change');
assert.equal(node('loop').disabled,true);assert.equal(node('audio-captions').disabled,true);
node('source-start').value='.1';node('source-end').value='.6';node('timeline-start').value='.9';node('volume').value='.3';node('fade-in').value='.05';node('fade-out').value='.05';
await controller.applyAudio();assert.equal(saved.length,1,JSON.stringify(messages));assert.equal(requests.length,2);
const result=saved[0];assert.equal(result.tracks.find(t=>t.track_id===result.mutation.track_id)?.kind,'sfx');assert.equal(result.mutation.asset_sha256,asset.asset_sha256);
assert.deepEqual(result.mutation.source_window,[.1,.6]);assert.deepEqual(result.mutation.timeline_window,[.9,1.4]);assert.equal(result.mutation.speech_boundary_verified,false);
process.stdout.write(JSON.stringify({schema_version:'native-media-sfx-signed-controller-proof-v1',initial,saved:result,requests,fixture_human:true,fake_DOM:true,
  saved_ASR_fixture:initial.timeline_mode==='source',synthetic_measured_narration_fixture:initial.timeline_mode==='narrated',actual_signed_HTTP:true,actual_shipped_media_card:true,
  browser_rendered:false,whole_parent_editor_DOM_exercised:false,owner_UAT:false,provider_calls:0,paid_calls:0,publishing_enabled:false})+'\n');
