import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
import {audioRole} from '../uploaded-audio-review.mjs';
import {initializeSqlBrollTimelineReview,brollTimelineRead,brollTimelineSelection} from '../sql-broll-timeline-review.mjs';

const code=readFileSync(new URL('../studio.js',import.meta.url),'utf8'),html=readFileSync(new URL('../studio.html',import.meta.url),'utf8');
const capture=JSON.parse(readFileSync(new URL('./fixtures/sql-broll-timeline-review.json',import.meta.url),'utf8'));
const r=Object.fromEntries(capture.records.map(v=>[v.name,v])),clone=structuredClone;
function segment(a,b){const start=code.indexOf(a),end=code.indexOf(b,start);assert.ok(start>=0&&end>start);return code.slice(start,end);}
function fixtureState(){const timeline=clone(r.context_before.body.timeline);return{workspaceId:timeline.workspace_id,projectId:timeline.project_id,
 timeline,analysis:clone(capture.analysis),analyses:[clone(capture.analysis)],assets:clone(capture.assets),mediaPlans:[clone(capture.plan)],
 selectedBrollPlanId:capture.plan.media_plan_id,versions:clone(r.history.body.filter(v=>v.version===1)),playhead:999,selectedClipId:'kept-clip',undoStack:[1],redoStack:[2],
 preview:{status:'ready',valid_for_current_timeline:true},productionPackage:{approval:{status:'approved'},current_for_timeline:true,
 latest_review_render:{status:'ready'},latest_final_render:{status:'ready'}},activeProductionRender:null,busy:false,dirty:false,
 principal:{subject:r.context_before.body.actor_ref,display_name:'Explicit Node B-roll fixture',platform_role:null,
  workspace_roles:{[timeline.workspace_id]:'editor'},expires_at:'2100-01-01T00:00:00Z',human_write_enabled:true}};}
