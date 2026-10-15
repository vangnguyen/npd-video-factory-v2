import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
import {audioRole,audioByteHash} from '../uploaded-audio-review.mjs';
import {compatibleBrollPlans} from '../broll-planner.mjs';
import {initializeSqlBrollInternalResolution,validateBrollInternalContext} from '../sql-broll-internal-resolution.mjs';
const code=readFileSync(new URL('../studio.js',import.meta.url),'utf8').replaceAll('\r\n','\n'),html=readFileSync(new URL('../studio.html',import.meta.url),'utf8');
const fixture=JSON.parse(readFileSync(new URL('./fixtures/broll-internal-resolution-studio.json',import.meta.url),'utf8'));
const clone=structuredClone,raw=name=>clone(fixture.records.find(r=>r.name===name).response.json);
function segment(a,b){const start=code.indexOf(a),end=code.indexOf(b,start);assert.ok(start>=0&&end>start);return code.slice(start,end);}
class Element{
 constructor(id){this.id=id;this.type='button';this.value='';this.checked=false;this.disabled=false;this.children=[];this.dataset={};this.attributes={};this.listeners={};this.textContent='';}
 append(...v){this.children.push(...v);}replaceChildren(...v){this.children=[...v];}
 setAttribute(k,v){this.attributes[k]=v;}addEventListener(k,fn){(this.listeners[k]??=[]).push(fn);}focus(){this.focused=true;}
 async fire(k,target=this){for(const fn of this.listeners[k]??[])await fn({target,currentTarget:this,preventDefault(){}});}
}
function stateFixture(){const s=clone(fixture.state_projection);return {...s,selectedBrollPlanId:s.mediaPlanId,analyses:[s.analysis],query:'',panelTab:'broll',
 versions:[{version:1}],preview:{status:'ready'},productionPackage:{approval:{status:'approved'}},activeProductionRender:{status:'ready'},
 selectedClipId:'saved-clip',playhead:2,undoStack:[1],redoStack:[2]};}
