import test from 'node:test';import assert from 'node:assert/strict';
import {initializeNativeDrama,validateDramaPage,dramaRequest,splitDialogueLine,validateDramaWrite} from '../native-drama.mjs';
import {currentVideo,canRender} from '../native.mjs';
import {currentStudioRender,boundPreview,previewTimingLabel} from '../shot-studio.mjs';
const P='a'.repeat(32),C='chr_'+'b'.repeat(32),L='line_'+'c'.repeat(32),S='shot_'+'d'.repeat(32),V='nvoice_'+'e'.repeat(32),H='f'.repeat(64);
const config=()=>({narrator_enabled:false,characters:[{character_id:C,name:'An <script>literal</script>',role:'character'}],casting:[{character_id:C,voice_id:V,voice_version:1,voice_sha256:H}],
  lines:[{line_id:L,character_id:C,shot_id:S,text:'Xin chào. Cảm ơn.',enabled:true,speed:1,style:'neutral',pause_after_seconds:.15}]});
const state=()=>({project:{id:P,revision:7,document:{proposal:{},canonical_timeline:{snapshot:{metadata:{}}},compiled_dialogue:{version:1}},jobs:[]},workspace_id:'wsp_ui_fixture',canEdit:true,canManage:true,dirty:false,dirtyPart:null,busy:false});
const page=s=>({schema_version:'native-drama-studio.v1',workspace_id:s.workspace_id,project_id:s.project.id,revision:s.project.revision,
  casting:{version:1,sha256:H,configuration:config()},compiled_current:true,needs_attention:[],error_code:null,shots:[{shot_id:S,scene:1,narration:'Xin chào. Cảm ơn.',narration_enabled:true}],provider_calls:0,human_voice_uat_complete:false});
