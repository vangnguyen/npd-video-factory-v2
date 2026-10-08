import test from 'node:test';import assert from 'node:assert/strict';
import {initializeNarratedVariants,validateNarratedVariantBatch} from '../native-narrated-variants.mjs';
import {nativeRequestBody} from '../native.mjs';
import {validateNarrationPage} from '../native-narration.mjs';
const master='a'.repeat(32),child='b'.repeat(32),job='c'.repeat(32),batch='nnvb_'+'d'.repeat(32),SHA='e'.repeat(64),workspace='wsp_native_fixture';
const profile={profile_ref:'social-square@1',label:'Square <script>literal</script>',width:1080,height:1080,aspect_ratio:'1:1',platform:null};
const derivation=()=>({schema_version:'native-narrated-narration-derivation-v1',batch_id:batch,workspace_id:workspace,master_project_id:master,child_project_id:child,
  source_project_id:master,source_narration_job_id:job,source_snapshot_sha256:SHA,source_approval_sha256:SHA,source_plan_sha256:SHA,source_voice_sha256:SHA,voice_input_sha256:SHA,source_prepared_reference_sha256:SHA,
  approval_inherited:false,rights_authority_inherited:false,new_inference_calls:0,human_review_required:true});
const row=()=>({schema_version:'native-narrated-variant-batch-v1',batch_id:batch,workspace_id:workspace,master_project_id:master,external_provider_calls:0,
  snapshot:{master_revision:2},result:{schema_version:'native-narrated-variants-v1',master_project_mutated:false,publishing_enabled:false,new_inference_calls:0,external_provider_calls:0,
    rights_authority_inherited:false,human_approval_required_per_variant:true,variants:[{project_id:child,name:'Square <img src=x>',profile,initial_document_sha256:SHA,initial_timeline_sha256:SHA,derivation:derivation(),approval_inherited:false,render_dispatched:false}]}});
const page=()=>({schema_version:'native-narrated-variant-page-v1',workspace_id:workspace,master_project_id:master,external_provider_calls:0,
  current_master:{revision:2,timeline_version:1,prepared_reference_sha256:SHA},items:[row()],next_cursor:null});
