import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync}from'node:fs';
import {initializeSourceCropReview}from'../native-source-crop-review.mjs';
const fixture=JSON.parse(readFileSync(new URL('./fixtures/native-scene-review-v1.json',import.meta.url)));
assert.equal(fixture.fixture_kind,'explicit_saved_source_asr_and_protocol_mock_not_provider_acceptance');
const clone=v=>structuredClone(v);
function harness(){
  class Node{constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.listeners={};this.textContent='';this.checked=false;this.value='';}
    append(...values){this.children.push(...values);}setAttribute(k,v){this.attributes[k]=v;}addEventListener(k,v){this.listeners[k]=v;}}
  const dom={createElement:tag=>new Node(tag)},root=dom.createElement('section'),state={project:clone(fixture.project),workspace_id:fixture.workspace_id,canEdit:true,dirty:false,busy:false,active:false};
  const messages=[];let selected=clone(fixture.main_vision);const all=()=>{const find=n=>[n,...n.children.flatMap(find)];return find(root);},get=key=>all().find(n=>Object.hasOwn(n.attributes,key));
  const controller=initializeSourceCropReview({root,dom,getState:()=>state,getReviewedVision:()=>selected,onMessage:(...v)=>messages.push(v)});
  return{controller,state,messages,all,get,vision:v=>{selected=v;}};
}
function ack(h){h.get('data-crop-review-ack').checked=h.get('data-crop-review-mock').checked=true;h.controller.controls();}
test('choose is local, independent mock review is required, all four formats bind original result and both versions',()=>{
  const h=harness();assert.throws(()=>h.controller.request());h.controller.choose();assert.equal(h.get('data-reframe-reviewed-apply').disabled,true);
  h.get('data-crop-review-ack').checked=true;assert.throws(()=>h.controller.request());ack(h);
  for(const ratio of ['9:16','16:9','1:1','4:5']){h.get('data-crop-review-ratio').value=ratio;const body=h.controller.request();
    assert.equal(body.action,'reframe');assert.equal(body.revision,fixture.project.revision);assert.equal(body.payload.expected_version,fixture.project.document.canonical_timeline.version);
    assert.equal(body.payload.mode,'reviewed_vision');assert.equal(body.payload.aspect_ratio,ratio);assert.deepEqual(body.payload.points,[]);
    assert.equal(body.payload.reviewed_vision.vision_id,fixture.main_vision.vision_id);assert.equal(body.payload.reviewed_vision.expected_result_sha256,fixture.main_vision.result_sha256);
    assert.equal(body.payload.api_key,undefined);assert.equal(body.payload.max_operation_cost_vnd,undefined);
  }
  assert.match(h.all().map(n=>n.textContent).join(' '),/chưa có tracking liên tục/);assert.match(h.all().map(n=>n.textContent).join(' '),/Hóa đơn thực tế chưa có/);
});
test('raw boolean review refusal and changed workspace revision source identity access dirty busy active clear review',()=>{
  for(const key of ['data-crop-review-ack','data-crop-review-mock']){const h=harness();h.controller.choose();ack(h);h.get(key).checked=1;assert.throws(()=>h.controller.request());}
  for(const change of [h=>h.state.workspace_id='foreign',h=>h.state.project.id='f'.repeat(32),h=>h.state.project.revision++,
    h=>h.state.project.document.canonical_timeline.sha256='f'.repeat(64),h=>h.state.canEdit=false,h=>h.state.dirty=true,
    h=>h.state.busy=true,h=>h.state.active=true,h=>h.state.project.archived=true,h=>h.vision(null)]){
    const h=harness();h.controller.choose();ack(h);change(h);h.controller.sync();assert.equal(h.get('data-crop-review-ack').checked,false);
    assert.equal(h.get('data-crop-review-mock').checked,false);assert.throws(()=>h.controller.request());
  }
});
test('supporting asset foreign incomplete and viewer result cannot choose source crop',()=>{
  for(const row of [null,clone(fixture.support_vision),{...clone(fixture.main_vision),project_id:'f'.repeat(32)},
    {...clone(fixture.main_vision),status:'approved'}]){const h=harness();h.vision(row);h.controller.choose();assert.throws(()=>h.controller.request());assert.equal(h.messages.length,1);}
  const h=harness();h.state.canEdit=false;h.controller.choose();assert.equal(h.get('data-crop-review-pick').disabled,true);assert.throws(()=>h.controller.request());
});
test('provider text is literal, choice clears without changing baseline, parent captures reviewed request before busy state',()=>{
  const h=harness(),row=clone(fixture.main_vision);row.snapshot.source.asset.filename='<img onerror=PRIVATE>';h.vision(row);h.controller.choose();
  assert.match(h.all().map(n=>n.textContent).join(' '),/<img onerror=PRIVATE>/);assert.ok(h.all().every(n=>n.innerHTML===undefined));
  ack(h);const before=clone(h.state.project);h.controller.clear();assert.deepEqual(h.state.project,before);assert.throws(()=>h.controller.request());
  const source=readFileSync(new URL('../native-source-editor.mjs',import.meta.url),'utf8');
  assert.match(source,/const body=cropReview.request\(\);void run\(\(\)=>send\(body\)\)/);assert.match(source,/host.append\(cropRoot\)/);
  assert.match(source,/getGuards\(\).workspace_id!==workspace/);assert.match(source,/value\?\.id!==p.id/);
});
