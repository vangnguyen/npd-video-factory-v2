// Fake DOM + actual owned localhost HTTP. The Python harness injects protocol/Owner/media mocks.
import assert from 'node:assert/strict';
import {initializeNativePublications} from '../apps/studio-web/native-publications.mjs';
import {initializeNativeOfficialPublications} from '../apps/studio-web/native-official-publications.mjs';
let raw='';for await(const chunk of process.stdin)raw+=chunk;const input=JSON.parse(raw);
assert.match(input.origin,/^http:\/\/127\.0\.0\.1:[0-9]+$/);const calls=[],messages=[];
const api=async(path,body)=>{assert.ok(path.startsWith('/api/'));const response=await fetch(input.origin+path,{method:body?'POST':'GET',headers:{Cookie:'vf_native_session='+input.cookie,'X-VF-CSRF':input.csrf,Origin:input.origin,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
  const value=await response.json();calls.push({path,method:body?'POST':'GET',status:response.status,schema_version:value.schema_version??null});if(!response.ok)throw Error('Owned HTTP '+response.status+' '+(value.code??'unknown'));return value;};
const nodes=new Map();class Node{constructor(){this.value='';this.checked=false;this.dataset={};this.listeners={};this.children=[];}set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,v){this.listeners[k]=v;}}
const root={createElement:()=>new Node(),getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);}},get=name=>root.getElementById('native-official-publish-'+name);
const state={workspace_id:input.workspace_id,project:input.project,canManage:true,canEdit:true,dirty:false,busy:false,active:false};
const dry=initializeNativePublications({api,root,getState:()=>state,getTikTokDraft:()=>input.draft,onMessage:(...v)=>messages.push(v)});
assert.equal(calls.length,0);await dry.execute('create-tiktok');assert.equal(calls.length,1);root.getElementById('native-publish-ack').checked=true;await dry.execute('approve');await dry.execute('dry-run');
assert.equal(messages.some(v=>v[1]===true),false,JSON.stringify(messages));assert.equal(calls.length,3);
const live=initializeNativeOfficialPublications({api,root,getState:()=>state,onMessage:(...v)=>messages.push(v)});
await live.readConfig();await live.readSources();assert.equal(get('create').disabled,false,JSON.stringify(messages));await live.execute('create');
assert.equal(live.currentBinding().publication?.status,'awaiting_publish_approval',JSON.stringify(messages));get('ack').checked=true;await live.execute('approve');
const stages=[];for(const action of['step','step','poll','poll']){await live.readState();get('send-ack').checked=true;live.controls();assert.equal(get(action).disabled,false,JSON.stringify(messages));await live.execute(action);assert.equal(get('send-ack').checked,false);stages.push(live.currentBinding().publication);}
assert.equal(stages[2].status,'queued');assert.equal(stages[2].receipt,null);assert.equal(stages.at(-1).status,'completed');await live.readState();
assert.equal(live.currentBinding().dispatch.dispatch.phase,'uploaded');assert.equal(live.currentBinding().publication.published,false);assert.equal(live.currentBinding().publication.mock_publication_complete,true);assert.equal(live.currentBinding().publication.receipt.remote_post_id,null);assert.equal(messages.some(v=>v[1]===true),false,JSON.stringify(messages));
process.stdout.write(JSON.stringify({status:'PASS',fixture_kind:'fake_dom_actual_owned_cookie_csrf_http_protocol_owner_platform_nonplayable_media_mocks',calls,messages,stages,publication:live.currentBinding().publication,dispatch:live.currentBinding().dispatch,
  real_provider_calls:0,owner_uat:false,browser_rendered:false,production_deployed:false})+'\n');
