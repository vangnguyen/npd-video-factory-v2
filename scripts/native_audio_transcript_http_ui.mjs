// Owned signed HTTP rehearsal of the actual controller. Fake DOM, mock ASR, no Owner UAT.
import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import {initializeNativeAudioTranscripts} from '../apps/studio-web/native-audio-transcripts.mjs';
const context=JSON.parse(readFileSync(process.argv[2],'utf8'));
assert.equal(context.fixture_human,true);assert.match(context.origin,/^http:\/\/127\.0\.0\.1:\d+$/);
class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.listeners={};this.value='';}
  append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,fn){this.listeners[k]=fn;}}
const card=new Node('details');card.id='native-audio-transcripts-card';const walk=(n,id)=>n.id===id?n:n.children.map(c=>walk(c,id)).find(Boolean);
const root={getElementById:id=>walk(card,id),createElement:t=>new Node(t)},state={workspace_id:context.workspace_id,project:context.project,canEdit:true,dirty:false,busy:false,active:false};
const requests=[],saved=[],messages=[];
const controller=initializeNativeAudioTranscripts({root,getState:()=>state,
  api:async(path,body)=>{assert.match(path,/^\/api\/projects\/[a-f0-9]{32}\/audio-transcripts(?:\/[a-f0-9]{32}(?:\.[a-z0-9]{1,16}){1,3})?$/);
    const response=await fetch(context.origin+path,{method:body?'POST':'GET',headers:{Cookie:'vf_native_session='+context.cookie,'X-VF-CSRF':context.csrf,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
    const value=await response.json();requests.push({method:body?'POST':'GET',path,status:response.status,revision:value.revision});assert.equal(response.status,200,JSON.stringify(value));assert.equal(response.headers.get('Cache-Control'),'no-store');return value;},
  onWorking:v=>{state.busy=v;},onSaved:async v=>{saved.push(v);state.project.revision=v.revision;},onMessage:(...v)=>messages.push(v)});
assert.equal(requests.length,0);await controller.load();assert.equal(controller.fields.size,1,JSON.stringify(messages));
const original=structuredClone(controller.currentBinding().selected.original);controller.fields.values().next().value.value='Lời nói Cần Giờ được sửa qua HTTP Studio.';
await controller.save();assert.equal(saved.length,1,JSON.stringify(messages));assert.equal(saved[0].items[0].current.version,2);assert.equal(saved[0].items[0].current.segments[0].words.length,0);
await controller.load();await controller.restore();assert.equal(saved.length,2,JSON.stringify(messages));assert.equal(saved[1].items[0].current.version,3);
assert.deepEqual(saved[1].items[0].original,original);assert.equal(saved[1].items[0].current.segments[0].text,original.segments[0].text);assert.equal(requests.length,4);
process.stdout.write(JSON.stringify({schema_version:'native-audio-transcript-signed-controller-proof-v1',requests,versions:[1,2,3],original_preserved:true,
  word_alignment_discarded_for_changed_text:true,restored_original_word_timing:true,ASR_dispatch_from_controller:0,real_provider_calls:0,
  fixture_human:true,mock_ASR:true,fake_DOM:true,browser_rendered:false,owner_UAT:false,publishing_enabled:false})+'\n');