function harness({s=stateFixture(),memory=new Map(),handler,badGuard,replaceGuard=false}={}){
 const ids=Object.fromEntries(['plan','item','read','open-held','context','form','fields','asset','acknowledge','admit','observe','retry','discard','status','result','pending','workbench','browser-search']
  .map(n=>[n==='browser-search'?n:'broll-internal-'+n,new Element(n==='browser-search'?n:'broll-internal-'+n)]));
 ids['broll-internal-asset'].type='select-one';ids['broll-internal-acknowledge'].type='checkbox';
 const dom={createElement:t=>new Element(t),querySelectorAll:()=>[ids['broll-internal-asset'],ids['broll-internal-acknowledge']]};
 const messages=[],calls=[],effects=[],guards=[],peers={preparation:false,placement:false,manual:false,linked:false,words:false,audio:false,family:false,narration:false};
 const peer=n=>({isBusy:()=>peers[n],isWorking:()=>peers[n],isPending:()=>peers[n],isDirty:()=>peers[n],sync(){}});
 let token='vf1.explicit-internal-Root-fixture',clock=fixture.clock_ms,ready=false,jobReads=0,root,getHook=null;
 const storage={getItem:k=>{const v=memory.get(k)??null;getHook?.(k,v);return v;},setItem:(k,v)=>memory.set(k,v),compareAndRemoveItem(k,v){if(memory.get(k)!==v)return false;memory.delete(k);return true;}};
 const api=async(path,options={})=>{const c={path,method:options.method??'GET',body:options.body?JSON.parse(options.body):null,privateAdmission:options.brollInternalAdmission};calls.push(c);
  let phase,value;if(path==='/api/v1/auth/session'){phase='session';value=raw('session');}
  else if(c.method==='POST'){phase='post';value=raw('admitted');}
  else if(path.includes('/requests/')){phase=ready?['observe','proof','final'][jobReads++%3]:'queued';value=raw(ready?'poll-resolved':'poll-queued');}
  else{phase=ready?'context-proof':'context';value=raw(ready?'resolved-current-context':'review-context');}
  return handler?handler(c,phase,value,{s,peers,memory,storage,setToken:v=>{token=v;},setClock:v=>{clock=v;}}):value;};
 const stable=new Function(segment('function sqlAudioStable(','\nfunction sqlAudioSourceValue(')+'\nreturn sqlAudioStable;')();
 const args=['state','document','$','videoWordSessionStorage','sessionToken','sqlEditorState','activeAnalysis','variantFamilies','variantNarration','videoWordReview',
  'sqlAudioProcessing','sourceLinkedEditor','sourceLinkedHeld','manualReframeEditor','manualReframeHeld','brollPreparationHeld','brollTimelineHeld',
  'productionWorkbenchDraft','audioWorkbenchDraft','audioRole','audioByteHash','sqlAudioStable','compatibleBrollPlans','validateBrollInternalContext',
  'initializeSqlBrollInternalResolution','api','toast','syncBrollPlanPeers','clearBrollTimelineForm','renderBrowser','Date'];
 const body=segment('let brollInternalController=null','\nlet manualReframeEditor')+'\n'
  +segment('// Reviewed internal B-roll resolution Root integration.','\nensureAuthenticatedSession()')
  +'\nreturn {controller:brollInternalController,brollInternalHeld,brollInternalDirty,brollInternalEditorState,brollInternalSourceContext,brollInternalDraft,'
  +'brollInternalApi,brollInternalStorage,brollInternalBucket,syncBrollInternalForm,runBrollInternalAction,refreshBrollInternal,admission:brollInternalAdmission};';
 const sync=()=>{root?.controller.sync();root?.syncBrollInternalForm();};
 root=new Function(...args,body)(s,dom,q=>ids[q.slice(1)],()=>storage,()=>token,()=>({...s}),()=>s.analysis,peer('family'),peer('narration'),peer('words'),peer('audio'),
  peer('linked'),()=>peers.linked,peer('manual'),()=>peers.manual,()=>peers.preparation,()=>peers.placement,()=> 'saved-production',()=> 'saved-audio',audioRole,
  bytes=>audioByteHash(bytes,webcrypto),stable,compatibleBrollPlans,validateBrollInternalContext,options=>initializeSqlBrollInternalResolution({...options,cryptoImpl:webcrypto,
   clock:()=>clock,newRequestKey:()=>raw('admitted').receipt.request_key,onResolved:async(v,g)=>{guards.push(g);return options.onResolved(v,replaceGuard?badGuard:g);}}),
  api,(...v)=>messages.push(v),sync,()=>effects.push('clear-placement'),()=>effects.push('render-browser'),class extends Date{static now(){return clock;}});
 return {...root,s,memory,storage,ids,calls,messages,guards,peers,effects,setToken:v=>{token=v;},setClock:v=>{clock=v;},setGetHook:v=>{getHook=v;},finish:()=>{ready=true;},
  read:()=>ids['broll-internal-read'].fire('click'),admit:()=>ids['broll-internal-admit'].fire('click'),observe:()=>ids['broll-internal-observe'].fire('click'),
  retry:()=>ids['broll-internal-retry'].fire('click'),openHeld:()=>ids['broll-internal-open-held'].fire('click'),
  fill:async()=>{ids['broll-internal-asset'].value=raw('admitted').receipt.asset_id;ids['broll-internal-acknowledge'].checked=true;await ids['broll-internal-form'].fire('change');}};
}
async function queued(h){await h.read();await h.fill();await h.admit();}
test('persistent form is outside transient browser and mount makes zero requests',()=>{
 assert.ok(html.indexOf('id="broll-internal-workbench"')<html.indexOf('id="browser-content"'));assert.match(html,/id="broll-internal-fields" disabled/);
 const h=harness();assert.equal(h.calls.length,0);assert.equal(h.memory.size,0);assert.equal(h.ids['broll-internal-fields'].disabled,true);
});
test('explicit read uses actual saved N3 context, no POST and no canonical mutation',async()=>{
 const h=harness(),before=clone(h.s);await h.read();assert.deepEqual(h.calls.map(c=>c.method),['GET','GET']);assert.deepEqual(h.s,before);
 assert.equal(h.ids['broll-internal-fields'].disabled,false);assert.equal(h.ids['broll-internal-asset'].children.length,2);
});
test('actual controller + Root receives exact job and only four matching item fields, preserving approval and timeline',async()=>{
 const h=harness(),before=clone(h.s);await queued(h);assert.equal(h.memory.size,1);assert.equal(h.calls.filter(c=>c.method==='POST').length,1);
 assert.deepEqual(h.s,before);h.finish();await h.observe();assert.equal(h.memory.size,0);assert.equal(h.messages.length,0);
 const after=clone(h.s),oldItem=before.mediaPlans[0].items[0],item=after.mediaPlans[0].items[0];
 assert.equal(item.status,'resolved');assert.equal(item.selected_media_asset_id,raw('poll-resolved').job.output_media_asset_id);
 for(const k of ['status','updated_at','selected_media_asset_id','needs_attention']){if(Object.hasOwn(oldItem,k))item[k]=oldItem[k];else delete item[k];}assert.deepEqual(after,before);
 assert.ok(h.guards.length===1);assert.throws(h.guards[0],/kết thúc/);
 assert.equal(h.calls.filter(c=>c.method==='POST').length,1);assert.equal(h.calls.filter(c=>c.path.includes('/requests/')).length,3);
});
test('lost admission response stays UNKNOWN; cold explicit retry sends exact body/key and observes same job',async()=>{
 const memory=new Map(),lost=harness({memory,handler:(c,p,v)=>{if(p==='post')throw Error('owned lost acknowledgement');return v;}});await queued(lost);
 const original=lost.calls.find(c=>c.method==='POST').body,rawHeld=[...memory.values()][0];assert.ok(rawHeld);assert.ok(!rawHeld.includes('vf1.explicit-internal-Root-fixture'));
 const cold=harness({memory});await cold.openHeld();assert.equal(cold.calls.length,0);await cold.read();assert.equal(cold.calls.filter(c=>c.method==='POST').length,0);cold.ids['broll-internal-acknowledge'].checked=true;await cold.retry();
 const resend=cold.calls.find(c=>c.method==='POST');assert.ok(resend,JSON.stringify(cold.messages));assert.deepEqual(resend.body,original);cold.finish();await cold.observe();assert.equal(memory.size,0);
});
test('legacy internal submission opens persistent review instead of dispatching or polling',()=>{
 const action=segment("$('#browser-content').addEventListener('submit',async event=>{",'$("#canonical-shot-list")');
 const internal=action.slice(action.indexOf('if(form.dataset.brollSelect)'),action.indexOf("const button=form.querySelector"));
 assert.match(internal,/broll-internal-workbench.*open=true/);assert.doesNotMatch(internal,/await api|setTimeout|media-resolution-jobs/);
 assert.match(internal,/return;/);assert.match(action,/data-broll-stock/);
});
const drift={actor:h=>h.s.principal.subject='usr:foreign',token:h=>h.setToken('vf1.foreign-credential'),
 expiry:h=>h.s.principal.expires_at=new Date(fixture.clock_ms-1).toISOString(),write:h=>h.s.principal.human_write_enabled=false,
 role:h=>h.s.principal.workspace_roles={'*':'viewer'},analysis:h=>h.s.analysis.fingerprint='f'.repeat(64),
 asset:h=>h.s.assets[1].storage_provider='s3',timeline:h=>h.s.timeline.current_version++,plan:h=>h.s.mediaPlans[0].fingerprint='f'.repeat(64),
 selection:h=>h.s.selectedBrollPlanId='mpl_foreign_plan',form:h=>h.ids['broll-internal-asset'].value='ast_foreign_choice',
 peer:h=>h.peers.manual=true,placement:h=>h.peers.placement=true,preparation:h=>h.peers.preparation=true,
 raw:h=>h.memory.set(h.brollInternalBucket(),'foreign durable request B')};
