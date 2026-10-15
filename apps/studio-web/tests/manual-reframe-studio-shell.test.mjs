import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash, webcrypto} from 'node:crypto';
import {audioRole} from '../uploaded-audio-review.mjs';
import {initializeSqlManualReframe, manualReframeRead, manualReframeSettings} from '../sql-manual-reframe.mjs';
import {timelineTranscriptId} from '../timeline-history.mjs';

const code=readFileSync(new URL('../studio.js',import.meta.url),'utf8');
const bytes=readFileSync(new URL('./fixtures/manual-reframe/asgi.json',import.meta.url));
const captured=JSON.parse(bytes),r=captured.responses;
const manifest=JSON.parse(readFileSync(new URL('./fixtures/manual-reframe/manifest.json',import.meta.url)));
const clone=structuredClone;
function segment(a,b){const start=code.indexOf(a),end=code.indexOf(b,start);assert.ok(start>=0&&end>start);return code.slice(start,end);}
function fixtureState(){const timeline=clone(r.manual_before.body.timeline),p=r.manual_before.body.source;
 const media={media_kind:'video',duration_seconds:p.duration_seconds,width:p.width,height:p.height,fps:p.fps,audio_codec:p.has_audio?'aac':null};
 const asset={asset_id:p.asset_id,workspace_id:timeline.workspace_id,project_id:timeline.project_id,asset_class:'source',kind:'video',content_type:'video/mp4',
  checksum_sha256:p.source_sha256,size_bytes:4096,object_key:p.object_key,provenance:{source_type:'user_upload',media_metadata:clone(media)}};
 const analysis={analysis_id:p.analysis_id,asset_id:p.asset_id,workspace_id:timeline.workspace_id,project_id:timeline.project_id,status:'succeeded',
  fingerprint:p.analysis_fingerprint,source_media:media,source_media_mutated:false,publish_requested:false,configuration:{asset_id:p.asset_id}};
 return{workspaceId:timeline.workspace_id,projectId:timeline.project_id,timeline,analysis,analyses:[analysis],assets:[asset],mediaPlans:[],busy:false,dirty:false,
  principal:{...clone(r.session.body),expires_at:'2100-01-01T00:00:00Z'},versions:[],undoStack:[1],redoStack:[1],playhead:99,selectedClipId:'old',
  preview:{status:'ready',valid_for_current_timeline:true},productionPackage:{current_for_timeline:true,approval:{status:'approved'},latest_review_render:{},latest_final_render:{}},activeProductionRender:null,
  projectLoading:0,transcriptDrafts:new Map()};
}
class Element{
 constructor(tag='div'){this.tagName=tag;this.children=[];this.attributes={};this.dataset={};this.listeners={};this.value='';this.disabled=false;this.textContent='';this._html='';this.rows=[];}
 append(...items){this.children.push(...items);}setAttribute(k,v){this.attributes[k]=String(v);if(k.startsWith('data-'))this.dataset[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=String(v);}
 addEventListener(k,f){(this.listeners[k]??=[]).push(f);}
 async fire(k,target=this){for(const f of this.listeners[k]??[])await f({target,currentTarget:this,preventDefault(){}});}
 closest(selector){return selector.startsWith('[data-')&&Object.hasOwn(this.attributes,selector.slice(1,-1))?this:null;}
 querySelector(selector){const field=selector.match(/data-manual-reframe-field="([^"]+)"/)?.[1];return this.inputs?.find(input=>input.dataset.manualReframeField===field)??null;}
 get innerHTML(){return this._html;}
 set innerHTML(value){this._html=value;if(!this.isPointBody)return;
  this.rows=[...value.matchAll(/<tr>([\s\S]*?)<\/tr>/g)].map(match=>{const row=new Element('tr');row.inputs=[];
   for(const input of match[1].matchAll(/<input[^>]*data-manual-reframe-field="([^"]+)"[^>]*value="([^"]*)"[^>]*>/g)){
    const e=new Element('input');e.dataset.manualReframeField=input[1];e.value=input[2];row.inputs.push(e);}
   return row;});}
}
function harness({handler,memory=new Map(),s=fixtureState()}={}){
 const ids={};for(const id of ['manual-reframe-aspect','manual-reframe-points','manual-reframe-fields','manual-reframe-discard','manual-reframe-add',
  'manual-reframe-apply','manual-reframe-form-status','manual-reframe-form','sql-manual-reframe'])ids[id]=new Element(id==='manual-reframe-form'?'form':'div');
 ids['manual-reframe-aspect'].value='9:16';ids['manual-reframe-fields'].disabled=true;ids['manual-reframe-points'].isPointBody=true;
 const dom={createElement:tag=>new Element(tag),querySelectorAll:selector=>selector.endsWith(' tr')?ids['manual-reframe-points'].rows:
  selector.includes('[data-manual-reframe-field]')?ids['manual-reframe-points'].rows.flatMap(row=>row.inputs):[]};
 const calls=[],effects=[],messages=[];let token='EXPLICIT_ROOT_MANUAL_FIXTURE_TOKEN',clock=Date.now(),committed=false,readsAfterPut=0,outer;
 const peers={family:false,narration:false,words:false,audio:false,linked:false};
 const peer=name=>({isBusy:()=>peers[name],isWorking:()=>peers[name],isPending:()=>peers[name],isDirty:()=>peers[name],sync(){}});
 const noop={sync(){}};
 const api=async(path,options)=>{const c={path,method:options?.method??'GET',body:options?.body?JSON.parse(options.body):null};calls.push(c);
  let data,phase='before';if(c.method==='PUT'){data=clone(r.manual_put.body);phase='put';committed=true;}
  else if(path.endsWith('/versions')){data=clone(r.history_after.body);phase='history';}
  else{data=clone(committed?r.manual_put.body:r.manual_before.body);if(committed)phase=++readsAfterPut===1?'proof':'final';}
  return handler?handler(c,phase,data,{s,peers,setToken:v=>{token=v;},setClock:v=>{clock=v;},committed:()=>committed}):data;
 };
 const storage={getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v),compareAndRemoveItem:(k,v)=>{if(memory.get(k)!==v)return false;memory.delete(k);return true;}};
 const stable=new Function(segment('function sqlAudioStable(','\nfunction sqlAudioSourceValue(')+'\nreturn sqlAudioStable;')();
 const history=new Function(segment('function videoWordHistoryMatches(','\nasync function refreshVideoWordReceipt')+'\nreturn videoWordHistoryMatches;')();
 const args=['state','document','$','sqlEditorState','activeAnalysis','variantFamilies','variantNarration','videoWordReview','sqlAudioProcessing','sourceLinkedEditor','sourceLinkedHeld',
  'audioRole','sessionToken','productionWorkbenchDraft','audioWorkbenchDraft','api','sqlAudioStable','videoWordHistoryMatches','manualReframeRead','manualReframeSettings',
  'initializeSqlManualReframe','audioReview','stockReview','videoReview','stopPreviewPolling','stopProductionPolling','render','setSaveStatus','toast','Date'];
 const body=segment('let manualReframeEditor = null;','\nconst initialProjectRead')+'\n'+segment('function manualReframeEditorState(){','\nasync function loadProjectList()')+
  '\nreturn {controller:manualReframeEditor,manualReframeHeld,manualReframeDirty,manualReframeEditorState,manualReframeDraft,manualReframeBoundary,manualReframeContext,manualReframeApi,refreshManualReframe,readManualReframeForm,syncManualReframeForm,manualReframeSettingsFromForm,formRead:()=>manualReframeFormRead,applyBinding:v=>{manualReframeApplying=v;}};';
 outer=new Function(...args,body)(s,dom,selector=>ids[selector.slice(1)],()=>({...s}),()=>s.analysis,peer('family'),peer('narration'),peer('words'),peer('audio'),peer('linked'),()=>peers.linked,
  audioRole,()=>token,()=> 'saved-production',()=> 'saved-audio',api,stable,history,manualReframeRead,manualReframeSettings,
  options=>initializeSqlManualReframe({...options,dom,storage,cryptoImpl:webcrypto,newRequestKey:()=>r.manual_put.request.request_key}),noop,noop,noop,
  ()=>effects.push('stop-preview'),()=>effects.push('stop-production'),()=>{effects.push('render');outer?.syncManualReframeForm();},(...v)=>effects.push({status:v}),(...v)=>messages.push(v),{parse:Date.parse,now:()=>clock});
 const all=e=>[e,...e.children.flatMap(all)],control=name=>all(ids['sql-manual-reframe']).find(e=>Object.hasOwn(e.attributes,'data-manual-reframe-'+name));
 const type=async(index,field,value)=>{const input=ids['manual-reframe-points'].rows[index].querySelector(`[data-manual-reframe-field="${field}"]`);input.value=String(value);await ids['manual-reframe-form'].fire('input',input);};
 return{...outer,s,ids,calls,effects,messages,memory,peers,control,type,setToken:v=>{token=v;},setClock:v=>{clock=v;},
  read:()=>control('read').fire('click'),submit:()=>ids['manual-reframe-form'].fire('submit'),
  fill:async()=>{await type(0,'x',20);await ids['manual-reframe-add'].fire('click');await type(1,'time',8);await type(1,'x',80);await type(1,'zoom',1.1);}};
}

