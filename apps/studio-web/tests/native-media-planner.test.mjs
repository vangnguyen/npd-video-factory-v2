import test from 'node:test';import assert from 'node:assert/strict';
import {initializeNativeMediaPlanner,validateMediaPlanPage,mediaPlanRequest} from '../native-media-planner.mjs';
const WSP='wsp_media_plan_fixture',PROJECT='a'.repeat(32),PLAN='nmp_'+'b'.repeat(32),SHOT='shot_'+'c'.repeat(32),SHA='d'.repeat(64),ASSET='e'.repeat(32)+'.jpg';
function state(){return {workspace_id:WSP,project:{id:PROJECT,revision:5,document:{}},canEdit:true,dirty:false,busy:false,active:false};}
function page(){return {schema_version:'native-storyboard-media-page-v1',workspace_id:WSP,project_id:PROJECT,revision:5,timeline_version:0,input_sha256:SHA,
  input:{budget:{max_ai_cost_vnd:null,known_paid_exposure_vnd:'0',unknown_paid_actual_costs:0},provider_availability:{stock:{items:[]},generation:{items:[]}}},unavailable_reason:null,
  history_versions:1,external_dispatches:0,paid_operations:0,publishing_enabled:false,real_provider_tested:false,items:[{sha256:SHA,input_current:true,
    plan:{schema_version:'native-storyboard-media-plan-v1',algorithm:'native-storyboard-media-planner-v1',workspace_id:WSP,project_id:PROJECT,media_plan_id:PLAN,version:1,input_sha256:SHA,fingerprint:SHA,
      external_dispatches:0,paid_operations:0,publishing_enabled:false,semantic_vision_used:false,real_provider_tested:false,recommendation_only:true,
      items:[{shot_id:SHOT,ordinal:1,visual_brief:'AI <script> teaching',narration:'Nội dung fixture',duration_seconds:3,target_aspect_ratio:'9:16',strategy:'user_asset',fallback:['ai_image'],
        query:'Technology AI',generation_prompt:'Original AI visual',estimated_cost_vnd:null,needs_attention:true,needs_approval:false,status:'selected',selected_asset_id:ASSET,selected_asset_sha256:SHA,
        candidates:[{asset_id:ASSET,sha256:SHA,filename:'Vang Nguyễn <img onerror=x>',confidence:null,selectable:true,fixture:true,
          provenance:{license:'owner_upload_rights_attestation',provider:'user-upload',source_reference:'assets/'+ASSET,actual_native_rights_status:'unknown',rights_verification_basis:'Owner upload attestation; no independent license'}}]}]}}]};}
function harness(){class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.listeners={};this.value='';this.checked=false;}
  append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}setAttribute(name,value){this[name]=value;}addEventListener(name,fn){this.listeners[name]=fn;}
  querySelectorAll(selector){return this.children.flatMap(node=>[...(selector.split(',').includes(node.tagName.toLowerCase())?[node]:[]),...node.querySelectorAll(selector)]);}}
  const root=new Node('details'),dom={getElementById:()=>root,createElement:tag=>new Node(tag)},current=state(),calls=[],messages=[],saved=[];let answer=async()=>page();
  const controller=initializeNativeMediaPlanner({dom,getState:()=>current,api:async(path,options)=>{calls.push([path,options]);return answer(path,options);},onMessage:(...values)=>messages.push(values),
    onSaved:async()=>{saved.push(true);current.project.revision++;controller.sync();}});
  return {root,current,calls,messages,saved,controller,handler:fn=>{answer=fn;},button:text=>root.querySelectorAll('button').find(node=>node.textContent===text)};
}

