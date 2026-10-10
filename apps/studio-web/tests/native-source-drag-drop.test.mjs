import test from 'node:test';import assert from 'node:assert/strict';
import {initializeSourceDragDrop}from'../native-source-drag-drop.mjs';import{sourceAdvancedMarkup,sourceClipAction}from'../native-source-editor.mjs';import{pixelsPerSecond}from'../studio-utils.mjs';
function harness(){
  const clip={clip_id:'clip_fixture',timeline_start:0,duration:1.5,metadata:{}},track={track_id:'trk_source',kind:'source',type:'video',locked:false,clips:[clip]},
    timeline={version:2,sha256:'a'.repeat(64),snapshot:{duration_seconds:3,metadata:{native_auto_edit_schema:'native-auto-edit-timeline-v1'},tracks:[track]}},
    s={workspace_id:'wsp_fixture',project:{id:'a'.repeat(32),revision:4,document:{canonical_timeline:timeline}},timeline,canEdit:true,busy:false,active:false,dirty:false,zoom:2,snapping:true};
  const listeners={},el={dataset:{sourceClip:clip.clip_id},closest:()=>el,getBoundingClientRect:()=>({left:80})},lane={dataset:{sourceLane:track.track_id},closest:()=>lane,getBoundingClientRect:()=>({left:-10})},
    root={querySelectorAll:()=>[el],addEventListener:(k,f)=>{listeners[k]=f;}},calls=[],messages=[];
  let respond=async(at,binding)=>{calls.push({at,binding,body:sourceClipAction(s.project,binding.clip_id,'move',{timeline_start:at})});s.project.revision++;s.timeline.version++;s.timeline.sha256='b'.repeat(64);return true;};
  const controller=initializeSourceDragDrop({root,getState:()=>s,onMove:(...v)=>respond(...v),onMessage:(...v)=>messages.push(v)});
  const start=()=>listeners.dragstart({target:el,clientX:87,preventDefault(){},dataTransfer:{setData(){},getData(){throw Error('Foreign payload read');}}});
  const drop=(at=1.6,target=lane)=>listeners.drop({target,clientX:-10+7+at*pixelsPerSecond(s.zoom),preventDefault(){}});
  return{s,track,clip,el,lane,calls,messages,controller,listeners,start,drop,respond:fn=>{respond=fn;}};
}
test('source graph move binds the canonical revision/version/SHA and uses linked ripple routing with snapping',async()=>{
  const h=harness();assert.equal(h.el.draggable,true);h.start();await h.drop();assert.equal(h.calls.length,1);assert.equal(h.calls[0].at,1.5);
  assert.deepEqual(h.calls[0].binding,{workspace_id:'wsp_fixture',project_id:'a'.repeat(32),revision:4,timeline_version:2,timeline_sha256:'a'.repeat(64),clip_id:'clip_fixture',track_id:'trk_source'});
  assert.equal(h.calls[0].body.action,'linked_edit');assert.equal(h.calls[0].body.payload.operation.timeline_start,1.5);
});
test('source dragover accepts only the local captured lane and ignores transfer strings',()=>{
  const h=harness();let allowed=0;h.start();h.listeners.dragover({target:h.lane,preventDefault(){allowed++;}});
  const foreign={dataset:{sourceLane:'trk_foreign'},closest:()=>foreign};h.listeners.dragover({target:foreign,preventDefault(){allowed++;}});assert.equal(allowed,1);
});
test('viewer, dirty, locked, busy, active, archive and generated voice disable graph movement',async()=>{
  for(const flag of ['viewer','dirty','locked','busy','active','archive','generated']){const h=harness();
    if(flag==='viewer')h.s.canEdit=false;else if(flag==='locked')h.track.locked=true;else if(flag==='archive')h.s.project.archived=true;
    else if(flag==='generated')h.clip.metadata.narrated_generated_voice=true;else h.s[flag]=true;
    h.controller.sync();assert.equal(h.el.draggable,false,flag);h.start();await h.drop();assert.equal(h.calls.length,0,flag);
  }
});
test('stale project, workspace, revision, SHA, zoom and snapping cancel a pending graph drop',async()=>{
  for(const flag of ['project','workspace','revision','sha','zoom','snapping']){const h=harness();h.start();
    if(flag==='project')h.s.project.id='foreign';else if(flag==='workspace')h.s.workspace_id='foreign';else if(flag==='revision')h.s.project.revision++;
    else if(flag==='sha')h.s.timeline.sha256='c'.repeat(64);else if(flag==='zoom')h.s.zoom=3;else h.s.snapping=false;
    await h.drop();assert.equal(h.calls.length,0,flag);
  }
});
test('foreign lane, out-of-canvas marker and unmeasurable coordinates do not dispatch',async()=>{
  const h=harness(),foreign={dataset:{sourceLane:'trk_foreign'},closest:()=>foreign};h.start();await h.drop(1,foreign);assert.equal(h.calls.length,0);
  h.start();await h.drop(3.5);assert.equal(h.calls.length,0);h.start();await h.listeners.drop({target:h.lane,clientX:NaN,preventDefault(){}});assert.equal(h.calls.length,0);
});
test('independent audio uses exact placement and cannot extend beyond the visible canvas through drag',async()=>{
  const h=harness();h.track.type='audio';h.track.kind='music';h.start();await h.drop(1);assert.equal(h.calls[0].body.action,'edit');assert.equal(h.calls[0].at,1);
  h.start();await h.drop(2);assert.equal(h.calls.length,1);
});
test('cancel, no-op drop and failed or uncertain responses never repeat an old binding',async()=>{
  const h=harness();h.start();h.controller.cancel();await h.drop();assert.equal(h.calls.length,0);h.start();await h.drop(0);assert.equal(h.calls.length,0);
  let count=0;h.respond(async()=>{count++;throw Error('Owned uncertain HTTP response');});h.start();await h.drop();h.start();await h.drop();assert.equal(count,1);assert.equal(h.el.draggable,false);
});
test('pending movement is exclusive and a response cannot silently acknowledge unchanged storage',async()=>{
  const h=harness();let release,count=0;h.respond(()=>{count++;return new Promise(r=>{release=r;});});h.start();const pending=h.drop();assert.equal(h.controller.isWorking(),true);
  h.start();await h.drop();assert.equal(count,1);release(true);await pending;assert.equal(h.controller.isWorking(),false);assert.equal(h.el.draggable,false);assert.equal(h.messages.at(-1)[1],true);
});
test('source lane markup exposes scoped drop targets and starts inert until role guards synchronize',()=>{
  const h=harness();h.track.label='<img onerror=never>';h.clip.label='Owned clip';const html=sourceAdvancedMarkup(h.s.project);
  assert.match(html,/data-source-lane="trk_source"/);assert.match(html,/draggable="false"/);assert.ok(!html.includes('<img onerror'));
});
test('malformed project, versions, duration and mismatched parent canonical binding stay inert',async()=>{
  for(const flag of ['id','revision','version','duration','parent']){const h=harness();if(flag==='id')h.s.project.id='foreign';else if(flag==='revision')h.s.project.revision=true;
    else if(flag==='version')h.s.timeline.version=0;else if(flag==='duration')h.clip.duration=NaN;else h.s.timeline={...h.s.timeline,sha256:'b'.repeat(64)};
    h.controller.sync();h.start();await h.drop();assert.equal(h.calls.length,0,flag);assert.equal(h.el.draggable,false,flag);
  }
});
