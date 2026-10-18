// Actual Native HTTP/CAS + production onSaved/reload binding; DOM contract, not browser QA.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import * as native from '../native.mjs';
import {initializeDramaWorkflow} from '../drama-workflow.mjs';
import {Doc,Node} from './support/drama-dom.mjs';

const origin=process.env.VF_DRAMA_TEST_ORIGIN;
const until=async predicate=>{for(let i=0;i<300;i++){if(predicate())return;await new Promise(r=>setTimeout(r,10));}throw Error('Integration state did not settle');};
async function harness(t,{storage=new Map(),existingProject=null}={}){
  assert.ok(origin,'Run through the owned Native integration server');
  const sessionResponse=await fetch(origin+'/api/session'),cookie=sessionResponse.headers.get('set-cookie').split(';')[0],session=await sessionResponse.json();
  const calls=[],messages=[];let project=null,busy=false,dirty=false,dirtyPart=null,workflow;
  const dom=new Doc(),add=(tag,id,cls,parent=dom.body)=>{const n=new Node(tag);if(id)n.setAttribute('id',id);if(cls)n.setAttribute('class',cls);parent.append(n);return n;};
  add('nav',null,'stage-navigation');for(const stage of ['script','assets','video','storyboard'])add('section','stage-'+stage).setAttribute('data-stage-panel',stage);
  for(const id of ['brief-card','proposal-card','video-stage-body','video-review-body','studio-title','runtime-voice-summary'])add('div',id);
  const review=add('div',null,'review',dom.getElementById('proposal-card'));add('button','approve',null,review);add('section','script-only-review',null,dom.getElementById('stage-script'));add('details','native-drama-panel');add('details','native-narration-panel');
  const gates={};
  const api=async(path,body)=>{
    calls.push({path,body:body?structuredClone(body):null});
    if(body&&path.endsWith('/drama-script')&&gates.before){delete gates.before;throw TypeError('Explicit network failure before sending');}
    const response=await fetch(origin+path,{method:body?'POST':'GET',headers:{Cookie:cookie,...(body?{'Content-Type':'application/json','X-VF-CSRF':session.csrf}:{})},body:body?JSON.stringify(body):undefined});
    const value=await response.json();
    if(body&&path.endsWith('/drama-script')&&gates.post){const gate=gates.post;delete gates.post;await gate;}
    if(!body&&path.startsWith('/api/projects/')&&gates.get){const gate=gates.get;delete gates.get;await gate;}
    if(!response.ok){const error=Error(value.code);error.status=response.status;error.code=value.code;throw error;}
    if(body&&path.endsWith('/drama-script')&&gates.lose){delete gates.lose;throw TypeError('Explicit response lost after real server commit');}
    return value;
  };
  project=existingProject??await api('/api/projects',{name:'SELF CONFLICT INTEGRATION FIXTURE',prompt:'',workflow_kind:'drama',input_kind:'script'});
  const getState=()=>({project,busy,dirty,dirtyPart,workspace_id:'wsp_native_local',canEdit:true});
  const renderProject=reset=>{if(reset){dirty=false;dirtyPart=null;}workflow?.sync();};
  let onSaved;
  if(native.createNativeProjectReload){
    const reload=native.createNativeProjectReload({api,getState,onProject:p=>project=p,renderProject,projects:async()=>{},schedule(){}});
    onSaved=native.nativeDramaSaveCallback(reload);
  }else{
    // Baseline reproduction executes the exact callback and reload body in native.mjs.
    const source=readFileSync(new URL('../native.mjs',import.meta.url),'utf8');
    const reloadSource=source.slice(source.indexOf('  async function reload('),source.indexOf('  function schedule()',source.indexOf('  async function reload(')));
    const mount=source.slice(source.indexOf('dramaFlowUI=flow.initializeDramaWorkflow('));
    const callback=mount.match(/onSaved:(async\(\)=>\{await reload\(true\);\})/)[1];
    const factory=new Function('api','read','write','renderProject','projects','schedule',`let project,dirty;${reloadSource};return async function(){({project,dirty}=read());await (${callback})();write(project);};`);
    onSaved=factory(api,getState,p=>project=p,renderProject,async()=>{},()=>{});
  }
  workflow=initializeDramaWorkflow({api,getState,onSaved,onCreated:async p=>{project=p;workflow.sync();},onDirty:v=>{dirty=v;dirtyPart=v?'drama-script':null;},onWorking:v=>busy=v,onMessage:(text,error)=>messages.push({text,error}),showStage(){},dom,storage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)}});
  t.after(()=>workflow.dispose());
  await until(()=>calls.some(v=>v.path==='/api/app-info'));
  const button=label=>dom.querySelectorAll('button').find(n=>n.textContent===label);
  return {dom,workflow,api,calls,messages,gates,getState,button,storage,setProject:p=>{project=p;workflow.sync();},
    type:value=>{const input=dom.querySelector('textarea');input.value=value;input.listeners.input();},
    save:()=>button('Lưu nháp')?.listeners.click(),settle:()=>until(()=>!busy),input:()=>dom.querySelector('textarea').value};
}

