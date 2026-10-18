import test from 'node:test';import assert from 'node:assert/strict';
import {dramaRequestHash,verifyDramaSaveReceipt,verifyDramaCastingReceipt,matchesSavedDramaProject} from '../drama-script-save.mjs';
import {createNativeProjectReload,nativeDramaSaveCallback,nativeDramaDirtyPart} from '../native.mjs';
const request={revision:1,request_key:'explicit-receipt-test-01',text:'An: Xin chào.',input_mode:'script',confirm_characters:false,narrator_enabled:false,speaker_assignments:{},character_notes:{},series:null,episode:null};
const receipt=async()=>({project_id:'a',workspace_id:'workspace-a',request_key:request.request_key,base_revision:1,revision:2,request_sha256:await dramaRequestHash(request),provider_calls:0,human_approval_granted:false});
const snapshot=()=>({id:'a',revision:2,document:{production_workflow:{series:null,episode:null},drama_script:{raw_text:request.text,input_mode:'script',characters_confirmed:false,narrator_enabled:false,character_notes:{},parsed:{lines:[]}}}});
test('receipt rejects mismatched identity, hash, revision, workspace and false approval',async()=>{
  const result=await receipt(),context={project_id:'a',workspace_id:'workspace-a',request};
  assert.equal(await verifyDramaSaveReceipt(result,context),result);
  for(const delta of [{project_id:'b'},{workspace_id:'workspace-b'},{request_key:'another-request-key'},{request_sha256:'0'.repeat(64)},{base_revision:2},{revision:3},{human_approval_granted:true},{provider_calls:1}])await assert.rejects(()=>verifyDramaSaveReceipt({...result,...delta},context));
});
test('GET payload comparison covers metadata, character notes, narrator and speaker assignments',()=>{
  assert.equal(matchesSavedDramaProject(snapshot(),request),true);
  for(const delta of [{raw_text:'Nội dung khác'},{input_mode:'idea'},{narrator_enabled:true},{character_notes:{a:'khác'}},{characters_confirmed:true}]){
    const p=snapshot();Object.assign(p.document.drama_script,delta);assert.equal(matchesSavedDramaProject(p,request),false);
  }
  const p=snapshot();p.document.production_workflow.series='other';assert.equal(matchesSavedDramaProject(p,request),false);
  assert.equal(matchesSavedDramaProject(snapshot(),{...request,speaker_assignments:{line_a:'character_a'}}),false);
});
test('late GET after workspace selection changes cannot mutate state or reset draft',async()=>{
  let release,workspace='workspace-a',updates=0,resets=0;const result=await receipt();
  const reload=createNativeProjectReload({api:()=>new Promise(r=>release=r),getState:()=>({project:{id:'a',revision:1},workspace_id:workspace,dirty:true,dirtyPart:'drama-script'}),onProject:()=>updates++,renderProject:()=>resets++,projects:async()=>{},schedule(){}});
  const saved=nativeDramaSaveCallback(reload)({kind:'saved',project_id:'a',workspace_id:'workspace-a',request,result});workspace='workspace-b';release(snapshot());
  assert.equal((await saved).status,'stale-selection');assert.equal(updates,0);assert.equal(resets,0);
});
test('verified write is not changed into an uncertain save by an unrelated project list read failure',async()=>{
  let updates=0;const result=await receipt();
  const reload=createNativeProjectReload({api:async()=>snapshot(),getState:()=>({project:{id:'a',revision:1},workspace_id:'workspace-a',dirty:true,dirtyPart:'drama-script'}),onProject:()=>updates++,renderProject:reset=>assert.equal(reset,false),projects:async()=>{throw TypeError('Explicit ancillary read failure');},schedule(){}});
  assert.equal((await nativeDramaSaveCallback(reload)({kind:'saved',project_id:'a',workspace_id:'workspace-a',request,result})).status,'saved');assert.equal(updates,1);
});
test('ordinary dirty reload retains CAS protection and uses neutral conflict wording',async()=>{
  let updates=0;const reload=createNativeProjectReload({api:async()=>snapshot(),getState:()=>({project:{id:'a',revision:1},workspace_id:'workspace-a',dirty:true}),onProject:()=>updates++,renderProject(){},projects:async()=>{},schedule(){}});
  await assert.rejects(()=>reload(true),/Dự án có phiên bản mới hơn/);assert.equal(updates,0);
});

test('casting receipt rejects a different request, scope, payload, revision or approval',async()=>{
  const req={path:'/api/projects/a/drama-casting',body:{revision:2,expected_version:1,request_key:'casting-receipt-fixture',configuration:{characters:[],lines:[],casting:[],narrator_enabled:false}}};
  const result={project_id:'a',workspace_id:'workspace-a',request_key:req.body.request_key,request_sha256:await dramaRequestHash(req.body),project_revision_at_write:3,casting:{version:2,configuration:req.body.configuration},human_approval_granted:false,provider_calls:0};
  const context={project_id:'a',workspace_id:'workspace-a',request:req};assert.equal(await verifyDramaCastingReceipt(result,context),result);
  for(const delta of [{project_id:'b'},{workspace_id:'other'},{request_key:'wrong-request'},{request_sha256:'0'.repeat(64)},{project_revision_at_write:4},{casting:{...result.casting,version:3}},{casting:{...result.casting,configuration:{...req.body.configuration,narrator_enabled:true}}},{human_approval_granted:true},{provider_calls:1}])await assert.rejects(()=>verifyDramaCastingReceipt({...result,...delta},context));
});
test('notes-only retained confirmation requires an explicit server receipt; changed content never matches',()=>{
  const p=snapshot();p.document.drama_script.characters_confirmed=true;
  assert.equal(matchesSavedDramaProject(p,request),false);assert.equal(matchesSavedDramaProject(p,request,{confirmation_preserved:true,characters_confirmed:true}),true);
  p.document.drama_script.raw_text='Changed';assert.equal(matchesSavedDramaProject(p,request,{confirmation_preserved:true,characters_confirmed:true}),false);
});
test('combined script and casting drafts keep independent dirty flags and unrelated edit guards',()=>{
  assert.equal(nativeDramaDirtyPart({script:true,casting:true},'drama-script'),'drama-both');assert.equal(nativeDramaDirtyPart({script:false,casting:true},'drama-both'),'drama');
  assert.equal(nativeDramaDirtyPart({script:true,casting:false},'drama-both'),'drama-script');assert.equal(nativeDramaDirtyPart({script:false,casting:false},'drama'),null);
  for(const flags of [{script:true,casting:true},{script:false,casting:false}])assert.equal(nativeDramaDirtyPart(flags,'shot'),'shot');
});
