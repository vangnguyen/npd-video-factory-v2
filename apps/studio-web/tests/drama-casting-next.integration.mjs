// Real Native HTTP and production reload callbacks. DOM contract, never browser QA.
import test from 'node:test';import assert from 'node:assert/strict';
import {initializeNativeDrama} from '../native-drama.mjs';
import {initializeDramaWorkflow,dramaProgress} from '../drama-workflow.mjs';
import * as native from '../native.mjs';
import {Doc,Node} from './support/drama-dom.mjs';
const origin=process.env.VF_DRAMA_TEST_ORIGIN;
const SCRIPT='CẢNH 1: Chiếc phong bì\n(An đặt phong bì lên bàn.)\nAn: Mình tìm thấy phong bì của bạn.\nBình: Cảm ơn, mình đã tìm nó cả buổi.';
const until=async fn=>{for(let n=0;n<500;n++){if(fn())return;await new Promise(r=>setTimeout(r,10));}throw Error('Casting integration did not settle');};
export async function castingHarness(t,{storage=new Map(),project:existing=null,script=SCRIPT,confirm=true}={}){
  const response=await fetch(origin+'/api/session'),cookie=response.headers.get('set-cookie').split(';')[0],session=await response.json();
  const calls=[],messages=[],gates={};let project=null,busy=false,dirty=false,dirtyPart=null,scriptDirty=false,castingDirty=false,flow,drama;
  const api=async(path,options)=>{const body=native.nativeRequestBody(options);calls.push({path,body:body?structuredClone(body):null});
    const r=await fetch(origin+path,{method:body?'POST':'GET',headers:{Cookie:cookie,...(body?{'Content-Type':'application/json','X-VF-CSRF':session.csrf}:{})},body:body?JSON.stringify(body):undefined}),value=await r.json();
    if(!body&&/^\/api\/projects\/[a-f0-9]{32}$/.test(path)&&gates.projectReadLose){delete gates.projectReadLose;throw TypeError('Explicit project GET response lost');}
    if(body&&path.endsWith('/drama-casting')&&gates.post){const gate=gates.post;delete gates.post;gates.postWaiting=true;await gate;delete gates.postWaiting;}
    if(!r.ok){const e=Error(value.code);e.code=value.code;e.status=r.status;throw e;}
    if(body&&path.endsWith('/drama-casting')&&gates.lose){delete gates.lose;throw TypeError('Explicit response lost after server commit');}
    return value;};
  project=existing??await api('/api/projects',{name:'CASTING TO SCENES CONTRACT FIXTURE',prompt:'',input_kind:'script',workflow_kind:'drama'});
  if(!existing){await api('/api/projects/'+project.id+'/drama-script',{revision:project.revision,request_key:crypto.randomUUID(),text:script,confirm_characters:confirm});project=await api('/api/projects/'+project.id);}
  const dom=new Doc(),add=(tag,id,cls,parent=dom.body)=>{const n=new Node(tag);if(id)n.setAttribute('id',id);if(cls)n.setAttribute('class',cls);parent.append(n);return n;};
  add('nav',null,'stage-navigation');for(const stage of ['script','assets','video','storyboard'])add('section','stage-'+stage).setAttribute('data-stage-panel',stage);
  for(const id of ['brief-card','proposal-card','video-stage-body','video-review-body','studio-title','runtime-voice-summary'])add('div',id);
  const review=add('div',null,'review',dom.getElementById('proposal-card'));add('button','approve',null,review);add('section','script-only-review',null,dom.getElementById('stage-script'));add('details','native-drama-panel');add('details','native-narration-panel');
  const getState=()=>({project,busy,dirty,dirtyPart,workspace_id:'wsp_native_local',canEdit:true,canManage:false,dramaScriptDirty:scriptDirty,dramaCastingDirty:castingDirty});
  const mark=(part,value)=>{if(part==='drama-script')scriptDirty=value;else castingDirty=value;
    if(native.nativeDramaDirtyPart){dirtyPart=native.nativeDramaDirtyPart({script:scriptDirty,casting:castingDirty},dirtyPart);dirty=Boolean(dirtyPart);}else if(value){dirty=true;dirtyPart=part;}else if(dirtyPart===part){dirty=false;dirtyPart=null;}
    drama?.controls();flow?.controls();};
  const renderProject=reset=>{if(reset){dirty=false;dirtyPart=null;}drama?.sync();flow?.sync();};
  const reload=native.createNativeProjectReload({api,getState,onProject:p=>project=p,renderProject,projects:async()=>{},schedule(){}});
  drama=initializeNativeDrama({api,getState,dom,storage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},onDirty:v=>mark('drama',v),onWorking:v=>{busy=v;flow?.controls();},onMessage:(text,error)=>messages.push({text,error}),
    onSaved:native.nativeDramaCastingCallback?native.nativeDramaCastingCallback(reload):async()=>{await reload(true);}});
  flow=initializeDramaWorkflow({api,getState,dom,storage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},drama,onCreated:async p=>{project=p;renderProject(true);},onSaved:native.nativeDramaSaveCallback(reload),onDirty:v=>mark('drama-script',v),onWorking:v=>busy=v,onMessage:(text,error)=>messages.push({text,error}),showStage(){}});
  t.after(()=>{flow.dispose();drama.dispose?.();});flow.showStep('voices');await until(()=>!drama.isWorking());await drama.load();
  const button=text=>dom.querySelectorAll('button').find(v=>v.textContent===text),action=name=>dom.getElementById('native-drama-panel').querySelectorAll('button').find(v=>v.getAttribute('data-drama-action')===name);
  const voices=(await api('/api/voice-library')).items;
  const choose=(index,voice)=>{const select=dom.querySelectorAll('label').filter(n=>n.textContent==='Giọng của nhân vật trong phim này')[index].children[0];select.value=voice.voice_id;select.listeners.change();};
  return {dom,api,flow,drama,calls,messages,voices,getState,storage,gates,button,action,choose,settle:()=>until(()=>!busy&&!drama.isWorking()&&!flow.isWorking()),project:()=>project,
    select:async value=>{project=value;scriptDirty=castingDirty=dirty=false;dirtyPart=null;renderProject(true);}};
}

