// DOM contract fixture, not a browser screenshot or usability acceptance.
import test from 'node:test';import assert from 'node:assert/strict';
import {initializeDramaWorkflow} from '../drama-workflow.mjs';
class Node {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.parentNode=null;this.attributes={};this.dataset={};this.listeners={};this.value='';this.hidden=false;this.textContent='';this.style={setProperty(){}};const names=new Set();this.classList={add:x=>names.add(x),remove:x=>names.delete(x),contains:x=>names.has(x),toggle:(x,on)=>on?names.add(x):names.delete(x)};}
  setAttribute(k,v){this.attributes[k]=String(v);if(k==='id')this.id=v;if(k==='class'){this.className=v;for(const x of v.split(' '))this.classList.add(x);}if(k==='value')this.value=v;if(k.startsWith('data-'))this.dataset[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=v;}
  removeAttribute(k){delete this.attributes[k];}getAttribute(k){return this.attributes[k]??null;}
  remove(){if(this.parentNode)this.parentNode.children=this.parentNode.children.filter(v=>v!==this);this.parentNode=null;}
  append(...nodes){for(const n of nodes){n.remove();n.parentNode=this;this.children.push(n);}}
  prepend(n){n.remove();n.parentNode=this;this.children.unshift(n);}
  before(n){const p=this.parentNode;n.remove();n.parentNode=p;p.children.splice(p.children.indexOf(this),0,n);}
  replaceChildren(...nodes){for(const n of this.children)n.parentNode=null;this.children=[];this.append(...nodes);}
  addEventListener(name,fn){this.listeners[name]=fn;}focus(){this.focused=true;}scrollIntoView(){}
  descendants(){return this.children.flatMap(n=>[n,...n.descendants()]);}
  matches(s){if(s.startsWith('#'))return this.id===s.slice(1);if(s.startsWith('.'))return this.classList.contains(s.slice(1));const a=/^\[([^=\]]+)(?:="?([^"\]]+)"?)?\]$/.exec(s);if(a)return a[2]===undefined?this.getAttribute(a[1])!==null:this.getAttribute(a[1])===a[2];return this.tagName===s;}
  querySelectorAll(s){return this.descendants().filter(n=>s.split(',').some(x=>n.matches(x.trim())));}querySelector(s){return this.querySelectorAll(s)[0]??null;}
  closest(s){return this.matches(s)?this:this.parentNode?.closest(s)??null;}
}
class Doc extends Node {constructor(){super('document');this.body=new Node('body');this.append(this.body);}createElement(tag){return new Node(tag);}getElementById(id){return this.descendants().find(n=>n.id===id)??null;}}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function harness({failFirstScript=false}={}){const dom=new Doc(),add=(tag,id,cls,parent=dom.body)=>{const n=new Node(tag);if(id)n.setAttribute('id',id);if(cls)n.setAttribute('class',cls);parent.append(n);return n;};
  add('nav',null,'stage-navigation');for(const stage of ['script','assets','video','storyboard']){const n=add('section','stage-'+stage);n.setAttribute('data-stage-panel',stage);}
  for(const id of ['brief-card','proposal-card','video-stage-body','video-review-body','studio-title','runtime-voice-summary'])add('div',id);
  const review=add('div',null,'review',dom.getElementById('proposal-card'));add('button','approve',null,review);add('section','script-only-review',null,dom.getElementById('stage-script'));add('details','native-drama-panel');add('details','native-narration-panel');
  let project=null,busy=false,dirty=false,dirtyPart=null,serverProject=null,scriptReceipt=null,scriptWrites=0;const calls=[],messages=[],stages=[],data=new Map();let controller;
  const choices=[['standard','Video giới thiệu / nội dung'],['drama','Phim Drama'],['source','Dựng từ video có sẵn']].map(([kind,name])=>({kind,name,description:'Mô tả',input:'Đầu vào',output:'Video'}));
  controller=initializeDramaWorkflow({dom,storage:{getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v)},getState:()=>({project,busy,dirty,dirtyPart,canEdit:true}),onWorking:v=>busy=v,onDirty:v=>{dirty=v;dirtyPart=v?'drama-script':null;},onMessage:(...v)=>messages.push(v),showStage:s=>stages.push(s),
    onCreated:async p=>{project=p;controller.sync();},onSaved:async()=>{if(serverProject){project=serverProject;controller.sync();}},api:async(path,body)=>{calls.push({path,body});if(path==='/api/production-workflows')return {schema_version:'native-production-workflow.v1',choices};if(path==='/api/app-info')return {build:'fixture',commit:'explicit-test-only'};
      if(path==='/api/projects')return {id:'a'.repeat(32),revision:1,document:{name:body.name,production_workflow:{kind:body.workflow_kind},brand_template:{template:{aspect_ratio:body.output_format}}},jobs:[]};
      if(path.endsWith('/drama-script')){if(scriptReceipt?.key!==body.request_key){serverProject={...project,revision:body.revision+1,document:{...project.document,drama_script:{raw_text:body.text,input_mode:body.input_mode,characters_confirmed:body.confirm_characters,character_notes:body.character_notes,parsed:{characters:[],lines:[]}}}};scriptReceipt={key:body.request_key,project_id:project.id,revision:body.revision+1,provider_calls:0,human_approval_granted:false};}if(scriptWrites++===0&&failFirstScript)throw Error('Explicit lost response fixture');return scriptReceipt;}
      throw Error('Unexpected fixture API');}});
  return {dom,controller,calls,messages,stages,project:()=>project,switchStandard:()=>{project={id:'b'.repeat(32),revision:1,document:{name:'Legacy standard',proposal:{}},jobs:[]};controller.sync();},button:text=>dom.querySelectorAll('button').find(n=>n.textContent===text)};
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
  const input=h.dom.querySelector('textarea');input.value='An: Bản thứ nhất.';input.listeners.input();h.button('Lưu nháp').listeners.click();await tick();const original=h.calls.find(v=>v.path.endsWith('/drama-script')).body;
  input.value='An: Bản mới đang sửa.';input.listeners.input();h.button('Đối chiếu lần lưu trước').listeners.click();await tick();
  const writes=h.calls.filter(v=>v.path.endsWith('/drama-script'));assert.deepEqual(writes[1].body,original);assert.equal(input.value,'An: Bản mới đang sửa.');assert.equal(h.controller.isDirty(),true);assert.equal(h.project().document.drama_script.raw_text,'An: Bản thứ nhất.');
  h.button('Lưu nháp').listeners.click();await tick();assert.equal(h.project().document.drama_script.raw_text,'An: Bản mới đang sửa.');assert.equal(h.controller.isDirty(),false);
});
