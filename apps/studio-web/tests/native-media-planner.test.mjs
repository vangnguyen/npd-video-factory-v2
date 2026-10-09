import test from 'node:test';import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {initializeNativeMediaPlanner,validateMediaPlanPage,mediaPlanRequest,reviewedVisionRequest} from '../native-media-planner.mjs';
const visionFixture=JSON.parse(readFileSync(new URL('./fixtures/native-official-vision-v1.json',import.meta.url)));
assert.equal(visionFixture.fixture_kind,'explicit_nonplayable_protocol_mock_not_provider_or_owner_acceptance');
const visionSeed=visionFixture.histories.find(row=>row.status==='succeeded');
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
function harness({enableResolution=false}={}){class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.listeners={};this.value='';this.checked=false;}
  append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}setAttribute(name,value){this[name]=value;}addEventListener(name,fn){this.listeners[name]=fn;}
  querySelectorAll(selector){return this.children.flatMap(node=>[...(selector.split(',').includes(node.tagName.toLowerCase())?[node]:[]),...node.querySelectorAll(selector)]);}}
  const root=new Node('details'),dom={getElementById:()=>root,createElement:tag=>new Node(tag)},current=state(),calls=[],messages=[],saved=[];let answer=async()=>page(),vision=null;
  const controller=initializeNativeMediaPlanner({dom,enableResolution,getState:()=>current,getReviewedVision:()=>vision,api:async(path,options)=>{calls.push([path,options]);return answer(path,options);},onMessage:(...values)=>messages.push(values),
    onSaved:async()=>{saved.push(true);current.project.revision++;controller.sync();}});
  return {root,current,calls,messages,saved,controller,handler:fn=>{answer=fn;},vision:row=>{vision=row;},
    checkbox:text=>root.querySelectorAll('label').find(node=>node.textContent===text)?.querySelectorAll('input')[0],button:text=>root.querySelectorAll('button').find(node=>node.textContent===text)};
}

test('strict scope and claims keep missing estimates null, forbid promoted evidence and unsafe asset paths',()=>{
  const current=state();assert.equal(validateMediaPlanPage(page(),current).paid_operations,0);
  for(const mutate of [value=>value.workspace_id='wsp_foreign',value=>value.revision++,value=>value.paid_operations=1,value=>value.items[0].plan.semantic_vision_used=true,
    value=>value.items[0].plan.items[0].estimated_cost_vnd='0',value=>value.items[0].plan.items[0].candidates[0].asset_id=ASSET+'/../../private']){const value=page();mutate(value);assert.throws(()=>validateMediaPlanPage(value,current));}
});
test('actual planner composition exposes explicit per-shot resolution controls without loading or writing provider jobs',async()=>{
  const h=harness({enableResolution:true}),value=page();value.items[0].plan.items[0].strategy='ai_image';value.items[0].plan.items[0].status='requires_provider';value.items[0].plan.items[0].selected_asset_id=null;value.items[0].plan.items[0].selected_asset_sha256=null;
  value.input.provider_availability.generation.items=[{modality:'image',operation:'generate',mode:'fixture',status:'CONFIGURED'}];h.handler(async()=>value);
  assert.equal(h.calls.length,0);await h.controller.load();assert.equal(h.calls.length,1);assert.ok(h.button('Tạo AI theo shot'));assert.ok(h.button('Đọc lịch sử tư liệu theo shot'));
  const query=h.root.querySelectorAll('textarea')[0];query.value='Unsaved query fixture';await h.button('Tạo AI theo shot').listeners.click();assert.equal(h.calls.length,1);assert.match(h.messages.at(-1)[0],/Lưu/);
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
  const ack=h.checkbox('Tôi đã xem tư liệu và muốn thay hình của shot này.');ack.checked=true;h.handler(async()=>{const next=page();next.revision=6;next.items[0].input_current=false;next.items[0].plan.version=2;return next;});
  await h.button('Áp dụng vào shot').listeners.click();assert.equal(h.saved.length,1);const [path,options]=h.calls.at(-1);assert.equal(path,`/api/projects/${PROJECT}/media-plans/${PLAN}/apply`);
  assert.equal(JSON.parse(options.body).revision,5);assert.equal(JSON.parse(options.body).acknowledged,true);assert.match(h.messages.at(-1)[0],/preview/);assert.equal(h.current.project.revision,6);
  const value=page();value.items[0].plan.items[0].candidates[0].selectable=false;value.items[0].plan.items[0].selected_asset_id=null;value.items[0].plan.items[0].selected_asset_sha256=null;
  assert.throws(()=>mediaPlanRequest(state(),value,'select',{planId:PLAN,shotId:SHOT,assetId:ASSET}),/quyền/);
});

