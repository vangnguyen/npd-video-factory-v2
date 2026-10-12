import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import {initializeGapReview,validateGapReviews} from '../native-asr-gap-review.mjs';
const fixture=JSON.parse(readFileSync(new URL('./fixtures/native-asr-gap-review.json',import.meta.url),'utf8')),copy=v=>structuredClone(v);
function harness(){
  class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.dataset={};this.style={};this.value='';this.checked=false;}
    append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(n,fn){this.listeners[n]=fn;}}
  const card=new Node('details');card.id='native-asr-gap-review-card';
  const walk=(n,id)=>n.id===id?n:n.children.map(c=>walk(c,id)).find(Boolean),root={getElementById:id=>walk(card,id),createElement:t=>new Node(t)};
  const state={workspace_id:fixture.workspace_id,project:{id:fixture.project_id,revision:fixture.revision},canEdit:true,active:false,dirty:false,dirtyPart:null,busy:false},calls=[],messages=[],saved=[];
  let respond=async(path,body)=>{if(!body)return copy(fixture);if(path.endsWith('/resume'))return{id:fixture.items[0].job_id,project_id:state.project.id,kind:'asr',status:'queued'};
    const value=copy(fixture),item=value.items[0];item.version=1;item.current_words=copy(body.words);item.can_resume=true;
    item.history=[{version:1,candidate_sha256:item.candidate_sha256,job_id:item.job_id,asset_id:item.asset_id,sha256:'b'.repeat(64),acknowledged:true,source_media_mutated:false,provider_calls:0}];value.changed=true;return value;};
  const controller=initializeGapReview({root,getState:()=>state,api:async(path,body)=>{calls.push({path,body});return respond(path,body);},onMessage:(...v)=>messages.push(v),onWorking:v=>state.busy=v,
    onDirty:v=>{state.dirty=v;state.dirtyPart=v?'asr_gap_review':null;},onSaved:async v=>saved.push(v)});
  const node=id=>root.getElementById('native-asr-gap-review-'+id);
  const fix=()=>{const input=controller.fields.get(1).start;input.value='1.3';input.listeners.input();node('acknowledged').checked=true;node('acknowledged').listeners.change();};
  return{root,card,state,calls,messages,saved,controller,node,fix,respond:fn=>respond=fn};
}
test('gap review initializes without dispatch, preserves original words and explicitly saves/resumes the same job',async()=>{
  const h=harness();assert.equal(h.calls.length,0);await h.controller.load();assert.equal(h.calls.length,1);assert.equal(h.controller.fields.size,2);
  assert.equal(h.controller.binding().selected.original_words[1].start_seconds,.6);h.fix();await h.controller.save();assert.equal(h.saved.length,1,JSON.stringify(h.messages));
  const body=h.calls[1].body;assert.equal(body.words[1].start_seconds,1.3);assert.equal(body.candidate_sha256,fixture.items[0].candidate_sha256);assert.equal(body.acknowledged,true);
  assert.equal(h.controller.binding().selected.original_words[1].start_seconds,.6);assert.equal(h.node('rows').innerHTML,undefined);assert.equal(h.state.dirty,false);
  await h.controller.resume();assert.equal(h.calls[2].path,'/api/jobs/'+fixture.items[0].job_id+'/resume');assert.equal(h.calls.some(c=>c.body?.kind==='asr'),false);
});
test('viewer, unrelated dirty edits, active and archived state cannot write or resume',async()=>{
  for(const flag of ['viewer','dirty','active','archived']){const h=harness();await h.controller.load();h.fix();if(flag==='viewer')h.state.canEdit=false;if(flag==='dirty'){h.state.dirty=true;h.state.dirtyPart='script';}if(flag==='active')h.state.active=true;if(flag==='archived')h.state.project.archived=true;
    await h.controller.save();await h.controller.resume();assert.equal(h.calls.length,1,flag);assert.equal(h.saved.length,0);}
});
test('unresolved overlap, missing acknowledgement and empty retained transcript are refused before API mutation',async()=>{
  for(const kind of ['gap','ack','empty']){const h=harness();await h.controller.load();h.node('acknowledged').checked=true;if(kind==='ack'){h.fix();h.node('acknowledged').checked=false;}if(kind==='empty')for(const f of h.controller.fields.values()){f.removed.checked=true;f.removed.listeners.change();}
    await h.controller.save();assert.equal(h.calls.length,1,kind);assert.equal(h.saved.length,0);}
});
test('network retry retains the same idempotency key and verifies the prior applied receipt',async()=>{
  const h=harness();await h.controller.load();h.fix();let applied=null;
  h.respond(async(path,body)=>{if(!applied){const v=copy(fixture),item=v.items[0];item.version=1;item.current_words=copy(body.words);item.can_resume=true;item.history=[{version:1,candidate_sha256:item.candidate_sha256,job_id:item.job_id,asset_id:item.asset_id,sha256:'b'.repeat(64),acknowledged:true,source_media_mutated:false,provider_calls:0}];v.changed=false;applied=v;throw Error('Fixture response lost');}return copy(applied);});
  await h.controller.save();await h.controller.save();assert.equal(h.calls.length,3);assert.equal(h.calls[1].body.request_key,h.calls[2].body.request_key);assert.equal(h.saved.length,1,JSON.stringify(h.messages));
});
test('foreign revision/provider/source URL/private response and late prior-project data are rejected',async()=>{
  const s={workspace_id:fixture.workspace_id,project:{id:fixture.project_id,revision:fixture.revision}};
  for(const change of [v=>v.workspace_id='foreign',v=>v.revision++,v=>v.provider_calls=1,v=>v.items[0].source_url='https://untrusted.invalid/source',v=>v.items[0].access_token='bad']){const v=copy(fixture);change(v);assert.throws(()=>validateGapReviews(v,s));}
  const h=harness();let resolve;h.respond(()=>new Promise(r=>resolve=r));const work=h.controller.load();await Promise.resolve();h.state.project={id:'a'.repeat(32),revision:1};h.controller.sync();resolve(copy(fixture));await work;assert.equal(h.controller.binding().selected,null);assert.equal(h.controller.fields.size,0);
});
