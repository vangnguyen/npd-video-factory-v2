import test from 'node:test';import assert from 'node:assert/strict';
import {initializeNativeRightsOverride} from '../native-rights-override.mjs';
const WSP='wsp_native_override_fixture',PROJECT='a'.repeat(32),ASSET='b'.repeat(32)+'.jpg',SHA='c'.repeat(64);
function page(enabled=true){return{schema_version:'native-owner-rights-review-v1',workspace_id:WSP,project_id:PROJECT,revision:3,enabled,
  publishing_enabled:false,rights_independently_verified:false,external_calls:0,history:[],items:[{asset_id:ASSET,asset_sha256:SHA,
    rights_sha256:SHA,fixture:false,rights_status:'unknown',filename:'Cần Giờ · <script>',active_override:null}]};}
function receipt(body){const{request_key,...request}=body;return{schema_version:'native-owner-rights-override-v1',workspace_id:WSP,project_id:PROJECT,revision:4,
  approval_invalidated:true,media_bytes_changed:false,external_calls:0,record:{schema_version:'native-owner-rights-override-v1',workspace_id:WSP,project_id:PROJECT,
    override_id:'nro_'+'e'.repeat(32),asset_id:ASSET,asset_sha256:SHA,sha256:SHA,rights_independently_verified:false,publishing_authorized:false,request}};}
function harness(){class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.listeners={};this.value='';this.checked=false;}
  append(...values){this.children.push(...values);}replaceChildren(...values){this.children=values;}addEventListener(name,fn){this.listeners[name]=fn;}setAttribute(){}}
  const root=new Node('details'),dom={getElementById:()=>root,createElement:tag=>new Node(tag)},state={workspace_id:WSP,project:{id:PROJECT,revision:3},canManage:true,dirty:false,busy:false,active:false},calls=[],saved=[],messages=[];
  let response=async(path,body)=>body?receipt(body):page();
  const controller=initializeNativeRightsOverride({dom,getState:()=>state,api:async(path,body)=>{calls.push([path,body]);return response(path,body);},uuid:()=> 'fixture-uuid-01',
    onSaved:async value=>saved.push(value),onMessage:(...value)=>messages.push(value)});
  const[status,read,choice,detail,form,label,grant,revoke]=root.children;
  const[reason,reference,days,publish]=form.children.map(row=>row.children[0]);
  return{controller,state,calls,saved,messages,status,read,choice,detail,reason,reference,days,publish,ack:label.children[0],grant,revoke,handler:fn=>{response=fn;}};
}
function fill(h){h.reason.value='EXPLICIT SYNTHETIC OWNER DECISION, NO ACTUAL LEGAL REVIEW';h.reference.value='document://explicit-fixture';h.ack.checked=true;h.controller.controls();}
test('explicit read shows literal Vietnamese, default disabled and no automatic enablement or grant',async()=>{
  const h=harness();assert.equal(h.calls.length,0);h.handler(async()=>page(false));await h.controller.load();fill(h);
  assert.equal(h.grant.disabled,true);assert.equal(h.revoke.disabled,true);assert.match(h.status.textContent,/đang tắt/);assert.match(h.choice.children[0].textContent,/Cần Giờ/);
  assert.match(h.choice.children[0].textContent,/<script>/);assert.equal(h.choice.children[0].innerHTML,undefined);await h.controller.record('grant');assert.equal(h.calls.length,1);
});
test('stable request key binds revision/hash/rights/expiry and separate publishing review acknowledgment',async()=>{
  const h=harness();await h.controller.load();fill(h);h.days.value='9';h.publish.checked=true;let lost=true;
  h.handler(async(path,body)=>{if(lost)throw new Error('EXPLICIT LOST RESPONSE FIXTURE');return receipt(body);});await h.controller.record('grant');lost=false;await h.controller.record('grant');
  const writes=h.calls.filter(([,body])=>body);assert.equal(writes.length,2);assert.deepEqual(writes[0][1],writes[1][1]);assert.equal(writes[0][1].valid_days,9);
  assert.equal(writes[0][1].revision,3);assert.equal(writes[0][1].asset_sha256,SHA);assert.equal(writes[0][1].expected_rights_sha256,SHA);assert.equal(writes[0][1].allow_publishing_review,true);
  assert.equal(writes[0][1].publishing_authorized,undefined);assert.equal(writes[0][1].enabled,undefined);assert.equal(h.saved.length,1);assert.match(h.messages.at(-1)[0],/duyệt lại/);
});
test('disabled configuration still supports explicit revoke with frozen grant digest',async()=>{
  const h=harness(),value=page(false),grant=receipt({revision:2,asset_sha256:SHA,expected_rights_sha256:SHA,action:'grant',acknowledged:true}).record;
  value.history=[grant];h.handler(async(path,body)=>body?receipt(body):value);await h.controller.load();fill(h);assert.equal(h.grant.disabled,true);assert.equal(h.revoke.disabled,false);
  await h.controller.record('revoke');const body=h.calls.at(-1)[1];assert.equal(body.override_id,grant.override_id);assert.equal(body.expected_override_sha256,SHA);
  assert.equal(body.action,'revoke');assert.equal(body.allow_publishing_review,false);assert.equal(h.saved.length,1);
});
test('readonly, dirty, archived, busy, active, fixture and restricted states guard writes',async()=>{
  for(const change of[h=>h.state.canManage=false,h=>h.state.dirty=true,h=>h.state.busy=true,h=>h.state.active=true,h=>h.state.project.archived=true,
    h=>h.handler(async()=>{const v=page();v.items[0].fixture=true;return v;}),h=>h.handler(async()=>{const v=page();v.items[0].rights_status='restricted';return v;})]){
    const h=harness();change(h);await h.controller.load();fill(h);await h.controller.record('grant');assert.equal(h.saved.length,0);assert.equal(h.calls.filter(([,body])=>body).length,0);
  }
});
test('late foreign context and forged verified receipt cannot alter current workspace',async()=>{
  const h=harness();let release;h.handler(async()=>new Promise(resolve=>{release=resolve;}));const pending=h.controller.load();h.state.project={id:'d'.repeat(32),revision:1};h.controller.sync();release(page());await pending;
  assert.equal(h.choice.children.length,0);h.state.project={id:PROJECT,revision:3};h.controller.sync();h.handler(async()=>({...page(),workspace_id:'foreign'}));await h.controller.load();assert.equal(h.choice.children.length,0);
  h.handler(async()=>page());await h.controller.load();fill(h);h.handler(async(path,body)=>{const value=receipt(body);value.record.rights_independently_verified=true;return value;});
  await h.controller.record('grant');assert.equal(h.saved.length,0);assert.equal(h.messages.at(-1)[1],true);
});
