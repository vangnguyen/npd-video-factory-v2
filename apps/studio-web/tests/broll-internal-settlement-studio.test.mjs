import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
import {audioRole,audioByteHash} from '../uploaded-audio-review.mjs';
import {compatibleBrollPlans} from '../broll-planner.mjs';
import {initializeSqlBrollInternalResolution,validateBrollInternalContext} from '../sql-broll-internal-resolution.mjs';
import {initializeSqlBrollInternalSettlement,validateBrollInternalSettlement} from '../sql-broll-internal-settlement.mjs';
const wrapper=JSON.parse(readFileSync(new URL('./fixtures/broll-internal-settlement-studio.json',import.meta.url),'utf8'));
const clone=structuredClone,scenario=wrapper.scenarios[0].capture;
const raw=(c,name)=>clone(c.records.find(r=>r.name===name).response.json);
const code=readFileSync(new URL('../studio.js',import.meta.url),'utf8').replaceAll('\r\n','\n');
function segment(a,b){const start=code.indexOf(a),end=code.indexOf(b,start);assert.ok(start>=0&&end>start);return code.slice(start,end);}
class Element{constructor(id){this.id=id;this.value='';this.checked=false;this.disabled=false;this.children=[];this.listeners={};this.type='button';this.textContent='';}
 append(...v){this.children.push(...v);}replaceChildren(...v){this.children=[...v];}addEventListener(k,fn){(this.listeners[k]??=[]).push(fn);}
 focus(){this.focused=true;}async fire(k){for(const fn of this.listeners[k]??[])await fn({target:this,currentTarget:this,preventDefault(){}});}}