function harness(){
  class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.value='';this.checked=false;this.attributes={};this.textContent='';}
    append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}setAttribute(k,v){this.attributes[k]=v;this[k]=v;}getAttribute(k){return this.attributes[k]??null;}
    addEventListener(name,fn){this.listeners[name]=fn;}querySelectorAll(selector){const names=selector.split(',');return this.children.flatMap(n=>[...(names.includes(n.tagName.toLowerCase())?[n]:[]),...n.querySelectorAll(selector)]);}}
  const root=new Node('details'),dom={getElementById:()=>root,createElement:t=>new Node(t)},current=state(),calls=[],messages=[],saved=[];let serial=1,override=null,controller;
  const voice={voice_id:V,version:1,definition_sha256:H,definition:{display_name:'Giọng <img src=x>',provider:'vieneu-local',model:'vieneu-v3-turbo',provider_voice_id:'Preset A',rights_status:'unknown',source_type:'provider_preset'}};
  const base=`/api/projects/${P}/drama-casting`;
  async function answer(path,options){if(options){const body=JSON.parse(options.body);saved.push(body);return path.startsWith('/api/voice-library')?{voice_id:V,version:1,definition_sha256:H}:{project_id:P,project_revision_at_write:body.revision+1};}if(path.endsWith('/drama-casting'))return page(current);
    if(path==='/api/voice-library')return {items:[voice]};if(path==='/api/voice-library/presets')return {provider:'vieneu-local',status:'METADATA_AVAILABLE',model:'vieneu-v3-turbo',voices:[{provider_voice_id:'Preset A',display_name:'Preset A'}]};
    if(path==='/api/drama-series')return {items:[]};throw Error('Unexpected route');}
  controller=initializeNativeDrama({dom,getState:()=>current,newKey:()=>`${String(serial++).padStart(8,'0')}-1111-4111-8111-111111111111`,
    api:async(...args)=>{calls.push(args);return override?override(...args):answer(...args);},onMessage:(...v)=>messages.push(v),onWorking:v=>{current.busy=v;},
    onDirty:v=>{if(v){current.dirty=true;current.dirtyPart='drama';}else if(current.dirtyPart==='drama'){current.dirty=false;current.dirtyPart=null;}},
    onSaved:async()=>{current.project.revision++;controller.sync();}});
  return {root,current,calls,messages,saved,controller,base,override:fn=>override=fn,answer,action:name=>root.querySelectorAll('button').find(n=>n.getAttribute('data-drama-action')===name),
    label:text=>root.querySelectorAll('label').find(n=>n.textContent===text),editName:async()=>{const input=root.querySelectorAll('label').find(n=>n.textContent==='Tên nhân vật').children[0];input.value='An mới';await input.listeners.input();}};
}
test('page scope revision and acceptance flags are strict',()=>{
  const s=state();assert.equal(validateDramaPage(page(s),s).compiled_current,true);
  for(const mutate of [v=>v.project_id='0'.repeat(32),v=>v.workspace_id='wsp_foreign',v=>v.revision++,v=>v.human_voice_uat_complete=true,v=>v.provider_calls=1,v=>v.shots[0].shot_id='raw-id']){
    const value=page(s);mutate(value);assert.throws(()=>validateDramaPage(value,s));}
});
test('save explicitly mutates canonical script and carries exact current CAS',()=>{
  const s=state(),p=page(s);const r=dramaRequest(s,p,'save',{configuration:config(),requestKey:'explicit-save-key'});
  assert.equal(r.path,`/api/projects/${P}/drama-casting`);assert.deepEqual(r.body,{revision:7,request_key:'explicit-save-key',expected_version:1,configuration:config(),sync_canonical_script:true,clear_legacy_voice_policy:false});
  const c=config();c.lines[0].character_id='';assert.throws(()=>dramaRequest(s,p,'save',{configuration:c,requestKey:'explicit-save-key'}));
  assert.equal(dramaRequest(s,p,'save',{configuration:config(),requestKey:'explicit-save-key',clearLegacyVoicePolicy:true}).body.clear_legacy_voice_policy,true);
});
test('compile and targeted take never approve or enqueue automatically',()=>{
  const s=state(),p=page(s),opts={requestKey:'explicit-test-key',lineId:L};
  assert.deepEqual(dramaRequest(s,p,'compile',opts).body,{revision:7,request_key:'explicit-test-key',expected_version:1});
  assert.deepEqual(dramaRequest(s,p,'take',opts).body,{revision:7,request_key:'explicit-test-key',expected_casting_sha256:H,line_ids:[L]});
  for(const action of ['compile','take','series-save','series-apply'])assert.throws(()=>dramaRequest({...s,dirty:true,dirtyPart:'drama'},p,action,opts));
  const p2=page(s);p2.casting.configuration.lines[0].enabled=false;assert.throws(()=>dramaRequest(s,p2,'take',opts));
});
test('read-only busy source archived and unrelated dirty state block mutation',()=>{
  const s=state(),opts={configuration:config(),requestKey:'explicit-save-key'};
  for(const delta of [{canEdit:false},{busy:true},{active:true},{dirty:true,dirtyPart:'prompt'},{project:{...s.project,archived:true}},
    {project:{...s.project,document:{canonical_timeline:{snapshot:{metadata:{native_auto_edit_schema:'native-auto-edit-timeline-v1'}}}}}}])assert.throws(()=>dramaRequest({...s,...delta},page(s),'save',opts));
});
test('splitting keeps speaker and shot and rejects cutting through a word',()=>{
  const original=config(),next=splitDialogueLine(original,0,10,'line_'+'1'.repeat(32));assert.equal(original.lines.length,1);assert.equal(next.lines.length,2);
  assert.equal(next.lines[0].text,'Xin chào.');assert.equal(next.lines[1].text,'Cảm ơn.');assert.ok(next.lines.every(v=>v.character_id===C&&v.shot_id===S));
  for(const position of [0,5,999,NaN])assert.throws(()=>splitDialogueLine(original,0,position,'line_'+'1'.repeat(32)));
});
test('panel makes no startup requests and shows voice rights and text literally',async()=>{
  const h=harness();assert.equal(h.calls.length,0);await h.controller.load();assert.equal(h.calls.length,4);assert.equal(h.saved.length,0);
  const literal=h.root.querySelectorAll('p').find(n=>n.textContent.includes('<img src=x>'));assert.ok(literal);assert.equal(literal.innerHTML,undefined);
  assert.equal(h.label('Tên nhân vật').children[0].value,'An <script>literal</script>');assert.equal(h.label('Có người kể'),undefined);
  assert.ok(h.root.querySelectorAll('input').some(n=>n.type==='checkbox'&&!n.checked));
});
test('narrator starts off and new draft requires manually choosing speaker and voice',async()=>{
  const h=harness();h.override(async(path,options)=>{const value=await h.answer(path,options);if(path.endsWith('/drama-casting')&&!options)value.casting=null;return value;});
  await h.controller.load();await h.action('start').listeners.click();assert.equal(h.controller.isDirty(),true);
  assert.equal(h.label('Giọng của nhân vật trong phim này').children[0].value,'');assert.equal(h.label('Người nói · câu 1').children[0].value,'');
  await h.action('save').listeners.click();assert.equal(h.calls.filter(c=>c[1]).length,0);assert.match(h.messages.at(-1)[0],/Chọn người nói/);
});
test('lost save response pins exact request and only explicit retry resubmits',async()=>{
  const h=harness();await h.controller.load();await h.editName();h.override(async(path,options)=>{if(options)throw Error('Explicit uncertain response');return h.answer(path,options);});
  await h.action('save').listeners.click();const first=h.calls.at(-1);assert.equal(first[0],h.base);const count=h.calls.length;await h.action('save').listeners.click();
  assert.equal(h.calls.length,count+1);assert.equal(h.calls.at(-1)[1].body,first[1].body);assert.equal(h.action('character').disabled,true);assert.equal(h.saved.length,0);
});
test('revoked edit permission blocks explicit replay before dispatch',async()=>{
  const h=harness();await h.controller.load();await h.editName();h.override(async()=>{throw Error('Uncertain fixture');});await h.action('save').listeners.click();const count=h.calls.length;
  h.current.canEdit=false;h.controller.controls();await h.action('save').listeners.click();assert.equal(h.calls.length,count);
});
test('late foreign response never installs data or changes current project',async()=>{
  const h=harness();let release;const original=page(h.current);h.override((path)=>path.endsWith('/drama-casting')?new Promise(r=>release=r):h.answer(path));
  const loading=h.controller.load();h.current.project={...h.current.project,id:'9'.repeat(32)};h.controller.sync();release(original);await loading;
  assert.equal(h.root.querySelectorAll('textarea').length,0);assert.equal(h.controller.isDirty(),false);assert.equal(h.saved.length,0);
});
test('viewer can load safely and management action cannot write library',async()=>{
  const h=harness();h.current.canEdit=false;h.current.canManage=false;await h.controller.load();assert.equal(h.action('load').disabled,false);assert.equal(h.action('compile').disabled,true);
  const count=h.calls.length;await h.action('voice-save').listeners.click();assert.equal(h.calls.length,count);assert.match(h.messages.at(-1)[0],/Owner/);
});
test('unknown rights remain unchecked and cannot be promoted without evidence',async()=>{
  const h=harness();await h.controller.load();const choice=h.label('Thêm hoặc sửa giọng trong thư viện').children[0];choice.value=V;choice.listeners.change();
  const right=h.root.querySelectorAll('label').find(n=>n.children.some(c=>c.textContent?.startsWith('Tôi xác nhận có quyền'))).children[0];assert.equal(right.checked,false);
  right.checked=true;right.listeners.change();const count=h.calls.length;await h.action('voice-save').listeners.click();assert.equal(h.calls.length,count);assert.match(h.messages.at(-1)[0],/giấy phép/);
});
test('series apply sends selected immutable version and preserves separate manual approval',()=>{
  const s=state(),series={series_id:'nseries_'+'1'.repeat(32),version:3,sha256:H};const r=dramaRequest(s,page(s),'series-apply',{series,requestKey:'explicit-series-key'});
  assert.deepEqual(r.body,{revision:7,request_key:'explicit-series-key',series_id:series.series_id,version:3,expected_sha256:H});assert.ok(!('approved' in r.body));
});
test('successful save reloads current project without dispatching TTS render or approval',async()=>{
  const h=harness();await h.controller.load();await h.editName();await h.action('save').listeners.click();
  const writes=h.calls.filter(c=>c[1]);assert.equal(writes.length,1);assert.equal(writes[0][0],h.base);assert.equal(h.saved.length,1);assert.equal(h.current.project.revision,8);assert.equal(h.controller.isDirty(),false);
  assert.equal(h.calls.filter(c=>/\/jobs|\/approve|\/publications/.test(c[0])).length,0);
});
test('foreign write receipt retains pending exact request and does not reload or claim success',async()=>{
  const h=harness();await h.controller.load();await h.editName();h.override(async(path,options)=>options?{project_id:'8'.repeat(32),project_revision_at_write:8}:h.answer(path));
  await h.action('save').listeners.click();assert.equal(h.current.project.revision,7);assert.equal(h.controller.isDirty(),true);assert.match(h.messages.at(-1)[0],/không thuộc/);
  const body=h.calls.at(-1)[1].body;await h.action('save').listeners.click();assert.equal(h.calls.at(-1)[1].body,body);
});
test('write receipt rejects promoted approval voice acceptance and wrong revision',()=>{
  const request={body:{revision:7}};
  for(const delta of [{project_revision_at_write:9},{human_approval_granted:true},{human_voice_uat_complete:true}])assert.throws(()=>validateDramaWrite({project_id:P,project_revision_at_write:8,...delta},request,'save',P));
});
test('revoked library binding closes current render and preview without hiding historical exports',()=>{
  const job={kind:'render',status:'succeeded',revision:7},project={...state().project,approval:{revision:7},jobs:[job],drama_voice_binding:{current:true}};
  assert.equal(currentVideo(project),job);assert.equal(currentStudioRender(project),job);assert.equal(canRender(project,false,false),true);
  const stale={...project,drama_voice_binding:{current:false}};assert.equal(currentVideo(stale),null);assert.equal(currentStudioRender(stale),null);assert.equal(canRender(stale,false,false),false);
  const preview=boundPreview(stale,{status:'READY',video_url:'/private-current-preview'});assert.equal(preview.status,'STALE');assert.equal(preview.video_url,null);
});
test('dialogue playback describes selected character voices rather than the legacy narrator',()=>{
  const label=previewTimingLabel('final',null,{document:{drama_casting:{}}});assert.match(label,/giọng theo phân vai/);assert.doesNotMatch(label,/Thùy Dung/);
});
test('voice and dialogue drafts cannot trap each other with unsaved mixed forms',async()=>{
  const h=harness();await h.controller.load();const voiceName=h.label('Tên hiển thị').children[0];voiceName.value='Giọng mới';voiceName.listeners.input();
  assert.equal(h.label('Tên nhân vật').children[0].disabled,true);assert.equal(h.action('character').disabled,true);
  await h.action('discard').listeners.click();await h.editName();assert.equal(h.label('Tên hiển thị').children[0].disabled,true);assert.equal(h.label('Thêm hoặc sửa giọng trong thư viện').children[0].disabled,true);
  assert.equal(h.action('save').disabled,false);assert.equal(h.calls.filter(c=>c[1]).length,0);
});
test('editing an unsupported library voice cannot silently change provider model or locale',async()=>{
  const h=harness();h.override(async(path,options)=>{const value=await h.answer(path,options);if(path==='/api/voice-library')value.items[0].definition.provider='other-provider';return value;});
  await h.controller.load();const choice=h.label('Thêm hoặc sửa giọng trong thư viện').children[0];choice.value=V;choice.listeners.change();assert.equal(h.action('voice-save').disabled,true);
  const count=h.calls.length;await h.action('voice-save').listeners.click();assert.equal(h.calls.length,count);assert.match(h.messages.at(-1)[0],/chỉ sửa giọng preset local/);
});
