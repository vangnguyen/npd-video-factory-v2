import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync}from'node:fs';
import {initializeSourceThumbnailReview,validateThumbnailReview,thumbnailInputCurrent,thumbnailSelectionRequest}from'../native-source-thumbnail-review.mjs';
const fixture=JSON.parse(readFileSync(new URL('./fixtures/native-source-thumbnail-v1.json',import.meta.url)));
assert.equal(fixture.fixture_kind,'actual_owned_pixels_original_saved_asr_and_vision_mock_not_provider_acceptance');assert.equal(fixture.projection_only,true);
const clone=v=>structuredClone(v),record=()=>clone(fixture.project.document.source_thumbnail_reviews[0]);
function harness({api}={}){
  class Node{constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.listeners={};this.textContent='';this.checked=false;this.value='';}
    append(...values){this.children.push(...values);}replaceChildren(...values){this.children=[...values];}
    setAttribute(k,v){this.attributes[k]=v;if(k==='value')this.value=v;}addEventListener(k,v){this.listeners[k]=v;}}
  const dom={createElement:tag=>new Node(tag)},root=dom.createElement('section'),state={project:clone(fixture.project),workspace_id:fixture.workspace_id,canEdit:true,dirty:false,busy:false,active:false};
  const calls=[],messages=[],projects=[];let selected=clone(fixture.main_vision);
  const all=()=>{const find=n=>[n,...n.children.flatMap(find)];return find(root);},get=key=>all().find(n=>Object.hasOwn(n.attributes,key));
  const request=api??(async(path,body)=>{calls.push({path,body});return body?{schema_version:'native-reviewed-source-thumbnail-page-v1',project_id:state.project.id,
    revision:state.project.revision,items:clone(state.project.document.source_thumbnail_reviews),selection:clone(state.project.document.source_thumbnail_selection)}:clone(state.project);});
  const controller=initializeSourceThumbnailReview({root,dom,api:request,getState:()=>state,getReviewedVision:()=>selected,
    onMessage:(...v)=>messages.push(v),onProject:p=>{projects.push(p);state.project=p;}});
  const select=()=>{get('data-thumbnail-choice').value=record().recommendation.recommendation_id;get('data-thumbnail-choice').listeners.change();
    get('data-thumbnail-frame').value=fixture.project.document.source_thumbnail_selection.frame_id;get('data-thumbnail-frame').listeners.change();};
  return {controller,state,all,get,calls,messages,projects,select,vision:v=>{selected=v;}};
}
function ackVision(h){h.get('data-thumbnail-review-ack').checked=h.get('data-thumbnail-review-mock').checked=true;}
function ackSelection(h){h.get('data-thumbnail-selection-ack').checked=h.get('data-thumbnail-selection-mock').checked=true;}
test('initialization and choice are local, saved original mock attribution and scoped pixel images are explicit',()=>{
  const h=harness();assert.deepEqual(h.calls,[]);assert.equal(thumbnailInputCurrent(record(),h.state),true);
  h.controller.choose();assert.deepEqual(h.calls,[]);assert.equal(h.get('data-thumbnail-review-ack').checked,false);h.select();
  const images=h.all().filter(n=>n.tagName==='img');assert.equal(images.length,record().recommendation.candidates.length);
  for(const image of images)assert.match(image.attributes.src,new RegExp('^/api/projects/'+fixture.project.id+'/media-frames/mfr_[a-f0-9]{24}/image$'));
  assert.match(h.all().map(n=>n.textContent).join(' '),/Hóa đơn thực tế chưa có/);assert.ok(h.all().every(n=>n.innerHTML===undefined));
});
test('saving and selecting require separate raw Vision image and mock acknowledgements with original hashes only',async()=>{
  const h=harness();h.controller.choose();await h.controller.perform('save');assert.deepEqual(h.calls,[]);
  h.get('data-thumbnail-review-ack').checked=true;await h.controller.perform('save');assert.deepEqual(h.calls,[]);
  ackVision(h);await h.controller.perform('save');assert.equal(h.calls.length,2);assert.equal(h.calls[0].body.reviewed_vision.vision_id,fixture.main_vision.vision_id);
  assert.equal(h.calls[0].body.reviewed_vision.expected_result_sha256,fixture.main_vision.result_sha256);assert.equal(h.get('data-thumbnail-review-ack').checked,false);
  h.select();await h.controller.perform('select');assert.equal(h.calls.length,2);h.get('data-thumbnail-selection-ack').checked=true;
  await h.controller.perform('select');assert.equal(h.calls.length,2);ackSelection(h);await h.controller.perform('select');assert.equal(h.calls.length,4);
  const body=h.calls[2].body;assert.equal(body.expected_sha256,record().sha256);assert.equal(body.frame_id,fixture.project.document.source_thumbnail_selection.frame_id);
  assert.equal(body.acknowledged_thumbnail,true);assert.equal(body.acknowledged_protocol_mock,true);assert.equal(body.api_key,undefined);assert.equal(body.max_operation_cost_vnd,undefined);
  assert.equal(h.get('data-thumbnail-selection-ack').checked,false);assert.equal(h.get('data-thumbnail-selection-mock').checked,false);
});
test('supporting results raw flags stale inputs foreign frames and promoted mock factors refuse requests',()=>{
  const h=harness();h.vision(clone(fixture.support_vision));h.controller.choose();assert.equal(h.get('data-thumbnail-review-save').disabled,true);
  for(const options of [{acknowledged:1,acknowledgedMock:true},{acknowledged:true,acknowledgedMock:1},{acknowledged:true,acknowledgedMock:false},
    {acknowledged:true,acknowledgedMock:true,frameId:'mfr_'+'f'.repeat(24)}]){
    assert.throws(()=>thumbnailSelectionRequest(record(),h.state,{frameId:record().recommendation.candidates[0].frame_id,...options}));
  }
  for(const change of [v=>v.recommendation.publishing_authorized=1,v=>v.recommendation.candidates[0].confidence=.99,
    v=>v.recommendation.candidates[0].provider_caption='invented genuine',v=>v.recommendation.candidates[0].source_frame.sha256='0'.repeat(64),
    v=>v.recommendation.reviewed_vision.items[0].observed_actual_billed_cost_vnd='0',v=>v.recommendation.project_id='f'.repeat(32)]){
    const value=record();change(value);assert.throws(()=>validateThumbnailReview(value,h.state));
  }
  h.state.project.document.auto_edit_analyses[0].analysis.transcript.segments[0].text+=' changed';assert.equal(thumbnailInputCurrent(record(),h.state),false);
  assert.throws(()=>thumbnailSelectionRequest(record(),h.state,{frameId:record().recommendation.candidates[0].frame_id,acknowledged:true,acknowledgedMock:true}));
});
test('identity revision canonical access dirty active busy original-choice and image-choice drift clear review',()=>{
  for(const change of [h=>h.state.workspace_id='foreign',h=>h.state.project.id='f'.repeat(32),h=>h.state.project.revision++,
    h=>h.state.project.document.canonical_timeline.sha256='0'.repeat(64),h=>h.state.canEdit=false,h=>h.state.dirty=true,
    h=>h.state.busy=true,h=>h.state.active=true,h=>h.state.project.archived=true,h=>h.vision(null)]){
    const h=harness();h.controller.choose();ackVision(h);h.select();ackSelection(h);change(h);h.controller.sync();
    assert.equal(h.get('data-thumbnail-review-ack').checked,false);assert.equal(h.get('data-thumbnail-review-mock').checked,false);
  }
  const h=harness();h.select();ackSelection(h);h.get('data-thumbnail-frame').value=record().recommendation.candidates[0].frame_id;
  h.get('data-thumbnail-frame').listeners.change();assert.equal(h.get('data-thumbnail-selection-ack').checked,false);assert.equal(h.get('data-thumbnail-selection-mock').checked,false);
  h.state.canEdit=false;h.controller.sync();assert.equal(h.get('data-thumbnail-selection-apply').disabled,true);
});
test('late replies cannot adopt another identity, source text stays literal and parent mounts served controller',async()=>{
  let release;const h=harness({api:()=>new Promise(resolve=>{release=resolve;})});h.select();ackSelection(h);const pending=h.controller.perform('select');
  h.state.canEdit=false;release({});await pending;assert.deepEqual(h.projects,[]);
  const literal=harness(),row=clone(fixture.main_vision);row.snapshot.source.asset.filename='<img onerror=PRIVATE>';literal.vision(row);literal.controller.choose();
  assert.match(literal.all().map(n=>n.textContent).join(' '),/<img onerror=PRIVATE>/);assert.ok(literal.all().every(n=>n.innerHTML===undefined));
  const parent=readFileSync(new URL('../native-source-editor.mjs',import.meta.url),'utf8');assert.match(parent,/host.append\(thumbnailRoot\)/);assert.match(parent,/thumbnailReview.isWorking\(\)/);
});
