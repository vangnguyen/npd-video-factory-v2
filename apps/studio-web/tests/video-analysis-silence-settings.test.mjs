import test from 'node:test';
import assert from 'node:assert/strict';
import {initializeVideoAnalysisJobs,videoAnalysisPayload,videoSilenceSettings} from '../video-analysis-jobs.mjs';

// DOM, ASR/job replies, timers and transport are explicit fixtures; no model/server/browser is run.
const clone=structuredClone,assetId='ast_silence_source',jobId='job_analysis_'+'a'.repeat(24),analysisId='ana_'+'b'.repeat(24);
const defaults={silence_threshold_db:-35,minimum_silence_duration:.5,padding_before:.08,padding_after:.08};
const custom={silence_threshold_db:-42,minimum_silence_duration:.75,padding_before:.12,padding_after:.2};
const names={silence_threshold_db:'silence-threshold',minimum_silence_duration:'silence-duration',padding_before:'padding-before',padding_after:'padding-after'};
function state(){return{workspaceId:'wsp_silence',projectId:'prj_silence',principal:{subject:'usr:silence-fixture',
  platform_role:'editor',expires_at:'2100-01-01T00:00:00Z'},busy:false,dirty:false,assets:[{
    asset_id:assetId,workspace_id:'wsp_silence',project_id:'prj_silence',asset_class:'source',kind:'video',content_type:'video/mp4',
    checksum_sha256:'a'.repeat(64),size_bytes:1024,filename:'silence-contract.mp4',
    provenance:{source_type:'user_upload',media_metadata:{media_kind:'video',duration_seconds:8}}}]};}
function reply(s,body,status='queued'){
  return{schema_version:'auto-edit-analysis-job.v1',human_review_required:true,source_media_mutated:false,timeline_mutated:false,
    publishing_enabled:false,source_sha256:body.source_sha256,custody_sha256:'c'.repeat(64),
    job:{job_id:jobId,workspace_id:s.workspaceId,project_id:s.projectId,status,progress:10,
      request:{kind:'auto_edit_analysis',analysis_id:analysisId,source_sha256:body.source_sha256,provider_binding_sha256:'d'.repeat(64)}},
    analysis:{analysis_id:analysisId,workspace_id:s.workspaceId,project_id:s.projectId,asset_id:assetId,status:'pending',
      configuration:clone(body.configuration),provenance:{fixture:true}}};
}
function harness({s=state(),memory=new Map(),handler,storage}={}){
  class Element{constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.listeners={};this.value='';this.disabled=false;this.textContent='';}
    append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}
    setAttribute(key,value){this.attributes[key]=String(value);}addEventListener(key,value){this.listeners[key]=value;}}
  const root=new Element('div'),all=node=>[node,...node.children.flatMap(all)],calls=[],messages=[],timers=new Map();let counter=0;
  const api=async(path,options={})=>{const c={path,method:options.method??'GET',body:options.body?JSON.parse(options.body):null};calls.push(c);
    return handler?handler(c,s):c.method==='POST'?reply(s,c.body):[];};
  const controller=initializeVideoAnalysisJobs({root,dom:{createElement:tag=>new Element(tag)},api,getState:()=>s,
    onMessage:(...values)=>messages.push(values),storage:storage??{getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)},
    newKey:()=>`silence-intent-${++counter}`,setTimer:fn=>{const id=++counter;timers.set(id,fn);return id;},clearTimer:id=>timers.delete(id)});
  const get=name=>all(root).find(e=>Object.hasOwn(e.attributes,'data-video-job-'+name));
  const set=values=>{for(const[key,value]of Object.entries(values))get(names[key]).value=String(value);};
  return{s,root,calls,messages,timers,memory,controller,get,set,click:name=>get(name).listeners.click()};
}

