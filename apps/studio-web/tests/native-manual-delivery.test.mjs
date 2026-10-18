import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {EXPORT_PROFILES,profileForVideo,manualCaption,compareExports,initializeManualDelivery} from '../native-manual-delivery.mjs';

class Element {
  constructor(id=''){this.id=id;this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.dataset={};this.listeners={};this.children=[];this.textContent='';this.innerHTML='';}
  addEventListener(event,fn){(this.listeners[event]??=[]).push(fn);}
  async fire(event='click'){for(const fn of this.listeners[event]??[])await fn({preventDefault(){},target:this});}
  append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=[...nodes];this.innerHTML='';this.textContent='';}
  querySelectorAll(type){return this.children.flatMap(n=>typeof n==='object'?[...(type==='input'&&n.type==='checkbox'?[n]:[]),...n.querySelectorAll(type)]:[]);}
  click(){}scrollIntoView(){this.scrolled=true;}
}
const tick=()=>new Promise(r=>setImmediate(r));
function harness({handler,canEdit=true,storageFailure=false}={}){
  const ids=new Map(),get=id=>{if(!ids.has(id))ids.set(id,new Element(id));return ids.get(id);};
  const doc={getElementById:get,createElement:()=>new Element(),createTextNode:s=>s};
  const state={workspace_id:'wsp_test',canEdit,dirty:false,busy:false,active:false,project:{id:'a'.repeat(32),revision:7,document:{name:'Cần Giờ',proposal:{narration:'Lời đọc'}}}};
  const video={id:'b'.repeat(32),final_review:{decision:'approve'},result:{qc:{status:'passed',width:1080,height:1920,fps:30,final_sha256:'c'.repeat(64)}}};
  const memory=new Map(),calls=[],messages=[],copied=[],working=[];let captionVersion=1,copies={master:{title:'Tiêu đề đã lưu',caption:'Caption đã lưu',hashtags:'#CanGio'}};
  const value={export_id:'nexp_'+'d'.repeat(32),project_id:state.project.id,filename:'final-video.mp4',output_location:'C:/isolated/manual-delivery',
    files:['final-video.mp4','cover.jpg','subtitle.srt'],manifest:{width:1080,height:1920,duration_seconds:9,qc_result:'passed',video_codec:'h264',audio_codec:'aac',fps:30,video_sha256:video.result.qc.final_sha256}};
  const api=async(path,body)=>{calls.push({path,body:body?structuredClone(body):undefined});
    if(handler){const v=await handler(path,body,{state,video,value});if(v!==undefined)return v;}
    if(path.endsWith('/delivery-copy')){if(body){captionVersion++;copies=body.variants;return{version:captionVersion,variants:copies};}return{items:[{version:captionVersion,variants:copies}]};}
    if(body)return structuredClone(value);return{items:[]};};
  const controller=initializeManualDelivery({api,getState:()=>state,getVideo:()=>video,document:doc,
    storage:{getItem:k=>memory.get(k)??null,setItem:(k,v)=>{if(storageFailure)throw Error('storage blocked');memory.set(k,v);},removeItem:k=>memory.delete(k)},
    clipboard:{writeText:async text=>copied.push(text)},newKey:()=> 'explicit-stable-request-key',onMessage:(...args)=>messages.push(args),onWorking:v=>working.push(v)});
  get('delivery-filename').value='final-video.mp4';get('delivery-srt').checked=true;get('delivery-cover').checked=true;get('delivery-cover-time').value='0';
  controller.sync();return{state,video,controller,get,memory,calls,messages,copied,working,value};
}

for(const [id,label,width,height] of EXPORT_PROFILES)test(`profile ${id} binds actual approved geometry`,()=>{
  assert.equal(profileForVideo({result:{qc:{full_quality:{full_production_qc:{width,height}}}}}),id);
  assert.match(label,new RegExp(String(width)));});
