import test from 'node:test';import assert from 'node:assert/strict';
import {initializeNativeGeneration,supportsNativeGeneration} from '../native-generation.mjs';
const WSP='wsp_generation_fixture',PROJECT='a'.repeat(32),JOB='b'.repeat(32),SHA='e'.repeat(64),ASSET='f'.repeat(32)+'.jpg';
function config(mode='fixture',status='CONFIGURED'){const items=[];for(const [modality,operations]of [['image',['generate','image_to_image','variation','inpaint','upscale']],['video',['text_to_video','image_to_video','reference_assisted']]])
  for(const operation of operations)items.push({modality,operation,status,mode,workflow_sha256:SHA,provider_configuration_sha256:SHA});
  return {schema_version:'native-generation-providers-v1',workspace_id:WSP,ui_enablement_supported:false,automatic_attachment:false,publish_enabled:false,real_provider_tested:false,items};}
function row(status='queued'){return {schema_version:'native-generation-job-v1',generation_id:JOB,workspace_id:WSP,project_id:PROJECT,status,request_fingerprint:SHA,
  worker_wired:true,publish_enabled:false,automatic_attachment:false,real_provider_tested:false,cancel_requested:false,dispatch_started:status==='recovery_required',recovery_count:0,
  snapshot:{workspace_id:WSP,project_id:PROJECT,generation_id:JOB,selection:{mode:'fixture',provider:'comfyui-image'},request:{parameters:{modality:'image',operation:'generate'}}},
  result:status==='succeeded'?{generation_id:JOB,workspace_id:WSP,project_id:PROJECT,rights_status:'unknown',production_eligible:false,actual_cost_vnd:null,real_provider_tested:false,
    automatic_attachment:false,canonical_timeline_mutated:false,fixture:true,asset:{id:ASSET,kind:'image',sha256:SHA,rights_status:'unknown',production_eligible:false,
      needs_attention:true,explicit_fixture:true,width:640,height:360,generation_provenance:{native_generation_id:JOB}}}:null,attachment:null};}
