import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash,webcrypto} from 'node:crypto';
import {initializeSqlBrollTimelineReview,brollTimelineRead,brollTimelineSelection} from '../sql-broll-timeline-review.mjs';

const bytes=readFileSync(new URL('./fixtures/sql-broll-timeline-review.json',import.meta.url));
const actual=JSON.parse(bytes),records=Object.fromEntries(actual.records.map(v=>[v.name,v]));
const clone=structuredClone,request=records.apply.request,choice=()=>({item_ids:clone(request.item_ids),replace_plan_clips:false});
const stable=v=>JSON.stringify(v,(_k,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
const digest=v=>createHash('sha256').update(typeof v==='string'?v:stable(v)).digest('hex');
function state(role='editor'){
 const timeline=clone(records.context_before.body.timeline);return{workspaceId:timeline.workspace_id,projectId:timeline.project_id,timeline,
  analysis:clone(actual.analysis),assets:clone(actual.assets),mediaPlanId:actual.plan.media_plan_id,mediaPlans:[clone(actual.plan)],
  brollDraft:{selected:clone(request.item_ids),replace:false},busy:false,dirty:false,
  // Explicit six-field public principal fixture; no real session endpoint was captured.
  principal:{subject:records.context_before.body.actor_ref,display_name:'Node B-roll fixture',platform_role:null,
   workspace_roles:{[timeline.workspace_id]:role},expires_at:'2100-01-01T00:00:00Z',human_write_enabled:true}};
}
function harness({s=state(),handler,onRead,onSaved,memory=new Map(),storage,crypto}={}){
 let token='EXPLICIT_TRANSIENT_NODE_BROLL_TIMELINE_TOKEN',response=clone(records.context_before.body),digestCalls=0;
 const calls=[],saved=[],reads=[],messages=[];
 const result=body=>{const v=clone(records.apply.body);v.receipt.request_key=body.request_key;v.receipt.replace_plan_clips=body.replace_plan_clips;
  v.receipt.request_sha256=digest({project_id:s.projectId,media_plan_id:s.mediaPlanId,actor_ref:s.principal.subject,request:body});return v;};
 const api=async(path,options)=>{const c={path,method:options?.method??'GET',body:options?.body?JSON.parse(options.body):null};calls.push(c);
  if(handler)return handler(c,{result,setResponse:v=>{response=clone(v);},response:()=>clone(response)});
  if(c.method==='PUT')response=result(c.body);return clone(response);};
 const backing=storage??{getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v),
  compareAndRemoveItem:(k,v)=>{if(memory.get(k)!==v)return false;memory.delete(k);return true;}};
 const cryptoImpl=crypto??{subtle:{digest:async(...args)=>{digestCalls++;return webcrypto.subtle.digest(...args);}},randomUUID:()=>webcrypto.randomUUID()};
 const controller=initializeSqlBrollTimelineReview({api,getState:()=>s,getSessionToken:()=>token,storage:backing,cryptoImpl,
  newRequestKey:()=>request.request_key,onMessage:(...v)=>messages.push(v),
  onRead:async v=>{reads.push(v);if(onRead)return onRead(v,s);},
  onSaved:async(v,g)=>{saved.push(v);if(onSaved)return onSaved(v,s,g);assert.equal(g(),true);s.timeline=clone(v.timeline);}});
 return{controller,s,memory,calls,saved,reads,messages,result,setToken:v=>{token=v;},setResponse:v=>{response=clone(v);},
  digestCalls:()=>digestCalls,run:(v=choice(),o={acknowledged:true})=>controller.applySelection(v,o)};
}
test('exact retained actual main-ASGI fixture is pinned; Node replay is not new SQL/media/Owner acceptance',()=>{
 assert.equal(bytes.length,384811);assert.equal(digest(bytes.toString()),'0a9942826ccc131bf48dc112fc65f9c61bfd5ab1594a6cde49799ae50d19a53c');
 assert.equal(actual.source_unchanged,true);assert.equal(actual.scope.actual_sqlite,true);assert.equal(actual.scope.actual_main_asgi,true);
 assert.equal(actual.scope.actual_decode,false);assert.equal(actual.scope.actual_render,false);assert.equal(actual.scope.owner_uat,false);
 assert.equal(actual.scope.socket_attempts_after_setup,0);assert.equal(actual.canonical_versions_after,2);
 assert.deepEqual(actual.records.map(v=>v.name),['context_before','apply','current','history','replay']);
});
test('mount and sync have no network effect; selection requires explicit current read',async()=>{
 const h=harness();h.controller.sync();assert.equal(h.calls.length,0);assert.equal(await h.run(),false);assert.equal(h.calls.length,0);
 const before=clone(h.s.timeline);assert.deepEqual(await h.controller.reload(),records.context_before.body);
 assert.deepEqual(h.s.timeline,before);assert.equal(h.reads.length,1);assert.deepEqual(h.calls.map(c=>c.method),['GET']);
});
test('exact captured request installs through private guard and compare-removes only its own held bytes',async()=>{
 const h=harness(),before=clone(h.s.timeline);await h.controller.reload();assert.equal(await h.run(),true);
 assert.deepEqual(h.calls.map(c=>c.method),['GET','GET','PUT']);assert.deepEqual(h.calls[2].body,request);
 assert.equal(h.calls[2].path,records.apply.path);assert.equal(h.saved.length,1);assert.deepEqual(h.saved[0].parent_timeline,before);
 assert.deepEqual(h.saved[0].read,records.apply.body);assert.equal(h.controller.isPending(),false);assert.equal(h.memory.size,0);
 assert.deepEqual(h.s.timeline,records.apply.body.timeline);assert.match(h.controller.getStatus(),/preview/);
});
test('source/current read validators reject missing and foreign receipt custody',()=>{
 const s=state();assert.equal(brollTimelineRead(records.context_before.body,s),records.context_before.body);
 assert.equal(brollTimelineRead(records.apply.body,s),records.apply.body);
 for(const mutate of[v=>{v.extra=true;},v=>{v.source.object_key='private';},v=>{v.actor_ref='foreign';},v=>{v.media_plan_id='foreign';},
  v=>{v.timeline_version_id='foreign';},v=>{v.receipt.media_plan_id='foreign';},v=>{v.receipt.media_binding_sha256='f'.repeat(64);},
  v=>{v.receipt.result_snapshot_sha256='f'.repeat(64);},v=>{v.receipt.publishing_enabled=true;},v=>{v.receipt.owner_approval_inferred=true;},
  v=>{v.receipt.result_version++;},v=>{v.provider_calls=1;},v=>{v.source.transcript_version++;},v=>{v.source.source_sha256='f'.repeat(64);},
  v=>{v.ready_item_ids.push(v.ready_item_ids[0]);},v=>{v.items[0].media_plan_id='foreign';}]){
  const v=clone(records.apply.body);mutate(v);assert.throws(()=>brollTimelineRead(v,s));}
});
test('malformed selections and acknowledgement refuse before network or storage',async()=>{
 const invalid=[null,[],{}, {...choice(),extra:true},{...choice(),replace_plan_clips:0},{item_ids:[],replace_plan_clips:false},
  {item_ids:Array(201).fill('a'),replace_plan_clips:false},{item_ids:['same','same'],replace_plan_clips:false},
  {item_ids:['\u0000bad'],replace_plan_clips:false},{item_ids:[1],replace_plan_clips:false}];
 for(const v of invalid){assert.throws(()=>brollTimelineSelection(v));const h=harness();await h.controller.reload();assert.equal(await h.run(v),false);assert.equal(h.calls.length,1);assert.equal(h.memory.size,0);}
 for(const acknowledged of[undefined,false,1,'true']){const h=harness();await h.controller.reload();assert.equal(await h.run(choice(),{acknowledged}),false);assert.equal(h.calls.length,1);}
 const h=harness();await h.controller.reload();assert.equal(await h.run({item_ids:['not-ready'],replace_plan_clips:false}),false);assert.equal(h.calls.length,1);
});
for(const field of['viewer','write-disabled','expired','token','busy','dirty'])test(`authority ${field} blocks apply before extra GET`,async()=>{
 const h=harness();await h.controller.reload();if(field==='viewer')h.s.principal.workspace_roles={[h.s.workspaceId]:'viewer'};
 else if(field==='write-disabled')h.s.principal.human_write_enabled=false;else if(field==='expired')h.s.principal.expires_at='2000-01-01T00:00:00Z';
 else if(field==='token')h.setToken('');else h.s[field]=true;assert.equal(await h.run(),false);assert.equal(h.calls.length,1);assert.equal(h.memory.size,0);
});
for(const field of['source','transcript','plan','draft','credential','busy','dirty','disposed'])test(`drift ${field} during awaited source GET creates zero PUT`,async()=>{
 let h,reads=0;h=harness({handler:async(c,t)=>{if(c.method==='PUT')return t.result(c.body);if(++reads===2){
  if(field==='source')h.s.assets[0].checksum_sha256='f'.repeat(64);if(field==='transcript')h.s.timeline.snapshot.metadata.transcript_revision.version++;
  if(field==='plan')h.s.mediaPlanId='mpl_foreign';if(field==='draft')h.s.brollDraft.selected=[];if(field==='credential')h.setToken('another-token');
  if(field==='busy'||field==='dirty')h.s[field]=true;if(field==='disposed')h.controller.dispose();}return clone(records.context_before.body);}});
 await h.controller.reload();assert.equal(await h.run(),false);assert.equal(h.calls.filter(c=>c.method==='PUT').length,0);assert.equal(h.memory.size,0);
});
test('caller selection is frozen before awaited GET; later caller mutation cannot change exact body',async()=>{
 let release,entered;const wait=new Promise(r=>{release=r;}),start=new Promise(r=>{entered=r;});let reads=0;
 const h=harness({handler:async(c,t)=>{if(c.method==='PUT')return t.result(c.body);if(++reads===2){entered();await wait;}return clone(records.context_before.body);}});
 await h.controller.reload();const selected=choice(),running=h.run(selected);await start;selected.item_ids[0]='mutated';selected.replace_plan_clips=true;release();
 assert.equal(await running,true);assert.deepEqual(h.calls.at(-1).body,request);
});
test('final session digest expiry and draft drift are rechecked before durable storage and PUT',async()=>{
 for(const field of['expiry','draft','busy']){let h,n=0,armed=false;const crypto={subtle:{digest:async(...args)=>{
  const v=await webcrypto.subtle.digest(...args);if(armed&&++n===4){if(field==='expiry')h.s.principal.expires_at='2000-01-01T00:00:00Z';
   if(field==='draft')h.s.brollDraft.replace=true;if(field==='busy')h.s.busy=true;}return v;}}};
  h=harness({crypto});await h.controller.reload();armed=true;assert.equal(await h.run(),false);assert.equal(h.memory.size,0);assert.equal(h.calls.filter(c=>c.method==='PUT').length,0);}
});
test('foreign durable slot introduced during final digest is preserved before PUT',async()=>{
 let h,n=0,armed=false;const memory=new Map(),foreign='FOREIGN_UNTRUSTED_RAW';const crypto={subtle:{digest:async(...args)=>{
  const out=await webcrypto.subtle.digest(...args);if(armed&&++n===4)memory.set('vf-sql-broll-timeline-pending-v1:'+stable([h.s.workspaceId,h.s.projectId,h.s.principal.subject]),foreign);return out;}}};
 h=harness({memory,crypto});await h.controller.reload();armed=true;assert.equal(await h.run(),false);assert.equal([...memory.values()][0],foreign);assert.equal(h.calls.filter(c=>c.method==='PUT').length,0);
});
test('server context/content drift between displayed read and gesture rejects without PUT',async()=>{
 for(const field of['context','media','items','receipt']){let reads=0;const h=harness({handler:async c=>{assert.equal(c.method,'GET');const v=clone(records.context_before.body);
  if(++reads===2){if(field==='context')v.context_sha256='a'.repeat(64);if(field==='media')v.media_binding_sha256='b'.repeat(64);
   if(field==='items')v.items[0].broll.search_query='changed';if(field==='receipt')v.receipt=clone(records.apply.body.receipt);}return v;}});
  await h.controller.reload();assert.equal(await h.run(),false);assert.equal(h.memory.size,0);}
});
test('malformed PUT response retains UNKNOWN without callback or automatic resend',async()=>{
 for(const change of['null','key','actor','selection','requesthash','source','othertrack','metadata','approval','clipaudio']){const h=harness({handler:async(c,t)=>{
  if(c.method==='GET')return clone(records.context_before.body);const v=t.result(c.body);if(change==='null')v.receipt=null;
  if(change==='key')v.receipt.request_key='foreign-request-key';if(change==='actor')v.receipt.actor_ref='other-owner';
  if(change==='selection')v.receipt.item_ids=['other-item'];if(change==='requesthash')v.receipt.request_sha256='f'.repeat(64);
  if(change==='source')v.source.source_sha256='f'.repeat(64);if(change==='othertrack')v.timeline.snapshot.tracks[0].clips[0].volume=.5;
  if(change==='metadata')v.timeline.snapshot.metadata.extra_unsafe_override=true;
  if(change==='approval')v.timeline.approval_status='approved';if(change==='clipaudio')v.timeline.snapshot.tracks.find(t=>t.kind==='broll').clips[0].volume=1;return v;}});
  await h.controller.reload();assert.equal(await h.run(),false);assert.equal(h.saved.length,0);assert.equal(h.memory.size,1);assert.equal(h.controller.isPending(),true);
  assert.equal(h.calls.filter(c=>c.method==='PUT').length,1);assert.equal(await h.run(),false);assert.equal(h.calls.filter(c=>c.method==='PUT').length,1);}
});
test('lost apply response reconciles exact saved receipt and installs once without second PUT',async()=>{
 let committed=false;const h=harness({handler:async(c,t)=>{if(c.method==='PUT'){committed=true;throw Error('response lost');}
  return clone(committed?records.current.body:records.context_before.body);}});
 await h.controller.reload();assert.equal(await h.run(),false);assert.equal(h.memory.size,1);assert.equal(h.saved.length,0);
 await h.controller.reconcile();assert.equal(h.saved.length,1);assert.equal(h.memory.size,0);assert.equal(h.calls.filter(c=>c.method==='PUT').length,1);
});
test('proven unchanged parent permits only exact retry; fresh GET proof precedes same-key PUT',async()=>{
 let puts=0;const h=harness({handler:async(c,t)=>{if(c.method==='PUT'){if(++puts===1)throw Error('not delivered');return t.result(c.body);}
  return clone(records.context_before.body);}});await h.controller.reload();assert.equal(await h.run(),false);
 await assert.rejects(h.controller.retry());await h.controller.reconcile();assert.equal(h.controller.state().canRetry,true);
 assert.deepEqual(await h.controller.retry(),records.apply.body);assert.equal(puts,2);
 assert.deepEqual(h.calls.filter(c=>c.method==='PUT').map(c=>c.body),[request,request]);assert.equal(h.memory.size,0);
});
test('a later failed reconcile revokes previous parent-proof retry permission',async()=>{
 let reads=0;const h=harness({handler:async c=>{if(c.method==='PUT')throw Error('not delivered');reads++;if(reads===4)throw Error('unknown GET');return clone(records.context_before.body);}});
 await h.controller.reload();assert.equal(await h.run(),false);await h.controller.reconcile();assert.equal(h.controller.state().canRetry,true);
 await assert.rejects(h.controller.reconcile());assert.equal(h.controller.state().canRetry,false);await assert.rejects(h.controller.retry());assert.equal(h.calls.filter(c=>c.method==='PUT').length,1);
});
test('foreign raw introduced during final retry proof never sends the old PUT',async()=>{
 let reads=0,h,foreign;h=harness({handler:async c=>{if(c.method==='PUT')throw Error('not delivered');if(++reads===4){const[k,raw]=[...h.memory][0];
  const b=JSON.parse(raw);b.body.request_key='foreign-broll-request-B';foreign=JSON.stringify(b);h.memory.set(k,foreign);}return clone(records.context_before.body);}});
 await h.controller.reload();assert.equal(await h.run(),false);await h.controller.reconcile();await assert.rejects(h.controller.retry());
 assert.equal(h.calls.filter(c=>c.method==='PUT').length,1);assert.equal([...h.memory.values()][0],foreign);assert.equal(h.saved.length,0);
});
test('cold-held mount is immediately pending; unchanged exact credential restores then reconciles',async()=>{
 const memory=new Map(),first=harness({memory,handler:async c=>{if(c.method==='PUT')throw Error('lost');return clone(records.context_before.body);}});
 await first.controller.reload();assert.equal(await first.run(),false);first.controller.dispose();
 const cold=harness({memory,handler:async()=>clone(records.current.body)});assert.equal(cold.controller.isPending(),true);assert.equal(cold.calls.length,0);
 await cold.controller.reload();assert.equal(cold.controller.state().pending.body.request_key,request.request_key);await cold.controller.reconcile();assert.equal(cold.memory.size,0);
});
test('cold-held foreign credential or plan cannot clear, resend or adopt old intent',async()=>{
 const first=harness({handler:async c=>{if(c.method==='PUT')throw Error('lost');return clone(records.context_before.body);}});
 await first.controller.reload();await first.run();for(const field of['credential','plan']){const memory=new Map(first.memory),s=state();if(field==='plan')s.mediaPlanId='mpl_foreign';
  const cold=harness({memory,s});if(field==='credential')cold.setToken('new-token');await assert.rejects(cold.controller.reload());assert.equal(cold.calls.length,0);assert.equal(memory.size,1);assert.equal(cold.saved.length,0);}
});
test('private sync guard catches foreign raw and native-getter source drift before callback adoption; revoked after success',async()=>{
 for(const kind of['foreign','getter-source','expiry','none']){const memory=new Map();let h,armed=false,guardRef;
  const storage={getItem:k=>{const raw=memory.get(k)??null;if(armed&&kind==='getter-source')h.s.assets[0].checksum_sha256='f'.repeat(64);return raw;},
   setItem:(k,v)=>memory.set(k,v),compareAndRemoveItem:(k,v)=>{if(memory.get(k)!==v)return false;memory.delete(k);return true;}};
  h=harness({storage,memory,onSaved:async(v,s,g)=>{guardRef=g;assert.equal(g(),true);await Promise.resolve();
   if(kind==='foreign'){const[k,raw]=[...memory][0];const b=JSON.parse(raw);b.body.request_key='foreign-broll-guard';memory.set(k,JSON.stringify(b));}
   if(kind==='expiry')s.principal.expires_at='2000-01-01T00:00:00Z';armed=true;if(kind==='none'){assert.equal(g(),true);s.timeline=clone(v.timeline);}else assert.throws(()=>g());}});
  await h.controller.reload();const before=clone(h.s.timeline);assert.equal(await h.run(),kind==='none');assert.throws(()=>guardRef());
  if(kind!=='none'){assert.deepEqual(h.s.timeline,before);assert.equal(memory.size,1);}else assert.equal(memory.size,0);
 }
});
test('Root callback failure or failure to install exact canonical keeps UNKNOWN bytes',async()=>{
 for(const throws of[true,false]){const h=harness({onSaved:async()=>{if(throws)throw Error('history proof failed');}});await h.controller.reload();
  assert.equal(await h.run(),false);assert.equal(h.memory.size,1);assert.equal(h.controller.isPending(),true);assert.deepEqual(h.s.timeline,records.context_before.body.timeline);}
});
test('foreign storage introduced after callback installation is never deleted',async()=>{
 let foreign;const h=harness({onSaved:async(v,s,g)=>{assert.equal(g(),true);s.timeline=clone(v.timeline);const[k,raw]=[...h.memory][0];
  const b=JSON.parse(raw);b.body.request_key='foreign-after-adoption';foreign=JSON.stringify(b);h.memory.set(k,foreign);}});
 await h.controller.reload();assert.equal(await h.run(),false);assert.equal([...h.memory.values()][0],foreign);assert.equal(h.calls.filter(c=>c.method==='PUT').length,1);
});
test('explicit replace checkbox is forwarded literally; no implicit replacement',async()=>{
 const h=harness();await h.controller.reload();assert.equal(await h.run({...choice(),replace_plan_clips:true}),true);
 assert.equal(h.calls.at(-1).body.replace_plan_clips,true);assert.equal(h.saved[0].receipt.replace_plan_clips,true);
});
test('read callback may hydrate its own form but cannot change source or canonical data',async()=>{
 const allowed=harness({onRead:async(_v,s)=>{s.brollDraft={selected:[],replace:false};}});await allowed.controller.reload();assert.equal(allowed.calls.length,1);
 for(const field of['source','timeline']){const h=harness({onRead:async(_v,s)=>{if(field==='source')s.assets[0].provenance.license='changed';else s.timeline.snapshot.metadata.changed=true;}});
  await assert.rejects(h.controller.reload());assert.equal(await h.run(),false);assert.equal(h.calls.length,1);}
});
test('native storage-get scope drift before persist, PUT and final clear is checked after getter',async()=>{
 for(const phase of['before-persist','before-put','before-clear']){let h,armed=false,seen=0;const memory=new Map();
  const storage={getItem:k=>{const raw=memory.get(k)??null;if(armed){seen++;if((phase==='before-persist'&&raw===null)||(phase==='before-put'&&raw!==null)
    ||phase==='before-clear'&&h.s.timeline.current_version===2)h.s.principal.expires_at='2000-01-01T00:00:00Z';}return raw;},
   setItem:(k,v)=>memory.set(k,v),compareAndRemoveItem:(k,v)=>{if(memory.get(k)!==v)return false;memory.delete(k);return true;}};
  h=harness({memory,storage,onSaved:async(v,s,g)=>{assert.equal(g(),true);s.timeline=clone(v.timeline);if(phase==='before-clear')armed=true;}});
  await h.controller.reload();if(phase!=='before-clear')armed=true;assert.equal(await h.run(),false);assert.ok(seen>0);
  if(phase==='before-persist')assert.equal(memory.size,0);else assert.equal(memory.size,1);
  assert.equal(h.calls.filter(c=>c.method==='PUT').length,phase==='before-clear'?1:0);
 }
});
test('throwing storage writer never sends PUT and unknown failed compare-remove is retained',async()=>{
 const memory=new Map(),writer=harness({storage:{getItem:()=>null,setItem:()=>{throw Error('quota unavailable');}}});
 await writer.controller.reload();assert.equal(await writer.run(),false);assert.equal(writer.calls.filter(c=>c.method==='PUT').length,0);
 const stuck=harness({memory,storage:{getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v),compareAndRemoveItem:()=>false}});
 await stuck.controller.reload();assert.equal(await stuck.run(),false);assert.equal(memory.size,1);assert.equal(stuck.controller.isPending(),true);
});
