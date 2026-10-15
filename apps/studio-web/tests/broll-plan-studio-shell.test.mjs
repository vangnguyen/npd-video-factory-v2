import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto,createHash} from 'node:crypto';
import {audioRole} from '../uploaded-audio-review.mjs';
import {timelineTranscriptId} from '../timeline-history.mjs';
import {initializeBrollPlanReview,defaultBrollPlanSettings,brollPlanSettings,validateBrollPlanContext} from '../broll-plan-review.mjs';

const code=readFileSync(new URL('../studio.js',import.meta.url),'utf8'),html=readFileSync(new URL('../studio.html',import.meta.url),'utf8');
const captured=JSON.parse(readFileSync(new URL('./fixtures/sql-broll-plan-review.json',import.meta.url),'utf8'));
const clone=structuredClone;
function segment(a,b){const start=code.indexOf(a),end=code.indexOf(b,start);assert.ok(start>=0&&end>start);return code.slice(start,end);}
class Element{
 constructor(id){this.id=id;this.value='';this.checked=false;this.disabled=false;this.type='button';this.dataset={};this.listeners={};this.textContent='';this.open=false;}
 addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}focus(){this.focused=true;}
 async fire(name,target=this){for(const fn of this.listeners[name]??[])await fn({target,currentTarget:this,preventDefault(){}});}
}
function harness({memory=new Map(),handler,s=clone(captured.state)}={}){
 Object.assign(s,{analyses:[s.analysis],mediaPlans:[],versions:[],selectedBrollPlanId:null,transcriptDrafts:new Map(),projectLoading:0,
  preview:{status:'ready'},productionPackage:{approval:{status:'approved'}},selectedClipId:'kept-clip',undoStack:[1],redoStack:[2]});
 const names=['user','library','stock','user-order','library-order','stock-order','acknowledge','read','prepare','reconcile','resend','discard','form','fields','availability','pending','status','workbench'];
 const ids=Object.fromEntries(names.map(name=>['broll-plan-'+name,new Element('broll-plan-'+name)]));
 for(const name of ['user','library','stock','acknowledge']){ids['broll-plan-'+name].type='checkbox';ids['broll-plan-'+name].dataset.brollSetting='';}
 for(const name of ['user-order','library-order','stock-order']){ids['broll-plan-'+name].type='select';ids['broll-plan-'+name].dataset.brollSetting='';}
 ids['broll-plan-user'].checked=ids['broll-plan-library'].checked=true;
 for(const [name,value]of [['user-order','1'],['library-order','2'],['stock-order','3']])ids['broll-plan-'+name].value=value;
 const settings=Object.values(ids).filter(v=>Object.hasOwn(v.dataset,'brollSetting'));
 const dom={querySelectorAll:selector=>selector.includes('data-broll-setting')?settings:[]};
 let token='vf1.fixture-local-not-provider',clock=captured.clock,learning=null,committed=false,root;
 const calls=[],effects=[],messages=[],peers={family:false,narration:false,words:false,audio:false,linked:false,manual:false};
 const peer=name=>({sync(){},isBusy:()=>peers[name],isWorking:()=>peers[name],isPending:()=>peers[name],isDirty:()=>peers[name]});
 const storage={getItem:key=>memory.get(key)??null,setItem:(key,value)=>memory.set(key,value),
  compareAndRemoveItem:(key,value)=>{if(memory.get(key)!==value)return false;memory.delete(key);return true;}};
 const api=async(path,options={})=>{const c={path,method:options.method??'GET',body:options.body?JSON.parse(options.body):null};calls.push(c);
  let phase,value;if(path==='/api/v1/auth/session'){phase='session';value=clone(s.principal);}
  else if(c.method==='POST'){phase='post';committed=true;value=clone(captured.response);}
  else if(path.includes('/requests/')){phase='receipt';value={...clone(captured.response),replayed:true};}
  else if(path.includes('/media-plans/')){phase='plan';value=clone(captured.response.plan);}
  else{phase=committed?'context-proof':'context';value=clone(captured.context);}
  return handler?handler(c,phase,value,{s,peers,memory,storage,setToken:v=>{token=v;},setClock:v=>{clock=v;},setLearning:v=>{learning=v;}}):value;
 };
 const stable=new Function(segment('function sqlAudioStable(','\nfunction sqlAudioSourceValue(')+'\nreturn sqlAudioStable;')();
 const args=['state','document','$','videoWordSessionStorage','sqlEditorState','activeAnalysis','channelLearning','sessionToken','audioRole','sqlAudioStable',
  'variantFamilies','variantNarration','videoWordReview','sqlAudioProcessing','sourceLinkedEditor','sourceLinkedHeld','manualReframeEditor','manualReframeHeld','syncManualReframeForm',
  'productionWorkbenchDraft','audioWorkbenchDraft','defaultBrollPlanSettings','brollPlanSettings','validateBrollPlanContext','initializeBrollPlanReview',
  'api','audioReview','stockReview','videoReview','renderBrowser','toast','Date'];
 const body=segment('let brollPlanController=null','\nlet manualReframeEditor')+'\n'+segment('function brollPlanEditorState(){','\nasync function loadProjectList()')+
  '\nreturn {controller:brollPlanController,brollPlanHeld,brollPlanDirty,brollPlanDraft,brollPlanEditorState,brollPlanContext,syncBrollPlanForm,runBrollPlanAction,brollPlanSettingsFromForm,adoptPreparedBrollPlan,brollPlanApi,formRead:()=>brollPlanFormRead,storage:brollPlanStorage};';
 const noop={sync(){}};
 root=new Function(...args,body)(s,dom,selector=>ids[selector.slice(1)],()=>storage,()=>({...s,busy:s.busy||s.projectLoading>0}),()=>s.analysis,
  {advice:()=>learning?{learning_snapshot_id:learning}:{}},()=>token,audioRole,stable,peer('family'),peer('narration'),peer('words'),peer('audio'),peer('linked'),()=>peers.linked,
  peer('manual'),()=>peers.manual,()=>{},()=> 'production-baseline',()=> 'audio-baseline',defaultBrollPlanSettings,brollPlanSettings,
  (value,state,now=clock)=>validateBrollPlanContext(value,state,now),
  options=>initializeBrollPlanReview({...options,cryptoImpl:webcrypto,clock:()=>clock,newRequestKey:()=>captured.request.request_key}),api,noop,noop,noop,
  ()=>effects.push('render-browser'),(...v)=>messages.push(v),{parse:Date.parse,now:()=>clock});
 root.syncBrollPlanForm();
 const change=async(name,value)=>{const e=ids['broll-plan-'+name];if(e.type==='checkbox')e.checked=value;else e.value=value;await ids['broll-plan-form'].fire('change',e);};
 return {...root,s,ids,calls,effects,messages,memory,peers,change,storage,setClock:v=>{clock=v;},setToken:v=>{token=v;},setLearning:v=>{learning=v;},
  read:()=>ids['broll-plan-read'].fire('click'),prepare:()=>ids['broll-plan-prepare'].fire('click'),reconcile:()=>ids['broll-plan-reconcile'].fire('click'),
  resend:()=>ids['broll-plan-resend'].fire('click'),discard:()=>ids['broll-plan-discard'].fire('click')};
}
test('persistent reviewed form is outside transient browser-content, and the legacy create action only opens it',()=>{
 assert.ok(html.indexOf('id="broll-plan-workbench"')<html.indexOf('id="browser-content"'));
 const action=segment("    if(button.hasAttribute('data-broll-create')){",'    }else{');
 assert.match(action,/broll-plan-workbench.*open=true/);assert.match(action,/broll-plan-read.*focus/);assert.doesNotMatch(action,/api\(|POST|await /);
});
test('mount/change/explicit read use zero POST; default providers stay external-off and AI budget zero',async()=>{
 const h=harness();assert.equal(h.calls.length,0);assert.equal(h.ids['broll-plan-fields'].disabled,true);
 await h.read();assert.deepEqual(h.calls.map(v=>v.method),['GET','GET']);assert.deepEqual(h.brollPlanSettingsFromForm(),defaultBrollPlanSettings());
 assert.equal(h.ids['broll-plan-stock'].disabled,true);assert.match(h.ids['broll-plan-availability'].textContent,/chưa khả dụng/);
 await h.change('user-order','2');await h.change('library-order','1');assert.equal(h.calls.length,2);assert.equal(h.brollPlanDirty(),true);assert.equal(h.brollPlanHeld(),true);
 assert.equal(h.brollPlanEditorState().dirty,false);await h.discard();assert.equal(h.brollPlanDirty(),false);assert.equal(h.calls.length,2);
});
test('actual controller and full Root callback adopt only the exact receipt/plan/context, preserving canonical and independent state',async()=>{
 const h=harness(),before=clone(h.s);await h.read();await h.change('acknowledge',true);await h.prepare();
 assert.deepEqual(h.calls.map(v=>v.method),['GET','GET','GET','POST','GET','GET','GET']);assert.deepEqual(h.calls[3].body,captured.request);
 assert.deepEqual(h.s.mediaPlans,[captured.response.plan]);assert.equal(h.s.selectedBrollPlanId,captured.response.plan.media_plan_id);
 for(const key of ['timeline','assets','analyses','versions','preview','productionPackage','selectedClipId','undoStack','redoStack'])assert.deepEqual(h.s[key],before[key]);
 assert.deepEqual(h.effects,['render-browser']);assert.equal(h.memory.size,0);assert.equal(h.brollPlanHeld(),false);assert.equal(h.formRead(),null);
 assert.ok(!h.calls.some(v=>/stock-search|resolve|apply-broll|render/.test(v.path)));
});
test('read cannot overwrite dirty choices; confirmation, valid unique order, selected tier and availability are required before POST',async()=>{
 const h=harness();await h.read();await h.prepare();assert.equal(h.calls.length,2);assert.equal(h.memory.size,0);
 await h.change('user-order','2');const draft=h.brollPlanDraft();await h.read();assert.equal(h.brollPlanDraft(),draft);assert.equal(h.calls.length,2);
 await h.change('acknowledge',true);await h.prepare();assert.equal(h.calls.length,2);await h.discard();
 await h.change('user',false);await h.change('library',false);await h.change('acknowledge',true);await h.prepare();assert.equal(h.calls.length,2);
 await h.discard();await h.change('stock',true);await h.change('acknowledge',true);await h.prepare();assert.equal(h.calls.filter(v=>v.method==='POST').length,0);
});
for(const peer of ['family','narration','words','audio','linked','manual'])test(`active ${peer} peer prevents own private preparation before GET/POST`,async()=>{
 const h=harness();await h.read();await h.change('acknowledge',true);h.peers[peer]=true;await h.prepare();assert.equal(h.calls.length,2);assert.equal(h.memory.size,0);
});
for(const phase of ['receipt','plan','context-proof'])for(const drift of ['project','token','actor','expiry','role','write-off','timeline','analysis','assets','learning','peer','form']){
 test(`${drift} during ${phase} keeps original plans and exact UNKNOWN without adopting`,async()=>{
  const h=harness({handler:(c,p,value,t)=>{if(p===phase){
   if(drift==='project')t.s.projectId='prj_another';else if(drift==='token')t.setToken('vf1.other-literal-token');
   else if(drift==='actor')t.s.principal.subject='usr:other';else if(drift==='expiry')t.setClock(Date.parse(t.s.principal.expires_at));
   else if(drift==='role'){t.s.principal.platform_role='viewer';t.s.principal.workspace_roles={};}else if(drift==='write-off')t.s.principal.human_write_enabled=false;
   else if(drift==='timeline')t.s.timeline.current_version++;else if(drift==='analysis')t.s.analysis.fingerprint='f'.repeat(64);
   else if(drift==='assets')t.s.assets[0].filename='changed.mp4';else if(drift==='learning')t.setLearning('lsn_new_advice');
   else if(drift==='peer')t.peers.audio=true;else h.ids['broll-plan-user-order'].value='3';
  }return value;}});await h.read();await h.change('acknowledge',true);await h.prepare();
  assert.deepEqual(h.s.mediaPlans,[]);assert.equal(h.s.selectedBrollPlanId,null);assert.equal(h.memory.size,1);assert.deepEqual(h.effects,[]);
  assert.equal(h.calls.filter(v=>v.method==='POST').length,1);
 });
}
for(const bad of ['receipt-settings','receipt-source','receipt-actor','receipt-flags','saved-plan','fresh-context'])test(`contradictory ${bad} cannot enter the Studio plan list`,async()=>{
 const h=harness({handler:(c,p,v)=>{if(p==='receipt'){
  if(bad==='receipt-settings')v.receipt.settings.resolver_priority.reverse();else if(bad==='receipt-source')v.receipt.source.source_sha256='f'.repeat(64);
  else if(bad==='receipt-actor')v.receipt.actor_ref='usr:other';else if(bad==='receipt-flags')v.preparation_provider_calls=1;
 }if(p==='plan'&&bad==='saved-plan')v.version++;if(p==='context-proof'&&bad==='fresh-context')v.context_sha256='f'.repeat(64);return v;}});
 await h.read();await h.change('acknowledge',true);await h.prepare();assert.deepEqual(h.s.mediaPlans,[]);assert.equal(h.memory.size,1);assert.deepEqual(h.effects,[]);
});
test('lost response survives reload; a cold controller reconciles exact receipt without a second preparation',async()=>{
 const memory=new Map(),h=harness({memory,handler:(c,p,v)=>{if(p==='post')throw Error('lost');return v;}});
 await h.read();await h.change('acknowledge',true);await h.prepare();const raw=[...memory.values()][0];assert.ok(raw);assert.equal(h.brollPlanHeld(),true);
 await h.discard();assert.equal([...memory.values()][0],raw);const cold=harness({memory});assert.equal(cold.brollPlanHeld(),true);assert.equal(cold.calls.length,0);
 await cold.reconcile();assert.equal(cold.calls.filter(v=>v.method==='POST').length,0);assert.equal(cold.s.mediaPlans.length,1);assert.equal(memory.size,0);
});
test('untrusted storage is held at mount, never parsed/adopted/removed by discard, and no request occurs',async()=>{
 const memory=new Map(),s=clone(captured.state),key='vf-broll-plan-pending-v1:'+JSON.stringify([s.workspaceId,s.projectId,s.principal.subject]);memory.set(key,'malformed owner-held bytes');
 const h=harness({memory,s});assert.equal(h.brollPlanHeld(),true);await h.discard();assert.equal(memory.get(key),'malformed owner-held bytes');assert.equal(h.calls.length,0);
});
test('learning advice changed after explicit read cannot silently enter a new preparation',async()=>{
 const h=harness();await h.read();h.setLearning('lsn_new_snapshot');assert.equal(h.brollPlanEditorState().learning_snapshot_id,'lsn_new_snapshot');
 await h.change('acknowledge',true);await h.prepare();assert.equal(h.calls.length,2);assert.equal(h.memory.size,0);
});
test('a scoped 404 enables only identical explicit resend, and deferred stock is never searched by this workflow',async()=>{
 let posts=0;const h=harness({handler:(c,p,v)=>{if(p==='post'&&++posts===1)throw Error('did not arrive');
  if(p==='receipt'&&posts===1)throw Object.assign(Error('not found'),{status:404});return v;}});
 await h.read();await h.change('acknowledge',true);await h.prepare();const original=[...h.memory.values()][0];
 assert.equal(h.ids['broll-plan-resend'].disabled,true);await h.reconcile();assert.equal(h.ids['broll-plan-resend'].disabled,false);
 assert.equal([...h.memory.values()][0],original);await h.resend();const sent=h.calls.filter(c=>c.method==='POST');
 assert.equal(sent.length,2);assert.deepEqual(sent[0].body,sent[1].body);assert.equal(h.memory.size,0);assert.equal(h.s.mediaPlans.length,1);
 assert.ok(!h.calls.some(c=>/stock-search|resolve|apply-broll/.test(c.path)));
});
test('foreign pending bytes inserted during the resend context read cannot be posted over or removed by Root admission',async()=>{
 let posts=0,replace=false;const foreign='foreign UNKNOWN B';
 const h=harness({handler:(c,p,v,t)=>{if(p==='post'&&++posts===1)throw Error('did not arrive');
  if(p==='receipt')throw Object.assign(Error('not found'),{status:404});
  if(p==='context-proof'&&replace){const key=[...t.memory.keys()][0];t.memory.set(key,foreign);}return v;}});
 await h.read();await h.change('acknowledge',true);await h.prepare();await h.reconcile();replace=true;await h.resend();
 assert.equal(h.calls.filter(c=>c.method==='POST').length,1);assert.deepEqual([...h.memory.values()],[foreign]);assert.equal(h.s.mediaPlans.length,0);
});
test('Root private preparation admission strips only its own marker and cannot bypass manual/word/audio/linked holds',async()=>{
 let held=true,manual=false,word=false,audio=false,linked=false;const b=Symbol('broll'),m=Symbol('manual'),w=Symbol('word'),a=Symbol('audio'),l=Symbol('linked'),calls=[];
 const api=new Function('authenticatedFetch','brollPlanHeld','brollPlanAdmission','manualReframeHeld','manualReframeAdmission','videoWordsHeld','videoWordAdmission',
  'audioProcessingHeld','audioProcessingAdmission','sourceLinkedHeld','sourceLinkedAdmission',segment('class ApiError extends Error {','\nfunction toast(')+'\nreturn api;')(
   async(path,options)=>{calls.push({path,options});return{ok:true,status:204};},()=>held,b,()=>manual,m,()=>word,w,()=>audio,a,()=>linked,l);
 for(const method of ['POST','PUT','PATCH','DELETE'])await assert.rejects(api('/api/v1/projects/current/timeline',{method}),/B-roll/);
 await api('/api/v1/projects/current/timeline');await api('/api/v1/projects/current/broll-plan-review',{method:'POST',brollPlanAdmission:b});
 assert.equal(Object.hasOwn(calls.at(-1).options,'brollPlanAdmission'),false);
 for(const peer of ['manual','word','audio','linked']){
  if(peer==='manual')manual=true;if(peer==='word')word=true;if(peer==='audio')audio=true;if(peer==='linked')linked=true;
  await assert.rejects(api('/api/v1/projects/current/broll-plan-review',{method:'POST',brollPlanAdmission:b}));manual=word=audio=linked=false;
 }
 assert.equal(calls.length,2);held=false;await api('/api/v1/projects/current/timeline',{method:'PUT'});assert.equal(calls.length,3);
});
function rootLoad(h,{gate=null}={}){
 const initial=Symbol('private-canonical-read'),effects=[],calls=[],target={timeline:clone(captured.state.timeline),assets:clone(captured.state.assets),analyses:[clone(captured.state.analysis)]};
 let reached,release;const arrived=new Promise(resolve=>{reached=resolve;});h.ids['project-select']=new Element('project-select');h.ids['project-select'].value=h.s.projectId;
 const peer={sync(){},isBusy:()=>false,isWorking:()=>false,isPending:()=>false,isDirty:()=>false,reload:async()=>effects.push('peer-read')};
 const api=async(path,options={})=>{assert.equal(options.method??'GET','GET');calls.push(path);
  if(gate&&path.endsWith(gate)){reached();await new Promise(resolve=>{release=resolve;});}
  if(path.endsWith('/assets'))return clone(target.assets);if(path.endsWith('/analyses'))return clone(target.analyses);
  if(path.endsWith('/timeline'))return clone(target.timeline);if(path.endsWith('/timeline/versions'))return [];
  if(path.endsWith('/analytics'))return {latest_sync:null};if(path.endsWith('/production-package'))return null;return [];
 };
 const args=['state','initialProjectRead','brollPlanHeld','brollPlanBusy','brollPlanDirty','brollPlanOperation','brollPlanDraft','syncBrollPlanForm','manualReframeHeld',
  'manualReframeEditor','manualReframeDirty','manualReframeApplying','manualReframeDraft','syncManualReframeForm','sourceLinkedHeld','audioProcessingHeld','videoWordsHeld',
  'sourceLinkedEditor','sqlAudioProcessing','videoWordReview','variantNarration','audioReview','stockReview','toast','sessionToken','productionWorkbenchDraft','audioWorkbenchDraft',
  '$','videoReview','multiInput','variantFamilies','stopPreviewPolling','stopProductionPolling','stopAnalyticsPolling','setSaveStatus','api','timelineTranscriptId','render',
  'startPreviewPolling','startProductionPolling','startAnalyticsPolling','window','Date'];
 const workbench={setBusy(){},async prepareReload({isCurrent}){assert.equal(isCurrent(),true);return()=>{assert.equal(isCurrent(),true);effects.push('hydrate');};}};
 const made=new Function(...args,'let multiInputBaseline="before-load";\n'+segment('async function loadProject(','\nfunction renderNoProject(')+'\n'+
  segment('$("#project-select").addEventListener("change",','\n$("#reload-button")')+'\nreturn loadProject;')(
  h.s,initial,h.brollPlanHeld,false,h.brollPlanDirty,null,h.brollPlanDraft,h.syncBrollPlanForm,()=>false,peer,()=>false,null,()=> 'manual-baseline',()=>{},
  ()=>false,()=>false,()=>false,peer,peer,peer,peer,peer,peer,(...v)=>h.messages.push(v),()=> 'vf1.fixture-local-not-provider',()=> 'production-baseline',()=> 'audio-baseline',
  selector=>h.ids[selector.slice(1)],peer,workbench,peer,()=>{},()=>{},()=>{},()=>{},api,timelineTranscriptId,()=>{effects.push('render');h.syncBrollPlanForm();},()=>{},()=>{},()=>{},
  {localStorage:{setItem(){}}},{parse:Date.parse,now:()=>captured.clock});
 return {run:made,initial,calls,effects,target,arrived,release:()=>release(),switchTo:async id=>{h.ids['project-select'].value=id;await h.ids['project-select'].fire('change');}};
}
test('dirty B-roll choices block project switch and reload before any canonical read',async()=>{
 const h=harness();await h.read();await h.change('user',false);const load=rootLoad(h),before=clone(h.s.timeline),draft=h.brollPlanDraft();
 await load.switchTo('prj_new_project');await load.run();assert.equal(h.s.projectId,before.project_id);assert.equal(h.ids['project-select'].value,before.project_id);
 assert.deepEqual(h.s.timeline,before);assert.equal(h.brollPlanDraft(),draft);assert.equal(load.calls.length,0);
});
test('clean B-roll read permits a normal project switch, clearing stale UI before staged read capture',async()=>{
 const h=harness();await h.read();const load=rootLoad(h),id='prj_other_clean';load.target.timeline.project_id=id;
 for(const row of load.target.assets)row.project_id=id;for(const row of load.target.analyses)row.project_id=id;
 await load.switchTo(id);assert.deepEqual(h.s.timeline,load.target.timeline);assert.equal(h.formRead(),null);assert.equal(h.brollPlanHeld(),false);
 assert.equal(load.effects.filter(v=>v==='hydrate').length,1);assert.equal(h.calls.length,2);
});
test('durable B-roll UNKNOWN permits only pristine private cold canonical bootstrap, without automatic B-roll requests',async()=>{
 const memory=new Map(),s=clone(captured.state),key='vf-broll-plan-pending-v1:'+JSON.stringify([s.workspaceId,s.projectId,s.principal.subject]);memory.set(key,'untrusted held bytes');
 const h=harness({s,memory});Object.assign(h.s,{timeline:null,assets:[],analyses:[],versions:[],preview:null,productionPackage:null});const load=rootLoad(h);
 await load.run();await load.run({initialRead:Symbol('foreign')});assert.equal(load.calls.length,0);
 await load.run({initialRead:load.initial});assert.deepEqual(h.s.timeline,load.target.timeline);assert.equal(h.calls.length,0);
 assert.equal(memory.get(key),'untrusted held bytes');assert.equal(h.brollPlanHeld(),true);assert.equal(load.effects.filter(v=>v==='hydrate').length,1);
});
test('late B-roll choice change invalidates the full staged load without partial source/workbench adoption',async()=>{
 const h=harness();await h.read();const load=rootLoad(h,{gate:'/production-package'}),before=clone(h.s.timeline),work=load.run();await load.arrived;
 await h.change('user',false);const draft=h.brollPlanDraft();load.release();await work;assert.deepEqual(h.s.timeline,before);assert.equal(h.brollPlanDraft(),draft);
 assert.equal(load.effects.includes('hydrate'),false);assert.equal(load.effects.includes('render'),false);assert.equal(h.s.projectLoading,0);
});
test('configured unpaid stock availability is read-only; choosing its explicit priority still performs zero POST',async()=>{
 const h=harness({handler:(c,p,v)=>{if(p==='context'){
  const {context_json,context_sha256,...raw}=v;raw.licensed_stock_enabled=true;raw.providers.stock={...raw.providers.stock,status:'healthy',paid:false};
  raw.stock_binding={provider:'pexels',mode:'official',paid:false,configuration_sha256:'a'.repeat(64)};
  const literal=JSON.stringify(raw);return {...raw,context_json:literal,context_sha256:createHash('sha256').update(literal).digest('hex')};
 }return v;}});await h.read();assert.equal(h.ids['broll-plan-stock'].disabled,false);
 await h.change('stock',true);await h.change('stock-order','1');await h.change('user-order','2');await h.change('library-order','3');
 assert.deepEqual(h.brollPlanSettingsFromForm(),{allow_stock:true,allow_ai_image:false,allow_ai_video:false,max_ai_cost_vnd:'0',
  resolver_priority:['licensed_stock','user_asset','internal_library']});assert.equal(h.calls.length,2);assert.equal(h.memory.size,0);
 // The changed availability is an explicit Node contract projection; no
 // configured provider or search result is represented as a real API test.
});
for(const drift of ['form','learning','credential'])test(`late ${drift} during preparation session read prevents durable intent and POST`,async()=>{
 let sessions=0;const h=harness({handler:(c,p,v,t)=>{if(p==='session'&&++sessions===2){
  if(drift==='form')h.ids['broll-plan-user-order'].value='3';else if(drift==='learning')t.setLearning('lsn_late_advice');else t.setToken('vf1.changed-credential');
 }return v;}});await h.read();await h.change('acknowledge',true);await h.prepare();
 assert.equal(h.calls.filter(v=>v.method==='POST').length,0);assert.equal(h.memory.size,0);assert.deepEqual(h.s.mediaPlans,[]);
});
test('captured-clock replay stays reproducible after the ambient machine clock passes the fixture expiry',async t=>{
 t.mock.method(Date,'now',()=>Date.parse(captured.state.principal.expires_at)+86400_000);
 const h=harness();await h.read();await h.change('acknowledge',true);await h.prepare();
 assert.equal(h.s.mediaPlans.length,1);assert.equal(h.memory.size,0);
});
for(const phase of ['receipt','plan','context-proof'])test(`foreign durable bytes at ${phase} proof are retained before Root plan adoption`,async()=>{
 const foreign='foreign durable request B';const h=harness({handler:(c,p,value,t)=>{if(p===phase){const key=[...t.memory.keys()][0];t.memory.set(key,foreign);}return value;}});
 await h.read();await h.change('acknowledge',true);await h.prepare();
 assert.deepEqual(h.s.mediaPlans,[]);assert.equal(h.s.selectedBrollPlanId,null);assert.deepEqual(h.effects,[]);
 assert.deepEqual([...h.memory.values()],[foreign]);assert.equal(h.calls.filter(v=>v.method==='POST').length,1);
});
test('scope changed inside the final synchronous durable read cannot retarget or adopt a prepared plan',async()=>{
 let afterContext=false,reads=0;const h=harness({handler:(c,p,v)=>{if(p==='context-proof')afterContext=true;return v;}});
 const get=h.storage.getItem;h.storage.getItem=key=>{const raw=get(key);if(afterContext&&++reads===2)h.s.projectId='prj_drift_final_raw';return raw;};
 await h.read();await h.change('acknowledge',true);await h.prepare();
 assert.deepEqual(h.s.mediaPlans,[]);assert.equal(h.s.selectedBrollPlanId,null);assert.deepEqual(h.effects,[]);assert.equal(h.memory.size,1);
});
for(const changed of ['selection','plan-list'])test(`a newer ${changed} inside the final native read is preserved without accepting the old proposal`,async()=>{
 let afterContext=false,reads=0;const h=harness({handler:(c,p,v)=>{if(p==='context-proof')afterContext=true;return v;}});
 const newer={media_plan_id:'mpl_newer_proposal',version:9},get=h.storage.getItem;
 h.storage.getItem=key=>{const raw=get(key);if(afterContext&&++reads===2){
  if(changed==='selection')h.s.selectedBrollPlanId=newer.media_plan_id;else h.s.mediaPlans=[newer];
 }return raw;};
 await h.read();await h.change('acknowledge',true);await h.prepare();
 assert.deepEqual(h.s.mediaPlans,changed==='plan-list'?[newer]:[]);
 assert.equal(h.s.selectedBrollPlanId,changed==='selection'?newer.media_plan_id:null);
 assert.deepEqual(h.effects,[]);assert.equal(h.memory.size,1);
});