// Projection derived from an explicitly mocked original fixture for UI contracts.
// Signed native tests separately validate it against the immutable original journal.
function reviewedPage(seed=visionSeed){const value=page(),record=value.items[0],plan=record.plan,request={vision_id:seed.vision_id,expected_snapshot_sha256:seed.snapshot_sha256,
  expected_result_sha256:seed.result_sha256,acknowledged_reviewed_result:true,acknowledged_protocol_mock:true},source=seed.snapshot.source,result=seed.result;
  value.workspace_id=plan.workspace_id=seed.workspace_id;value.project_id=plan.project_id=seed.project_id;
  value.current_algorithm='native-storyboard-media-planner-v2';value.supported_algorithms=['native-storyboard-media-planner-v2','native-storyboard-media-planner-v3'];
  const item={schema_version:'native-reviewed-vision-item-v1',request,workspace_id:seed.workspace_id,project_id:seed.project_id,asset_id:source.asset.id,source_sha256:source.asset.sha256,
    source_observation_sha256:source.source_observation.sha256,source_binding_sha256:seed.snapshot.input_binding.source_binding_sha256,input_binding_sha256:SHA,
    response_id:seed.response_id,response_sha256:result.response_sha256,cost_operation_id:seed.cost_operation_id,original_approved_at:seed.snapshot.approved_at,original_deadline:seed.snapshot.deadline,
    provider:'openai-vision',model:'gpt-5-mini',mock:true,semantic_inference_performed:false,frames:structuredClone(result.frames),scenes:structuredClone(result.scenes),
    best_frame_ids:result.best_frame_ids,thumbnail_candidate_ids:result.thumbnail_candidate_ids,source_frame_evidence:seed.snapshot.input_binding.source_frame_evidence,
    calculated_usage_cost_vnd:result.calculated_usage_cost_vnd,observed_actual_billed_cost_vnd:null,prediction_confidence_calibrated:false,continuous_tracking_performed:false,decoded_pts_verified:false,
    automatic_application:false,planning_authorizes_payment:false,full_media_qc_replaced:false,publishing_authorized:false,owner_uat_accepted:false,real_provider_tested:false};
  plan.schema_version='native-storyboard-media-plan-v2';plan.algorithm='native-storyboard-media-planner-v3';plan.input={schema_version:'native-storyboard-media-input-v2',
    reviewed_vision:{schema_version:'native-reviewed-vision-context-v1',workspace_id:seed.workspace_id,project_id:seed.project_id,items:[item],semantic_vision_used:false,mock_present:true,
      recommendation_only:true,automatic_application:false,external_dispatches:0,paid_operations:0,original_provider_consent_renewed:false,full_media_qc_replaced:false,publishing_authorized:false,owner_uat_accepted:false}};
  const candidate=plan.items[0].candidates[0];candidate.asset_id=plan.items[0].selected_asset_id=source.asset.id;candidate.sha256=plan.items[0].selected_asset_sha256=source.asset.sha256;
  candidate.score_basis='saved_filename_description_tags_and_uncalibrated_pixel_tiebreak';candidate.provenance.reviewed_vision={request,response_id:seed.response_id,response_sha256:result.response_sha256,
    cost_operation_id:seed.cost_operation_id,mock:true,semantic_inference_performed:false,confidence_calibrated:false,full_evidence_in:'input.reviewed_vision'};
  return value;
}
function reviewedHarness(){const h=harness();h.current.workspace_id=visionSeed.workspace_id;h.current.project.id=visionSeed.project_id;h.vision(structuredClone(visionSeed));h.controller.sync();
  h.handler(async()=>reviewedPage());return h;}
