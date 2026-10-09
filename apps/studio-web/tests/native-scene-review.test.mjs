import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync}from'node:fs';
import {initializeSceneReview,validateSceneRecommendation,sceneInputCurrent,sceneEditRequest}from'../native-scene-review.mjs';
const fixture=JSON.parse(readFileSync(new URL('./fixtures/native-scene-review-v1.json',import.meta.url)));
assert.equal(fixture.fixture_kind,'explicit_saved_source_asr_and_protocol_mock_not_provider_acceptance');
const clone=v=>structuredClone(v);
const record=()=>clone(fixture.project.document.source_scene_recommendations[0]);
const state=()=>({project:clone(fixture.project),workspace_id:fixture.workspace_id,canEdit:true,dirty:false,busy:false,active:false});
export function harness({initial=state(),api}={}){
  class Node{constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.listeners={};this.textContent='';this.checked=false;this.value='';}
    append(...values){this.children.push(...values);}replaceChildren(...values){this.children=[...values];}
    setAttribute(k,v){this.attributes[k]=v;if(k==='value')this.value=v;}addEventListener(k,v){this.listeners[k]=v;}}
  const dom={createElement:tag=>new Node(tag)},root=dom.createElement('section'),calls=[],messages=[],projects=[];let selected=clone(fixture.main_vision);
  const all=()=>{const find=n=>[n,...n.children.flatMap(find)];return find(root);},get=key=>all().find(n=>Object.hasOwn(n.attributes,key));
  const request=api??(async(path,body)=>{calls.push({path,body});return path.endsWith('/scene-reviews')?{items:[record()]}:path.endsWith('/shorts')?
    {batch:{generated_count:1,requested_count:3,drafts:[{name:'Explicit reply fixture',source_window:[0,3]}]}}:clone(initial.project);});
  const controller=initializeSceneReview({root,dom,api:request,getState:()=>initial,getReviewedVision:()=>selected,onMessage:(...v)=>messages.push(v),
    onProject:p=>{projects.push(p);initial.project=p;},onDraftsCreated:async()=>calls.push({drafts_refresh:true})});
  const select=()=>{get('data-scene-choice').value=record().recommendation.recommendation_id;get('data-scene-choice').listeners.change();};
  return {controller,root,state:initial,get,all,calls,messages,projects,select,vision:v=>{selected=v;}};
}
function ackVision(h){h.get('data-scene-review-ack').checked=h.get('data-scene-review-mock').checked=true;}
function ackRecommendation(h){h.get('data-scene-selection-ack').checked=h.get('data-scene-selection-mock').checked=true;}

