import test from 'node:test';import assert from 'node:assert/strict';
import {validateResolution,resolutionRequest,initializeNativeMediaResolution} from '../native-media-resolution.mjs';
const WSP='wsp_resolution_fixture',PROJECT='a'.repeat(32),PLAN='nmp_'+'b'.repeat(32),SHOT='shot_'+'c'.repeat(32),RES='nmr_'+'d'.repeat(32),CHILD='e'.repeat(32),SHA='f'.repeat(64),ASSET='1'.repeat(32)+'.jpg',STOCK='nstk_'+'2'.repeat(32),CAND='smc_'+'3'.repeat(24);
function state(){return {workspace_id:WSP,project:{id:PROJECT,revision:5,document:{}},canEdit:true,canManage:true,dirty:false,busy:false,active:false};}
function plan(){return {workspace_id:WSP,project_id:PROJECT,revision:5,input:{provider_availability:{generation:{items:[{modality:'image',operation:'generate',mode:'fixture',status:'CONFIGURED'}]},stock:{items:[{provider:'pexels',mode:'fixture',status:'CONFIGURED'}]}}},items:[{sha256:SHA,input_current:true,plan:{media_plan_id:PLAN,version:1,items:[{shot_id:SHOT,ordinal:1,strategy:'ai_image',duration_seconds:3,selected_asset_id:null,new_generation_budget_blocked:[]}]}}]};}
function resolution(){return {binding:{schema_version:'native-storyboard-media-resolution-v1',resolution_id:RES,workspace_id:WSP,project_id:PROJECT,media_plan_id:PLAN,plan_version:1,plan_sha256:SHA,plan_fingerprint:SHA,input_sha256:SHA,shot_id:SHOT,revision:5,document_sha256:SHA,request_fingerprint:SHA,child_kind:'generation',child_id:CHILD,child_fingerprint:SHA,child_request_sha256:SHA,automatic_attachment:false,automatic_timeline_apply:false,provider_calls_at_creation:0,paid_operations_at_creation:0},binding_sha256:SHA,child:{schema_version:'native-generation-job-v1',generation_id:CHILD,workspace_id:WSP,project_id:PROJECT,request_fingerprint:SHA,snapshot:{request:{revision:5},document_sha256:SHA,selection:{mode:'fixture'}},status:'queued',automatic_attachment:false,result:null,attachment:null},automatic_attachment:false,automatic_timeline_apply:false,real_provider_acceptance_complete:false};}
function result(){const value=resolution();value.child.status='succeeded';value.child.result={asset:{id:ASSET,sha256:SHA,rights_status:'unknown',production_eligible:false},actual_cost_vnd:null};return value;}
function search(){const value=resolution();value.binding.child_kind='stock_search';value.binding.child_id=STOCK;value.child.schema_version='native-stock-job-v1';delete value.child.generation_id;value.child.stock_id=STOCK;value.child.status='succeeded';value.child.snapshot.provider='pexels';value.child.snapshot.provider_mode='fixture';value.child.result_sha256=SHA;value.child.result={mock:true,candidates:[{candidate_id:CAND,provider_asset_id:'11',license:'EXPLICIT FIXTURE <img onerror=x>',media_type:'image'}],candidate_sha256:{[CAND]:SHA}};return value;}
function harness(){class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.listeners={};this.value='';this.checked=false;}append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}setAttribute(name,value){this[name]=value;}addEventListener(name,fn){this.listeners[name]=fn;}querySelectorAll(selector){return this.children.flatMap(node=>[...(selector.split(',').includes(node.tagName.toLowerCase())?[node]:[]),...node.querySelectorAll(selector)]);}}
  const root=new Node('section'),current=state(),saved=[],messages=[],calls=[],page=plan(),dom={createElement:tag=>new Node(tag)};let reply=async()=>({schema_version:'native-storyboard-media-resolutions-page-v1',workspace_id:WSP,project_id:PROJECT,items:[],automatic_attachment:false,automatic_timeline_apply:false});
  const controller=initializeNativeMediaResolution({root,dom,getState:()=>current,getPlanPage:()=>page,uuid:()=> 'explicit-fixture-key-01',api:async(path,options)=>{calls.push([path,options]);return reply(path,options);},onMessage:(...values)=>messages.push(values),onSaved:async()=>{saved.push(true);current.project.revision++;controller.sync();}});
  return {root,current,saved,messages,calls,page,controller,reply:fn=>{reply=fn;},button:text=>root.querySelectorAll('button').find(node=>node.textContent===text),scene:(options={})=>controller.scene(page.items[0],page.items[0].plan.items[0],root,options)};
}
test('immutable scope and child bindings reject foreign results, unsafe paths and promoted execution',()=>{
  assert.equal(validateResolution(resolution(),state()).binding.child_id,CHILD);
  for(const change of [v=>v.binding.workspace_id='foreign',v=>v.child.project_id='9'.repeat(32),v=>v.child.request_fingerprint='0'.repeat(64),v=>v.binding.provider_calls_at_creation=1,v=>v.automatic_timeline_apply=true,v=>v.child.result={asset:{id:'../../private',sha256:SHA}}]){const value=resolution();change(value);assert.throws(()=>validateResolution(value,state()));}
});
test('generation uses saved plan and exact seed with explicit fixture acknowledgement, never a client graph or price',()=>{
  const args={planId:PLAN,shotId:SHOT,seed:19,acknowledged:true},request=resolutionRequest(state(),plan(),'generate',args,'explicit-fixture-key-01');
  assert.equal(request.path,`/api/projects/${PROJECT}/media-plans/${PLAN}/resolve/generate`);assert.equal(request.body.expected_plan_sha256,SHA);assert.equal(request.body.seed,19);assert.equal(request.body.fixture_acknowledged,true);assert.equal(request.body.external_acknowledged,false);
  for(const key of ['prompt','query','graph','provider_url','estimated_cost_vnd','result'])assert.equal(request.body[key],undefined);
  assert.throws(()=>resolutionRequest(state(),plan(),'generate',{...args,acknowledged:false},'explicit-fixture-key-01'));
  const finite=plan();finite.items[0].plan.items[0].new_generation_budget_blocked=['ai_image'];assert.throws(()=>resolutionRequest(state(),finite,'generate',args,'explicit-fixture-key-01'));
});
test('stock download binds the server candidate digest and exact parent plan, retaining Owner permission',()=>{
  const page=plan();page.items[0].plan.items[0].strategy='stock_image';const parent=search(),args={planId:PLAN,shotId:SHOT,resolution:parent,candidateId:CAND,acknowledged:true};
  const request=resolutionRequest(state(),page,'download',args,'explicit-fixture-key-01');assert.equal(request.body.expected_candidate_sha256,SHA);assert.equal(request.body.expected_result_sha256,SHA);assert.equal(request.body.parent_resolution_id,RES);
  assert.throws(()=>resolutionRequest({...state(),canManage:false},page,'download',args,'explicit-fixture-key-01'));parent.binding.plan_sha256='0'.repeat(64);assert.throws(()=>resolutionRequest(state(),page,'download',args,'explicit-fixture-key-01'));
});
test('explicit result import needs current revision, exact bytes and acknowledgement while ignoring a legitimately stale plan',()=>{
  const current=state();current.project.revision=6;const request=resolutionRequest(current,null,'import',{resolution:result(),acknowledged:true},'explicit-fixture-key-01');assert.equal(request.body.revision,6);assert.equal(request.body.expected_binding_sha256,SHA);assert.equal(request.body.expected_asset_sha256,SHA);
  assert.throws(()=>resolutionRequest(current,null,'import',{resolution:result(),acknowledged:false},'explicit-fixture-key-01'));
  for(const changes of [{dirty:true},{busy:true},{active:true},{canEdit:false}])assert.throws(()=>resolutionRequest({...current,...changes},null,'import',{resolution:result(),acknowledged:true},'explicit-fixture-key-01'));
});
test('scene controls execute only after acknowledgement and require saving modified plan drafts',async()=>{
  const h=harness();h.scene({isDraftChanged:()=>true});await h.button('Tạo AI theo shot').listeners.click();assert.equal(h.calls.length,0);assert.match(h.messages.at(-1)[0],/Lưu/);
  const ready=harness();ready.scene();await ready.button('Tạo AI theo shot').listeners.click();assert.equal(ready.calls.length,0);ready.root.querySelectorAll('input').find(node=>node.type==='checkbox').checked=true;ready.reply(async()=>resolution());await ready.button('Tạo AI theo shot').listeners.click();assert.equal(ready.calls.length,1);assert.equal(ready.saved.length,0);
  assert.equal(JSON.parse(ready.calls[0][1].body).expected_plan_sha256,SHA);assert.match(ready.root.querySelectorAll('p').map(node=>node.textContent).join(' '),/MÔ PHỎNG/);
});
test('lost reply permits explicit replay with the same body and key, and never submits automatically',async()=>{
  const h=harness();h.scene();h.root.querySelectorAll('input').find(node=>node.type==='checkbox').checked=true;h.reply(async()=>{throw new Error('Explicit lost response fixture');});await h.button('Tạo AI theo shot').listeners.click();assert.equal(h.calls.length,1);
  const body=h.calls[0][1].body;h.reply(async()=>resolution());await h.button('Đối soát phản hồi chưa nhận').listeners.click();assert.equal(h.calls.length,2);assert.equal(h.calls[1][1].body,body);assert.equal(h.saved.length,0);
});
test('history renders evidence literally and discards delayed foreign replies on project switch',async()=>{
  const h=harness();let release;h.reply(()=>new Promise(resolve=>{release=resolve;}));const pending=h.controller.load();h.current.project={id:'9'.repeat(32),revision:1,document:{}};h.controller.sync();release({schema_version:'native-storyboard-media-resolutions-page-v1',workspace_id:WSP,project_id:PROJECT,items:[result()],automatic_attachment:false,automatic_timeline_apply:false});await pending;
  assert.equal(h.root.querySelectorAll('article').length,0);assert.equal(h.saved.length,0);
  const next=harness();next.reply(async()=>({schema_version:'native-storyboard-media-resolutions-page-v1',workspace_id:WSP,project_id:PROJECT,items:[search()],automatic_attachment:false,automatic_timeline_apply:false}));await next.controller.load();assert.ok(next.root.querySelectorAll('p').some(node=>String(node.textContent).includes('<img')));assert.equal(next.root.querySelectorAll('p').find(node=>String(node.textContent).includes('<img')).innerHTML,undefined);
});
test('history import refreshes project and tells the user to review rights and replan',async()=>{
  const h=harness();h.reply(async()=>({schema_version:'native-storyboard-media-resolutions-page-v1',workspace_id:WSP,project_id:PROJECT,items:[result()],automatic_attachment:false,automatic_timeline_apply:false}));await h.controller.load();await h.button('Thêm kết quả vào dự án').listeners.click();assert.equal(h.calls.length,1);
  h.root.querySelectorAll('input').find(node=>node.type==='checkbox').checked=true;h.reply(async()=>({...result(),replan_required:true}));await h.button('Thêm kết quả vào dự án').listeners.click();assert.equal(h.saved.length,1);assert.equal(h.current.project.revision,6);assert.match(h.messages.at(-1)[0],/quyền/);assert.equal(h.root.querySelectorAll('article').length,0);
});
test('previously loaded stock results rebind download controls when the matching plan becomes current without a network write',async()=>{
  const h=harness();h.page.items[0].plan.items[0].strategy='stock_image';h.page.items[0].input_current=false;
  h.reply(async()=>({schema_version:'native-storyboard-media-resolutions-page-v1',workspace_id:WSP,project_id:PROJECT,items:[search()],automatic_attachment:false,automatic_timeline_apply:false}));
  await h.controller.load();assert.equal(h.button('Tải stock đã chọn').disabled,true);h.page.items[0].input_current=true;h.controller.refresh();assert.equal(h.button('Tải stock đã chọn').disabled,false);assert.equal(h.calls.length,1);
  h.current.canManage=false;h.controller.controls();assert.equal(h.button('Tải stock đã chọn').disabled,true);
});