const saves=h=>h.calls.filter(v=>v.body&&v.path.endsWith('/drama-casting'));
const next=h=>h.button('Lưu phân vai & tiếp tục')??h.button('Đối chiếu phân vai & tiếp tục');
async function selectBoth(h){h.choose(0,h.voices[0]);h.choose(1,h.voices[1]);}
async function continueToScenes(h){assert.equal(next(h).disabled,false,JSON.stringify(h.drama.continuationState()));await next(h).listeners.click();await h.settle();assert.equal(h.dom.body.dataset.dramaStep,'scenes',JSON.stringify(h.messages));}

test('two selected voices can be saved and opened in scenes without media or audio',async t=>{
  const h=await castingHarness(t);h.choose(0,h.voices[0]);h.choose(1,h.voices[1]);await h.action('save').listeners.click();await h.settle();
  const p=h.project(),before=p.document.drama_casting.configuration;
  console.log(JSON.stringify({case:'casting-save',revision:p.revision,confirmed:dramaProgress(p).confirmed,uncast:dramaProgress(p).uncast,dirty:h.getState().dirty,dirtyPart:h.getState().dirtyPart,next_disabled:h.button('Tiếp tục →')?.disabled,casting_version:p.document.drama_casting.version}));
  const next=h.button('Lưu phân vai & tiếp tục')??h.button('Tiếp tục →');assert.equal(next.disabled,false);await next.listeners.click();await h.settle();
  assert.equal(h.dom.body.dataset.dramaStep,'scenes');assert.equal(p.approval,null);assert.deepEqual(p.jobs,[]);assert.equal(p.document.assets.length,0);assert.equal(before.casting.length,2);
});