test('strict scope and claims keep missing estimates null, forbid promoted evidence and unsafe asset paths',()=>{
  const current=state();assert.equal(validateMediaPlanPage(page(),current).paid_operations,0);
  for(const mutate of [value=>value.workspace_id='wsp_foreign',value=>value.revision++,value=>value.paid_operations=1,value=>value.items[0].plan.semantic_vision_used=true,
    value=>value.items[0].plan.items[0].estimated_cost_vnd='0',value=>value.items[0].plan.items[0].candidates[0].asset_id=ASSET+'/../../private']){const value=page();mutate(value);assert.throws(()=>validateMediaPlanPage(value,current));}
});
test('requests bind actual revision plan hash asset bytes and explicit apply acknowledgment without provider DTO',()=>{
  const current=state(),value=page(),args={planId:PLAN,shotId:SHOT};
  assert.deepEqual(mediaPlanRequest(current,value,'create').body,{revision:5,expected_timeline_version:0,options:{}});
  const select=mediaPlanRequest(current,value,'select',{...args,assetId:ASSET});assert.equal(select.body.expected_asset_sha256,SHA);assert.equal(select.body.expected_plan_sha256,SHA);
  assert.throws(()=>mediaPlanRequest(current,value,'apply',args));const apply=mediaPlanRequest(current,value,'apply',{...args,acknowledged:true});assert.deepEqual(apply.body.shot_ids,[SHOT]);assert.equal(apply.body.acknowledged,true);
  for(const key of ['graph','provider','service_token','result','max_ai_cost_vnd'])assert.equal(apply.body[key],undefined);
  value.items[0].input_current=false;assert.throws(()=>mediaPlanRequest(current,value,'select',{...args,assetId:ASSET}));
});
test('dirty busy active archived read-only and source projects cannot save or apply planner decisions',()=>{
  for(const changes of [{dirty:true},{busy:true},{active:true},{canEdit:false},{project:{id:PROJECT,revision:5,archived:true,document:{}}},
    {project:{id:PROJECT,revision:5,document:{canonical_timeline:{snapshot:{metadata:{native_auto_edit_schema:'native-auto-edit-timeline-v1'}}}}}}])assert.throws(()=>mediaPlanRequest({...state(),...changes},page(),'create'));
});
test('panel loads only on explicit read and renders source strings literally with no provider submission',async()=>{
  const h=harness();assert.equal(h.calls.length,0);await h.controller.load();assert.equal(h.calls.length,1);assert.equal(h.calls[0][0],`/api/projects/${PROJECT}/media-plans`);
  const candidate=h.root.querySelectorAll('option').find(node=>String(node.textContent).includes('<img'));assert.ok(candidate);assert.equal(candidate.innerHTML,undefined);
  const link=h.root.querySelectorAll('a')[0];assert.equal(link.href,`/api/projects/${PROJECT}/media/${ASSET}`);assert.equal(link.rel,'noopener');assert.equal(h.saved.length,0);
});
test('unacknowledged apply and unknown-rights selection send no write; saved apply reloads new revision',async()=>{
  const h=harness();await h.controller.load();await h.button('Áp dụng vào shot').listeners.click();assert.equal(h.calls.filter(([,options])=>options).length,0);
  const ack=h.root.querySelectorAll('input')[0];ack.checked=true;h.handler(async()=>{const next=page();next.revision=6;next.items[0].input_current=false;next.items[0].plan.version=2;return next;});
  await h.button('Áp dụng vào shot').listeners.click();assert.equal(h.saved.length,1);const [path,options]=h.calls.at(-1);assert.equal(path,`/api/projects/${PROJECT}/media-plans/${PLAN}/apply`);
  assert.equal(JSON.parse(options.body).revision,5);assert.equal(JSON.parse(options.body).acknowledged,true);assert.match(h.messages.at(-1)[0],/preview/);assert.equal(h.current.project.revision,6);
  const value=page();value.items[0].plan.items[0].candidates[0].selectable=false;value.items[0].plan.items[0].selected_asset_id=null;value.items[0].plan.items[0].selected_asset_sha256=null;
  assert.throws(()=>mediaPlanRequest(state(),value,'select',{planId:PLAN,shotId:SHOT,assetId:ASSET}),/quyền/);
});
test('late foreign response is discarded after project changes and cannot restore old choices',async()=>{
  const h=harness();let release;h.handler(()=>new Promise(resolve=>{release=resolve;}));const pending=h.controller.load();h.current.project={id:'f'.repeat(32),revision:1,document:{}};h.controller.sync();release(page());await pending;
  assert.equal(h.root.querySelectorAll('article').length,0);assert.equal(h.saved.length,0);assert.equal(h.button('Tạo kế hoạch mới').disabled,true);
});
test('read-only panel remains reviewable and blocks stale plans without automatic writes',async()=>{
  const h=harness();h.current.canEdit=false;await h.controller.load();assert.equal(h.button('Tạo kế hoạch mới').disabled,true);assert.equal(h.button('Lưu lựa chọn tư liệu').disabled,true);
  assert.equal(h.button('Tải kế hoạch').disabled,false);h.current.canEdit=true;const value=page();value.items[0].input_current=false;h.handler(async()=>value);await h.controller.load();
  assert.equal(h.button('Áp dụng vào shot').disabled,true);assert.equal(h.calls.filter(([,options])=>options).length,0);
});
test('current v2 budget fallback and prior v1 history remain distinct without promoted prices or automatic dispatch',async()=>{
  const h=harness(),value=page();value.current_algorithm='native-storyboard-media-planner-v2';value.items[0].plan.algorithm='native-storyboard-media-planner-v2';
  value.items[0].plan.items[0].new_generation_budget_blocked=['ai_image','ai_video'];value.input.budget.max_ai_cost_vnd='0';h.handler(async()=>value);await h.controller.load();
  assert.ok(h.root.querySelectorAll('p').some(node=>String(node.textContent).includes('giá ước tính')));assert.equal(h.calls.filter(([,options])=>options).length,0);
  const old=page();old.current_algorithm='native-storyboard-media-planner-v2';old.items[0].input_current=false;assert.doesNotThrow(()=>validateMediaPlanPage(old,state()));
  assert.throws(()=>mediaPlanRequest(state(),old,'apply',{planId:PLAN,shotId:SHOT,acknowledged:true}));old.items[0].input_current=true;assert.throws(()=>validateMediaPlanPage(old,state()));
});