const page=(items=[])=>({schema_version:'native-generation-page-v1',workspace_id:WSP,project_id:PROJECT,worker_wired:true,publish_enabled:false,automatic_attachment:false,items,total:items.length,has_more:false});
function harness(){class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.listeners={};this.value='';this.checked=false;this.selectedOptions=[];}
  append(...values){this.children.push(...values);}replaceChildren(...values){this.children=values;}addEventListener(name,fn){this.listeners[name]=fn;}}
  const root=new Node('details'),dom={getElementById:()=>root,createElement:tag=>new Node(tag)},state={workspace_id:WSP,project:{id:PROJECT,revision:3,document:{assets:[{id:ASSET,kind:'image',sha256:SHA,filename:'Vang Nguyễn <script>'}]}},canEdit:true,dirty:false,busy:false,active:false};
  const calls=[],messages=[],saved=[],timers=[];let response=async path=>path==='/api/generation/providers'?config():page();
  const controller=initializeNativeGeneration({dom,getState:()=>state,api:async(path,body)=>{calls.push([path,body]);return response(path,body);},onSaved:async value=>saved.push(value),
    onMessage:(...values)=>messages.push(values),uuid:()=> 'explicit-fixture-uuid-001',setTimer:fn=>{timers.push(fn);return timers.length;},clearTimer:()=>{}});
  const [status,read,operationLabel,promptLabel,negativeLabel,aspectLabel,seedLabel,referencesLabel,durationLabel,maskLabel,scaleLabel,ackLabel,create,jobsLabel,summary,preview,cancel,recoveryLabel,recover,importLabel,attach,more]=root.children;
  return {controller,state,calls,messages,saved,timers,status,read,operation:operationLabel.children[0],prompt:promptLabel.children[0],negative:negativeLabel.children[0],aspect:aspectLabel.children[0],
    seed:seedLabel.children[0],references:referencesLabel.children[0],duration:durationLabel.children[0],mask:maskLabel.children[0],scale:scaleLabel.children[0],ack:ackLabel.children[0],
    create,jobs:jobsLabel.children[0],summary,preview,cancel,recoveryAck:recoveryLabel.children[0],recover,importAck:importLabel.children[0],attach,more,handler:value=>{response=value;}};
}
test('explicit scoped catalog read has eight choices, literal asset names and no automatic generation or enablement',async()=>{
  const h=harness();assert.equal(h.calls.length,0);assert.equal(supportsNativeGeneration({capabilities:{native_generation_media:true}}),true);await h.controller.load();
  assert.equal(h.calls.length,2);assert.equal(h.operation.children.length,8);assert.match(h.status.textContent,/MÔ PHỎNG/);assert.match(h.references.children[0].textContent,/Vang Nguyễn <script>/);
  assert.equal(h.references.children[0].innerHTML,undefined);assert.equal(h.create.disabled,true);assert.equal(h.preview.children.length,0);assert.equal(h.saved.length,0);
});
test('lost create reply retains exact typed request key and fixture acknowledgment without endpoints graphs or results',async()=>{
  const h=harness();await h.controller.load();h.prompt.value='EXPLICIT PROMPT';h.ack.checked=true;let lost=true;
  h.handler(async()=>{if(lost)throw new Error('EXPLICIT LOST REPLY');return row();});await h.controller.execute('create');lost=false;await h.controller.execute('create');
  const writes=h.calls.filter(([,body])=>body);assert.equal(writes.length,2);assert.deepEqual(writes[0][1],writes[1][1]);const body=writes[0][1];
  assert.equal(body.parameters.modality,'image');assert.equal(body.parameters.operation,'generate');assert.equal(body.fixture_acknowledged,true);assert.equal(body.external_acknowledged,false);
  for(const key of ['bridge_url','service_token','graph','result','provider','workflow_id'])assert.equal(body[key],undefined);assert.equal(h.ack.checked,false);assert.equal(h.saved.length,0);
});
test('read-only dirty busy archived active and not-configured controls cannot request generation',async()=>{
  for(const changes of [{canEdit:false},{dirty:true},{busy:true},{active:true},{project:{id:PROJECT,revision:3,archived:true}}]){
    const h=harness();await h.controller.load();Object.assign(h.state,changes);h.prompt.value='EXPLICIT';h.ack.checked=true;await h.controller.execute('create');assert.equal(h.calls.filter(([,body])=>body).length,0);}
  const h=harness();h.handler(async path=>path==='/api/generation/providers'?config('official','NOT_CONFIGURED'):page());await h.controller.load();h.prompt.value='EXPLICIT';h.ack.checked=true;
  await h.controller.execute('create');assert.equal(h.calls.length,2);assert.match(h.status.textContent,/Chưa cấu hình/);
});
test('all reference modes bind owned asset hashes, explicit mask/scale and numeric video duration without source URLs',async()=>{
  for(const operation of ['image:image_to_image','image:variation','image:inpaint','image:upscale','video:image_to_video','video:reference_assisted','video:text_to_video']){
    const h=harness();await h.controller.load();h.operation.value=operation;h.prompt.value='EXPLICIT';h.ack.checked=true;h.references.selectedOptions=[{value:ASSET}];h.mask.value=ASSET;
    h.handler(async()=>row());await h.controller.execute('create');const body=h.calls.at(-1)[1];assert.deepEqual(body.parameters.references,[{asset_id:ASSET,asset_sha256:SHA}]);
    assert.equal(body.parameters.reference_images,undefined);if(operation==='image:inpaint')assert.deepEqual(body.parameters.mask,{asset_id:ASSET,asset_sha256:SHA});
    if(operation==='image:upscale')assert.equal(body.parameters.upscale_factor,2);if(operation.startsWith('video:'))assert.equal(body.parameters.duration_seconds,5);
  }
});
test('generated media is reviewed locally and explicit import receipt invalidates approval without granting rights',async()=>{
  const h=harness();h.handler(async path=>path==='/api/generation/providers'?config():page([row('succeeded')]));await h.controller.load();
  assert.equal(h.preview.children[1].src,`/api/projects/${PROJECT}/generation/${JOB}/file`);assert.equal(h.preview.children[1].tagName,'IMG');assert.equal(h.attach.disabled,true);
  h.importAck.checked=true;h.handler(async()=>({schema_version:'native-generation-import-v1',generation_id:JOB,workspace_id:WSP,project_id:PROJECT,revision:4,asset_sha256:SHA,
    approval_invalidated:true,rights_independently_verified:false,canonical_timeline_auto_edited:false,external_calls:0}));await h.controller.execute('import');
  assert.equal(h.saved.length,1);assert.equal(h.calls.at(-1)[0],`/api/projects/${PROJECT}/generation/${JOB}/import`);assert.equal(h.calls.at(-1)[1].expected_asset_sha256,SHA);assert.match(h.messages.at(-1)[0],/duyệt lại/);
});
test('explicit interrupted-job recovery calls only recovery route then existing-job read, never create',async()=>{
  const h=harness();h.handler(async path=>path==='/api/generation/providers'?config():page([row('recovery_required')]));await h.controller.load();h.recoveryAck.checked=true;
  h.handler(async(path,body)=>body?{schema_version:'native-generation-reconciliation-request-v1',generation_id:JOB,workspace_id:WSP,project_id:PROJECT,mode:'reconcile',generation_submission_authorized:false,external_calls:0}:row());
  await h.controller.execute('recover');const writes=h.calls.filter(([,body])=>body);assert.equal(writes.length,1);assert.equal(writes[0][0],`/api/projects/${PROJECT}/generation/${JOB}/recover`);
  assert.equal(writes[0][1].acknowledged,true);assert.equal(h.calls.at(-1)[0],`/api/projects/${PROJECT}/generation/${JOB}`);
});
test('late foreign scopes and promoted mock results cannot restore media choices or initiate actions',async()=>{
  const h=harness();let release;h.handler(async path=>path==='/api/generation/providers'?config():new Promise(resolve=>{release=resolve;}));const pending=h.controller.load();
  h.state.project={id:'9'.repeat(32),revision:1};h.controller.sync();release(page([row('succeeded')]));await pending;assert.equal(h.preview.children.length,0);assert.equal(h.controller.isWorking(),false);
  h.state.project={id:PROJECT,revision:3};h.controller.sync();const promoted=row('succeeded');promoted.result.asset.rights_status='owned';
  h.handler(async path=>path==='/api/generation/providers'?config():page([promoted]));await h.controller.load();assert.equal(h.preview.children.length,0);assert.equal(h.messages.at(-1)[1],true);
});
test('a missing optional workflow remains visible but disabled and nonfinite duration never dispatches',async()=>{
  const h=harness(),partial=config();partial.items[0]={...partial.items[0],status:'NOT_CONFIGURED',workflow_sha256:null};
  h.handler(async path=>path==='/api/generation/providers'?partial:page());await h.controller.load();assert.match(h.status.textContent,/MÔ PHỎNG/);assert.equal(h.create.disabled,true);
  h.operation.value='video:text_to_video';h.prompt.value='EXPLICIT';h.ack.checked=true;h.duration.value='not-a-number';await h.controller.execute('create');assert.equal(h.calls.filter(([,body])=>body).length,0);
});