test('personality note after confirmation preserves confirmation casting line IDs and scene IDs',async t=>{
  const h=await castingHarness(t);h.choose(0,h.voices[0]);h.choose(1,h.voices[1]);await h.action('save').listeners.click();await h.settle();
  const before=structuredClone(h.project().document),note=h.dom.querySelectorAll('label').find(v=>v.textContent==='Vai trò / tính cách của An (tùy chọn)').children[0];
  note.value='Điềm tĩnh, nói ngắn gọn.';note.listeners.input();await until(()=>h.calls.filter(v=>v.path.endsWith('/drama-script')&&v.body).length>=2);await h.settle();
  const after=h.project().document;console.log(JSON.stringify({case:'note-save',confirmed:after.drama_script.characters_confirmed,casting_version:after.drama_casting.version,dirty:h.getState().dirty,dirtyPart:h.getState().dirtyPart}));
  assert.equal(after.drama_script.characters_confirmed,true);assert.deepEqual(after.drama_casting,before.drama_casting);assert.deepEqual(after.canonical_timeline,before.canonical_timeline);
  const next=h.button('Lưu phân vai & tiếp tục')??h.button('Tiếp tục →');assert.equal(next.disabled,false);await next.listeners.click();await h.settle();assert.equal(h.dom.body.dataset.dramaStep,'scenes');
});

test('primary action saves once then continues; saved casting continues without another revision',async t=>{
  const h=await castingHarness(t);await selectBoth(h);const before=structuredClone(h.project().document.drama_casting.configuration);await continueToScenes(h);
  assert.equal(saves(h).length,1);assert.equal(h.project().revision,3);assert.equal(h.project().approval,null);assert.deepEqual(h.project().jobs,[]);
  const after=h.project().document.drama_casting.configuration;assert.deepEqual(after.characters,before.characters);assert.deepEqual(after.lines,before.lines);assert.equal(after.narrator_enabled,false);
  h.flow.showStep('voices');await h.settle();await continueToScenes(h);assert.equal(saves(h).length,1);assert.equal(h.project().revision,3);
  h.flow.showStep('voices');await h.settle();h.choose(1,h.voices[1]);h.choose(0,h.voices[0]);await continueToScenes(h);assert.equal(saves(h).length,1);assert.equal(h.project().revision,3);
});

test('real voice picker callbacks select two voices and continue without generating samples',async t=>{
  const h=await castingHarness(t);
  for(const [index,name] of ['An','Bình'].entries()){
    await h.button('Nghe và chọn giọng cho '+name).listeners.click();
    const cards=h.dom.querySelectorAll('.voice-card'),card=cards.find(v=>v.querySelector('h3').textContent===h.voices[index].definition.display_name);
    const choice=card.querySelectorAll('button').find(v=>v.textContent==='Chọn cho '+name);assert.ok(choice);assert.equal(choice.disabled,false);choice.listeners.click();
  }
  await continueToScenes(h);const saved=h.project().document.drama_casting.configuration;
  assert.equal(saved.casting.length,2);assert.equal(saves(h).length,1);assert.equal(h.calls.filter(v=>v.body&&v.path==='/api/voice-auditions').length,0);
});

test('missing Bình is named and focused; one optional silent role and disabled narrator never require voices',async t=>{
  const h=await castingHarness(t);h.choose(0,h.voices[0]);assert.equal(next(h).disabled,true);assert.match(next(h).title,/Bình/);
  h.button('Chọn giọng còn thiếu').listeners.click();const selects=h.dom.querySelectorAll('label').filter(v=>v.textContent==='Giọng của nhân vật trong phim này');assert.equal(selects[1].children[0].focused,true);
  h.choose(1,h.voices[1]);h.action('character').listeners.click();assert.equal(h.drama.continuationState().needed,2);assert.equal(h.drama.continuationState().assigned,2);
  await continueToScenes(h);assert.equal(h.project().document.drama_casting.configuration.characters.length,3);assert.equal(h.project().document.drama_casting.configuration.casting.length,2);
});

