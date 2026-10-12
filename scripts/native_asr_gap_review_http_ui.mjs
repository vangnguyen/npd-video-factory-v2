// Actual signed local HTTP, explicit fixture actor and a minimal DOM, not browser UAT.
import {readFileSync} from 'node:fs';import assert from 'node:assert/strict';import {createHash} from 'node:crypto';
import {initializeGapReview} from '../apps/studio-web/native-asr-gap-review.mjs';
const config=JSON.parse(readFileSync(process.argv[2],'utf8')),calls=[],messages=[],saved=[];
class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.dataset={};this.style={};this.value='';this.checked=false;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(n,f){this.listeners[n]=f;}}
const card=new Node('details');card.id='native-asr-gap-review-card';const walk=(n,id)=>n.id===id?n:n.children.map(c=>walk(c,id)).find(Boolean),root={getElementById:id=>walk(card,id),createElement:t=>new Node(t)};
const state={workspace_id:config.workspace_id,project:{id:config.project_id,revision:config.revision},canEdit:true,busy:false,active:false,dirty:false,dirtyPart:null};
async function api(path,body){calls.push({method:body===undefined?'GET':'POST',path});const response=await fetch(config.base+path,{method:body===undefined?'GET':'POST',headers:{Cookie:'vf_native_session='+config.cookie,'X-VF-CSRF':config.csrf,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const value=await response.json();assert.equal(response.status,200,JSON.stringify(value));return value;}
const ui=initializeGapReview({api,root,getState:()=>state,onWorking:v=>state.busy=v,onMessage:(...v)=>messages.push(v),onDirty:v=>{state.dirty=v;state.dirtyPart=v?'asr_gap_review':null;},onSaved:async v=>saved.push(v)});
assert.equal(calls.length,0);await ui.load();assert.equal(messages.length,0,JSON.stringify(messages));const initial=structuredClone(ui.binding().value),selected=ui.binding().selected;
const source=await fetch(config.base+selected.source_url,{headers:{Cookie:'vf_native_session='+config.cookie,Range:'bytes=0-63'}});assert.equal(source.status,206);const sourceBytes=Buffer.from(await source.arrayBuffer());assert.equal(sourceBytes.length,64);
const field=ui.fields.get(1);assert.equal(field.start.value,'0.6');field.start.value='1.3';field.start.listeners.input();const ack=root.getElementById('native-asr-gap-review-acknowledged');ack.checked=true;ack.listeners.change();
await ui.save();assert.equal(messages.length,0,JSON.stringify(messages));assert.equal(saved.length,1);const edited=structuredClone(ui.binding().value);assert.equal(edited.items[0].version,1);assert.deepEqual(edited.items[0].original_words,initial.items[0].original_words);
await ui.resume();assert.equal(messages.length,0,JSON.stringify(messages));assert.equal(saved.length,2);assert.equal(saved[1].id,selected.job_id);assert.equal(saved[1].status,'queued');assert.equal(calls.length,3);
process.stdout.write(JSON.stringify({scope:'signed-local-http-controller-fixture-dom',fixture_human:true,mock_ASR:true,Owner_UAT:false,browser_rendered:false,calls,initial,edited,
  resumed_job_id:saved[1].id,source_range_sha256:createHash('sha256').update(sourceBytes).digest('hex'),provider_calls:0}));
