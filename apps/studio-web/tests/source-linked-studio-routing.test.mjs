import {withIdleManualReframe} from './root-manual-reframe-idle-context.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {getClip} from '../studio-utils.mjs';

const code=readFileSync(new URL('../studio.js',import.meta.url),'utf8');
function segment(begin,end){const a=code.indexOf(begin),b=code.indexOf(end,a);assert.ok(a>=0&&b>a);return code.slice(a,b);}
function state(){return {projectId:'prj_routing',playhead:0,redoStack:[],selectedClipId:null,
  timeline:{timeline_id:'tml_routing',source_kind:'video_analysis',current_version:2,snapshot:{duration_seconds:8,tracks:[
    {track_id:'source',type:'video',kind:'source',clips:[{clip_id:'shot',kind:'source',source_start:0,source_end:4,timeline_start:0,duration:4,volume:1},
      {clip_id:'shot2',kind:'source',source_start:4,source_end:8,timeline_start:4,duration:4,volume:1}]},
    {track_id:'original',type:'audio',kind:'original_audio',clips:[{clip_id:'speech',kind:'audio',volume:.35}]},
    {track_id:'broll',type:'video',kind:'broll',clips:[{clip_id:'stock',kind:'video',volume:1}]}]}}};}
function normalize(s=state()){return withIdleManualReframe('state','getClip',segment('function sourceLinkedOperations(','\nsourceLinkedEditor=')+'\nreturn sourceLinkedOperations;')(s,getClip);}

test('source inspector keeps A/V linked without overwriting independent gain or caller inputs',()=>{
  const input=[{type:'trim',clip_id:'shot',source_start:.3,source_end:3,timeline_start:0},
    {type:'set_clip_properties',clip_id:'shot',speed:2,volume:1,opacity:.8,crop:{x:0,y:0,width:1,height:1}}];
  const before=structuredClone(input),s=state(),saved=structuredClone(s),out=normalize(s)(input);
  assert.deepEqual(out,[{type:'trim',clip_id:'shot',source_start:.3,source_end:3},
    {type:'set_clip_properties',clip_id:'shot',speed:2,opacity:.8,crop:{x:0,y:0,width:1,height:1}}]);
  assert.deepEqual(input,before);assert.deepEqual(s,saved);
});
test('changed inspector position becomes an explicit move within the same atomic linked batch',()=>{
  assert.deepEqual(normalize()([{type:'trim',clip_id:'shot',source_end:3,timeline_start:7},
    {type:'set_clip_properties',clip_id:'shot',speed:2}]),[
    {type:'trim',clip_id:'shot',source_end:3},{type:'move',clip_id:'shot',timeline_start:7},
    {type:'set_clip_properties',clip_id:'shot',speed:2}]);
});
test('same source lane drag strips only the proven matching destination',()=>{
  const op={type:'move',clip_id:'shot',target_track_id:'source',timeline_start:7};
  assert.deepEqual(normalize()([op]),[{type:'move',clip_id:'shot',timeline_start:7}]);
  assert.equal(op.target_track_id,'source');
  assert.throws(()=>normalize()([{...op,target_track_id:'broll'}]),/lớp hình gốc/);
});
test('source volume change is refused explicitly and independent speech gain stays available',()=>{
  assert.throws(()=>normalize()([{type:'set_clip_properties',clip_id:'shot',volume:.4}]),/lớp tiếng gốc/);
  assert.equal(normalize()([{type:'set_clip_properties',clip_id:'speech',volume:.4}]),null);
});
test('mixed source and independent-track mutations cannot partially dispatch',()=>{
  assert.throws(()=>normalize()([{type:'disable',clip_id:'shot',disabled:true},
    {type:'set_clip_properties',clip_id:'speech',volume:.4}]),/riêng với các lớp khác/);
});
test('independent stock, speech and track locks retain their existing command route',()=>{
  for(const op of [{type:'move',clip_id:'stock',target_track_id:'broll',timeline_start:2},
    {type:'trim',clip_id:'speech',source_start:.2},
    {type:'set_track_state',track_id:'source',locked:true}])assert.equal(normalize()([op]),null);
});
test('storyboard and mixed Mode A sources retain their accepted editing route',()=>{
  for(const kind of ['media_plan','storyboard','script']){
    const s=state();s.timeline.source_kind=kind;
    assert.equal(normalize(s)([{type:'trim',clip_id:'shot',source_end:3,timeline_start:0}]),null);
    assert.equal(normalize(s)([{type:'set_clip_properties',clip_id:'shot',volume:.4}]),null);
  }
});