test('default payload is unchanged and custom silence fields bind into the existing queued request',()=>{
  const s=state(),before=clone(s);assert.deepEqual(videoSilenceSettings(),defaults);
  const payload=videoAnalysisPayload(s,assetId,5,'silence-exact-intent',custom);
  assert.deepEqual(payload.configuration,{asset_id:assetId,acceptance_operation_id:null,top_highlights:5,...custom,
    word_timing_policy:'strict_provider_intervals'});
  assert.deepEqual(Object.keys(payload).sort(),['configuration','idempotency_key','source_sha256']);assert.deepEqual(s,before);
  assert.deepEqual(videoSilenceSettings({padding_after:.6}),{...defaults,padding_after:.6});
});
for(const[key,low,high]of [['silence_threshold_db',-80,-5],['minimum_silence_duration',.1,10],['padding_before',0,2],['padding_after',0,2]]){
  test(`silence contract accepts both inclusive bounds for ${key}`,()=>{
    for(const value of [low,high])assert.equal(videoSilenceSettings({[key]:value})[key],value);
  });
  test(`silence contract rejects coercion, non-finite and out-of-range ${key}`,()=>{
    for(const value of [low-.001,high+.001,NaN,Infinity,-Infinity,null,true,false,[],{},String(low),undefined])
      assert.throws(()=>videoSilenceSettings({[key]:value}));
  });
}
test('silence settings reject extra keys and non-object shapes without manufacturing authority',()=>{
  for(const value of [null,[],true,1,'settings',{...custom,publish:true},{...custom,actor_ref:'owner'}])assert.throws(()=>videoSilenceSettings(value));
});
test('mount and sync show defaults without dispatch; editing parameters does not submit or mutate source/timeline',()=>{
  const h=harness(),before=clone(h.s);h.controller.sync();
  for(const[key,name]of Object.entries(names)){assert.equal(h.get(name).value,String(defaults[key]));assert.equal(h.get(name).type,'number');}
  h.set(custom);h.controller.sync();assert.deepEqual(h.calls,[]);assert.deepEqual(h.s,before);assert.equal(h.memory.size,0);
});
test('one explicit start persists the full custom request before POST and displays the saved configuration',async()=>{
  const memory=new Map();let h;
  h=harness({memory,handler:(c,s)=>{assert.equal(c.method,'POST');assert.equal(memory.size,1);
    const frozen=JSON.parse([...memory.values()][0]);assert.deepEqual(frozen.body,c.body);return reply(s,c.body);}});
  h.set(custom);await h.click('start');assert.equal(h.calls.length,1);
  assert.deepEqual(h.calls[0].body.configuration,{asset_id:assetId,acceptance_operation_id:null,top_highlights:3,...custom,
    word_timing_policy:'strict_provider_intervals'});assert.equal(h.controller.isPending(),false);
  assert.match(h.get('saved-configuration').textContent,/-42 dBFS/);assert.match(h.get('saved-configuration').textContent,/0.75 giây/);
  h.controller.dispose();
});
for(const value of ['', ' ', 'NaN', 'Infinity', '0x1', '0.1seconds', '3'])
  test(`invalid padding text ${JSON.stringify(value)} cannot reach POST or persist an intent`,async()=>{
    const h=harness();h.get('padding-before').value=value;await h.click('start');
    assert.deepEqual(h.calls,[]);assert.equal(h.memory.size,0);assert.equal(h.controller.isPending(),false);assert.ok(h.messages.length);
  });
test('parameter drift during source-receipt await aborts before request persistence or dispatch',async()=>{
  const h=harness();h.set(custom);const work=h.click('start');h.get('padding-after').value='.4';await work;
  assert.deepEqual(h.calls,[]);assert.equal(h.memory.size,0);assert.ok(h.messages.length);
});
test('UNKNOWN retry keeps exact settings and key even if the disabled form was tampered',async()=>{
  let fail=true;const h=harness({handler:(c,s)=>{if(fail){fail=false;throw Error('explicit dropped reply fixture');}return reply(s,c.body);}});
  h.set(custom);await h.click('start');const body=clone(h.calls[0].body),stored=[...h.memory.values()][0];
  assert.equal(h.controller.isPending(),true);for(const name of Object.values(names))assert.equal(h.get(name).disabled,true);
  h.set({padding_before:2,padding_after:1,silence_threshold_db:-7,minimum_silence_duration:9});await h.click('retry');
  assert.deepEqual(h.calls[1].body,body);assert.equal(JSON.parse(stored).body.idempotency_key,body.idempotency_key);
  assert.equal(h.controller.isPending(),false);assert.equal(h.memory.size,0);h.controller.dispose();
});
test('reload restores a custom UNKNOWN body without automatic submission or reset to defaults',async()=>{
  const memory=new Map(),old=harness({memory,handler:()=>{throw Error('lost fixture reply');}});
  old.set(custom);await old.click('start');const frozen=clone(old.calls[0].body);old.controller.dispose();
  const fresh=harness({memory});assert.deepEqual(fresh.calls,[]);await fresh.click('read');
  assert.equal(fresh.controller.isPending(),true);assert.equal(fresh.calls.length,1);assert.equal(fresh.calls[0].method,'GET');
  await fresh.click('retry');assert.deepEqual(fresh.calls[1].body,frozen);assert.equal(memory.size,0);fresh.controller.dispose();
});
for(const mutation of ['range','extra','missing'])test(`tampered stored ${mutation} settings remain held and never dispatch`,async()=>{
  const memory=new Map(),old=harness({memory,handler:()=>{throw Error('lost fixture reply');}});
  old.set(custom);await old.click('start');old.controller.dispose();const key=[...memory.keys()][0],stored=JSON.parse(memory.get(key));
  if(mutation==='range')stored.body.configuration.padding_after=3;
  if(mutation==='extra')stored.body.configuration.publishing_enabled=true;
  if(mutation==='missing')delete stored.body.configuration.minimum_silence_duration;
  const raw=JSON.stringify(stored);memory.set(key,raw);const fresh=harness({memory});await fresh.click('retry');
  assert.deepEqual(fresh.calls,[]);assert.equal(memory.get(key),raw);assert.ok(fresh.messages.length);
});
test('saved job settings stay read-only and do not overwrite the next-analysis form or send a new job',async()=>{
  const s=state(),body=videoAnalysisPayload(s,assetId,5,'saved-silence-config',custom),h=harness({s,handler:()=>[reply(s,body)]});
  await h.click('read');assert.deepEqual(h.calls.map(c=>c.method),['GET']);
  assert.match(h.get('saved-configuration').textContent,/-42 dBFS/);assert.match(h.get('saved-configuration').textContent,/0.12 giây/);
  assert.equal(h.get('silence-threshold').value,'-35');assert.equal(h.get('padding-before').value,'0.08');h.controller.dispose();
});
test('viewer, busy, dirty and held contexts disable all four parameters',async()=>{
  for(const change of [s=>s.principal.platform_role='viewer',s=>s.busy=true,s=>s.dirty=true]){
    const s=state();change(s);const h=harness({s});
    for(const name of Object.values(names))assert.equal(h.get(name).disabled,true);
    await h.click('start');assert.deepEqual(h.calls,[]);
  }
});

