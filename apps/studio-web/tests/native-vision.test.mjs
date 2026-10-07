import test from 'node:test';
import assert from 'node:assert/strict';
import {supportsNativeVision,initializeNativeVision} from '../native-vision.mjs';
const project='a'.repeat(32),workspace='wsp_native_fixture',vision='nvis_'+'b'.repeat(32),hash='c'.repeat(64),observation='mfo_'+'d'.repeat(24),frameId='mfr_'+'e'.repeat(24),reference='media-frame://'+'f'.repeat(32)+'/frame-'+ 'e'.repeat(24)+'.png';
const source=()=>({frame_id:frameId,reference,timestamp_seconds:0});
const result=()=>({schema_version:'native-semantic-vision-fixture-v1',mock:true,semantic_inference_performed:false,external_provider_calls:0,automatic_planning_eligible:false,canonical_timeline_mutated:false,
  assets:[{asset_id:'fixture.png',provider:'fixture-native-vision-v1',model:'generic-frame-contract-v1',tracking_available:false,provenance:{semantic_model_saw_pixels:false},source_frame_evidence:[source()],
    frames:[{timestamp_seconds:0,evidence_frame_reference:reference,caption:'<img src=x onerror=attack()>',objects:[{label:'EXPLICIT FIXTURE person',confidence:.6}],ocr:[{language:'vi',text:'[MẪU] VĂN BẢN'}],environment:'fixture',action:'fixture',confidence:.6}],
    reframe_plans:['9:16','16:9','1:1','4:5'].map(aspect_ratio=>({aspect_ratio,fallback:'center_crop',confidence:0,needs_attention:true}))}]});
const row=()=>({schema_version:'native-vision-intent-v1',vision_id:vision,workspace_id:workspace,project_id:project,request_fingerprint:hash,external_provider_calls:0,
  official_adapter_state:'NOT_CONFIGURED',real_provider_tested:false,status:'succeeded',snapshot:{automatic_planning_eligible:false,request:{provider_mode:'fixture'}},result:result()});
function harness(){const nodes=new Map();class Node{constructor(){this.value='';this.checked=false;this.dataset={};this.listeners={};this.children=[];this.style={};}
  addEventListener(name,fn){this.listeners[name]=fn;}replaceChildren(){this.children=[];this.value='';}append(...children){this.children.push(...children);}}
  const root={getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);},createElement(){return new Node();}},get=id=>root.getElementById(id);
  const state={project:{id:project,revision:2},workspace_id:workspace,canManage:true,dirty:false,busy:false},calls=[],messages=[];let n=0;
  get('native-vision-mode').value='official';let handler=async()=>({schema_version:'native-vision-page-v1',workspace_id:workspace,project_id:project,external_provider_calls:0,items:[row()],next_cursor:null});
  const controller=initializeNativeVision({root,getState:()=>state,api:async(...args)=>{calls.push(args);return handler(...args);},onMessage:(...args)=>messages.push(args),uuid:()=>`fixture-${++n}`});
  get('native-vision-observation').value=observation;
  return{get,state,calls,messages,controller,handler(fn){handler=fn;}};
}
test('capability and explicit reads keep actual evidence frames beside literal labelled fixture predictions',async()=>{
  assert.equal(supportsNativeVision({}),false);assert.equal(supportsNativeVision({capabilities:{native_vision_review:true}}),true);
  const h=harness();assert.equal(h.calls.length,0);await h.controller.read();assert.equal(h.calls.length,1);assert.equal(h.calls[0][1],undefined);
  const figure=h.get('native-vision-results').children[0].children[2];assert.equal(figure.children[0].src,`/api/projects/${project}/media-frames/${frameId}/image`);
  assert.equal(figure.children[1].textContent,'0s · <img src=x onerror=attack()>');assert.ok(figure.children[3].textContent.includes('[MẪU] VĂN BẢN'));
  assert.equal(h.state.project.revision,2);assert.ok(h.get('native-vision-status').textContent.includes('Không dùng mẫu'));
});
test('Owner fixture acknowledgement and idempotency are explicit while official requests never auto-fallback',async()=>{
  const h=harness();h.get('native-vision-mode').value='fixture';await h.controller.execute('create');assert.equal(h.calls.length,0);
  h.handler(async()=>row());h.get('native-vision-ack').checked=true;await h.controller.execute('create');const key=h.calls[0][1].request_key;
  assert.equal(h.calls[0][1].fixture_acknowledged,true);assert.equal(h.get('native-vision-ack').checked,false);
  h.get('native-vision-ack').checked=true;await h.controller.execute('create');assert.equal(h.calls[1][1].request_key,key);
  h.get('native-vision-mode').value='official';h.handler(async()=>({...row(),status:'not_configured',result:null,snapshot:{automatic_planning_eligible:false,request:{provider_mode:'official'}}}));
  await h.controller.execute('create');assert.equal(h.calls[2][1].fixture_acknowledged,false);assert.equal(h.get('native-vision-results').children.length,0);
  h.state.canManage=false;await h.controller.execute('create');assert.equal(h.calls.length,3);
});
test('late project responses and contradictory inference or frame references fail closed',async()=>{
  const h=harness();let resolve;h.handler(()=>new Promise(done=>{resolve=done;}));const pending=h.controller.read();h.state.project={id:'9'.repeat(32),revision:1};h.controller.sync();
  resolve({schema_version:'native-vision-page-v1',workspace_id:workspace,project_id:project,external_provider_calls:0,items:[row()],next_cursor:null});await pending;
  assert.equal(h.get('native-vision-results').children.length,0);h.state.project={id:project,revision:2};h.controller.sync();
  for(const alter of [value=>value.result.semantic_inference_performed=true,value=>value.result.assets[0].frames[0].evidence_frame_reference='https://outside.example/frame',value=>value.workspace_id='wsp_outside']){
    const value=row();alter(value);h.handler(async()=>({schema_version:'native-vision-page-v1',workspace_id:workspace,project_id:project,external_provider_calls:0,items:[value],next_cursor:null}));await h.controller.read();
    assert.equal(h.get('native-vision-results').children.length,0);assert.equal(h.messages.at(-1)[1],true);}
});
test('source selection reads only measured observations and process/cancel remain fingerprint-bound',async()=>{
  const h=harness();h.handler(async()=>({project_id:project,observations:[{observation_id:observation,asset_id:'owned.png',frames:[source()],semantic_inference_performed:false,semantic_provider_status:'NOT_CONFIGURED'}]}));
  await h.controller.sources();assert.equal(h.calls[0][1],undefined);assert.equal(h.get('native-vision-observation').children[1].value,observation);
  h.get('native-vision-observation').value=observation;h.get('native-vision-mode').value='fixture';h.get('native-vision-ack').checked=true;
  h.handler(async()=>({...row(),status:'queued',result:null}));await h.controller.execute('create');assert.equal(h.get('native-vision-process').disabled,false);
  h.handler(async()=>row());await h.controller.execute('process');assert.equal(h.calls.at(-1)[0],`/api/projects/${project}/vision/${vision}/process`);
  assert.deepEqual(h.calls.at(-1)[1],{expected_fingerprint:hash});assert.equal(h.get('native-vision-process').disabled,true);
});