function mutationHarness({saved=true,pending=false,missing=false}={}){
  const s=state(),calls=[],effects=[];
  const controller=missing?null:{runOperations:async(ops,options)=>{calls.push({kind:'linked',ops,options});return saved;},isPending:()=>pending};
  const run=withIdleManualReframe('state','sourceLinkedOperations','sourceLinkedEditor','setSaveStatus','toast','api','selectedClip','render','loadProject',
    segment('async function mutate(','\nasync function restoreVersion(')+'\nreturn mutate;')(
      s,normalize(s),controller,(...args)=>effects.push({status:args}),(message,error)=>effects.push({message,error}),
      async(path,options)=>{calls.push({kind:'generic',path,options});return path.endsWith('/versions')?[]:
        {...structuredClone(s.timeline),current_version:s.timeline.current_version+1};},()=>null,()=>effects.push({render:true}),()=>effects.push({reload:true}));
  return {s,calls,effects,run};
}
test('actual mutate uses one explicit linked gesture and never the generic source PUT',async()=>{
  const h=mutationHarness();await h.run([{type:'split',clip_id:'shot',at_seconds:2}],'split-at-playhead');
  assert.deepEqual(h.calls,[{kind:'linked',ops:[{type:'split',clip_id:'shot',at_seconds:2}],options:{acknowledged:true}}]);
  assert.deepEqual(h.effects.at(-1),{status:['Đã lưu','safe']});
});
test('UNKNOWN linked save cannot fall through, reload/rebase or report success',async()=>{
  const h=mutationHarness({saved:false,pending:true}),before=structuredClone(h.s);
  await h.run([{type:'disable',clip_id:'shot',disabled:true}],'toggle-clip');
  assert.equal(h.calls.length,1);assert.equal(h.calls[0].kind,'linked');assert.deepEqual(h.s,before);
  assert.deepEqual(h.effects.at(-1),{status:['Cần đối chiếu','warning']});
  assert.ok(!h.effects.some(e=>e.reload||e.render));
});
test('invalid source destination and missing linked controller both stop before dispatch',async()=>{
  const h=mutationHarness();await h.run([{type:'move',clip_id:'shot',target_track_id:'broll',timeline_start:2}],'drag');
  assert.equal(h.calls.length,0);assert.ok(h.effects.at(-1).error);
  const absent=mutationHarness({missing:true});await absent.run([{type:'delete',clip_id:'shot'}],'delete');
  assert.equal(absent.calls.length,0);assert.ok(absent.effects.at(-1).error);
});
test('actual independent speech mutation retains the generic route and old invalidation',async()=>{
  const h=mutationHarness();h.s.productionPackage={current_for_timeline:true,approval:{status:'approved'}};
  await h.run([{type:'set_clip_properties',clip_id:'speech',volume:.4}],'audio-edit');
  assert.equal(h.calls[0].kind,'generic');assert.equal(h.calls[0].options.method,'PUT');
  assert.equal(JSON.parse(h.calls[0].options.body).operations[0].volume,.4);
  assert.equal(h.s.productionPackage.current_for_timeline,false);assert.equal(h.s.productionPackage.approval,null);
});