function rootHarness({capture=scenario,handler,replaceGuard=false,badGuard,store={},afterProof}={}){
 const s=clone(capture.state_projection_current);Object.assign(s,{selectedBrollPlanId:s.mediaPlanId,analyses:[s.analysis],versions:[{version:1}],
  preview:{status:'ready'},productionPackage:{approval:{status:'approved'}},activeProductionRender:null,selectedClipId:null,playhead:1,undoStack:[],redoStack:[],query:'',panelTab:'broll'});
 const ids=Object.fromEntries([...['inspect','acknowledge','settle','read','reset-ack','context','status','receipt','form','workbench'].map(n=>'broll-terminal-'+n),
  ...['plan','item','read','open-held','context','form','fields','asset','acknowledge','admit','observe','retry','discard','status','result','pending','workbench'].map(n=>'broll-internal-'+n),
  'browser-search'].map(n=>[n,new Element(n)]));ids['broll-internal-acknowledge'].type='checkbox';ids['broll-terminal-acknowledge'].type='checkbox';
 const dom={createElement:t=>new Element(t),querySelectorAll:q=>q.includes('broll-internal-form')?[ids['broll-internal-asset'],ids['broll-internal-acknowledge']]:[]};
 const key='vf-sql-broll-internal-pending-v1:'+JSON.stringify([s.workspaceId,s.projectId,s.principal.subject]),memory=new Map([[key,capture.request.intent_json]]);
 let token='vf1.explicit-terminal-Root-renewed',clock=capture.clock_ms,settled=false,audits=0,root,getHook=null;
 const calls=[],guards=[],messages=[],peers={preparation:false,placement:false,manual:false,linked:false,words:false,audio:false,family:false,narration:false};
 const peer=n=>({isBusy:()=>peers[n],isWorking:()=>peers[n],isPending:()=>peers[n],isDirty:()=>peers[n],sync(){}});
 const storage={getItem(k){const v=memory.get(k)??null;getHook?.(k,v);return v;},compareAndRemoveItem(k,v){if(store.cas)return store.cas(k,v,{memory,s});
  if(memory.get(k)!==v)return false;memory.delete(k);return true;},setItem(k,v){memory.set(k,v);}};
 const api=async(path,options={})=>{const c={path,method:options.method??'GET',body:options.body?JSON.parse(options.body):null,admission:options.brollTerminalAdmission};calls.push(c);
  let phase,value;if(path==='/api/v1/auth/session'){phase='session';value=raw(capture,'current-session');}
  else if(path.endsWith('/inspect')){phase='inspect';value=raw(capture,settled?'read-exact-audit':'inspect-terminal');}
  else if(path.endsWith('/settle')){phase='settle';settled=true;value=raw(capture,'settle-terminal');}
  else{phase=['audit','root-proof','final'][audits++%3];value=raw(capture,'read-exact-audit');}
  return handler?handler(c,phase,value,{s,memory,peers,setToken:v=>{token=v;}}):value;};
 const stable=new Function(segment('function sqlAudioStable(','\nfunction sqlAudioSourceValue(')+'\nreturn sqlAudioStable;')();
 const args=['state','document','$','videoWordSessionStorage','sessionToken','sqlEditorState','activeAnalysis','variantFamilies','variantNarration','videoWordReview',
  'sqlAudioProcessing','sourceLinkedEditor','sourceLinkedHeld','manualReframeEditor','manualReframeHeld','brollPreparationHeld','brollTimelineHeld',
  'productionWorkbenchDraft','audioWorkbenchDraft','audioRole','audioByteHash','sqlAudioStable','compatibleBrollPlans','validateBrollInternalContext',
  'initializeSqlBrollInternalResolution','initializeSqlBrollInternalSettlement','validateBrollInternalSettlement','api','toast','syncBrollPlanPeers','clearBrollTimelineForm','renderBrowser','Date'];
 const body=segment('let brollInternalController=null','\nlet manualReframeEditor')+'\n'
  +segment('// Reviewed internal B-roll resolution Root integration.','\nensureAuthenticatedSession()')
  +'\nreturn {controller:brollTerminalController,oldController:()=>brollInternalController,brollTerminalHeld,brollTerminalEditorState,brollTerminalSourceContext,'
  +'brollTerminalDraft,brollInternalEditorState,brollTerminalApi,verifyBrollTerminalReceipt,rebindBrollInternalAfterSettlement,runBrollTerminalAction,syncBrollTerminalForm,admission:brollTerminalAdmission};';
 const sync=()=>{if(root){root.controller.sync();root.syncBrollTerminalForm();}};
 root=new Function(...args,body)(s,dom,q=>ids[q.slice(1)],()=>storage,()=>token,()=>({...s}),()=>s.analysis,peer('family'),peer('narration'),peer('words'),peer('audio'),
  peer('linked'),()=>peers.linked,peer('manual'),()=>peers.manual,()=>peers.preparation,()=>peers.placement,()=> 'saved-production',()=> 'saved-audio',audioRole,
  bytes=>audioByteHash(bytes,webcrypto),stable,compatibleBrollPlans,validateBrollInternalContext,initializeSqlBrollInternalResolution,
  options=>initializeSqlBrollInternalSettlement({...options,cryptoImpl:webcrypto,clock:()=>clock,onSettled:async(v,g)=>{guards.push(g);const result=await options.onSettled(v,replaceGuard?badGuard:g);
    afterProof?.({s,memory,peers,setToken:v=>{token=v;}});return result;}}),
  validateBrollInternalSettlement,api,(...v)=>messages.push(v),sync,()=>{},()=>{},class extends Date{static now(){return clock;}});
 return {...root,s,memory,key,calls,guards,ids,messages,peers,setToken:v=>{token=v;},setGetHook:v=>{getHook=v;},
  inspect:()=>ids['broll-terminal-inspect'].fire('click'),settle:()=>ids['broll-terminal-settle'].fire('click'),read:()=>ids['broll-terminal-read'].fire('click'),
  ack:async()=>{ids['broll-terminal-acknowledge'].checked=true;await ids['broll-terminal-form'].fire('change');}};
}
function moduleHarness({capture=scenario,handler,onSettled,onReleased,memory,store={}}={}){
 const s=clone(capture.state_projection_current);s.settlementSource={selected_plan:s.mediaPlanId,workbench:'saved'};s.settlementDraft={acknowledged:false};
 const key='vf-sql-broll-internal-pending-v1:'+JSON.stringify([s.workspaceId,s.projectId,s.principal.subject]);
 memory??=new Map([[key,capture.request.intent_json]]);let token='vf1.explicit-renewed-terminal-client',clock=capture.clock_ms,settled=false,reset=0,gets=0;
 const calls=[],guards=[],messages=[];
 const storage={getItem(k){gets++;const v=memory.get(k)??null;store.get?.(k,v,{s,memory});return v;},compareAndRemoveItem(k,v){
   if(store.cas)return store.cas(k,v,{s,memory});if(memory.get(k)!==v)return false;memory.delete(k);return true;}};
 const api=async(path,options={})=>{const call={path,method:options.method??'GET',body:options.body?JSON.parse(options.body):null};calls.push(call);let phase,result;
  if(path==='/api/v1/auth/session'){phase='session';result=raw(capture,'current-session');}
  else if(path.endsWith('/inspect')){phase='inspect';result=raw(capture,settled?'read-exact-audit':'inspect-terminal');}
  else if(path.endsWith('/settle')){phase='settle';settled=true;result=raw(capture,'settle-terminal');}
  else{phase='audit';result=raw(capture,'read-exact-audit');}
  return handler?handler(call,phase,result,{s,memory,setToken:v=>{token=v;},setClock:v=>{clock=v;}}):result;};
 const controller=initializeSqlBrollInternalSettlement({api,getState:()=>s,getSessionToken:()=>token,storage,cryptoImpl:webcrypto,clock:()=>clock,
  onInspected:async(v,g)=>{assert.equal(g(),true);guards.push(g);return true;},onSettled:async(v,g)=>{guards.push(g);return onSettled?onSettled(v,g,{s,memory}):g();},
  onReleased:(v,g)=>{guards.push(g);if(onReleased)return onReleased(v,g,{s,memory});g();reset++;return true;},onStatus:v=>messages.push(v)});
 return {controller,s,key,memory,calls,guards,messages,resetCount:()=>reset,getCount:()=>gets,setToken:v=>{token=v;},setClock:v=>{clock=v;},storage};
}
test('new terminal controller constructor has zero network and preserves raw held bytes',()=>{
 const h=moduleHarness();assert.deepEqual(h.calls,[]);assert.equal(h.controller.isHeld(),true);assert.equal(h.memory.size,1);
 assert.equal(wrapper.scenarios.length,2);for(const x of wrapper.scenarios)assert.equal(x.capture.records.length,7);
});
for(const item of wrapper.scenarios)test('explicit '+item.name+' inspect/settle/read releases exact held record without data adoption',async()=>{
 const h=moduleHarness({capture:item.capture}),before=clone(h.s);await h.controller.inspect();assert.equal(h.memory.size,1);assert.equal(h.resetCount(),0);
 assert.equal(h.calls.filter(c=>c.path.endsWith('/settle')).length,0);h.s.settlementDraft.acknowledged=true;
 const result=await h.controller.settle(true);assert.deepEqual(result,raw(item.capture,'settle-terminal'));assert.equal(h.memory.size,0);assert.equal(h.resetCount(),1);
 assert.equal(h.controller.state().released,true);assert.equal(h.controller.isHeld(),false);before.settlementDraft.acknowledged=true;assert.deepEqual(h.s,before);
 assert.equal(h.calls.filter(c=>c.path.endsWith('/settle')).length,1);for(const g of h.guards)assert.throws(g,/kết thúc/);
});
test('lost settlement response requires explicit inspect then exact immutable GET, no second settlement POST',async()=>{
 const h=moduleHarness({handler:(c,p,v)=>{if(p==='settle')throw Error('owned lost response');return v;}});await h.controller.inspect();
 await assert.rejects(h.controller.settle(true),/owned lost/);assert.equal(h.memory.size,1);assert.equal(h.resetCount(),0);
 await assert.rejects(h.controller.settle(true),/Kiểm tra/);assert.equal(h.calls.filter(c=>c.path.endsWith('/settle')).length,1);
 const restored=await h.controller.inspect();assert.equal(restored.state,'settled');assert.equal(h.memory.size,1);
 await h.controller.readSettlement(true);assert.equal(h.memory.size,0);assert.equal(h.resetCount(),1);assert.equal(h.calls.filter(c=>c.path.endsWith('/settle')).length,1);
});
test('queued microtask after proof helper returns cannot remove a foreign pending record or reset old controller',async()=>{
 const h=moduleHarness({onSettled:async(v,g,{memory})=>{g();queueMicrotask(()=>memory.set(h.key,'foreign record B'));return true;}});
 await h.controller.inspect();await assert.rejects(h.controller.settle(true));assert.equal(h.memory.get(h.key),'foreign record B');assert.equal(h.resetCount(),0);
});
for(const [name,mutate]of Object.entries({token:h=>h.setToken('vf1.foreign-terminal-token'),expiry:h=>h.setClock(scenario.clock_ms+864000000),
 source:h=>h.s.assets[0].storage_provider='unexpected',peer:h=>h.s.dirty=true,draft:h=>h.s.settlementDraft.extra='changed'}))
 test('terminal ownership rejects '+name+' drift during immutable audit',async()=>{
  let h;h=moduleHarness({handler:(c,p,v)=>{if(p==='audit')mutate(h);return v;}});await h.controller.inspect();await assert.rejects(h.controller.settle(true));
  assert.equal(h.memory.size,1);assert.equal(h.resetCount(),0);
 });