for(const phase of ['proof','context-proof','final'])for(const [name,mutate]of Object.entries(drift))
 test('Root receives no item after '+name+' changes during '+phase,async()=>{
  let h;h=harness({handler:(c,p,v)=>{if(p===phase)mutate(h);return v;}});await queued(h);const plan=clone(h.s.mediaPlans);
  h.finish();await h.observe();assert.notEqual(h.memory.size,0);assert.equal(h.guards.length,1);assert.equal(h.s.mediaPlans[0].items[0].status,plan[0].items[0].status);
  assert.equal(h.calls.filter(c=>c.method==='POST').length,1);if(name==='raw')assert.ok([...h.memory.values()].includes('foreign durable request B'));
 });
for(const [name,badGuard]of [['undefined',undefined],['false',()=>false],['throw',()=>{throw Error('private guard refused');}],['Promise',()=>Promise.resolve(true)]])
 test('Root requires synchronous literal true private guard: '+name,async()=>{
  const h=harness({badGuard,replaceGuard:true});await queued(h);const before=clone(h.s);h.finish();await h.observe();
  assert.deepEqual(h.s,before);assert.equal(h.memory.size,1);assert.ok(h.messages.length>0);assert.equal(h.calls.filter(c=>c.path.includes('/requests/')).length,1);
 });