class Element{
 constructor(id){this.id=id;this.type='button';this.checked=false;this.disabled=false;this.value='';this.dataset={};this.children=[];this.attributes={};this.listeners={};this.textContent='';this.open=false;}
 setAttribute(k,v){this.attributes[k]=String(v);if(k.startsWith('data-'))this.dataset[k.slice(5).replace(/-([a-z])/g,(_m,c)=>c.toUpperCase())]=String(v);}
 append(...v){this.children.push(...v);}replaceChildren(...v){this.children=[...v];}
 addEventListener(k,fn){(this.listeners[k]??=[]).push(fn);}focus(){this.focused=true;}
 async fire(k,target=this){for(const fn of this.listeners[k]??[])await fn({target,currentTarget:this,preventDefault(){}});}
}
function harness({s=fixtureState(),memory=new Map(),handler,guardValues=null}={}){
 const ids=Object.fromEntries(['read','open-held','context','form','fields','items','replace','acknowledge','apply','reconcile','retry','discard','status','pending','workbench']
  .map(v=>['broll-timeline-'+v,new Element('broll-timeline-'+v)]));
 for(const name of ['replace','acknowledge']){ids['broll-timeline-'+name].type='checkbox';ids['broll-timeline-'+name].setAttribute('data-broll-timeline-setting','');}
 const all=e=>[e,...e.children.flatMap(all)],dom={createElement:tag=>new Element(tag),querySelectorAll:selector=>{
  if(selector.includes('#broll-timeline-items'))return all(ids['broll-timeline-items']).filter(e=>Object.hasOwn(e.dataset,'brollTimelineItem'));
  if(selector.includes('#broll-timeline-form'))return [...all(ids['broll-timeline-items']),ids['broll-timeline-replace'],ids['broll-timeline-acknowledge']]
   .filter(e=>Object.hasOwn(e.attributes,'data-broll-timeline-setting'));return[];}};
 let token='EXPLICIT_NODE_BROLL_PLACEMENT_TOKEN',committed=s.timeline.current_version===2,root,proofReads=0;
 const calls=[],messages=[],effects=[],savedParents=[],guards=[],peers={family:false,narration:false,words:false,audio:false,linked:false,manual:false};
 const peer=name=>({isBusy:()=>peers[name],isWorking:()=>peers[name],isPending:()=>peers[name],isDirty:()=>peers[name],sync(){}});
 const storage={getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v),
  compareAndRemoveItem:(k,v)=>{if(memory.get(k)!==v)return false;memory.delete(k);return true;}};
 const api=async(path,options={})=>{const c={path,method:options.method??'GET',body:options.body?JSON.parse(options.body):null,
  privateAdmission:options.brollTimelineAdmission};calls.push(c);let phase,value;
  if(c.method==='PUT'){phase='put';committed=true;value=clone(r.apply.body);}
  else if(path.endsWith('/versions')){phase='history';value=clone(r.history.body);}
  else{phase=committed?(++proofReads%2===1?'proof':'final'):'read';value=clone(committed?r.current.body:r.context_before.body);}
  return handler?handler(c,phase,value,{s,peers,storage,memory,setToken:v=>{token=v;}}):value;};
 const stable=new Function(segment('function sqlAudioStable(','\nfunction sqlAudioSourceValue(')+'\nreturn sqlAudioStable;')();
 const history=new Function(segment('function videoWordHistoryMatches(','\nasync function refreshVideoWordReceipt')+'\nreturn videoWordHistoryMatches;')();
 const args=['state','document','$','videoWordSessionStorage','sessionToken','sqlEditorState','activeAnalysis','variantFamilies','variantNarration',
  'videoWordReview','sqlAudioProcessing','sourceLinkedEditor','sourceLinkedHeld','manualReframeEditor','manualReframeHeld','productionWorkbenchDraft',
  'audioWorkbenchDraft','audioRole','sqlAudioStable','brollTimelineRead','brollTimelineSelection','initializeSqlBrollTimelineReview','videoWordHistoryMatches',
  'api','toast','syncBrollPlanPeers','stopPreviewPolling','stopProductionPolling','render','renderBrowser','Date'];
 const body=segment('let brollPlanController=null','\nlet manualReframeEditor')+'\n'
  +segment('// Reviewed B-roll placement Root integration.','\nensureAuthenticatedSession()')
  +'\nreturn {controller:brollTimelineController,brollPlanHeld,brollTimelineHeld,brollTimelineDirty,brollTimelineDraft,brollTimelineEditorState,brollTimelineSourceContext,'
  +'brollTimelineCanonicalContext,assertBrollTimelineOperation,brollTimelineApi,brollTimelineStorage,syncBrollTimelineForm,refreshBrollTimeline,runBrollTimelineAction,'
  +'admission:brollTimelineAdmission,formRead:()=>brollTimelineFormRead,setPreparation:v=>{brollPlanBusy=v;}};';
 const sync=()=>{root?.controller.sync();root?.syncBrollTimelineForm();};
 root=new Function(...args,body)(s,dom,selector=>ids[selector.slice(1)],()=>storage,()=>token,()=>({...s}),()=>s.analysis,
  peer('family'),peer('narration'),peer('words'),peer('audio'),peer('linked'),()=>peers.linked,peer('manual'),()=>peers.manual,
  ()=> 'saved-production',()=> 'saved-audio',audioRole,stable,brollTimelineRead,brollTimelineSelection,
  options=>initializeSqlBrollTimelineReview({...options,cryptoImpl:webcrypto,newRequestKey:()=>r.apply.request.request_key,
   onSaved:async(v,g)=>{savedParents.push(v.parent_timeline);guards.push(g);return options.onSaved(v,guardValues?guardValues[0]:g);}}),
  history,api,(...v)=>messages.push(v),sync,()=>effects.push('stop-preview'),()=>effects.push('stop-production'),()=>effects.push('render'),()=>effects.push('render-browser'),Date);
 const select=()=>dom.querySelectorAll('#broll-timeline-items [data-broll-timeline-item]').find(e=>e.dataset.brollTimelineItem===r.apply.request.item_ids[0]);
 return{...root,s,ids,calls,messages,effects,savedParents,guards,memory,storage,peers,select,setToken:v=>{token=v;},
  read:()=>ids['broll-timeline-read'].fire('click'),apply:()=>ids['broll-timeline-apply'].fire('click'),
  reconcile:()=>ids['broll-timeline-reconcile'].fire('click'),retry:()=>ids['broll-timeline-retry'].fire('click'),
  discard:()=>ids['broll-timeline-discard'].fire('click'),
  openHeld:()=>ids['broll-timeline-open-held'].fire('click'),
  fill:async()=>{select().checked=true;ids['broll-timeline-acknowledge'].checked=true;await ids['broll-timeline-form'].fire('change');}};
}
test('persistent accessible placement form remains outside transient browser; legacy apply action opens it with no write',()=>{
 assert.ok(html.indexOf('id="broll-timeline-workbench"')<html.indexOf('id="browser-content"'));assert.match(html,/id="broll-timeline-fields" disabled/);
 const action=segment("$('#browser-content').addEventListener('click',async event=>{","\n$('#browser-content').addEventListener('submit'");
 assert.match(action,/broll-timeline-workbench.*open=true/);assert.doesNotMatch(action,/apply-broll|await api|await loadProject/);
 assert.match(html,/bản preview và duyệt cũ sẽ hết hiệu lực/);
});
test('mount is unread and zero network; explicit read hydrates current plan without canonical change',async()=>{
 const h=harness(),before=clone(h.s);assert.equal(h.calls.length,0);assert.equal(h.ids['broll-timeline-fields'].disabled,true);
 await h.read();assert.deepEqual(h.calls.map(v=>v.method),['GET']);assert.deepEqual(h.s,before);
 assert.equal(h.ids['broll-timeline-fields'].disabled,false);assert.ok(h.select());assert.equal(h.select().checked,false);
});
test('actual shipped controller + Root proof saves exact one-version receipt and invalidates old review state',async()=>{
 const h=harness(),source=clone(h.s.assets),analysis=clone(h.s.analyses),plans=clone(h.s.mediaPlans);
 await h.read();await h.fill();await h.apply();
 assert.deepEqual(h.calls.map(v=>v.method),['GET','GET','PUT','GET','GET','GET']);assert.deepEqual(h.calls[2].body,r.apply.request);
 assert.equal(h.calls[2].privateAdmission,h.admission);assert.equal(h.memory.size,0);assert.equal(h.controller.isPending(),false);
 assert.deepEqual(h.s.timeline,r.current.body.timeline);assert.deepEqual(h.s.versions,r.history.body);
 assert.equal(h.s.preview.status,'stale');assert.equal(h.s.preview.valid_for_current_timeline,false);assert.equal(h.s.productionPackage.approval,null);
 assert.equal(h.s.productionPackage.latest_final_render,null);assert.equal(h.s.selectedClipId,null);assert.deepEqual(h.s.undoStack,[]);assert.deepEqual(h.s.redoStack,[]);
 assert.equal(h.s.playhead,h.s.timeline.snapshot.duration_seconds);assert.deepEqual(h.effects,['stop-preview','stop-production','render']);
 assert.deepEqual(h.s.assets,source);assert.deepEqual(h.s.analyses,analysis);assert.deepEqual(h.s.mediaPlans,plans);assert.equal(h.formRead(),null);
 assert.throws(()=>h.guards[0]());
});
test('selection/acknowledgement cannot bypass explicit read or resolved items; unsent discard restores clean choices',async()=>{
 const h=harness();await h.apply();assert.equal(h.calls.length,0);await h.read();await h.apply();assert.equal(h.calls.length,1);
 h.select().checked=true;await h.apply();assert.equal(h.calls.length,1);h.syncBrollTimelineForm();assert.equal(h.brollTimelineHeld(),true);
 await h.discard();assert.equal(h.select().checked,false);assert.equal(h.brollTimelineDirty(),false);assert.equal(h.calls.length,1);
});
test('cold current-result replay uses real history parent snapshot when full parent TimelineRead is absent',async()=>{
 const memory=new Map(),lost=harness({memory,handler:(_c,p,v)=>{if(p==='put')throw Error('lost committed response');return v;}});
 await lost.read();await lost.fill();await lost.apply();assert.equal(memory.size,1);lost.controller.dispose();
 const s=fixtureState();s.timeline=clone(r.current.body.timeline);s.versions=clone(r.history.body);
 const cold=harness({s,memory});assert.equal(cold.calls.length,0);assert.equal(cold.controller.isPending(),true);
 await cold.read();await cold.reconcile();assert.equal(cold.memory.size,0);assert.equal(cold.savedParents.at(-1),null);
 assert.deepEqual(cold.s.timeline,r.current.body.timeline);assert.equal(cold.s.productionPackage.approval,null);
 assert.equal(cold.calls.filter(c=>c.method==='PUT').length,0);assert.deepEqual(cold.effects,['stop-preview','stop-production','render']);
});
for(const phase of ['proof','history','final'])for(const drift of ['actor','token','expiry','role','write','analysis','asset','timeline','plan','form','peer','preparation','raw'])
 test('Root placement '+drift+' drift during '+phase+' preserves UNKNOWN and never adopts',async()=>{
  let h,external;h=harness({handler:(c,p,v,t)=>{if(p===phase){
   if(drift==='actor')t.s.principal.subject='usr:foreign';if(drift==='token')t.setToken('different-node-session');
   if(drift==='expiry')t.s.principal.expires_at='2000-01-01T00:00:00Z';
   if(drift==='role')t.s.principal.workspace_roles={[t.s.workspaceId]:'viewer'};if(drift==='write')t.s.principal.human_write_enabled=false;
   if(drift==='analysis')t.s.analysis.fingerprint='f'.repeat(64);if(drift==='asset')t.s.assets[0].provenance.license='changed';
   if(drift==='timeline')t.s.timeline.current_version++;if(drift==='plan')t.s.selectedBrollPlanId='mpl_other-plan';
   if(drift==='form')h.ids['broll-timeline-replace'].checked=true;if(drift==='peer')t.peers.audio=true;if(drift==='preparation')h.setPreparation(true);
   if(drift==='raw')t.memory.set([...t.memory.keys()][0],'FOREIGN_DURABLE_REQUEST_B');external=clone(t.s);
  }return v;}});
  await h.read();await h.fill();const before=clone(h.s);await h.apply();assert.ok(external);
  assert.deepEqual(h.s.timeline,external.timeline);assert.equal(h.memory.size,1);assert.deepEqual(h.effects,[]);
  assert.deepEqual(h.s.preview,before.preview);assert.deepEqual(h.s.productionPackage,before.productionPackage);
  assert.equal(h.calls.filter(c=>c.method==='PUT').length,1);if(drift==='raw')assert.equal([...h.memory.values()][0],'FOREIGN_DURABLE_REQUEST_B');
 });
