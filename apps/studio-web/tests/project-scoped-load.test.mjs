import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {timelineTranscriptId} from '../timeline-history.mjs';

const code=readFileSync(new URL('../studio.js',import.meta.url),'utf8');
const first=code.indexOf('async function loadProject('),last=code.indexOf('\nfunction renderNoProject(',first);
assert.ok(first>=0&&last>first);
const captured=JSON.parse(readFileSync(new URL('./fixtures/source-linked-edit/asgi.json',import.meta.url),'utf8'));
const clone=structuredClone;
const late=['versions','vision','subtitles','scenes','transcript','highlights','preview','package','workbench'];
function harness({gate=null,reject=false,missing=[],noTimeline=false,wrongTranscript=false}={}){
  const timeline=clone(captured.responses.timeline_before.body);
  timeline.latest_preview_id='preview-scoped-read-fixture';
  const id=timelineTranscriptId(timeline);assert.ok(id);
  const savedAnalysis={analysis_id:timeline.source_analysis_id,transcript:{transcript_id:id}};
  const headAnalysis={...clone(savedAnalysis),transcript:{transcript_id:'newer-unsaved-revision'}};
  const state={workspaceId:timeline.workspace_id,projectId:timeline.project_id,projectLoading:0,
    principal:{subject:'usr:read-fixture',expires_at:'2100-01-01T00:00:00Z'},timeline:null,assets:[],analyses:[],
    mediaPlans:[],versions:[],transcriptDrafts:new Map(),playhead:99,selectedClipId:'old-selection',redoStack:['redo'],undoStack:['undo'],
    preview:{preview_id:'kept-preview'},productionPackage:{package_id:'kept-package'}};
  const permit=Symbol('initial-read');let token='fixture-token',audioDraft='saved-audio',productionDraft='saved-production';
  let baseline='kept-baseline',release,reached;
  const arrived=new Promise(resolve=>{reached=resolve;}),effects=[],calls=[];
  const peer={sync(){},isWorking:()=>false,isPending:()=>true,isDirty:()=>true,reload:async()=>effects.push('peer-read')};
  function response(path){
    if(path.endsWith('/assets'))return[{asset_id:'asset-scoped-read-fixture'}];
    if(path.endsWith('/analyses'))return[clone(headAnalysis)];
    if(path.includes('?transcript_id='))return wrongTranscript?headAnalysis:savedAnalysis;
    if(path.endsWith('/timeline'))return noTimeline?null:timeline;
    if(path.endsWith('/timeline/versions'))return captured.responses.history_before.body;
    if(path.endsWith('/analytics'))return{latest_sync:{status:'queued'}};
    if(path.endsWith('/subtitle-templates'))return{templates:[]};
    if(path.includes('/previews/'))return{preview_id:timeline.latest_preview_id,status:'queued'};
    if(path.endsWith('/production-package'))return{latest_review_render:{status:'running'}};
    return[];
  }
  function kind(path){
    if(path.endsWith('/timeline/versions'))return'versions';
    if(path.endsWith('/vision-analyses'))return'vision';
    if(path.endsWith('/subtitle-templates'))return'subtitles';
    if(path.endsWith('/scene-intelligence'))return'scenes';
    if(path.includes('?transcript_id='))return'transcript';
    if(path.endsWith('/highlight-drafts'))return'highlights';
    if(path.includes('/previews/'))return'preview';
    if(path.endsWith('/production-package'))return'package';
    if(path==='/fixture/workbench-stage')return'workbench';
    if(path.endsWith('/assets'))return'initial';
    return'other';
  }
  const api=async(path,options={})=>{
    assert.equal(options.method??'GET','GET');calls.push(path);const key=kind(path);
    if(key===gate){reached();await new Promise(resolve=>{release=resolve;});
      if(reject)throw Object.assign(Error('optional read failed'),{status:404});}
    if(missing.includes(key))throw Object.assign(Error('not configured'),{status:404});
    return clone(response(path));
  };
  const multiInput={setBusy(){},async prepareReload({isCurrent}){
    assert.equal(isCurrent(),true);await api('/fixture/workbench-stage');
    if(!isCurrent())throw Error('stale workbench');
    return()=>{assert.equal(isCurrent(),true);assert.equal(state.timeline?.project_id,noTimeline?undefined:timeline.project_id);
      effects.push('hydrate');audioDraft='hydrated-content';};
  }};
  const functions=['state','initialProjectRead','sourceLinkedHeld','audioProcessingHeld','videoWordsHeld','sourceLinkedEditor',
    'sqlAudioProcessing','videoWordReview','variantNarration','audioReview','stockReview','toast','sessionToken','productionWorkbenchDraft',
    'audioWorkbenchDraft','$','videoReview','multiInput','variantFamilies','stopPreviewPolling','stopProductionPolling','stopAnalyticsPolling',
    'setSaveStatus','api','timelineTranscriptId','render','startPreviewPolling','startProductionPolling','startAnalyticsPolling'];
  const made=new Function(...functions,'let multiInputBaseline="kept-baseline";\n'+code.slice(first,last)+
    '\nreturn {run:loadProject,baseline:()=>multiInputBaseline};')(
      state,permit,()=>true,()=>true,()=>true,peer,peer,peer,peer,peer,peer,(...args)=>effects.push(['toast',...args]),
      ()=>token,()=>productionDraft,()=>audioDraft,()=>({disabled:false}),peer,multiInput,peer,
      ()=>effects.push('stop-preview'),()=>effects.push('stop-production'),()=>effects.push('stop-analytics'),
      (...args)=>effects.push(['status',...args]),api,timelineTranscriptId,()=>effects.push('render'),
      ()=>effects.push('start-preview'),()=>effects.push('start-production'),()=>effects.push('start-analytics'));
  function drift(key){
    if(key==='token')token='different-token';
    if(key==='principal')state.principal.subject='usr:changed';
    if(key==='project')state.projectId='prj-new-context';
    if(key==='draft')state.transcriptDrafts.set('ana-unsaved','keep these words');
    if(key==='audio-draft')audioDraft='unsaved-audio';
    if(key==='production-draft')productionDraft='unsaved-subtitle';
    if(key==='expiry')state.principal.expires_at='2000-01-01T00:00:00Z';
    if(key==='timeline')state.timeline={timeline_id:'tml-other',snapshot:{}};
    if(key==='analysis')state.analyses=[{analysis_id:'ana-other'}];
    if(key==='asset')state.assets=[{asset_id:'ast-other'}];
    if(key==='history')state.versions=[{version:99}];
  }
  return{state,effects,calls,permit,arrived,release:()=>release(),drift,run:made.run,baseline:made.baseline,timeline,id};
}
function noAdoption(h,expected){
  assert.deepEqual(h.state,{...expected,projectLoading:0});assert.equal(h.baseline(),'kept-baseline');
  for(const item of ['hydrate','render','start-preview','start-production','start-analytics','peer-read'])
    assert.equal(h.effects.includes(item),false,item);
  assert.equal(h.effects.some(item=>Array.isArray(item)&&item[0]==='toast'),false);
}
for(const gate of ['initial',...late])for(const drift of ['token','principal','project','draft'])
  test(`cold read discards all staged data when ${drift} changes at ${gate}`,async()=>{
    const h=harness({gate}),work=h.run({initialRead:h.permit});await h.arrived;
    // No partial history/assets/review installation, even before the context changes.
    assert.equal(h.state.timeline,null);assert.deepEqual(h.state.assets,[]);assert.deepEqual(h.state.versions,[]);
    h.drift(drift);const expected=clone(h.state);h.release();await work;noAdoption(h,expected);
  });
