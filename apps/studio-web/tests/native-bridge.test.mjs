import test from 'node:test';import assert from 'node:assert/strict';
import {initializeNativeBridge} from '../native-bridge.mjs';
const WSP='wsp_fixture_bridge';const ID='bevt_'+'a'.repeat(48);const SHA='b'.repeat(64);const DEST='c'.repeat(64);
const contract=(enabled=false)=>({contract_version:'agent-hub-bridge.v1',native_dto_version:'native-bridge-operator-v1',workspace_id:WSP,
  live_publishing_enabled:false,http_enablement_from_ui:false,webhook_delivery_enabled:enabled,webhook_mode:enabled?'fixture':'disabled',
  destination_sha256:enabled?DEST:null,destination_label:'<script>fixture</script>'});
const row=(status='disabled')=>({envelope:{contract_version:'agent-hub-bridge.v1',event_id:ID,event_type:'video.project.created',occurred_at:'2026-10-08T00:00:00Z',
  payload:{workspace_id:WSP,project_id:'d'.repeat(32)}},envelope_sha256:SHA,delivery:{workspace_id:WSP,event_id:ID,status,mode:status==='disabled'?'disabled':'fixture',destination_sha256:status==='disabled'?null:DEST}});
function harness(){class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.listeners={};this.value='';this.checked=false;}
  append(...values){this.children.push(...values);}replaceChildren(...values){this.children=values;}addEventListener(name,fn){this.listeners[name]=fn;}}
  const root=new Node('details'),dom={getElementById:()=>root,createElement:tag=>new Node(tag)},state={workspace_id:WSP,busy:false,canManage:true},calls=[],messages=[];
  let response=async path=>path.endsWith('/state')?contract():{contract_version:'agent-hub-bridge.v1',workspace_id:WSP,items:[row()],next_cursor:null};
  const controller=initializeNativeBridge({dom,getState:()=>state,api:async(path,body)=>{calls.push([path,body]);return response(path,body);},onMessage:(...value)=>messages.push(value),uuid:()=> 'fixture-uuid-00001'});
  const [status,read,choices,detail,label,send,cancel,audit,more]=root.children;
  return {controller,state,calls,messages,status,read,choices,detail,ack:label.children[0],send,cancel,audit,more,handler:value=>{response=value;}};}
test('explicit read default-off literal destination and viewer guards cause no selection or network request',async()=>{
  const h=harness();assert.equal(h.calls.length,0);assert.equal(h.send.disabled,true);await h.read.listeners.click();assert.equal(h.calls.length,2);
  assert.equal(h.send.disabled,true);h.ack.checked=true;await h.send.listeners.click();assert.equal(h.calls.length,2);
  h.handler(async path=>path.endsWith('/state')?contract(true):{contract_version:'agent-hub-bridge.v1',workspace_id:WSP,items:[row()],next_cursor:null});
  await h.controller.load();assert.match(h.status.textContent,/<script>fixture/);h.state.canManage=false;h.controller.controls();assert.equal(h.send.disabled,true);
  await h.send.listeners.click();assert.equal(h.calls.length,4);assert.equal(h.status.innerHTML,undefined);
});
test('acknowledged exact event selection uses stable key on lost reply and never enables or mutates a project',async()=>{
  const h=harness();let failure=true;
  h.handler(async(path,body)=>{if(path.endsWith('/state'))return contract(true);if(!body)return {contract_version:'agent-hub-bridge.v1',workspace_id:WSP,items:[row()],next_cursor:null};
    if(failure)throw new Error('Explicit lost reply fixture');return {contract_version:'agent-hub-bridge.v1',workspace_id:WSP,event_id:ID,action:'enqueue',selected_status:'queued',external_call_performed:false};});
  await h.controller.load();h.ack.checked=true;h.ack.listeners.change();assert.equal(h.send.disabled,false);await h.send.listeners.click();failure=false;await h.send.listeners.click();
  const writes=h.calls.filter(([,body])=>body);assert.equal(writes.length,2);assert.deepEqual(writes[0][1],writes[1][1]);assert.equal(writes[0][0],`/api/bridge/events/${ID}/enqueue`);
  assert.equal(writes[0][1].fixture_acknowledged,true);assert.equal(writes[0][1].http_acknowledged,false);assert.equal(writes[0][1].expected_envelope_sha256,SHA);
  assert.equal(h.ack.checked,false);assert.equal(h.send.disabled,true);assert.equal(h.calls.some(([path])=>path.includes('/projects')||path.includes('/enable')),false);
});
test('queued event cancellation works while delivery disabled and history remains visible',async()=>{
  const h=harness();h.handler(async(path,body)=>{if(path.endsWith('/state'))return contract();if(body)return {contract_version:'agent-hub-bridge.v1',workspace_id:WSP,event_id:ID,action:'cancel',selected_status:'cancelled',external_call_performed:false};
    if(path.endsWith('/delivery'))return {contract_version:'agent-hub-bridge.v1',workspace_id:WSP,event_id:ID,fixture:true,real_hub_receipt_verified:false,
      delivery:{status:'retry_scheduled'},attempts:[{attempt:1,response_status:429,external_call:0}],operator_receipts:[]};
    return {contract_version:'agent-hub-bridge.v1',workspace_id:WSP,items:[row('retry_scheduled')],next_cursor:null};});
  await h.controller.load();await h.audit.listeners.click();assert.match(h.detail.textContent,/429/);assert.match(h.messages.at(-1)[0],/mô phỏng/);
  assert.equal(h.cancel.disabled,false);await h.cancel.listeners.click();const body=h.calls.find(([,value])=>value)[1];
  assert.equal(body.expected_destination_sha256,DEST);assert.equal(body.fixture_acknowledged,false);assert.equal(body.http_acknowledged,false);
});
test('foreign workspace and stale reads cannot restore old choices or select malformed receipt',async()=>{
  const h=harness();let release;h.handler(async()=>new Promise(resolve=>{release=resolve;}));const reading=h.controller.load();
  h.state.workspace_id='wsp_new_fixture';h.controller.sync();release(contract(true));await reading;assert.equal(h.choices.children.length,0);assert.equal(h.send.disabled,true);
  h.handler(async()=>({...contract(true),workspace_id:WSP}));await h.controller.load();assert.equal(h.choices.children.length,0);
  assert.equal(h.calls.some(([,body])=>body),false);assert.equal(h.messages.at(-1)[1],true);
});