test('missing acknowledgement, absent or receipt-null original never settles or infers latest job',async()=>{
 const h=moduleHarness();await h.controller.inspect();await assert.rejects(h.controller.settle(false));assert.equal(h.calls.filter(c=>c.path.endsWith('/settle')).length,0);
 for(const rawText of ['broken',JSON.stringify({...scenario.held_intent,receipt:null})]){const x=moduleHarness();x.memory.set(x.key,rawText);
  await assert.rejects(x.controller.inspect());assert.deepEqual(x.calls,[]);assert.equal(x.memory.get(x.key),rawText);}
});
test('failed exact compare-and-remove never resets controller or reports a local release',async()=>{
 const h=moduleHarness({store:{cas:()=>false}});await h.controller.inspect();await assert.rejects(h.controller.settle(true));assert.equal(h.memory.size,1);
 assert.equal(h.resetCount(),0);assert.equal(h.controller.state().released,false);
});
test('reset callback is synchronous literaltrue and failure after verified CAS remains explicitly blocked',async()=>{
 const h=moduleHarness({onReleased:()=>Promise.resolve(true)});await h.controller.inspect();await assert.rejects(h.controller.settle(true));
 assert.equal(h.memory.size,0);assert.equal(h.controller.state().released,false);assert.equal(h.controller.state().rebind_blocked,true);assert.equal(h.controller.isHeld(),true);
});
test('typed settlement cannot authorize active job, output adoption, foreign job or safety flag drift',()=>{
 const held=scenario.held_intent,hash=scenario.request.intent_sha256;
 for(const mutate of [v=>v.job.status='running',v=>v.output={},v=>v.can_adopt=true,v=>v.job.resolution_job_id='mrj_foreign_job',
  v=>v.provider_calls=1,v=>v.owner_approval_inferred=true,v=>v.settlement.current_output_adopted=true]){
  const value=raw(scenario,'settle-terminal');mutate(value);assert.throws(()=>validateBrollInternalSettlement(value,held,hash));}
});
for(const item of wrapper.scenarios)test('actual terminal controller→Root '+item.name+' removes only exact raw and rebinds old controller without data mutation',async()=>{
 const h=rootHarness({capture:item.capture}),before=clone(h.s),old=h.oldController();assert.equal(h.calls.length,0);assert.equal(old.isPending(),true);
 await h.inspect();assert.equal(h.memory.size,1);assert.equal(h.oldController(),old);await h.ack();await h.settle();
 assert.equal(h.memory.size,0,JSON.stringify(h.messages));assert.notEqual(h.oldController(),old);assert.equal(h.oldController().isPending(),false);
 assert.deepEqual(h.s,before);assert.equal(h.controller.state().released,true);assert.equal(h.guards.length,1);assert.throws(h.guards[0],/kết thúc/);
 assert.equal(h.calls.filter(c=>c.path.endsWith('/settle')).length,1);assert.equal(h.calls.filter(c=>c.path.includes('/settlements/')).length,3);
});
test('Root lost-settlement acknowledgement recovers only through explicit inspect and immutable receipt read',async()=>{
 const h=rootHarness({handler:(c,p,v)=>{if(p==='settle')throw Error('owned lost Root acknowledgement');return v;}}),old=h.oldController();
 await h.inspect();await h.ack();await h.settle();assert.equal(h.memory.size,1);assert.equal(h.oldController(),old);
 await h.inspect();assert.equal(h.controller.state().view.state,'settled');await h.read();assert.equal(h.memory.size,0);assert.notEqual(h.oldController(),old);
 assert.equal(h.calls.filter(c=>c.path.endsWith('/settle')).length,1);
});
const rootDrift={token:h=>h.setToken('vf1.foreign-terminal-Root-token'),expiry:h=>h.s.principal.expires_at='2000-01-01T00:00:00Z',
 source:h=>h.s.assets[0].storage_provider='changed-during-proof',form:h=>h.ids['broll-terminal-acknowledge'].checked=false,
 peer:h=>h.peers.audio=true,plan:h=>h.s.mediaPlans[0].fingerprint='f'.repeat(64),raw:h=>h.memory.set(h.key,'foreign pending B'),
 authority:h=>h.s.principal.human_write_enabled=false};