for(const field of ['parent-id','head-actor','head-receipt','head-snapshot','parent-source-audio'])test('contradictory '+field+' history cannot certify B-roll adoption',async()=>{
 const h=harness({handler:(_c,p,v)=>{if(p==='history'){
  const parent=v.find(x=>x.version===1),head=v.find(x=>x.version===2);
  if(field==='parent-id')parent.timeline_version_id='foreign-parent';if(field==='head-actor')head.actor_ref='foreign-actor';
  if(field==='head-receipt')head.mutation.receipt.request_key='foreign-history-key';if(field==='head-snapshot')head.snapshot.tracks[0].clips[0].volume=.4;
  if(field==='parent-source-audio')parent.snapshot.tracks.find(t=>t.kind==='original_audio').clips[0].volume=.5;
 }return v;}});await h.read();await h.fill();const before=clone(h.s);await h.apply();
 assert.deepEqual(h.s.timeline,before.timeline);assert.deepEqual(h.effects,[]);assert.equal(h.memory.size,1);
});
test('Root requires a synchronous literal-true private guard; missing/false/throw/Promise cannot reach proof GET',async()=>{
 for(const value of [undefined,()=>false,()=>{throw Error('closed');},()=>Promise.resolve(true)]){
  const h=harness({guardValues:[value]});await h.read();await h.fill();await h.apply();
  assert.deepEqual(h.calls.map(c=>c.method),['GET','GET','PUT']);assert.deepEqual(h.effects,[]);assert.equal(h.memory.size,1);assert.throws(()=>h.guards[0]());
 }
});
test('native final storage getter changing raw, selection, token or peer blocks first canonical write',async()=>{
 for(const drift of ['raw','selection','token','peer']){let armed=false,gets=0;
  const h=harness({handler:(_c,p,v)=>{if(p==='final')armed=true;return v;}}),get=h.storage.getItem;
  h.storage.getItem=key=>{const raw=get(key);if(key.startsWith('vf-sql-broll-timeline-pending-v1:')&&armed&&++gets===1){if(drift==='raw')h.memory.set(key,'FOREIGN_FINAL_RAW');
   if(drift==='selection')h.s.selectedBrollPlanId='mpl_newer-selection';if(drift==='token')h.setToken('late-new-session');if(drift==='peer')h.peers.manual=true;}return raw;};
  await h.read();await h.fill();const before=clone(h.s.timeline);await h.apply();assert.ok(armed);assert.ok(gets>=1);
  assert.deepEqual(h.s.timeline,before);assert.deepEqual(h.effects,[]);assert.equal(h.memory.size,1);
 }
});
test('cold full-parent-absent history still protects original audio and cannot clear UNKNOWN',async()=>{
 const memory=new Map(),lost=harness({memory,handler:(_c,p,v)=>{if(p==='put')throw Error('lost');return v;}});
 await lost.read();await lost.fill();await lost.apply();lost.controller.dispose();
 const s=fixtureState();s.timeline=clone(r.current.body.timeline);s.versions=clone(r.history.body);
 const cold=harness({s,memory,handler:(_c,p,v)=>{if(p==='history')v.find(x=>x.version===1).snapshot.tracks.find(t=>t.kind==='original_audio').clips[0].volume=.4;return v;}});
 await cold.read();await cold.reconcile();assert.equal(cold.savedParents.at(-1),null);assert.equal(memory.size,1);assert.deepEqual(cold.effects,[]);
 assert.equal(cold.s.productionPackage.approval.status,'approved');
});
test('explicit held-plan routing is read-only, retains raw and permits cold recovery when default plan differs',async()=>{
 const original=fixtureState(),other=clone(capture.plan);other.media_plan_id='mpl_another-existing-plan';original.mediaPlans=[other,...original.mediaPlans];
 const memory=new Map(),lost=harness({s:original,memory,handler:(_c,p,v)=>{if(p==='put')throw Error('lost');return v;}});
 await lost.read();await lost.fill();await lost.apply();const raw=[...memory.values()][0];lost.controller.dispose();
 const s=fixtureState();s.mediaPlans=[other,...s.mediaPlans];s.selectedBrollPlanId=other.media_plan_id;s.timeline=clone(r.current.body.timeline);s.versions=clone(r.history.body);
 const cold=harness({s,memory});assert.equal(cold.ids['broll-timeline-open-held'].disabled,false);await cold.openHeld();
 assert.equal(cold.calls.length,0);assert.equal(cold.s.selectedBrollPlanId,capture.plan.media_plan_id);assert.equal([...memory.values()][0],raw);
 await cold.read();await cold.reconcile();assert.equal(memory.size,0);assert.deepEqual(cold.s.timeline,r.current.body.timeline);
});
test('malformed or foreign held-plan hint cannot retarget source or clear durable bytes',async()=>{
 for(const raw of ['bad-json',JSON.stringify({schema_version:'sql-broll-timeline-pending.v1',workspace_id:'foreign'})]){
  const s=fixtureState(),key='vf-sql-broll-timeline-pending-v1:'+JSON.stringify([s.workspaceId,s.projectId,s.principal.subject]),memory=new Map([[key,raw]]);
  const h=harness({s,memory}),before=clone(h.s);await h.openHeld();assert.equal(h.calls.length,0);assert.deepEqual(h.s,before);assert.equal(memory.get(key),raw);
 }
});
test('peer writer/preparation holds are enforced while the placement getter excludes its own dirty/pending',async()=>{
 for(const name of ['family','narration','words','audio','linked','manual','preparation']){
  const h=harness();await h.read();await h.fill();if(name==='preparation')h.setPreparation(true);else h.peers[name]=true;await h.apply();
  assert.equal(h.calls.filter(c=>c.method==='PUT').length,0);assert.equal(h.memory.size,0);
 }
 const h=harness();await h.read();await h.fill();assert.equal(h.brollTimelineDirty(),true);assert.equal(h.brollTimelineHeld(),true);
 assert.equal(h.brollTimelineEditorState().dirty,false);
});
test('private API admits only exact owned review route/body and keeps public generic writes fenced',async()=>{
 const h=harness();await assert.rejects(h.brollTimelineApi(r.apply.path,{method:'PUT',body:JSON.stringify(r.apply.request)}));assert.equal(h.calls.length,0);
 await h.read();await h.fill();assert.equal(h.brollPlanHeld(),true);
 const start=code.indexOf('async function api('),source=code.slice(start,code.indexOf('\n}\n',start)+3);const fetches=[];
 const symbols=Array.from({length:5},()=>Symbol('other-private-controller'));
 class ApiError extends Error{}
 const make=new Function('brollPlanHeld','manualReframeHeld','sourceLinkedHeld','audioProcessingHeld','videoWordsHeld',
  'brollPlanAdmission','manualReframeAdmission','sourceLinkedAdmission','audioProcessingAdmission','videoWordAdmission','brollTimelineAdmission',
  'authenticatedFetch','ApiError',source+'\nreturn api;');
 const api=make(h.brollPlanHeld,()=>false,()=>false,()=>false,()=>false,...symbols,h.admission,
  async(path,options)=>{fetches.push({path,options});return{ok:true,status:200,json:async()=>({ok:true})};},ApiError);
 await assert.rejects(api('/api/v1/projects/other',{method:'POST'}));
 await assert.rejects(api(r.apply.path,{method:'PUT',brollTimelineAdmission:Symbol('foreign'),body:'{}'}));assert.equal(fetches.length,0);
 await api(r.apply.path,{method:'PUT',body:JSON.stringify(r.apply.request),brollTimelineAdmission:h.admission});
 assert.equal(fetches.length,1);assert.equal(Object.hasOwn(fetches[0].options,'brollTimelineAdmission'),false);
});
test('actual project/search/plan event guards preserve current view while placement has an unsent draft',async()=>{
 const h=harness();await h.read();await h.fill();const before=clone(h.s);h.s.query='kept search';
 const project=new Element('project-select'),search=new Element('browser-search'),notices=[];let rendered=0;
 const dollar=selector=>selector==='#project-select'?project:search;
 const projectCode=segment('$("#project-select").addEventListener("change",','\n$("#reload-button")');
 new Function('$','state','brollPlanHeld','toast',projectCode)(dollar,h.s,h.brollPlanHeld,(...v)=>notices.push(v));
 project.value='prj_foreign_target';await project.fire('change');assert.equal(project.value,h.s.projectId);
 const searchCode=segment('$("#browser-search").addEventListener("input",','\n$(\'#browser-content\').addEventListener(\'change\'');
 new Function('$','state','brollTimelineHeld','toast','renderBrowser',searchCode)(dollar,h.s,h.brollTimelineHeld,(...v)=>notices.push(v),()=>rendered++);
 search.value='changed query';await search.fire('input');assert.equal(search.value,'kept search');assert.equal(h.s.query,'kept search');
 const start=code.indexOf("  if(event.target.matches('[data-broll-plan]'))"),end=code.indexOf('\n});',start);
 const plan={value:'mpl_wrong-plan',matches:()=>true};
 new Function('event','state','brollTimelineHeld','toast','clearBrollTimelineForm','renderBrowser',code.slice(start,end))(
  {target:plan},h.s,h.brollTimelineHeld,(...v)=>notices.push(v),()=>assert.fail('must preserve form'),()=>rendered++);
 assert.equal(plan.value,before.selectedBrollPlanId);assert.equal(h.s.selectedBrollPlanId,before.selectedBrollPlanId);
 assert.equal(rendered,0);assert.equal(h.calls.filter(c=>c.method==='PUT').length,0);assert.equal(notices.length,3);
});
test('read-only role may inspect while forged placement gesture cannot write',async()=>{
 const s=fixtureState();s.principal.workspace_roles={[s.workspaceId]:'viewer'};const h=harness({s});await h.read();
 assert.equal(h.calls.length,1);assert.equal(h.ids['broll-timeline-fields'].disabled,true);
 await h.fill();await h.apply();assert.equal(h.calls.length,1);assert.equal(h.memory.size,0);
});
test('forged unresolved checkbox never posts; explicit replace forwards true and rejects mismatched receipt',async()=>{
 const h=harness();await h.read();const items=h.ids['broll-timeline-items'].children;
 const unavailable=items.map(label=>label.children[0]).find(input=>input.disabled);assert.ok(unavailable);
 unavailable.checked=true;h.ids['broll-timeline-acknowledge'].checked=true;await h.apply();assert.equal(h.calls.length,1);assert.equal(h.memory.size,0);
 await h.discard();await h.fill();h.ids['broll-timeline-replace'].checked=true;await h.apply();
 const put=h.calls.find(c=>c.method==='PUT');assert.equal(put.body.replace_plan_clips,true);assert.equal(h.memory.size,1);assert.deepEqual(h.effects,[]);
});
test('UI unchanged-parent reconciliation permits only explicit acknowledged retry with exact original body/key',async()=>{
 let puts=0;const h=harness({handler:(c,_p,v)=>{if(c.method==='PUT'&&++puts===1)throw Error('not delivered');
  if(c.method==='GET'&&puts===1)return clone(r.context_before.body);return v;}});
 await h.read();await h.fill();await h.apply();assert.equal(h.memory.size,1);await h.reconcile();assert.equal(h.controller.state().canRetry,true);
 assert.equal(h.ids['broll-timeline-retry'].disabled,false);h.ids['broll-timeline-acknowledge'].checked=false;await h.retry();assert.equal(puts,1);
 h.ids['broll-timeline-acknowledge'].checked=true;await h.retry();assert.equal(puts,2);
 assert.deepEqual(h.calls.filter(c=>c.method==='PUT').map(c=>c.body),[r.apply.request,r.apply.request]);
 assert.equal(h.memory.size,0);assert.deepEqual(h.s.timeline,r.current.body.timeline);
});
test('explicit read may restore submitted held choices after returning to exact original credential, without discarding UNKNOWN',async()=>{
 const h=harness({handler:(_c,p,v)=>{if(p==='put')throw Error('lost committed reply');return v;}});
 await h.read();await h.fill();await h.apply();assert.equal(h.memory.size,1);assert.equal(h.brollTimelineDirty(),true);
 h.setToken('temporary-other-credential');h.controller.sync();h.setToken('EXPLICIT_NODE_BROLL_PLACEMENT_TOKEN');h.controller.sync();h.syncBrollTimelineForm();
 assert.equal(h.controller.state().pending,null);assert.equal(h.ids['broll-timeline-read'].disabled,false);
 await h.read();assert.ok(h.controller.state().pending);assert.equal(h.memory.size,1);assert.equal(h.brollTimelineDirty(),false);
 await h.reconcile();assert.equal(h.memory.size,0);assert.equal(h.calls.filter(c=>c.method==='PUT').length,1);
});
