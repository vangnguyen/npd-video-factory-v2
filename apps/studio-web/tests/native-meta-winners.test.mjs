import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {initializeNativeOfficialWinners} from '../native-official-winners.mjs';
import {initializeNativeOfficialLearning} from '../native-official-learning.mjs';
const fixtures=JSON.parse(fs.readFileSync(new URL('./fixtures/native-meta-winners-v1.json',import.meta.url),'utf8'));
const clone=v=>structuredClone(v);

function harness(F,kind='winners'){
  const nodes=new Map();class Node{constructor(){this.children=[];this.value='';this.checked=false;this.dataset={};this.listeners={};this.textContent='';}
    set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,v){this.listeners[k]=v;}}
  const prefix='native-official-'+kind+'-',root={createElement:()=>new Node(),getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);}},
    get=id=>{assert.ok(nodes.has(prefix+id),id);return nodes.get(prefix+id);},
    state={workspace_id:F.workspace_id,project:clone(F.project),canManage:true,dirty:false,busy:false,active:false},calls=[],messages=[];
  let current=clone(kind==='winners'?F.assessment:F.learning),handler,count=0;
  const defaultHandler=async(path,body)=>{
    if(path.includes('/connections/'))return clone(kind==='winners'?F.runtime:F.learning_runtime);
    if(path.includes('/source/'))return clone(kind==='winners'?F.source:F.learning_source);
    if(body)return clone(current);
    if(path.includes('?'))return clone(kind==='winners'?F.page:F.learning_page);
    return clone(current);
  };handler=defaultHandler;
  const common={root,getState:()=>state,getBinding:()=>kind==='winners'?{sync:clone(F.analytics)}:{assessment:clone(F.assessment)},
    api:async(...args)=>{calls.push(args);return handler(...args);},onMessage:(...v)=>messages.push(v),onWorking:v=>{state.busy=v;},uuid:()=> 'explicit-meta-feedback-ui-'+(++count)};
  const controller=kind==='winners'?initializeNativeOfficialWinners(common):initializeNativeOfficialLearning(common);
  return{controller,get,state,calls,messages,handler:v=>{handler=v;},defaultHandler,current:v=>{current=clone(v);}};
}

for(const [platform,F] of Object.entries(fixtures)){
  test(platform+' captured counter assessment enters the normal owner workflow with explicit mock consent',async()=>{
    const h=harness(F);await h.controller.readConfig();await h.controller.readSource();
    const policy=F.request.policy;for(const [k,v] of Object.entries(policy)){if(k==='schema_version')continue;
      if(k==='weights'){for(const [name,weight]of Object.entries(v))h.get('weight-'+name).value=String(weight);}
      else h.get(k.replaceAll('_','-')).value=String(v);
    }
    h.get('ack').checked=true;h.get('mock-ack').checked=true;h.controller.controls();assert.equal(h.get('create').disabled,false);
    await h.controller.createAssessment();assert.deepEqual(h.messages,[]);
    assert.equal(h.controller.currentBinding().assessment.assessment.algorithm_version,'winner-meta-counter-assessment-v1');
    assert.equal(h.controller.currentBinding().assessment.assessment.state,platform==='instagram_reels'?'winner_candidate':'insufficient_data');
    assert.equal(h.calls.filter(v=>v[1]).length,1);assert.match(h.get('status').textContent,/mô phỏng/i);
  });
  test(platform+' viewer reads exact counter/learning histories with no write or invented publication window',async()=>{
    const h=harness(F);h.state.canManage=false;h.controller.sync();await h.controller.readSource();await h.controller.readHistory();
    assert.deepEqual(h.messages,[]);assert.equal(h.get('create').disabled,true);assert.equal(h.calls.filter(v=>v[1]).length,0);
    assert.equal(h.controller.currentBinding().assessment.assessment.publishing_age_hours,null);
    const l=harness(F,'learning');l.state.canManage=false;l.controller.sync();await l.controller.readSource();await l.controller.readHistory();
    assert.deepEqual(l.messages,[]);assert.equal(l.get('create').disabled,true);assert.equal(l.calls.filter(v=>v[1]).length,0);
    assert.equal(l.controller.currentBinding().learning.observation_count,platform==='instagram_reels'?6:0);
    assert.ok(l.controller.currentBinding().learning.snapshot.observations.every(o=>o.features.publishing_window===null));
  });
  test(platform+' substituted API version or metric-definition fingerprint fails before assessment selection',async()=>{
    const h=harness(F);h.handler(async(path,body)=>{const v=await h.defaultHandler(path,body);if(path.includes('/source/'))v.scope.api_version='v25.0';return v;});
    await h.controller.readSource();assert.ok(h.messages.length);assert.equal(h.get('create').disabled,true);
    const q=harness(F);await q.controller.readSource();q.handler(async(path,body)=>{const v=await q.defaultHandler(path,body);
      if(path.includes('?'))v.items[0].snapshot.candidate.scope.metric_definition_sha256='0'.repeat(64);return v;});
    await q.controller.readHistory();assert.ok(q.messages.length);assert.equal(q.controller.currentBinding().assessment,null);
  });
}