test('reviewed v3 page preserves mock evidence and refuses reclassified flags or detached candidate lineage',()=>{
  const current={...state(),workspace_id:visionSeed.workspace_id,project:{id:visionSeed.project_id,revision:5,document:{}}};assert.doesNotThrow(()=>validateMediaPlanPage(reviewedPage(),current));
  for(const mutate of[v=>v.items[0].plan.semantic_vision_used=true,v=>v.items[0].plan.input.reviewed_vision.items[0].mock=false,
    v=>v.items[0].plan.input.reviewed_vision.original_provider_consent_renewed=true,v=>v.items[0].plan.items[0].candidates[0].provenance.reviewed_vision.response_sha256='0'.repeat(64),
    v=>v.items[0].plan.items[0].candidates[0].score_basis='reviewed_provider_labels_and_uncalibrated_predicted_sample_quality',
    v=>v.items[0].plan.input.reviewed_vision.items[0].observed_actual_billed_cost_vnd='0',v=>v.supported_algorithms=['native-storyboard-media-planner-v3']]){
    const value=reviewedPage();mutate(value);assert.throws(()=>validateMediaPlanPage(value,current));}
});
test('original reviewed request requires separate raw mock and reviewed acknowledgements and exact scope',()=>{
  const current={workspace_id:visionSeed.workspace_id,project:{id:visionSeed.project_id}};
  for(const options of[{}, {acknowledgedReviewed:1,acknowledgedMock:true},{acknowledgedReviewed:true,acknowledgedMock:false},{acknowledgedReviewed:true,acknowledgedMock:1}])assert.throws(()=>reviewedVisionRequest(visionSeed,current,options));
  const request=reviewedVisionRequest(visionSeed,current,{acknowledgedReviewed:true,acknowledgedMock:true});assert.equal(request.expected_result_sha256,visionSeed.result_sha256);
  assert.equal(request.acknowledged_reviewed_result,true);assert.equal(request.max_operation_cost_vnd,undefined);
  assert.throws(()=>reviewedVisionRequest(visionSeed,{...current,project:{id:PROJECT}},{acknowledgedReviewed:true,acknowledgedMock:true}));
});
test('choosing reviewed Vision is local and only an explicitly acknowledged new plan sends references',async()=>{
  const h=reviewedHarness();await h.controller.load();const count=h.calls.length;await h.button('Chọn kết quả Vision đang xem').listeners.click();assert.equal(h.calls.length,count);
  await h.button('Tạo kế hoạch mới').listeners.click();assert.equal(h.calls.length,count);
  h.checkbox('Tôi đã xem kết quả Vision và muốn dùng cho kế hoạch mới.').checked=true;
  await h.button('Tạo kế hoạch mới').listeners.click();assert.equal(h.calls.length,count);
  h.checkbox('Tôi hiểu mô phỏng không bổ sung điểm nhận diện hoặc chất lượng thật.').checked=true;
  h.handler(async()=>{const next=reviewedPage();next.revision=6;return next;});await h.button('Tạo kế hoạch mới').listeners.click();
  assert.equal(h.calls.length,count+1);const body=JSON.parse(h.calls.at(-1)[1].body);assert.deepEqual(body.reviewed_vision,[reviewedVisionRequest(visionSeed,h.current,{acknowledgedReviewed:true,acknowledgedMock:true})]);
  assert.equal(h.calls.some(([path])=>path.endsWith('/process')),false);assert.equal(body.acknowledged_external_image_analysis,undefined);
  assert.equal(h.checkbox('Tôi đã xem kết quả Vision và muốn dùng cho kế hoạch mới.').checked,false);
});
test('context access and selection drift clear local Vision acknowledgements without provider actions',async()=>{
  for(const mutate of[h=>h.current.project.revision++,h=>h.current.canEdit=false,h=>h.current.dirty=true,h=>h.current.busy=true,
    h=>h.current.active=true,h=>h.current.project.archived=true,h=>h.vision(null)]){
    const h=reviewedHarness();await h.controller.load();await h.button('Chọn kết quả Vision đang xem').listeners.click();
    h.checkbox('Tôi đã xem kết quả Vision và muốn dùng cho kế hoạch mới.').checked=true;h.checkbox('Tôi hiểu mô phỏng không bổ sung điểm nhận diện hoặc chất lượng thật.').checked=true;
    const count=h.calls.length;mutate(h);h.controller.sync();assert.equal(h.checkbox('Tôi đã xem kết quả Vision và muốn dùng cho kế hoạch mới.').checked,false);assert.equal(h.calls.length,count);
  }
});
test('literal reviewed mock result remains visible in history without automatically choosing it',async()=>{
  const h=reviewedHarness();await h.controller.load();assert.equal(h.checkbox('Tôi đã xem kết quả Vision và muốn dùng cho kế hoạch mới.').checked,false);
  assert.ok(h.root.querySelectorAll('p').some(node=>String(node.textContent).includes('không bổ sung điểm nhận diện')));assert.equal(h.calls.length,1);
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