for(const drift of ['audio-draft','production-draft','expiry','timeline','analysis','asset','history'])
  test(`late canonical load preserves newer ${drift}`,async()=>{
    const h=harness({gate:'package'}),work=h.run({initialRead:h.permit});await h.arrived;
    h.drift(drift);const expected=clone(h.state);h.release();await work;noAdoption(h,expected);
  });
test('optional preview catch cannot swallow context invalidation',async()=>{
  const h=harness({gate:'preview',reject:true}),work=h.run({initialRead:h.permit});await h.arrived;
  h.drift('token');const expected=clone(h.state);h.release();await work;noAdoption(h,expected);
});
test('valid held cold read stages the saved transcript and hydrates once without mutation or automatic reconcile',async()=>{
  const h=harness();await h.run({initialRead:h.permit});
  assert.deepEqual(h.state.timeline,h.timeline);assert.equal(h.state.analyses[0].transcript.transcript_id,h.id);
  assert.equal(h.state.playhead,h.timeline.snapshot.duration_seconds);assert.equal(h.state.selectedClipId,null);
  assert.deepEqual(h.state.redoStack,[]);assert.equal(h.baseline(),'hydrated-content');
  assert.equal(h.effects.filter(x=>x==='hydrate').length,1);assert.equal(h.effects.filter(x=>x==='render').length,1);
  assert.equal(h.effects.filter(x=>x==='peer-read').length,2);
  assert.equal(h.calls.some(path=>/source-linked-edit|audio-processing|\/words/.test(path)),false);
  assert.equal(h.state.projectLoading,0);
});
test('unconfigured optional panels and absent preview retain explicit fallback states',async()=>{
  const h=harness({missing:['vision','subtitles','scenes','highlights','preview','package']});await h.run({initialRead:h.permit});
  assert.equal(h.state.sceneIntelligenceSupported,false);assert.equal(h.state.highlightSupported,false);
  assert.deepEqual(h.state.sceneAssessments,[]);assert.deepEqual(h.state.highlightDrafts,[]);
  assert.equal(h.state.preview,null);assert.equal(h.state.productionPackage,null);assert.equal(h.state.subtitleCatalog,null);
  assert.equal(h.effects.filter(x=>x==='render').length,1);
});
test('no-timeline project still hydrates independent content without version or render reads',async()=>{
  const h=harness({noTimeline:true});await h.run({initialRead:h.permit});
  assert.equal(h.state.timeline,null);assert.deepEqual(h.state.versions,[]);assert.equal(h.state.preview,null);
  assert.equal(h.calls.some(path=>/\/versions|\/previews\/|\/production-package|\?transcript_id=/.test(path)),false);
  assert.equal(h.effects.filter(x=>x==='hydrate').length,1);
});
test('mismatched saved transcript aborts without partially installing canonical data',async()=>{
  const h=harness({wrongTranscript:true}),before=clone(h.state);await h.run({initialRead:h.permit});
  assert.deepEqual(h.state,before);assert.equal(h.baseline(),'kept-baseline');
  assert.equal(h.effects.includes('render'),false);assert.equal(h.effects.includes('peer-read'),false);
  assert.equal(h.effects.filter(item=>Array.isArray(item)&&item[0]==='toast').length,1);
});
