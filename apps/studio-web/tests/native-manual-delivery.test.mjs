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
function harness({handler,canEdit=true,storageFailure=false,uploadCover=null}={}){
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
    clipboard:{writeText:async text=>copied.push(text)},newKey:()=> 'explicit-stable-request-key',onMessage:(...args)=>messages.push(args),onWorking:v=>working.push(v),uploadCoverFile:uploadCover});
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
test('cover options persist only in delivery request and do not change approved video',async()=>{
  const h=harness();await tick();const before=structuredClone(h.video);h.get('delivery-cover-source').value='uploaded_cover:ncov_'+'f'.repeat(32);
  h.get('delivery-cover-format').value='png';h.get('delivery-cover-x').value='0';h.get('delivery-cover-y').value='75';h.get('delivery-cover-zoom').value='1.5';h.get('delivery-cover-title').value='Vang Nguyễn';
  await h.get('delivery-create').fire();const request=h.calls.find(c=>c.path.endsWith('/exports')&&c.body);
  assert.deepEqual(request.body.cover_settings,{source:'uploaded_cover',source_id:'ncov_'+'f'.repeat(32),format:'png',center_x:0,center_y:.75,zoom:1.5,title:'Vang Nguyễn',logo:false});assert.deepEqual(h.video,before);
});
test('copy regeneration affects selected variant and history restores as a new draft',async()=>{
  const h=harness();await tick();h.get('delivery-copy-platform').value='tiktok';await h.get('delivery-copy-platform').fire('change');await h.get('delivery-regenerate-copy').fire();
  assert.equal(h.get('delivery-copy-caption').value,'Caption đã lưu');await h.get('delivery-save-copy').fire();
  const saved=h.calls.find(c=>c.path.endsWith('/delivery-copy')&&c.body);assert.equal(saved.body.variants.tiktok.caption,saved.body.variants.master.caption);
  h.get('delivery-copy-history').value='2';await h.get('delivery-copy-history').fire('change');assert.equal(h.get('delivery-create').disabled,true);
});
test('history recreation retains exact endpoint and key through lost-response retry',async()=>{
  let lost=true;const project='a'.repeat(32),source='nexp_'+'e'.repeat(32),path=`/api/projects/${project}/exports/${source}/recreate-package`;
  const item={project_id:project,export_id:source,manifest_sha256:'f'.repeat(64),status:'ready',profile:'vertical-short',binding:{project_title:'Old export'},created_at:'2026-10-18T00:00:00Z'};
  const h=harness({handler:(url,body)=>{if(url.endsWith('/exports')&&!body)return{items:[item]};if(url===path&&body&&lost){lost=false;throw Error('lost response');}}});await tick();
  const button=h.get('delivery-history').children[0].children.find(n=>n.textContent==='Tạo lại gói thành bản mới');await button.fire();
  assert.equal(h.memory.size,1);const held=JSON.parse([...h.memory.values()][0]);assert.equal(held.schema_version,'manual-delivery-pending.v2');assert.equal(held.path,path);
  await h.get('delivery-retry').fire();const posts=h.calls.filter(c=>c.path===path&&c.body);assert.equal(posts.length,2);assert.deepEqual(posts[0].body,posts[1].body);assert.equal(h.memory.size,0);
});
test('held recreation path cannot post into a foreign project or arbitrary endpoint',async()=>{
  const h=harness();await tick();const key='vf-manual-delivery-v1:wsp_test:'+'a'.repeat(32);
  for(const path of ['/api/projects/'+ 'b'.repeat(32)+'/exports/nexp_'+'d'.repeat(32)+'/recreate-package','/api/connections/private']){
    h.memory.set(key,JSON.stringify({schema_version:'manual-delivery-pending.v2',path,body:{request_key:'explicit-stable-request-key'}}));await h.get('delivery-retry').fire();
  }
  assert.equal(h.calls.filter(c=>c.body).length,0);assert.equal(h.memory.size,1);
});
test('failed export resumes from durable history without an old browser receipt',async()=>{
  const project='a'.repeat(32),source='nexp_'+'e'.repeat(32),path=`/api/projects/${project}/exports/${source}/resume`;
  const item={project_id:project,export_id:source,request_key:'original-server-request-key',status:'failed',profile:'vertical-short',binding:{project_title:'Interrupted export'},created_at:'2026-10-18T00:00:00Z'};
  const h=harness({handler:(url,body)=>url.endsWith('/exports')&&!body?{items:[item]}:undefined});await tick();
  const button=h.get('delivery-history').children[0].children.find(n=>n.textContent==='Đối chiếu / tiếp tục lần xuất');await button.fire();
  assert.ok(h.calls.some(c=>c.path===path&&c.body&&Object.keys(c.body).length===0));assert.equal(h.memory.size,0);
});