test('selected actual ASGI fixture remains pinned and explicitly separates Node mocks from provider/UAT',()=>{
 assert.equal(createHash('sha256').update(bytes).digest('hex'),manifest.artifact_sha256);assert.equal(bytes.length,manifest.artifact_bytes);
 assert.equal(captured.scope.actual_sqlite,true);assert.equal(captured.scope.actual_asgi,true);assert.equal(captured.scope.actual_decode,false);assert.equal(captured.scope.owner_uat,false);
 assert.equal(manifest.selected_records,4);assert.equal(manifest.manual_put_body_equals_current_body,true);
});
test('actual initializer and Root form remain unread/disabled at mount, then explicit read hydrates only current source',async()=>{
 const h=harness();assert.equal(h.calls.length,0);assert.equal(h.ids['manual-reframe-fields'].disabled,true);assert.equal(h.formRead(),null);
 await h.read();assert.deepEqual(h.calls.map(c=>c.method),['GET']);assert.equal(h.ids['manual-reframe-fields'].disabled,false);
 assert.match(h.ids['manual-reframe-form-status'].textContent,/Chưa có đường crop thủ công được lưu/);
 assert.deepEqual(h.manualReframeSettingsFromForm(),{aspect_ratio:'9:16',points:[{time:0,x:.5,y:.5,zoom:1}]});assert.equal(h.manualReframeDirty(),false);
});
test('actual form typing/add + actual controller + full Root callback verify three reads before exact canonical adoption',async()=>{
 const h=harness(),before=clone(h.s.timeline);await h.read();await h.fill();assert.equal(h.manualReframeDirty(),true);assert.equal(h.manualReframeHeld(),true);
 assert.equal(h.manualReframeEditorState().dirty,false);await h.submit();
 assert.deepEqual(h.calls.map(c=>c.method),['GET','GET','PUT','GET','GET','GET']);assert.deepEqual(h.calls[2].body,r.manual_put.request);
 assert.deepEqual(h.s.timeline,r.manual_put.body.timeline);assert.deepEqual(h.s.versions,r.history_after.body);assert.equal(h.s.preview.status,'stale');
 assert.equal(h.s.productionPackage.current_for_timeline,false);assert.equal(h.s.productionPackage.approval,null);assert.equal(h.s.activeProductionRender,null);
 assert.equal(h.s.selectedClipId,null);assert.deepEqual(h.s.undoStack,[]);assert.deepEqual(h.s.redoStack,[]);assert.equal(h.memory.size,0);
 assert.equal(h.manualReframeDirty(),false);assert.equal(h.manualReframeHeld(),false);assert.equal(h.s.playhead,16);
 for(const track of before.snapshot.tracks)if(track.kind!=='source')assert.deepEqual(h.s.timeline.snapshot.tracks.find(t=>t.track_id===track.track_id),track);
 assert.ok(h.effects.includes('stop-preview')&&h.effects.includes('stop-production')&&h.effects.includes('render'));
});
test('explicit reread rejects overwriting an unsaved form and discard restores the read baseline without PUT',async()=>{
 const h=harness();await h.read();await h.type(0,'x',20);const draft=h.manualReframeDraft();await h.read();
 assert.equal(h.manualReframeDraft(),draft);assert.equal(h.manualReframeDirty(),true);assert.equal(h.calls.filter(c=>c.method==='PUT').length,0);
 assert.match(h.messages.at(-1)[0],/bản sửa crop/);await h.ids['manual-reframe-discard'].fire('click');assert.equal(h.manualReframeDirty(),false);
 assert.equal(h.manualReframeSettingsFromForm().points[0].x,.5);assert.equal(h.calls.filter(c=>c.method==='PUT').length,0);
});
test('form retains valid four ratios, rejects empty/string/nonfinite/out-of-duration values before GET, and keeps one point',async()=>{
 const h=harness();await h.read();for(const ratio of ['9:16','16:9','1:1','4:5']){h.ids['manual-reframe-aspect'].value=ratio;assert.equal(h.manualReframeSettingsFromForm().aspect_ratio,ratio);}
 h.ids['manual-reframe-aspect'].value='9:16';const input=h.ids['manual-reframe-points'].rows[0].inputs[0];
 for(const value of ['','Infinity','NaN','true','0x10','17','-1']){input.value=value;await h.submit();assert.equal(h.calls.length,1);assert.equal(h.memory.size,0);}
 input.value='0';const remove=new Element('button');remove.setAttribute('data-manual-reframe-remove','0');await h.ids['manual-reframe-points'].fire('click',remove);
 assert.equal(h.ids['manual-reframe-points'].rows.length,1);assert.equal(h.calls.length,1);
});
test('last explicit read source binding is frozen before Apply, so a newer opaque binding cannot rebase the intent',async()=>{
 let reads=0;const h=harness({handler:(c,phase,data)=>{if(c.method==='GET'&&++reads===2)data.source_binding_sha256='f'.repeat(64);return data;}});
 await h.read();await h.fill();await h.submit();assert.equal(h.calls.length,2);assert.equal(h.calls.filter(c=>c.method==='PUT').length,0);assert.equal(h.memory.size,0);
 assert.equal(h.manualReframeDirty(),true);assert.deepEqual(h.s.timeline,r.manual_before.body.timeline);
});
test('peer words/audio/linked/family/narration state blocks manual writes despite scoped admission',async()=>{
 for(const name of ['words','audio','linked','family','narration']){const h=harness();await h.read();await h.fill();h.peers[name]=true;await h.submit();
  assert.equal(h.calls.length,1);assert.equal(h.memory.size,0);assert.equal(h.manualReframeDirty(),true);}
});
for(const phase of ['proof','history','final'])for(const change of ['project','token','actor','expiry','elapsed','role','write-off','timeline','analysis','asset','peer-draft','form-draft']){
 test(`${change} drift during ${phase} never installs a stale Root crop receipt`,async()=>{
  const h=harness({handler:(c,p,data,tools)=>{if(p===phase){
   if(change==='project')tools.s.projectId='prj_foreign';else if(change==='token')tools.setToken('DIFFERENT_ROOT_MANUAL_FIXTURE_TOKEN');
   else if(change==='actor')tools.s.principal.subject='usr:other';else if(change==='expiry')tools.s.principal.expires_at='2000-01-01T00:00:00Z';
   else if(change==='elapsed')tools.setClock(Date.parse(tools.s.principal.expires_at)+1);else if(change==='role')tools.s.principal.workspace_roles={[tools.s.workspaceId]:'viewer'};
   else if(change==='write-off')tools.s.principal.human_write_enabled=false;else if(change==='timeline')tools.s.timeline.current_version++;
   else if(change==='analysis')tools.s.analysis.fingerprint='e'.repeat(64);else if(change==='asset')tools.s.assets[0].filename='changed.mp4';
   else if(change==='peer-draft')tools.peers.audio=true;else h.ids['manual-reframe-points'].rows[0].inputs[1].value='42';
  }return data;}});
  await h.read();await h.fill();const before=clone(h.s.timeline);await h.submit();
  if(change!=='timeline')assert.deepEqual(h.s.timeline,before);else assert.equal(h.s.timeline.current_version,before.current_version+1);
  if(!['project','actor'].includes(change))assert.equal(h.controller.isPending(),true);
  assert.equal(h.memory.size,1);assert.equal(h.manualReframeHeld(),true);
  const held=JSON.parse([...h.memory.values()][0]);assert.equal(held.project_id,r.manual_before.body.timeline.project_id);assert.equal(held.actor_ref,r.session.body.subject);
  assert.equal(h.calls.filter(c=>c.method==='PUT').length,1);assert.ok(!h.effects.includes('render'));
 });
}
for(const contradiction of ['parent-id','parent-snapshot','actor','type','receipt','source-flag','publish-flag','applied-path']){
 test(`contradictory ${contradiction} history keeps UNKNOWN and original timeline`,async()=>{
  const h=harness({handler:(c,p,data)=>{if(p==='history'){const parent=data.find(v=>v.version===1),head=data.find(v=>v.version===2);
   if(contradiction==='parent-id')parent.timeline_version_id='tlv_foreign';else if(contradiction==='parent-snapshot')parent.snapshot.width++;
   else if(contradiction==='actor')head.actor_ref='usr:other';else if(contradiction==='type')head.mutation.type='other';
   else if(contradiction==='receipt')head.mutation.receipt.request_key='foreign-key';else if(contradiction==='source-flag')head.mutation.source_media_mutated=true;
   else if(contradiction==='publish-flag')head.mutation.publish_requested=true;else head.mutation.receipt.applied_keyframes[0].x+=.01;
  }return data;}});await h.read();await h.fill();const before=clone(h.s.timeline);await h.submit();
  assert.deepEqual(h.s.timeline,before);assert.equal(h.controller.isPending(),true);assert.equal(h.memory.size,1);assert.ok(!h.effects.includes('render'));
 });
}
test('manual private admission only bypasses its own hold, is stripped, and cannot bypass peers',async()=>{
 let held=true,linked=false,audio=false,words=false;const calls=[],m=Symbol('manual'),l=Symbol('linked'),a=Symbol('audio'),w=Symbol('words');
 const api=new Function('authenticatedFetch','manualReframeHeld','manualReframeAdmission','sourceLinkedHeld','sourceLinkedAdmission','audioProcessingHeld','audioProcessingAdmission','videoWordsHeld','videoWordAdmission',
  segment('class ApiError extends Error {','\nfunction toast(')+'\nreturn api;')(
   async(path,options)=>{calls.push({path,options});return{ok:true,status:204};},()=>held,m,()=>linked,l,()=>audio,a,()=>words,w);
 for(const method of ['PUT','POST','DELETE','PATCH'])await assert.rejects(api('/api/v1/projects/current/timeline',{method}),/đường crop/);
 await api('/api/v1/projects/current/timeline');await api('/api/v1/projects/current/timeline/manual-reframe',{method:'PUT',manualReframeAdmission:m});
 assert.equal(Object.hasOwn(calls.at(-1).options,'manualReframeAdmission'),false);
 linked=true;await assert.rejects(api('/api/v1/projects/current/timeline/manual-reframe',{method:'PUT',manualReframeAdmission:m}),/chỉnh shot/);linked=false;
 audio=true;await assert.rejects(api('/api/v1/projects/current/timeline/manual-reframe',{method:'PUT',manualReframeAdmission:m}),/âm thanh/);audio=false;
 words=true;await assert.rejects(api('/api/v1/projects/current/timeline/manual-reframe',{method:'PUT',manualReframeAdmission:m}),/sửa từ/);words=false;
 held=false;await api('/api/v1/projects/current/timeline',{method:'PUT'});assert.equal(calls.length,3);
});