test('one tab: own POST commit reloads successfully and enables step 2 without approval',async t=>{
  const h=await harness(t);h.type('An: Đây là bản nháp kiểm thử.\nBình: Mình nghe rõ.');h.save();await h.settle();
  const server=await h.api('/api/projects/'+h.getState().project.id);
  console.log(JSON.stringify({case:'one-tab',server_revision:server.revision,client_revision:h.getState().project.revision,dirty:h.workflow.isDirty(),pending_button:Boolean(h.button('Đối chiếu lần lưu trước')),messages:h.messages}));
  assert.equal(server.revision,2);
  assert.equal(h.getState().project.revision,2);
  assert.equal(h.workflow.isDirty(),false,JSON.stringify(h.messages));
  assert.ok(!h.messages.some(v=>v.error));assert.ok(h.dom.querySelectorAll('p').some(n=>n.textContent==='Đã lưu'));
  const next=h.button('Tiếp tục →');assert.equal(next.disabled,false);next.listeners.click();assert.equal(h.dom.body.dataset.dramaStep,'voices');
  assert.equal(h.getState().project.approval,null);assert.deepEqual(h.getState().project.jobs,[]);
});

const pause=()=>{let release;const promise=new Promise(r=>release=r);return {promise,release};};
const writes=h=>h.calls.filter(v=>v.path.endsWith('/drama-script')&&v.body);
const serverProject=h=>h.api('/api/projects/'+h.getState().project.id);

test('autosave then manual Save shares one in-flight request and clean Save is a no-op',async t=>{
  const h=await harness(t),hold=pause();h.gates.post=hold.promise;h.type('An: Tự lưu đúng một lần.');
  await until(()=>writes(h).length===1);h.button('Đối chiếu lần lưu trước').listeners.click();assert.equal(writes(h).length,1);
  hold.release();await h.settle();h.save();await new Promise(r=>setTimeout(r,20));
  assert.equal(writes(h).length,1);assert.equal((await serverProject(h)).revision,2);assert.equal(h.workflow.isDirty(),false);
});

test('lost response after commit replays the exact original request without a duplicate version',async t=>{
  const h=await harness(t);h.gates.lose=true;h.type('An: Bản đã lưu nhưng mất phản hồi.');h.save();await h.settle();
  assert.equal((await serverProject(h)).revision,2);const first=structuredClone(writes(h)[0].body);
  assert.equal(h.workflow.isDirty(),true);h.button('Đối chiếu lần lưu trước').listeners.click();await h.settle();
  assert.deepEqual(writes(h)[1].body,first);assert.equal((await serverProject(h)).revision,2);assert.equal(h.workflow.isDirty(),false);
});

test('edits during verified POST/GET reconciliation remain dirty and are never replaced by the old reply',async t=>{
  const h=await harness(t),hold=pause();h.gates.get=hold.promise;h.type('An: Bản đã gửi.');h.save();
  await until(()=>writes(h).length===1&&h.calls.some(v=>!v.body&&v.path==='/api/projects/'+h.getState().project.id));
  h.type('An: Nội dung mới trong lúc đối chiếu.');hold.release();await h.settle();
  assert.equal(h.input(),'An: Nội dung mới trong lúc đối chiếu.');assert.equal(h.workflow.isDirty(),true);
  assert.equal(h.getState().project.document.drama_script.raw_text,'An: Bản đã gửi.');
  h.save();await h.settle();assert.equal((await serverProject(h)).revision,3);assert.equal(h.workflow.isDirty(),false);
});

test('two tabs: real CAS conflict preserves both drafts and requires explicit reviewed rebase',async t=>{
  const first=await harness(t),second=await harness(t,{existingProject:structuredClone(first.getState().project)});
  first.type('An: Nội dung tab thứ nhất.');first.save();await first.settle();
  second.type('An: Nội dung tab thứ hai.');second.save();await second.settle();
  assert.equal(second.workflow.isDirty(),true);assert.equal(second.input(),'An: Nội dung tab thứ hai.');
  assert.equal((await serverProject(first)).document.drama_script.raw_text,'An: Nội dung tab thứ nhất.');
  assert.ok(second.dom.querySelectorAll('p').some(n=>n.textContent.startsWith('Dự án có phiên bản mới hơn.')));
  assert.equal(second.button('Lưu nháp').disabled,true);second.save();assert.equal(writes(second).length,1);
  second.button('Giữ bản đang nhập · dùng phiên bản này làm mốc lưu').listeners.click();await second.settle();
  assert.equal(second.input(),'An: Nội dung tab thứ hai.');assert.equal(second.getState().project.revision,2);
  second.save();await second.settle();assert.equal((await serverProject(second)).revision,3);assert.equal(second.workflow.isDirty(),false);
});

