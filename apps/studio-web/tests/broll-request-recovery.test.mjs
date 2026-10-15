import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
import {initializeBrollPlanReview} from '../broll-plan-review.mjs';
const fixture=JSON.parse(readFileSync(new URL('./fixtures/broll-request-recovery.json',import.meta.url),'utf8'));
const copy=structuredClone;
function harness(scenario=fixture.scenarios[0],hooks={}) {
  const state=copy(scenario.state),calls=[],read=[],settled=[],guards=[],notices=[];
  const key='vf-broll-plan-pending-v1:'+JSON.stringify([state.workspaceId,state.projectId,state.principal.subject]);
  const memory=new Map([[key,scenario.pending_raw]]); let now=scenario.clock,token='vf1.renewed-owner.'+'r'.repeat(40),h;
  const storage={getItem:k=>{const value=memory.get(k)??null;hooks.get?.(h,k);return value;},
    setItem:(k,v)=>memory.set(k,v),removeItem:k=>{throw Error('recovery must use trusted CAS');},
    compareAndRemoveItem:(k,raw)=>{if(memory.get(k)!==raw)return false;memory.delete(k);return true;}};
  const api=async(path,options={})=>{
    calls.push({path,method:options.method??'GET',body:options.body?JSON.parse(options.body):null});
    const changed=await hooks.api?.(h,path,options);if(changed!==undefined)return changed;
    if(path==='/api/v1/auth/session')return copy(state.principal);
    if(path.endsWith('/recovery/inspect'))return copy(scenario.observed);
    if(path.endsWith('/recovery/abandon')||path.includes('/recovery/settlements/'))return copy(scenario.settled);
    if(path.includes('/requests/'))throw Object.assign(Error('missing'),{status:404});
    return copy(scenario.context);
  };
  const controller=initializeBrollPlanReview({api,getState:()=>state,getSessionToken:()=>token,storage,clock:()=>now,
    cryptoImpl:{subtle:{digest:async(...args)=>{const value=await webcrypto.subtle.digest(...args);hooks.digest?.(h);return value;}}},
    onRecoveryRead:async(value,guard)=>{guards.push(guard);assert.equal(guard(),true);await hooks.read?.(h,value,guard);read.push(value);return true;},
    onRecovered:async(value,guard)=>{guards.push(guard);assert.equal(guard(),true);await hooks.settled?.(h,value,guard);settled.push(value);return true;},
    onPrepared:()=>{throw Error('recovery never adopts or applies a plan');},onStatus:text=>notices.push(text)});
  h={controller,state,calls,memory,key,storage,read,settled,guards,notices,scenario,
    setNow:v=>now=v,setToken:v=>token=v};return h;
}
test('actual authenticated ASGI/SQLite recovery captures: absent and committed snapshots, zero provider',()=>{
  assert.match(fixture.fixture_notice,/Actual SQLite and authenticated ASGI/);assert.equal(fixture.network_attempts,0);
  const h=harness();assert.equal(h.calls.length,0);assert.equal(h.memory.size,1);assert.equal(h.controller.state().recovery,null);
});
for(const scenario of fixture.scenarios)test(`explicit server inspection and settlement retain original plan: ${scenario.scenario}`,async()=>{
  const h=harness(scenario);
  await assert.rejects(h.controller.abandonRecovery(true));assert.equal(h.calls.filter(v=>v.method==='POST').length,0);
  const observed=await h.controller.inspectRecovery();assert.deepEqual(observed,scenario.observed);assert.equal(h.memory.size,1);
  await assert.rejects(h.controller.abandonRecovery(false));assert.equal(h.memory.size,1);
  const result=await h.controller.abandonRecovery(true);assert.deepEqual(result,scenario.settled);assert.equal(h.memory.size,0);
  assert.equal(h.controller.state().pending,null);assert.equal(h.settled.length,1);assert.equal(h.read.length,1);
  const posts=h.calls.filter(v=>v.method==='POST');assert.deepEqual(posts.map(v=>v.path.split('/').at(-1)),['inspect','abandon']);
  assert.equal(posts[0].body.intent_json,scenario.pending_raw);assert.equal(posts[1].body.intent_json,scenario.pending_raw);
  assert.equal(posts[1].body.observation_sha256,scenario.observed.observation_sha256);
  for(const guard of h.guards)assert.throws(()=>guard());
});
test('ordinary reconcile does not silently renew/rebase an old intent',async()=>{
  const h=harness(fixture.scenarios[1]);await assert.rejects(h.controller.reconcile());assert.equal(h.calls.filter(v=>v.method==='POST').length,0);
  assert.equal(h.memory.get(h.key),h.scenario.pending_raw);
});
for(const [name,change] of [
  ['actor',h=>h.state.principal.subject='usr:foreign'],['roles',h=>h.state.principal.platform_role='editor'],
  ['source',h=>h.state.analysis.fingerprint='f'.repeat(64)],['transcript',h=>h.state.timeline.snapshot.metadata.transcript_revision.version++],
  ['peer draft',h=>h.state.dirty=true],['expired',h=>h.setNow(Date.parse(h.state.principal.expires_at))]
])test(`foreign or changed recovery remains held before POST: ${name}`,async()=>{
  const h=harness();change(h);await assert.rejects(h.controller.inspectRecovery());
  assert.equal(h.calls.filter(v=>v.method==='POST').length,0);assert.equal(h.memory.get(h.key),h.scenario.pending_raw);
});
for(const at of ['/recovery/inspect','/recovery/abandon','/recovery/settlements/'])test(`foreign bytes during ${at} retain replacement`,async()=>{
  let attack=false;const raw='{"foreign":"request B"}';
  const h=harness(undefined,{api:(h,path)=>{if(attack&&path.includes(at))h.memory.set(h.key,raw);}});
  if(at!=='/recovery/inspect')await h.controller.inspectRecovery();attack=true;
  await assert.rejects(at==='/recovery/inspect'?h.controller.inspectRecovery():h.controller.abandonRecovery(true));
  assert.equal(h.memory.get(h.key),raw);assert.equal(h.settled.length,0);
});
for(const [name,change] of [
  ['source',h=>h.state.analysis.fingerprint='f'.repeat(64)],['principal',h=>h.state.principal.display_name='Changed'],
  ['token',h=>h.setToken('vf1.changed.literal')],['expiry',h=>h.setNow(Date.parse(h.state.principal.expires_at))],
  ['draft',h=>h.state.dirty=true],['dispose',h=>h.controller.dispose()],['raw',h=>h.memory.set(h.key,'{"foreign":"B"}')]
])test(`private settlement guard rejects ${name} drift inside callback`,async()=>{
  const h=harness(undefined,{settled:async(h,_v,guard)=>{change(h);assert.throws(()=>guard());}});
  await h.controller.inspectRecovery();await assert.rejects(h.controller.abandonRecovery(true));assert.equal(h.memory.size,1);
  assert.ok(h.controller.state().pending);for(const guard of h.guards)assert.throws(()=>guard());
});
test('inspection context/settlement tamper and untrusted no-CAS store cannot clear UNKNOWN',async()=>{
  for(const mutate of [v=>v.original_authority_sha256='f'.repeat(64),v=>v.source.source_sha256='f'.repeat(64),v=>v.provider_calls=1]){
    const h=harness(undefined,{api:(_h,path)=>{if(path.endsWith('/recovery/inspect')){const v=copy(fixture.scenarios[0].observed);mutate(v);return v;}}});
    await assert.rejects(h.controller.inspectRecovery());assert.equal(h.memory.size,1);
  }
  const h=harness();await h.controller.inspectRecovery();delete h.storage.compareAndRemoveItem;
  await assert.rejects(h.controller.abandonRecovery(true));assert.equal(h.memory.get(h.key),h.scenario.pending_raw);
});
test('invalid and oversized pending bytes are bounded and preserved before a recovery POST',async()=>{
  for(const raw of ['{"foreign":1}','{', ' '.repeat(5*1024*1024+1)]){
    const h=harness();h.memory.set(h.key,raw);await assert.rejects(h.controller.inspectRecovery());
    assert.equal(h.memory.get(h.key),raw);assert.equal(h.calls.filter(v=>v.method==='POST').length,0);
  }
});
test('lost settlement response is recovered by explicit new inspection, never a fresh prepare or local clear',async()=>{
  let attempts=0,committed=false;
  const h=harness(undefined,{api:(_h,path)=>{
    if(path.endsWith('/recovery/abandon')&&++attempts===1){committed=true;throw Error('response lost after server commit');}
    if(committed&&path.endsWith('/recovery/inspect'))return {...copy(fixture.scenarios[0].settled),observation_sha256:'e'.repeat(64)};
  }});
  await h.controller.inspectRecovery();await assert.rejects(h.controller.abandonRecovery(true));assert.equal(h.memory.size,1);
  await h.controller.inspectRecovery();await h.controller.abandonRecovery(true);assert.equal(h.memory.size,0);
  assert.equal(attempts,2);assert.ok(h.calls.filter(v=>v.method==='POST').every(v=>v.path.includes('/recovery/')));
});