test('response A cannot adopt or remove another stored request B with different settings',async()=>{
  const memory=new Map();let foreignRaw;
  const h=harness({memory,handler:(call,s)=>{
    const key=[...memory.keys()][0],foreign=JSON.parse(memory.get(key));
    foreign.body.idempotency_key='foreign-silence-intent';foreign.body.configuration.padding_after=.61;
    foreignRaw=JSON.stringify(foreign);memory.set(key,foreignRaw);return reply(s,call.body);
  }});
  h.set(custom);await h.click('start');
  assert.equal(h.calls.length,1);assert.equal(h.memory.size,1);assert.equal([...memory.values()][0],foreignRaw);
  assert.equal(h.controller.isPending(),true);assert.equal(h.get('saved').children.length,0);assert.equal(h.timers.size,0);
  await h.click('retry');assert.equal(h.calls.length,1);assert.equal([...memory.values()][0],foreignRaw);
});
test('an UNKNOWN retry checks exact raw ownership before any second POST',async()=>{
  const h=harness({handler:()=>{throw Error('lost fixture reply');}});h.set(custom);await h.click('start');
  const key=[...h.memory.keys()][0],foreign=JSON.parse(h.memory.get(key));foreign.body.idempotency_key='replacement-intent';
  const raw=JSON.stringify(foreign);h.memory.set(key,raw);await h.click('retry');
  assert.equal(h.calls.length,1);assert.equal(h.memory.get(key),raw);assert.equal(h.controller.isPending(),true);
});
test('stored whitespace is preserved as the owned record and can be cleared only on exact valid replay',async()=>{
  const memory=new Map(),old=harness({memory,handler:()=>{throw Error('lost fixture reply');}});
  old.set(custom);await old.click('start');const body=clone(old.calls[0].body);old.controller.dispose();
  const key=[...memory.keys()][0];memory.set(key,JSON.stringify(JSON.parse(memory.get(key)),null,2)+'\n');
  const fresh=harness({memory});await fresh.click('read');assert.equal(fresh.controller.isPending(),true);
  await fresh.click('retry');assert.deepEqual(fresh.calls[1].body,body);assert.equal(memory.size,0);fresh.controller.dispose();
});
for(const drift of ['source','principal'])test(`last storage read cannot clear an intent after ${drift} drift`,async()=>{
  const memory=new Map();let reads=0,h;
  const storage={getItem:key=>{const raw=memory.get(key)??null;if(++reads===5){
    if(drift==='source')h.s.assets[0].checksum_sha256='f'.repeat(64);else h.s.principal.subject='usr:changed';
  }return raw;},setItem:(key,value)=>memory.set(key,value),removeItem:key=>memory.delete(key)};
  h=harness({memory,storage});h.set(custom);await h.click('start');
  assert.equal(h.calls.length,1);assert.equal(memory.size,1);assert.equal(h.get('saved').children.length,0);
  assert.equal(h.timers.size,0);
});