for(const phase of ['audit','root-proof','final'])for(const [name,mutate]of Object.entries(rootDrift))
 test('Root terminal '+name+' drift during '+phase+' never clears old raw or rebinds controller',async()=>{
  let h;h=rootHarness({handler:(c,p,v)=>{if(p===phase)mutate(h);return v;}});const old=h.oldController();await h.inspect();await h.ack();await h.settle();
  assert.equal(h.memory.size,1);assert.equal(h.oldController(),old);assert.equal(h.controller.state().released,false);
  if(name==='raw')assert.equal(h.memory.get(h.key),'foreign pending B');
 });
for(const [name,badGuard]of [['missing',undefined],['false',()=>false],['throw',()=>{throw Error('owned private guard failure');}],['Promise',()=>Promise.resolve(true)]])
 test('Root terminal private proof requires synchronous literaltrue: '+name,async()=>{
  const h=rootHarness({replaceGuard:true,badGuard}),old=h.oldController();await h.inspect();await h.ack();await h.settle();
  assert.equal(h.memory.size,1);assert.equal(h.oldController(),old);assert.equal(h.calls.filter(c=>c.path.includes('/settlements/')).length,1);
 });
test('actual Root proof helper return followed queued foreign record is fenced before trusted CAS',async()=>{
 let h;h=rootHarness({afterProof:({memory})=>queueMicrotask(()=>memory.set(h.key,'foreign after proof helper'))});
 const old=h.oldController();await h.inspect();await h.ack();await h.settle();assert.equal(h.memory.get(h.key),'foreign after proof helper');assert.equal(h.oldController(),old);
});
for(const name of ['source','token','raw'])test('Root final native getter '+name+' drift preserves raw custody and old controller',async()=>{
 let h;h=rootHarness({handler:(c,p,v)=>{if(p==='final')h.setGetHook(()=>{h.setGetHook(null);rootDrift[name](h);});return v;}});
 const old=h.oldController();await h.inspect();await h.ack();await h.settle();assert.equal(h.memory.size,1);assert.equal(h.oldController(),old);
});
test('terminal holds block old internal writer while its own getter excludes expected pending/ack and includes peers',async()=>{
 const h=rootHarness();await h.inspect();await h.ack();assert.equal(h.brollTerminalHeld(),true);assert.equal(h.brollInternalEditorState().dirty,true);
 assert.equal(h.brollTerminalEditorState().dirty,false);assert.equal(h.brollTerminalEditorState().busy,false);
 for(const key of Object.keys(h.peers)){h.peers[key]=true;assert.equal(h.brollTerminalEditorState().busy||h.brollTerminalEditorState().dirty,true,key);h.peers[key]=false;}
 const before=h.memory.get(h.key);await h.ids['broll-terminal-reset-ack'].fire('click');assert.equal(h.memory.get(h.key),before);assert.equal(h.ids['broll-terminal-acknowledge'].checked,false);
});
test('ordinary internal pending and inspection without acknowledgement do not self-block the existing internal writer',async()=>{
 const h=rootHarness();assert.equal(h.oldController().isPending(),true);assert.equal(h.brollTerminalHeld(),false);assert.equal(h.brollInternalEditorState().dirty,false);
 await h.inspect();assert.equal(h.brollTerminalHeld(),false);assert.equal(h.brollInternalEditorState().dirty,false);assert.equal(h.memory.size,1);
 await h.ack();assert.equal(h.brollInternalEditorState().dirty,true);await h.ids['broll-terminal-reset-ack'].fire('click');assert.equal(h.brollInternalEditorState().dirty,false);
 assert.equal(h.memory.size,1);assert.equal(h.calls.filter(c=>c.path.endsWith('/settle')).length,0);
});
test('actual generic API strips only private terminal admission and fences all unrelated writes',async()=>{
 const h=rootHarness();await h.inspect();await h.ack();const start=code.indexOf('async function api('),source=code.slice(start,code.indexOf('\n}\n',start)+3),fetches=[];
 const api=new Function('brollPlanHeld','manualReframeHeld','sourceLinkedHeld','audioProcessingHeld','videoWordsHeld','brollTerminalAdmission','authenticatedFetch','ApiError',
  'const brollPlanAdmission=Symbol(),brollTimelineAdmission=Symbol(),brollInternalAdmission=Symbol(),manualReframeAdmission=Symbol(),sourceLinkedAdmission=Symbol(),audioProcessingAdmission=Symbol(),videoWordAdmission=Symbol();\n'+source+'\nreturn api;')(
   h.brollTerminalHeld,()=>false,()=>false,()=>false,()=>false,h.admission,async(path,options)=>{fetches.push({path,options});return{ok:true,status:204};},class extends Error{});
 await assert.rejects(api('/unrelated',{method:'POST'}));await assert.rejects(api('/unrelated',{method:'POST',brollTerminalAdmission:Symbol('foreign')}));assert.equal(fetches.length,0);
 await api('/owned-terminal-only',{method:'POST',brollTerminalAdmission:h.admission});assert.equal(fetches.length,1);assert.equal(Object.hasOwn(fetches[0].options,'brollTerminalAdmission'),false);
 await assert.rejects(h.brollTerminalApi('/unrelated',{method:'POST',body:'{}'}));
});
test('persistent terminal form and Root code have no automatic seal/timer/data adoption/localclear path',()=>{
 const html=readFileSync(new URL('../studio.html',import.meta.url),'utf8');assert.ok(html.indexOf('id="broll-terminal-workbench"')<html.indexOf('id="browser-content"'));
 assert.match(html,/id="broll-terminal-acknowledge" type="checkbox" disabled/);
 const terminal=segment('// Reviewed terminal INTERNAL intent release.','\nensureAuthenticatedSession()');
 assert.doesNotMatch(terminal,/setTimeout|setInterval|state\.timeline\s*=|state\.mediaPlans\s*=|state\.preview\s*=|state\.productionPackage\s*=/);
 assert.match(terminal,/op\.controller\.dispose\(\);brollInternalController=makeBrollInternalController\(\)/);
});
test('post-CAS module credential drift keeps verified release explicitly blocked without reset',async()=>{
 let h;h=moduleHarness({store:{cas:(k,v,{memory})=>{assert.equal(memory.get(k),v);memory.delete(k);h.setToken('vf1.changed-inside-successful-CAS');return true;}}});
 await h.controller.inspect();await assert.rejects(h.controller.settle(true));assert.equal(h.memory.size,0);assert.equal(h.resetCount(),0);
 assert.equal(h.controller.state().released,false);assert.equal(h.controller.state().rebind_blocked,true);assert.equal(h.controller.isHeld(),true);
});
test('post-CAS Root storage guard failure shows reload and keeps controller/data unchanged',async()=>{
 let h;h=rootHarness({store:{cas:(k,v,{memory})=>{assert.equal(memory.get(k),v);memory.delete(k);h.setToken('vf1.changed-in-Root-CAS');return true;}}});
 const before=clone(h.s),old=h.oldController();await h.inspect();await h.ack();await h.settle();assert.equal(h.memory.size,0);assert.equal(h.oldController(),old);
 assert.deepEqual(h.s,before);assert.equal(h.controller.state().released,false);assert.equal(h.controller.state().rebind_blocked,true);
 assert.equal(h.brollTerminalHeld(),true);assert.match(h.ids['broll-terminal-status'].textContent,/tải lại Studio/);
});