// The complete shipped loadProject and project selector run against the actual
// manual initializer/form above. Transport/DOM/timers here are Node mocks.
function rootLoad(h,{gate=null}={}){
 const permit=Symbol('initial-read'),effects=[],calls=[],target={timeline:clone(r.manual_before.body.timeline),assets:clone(h.s.assets),analyses:clone(h.s.analyses)};
 for(const analysis of target.analyses)analysis.transcript={transcript_id:timelineTranscriptId(target.timeline)};
 let reached,release;const arrived=new Promise(resolve=>{reached=resolve;});
 h.ids['project-select']=new Element('select');h.ids['project-select'].value=h.s.projectId;
 const peer={sync(){},isBusy:()=>false,isWorking:()=>false,isPending:()=>false,isDirty:()=>false,reload:async()=>effects.push('peer-read')};
 const api=async(path,options={})=>{assert.equal(options.method??'GET','GET');calls.push(path);
  if(gate&&path.endsWith(gate)){reached();await new Promise(resolve=>{release=resolve;});}
  if(path.endsWith('/assets'))return clone(target.assets);if(path.endsWith('/analyses'))return clone(target.analyses);
  if(path.endsWith('/timeline'))return clone(target.timeline);if(path.endsWith('/timeline/versions'))return clone(r.history_after.body.filter(v=>v.version===1));
  if(path.endsWith('/analytics'))return {latest_sync:null};if(path.endsWith('/production-package'))return null;
  return [];
 };
 const multiInput={setBusy(){},async prepareReload({isCurrent}){assert.equal(isCurrent(),true);return()=>{assert.equal(isCurrent(),true);effects.push('hydrate');};}};
 const args=['state','initialProjectRead','manualReframeEditor','manualReframeHeld','manualReframeDirty','manualReframeApplying','manualReframeDraft','syncManualReframeForm',
  'sourceLinkedHeld','audioProcessingHeld','videoWordsHeld','sourceLinkedEditor','sqlAudioProcessing','videoWordReview','variantNarration','audioReview','stockReview','toast',
  'sessionToken','productionWorkbenchDraft','audioWorkbenchDraft','$','videoReview','multiInput','variantFamilies','stopPreviewPolling','stopProductionPolling','stopAnalyticsPolling',
  'setSaveStatus','api','timelineTranscriptId','render','startPreviewPolling','startProductionPolling','startAnalyticsPolling','window'];
 const made=new Function(...args,'let multiInputBaseline="before-load";\n'+segment('async function loadProject(','\nfunction renderNoProject(')+'\n'+
  segment('$("#project-select").addEventListener("change",','\n$("#reload-button")')+'\nreturn {run:loadProject,baseline:()=>multiInputBaseline};')(
  h.s,permit,h.controller,h.manualReframeHeld,h.manualReframeDirty,null,h.manualReframeDraft,h.syncManualReframeForm,
  ()=>false,()=>false,()=>false,peer,peer,peer,peer,peer,peer,(...v)=>h.messages.push(v),()=> 'EXPLICIT_ROOT_MANUAL_FIXTURE_TOKEN',
  ()=> 'saved-production',()=> 'saved-audio',selector=>h.ids[selector.slice(1)],peer,multiInput,peer,
  ()=>{},()=>{},()=>{},()=>{},api,timelineTranscriptId,()=>{effects.push('render');h.syncManualReframeForm();},()=>{},()=>{},()=>{},
  {localStorage:{setItem:(...v)=>effects.push(['storage',...v])}});
 return {...made,permit,effects,calls,target,arrived,release:()=>release(),switchTo:async id=>{h.ids['project-select'].value=id;await h.ids['project-select'].fire('change');}};
}
test('a clean manual form permits a complete project switch without self-invalidating the staged draft boundary',async()=>{
 const h=harness();await h.read();const load=rootLoad(h),other='prj_other_clean';load.target.timeline.project_id=other;
 for(const asset of load.target.assets)asset.project_id=other;for(const analysis of load.target.analyses)analysis.project_id=other;
 await load.switchTo(other);assert.equal(h.s.projectId,other);assert.deepEqual(h.s.timeline,load.target.timeline);
 assert.equal(load.effects.filter(v=>v==='hydrate').length,1);assert.equal(load.effects.filter(v=>v==='render').length,1);
 assert.equal(h.formRead(),null);assert.equal(h.ids['manual-reframe-fields'].disabled,true);assert.equal(h.manualReframeHeld(),false);
 assert.equal(h.calls.length,1);assert.equal(h.memory.size,0);assert.equal(h.s.projectLoading,0);
});
test('dirty manual form blocks project selector and ordinary reload before any canonical GET',async()=>{
 const h=harness();await h.read();await h.fill();const load=rootLoad(h),before=clone(h.s.timeline),draft=h.manualReframeDraft();
 await load.switchTo('prj_other_dirty');await load.run();assert.equal(h.s.projectId,before.project_id);assert.deepEqual(h.s.timeline,before);
 assert.equal(h.ids['project-select'].value,before.project_id);assert.equal(h.manualReframeDraft(),draft);assert.equal(load.calls.length,0);assert.equal(h.memory.size,0);
});
test('durable manual UNKNOWN allows only a pristine private cold canonical read and performs no automatic manual GET/PUT',async()=>{
 const s=fixtureState();s.timeline=null;s.assets=[];s.analyses=[];s.versions=[];s.preview=null;s.productionPackage=null;
 const memory=new Map(),key='vf-sql-manual-reframe-pending-v1:'+JSON.stringify([s.workspaceId,s.projectId,s.principal.subject]);memory.set(key,'untrusted-retained-UNKNOWN');
 const h=harness({s,memory}),load=rootLoad(h);load.target.assets=fixtureState().assets;load.target.analyses=fixtureState().analyses;
 for(const analysis of load.target.analyses)analysis.transcript={transcript_id:timelineTranscriptId(load.target.timeline)};
 assert.equal(h.controller.isPending(),true);await load.run();await load.run({initialRead:Symbol('foreign')});assert.equal(load.calls.length,0);
 await load.run({initialRead:load.permit});assert.deepEqual(h.s.timeline,load.target.timeline);assert.equal(load.effects.filter(v=>v==='hydrate').length,1);
 assert.equal(h.calls.length,0);assert.equal(memory.get(key),'untrusted-retained-UNKNOWN');assert.equal(h.controller.isPending(),true);assert.equal(h.formRead(),null);
});
test('manual form edits during a late staged load retain all newer data and prevent partial canonical hydration',async()=>{
 const h=harness();await h.read();const load=rootLoad(h,{gate:'/production-package'}),before=clone(h.s.timeline),work=load.run();await load.arrived;
 await h.type(0,'x',22);const draft=h.manualReframeDraft();load.release();await work;
 assert.deepEqual(h.s.timeline,before);assert.equal(h.manualReframeDraft(),draft);assert.equal(h.manualReframeDirty(),true);
 assert.equal(load.effects.includes('hydrate'),false);assert.equal(load.effects.includes('render'),false);assert.equal(h.memory.size,0);assert.equal(h.s.projectLoading,0);
});