const catalog=()=>({schema_version:'native-narrated-variant-catalog-v1',profiles:[profile],publishing_enabled:false,provider_dispatches:0});
function harness(){class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.checked=false;this.dataset={};}
  append(...n){this.children.push(...n);}replaceChildren(...n){this.children=n;}setAttribute(k,v){this[k]=v;}addEventListener(k,fn){this.listeners[k]=fn;}
  querySelectorAll(tag){return this.children.flatMap(n=>[...(n.tagName.toLowerCase()===tag?[n]:[]),...n.querySelectorAll(tag)]);}}
  const root=new Node('details'),dom={getElementById:()=>root,createElement:t=>new Node(t)},state={workspace_id:workspace,project:{id:master,revision:2,document:{canonical_timeline:{version:1},prepared_narration:{job_id:job}},jobs:[]},canEdit:true};
  const calls=[],messages=[],opened=[];let response=async path=>path==='/api/narrated/variant-profiles'?catalog():page();
  const controller=initializeNarratedVariants({dom,getState:()=>state,api:async(...args)=>{calls.push(args);return response(...args);},onMessage:(...m)=>messages.push(m),onOpen:async id=>opened.push(id),newKey:()=> 'explicit-fixture-key'});
  return {root,state,calls,messages,opened,controller,handler:fn=>{response=fn;},button:text=>root.querySelectorAll('button').find(n=>n.textContent===text)};
}
test('family reads are explicit and creation sends exact frozen binding with stable lost-response key',async()=>{
  const h=harness();assert.equal(h.calls.length,0);await h.controller.read();assert.equal(h.calls.length,2);assert.ok(h.calls.every(c=>c[1]===undefined));
  assert.equal(h.root.querySelectorAll('label')[0].textContent,profile.label+' ');assert.equal(h.root.querySelectorAll('label')[0].innerHTML,undefined);
  await h.button('Mở bản lồng tiếng').listeners.click();assert.deepEqual(h.opened,[child]);
  h.handler(async()=>{throw new Error('Lost explicit response');});await h.controller.create();await h.controller.create();const writes=h.calls.filter(c=>c[1]);assert.equal(writes.length,2);assert.deepEqual(writes[0],writes[1]);
  assert.deepEqual(writes[0][1],{schema_version:'native-narrated-variant-request-v1',revision:2,expected_version:1,expected_prepared_reference_sha256:SHA,profile_refs:['social-square@1'],request_key:'native-narrated-explicit-fixture-key'});
});
test('viewer dirty active archived and unprepared masters cannot create children',async()=>{
  for(const change of [{canEdit:false},{dirty:true},{busy:true},{active:true}]){const h=harness();await h.controller.read();Object.assign(h.state,change);h.controller.controls();assert.equal(h.button('Tạo các bản lồng tiếng đã chọn').disabled,true);await h.controller.create();assert.equal(h.calls.filter(c=>c[1]).length,0);}
  const h=harness();await h.controller.read();delete h.state.project.document.prepared_narration;await h.controller.create();assert.equal(h.calls.filter(c=>c[1]).length,0);
});
test('late responses and forged foreign approved generated or publishing results are discarded',async()=>{
  const h=harness();let release;h.handler(path=>path==='/api/narrated/variant-profiles'?Promise.resolve(catalog()):new Promise(done=>release=done));const pending=h.controller.read();h.state.project.id='f'.repeat(32);h.controller.sync();release(page());await pending;assert.equal(h.root.querySelectorAll('article').length,0);
  const state=harness().state;
  for(const mutate of [v=>v.workspace_id='wsp_foreign',v=>v.result.publishing_enabled=true,v=>v.result.new_inference_calls=1,v=>v.result.variants[0].derivation.child_project_id=master,
    v=>v.result.variants[0].approval_inherited=true,v=>v.result.variants[0].profile.width=1920,v=>v.result.variants[0].derivation.rights_authority_inherited=0]){const v=structuredClone(row());mutate(v);assert.throws(()=>validateNarratedVariantBatch(v,state));}
});
test('Studio JSON adapter unwraps fetch-style panel requests and preserves plain domain bodies',()=>{
  const body={revision:4,acknowledged:true,reason:'Explicit <script>literal</script>'};assert.deepEqual(nativeRequestBody({method:'POST',body:JSON.stringify(body)}),body);assert.equal(nativeRequestBody(body),body);assert.equal(nativeRequestBody(undefined),undefined);
  for(const request of [{method:'DELETE',body:'{}'},{method:'POST',body:'{}',headers:{authorization:'forged'}},{method:'POST',body:'[]'},{method:'POST',body:'null'},{method:'POST',body:'broken'},[],false])assert.throws(()=>nativeRequestBody(request));
});
test('derived audio keeps original source-plan identity and child URL while rejecting authority promotion',()=>{
  const d=derivation(),plan={schema_version:'native-scene-narration-plan-v1',project_id:master,job_id:job,voice_audio_sha256:SHA,voice_input_sha256:SHA,word_alignment_claimed:false,speech_quality_accepted:false,confidence:null,source_duration_seconds:1.2,items:[{}]},
    value={schema_version:'native-scene-narration-plan-v1',project_id:child,revision:1,items:[],derived_narration:{schema_version:'native-derived-narration-review-v1',project_id:child,workspace_id:workspace,source_project_id:master,source_job_id:job,
      derivation:d,derivation_sha256:SHA,source_result:{plan,plan_sha256:SHA,voice_url:`/api/projects/${master}/narration/${job}/audio`},voice_url:`/api/projects/${child}/narration/${job}/audio`,new_inference_calls:0,human_review_required:true,approval_inherited:false,rights_authority_inherited:false}},
    state={workspace_id:workspace,project:{id:child,revision:1,document:{prepared_narration:{job_id:job,derivation:d}}}};
  assert.equal(validateNarrationPage(value,state).derived_narration.source_result.plan.project_id,master);
  for(const mutate of [v=>v.derived_narration.source_result.plan.project_id=child,v=>v.derived_narration.voice_url='https://foreign.invalid/audio',v=>v.derived_narration.rights_authority_inherited=true,v=>v.derived_narration.derivation.source_voice_sha256='invalid']){const v=structuredClone(value);mutate(v);assert.throws(()=>validateNarrationPage(v,state));}
});