test('intentional shared voice is advisory and does not block scenes',async t=>{
  const h=await castingHarness(t);h.choose(0,h.voices[0]);h.choose(1,h.voices[0]);assert.equal(h.drama.continuationState().shared_voice_warning,true);await continueToScenes(h);
});

test('response lost after server commit replays only the exact casting request without duplicate version',async t=>{
  const h=await castingHarness(t);await selectBoth(h);h.gates.lose=true;await next(h).listeners.click();await h.settle();
  assert.equal(h.dom.body.dataset.dramaStep,'voices');assert.equal(h.getState().dirty,true);assert.equal(h.drama.continuationState().pending,true);
  const committed=await h.api('/api/projects/'+h.project().id);assert.equal(committed.revision,3);await continueToScenes(h);
  assert.equal(saves(h).length,2);assert.deepEqual(saves(h)[0],saves(h)[1]);assert.equal(h.project().revision,3);assert.equal(h.project().document.drama_casting.version,2);
});

test('verified POST with unavailable project read keeps its receipt and retries only the GET',async t=>{
  const h=await castingHarness(t);await selectBoth(h);h.gates.projectReadLose=true;await next(h).listeners.click();await h.settle();
  assert.equal(h.dom.body.dataset.dramaStep,'voices');assert.equal(h.drama.continuationState().pending,true);assert.equal(saves(h).length,1);
  await continueToScenes(h);assert.equal(saves(h).length,1);assert.equal(h.project().revision,3);
});

test('manual save and continue while response pending cannot create competing casting writes',async t=>{
  const h=await castingHarness(t);await selectBoth(h);let release;h.gates.post=new Promise(r=>release=r);const saving=h.action('save').listeners.click();await until(()=>saves(h).length===1);
  assert.equal(next(h).disabled,true);await next(h).listeners.click();assert.equal(saves(h).length,1);release();await saving;await h.settle();await continueToScenes(h);assert.equal(saves(h).length,1);
});

test('true two-tab conflict preserves local selections and server casting until explicit comparison',async t=>{
  const a=await castingHarness(t),b=await castingHarness(t,{project:structuredClone(a.project())});await selectBoth(a);b.choose(0,b.voices[1]);b.choose(1,b.voices[0]);await continueToScenes(a);
  await next(b).listeners.click();await b.settle();assert.equal(b.dom.body.dataset.dramaStep,'voices');assert.equal(b.getState().dirty,true);assert.equal(b.drama.continuationState().pending,false);assert.match(next(b).title,/phiên bản mới hơn/);
  const persisted=await a.api('/api/projects/'+a.project().id);assert.deepEqual(persisted.document.drama_casting,a.project().document.drama_casting);
  const chosen=b.dom.querySelectorAll('label').filter(v=>v.textContent==='Giọng của nhân vật trong phim này');assert.equal(chosen[0].children[0].value,b.voices[1].voice_id);assert.equal(chosen[1].children[0].value,b.voices[0].voice_id);
  assert.equal(b.action('adopt-casting').disabled,false);await b.action('adopt-casting').listeners.click();await b.settle();await continueToScenes(b);assert.equal(b.project().revision,4);
});

test('reopening restores the exact pending request; saved voices and last step survive restart',async t=>{
  const h=await castingHarness(t);await selectBoth(h);h.gates.lose=true;await next(h).listeners.click();await h.settle();h.flow.dispose();h.drama.dispose();
  const committed=await h.api('/api/projects/'+h.project().id),reopened=await castingHarness(t,{storage:h.storage,project:committed});assert.equal(reopened.drama.continuationState().pending,true);await continueToScenes(reopened);
  assert.deepEqual(saves(reopened)[0].body,saves(h)[0].body);assert.equal(reopened.project().revision,3);assert.equal(reopened.storage.get('vf-drama-step:'+h.project().id),'scenes');
  const again=await castingHarness(t,{storage:h.storage,project:await h.api('/api/projects/'+h.project().id)});const selects=again.dom.querySelectorAll('label').filter(v=>v.textContent==='Giọng của nhân vật trong phim này');assert.equal(selects[0].children[0].value,h.voices[0].voice_id);assert.equal(selects[1].children[0].value,h.voices[1].voice_id);
});