test('immutable original scene/mock attribution is rendered without initializing an API or renewing consent',()=>{
  const h=harness();assert.deepEqual(h.calls,[]);assert.equal(sceneInputCurrent(record(),h.state),true);
  assert.match(h.all().map(n=>n.textContent).join(' '),/Gợi ý đã lưu · 1/);assert.match(h.all().map(n=>n.textContent).join(' '),/mô phỏng/);
  h.controller.choose();assert.deepEqual(h.calls,[]);assert.equal(h.get('data-scene-review-ack').checked,false);
  assert.equal(h.get('data-scene-review-mock').checked,false);
});
test('saving requires independent raw Vision/mock review and uses original main result without provider/payment DTO',async()=>{
  const h=harness();h.controller.choose();await h.controller.perform('save');assert.deepEqual(h.calls,[]);
  h.get('data-scene-review-ack').checked=true;await h.controller.perform('save');assert.deepEqual(h.calls,[]);
  ackVision(h);await h.controller.perform('save');assert.equal(h.calls.length,2);
  const request=h.calls[0];assert.match(request.path,/auto-edit\/scene-reviews$/);assert.equal(request.body.reviewed_vision.vision_id,fixture.main_vision.vision_id);
  assert.equal(request.body.reviewed_vision.expected_result_sha256,fixture.main_vision.result_sha256);
  assert.equal(request.body.reviewed_vision.acknowledged_protocol_mock,true);assert.equal(request.body.api_key,undefined);assert.equal(request.body.max_operation_cost_vnd,undefined);
  assert.equal(h.projects.length,1);assert.equal(h.get('data-scene-review-ack').checked,false);
  const support=harness();support.vision(clone(fixture.support_vision));support.controller.choose();assert.equal(support.get('data-scene-review-save').disabled,true);
  assert.match(support.messages[0][0],/nguồn chính/);assert.deepEqual(support.calls,[]);
});
test('reviewed highlight and Shorts requests preserve original recommendation hash and separate approval',async()=>{
  const h=harness();h.select();await h.controller.perform('apply');assert.deepEqual(h.calls,[]);ackRecommendation(h);
  const body=sceneEditRequest(record(),h.state,{highlightId:record().recommendation.result.highlights[0].highlight_id,acknowledged:true,acknowledgedMock:true});
  assert.equal(body.payload.source_window,undefined);assert.equal(body.payload.silence_decision_ids,undefined);
  assert.equal(body.payload.reviewed_scene.expected_recommendation_sha256,record().sha256);
  await h.controller.perform('apply');assert.equal(h.calls.length,1);assert.equal(h.calls[0].body.payload.reviewed_highlight_id,body.payload.reviewed_highlight_id);
  const shorts=harness();shorts.select();ackRecommendation(shorts);await shorts.controller.perform('shorts');
  assert.equal(shorts.calls[0].body.payload.count,3);assert.equal(shorts.calls[0].body.payload.maximum_duration_seconds,60);
  assert.equal(shorts.calls[0].body.payload.reviewed_scene.expected_recommendation_sha256,record().sha256);assert.deepEqual(shorts.calls[1],{drafts_refresh:true});
  assert.equal(shorts.projects.length,0);assert.match(shorts.messages.at(-1)[0],/chưa duyệt/);
});
test('raw boolean, changed input, forged original lineage and mock semantic promotion cannot create edits',()=>{
  for(const options of[{acknowledged:1,acknowledgedMock:true},{acknowledged:true,acknowledgedMock:1},{acknowledged:true,acknowledgedMock:false}]){
    assert.throws(()=>sceneEditRequest(record(),state(),{highlightId:record().recommendation.result.highlights[0].highlight_id,...options}));
  }
  for(const mutate of[v=>v.recommendation.result.semantic_vision_used=true,v=>v.recommendation.result.prediction_confidence_calibrated=1,
    v=>v.recommendation.result.scenes[0].evidence.vision_used=true,v=>v.recommendation.result.scene_ranking[0].evidence.original_response_sha256='0'.repeat(64),
    v=>v.recommendation.reviewed_vision.items[0].observed_actual_billed_cost_vnd='0']){
    const value=record();mutate(value);assert.throws(()=>validateSceneRecommendation(value,state()));
  }
  const edited=state();edited.project.document.auto_edit_analyses[0].analysis.transcript.segments[0].text+=' changed';
  assert.equal(sceneInputCurrent(record(),edited),false);assert.throws(()=>sceneEditRequest(record(),edited,{acknowledged:true,acknowledgedMock:true}));
});
test('role project revision canonical workspace dirty active busy and original choice drift clear both review acknowledgements',()=>{
  for(const change of[h=>h.state.canEdit=false,h=>h.state.project.revision++,h=>h.state.project.document.canonical_timeline.sha256='0'.repeat(64),
    h=>h.state.workspace_id='foreign',h=>h.state.dirty=true,h=>h.state.busy=true,h=>h.state.active=true,h=>h.state.project.archived=true,
    h=>h.vision(null)]){
    const h=harness();h.controller.choose();ackVision(h);h.select();ackRecommendation(h);change(h);h.controller.sync();
    assert.equal(h.get('data-scene-review-ack').checked,false);assert.equal(h.get('data-scene-review-mock').checked,false);
    if(!h.get('data-scene-review-pick').disabled)assert.deepEqual(h.calls,[]);
  }
  const viewer=harness();viewer.state.canEdit=false;viewer.controller.sync();assert.equal(viewer.get('data-scene-selection-apply').disabled,true);
});
test('late result cannot replace a changed identity and literal source/provider text is never executed',async()=>{
  let release;const h=harness({api:()=>new Promise(resolve=>{release=resolve;})});h.select();ackRecommendation(h);const pending=h.controller.perform('apply');
  h.state.canEdit=false;release(clone(fixture.project));await pending;assert.deepEqual(h.projects,[]);
  const literal=harness();const row=clone(fixture.main_vision);row.snapshot.source.asset.filename='<img onerror=PRIVATE>';literal.vision(row);literal.controller.choose();
  assert.match(literal.all().map(n=>n.textContent).join(' '),/<img onerror=PRIVATE>/);assert.ok(literal.all().every(n=>n.innerHTML===undefined));
});
test('uncertain Shorts retry keeps the same idempotency key and project changes clear local draft content',async()=>{
  const requests=[];let fail=true;
  const h=harness({api:async(path,body)=>{requests.push(body);if(fail){fail=false;throw new Error('Explicit uncertain reply fixture');}
    return {batch:{generated_count:1,requested_count:3,drafts:[{name:'Explicit independent child fixture',source_window:[0,3]}]}};}});
  h.select();ackRecommendation(h);await h.controller.perform('shorts');ackRecommendation(h);await h.controller.perform('shorts');
  assert.equal(requests[0].payload.request_key,requests[1].payload.request_key);
  assert.match(h.all().map(n=>n.textContent).join(' '),/Explicit independent child fixture/);
  h.state.project.id='0'.repeat(32);h.controller.sync();assert.doesNotMatch(h.all().map(n=>n.textContent).join(' '),/Explicit independent child fixture/);
});