test('GET newer than own POST keeps successful receipt separate from the later conflicting snapshot',async t=>{
  const h=await harness(t),hold=pause();h.gates.post=hold.promise;h.type('An: Bản lưu của tab này.');h.save();await until(()=>writes(h).length===1&&!h.gates.post);
  const request={...writes(h)[0].body,revision:2,request_key:crypto.randomUUID(),text:'An: Thay đổi phát sinh sau.'};
  await h.api('/api/projects/'+h.getState().project.id+'/drama-script',request);hold.release();await h.settle();
  assert.equal(h.input(),'An: Bản lưu của tab này.');assert.equal(h.workflow.isDirty(),true);assert.equal((await serverProject(h)).revision,3);
  assert.ok(h.dom.querySelectorAll('p').some(n=>n.textContent.startsWith('Lần lưu của bạn đã thành công;')));
  assert.equal(Boolean(h.button('Đối chiếu lần lưu trước')),false);assert.equal(h.button('Lưu nháp').disabled,true);
});

test('late response from film A cannot update film B; reopening A reconciles its own saved receipt',async t=>{
  const h=await harness(t),hold=pause(),old=structuredClone(h.getState().project);h.gates.post=hold.promise;h.type('An: Nội dung phim A.');h.save();await until(()=>writes(h).length===1&&!h.gates.post);
  const other=await h.api('/api/projects',{name:'OTHER ISOLATED FILM',prompt:'',workflow_kind:'drama',input_kind:'script'});h.setProject(other);hold.release();await h.settle();
  assert.equal(h.getState().project.id,other.id);assert.equal(h.getState().project.revision,1);assert.equal(h.input(),'');
  const reopened=await h.api('/api/projects/'+old.id);h.setProject(reopened);assert.equal(h.input(),'An: Nội dung phim A.');
  h.button('Đối chiếu lần lưu trước').listeners.click();await h.settle();assert.equal(writes(h).length,1);assert.equal(h.getState().project.revision,2);assert.equal(h.workflow.isDirty(),false);
});

test('validation rejection releases the rejected attempt while network uncertainty retains the old identity',async t=>{
  const h=await harness(t);h.type('x'.repeat(20001));h.save();await h.settle();assert.equal((await serverProject(h)).revision,1);
  assert.equal(Boolean(h.button('Đối chiếu lần lưu trước')),false);assert.equal(h.input().length,20001);
  h.type('An: Bản hợp lệ.');h.gates.before=true;h.save();await h.settle();const request=structuredClone(writes(h).at(-1).body);
  assert.equal((await serverProject(h)).revision,1);h.button('Đối chiếu lần lưu trước').listeners.click();await h.settle();
  assert.deepEqual(writes(h).at(-1).body,request);assert.equal((await serverProject(h)).revision,2);assert.equal(h.workflow.isDirty(),false);
});

test('restart restores uncertain request and newer local text, then saves a new version only after reconciliation',async t=>{
  const storage=new Map(),h=await harness(t,{storage});h.gates.lose=true;h.type('An: Bản đã gửi trước restart.');h.save();await h.settle();
  h.type('An: Bản mới cần giữ qua restart.');const reopened=await serverProject(h);h.workflow.dispose();
  const next=await harness(t,{storage,existingProject:reopened});assert.equal(next.input(),'An: Bản mới cần giữ qua restart.');next.button('Đối chiếu lần lưu trước').listeners.click();await next.settle();
  assert.equal((await serverProject(next)).revision,2);assert.equal(next.input(),'An: Bản mới cần giữ qua restart.');assert.equal(next.workflow.isDirty(),true);
  next.save();await next.settle();assert.equal((await serverProject(next)).revision,3);next.workflow.showStep('voices');
  const last=await harness(t,{storage,existingProject:await serverProject(next)});assert.equal(last.input(),'An: Bản mới cần giữ qua restart.');assert.equal(last.workflow.isDirty(),false);assert.equal(last.dom.body.dataset.dramaStep,'voices');
  for(const value of [h,next,last])assert.ok(!value.calls.some(v=>/approve|\/jobs|compile|narration/.test(v.path)));
});
