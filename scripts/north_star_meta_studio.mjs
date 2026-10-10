// Actual signed owned loopback HTTP through real controllers and an explicit fake DOM.
import assert from 'node:assert/strict';
import {initializeNativeOfficialPublications} from '../apps/studio-web/native-official-publications.mjs';
import {initializeNativePublishingMedia} from '../apps/studio-web/native-publishing-media.mjs';
import {initializeNativeOfficialPublicationQueue} from '../apps/studio-web/native-official-publication-queue.mjs';
let raw='';for await(const chunk of process.stdin)raw+=chunk;const input=JSON.parse(raw);assert.match(input.origin,/^http:\/\/127\.0\.0\.1:[0-9]+$/);
const calls=[],messages=[],staticFiles=[],headers={Cookie:'vf_native_session='+input.cookie,'X-VF-CSRF':input.csrf,Origin:input.origin,'Content-Type':'application/json'};
const api=async(path,body)=>{assert.ok(path.startsWith('/api/'));const response=await fetch(input.origin+path,{method:body?'POST':'GET',headers,...(body?{body:JSON.stringify(body)}:{})});const value=await response.json();calls.push({path,method:body?'POST':'GET',status:response.status,schema_version:value.schema_version??null});if(!response.ok)throw Error('Owned HTTP '+response.status+' '+(value.code??'unknown'));return value;};
for(const[path,content]of [['/native.html','native-publishing-media-card'],['/native-meta-publication.mjs','validateMetaPublication'],['/native-publishing-media.mjs','initializeNativePublishingMedia']]){
  const response=await fetch(input.origin+path,{headers}),text=await response.text();assert.equal(response.status,200);assert.ok(text.includes(content));staticFiles.push({path,status:response.status,bytes:Buffer.byteLength(text)});
}
const nodes=new Map();class Node{constructor(){this.value='';this.checked=false;this.dataset={};this.listeners={};this.children=[];}set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,v){this.listeners[k]=v;}}
const root={createElement:()=>new Node(),getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);}},get=n=>root.getElementById('native-official-publish-'+n),getMedia=n=>root.getElementById('native-publishing-media-'+n);
const state={workspace_id:input.workspace_id,project:input.project,canManage:true,canEdit:true,dirty:false,busy:false,active:false};let media=null;
const publisher=initializeNativeOfficialPublications({api,root,getState:()=>state,onMessage:(...v)=>messages.push(v),getMediaSelection:()=>media?.currentSelection()??null,onSelection:()=>media?.sync()});
media=initializeNativePublishingMedia({api,root,getState:()=>state,getBinding:()=>publisher.currentBinding(),onMessage:(...v)=>messages.push(v),onSelection:()=>publisher.controls()});
const queue=initializeNativeOfficialPublicationQueue({api,root,getState:()=>state,getBinding:()=>publisher.currentBinding(),onMessage:(...v)=>messages.push(v)});assert.equal(calls.length,0);
const stages=[];let plan=null;
if(input.read_only){await publisher.readHistory();await publisher.readState();await media.readHistory();await queue.readHistory();if(root.getElementById('native-official-queue-detail').textContent)await queue.readState();assert.equal(publisher.currentBinding().publication.status,'completed');assert.ok(calls.every(x=>x.method==='GET'));}
else{
  await publisher.readConfig();await publisher.readSources();assert.equal(get('create').disabled,false,JSON.stringify(messages));await publisher.execute('create');assert.equal(publisher.currentBinding().publication.status,'awaiting_publish_approval');
  get('ack').checked=true;await publisher.execute('approve');await publisher.readState();get('send-ack').checked=true;publisher.controls();assert.equal(get('step').disabled,true);
  if(!input.legacy){
    await media.readConfig();getMedia('ack').checked=true;await media.execute('create');assert.equal(getMedia('ack').checked,false);await media.execute('process');assert.equal(media.currentSelection(),null);
    getMedia('selection-ack').checked=true;await media.execute('select');assert.ok(media.currentSelection());assert.equal(getMedia('selection-ack').checked,false);
    if(input.queue){
      await queue.readConfig();const local=at=>[at.getFullYear(),String(at.getMonth()+1).padStart(2,'0'),String(at.getDate()).padStart(2,'0')].join('-')+'T'+[at.getHours(),at.getMinutes(),at.getSeconds()].map(x=>String(x).padStart(2,'0')).join(':');
      root.getElementById('native-official-queue-start').value=local(new Date(Date.now()+3000));root.getElementById('native-official-queue-deadline').value=local(new Date(Date.now()+300000));root.getElementById('native-official-queue-max').value='8';root.getElementById('native-official-queue-interval').value='30';root.getElementById('native-official-queue-ack').checked=true;queue.controls();assert.equal(root.getElementById('native-official-queue-create').disabled,false);await queue.createPlan();
      assert.ok(messages.some(v=>String(v[0]).includes('kế hoạch')));await queue.readHistory();await queue.readState();plan=JSON.parse(root.getElementById('native-official-queue-detail').textContent);assert.equal(plan.status,'queued');assert.equal(plan.policy.request.acknowledged_background_steps,true);
    }else{
      for(const action of input.platform==='facebook'?['step','step','poll','step','poll']:['step','poll','step']){await publisher.readState();get('send-ack').checked=true;publisher.controls();assert.equal(get(action).disabled,false,JSON.stringify(messages));await publisher.execute(action);assert.equal(get('send-ack').checked,false);stages.push(publisher.currentBinding().publication);}
      await publisher.readState();assert.equal(publisher.currentBinding().publication.mock_publication_complete,true);assert.equal(publisher.currentBinding().publication.published,false);
    }
  }else{assert.equal(messages.some(v=>v[1]),false,JSON.stringify(messages));assert.ok(publisher.currentBinding().dispatch);assert.equal(get('step').disabled,true);const count=messages.length;
    await publisher.execute('step');assert.equal(calls.some(x=>x.path.endsWith('/step')),false);assert.equal(messages.length,count+1);assert.equal(messages.at(-1)[1],true);assert.match(messages.at(-1)[0],/Cho phép riêng/);messages.pop();}
}
if(input.legacy)assert.equal(publisher.currentBinding().publication.snapshot.execution_supported,false);
assert.equal(messages.some(v=>v[1]===true),false,JSON.stringify(messages));
process.stdout.write(JSON.stringify({status:'PASS',scope:'actual_local_cookie_csrf_HTTP_real_Studio_controllers_fake_DOM_explicit_meta_s3_owner_platform_nonplayable_media_mocks',calls,staticFiles,stages,queue_plan:plan,
  publication:publisher.currentBinding().publication,dispatch:publisher.currentBinding().dispatch,media_selection:media.currentSelection(),messages,legacy_execution_disabled:input.legacy===true,
  real_provider_calls:0,paid_operations:0,browser_rendered:false,owner_uat:false,production_deployed:false})+'\n');
