import test from 'node:test';import assert from 'node:assert/strict';
import {initializeNativeRights} from '../native-rights.mjs';
const WSP='wsp_native_rights_fixture',PROJECT='a'.repeat(32),ASSET='b'.repeat(32)+'.jpg',SHA='c'.repeat(64);
function page(){return {schema_version:'native-rights-review-v1',workspace_id:WSP,project_id:PROJECT,revision:3,external_calls:0,
  unknown_rights_block_publishing:true,owner_override_enabled:false,items:[{asset_id:ASSET,asset_sha256:SHA,filename:'Tư liệu <script> · Cần Giờ',
    source_type:'user_upload',rights_status:'unknown',license:null,provider:'native-local-upload',source_reference:'upload://fixture',generation_provenance:{},
    human_assertion_is_provider_verification:false,declaration:null}]};}
function receipt(body){const {request_key,...request}=body;return {schema_version:'native-rights-declaration-v1',workspace_id:WSP,project_id:PROJECT,revision:4,
  approval_invalidated:true,media_bytes_changed:false,external_calls:0,declaration:{schema_version:'native-rights-declaration-v1',workspace_id:WSP,
    project_id:PROJECT,asset_id:ASSET,asset_sha256:SHA,verified:false,owner_override_recorded:false,sha256:SHA,request,
    declaration_id:'nrd_'+'e'.repeat(32),effective_rights_status:request.claimed_rights==='restricted'?'restricted':'unknown'}};}
function harness(){class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.listeners={};this.value='';this.checked=false;}
  append(...values){this.children.push(...values);}replaceChildren(...values){this.children=values;}addEventListener(name,fn){this.listeners[name]=fn;}setAttribute(){}}
  const root=new Node('details'),dom={getElementById:()=>root,createElement:tag=>new Node(tag)},state={workspace_id:WSP,project:{id:PROJECT,revision:3},canManage:true,dirty:false,busy:false,active:false};
  const calls=[],messages=[],saved=[],working=[];let response=async(path,body)=>body?receipt(body):page();
  const controller=initializeNativeRights({dom,getState:()=>state,api:async(path,body)=>{calls.push([path,body]);return response(path,body);},uuid:()=> 'fixture-uuid-00001',
    onSaved:async value=>saved.push(value),onWorking:()=>working.push(controller?.isWorking()),onMessage:(...value)=>messages.push(value)});
  const [status,read,choice,detail,form,label,save]=root.children;
  const fields=Object.fromEntries(['claimed_source_type','claimed_rights','license','provider','source_reference','creator','attribution_requirement'].map((name,i)=>[name,form.children[i].children[0]]));
  return {controller,state,calls,messages,saved,working,status,read,choice,detail,fields,ack:label.children[0],save,handler:value=>{response=value;}};}
test('explicit rights read displays literal Vietnamese sources and owner-only form never grants verified rights',async()=>{
  const h=harness();assert.equal(h.calls.length,0);assert.equal(h.save.disabled,true);await h.controller.load();assert.equal(h.calls.length,1);
  assert.match(h.choice.children[0].textContent,/Cần Giờ/);assert.match(h.choice.children[0].textContent,/<script>/);assert.equal(h.choice.children[0].innerHTML,undefined);
  assert.match(h.status.textContent,/chặn xuất bản/);h.state.canManage=false;h.controller.controls();h.ack.checked=true;await h.save.listeners.click();assert.equal(h.calls.length,1);assert.equal(h.save.disabled,true);
  assert.equal(Object.values(h.fields).every(control=>control.disabled),true);
});
test('stable declaration key handles lost reply with exact revision and hash, reload callback clears selection and approval warning',async()=>{
  const h=harness();await h.controller.load();h.fields.claimed_rights.value='owned';h.fields.creator.value='Vang Nguyễn';h.ack.checked=true;
  let lost=true;h.handler(async(path,body)=>{if(lost)throw new Error('Explicit lost reply fixture');return receipt(body);});
  await h.controller.declare();lost=false;await h.controller.declare();const writes=h.calls.filter(([,body])=>body);
  assert.equal(writes.length,2);assert.deepEqual(writes[0][1],writes[1][1]);assert.equal(writes[0][1].revision,3);assert.equal(writes[0][1].asset_sha256,SHA);
  assert.equal(writes[0][1].creator,'Vang Nguyễn');assert.equal(writes[0][1].owner_override,undefined);assert.equal(writes[0][0],`/api/projects/${PROJECT}/rights/${ASSET}`);
  assert.equal(h.saved.length,1);assert.equal(h.ack.checked,false);assert.equal(h.save.disabled,true);assert.match(h.messages.at(-1)[0],/cần duyệt lại/);
});
test('dirty, archived, active, busy and absent project guards prohibit declaration',async()=>{
  for(const mutation of [state=>state.dirty=true,state=>state.busy=true,state=>state.active=true,state=>state.project.archived=true,state=>state.project=null]){
    const h=harness();await h.controller.load();h.ack.checked=true;mutation(h.state);h.controller.controls();await h.controller.declare();assert.equal(h.calls.length,1);assert.equal(h.saved.length,0);assert.equal(h.save.disabled,true);
  }
});
test('late foreign revisions and fabricated verification cannot update current form or apply receipt',async()=>{
  const h=harness();let release;h.handler(async()=>new Promise(resolve=>{release=resolve;}));const pending=h.controller.load();h.state.project={id:'d'.repeat(32),revision:1};h.controller.sync();release(page());await pending;
  assert.equal(h.choice.children.length,0);assert.equal(h.saved.length,0);assert.equal(h.controller.isWorking(),false);
  h.state.project={id:PROJECT,revision:3};h.controller.sync();h.handler(async()=>({...page(),workspace_id:'foreign'}));await h.controller.load();assert.equal(h.choice.children.length,0);
  h.handler(async()=>page());await h.controller.load();h.ack.checked=true;h.handler(async(path,body)=>{const value=receipt(body);value.declaration.verified=true;return value;});
  await h.controller.declare();assert.equal(h.saved.length,0);assert.equal(h.messages.at(-1)[1],true);assert.equal(h.ack.checked,true);
});
test('music intake suffix supports an explicit declaration without treating it as verified rights',async()=>{
  const h=harness(),asset='b'.repeat(32)+'.music.wav';
  h.handler(async(path,body)=>{const v=body?receipt(body):page();if(body)v.declaration.asset_id=asset;else v.items[0].asset_id=asset;return v;});
  await h.controller.load();h.fields.claimed_rights.value='owned';h.ack.checked=true;await h.controller.declare();
  assert.equal(h.saved.length,1);assert.equal(h.calls.at(-1)[0],`/api/projects/${PROJECT}/rights/${asset}`);
  assert.equal(h.saved[0].declaration.verified,false);
});