test('no inferred format from missing or proxy geometry',()=>{assert.equal(profileForVideo(null),null);assert.equal(profileForVideo({result:{qc:{width:540,height:960}}}),null);});
test('copy caption combines only actual local text',()=>{assert.equal(manualCaption({caption:'Cần Giờ',cta:'Xem thêm',hashtags:'#CanGio'}),'Cần Giờ\n\nXem thêm\n\n#CanGio');assert.equal(manualCaption({}), '');});
test('compare versions explains changed bound fields',()=>{assert.deepEqual(compareExports({binding:{timeline_version:1}},{binding:{timeline_version:2}}),[{field:'timeline_version',before:1,after:2}]);});
test('Native mounts local Export Center without changing platform contracts',()=>{
  const html=readFileSync(new URL('../native.html',import.meta.url),'utf8'),native=readFileSync(new URL('../native.mjs',import.meta.url),'utf8');
  assert.match(html,/id="native-delivery-center"/);assert.match(native,/native_manual_delivery===true/);
  assert.match(native,/deliveryUI\?\.sync\(\)/);assert.match(native,/deliveryUI\?\.controls\(\)/);
});
test('current approved export uses exact hash, saved copy version and local request custody',async()=>{
  const h=harness();await tick();assert.equal(h.get('delivery-create').disabled,false);
  await h.get('delivery-create').fire();const posted=h.calls.filter(c=>c.body&&c.path.endsWith('/exports'));assert.equal(posted.length,1);
  assert.equal(posted[0].body.expected_video_sha256,h.video.result.qc.final_sha256);assert.equal(posted[0].body.caption_version,1);
  assert.equal(posted[0].body.profile,'vertical-short');assert.equal(h.memory.size,0);
  assert.match(h.get('delivery-result').innerHTML,/Tải video MP4/);assert.match(h.get('delivery-result').innerHTML,/Tải gói ZIP/);
  assert.ok(h.calls.every(c=>c.path.startsWith('/api/projects/')));assert.deepEqual(h.working,[true,false]);
});
test('lost response keeps exact request and cold retry key rather than creating another export',async()=>{
  let lost=true;const h=harness({handler:async(path,body)=>{if(body&&path.endsWith('/exports')&&lost){lost=false;throw Error('lost response');}}});await tick();
  await h.get('delivery-create').fire();assert.equal(h.memory.size,1);assert.equal(h.get('delivery-retry').hidden,false);
  h.get('delivery-filename').value='other-file.mp4';await h.get('delivery-retry').fire();
  const requests=h.calls.filter(c=>c.path.endsWith('/exports')&&c.body);assert.equal(requests.length,2);assert.deepEqual(requests[0].body,requests[1].body);assert.equal(h.memory.size,0);
});
test('unapproved preview and reader role cannot forge local export requests',async()=>{
  for(const alter of [h=>h.video.final_review=null,h=>h.state.canEdit=false,h=>h.state.dirty=true,h=>h.state.active=true]){
    const h=harness();await tick();alter(h);h.controller.controls();assert.equal(h.get('delivery-create').disabled,true);await h.get('delivery-create').fire();
    assert.equal(h.calls.filter(c=>c.body&&c.path.endsWith('/exports')).length,0);
  }
});
test('copy editing persists variants, retains unsaved text on project revision and supports clipboard',async()=>{
  const h=harness();await tick();h.get('delivery-copy-caption').value='Bản chỉnh sửa';await h.get('delivery-copy-caption').fire('input');
  assert.equal(h.get('delivery-create').disabled,true);h.state.project.revision++;h.controller.sync();await tick();
  assert.equal(h.get('delivery-copy-caption').value,'Bản chỉnh sửa');
  await h.get('delivery-save-copy').fire();const request=h.calls.find(c=>c.body&&c.path.endsWith('/delivery-copy'));
  assert.equal(request.body.variants.master.caption,'Bản chỉnh sửa');await h.get('delivery-copy-caption-button').fire();assert.match(h.copied[0],/Bản chỉnh sửa/);
});
test('storage failure blocks export before any POST',async()=>{const h=harness({storageFailure:true});await tick();await h.get('delivery-create').fire();assert.equal(h.calls.filter(c=>c.body).length,0);assert.match(h.messages.at(-1)[0],/storage blocked/);});
test('rendered form IDs are unique and caption field is separate from clipboard action',()=>{const h=harness();const ids=[...h.get('native-delivery-center').innerHTML.matchAll(/id="([^"]+)"/g)].map(m=>m[1]);assert.equal(new Set(ids).size,ids.length);assert.ok(ids.includes('delivery-copy-caption'));assert.ok(ids.includes('delivery-copy-caption-button'));});
test('project switch cannot display late successful package in a different project',async()=>{
  let release;const h=harness({handler:(path,body)=>body&&path.endsWith('/exports')?new Promise(r=>release=r):undefined});await tick();
  const pending=h.get('delivery-create').fire();await tick();h.state.project={id:'e'.repeat(32),revision:1,document:{name:'Other'}};h.controller.sync();release(h.value);await pending;
  assert.equal(h.get('delivery-result').innerHTML,'');assert.equal(h.memory.size,1);
});