test('late response from film A cannot install casting in film B',async t=>{
  const h=await castingHarness(t);await selectBoth(h);let release;h.gates.post=new Promise(r=>release=r);const saving=next(h).listeners.click();await until(()=>saves(h).length===1);
  const b=await h.api('/api/projects',{name:'LATE RESPONSE TARGET FIXTURE',prompt:'',input_kind:'script',workflow_kind:'drama'});await h.select(b);release();await saving;await h.settle();assert.equal(h.project().id,b.id);assert.equal(h.project().revision,1);assert.equal(h.project().document.drama_casting,undefined);assert.equal(h.project().approval,null);
});

test('validation rejection retains form and permits a corrected request without a stale pending write',async t=>{
  const h=await castingHarness(t);await selectBoth(h);const name=h.dom.querySelectorAll('label').find(v=>v.textContent==='Tên nhân vật').children[0];name.value='';name.listeners.input();
  await next(h).listeners.click();await h.settle();assert.equal(h.dom.body.dataset.dramaStep,'voices');assert.equal(h.getState().dirty,true);assert.equal(h.drama.continuationState().pending,false);assert.equal(name.value,'');
  name.value='An';name.listeners.input();await continueToScenes(h);assert.equal(h.project().revision,3);assert.equal(h.project().document.drama_casting.configuration.casting.length,2);
});

test('real script edit requires explicit speaker confirmation while retaining compatible voices and IDs',async t=>{
  const h=await castingHarness(t);await selectBoth(h);await h.action('save').listeners.click();await h.settle();const before=structuredClone(h.project().document.drama_casting.configuration);
  await h.api('/api/projects/'+h.project().id+'/drama-script',{revision:h.project().revision,request_key:crypto.randomUUID(),text:SCRIPT.replace('cả buổi.','cả ngày.'),confirm_characters:false});
  await h.select(await h.api('/api/projects/'+h.project().id));await h.settle();await h.drama.load();assert.equal(h.project().document.drama_script.characters_confirmed,false);assert.equal(next(h).disabled,true);
  const confirm=h.button('Xác nhận người nói');assert.equal(confirm.hidden,false);assert.equal(confirm.disabled,false);await confirm.listeners.click();await h.settle();await h.drama.load();
  assert.equal(h.project().document.drama_script.characters_confirmed,true);assert.deepEqual(h.project().document.drama_casting.configuration.casting,before.casting);assert.deepEqual(h.project().document.drama_casting.configuration.lines.map(v=>v.line_id),before.lines.map(v=>v.line_id));
  await continueToScenes(h);assert.equal(h.project().approval,null);assert.deepEqual(h.project().jobs,[]);
});

test('later server revision is separated from this tab own successful write without overwriting its form',async t=>{
  const h=await castingHarness(t);await selectBoth(h);let release;h.gates.post=new Promise(r=>release=r);const saving=next(h).listeners.click();await until(()=>h.gates.postWaiting===true);
  const latest=await h.api('/api/projects/'+h.project().id);await h.api('/api/projects/'+latest.id+'/drama-script',{revision:latest.revision,request_key:crypto.randomUUID(),text:SCRIPT,character_notes:{fixture:'Later edit'},confirm_characters:false});
  release();await saving;await h.settle();assert.equal(h.dom.body.dataset.dramaStep,'voices');assert.equal(h.getState().dirty,true);assert.equal(h.drama.continuationState().pending,false);assert.match(next(h).title,/phiên bản mới hơn/);
  const current=await h.api('/api/projects/'+latest.id);assert.equal(current.revision,4);assert.equal(current.document.drama_casting.version,2);assert.equal(saves(h).length,1);assert.equal(h.project().revision,2);
});