for(const [name,mutate]of Object.entries({provider:h=>h.s.assets[1].storage_provider='s3',token:h=>h.setToken('vf1.changed-last-get'),peer:h=>h.peers.audio=true,
 form:h=>h.ids['broll-internal-asset'].value='ast_changed_last_get'}))
 test('final native getter '+name+' drift is fenced before first item write',async()=>{
  let h;h=harness({handler:(c,p,v)=>{if(p==='final')h.setGetHook(()=>{h.setGetHook(null);mutate(h);});return v;}});
  await queued(h);const before=clone(h.s.mediaPlans);h.finish();await h.observe();assert.deepEqual(h.s.mediaPlans,before);assert.equal(h.memory.size,1);
 });
for(const [name,mutate]of Object.entries({plan:v=>v.plan.configuration_json.brand_context='changed',source:v=>v.source.transcript_sha256='f'.repeat(64),
 item:v=>v.item.strategy='ai_video',candidate:v=>v.candidates[0].candidate.license='changed',timeline:v=>v.timeline_sha256='f'.repeat(64)}))
 test('fresh context valid mock literal hash cannot authorize '+name+' drift',async()=>{
  const h=harness({handler:async(c,p,v)=>{if(p==='context-proof'){mutate(v);const {context_json,context_sha256,...projected}=v;
      v.context_json=JSON.stringify(projected);v.context_sha256=await audioByteHash(new TextEncoder().encode(v.context_json),webcrypto);}return v;}});
  await queued(h);const before=clone(h.s);h.finish();await h.observe();assert.deepEqual(h.s,before);assert.equal(h.memory.size,1);
 });
