import test from 'node:test';
import assert from 'node:assert/strict';
import {visualDraft,visualProperties,visualChanges,visualSchematic,initializeVisualProperties} from '../native-visual-properties.mjs';
const clone=v=>structuredClone(v);
const clip={clip_id:'clip_visual_fixture',asset_id:'asset_fixture',kind:'video',crop:{x:.1,y:.05,width:.8,height:.9},
  transform:{x:.05,y:-.02,scale:1.1,rotation_degrees:8},opacity:.9,metadata:{reframe:{fixture:true}}};
function harness(){
  class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.value='';}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,fn){(this.listeners[k]??=[]).push(fn);}}
  const root=new Node('section');root.id='fixture-visual';const dom={createElement:t=>new Node(t)},s={workspace_id:'wsp_fixture',project:{id:'project_fixture',revision:4},timeline:{version:3,sha256:'a'.repeat(64)},
    selected:{track:{track_id:'trk_visual_fixture',type:'video',locked:false},clip:clone(clip)},canEdit:true,busy:false,active:false,dirty:false,dirtyPart:null},calls=[],messages=[];
  let respond=async(values,binding)=>{calls.push({values:clone(values),binding});Object.assign(s.selected.clip,values);s.project.revision++;s.timeline.version++;s.timeline.sha256='b'.repeat(64);return true;};
  const widget=initializeVisualProperties({root,dom,getState:()=>s,onSave:(...args)=>respond(...args),onDirty:v=>{s.dirty=v;s.dirtyPart=v?'visual':null;},onMessage:(...args)=>messages.push(args)});
  const input=(key,value)=>{widget.controls[key].value=String(value);widget.controls[key].listeners.input[0]();};
  return {root,s,calls,messages,widget,input,respond:fn=>{respond=fn;}};
}
test('visual percentages round trip canonical transforms and send only changed properties',()=>{
  const draft=visualDraft(clip);assert.deepEqual(visualProperties(draft),{crop:clip.crop,transform:clip.transform,opacity:clip.opacity});
  assert.deepEqual(visualChanges(clip,draft),{});draft.rotation_degrees=12;assert.deepEqual(visualChanges(clip,draft),{transform:{...clip.transform,rotation_degrees:12}});
  assert.ok(!('crop' in visualChanges(clip,draft)),'An unchanged crop must not destroy a tracked crop path');
});
test('closed numeric visual inputs reject blank, foreign, non-finite and out of bounds values',()=>{
  const draft=visualDraft(clip);
  for(const [key,value] of [['x',201],['y',-201],['scale',0],['scale',801],['rotation_degrees',361],['opacity',101],['crop_width',0],['crop_x',40],['crop_height',100],['opacity',NaN],['x',Infinity],['x','12']]){
    assert.throws(()=>visualProperties({...draft,[key]:value}),undefined,key+':'+value);
  }
  assert.throws(()=>visualProperties({...draft,token:'never'}));assert.throws(()=>visualProperties(null));
});
test('schematic declares illustrative scope and cannot embed a foreign SVG identifier',()=>{
  const svg=visualSchematic(visualDraft(clip),'fixture-layout');assert.match(svg,/chưa phải khung hình render/);assert.match(svg,/id="fixture-layout"/);
  assert.throws(()=>visualSchematic(visualDraft(clip),'x" onload="alert(1)'));assert.throws(()=>visualSchematic({...visualDraft(clip),x:'<script>'}));
});
test('actual shared widget sends one canonical bound edit and clears its own draft after ack',async()=>{
  const h=harness();assert.equal(h.widget.apply.disabled,true);h.input('scale',125);assert.equal(h.widget.apply.disabled,false);
  await h.widget.save();assert.equal(h.calls.length,1);assert.deepEqual(h.calls[0].values,{transform:{...clip.transform,scale:1.25}});
  assert.deepEqual(h.calls[0].binding,{project_id:'project_fixture',revision:4,timeline_version:3,timeline_sha256:'a'.repeat(64),clip_id:clip.clip_id,workspace_id:'wsp_fixture'});
  assert.equal(h.widget.isDirty(),false);assert.equal(h.s.dirty,false);assert.equal(h.widget.controls.scale.value,'125');assert.ok(h.s.selected.clip.metadata.reframe);
});
test('no-op save, reset and discard never mutate until the human saves a changed draft',async()=>{
  const h=harness();h.input('scale',110);await h.widget.save();assert.equal(h.calls.length,0);assert.equal(h.widget.isDirty(),false);
  h.widget.reset.listeners.click[0]();assert.equal(h.widget.controls.scale.value,'100');assert.equal(h.widget.isDirty(),true);assert.equal(h.calls.length,0);
  h.widget.discardDraft();assert.equal(h.widget.controls.scale.value,'110');assert.equal(h.widget.isDirty(),false);assert.equal(h.calls.length,0);
});
test('empty numeric field fails without coercing to zero or losing the human draft',async()=>{
  const h=harness();h.input('x','');await h.widget.save();assert.equal(h.calls.length,0);assert.equal(h.widget.isDirty(),true);assert.equal(h.messages.at(-1)[1],true);
});
test('viewer, locked, active, busy, archived, stale voice and another form fence both drafts and writes',async()=>{
  for(const flag of ['viewer','locked','active','busy','archived','voice','other']){
    const h=harness();if(flag==='viewer')h.s.canEdit=false;else if(flag==='locked')h.s.selected.track.locked=true;else if(flag==='archived')h.s.project.archived=true;
    else if(flag==='voice')h.s.voice_input_current=false;else if(flag==='other'){h.s.dirty=true;h.s.dirtyPart='trim';}else h.s[flag]=true;
    h.widget.sync();h.input('rotation_degrees',12);await h.widget.save();assert.equal(h.calls.length,0,flag);assert.equal(h.widget.controls.x.disabled,true,flag);
  }
});
test('stale project, workspace, revision, SHA and selection refuse an unsynchronized draft',async()=>{
  for(const flag of ['project','workspace','revision','sha','clip']){
    const h=harness();h.input('opacity',80);if(flag==='project')h.s.project.id='foreign';else if(flag==='workspace')h.s.workspace_id='foreign';
    else if(flag==='revision')h.s.project.revision++;else if(flag==='sha')h.s.timeline.sha256='c'.repeat(64);else h.s.selected.clip.clip_id='clip_foreign';
    await h.widget.save();assert.equal(h.calls.length,0,flag);h.widget.sync();assert.equal(h.widget.isDirty(),false,flag);
  }
});
test('audio selection cannot use visual controls or mutate generated voice',async()=>{
  const h=harness();h.s.selected.track.type='audio';h.widget.sync();assert.equal(h.root.hidden,true);h.input('scale',120);await h.widget.save();assert.equal(h.calls.length,0);
  h.s.selected.track.type='video';h.s.selected.clip.metadata.narrated_generated_voice=true;h.widget.sync();assert.equal(h.root.hidden,true);
});
test('an uncertain or false save is not repeated from the same saved binding, even after discard',async()=>{
  for(const response of ['throw','false','unchanged']){
    const h=harness();let count=0;h.respond(async()=>{count++;if(response==='throw')throw Error('Owned response loss');return response==='false'?false:true;});
    h.input('scale',120);await h.widget.save();await h.widget.save();h.widget.discardDraft();h.input('scale',125);await h.widget.save();assert.equal(count,1,response);assert.equal(h.widget.apply.disabled,true,response);
    assert.equal(h.messages.at(-1)[1],true);
  }
});
test('an in-flight save remains fenced and its old response cannot acknowledge a new project',async()=>{
  const h=harness();let release;h.respond(()=>new Promise(r=>{release=r;}));h.input('opacity',80);const pending=h.widget.save();assert.equal(h.widget.isWorking(),true);
  await h.widget.save();h.s.project={id:'foreign',revision:1};h.s.timeline={version:1,sha256:'c'.repeat(64)};h.widget.sync();release(false);await pending;
  assert.equal(h.s.project.id,'foreign');assert.equal(h.s.selected.clip.opacity,.9);assert.equal(h.widget.isWorking(),false);assert.equal(h.widget.isDirty(),false);
});