test('private linked admission cannot bypass held audio/words and never reaches fetch',async()=>{
  let linked=true,audio=false,words=false;const calls=[],l=Symbol('linked'),a=Symbol('audio'),w=Symbol('words');
  const api=withIdleManualReframe('authenticatedFetch','sourceLinkedHeld','sourceLinkedAdmission','audioProcessingHeld','audioProcessingAdmission','videoWordsHeld','videoWordAdmission',
    segment('class ApiError extends Error {','\nfunction toast(')+'\nreturn api;')(
      async(path,options)=>{calls.push({path,options});return{ok:true,status:204};},()=>linked,l,()=>audio,a,()=>words,w);
  for(const method of ['PUT','POST','DELETE','PATCH'])await assert.rejects(api('/api/v1/projects/current/timeline',{method}),/chỉnh shot/);
  await api('/api/v1/projects/current/timeline');
  await api('/api/v1/projects/current/timeline/source-linked-edit',{method:'PUT',sourceLinkedAdmission:l});
  assert.equal(Object.hasOwn(calls.at(-1).options,'sourceLinkedAdmission'),false);
  await assert.rejects(api('/api/v1/projects/current/timeline',{method:'PUT',sourceLinkedAdmission:Symbol('foreign')}),/chỉnh shot/);
  audio=true;await assert.rejects(api('/api/v1/projects/current/timeline/source-linked-edit',{method:'PUT',sourceLinkedAdmission:l}),/cấu hình âm thanh/);
  audio=false;words=true;await assert.rejects(api('/api/v1/projects/current/timeline/source-linked-edit',{method:'PUT',sourceLinkedAdmission:l}),/sửa từ/);
});
test('audio admission tracks only its own work and does not self-block a linked request',()=>{
  const own=withIdleManualReframe('sqlAudioProcessing','sourceLinkedEditor',segment('function audioProcessingHeld(){','\nconst videoWordAdmission')+'\nreturn audioProcessingHeld;')(
    null,{isWorking:()=>true,isDirty:()=>true,isPending:()=>true});
  assert.equal(own(),false);
});

function initialReadHarness(s,active={}){
  const permit=Symbol('private-initial-read'),messages=[],intent='unchanged-frozen-intent';
  const preflight=segment('async function loadProject(','\n  const loadedProjectId = state.projectId;');
  const run=withIdleManualReframe('state','initialProjectRead','sourceLinkedHeld','audioProcessingHeld','videoWordsHeld',
    'sourceLinkedEditor','sqlAudioProcessing','videoWordReview','variantNarration','audioReview','stockReview','toast',
    preflight+'\nreturn "READ_ONLY_ADMITTED";}\nreturn loadProject;')(
      s,permit,()=>true,()=>true,()=>true,{isWorking:()=>active.source===true},
      {isWorking:()=>active.audio===true},{isWorking:()=>active.words===true},
      {isWorking:()=>active.narration===true,isPending:()=>true},{isDirty:()=>true},{isPending:()=>true},
      message=>messages.push(message));
  return {run,permit,messages,intent};
}
function pristine(){return {projectId:'prj_cold',timeline:null,projectLoading:0,assets:[],analyses:[],versions:[],transcriptDrafts:new Map()};}
test('cold reload can read canonical context while every durable UNKNOWN remains held',async()=>{
  const s=pristine(),before=structuredClone(s),h=initialReadHarness(s);
  assert.equal(await h.run({initialRead:h.permit}),'READ_ONLY_ADMITTED');
  assert.deepEqual(s,before);assert.equal(h.intent,'unchanged-frozen-intent');assert.deepEqual(h.messages,[]);
  assert.match(segment('async function loadProjectList(','\nasync function loadProject('),/loadProject\(\{initialRead:initialProjectRead\}\)/);
});
test('ordinary and foreign initial-read flags cannot rebase a held project even when unloaded',async()=>{
  const h=initialReadHarness(pristine());
  assert.equal(await h.run(),undefined);assert.equal(await h.run({initialRead:true}),undefined);
  assert.equal(await h.run({initialRead:Symbol('foreign')}),undefined);assert.equal(h.messages.length,3);
});
for(const existing of ['timeline','asset','analysis','history','draft','loading'])test(`private initial read cannot replace existing ${existing} context`,async()=>{
  const s=pristine();
  if(existing==='timeline')s.timeline=state().timeline;if(existing==='asset')s.assets.push({asset_id:'saved-source'});
  if(existing==='analysis')s.analyses.push({analysis_id:'saved-analysis'});if(existing==='history')s.versions.push({version:1});
  if(existing==='draft')s.transcriptDrafts.set('saved-analysis','unsaved words');if(existing==='loading')s.projectLoading=1;
  const h=initialReadHarness(s),before=structuredClone(s);
  assert.equal(await h.run({initialRead:h.permit}),undefined);assert.deepEqual(s,before);assert.equal(h.messages.length,1);
});
for(const working of ['source','audio','words','narration'])test(`private cold read cannot replace active ${working} work`,async()=>{
  const h=initialReadHarness(pristine(),{[working]:true});
  assert.equal(await h.run({initialRead:h.permit}),undefined);assert.equal(h.messages.length,1);
});