for(const state of ['failed','cancelled','unknown'])test(state+' observation stays held without item adoption or new request',async()=>{
 const h=harness({handler:(c,p,v)=>{if(p==='queued'){if(state==='unknown')return raw('poll-stale-custody');return {...v,state,
   job:{...v.job,status:state},can_adopt:false,output:null,error_code:'OWNED_NODE_TERMINAL_FIXTURE',needs_attention:true};}return v;}});
 await queued(h);const before=clone(h.s);await h.observe();assert.deepEqual(h.s,before);assert.equal(h.memory.size,1);assert.equal(h.guards.length,0);
 assert.equal(h.calls.filter(c=>c.method==='POST').length,1);assert.equal(h.controller.state().observation.state,state);
});
test('peer holds are reciprocal and own working/pending/draft excluded from operation getter',async()=>{
 const h=harness();for(const key of Object.keys(h.peers)){h.peers[key]=true;await h.read();assert.equal(h.calls.length,0,key);h.peers[key]=false;}
 await h.read();await h.fill();assert.equal(h.brollInternalDirty(),true);assert.equal(h.brollInternalHeld(),true);assert.equal(h.brollInternalEditorState().dirty,false);
 await h.admit();assert.equal(h.brollInternalHeld(),true);assert.equal(h.brollInternalEditorState().dirty,false);assert.equal(h.memory.size,1);
});
test('native read-only role cannot admit even forged click; absent acknowledgement/candidate cannot POST',async()=>{
 const h=harness();await h.read();await h.admit();assert.equal(h.calls.filter(c=>c.method==='POST').length,0);
 h.ids['broll-internal-acknowledge'].checked=true;await h.admit();assert.equal(h.calls.filter(c=>c.method==='POST').length,0);
 await h.fill();h.s.principal.human_write_enabled=false;await h.admit();assert.equal(h.calls.filter(c=>c.method==='POST').length,0);
});
test('cold malformed or foreign held record never clears bytes or sends request',async()=>{
 const key='vf-sql-broll-internal-pending-v1:'+JSON.stringify([fixture.state_projection.workspaceId,fixture.state_projection.projectId,fixture.state_projection.principal.subject]);
 for(const text of ['{broken',JSON.stringify({schema_version:'sql-broll-internal-pending.v1',context:{workspace_id:'wsp_foreign'}})]){
  const memory=new Map([[key,text]]),h=harness({memory});await h.openHeld();await h.read();assert.equal(memory.get(key),text);assert.equal(h.calls.length,0);assert.equal(h.brollInternalHeld(),true);}
});
test('actual generic API blocks unrelated writers and strips only owned private admission',async()=>{
 const h=harness();await h.read();await h.fill();const start=code.indexOf('async function api('),source=code.slice(start,code.indexOf('\n}\n',start)+3),calls=[];
 const api=new Function('brollPlanHeld','manualReframeHeld','sourceLinkedHeld','audioProcessingHeld','videoWordsHeld','brollInternalAdmission','authenticatedFetch','ApiError',
  'const brollPlanAdmission=Symbol(),brollTimelineAdmission=Symbol(),manualReframeAdmission=Symbol(),sourceLinkedAdmission=Symbol(),audioProcessingAdmission=Symbol(),videoWordAdmission=Symbol();\n'+source+'\nreturn api;')(
  h.brollInternalHeld,()=>false,()=>false,()=>false,()=>false,h.admission,async(path,options)=>{calls.push({path,options});return{ok:true,status:204};},class extends Error{});
 await assert.rejects(api('/unrelated',{method:'POST'}));await assert.rejects(api('/unrelated',{method:'POST',brollInternalAdmission:Symbol('foreign')}));assert.equal(calls.length,0);
 await api('/api/v1/projects/owned/review',{method:'POST',brollInternalAdmission:h.admission});assert.equal(calls.length,1);
 assert.equal(Object.hasOwn(calls[0].options,'brollInternalAdmission'),false);await assert.rejects(h.brollInternalApi('/unrelated',{method:'POST'}));
 assert.match(segment('function brollPlanHeld()','\nlet brollTimelineController'),/brollInternalHeld/);
 assert.match(segment('function brollPlanEditorState()','\nfunction brollPlanContext'),/brollInternalHeld/);
 assert.match(segment('function brollTimelineEditorState()','\nfunction brollTimelineSourceContext'),/brollInternalHeld/);
});
test('persistent plan/item handlers reject selection changes while own draft is unsent',async()=>{
 const h=harness();await h.read();await h.fill();const before=clone(h.s),item=h.brollInternalEditorState().mediaPlanItemId;
 h.ids['broll-internal-plan'].value='mpl_foreign_choice';await h.ids['broll-internal-plan'].fire('change');
 h.ids['broll-internal-item'].value='mpi_foreign_choice';await h.ids['broll-internal-item'].fire('change');
 assert.equal(h.ids['broll-internal-plan'].value,before.selectedBrollPlanId);assert.equal(h.ids['broll-internal-item'].value,item);assert.deepEqual(h.s,before);
 assert.equal(h.calls.filter(c=>c.method==='POST').length,0);
});
test('no timer, latest job, generic resolution polling or timeline mutation in reviewed Root module',()=>{
 const internal=segment('// Reviewed internal B-roll resolution Root integration.','\nensureAuthenticatedSession()');
 assert.doesNotMatch(internal,/setTimeout|setInterval|media-resolution-jobs|state\.timeline\s*=|state\.preview\s*=|state\.productionPackage\s*=/);
 assert.match(internal,/requests\/.*request_key.*jobs\/.*resolution_job_id/);
});
