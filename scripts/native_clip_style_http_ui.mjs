// Shipped shared style widget against signed owned HTTP. Whole parent/browser not initialized.
import assert from'node:assert/strict';import{readFileSync}from'node:fs';
import{initializeClipStyle}from'../apps/studio-web/native-clip-style.mjs';
import{sourceClipAction,sourceRequest}from'../apps/studio-web/native-source-editor.mjs';
const input=JSON.parse(readFileSync(process.argv[2],'utf8'));assert.equal(input.fixture_human,true);assert.match(input.origin,/^http:\/\/127\.0\.0\.1:\d+$/);
const narrated=input.clip_style_mode==='narrated',parity=input.clip_style_scenario==='parity',path='/api/projects/'+input.project.id+(narrated?'/narrated-timeline':'/auto-edit/timeline'),requests=[],messages=[];
async function api(body){const route=path+(narrated&&body?(body.operations?'/edit':'/restore'):'');const r=await fetch(input.origin+route,{method:body?'POST':'GET',headers:{Cookie:'vf_native_session='+input.cookie,'X-VF-CSRF':input.csrf,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const value=await r.json();requests.push({path:route,body:body??null,status:r.status});assert.equal(r.status,200,JSON.stringify(value));return value;}
let page=await api(),dirty=false,selection=null;
const timeline=()=>narrated?{version:page.timeline_version,sha256:page.timeline_sha256,snapshot:page.snapshot}:page.document.canonical_timeline;
const project=()=>narrated?{id:page.project_id,revision:page.revision}:page;
const selected=()=>{const t=timeline().snapshot.tracks.find(t=>t.clips.some(c=>c.clip_id===selection));return t?{track:t,clip:t.clips.find(c=>c.clip_id===selection)}:null;};
const bind=()=>({revision:page.revision,expected_version:timeline().version,timeline_sha256:timeline().sha256});
function edit(id,values){return narrated?{...bind(),operations:[{type:'set_clip_properties',clip_id:id,...values}]}:sourceClipAction(page,id,'set_clip_properties',values);}
class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.value='';}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,f){(this.listeners[k]??=[]).push(f);}}
const before=structuredClone(page),beforeSnapshot=structuredClone(timeline().snapshot);
if(parity&&!narrated){const clip=timeline().snapshot.tracks.find(t=>t.type==='video').clips[0];
  page=await api(sourceClipAction(page,clip.clip_id,'split',{at_seconds:clip.timeline_start+clip.duration/2}));}
const stylingSnapshot=structuredClone(timeline().snapshot);
const root=new Node('section'),dom={createElement:t=>new Node(t)};selection=timeline().snapshot.tracks.find(t=>t.type==='video').clips[0].clip_id;
const widget=initializeClipStyle({root,dom,getState:()=>({workspace_id:input.workspace_id,project:project(),timeline:timeline(),selected:selected(),canEdit:true,dirty,dirtyPart:dirty?'style':null,voice_input_current:page.voice_input_current}),
  onDirty:v=>{dirty=v;},onMessage:(...v)=>messages.push(v),onSave:async(values,binding)=>{assert.equal(binding.timeline_sha256,timeline().sha256);page=await api(edit(binding.clip_id,values));return page.revision===binding.revision+1&&timeline().version===binding.timeline_version+1;}});
function inputField(name,value){widget.controls[name].value=String(value);widget.controls[name].listeners.input[0]();}
function transition(name,kind,seconds){const c=widget.controls[name];c.kind.value=kind;c.kind.listeners.change[0]();c.duration.value=String(seconds);c.duration.listeners.input[0]();}
const original=structuredClone(selected().clip);
// The existing narrated fixture has an incoming fade. Review and change the
// next clip first; conflicting pairs must remain rejected atomically.
if(parity){const track=timeline().snapshot.tracks.find(t=>t.type==='video'),next=track.clips.find(c=>c.clip_id!==original.clip_id&&Math.abs(c.timeline_start-original.timeline_start-original.duration)<.001);assert.ok(next);
  selection=next.clip_id;widget.sync();for(const[name,value]of Object.entries({brightness:70,contrast:75,hue_rotate:-60,saturation:150,grayscale:25,blur:1}))inputField(name,value);
  transition('transition_in','cut',0);transition('transition_out','slide',.2);await widget.apply();assert.equal(dirty,false,JSON.stringify(messages));
  selection=original.clip_id;widget.sync();}
if(parity){for(const[name,value]of Object.entries({brightness:65,contrast:145,hue_rotate:50,saturation:80,grayscale:25,blur:2}))inputField(name,value);
  transition('transition_in','cut',0);transition('transition_out','crossfade',.2);
}else{inputField('brightness',80);inputField('saturation',35);transition('transition_in','slide',.2);transition('transition_out','fade',.2);}
await widget.apply();assert.equal(dirty,false,JSON.stringify(messages));const visual=structuredClone(page),changed=selected().clip;
assert.deepEqual(changed.effects,parity?[{type:'brightness',value:.65},{type:'contrast',value:1.45},{type:'saturation',value:.8},{type:'hue_rotate',value:50},{type:'grayscale',value:.25},{type:'blur',value:.02}]:[{type:'brightness',value:.8},{type:'saturation',value:.35}]);assert.deepEqual(changed.metadata.reframe,original.metadata.reframe);
for(const k of['asset_id','source_start','source_end','timeline_start','duration','speed','crop','transform','opacity'])assert.deepEqual(changed[k],original[k],k);
assert.deepEqual(timeline().snapshot.tracks.filter(t=>t.type!=='video'),stylingSnapshot.tracks.filter(t=>t.type!=='video'));
const audio=timeline().snapshot.tracks.find(t=>t.type==='audio'&&t.kind==='music'&&t.clips.some(c=>!c.metadata.narrated_generated_voice));assert.ok(audio);
selection=audio.clips[0].clip_id;widget.sync();transition('transition_out','fade',.4);await widget.apply();assert.equal(dirty,false,JSON.stringify(messages));const final=structuredClone(page),finalSha=timeline().sha256;
const firstSha=narrated?before.timeline_sha256:before.document.canonical_timeline.sha256;
page=await api(narrated?{...bind(),restore_revision:before.revision,restore_timeline_sha256:firstSha}:sourceRequest(page,'restore',{restore_revision:before.revision}));const undo=structuredClone(page);assert.equal(timeline().sha256,firstSha);
page=await api(narrated?{...bind(),restore_revision:final.revision,restore_timeline_sha256:finalSha}:sourceRequest(page,'restore',{restore_revision:final.revision}));const redo=structuredClone(page);assert.equal(timeline().sha256,finalSha);
page=await api();assert.equal(timeline().sha256,finalSha);
process.stdout.write(JSON.stringify({schema_version:'native-clip-style-signed-controller-proof-v1',mode:narrated?'narrated':'source',before,visual,final,undo,redo,reopened:page,requests,messages,
  actual_shared_style_widget:true,actual_signed_HTTP:true,canonical_source_windows_unchanged:true,style_only_preserves_source_windows:true,other_tracks_preserved_by_visual_edit:true,undo_redo_exact_snapshot:true,
  parity_scenario:parity,source_split_performed:parity&&!narrated,six_effects_and_crossfade_authored:parity,
  fixture_human:true,fake_DOM:true,whole_parent_editor_DOM_exercised:false,browser_rendered:false,owner_UAT:false,provider_calls:0,paid_calls:0,publishing_enabled:false})+'\n');
