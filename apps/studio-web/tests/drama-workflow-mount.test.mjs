// DOM contract fixture, not a browser screenshot or usability acceptance.
import test from 'node:test';import assert from 'node:assert/strict';
import {initializeDramaWorkflow} from '../drama-workflow.mjs';
import {Node,Doc} from './support/drama-dom.mjs';
import {createNativeProjectReload,nativeDramaSaveCallback} from '../native.mjs';
import {dramaRequestHash} from '../drama-script-save.mjs';
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const settled=async h=>{for(let n=0;n<100;n++){if(!h.controller.isWorking())return;await new Promise(r=>setTimeout(r,5));}throw Error('Fixture save did not settle');};
function harness({failFirstScript=false}={}){const dom=new Doc(),add=(tag,id,cls,parent=dom.body)=>{const n=new Node(tag);if(id)n.setAttribute('id',id);if(cls)n.setAttribute('class',cls);parent.append(n);return n;};
  add('nav',null,'stage-navigation');for(const stage of ['script','assets','video','storyboard']){const n=add('section','stage-'+stage);n.setAttribute('data-stage-panel',stage);}
  for(const id of ['brief-card','proposal-card','video-stage-body','video-review-body','studio-title','runtime-voice-summary'])add('div',id);
  const review=add('div',null,'review',dom.getElementById('proposal-card'));add('button','approve',null,review);add('section','script-only-review',null,dom.getElementById('stage-script'));add('details','native-drama-panel');add('details','native-narration-panel');
  let project=null,busy=false,dirty=false,dirtyPart=null,serverProject=null,scriptReceipt=null,scriptWrites=0;const calls=[],messages=[],stages=[],data=new Map();let controller;let api;
  const reload=createNativeProjectReload({api:(...args)=>api(...args),getState:()=>({project,busy,dirty,dirtyPart,workspace_id:'wsp_native_local'}),onProject:p=>project=p,renderProject:()=>controller?.sync(),projects:async()=>{},schedule(){}});
  const choices=[['standard','Video giới thiệu / nội dung'],['drama','Phim Drama'],['source','Dựng từ video có sẵn']].map(([kind,name])=>({kind,name,description:'Mô tả',input:'Đầu vào',output:'Video'}));
  controller=initializeDramaWorkflow({dom,storage:{getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v)},getState:()=>({project,busy,dirty,dirtyPart,canEdit:true}),onWorking:v=>busy=v,onDirty:v=>{dirty=v;dirtyPart=v?'drama-script':null;},onMessage:(...v)=>messages.push(v),showStage:s=>stages.push(s),
    onCreated:async p=>{project=p;controller.sync();},onSaved:nativeDramaSaveCallback(reload),api:api=async(path,body)=>{calls.push({path,body});if(path==='/api/production-workflows')return {schema_version:'native-production-workflow.v1',choices};if(path==='/api/app-info')return {build:'fixture',commit:'explicit-test-only'};
      if(path==='/api/projects')return {id:'a'.repeat(32),revision:1,document:{name:body.name,production_workflow:{kind:body.workflow_kind},brand_template:{template:{aspect_ratio:body.output_format}}},jobs:[]};
      if(path.endsWith('/drama-script')){if(scriptReceipt?.key!==body.request_key){serverProject={...project,revision:body.revision+1,document:{...project.document,production_workflow:{...project.document.production_workflow,series:body.series,episode:body.episode},drama_script:{raw_text:body.text,input_mode:body.input_mode,characters_confirmed:body.confirm_characters,character_notes:body.character_notes,narrator_enabled:body.narrator_enabled,parsed:{characters:[],lines:[]}}}};scriptReceipt={key:body.request_key,project_id:project.id,revision:body.revision+1,provider_calls:0,human_approval_granted:false,request_key:body.request_key,base_revision:body.revision,request_sha256:await dramaRequestHash(body),workspace_id:'wsp_native_local'};}if(scriptWrites++===0&&failFirstScript)throw Error('Explicit lost response fixture');return scriptReceipt;}
      if(path.startsWith('/api/projects/')&&!body)return structuredClone(serverProject);
      throw Error('Unexpected fixture API');}});
  return {dom,controller,calls,messages,stages,project:()=>project,setPrepared:()=>{project={...project,revision:project.revision+1,document:{...project.document,prepared_narration:{plan_sha256:'pinned-measured-fixture'}},drama_voice_binding:{current:true}};controller.sync();},switchStandard:()=>{project={id:'b'.repeat(32),revision:1,document:{name:'Legacy standard',proposal:{}},jobs:[]};controller.sync();},button:text=>dom.querySelectorAll('button').find(n=>n.textContent===text)};
}
test('actual workflow module mounts all three entry cards and creates Drama before script/media',async()=>{
  const h=harness();await tick();assert.ok(h.button('Bắt đầu Phim Drama'));await h.button('Bắt đầu Phim Drama').listeners.click();
  const name=h.dom.querySelectorAll('label').find(n=>n.textContent==='Tên phim / video').children[0];name.value='Bộ phim đầu tiên';
  await h.button('Tạo phim Drama').listeners.click();await tick();assert.equal(h.project().document.production_workflow.kind,'drama');assert.equal(h.project().document.brand_template.template.aspect_ratio,'9:16');
  assert.ok(h.dom.body.classList.contains('drama-project'));assert.equal(h.dom.getElementById('stage-script').hidden,true);assert.equal(h.calls.filter(v=>v.body).length,1);assert.ok(!h.calls.some(v=>/jobs|approve|voice-auditions/.test(v.path)));
  assert.ok(h.dom.querySelectorAll('button').some(n=>n.textContent==='1. Kịch bản'));assert.equal(h.dom.getElementById('approve').parentNode.parentNode.className,'card drama-final-approval');
});
test('scene navigation reuses the original asset and canonical scene editor panels',async()=>{
  const h=harness();await tick();await h.button('Bắt đầu Phim Drama').listeners.click();h.dom.querySelectorAll('label').find(n=>n.textContent==='Tên phim / video').children[0].value='Phim';await h.button('Tạo phim Drama').listeners.click();await tick();
  const panel=h.dom.getElementById('stage-video');h.controller.showStep('scenes');assert.equal(h.dom.getElementById('stage-video'),panel);assert.equal(panel.hidden,false);assert.equal(h.dom.body.dataset.dramaStep,'scenes');
  h.controller.showStep('export');assert.equal(h.dom.body.dataset.dramaStep,'export');assert.equal(h.calls.filter(v=>v.body).length,1);
});
test('switching back to a standard project restores the exact original narration casting and approval nodes',async()=>{
  const h=harness();await tick();const voice=h.dom.getElementById('native-drama-panel'),audio=h.dom.getElementById('native-narration-panel'),review=h.dom.getElementById('approve').parentNode;
  const originalVoiceParent=voice.parentNode,originalAudioParent=audio.parentNode,originalReviewParent=review.parentNode;
  await h.button('Bắt đầu Phim Drama').listeners.click();h.dom.querySelectorAll('label').find(n=>n.textContent==='Tên phim / video').children[0].value='Phim';await h.button('Tạo phim Drama').listeners.click();await tick();
  assert.notEqual(voice.parentNode,originalVoiceParent);h.switchStandard();assert.equal(voice.parentNode,originalVoiceParent);assert.equal(audio.parentNode,originalAudioParent);assert.equal(review.parentNode,originalReviewParent);
  assert.equal(h.dom.querySelector('.stage-navigation').hidden,false);assert.equal(h.dom.getElementById('script-only-review').parentNode,h.dom.getElementById('stage-script'));
});
test('lost save response replays the exact request and retains text edited after uncertainty',async t=>{
  const h=harness({failFirstScript:true});t.after(()=>h.controller.dispose());await tick();await h.button('Bắt đầu Phim Drama').listeners.click();h.dom.querySelectorAll('label').find(n=>n.textContent==='Tên phim / video').children[0].value='Phim';await h.button('Tạo phim Drama').listeners.click();await tick();
  const input=h.dom.querySelector('textarea');input.value='An: Bản thứ nhất.';input.listeners.input();h.button('Lưu nháp').listeners.click();await settled(h);const original=h.calls.find(v=>v.path.endsWith('/drama-script')).body;
  input.value='An: Bản mới đang sửa.';input.listeners.input();h.button('Đối chiếu lần lưu trước').listeners.click();await settled(h);
  const writes=h.calls.filter(v=>v.path.endsWith('/drama-script'));assert.deepEqual(writes[1].body,original);assert.equal(input.value,'An: Bản mới đang sửa.');assert.equal(h.controller.isDirty(),true);assert.equal(h.project().document.drama_script.raw_text,'An: Bản thứ nhất.');
  h.button('Lưu nháp').listeners.click();await settled(h);assert.equal(h.project().document.drama_script.raw_text,'An: Bản mới đang sửa.');assert.equal(h.controller.isDirty(),false);
});
test('applying audio brings the player forward and later refreshes respect a manually opened or closed audio panel',async()=>{
  const h=harness();await tick();await h.button('Bắt đầu Phim Drama').listeners.click();h.dom.querySelectorAll('label').find(n=>n.textContent==='Tên phim / video').children[0].value='Phim';h.button('Tạo phim Drama').listeners.click();await tick();
  h.controller.showStep('preview');const audio=h.dom.getElementById('native-narration-panel');assert.equal(audio.open,true);h.setPrepared();assert.equal(audio.open,false);
  audio.open=true;h.controller.sync();assert.equal(audio.open,true);audio.open=false;h.controller.sync();assert.equal(audio.open,false);
});
