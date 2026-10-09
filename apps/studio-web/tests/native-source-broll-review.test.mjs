import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import {initializeSourceBrollReview} from '../native-source-broll-review.mjs';
import {sourceBrollRequest,sourceBrollMarkup,validateReviewedSourceBroll} from '../native-source-broll.mjs';
const fixture=JSON.parse(readFileSync(new URL('./fixtures/native-source-broll-reviewed-v1.json',import.meta.url)));
assert.equal(fixture.fixture_kind,'explicit_protocol_and_saved_asr_fixtures_not_provider_or_owner_acceptance');
const clone=v=>structuredClone(v);
function harness(){class Node{constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.listeners={};this.textContent='';this.checked=false;}
  append(...nodes){this.children.push(...nodes);}setAttribute(k,v){this.attributes[k]=v;}addEventListener(k,v){this.listeners[k]=v;}}
  const dom={createElement:tag=>new Node(tag)},root=dom.createElement('section'),state={workspace_id:fixture.workspace_id,project:clone(fixture.project),canEdit:true,dirty:false,busy:false,active:false};
  const messages=[],all=()=>{const find=n=>[n,...n.children.flatMap(find)];return find(root);},get=attr=>all().find(n=>Object.hasOwn(n.attributes,attr));let selected=clone(fixture.original_vision);
  const controller=initializeSourceBrollReview({root,dom,getState:()=>state,getReviewedVision:()=>selected,onMessage:(...v)=>messages.push(v)});
  return {root,state,controller,messages,get,all,vision:v=>{selected=v;}};
}
function acknowledge(h){h.get('data-broll-review-ack').checked=h.get('data-broll-review-mock').checked=true;}
test('initialization and local choice perform no I/O and do not accept the separate mock review',()=>{
  const h=harness();assert.deepEqual(h.controller.references(),[]);h.controller.choose();assert.throws(()=>h.controller.references());
  h.get('data-broll-review-ack').checked=true;assert.throws(()=>h.controller.references());acknowledge(h);
  const ref=h.controller.references()[0];assert.equal(ref.vision_id,fixture.original_vision.vision_id);assert.equal(ref.expected_result_sha256,fixture.original_vision.result_sha256);
  assert.equal(ref.acknowledged_reviewed_result,true);assert.equal(ref.acknowledged_protocol_mock,true);assert.equal(ref.acknowledged_external_image_analysis,undefined);
  assert.match(h.all().map(n=>n.textContent).join(' '),/không bổ sung điểm nhận diện/);assert.match(h.all().map(n=>n.textContent).join(' '),/chưa có/);
});
test('raw review and mock acknowledgements cannot coerce numeric truth or authorize provider/payment',()=>{
  for(const key of['data-broll-review-ack','data-broll-review-mock']){const h=harness();h.controller.choose();acknowledge(h);h.get(key).checked=1;assert.throws(()=>h.controller.references());}
  const h=harness();h.controller.choose();acknowledge(h);const request=sourceBrollRequest(h.state.project,'create',{reviewedVision:h.controller.references()});
  assert.deepEqual(request.payload.reviewed_vision,h.controller.references());assert.equal(request.payload.max_ai_cost_vnd,undefined);
  assert.throws(()=>sourceBrollRequest(h.state.project,'create',{reviewedVision:[{...request.payload.reviewed_vision[0],provider:'fake'}]}));
  assert.throws(()=>sourceBrollRequest(h.state.project,'create',{reviewedVision:[request.payload.reviewed_vision[0],request.payload.reviewed_vision[0]]}));
});
test('project revision workspace canonical access dirty active busy and selected-result drift clear acknowledgements',()=>{
  for(const change of[h=>h.state.project.id='f'.repeat(32),h=>h.state.project.revision++,h=>h.state.workspace_id='foreign',
    h=>h.state.project.document.canonical_timeline.sha256='f'.repeat(64),h=>h.state.canEdit=false,h=>h.state.dirty=true,
    h=>h.state.busy=true,h=>h.state.active=true,h=>h.state.project.archived=true,h=>h.vision(null)]){
    const h=harness();h.controller.choose();acknowledge(h);change(h);h.controller.sync();assert.equal(h.get('data-broll-review-ack').checked,false);
    assert.equal(h.get('data-broll-review-mock').checked,false);assert.equal(h.get('data-broll-review-clear').disabled,true);
  }
});
test('viewer and foreign/incomplete result cannot choose while clear leaves baseline request exact',()=>{
  const h=harness();h.state.canEdit=false;h.controller.sync();assert.equal(h.get('data-broll-review-pick').disabled,true);h.controller.choose();assert.throws(()=>h.controller.references());
  for(const value of[null,{...clone(fixture.original_vision),status:'approved'},{...clone(fixture.original_vision),project_id:'f'.repeat(32)}]){
    const h=harness();h.vision(value);h.controller.choose();assert.deepEqual(h.controller.references(),[]);assert.equal(h.messages.length,1);
  }
  const owned=harness();owned.controller.choose();acknowledge(owned);owned.controller.clear();assert.deepEqual(sourceBrollRequest(owned.state.project,'create'),{
    revision:owned.state.project.revision,action:'create',payload:{expected_version:owned.state.project.document.canonical_timeline.version}});
});
test('reviewed history preserves original mock lineage and refuses semantic/cost/foreign promotions',()=>{
  const original=fixture.project.document.source_broll_plans[0].plan;
  assert.doesNotThrow(()=>validateReviewedSourceBroll(clone(original),fixture.project,fixture.workspace_id));
  for(const mutate of[v=>v.provenance.semantic_vision_used=true,v=>v.provenance.reviewed_vision.items[0].mock=false,
    v=>v.provenance.reviewed_vision.original_provider_consent_renewed=true,v=>v.provenance.reviewed_vision.items[0].observed_actual_billed_cost_vnd='0',
    v=>v.publishing_blocked=false,v=>v.provenance.provider_dispatches=1,
    v=>v.items[0].provenance.supporting_candidates[0].reviewed_vision.response_sha256='f'.repeat(64),
    v=>v.items[0].provenance.supporting_candidates[0].score_basis='claimed semantic ranking']){
    const value=clone(original);mutate(value);assert.throws(()=>validateReviewedSourceBroll(value,fixture.project,fixture.workspace_id));
  }
  assert.throws(()=>validateReviewedSourceBroll(original,fixture.project,'foreign'));
  const html=sourceBrollMarkup(fixture.project,{workspaceId:fixture.workspace_id});assert.match(html,/Mô phỏng đã xem/);assert.match(html,/phản hồi/);assert.match(html,/chưa có hóa đơn thực tế/);
});
test('source status uses literal provider/source text and parent module exposes the signed review handoff',()=>{
  const h=harness(),row=clone(fixture.original_vision);row.snapshot.source.asset.filename='<img onerror=PRIVATE>';h.vision(row);h.controller.choose();
  assert.match(h.all().map(n=>n.textContent).join(' '),/<img onerror=PRIVATE>/);assert.ok(h.all().every(n=>n.innerHTML===undefined));
  const native=readFileSync(new URL('../native.mjs',import.meta.url),'utf8'),source=readFileSync(new URL('../native-source-editor.mjs',import.meta.url),'utf8'),shell=readFileSync(new URL('../shot-studio.mjs',import.meta.url),'utf8');
  assert.match(native,/sourceUI,getReviewedVision:\(\)=>officialVisionUI\?\.currentBinding/);assert.match(source,/workspace_id:getGuards\(\)\.workspace_id/);
  assert.match(shell,/initializeSourceEditor\(\{api,getProject,getGuards,getReviewedVision/);assert.match(source,/brollReview\.references\(\)/);
});
