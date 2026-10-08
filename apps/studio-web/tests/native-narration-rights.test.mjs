import test from 'node:test';import assert from 'node:assert/strict';
import {initializeNativeNarrationRights,narrationRightsRequest,validateNarrationRightsPage} from '../native-narration-rights.mjs';
const W='wsp_native_voice_unit',P='a'.repeat(32),J='b'.repeat(32),S='c'.repeat(64);
function page(enabled=true){return {schema_version:'native-narration-rights-review-v1',workspace_id:W,project_id:P,revision:3,enabled,publishing_enabled:false,
  rights_independently_verified:false,speech_quality_accepted:false,external_calls:0,history:[],active_exception:null,provenance_sha256:S,
  provenance:{schema_version:'native-narration-publication-provenance-v1',workspace_id:W,project_id:P,narration_job_id:J,voice_audio_sha256:S,profile_sha256:S,
    explicit_fixture:false,rights_status:'unknown',rights_independently_verified:false,speech_quality_accepted:false,publishing_authorized:false,profile:{voice_id:'Thùy Dung <script>'}}};}
function receipt(body){const {request_key,...request}=body;return {schema_version:'native-narration-rights-exception-v1',workspace_id:W,project_id:P,revision:4,
  approval_invalidated:true,media_bytes_changed:false,external_calls:0,record:{schema_version:'native-narration-rights-exception-v1',workspace_id:W,project_id:P,
    exception_id:'nvr_'+'d'.repeat(32),narration_job_id:J,provenance_sha256:S,sha256:S,provenance:page().provenance,request,
    rights_independently_verified:false,speech_quality_accepted:false,publishing_authorized:false}};}
function harness(){class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.value='';this.checked=false;}
  append(...v){this.children.push(...v);}addEventListener(k,f){this.listeners[k]=f;}}
  const root=new Node('details'),dom={getElementById:()=>root,createElement:tag=>new Node(tag)},state={workspace_id:W,project:{id:P,revision:3,document:{}},canManage:true,dirty:false,busy:false,active:false},calls=[],saved=[],messages=[];
  let response=async(path,options)=>options?receipt(JSON.parse(options.body)):page();
  const controller=initializeNativeNarrationRights({dom,getState:()=>state,api:async(path,options)=>{calls.push([path,options]);return response(path,options);},
    newKey:()=> 'explicit-unit-key-01',onSaved:async value=>saved.push(value),onMessage:(...value)=>messages.push(value)});
  const[, ,status,read,detail,form,grant,revoke]=root.children;const[reason,reference,days,publish,ack]=form.children.map(n=>n.children[0]);
  return {controller,state,calls,saved,messages,status,read,detail,reason,reference,days,publish,ack,grant,revoke,handler:f=>{response=f;}};
}
function fill(h){h.reason.value='EXPLICIT UNIT OWNER EXCEPTION; NO LEGAL ACCEPTANCE';h.reference.value='document://explicit-unit';h.ack.checked=true;h.controller.controls();}
test('manual read, literal Vietnamese evidence, default disabled and no automatic grant',async()=>{
  const h=harness();assert.equal(h.calls.length,0);h.handler(async()=>page(false));await h.controller.load();fill(h);await h.controller.record('grant');
  assert.equal(h.calls.length,1);assert.equal(h.grant.disabled,true);assert.match(h.detail.textContent,/Thùy Dung <script>/);assert.equal(h.detail.innerHTML,undefined);assert.match(h.status.textContent,/đang tắt/);
});
test('lost reply retains exact acknowledged model/PCM/revision exception request without automatic retry',async()=>{
  const h=harness();await h.controller.load();fill(h);h.publish.checked=true;h.days.value='4';let lost=true;
  h.handler(async(path,options)=>{if(lost)throw new Error('EXPLICIT LOST REPLY');return receipt(JSON.parse(options.body));});await h.controller.record('grant');assert.equal(h.saved.length,0);
  lost=false;await h.controller.record('grant');const writes=h.calls.filter(([,o])=>o);assert.equal(writes.length,2);assert.deepEqual(writes[0],writes[1]);
  const body=JSON.parse(writes[1][1].body);assert.equal(body.expected_provenance_sha256,S);assert.equal(body.narration_job_id,J);assert.equal(body.valid_days,4);assert.equal(body.allow_publishing_review,true);
  assert.equal(body.enabled,undefined);assert.equal(body.actor_ref,undefined);assert.equal(body.publishing_authorized,undefined);assert.equal(h.saved.length,1);assert.match(h.messages.at(-1)[0],/preview có tiếng/);
});
test('revoke remains explicit with disabled or stale preparation and exact earlier grant digest',async()=>{
  const h=harness(),v=page(false),grant=receipt({revision:2,action:'grant',acknowledged:true}).record;v.history=[grant];v.provenance=v.provenance_sha256=null;
  h.handler(async(path,options)=>options?receipt(JSON.parse(options.body)):v);await h.controller.load();fill(h);assert.equal(h.revoke.disabled,false);assert.equal(h.grant.disabled,true);
  await h.controller.record('revoke');const body=JSON.parse(h.calls.at(-1)[1].body);assert.equal(body.exception_id,grant.exception_id);assert.equal(body.expected_exception_sha256,S);
  assert.equal(body.narration_job_id,J);assert.equal(body.allow_publishing_review,false);assert.equal(h.saved.length,1);
});
test('read-only dirty active archived fixture and foreign or forged claims guard all writes',async()=>{
  for(const change of [h=>h.state.canManage=false,h=>h.state.dirty=true,h=>h.state.active=true,h=>h.state.project.archived=true,h=>h.handler(async()=>{const p=page();p.provenance.explicit_fixture=true;return p;})]){
    const h=harness();change(h);await h.controller.load();fill(h);await h.controller.record('grant');assert.equal(h.calls.filter(([,o])=>o).length,0);
  }
  const h=harness();h.handler(async()=>({...page(),workspace_id:'foreign'}));await h.controller.load();assert.equal(h.detail.textContent,'');
  h.handler(async()=>page());await h.controller.load();fill(h);h.handler(async(path,options)=>{const r=receipt(JSON.parse(options.body));r.record.speech_quality_accepted=true;return r;});await h.controller.record('grant');assert.equal(h.saved.length,0);
});
test('late previous project evidence is discarded and request validation is strict',async()=>{
  const h=harness();let release;h.handler(async()=>new Promise(r=>{release=r;}));const pending=h.controller.load();h.state.project={id:'e'.repeat(32),revision:1,document:{}};h.controller.sync();release(page());await pending;assert.equal(h.detail.textContent,'');
  h.state.project={id:P,revision:3,document:{}};assert.throws(()=>validateNarrationRightsPage({...page(),publishing_enabled:true},h.state));
  for(const changes of [{acknowledged:1},{days:1.5},{days:31},{allowPublishingReview:1},{requestKey:'short'},{reason:'short'}])assert.throws(()=>narrationRightsRequest(h.state,page(),'grant',
    {reason:'EXPLICIT UNIT DECISION',reference:'document://unit',days:7,acknowledged:true,requestKey:'native-unit-request-key',...changes}));
});
