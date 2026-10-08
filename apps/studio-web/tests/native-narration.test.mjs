import test from 'node:test';import assert from 'node:assert/strict';
import {initializeNativeNarration,validateNarrationPage,narrationRequest} from '../native-narration.mjs';
const PROJECT='a'.repeat(32),JOB='b'.repeat(32),SHA='c'.repeat(64);
function state(){return {project:{id:PROJECT,revision:5,document:{canonical_timeline:{}},approval:{revision:5},jobs:[]},canEdit:true,busy:false,dirty:false};}
function page(){return {schema_version:'native-scene-narration-plan-v1',project_id:PROJECT,revision:5,items:[{job_id:JOB,status:'succeeded',voice_input_current:true,timing_apply_current:true,
  result:{plan_sha256:SHA,voice_url:`/api/projects/${PROJECT}/narration/${JOB}/audio`,plan:{schema_version:'native-scene-narration-plan-v1',project_id:PROJECT,job_id:JOB,version:1,
    word_alignment_claimed:false,speech_quality_accepted:false,confidence:null,source_duration_seconds:1.2,recommended_duration_seconds:3.3,fit_narration_template:true,
    items:[{scene:1,narration:'Vang Nguyễn <script>fixture</script>',measured_audio_seconds:.6,recommended_duration_seconds:1.7}]}}}]};}
function harness(){class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.checked=false;this.dataset={};}
  append(...values){this.children.push(...values);}replaceChildren(...values){this.children=values;}setAttribute(name,value){this[name]=value;}addEventListener(name,fn){this.listeners[name]=fn;}
  querySelectorAll(selector){return this.children.flatMap(n=>[...(selector.split(',').includes(n.tagName.toLowerCase())?[n]:[]),...n.querySelectorAll(selector)]);}}
  const root=new Node('details'),dom={getElementById:()=>root,createElement:t=>new Node(t)},current=state(),calls=[],saved=[],messages=[];let answer=async()=>page();
  const controller=initializeNativeNarration({dom,getState:()=>current,newKey:()=> 'explicit-narration-request-key',api:async(...args)=>{calls.push(args);return answer(...args);},onSaved:async()=>saved.push(true),onMessage:(...v)=>messages.push(v)});
  return {root,current,calls,saved,messages,controller,handler:fn=>{answer=fn;},button:text=>root.querySelectorAll('button').find(n=>n.textContent===text)};
}
test('strict plan scope rejects foreign ids URLs promoted alignment and invalid measured durations',()=>{
  assert.equal(validateNarrationPage(page(),state()).items.length,1);
  for(const mutate of [v=>v.project_id='d'.repeat(32),v=>v.revision++,v=>v.items[0].result.voice_url='https://untrusted.invalid/audio',v=>v.items[0].result.plan.word_alignment_claimed=true,
    v=>v.items[0].result.plan.confidence=.99,v=>v.items[0].result.plan.items[0].recommended_duration_seconds=NaN]){const v=page();mutate(v);assert.throws(()=>validateNarrationPage(v,state()));}
});
test('prepare preserves original human approval boundary and apply is acknowledged revision/hash edit',()=>{
  const s=state();assert.deepEqual(narrationRequest(s,page(),'prepare',{requestKey:'explicit-test-key'}).body,{revision:5,kind:'narration',request_key:'explicit-test-key'});
  assert.throws(()=>narrationRequest({...s,project:{...s.project,approval:null}},page(),'prepare',{requestKey:'explicit-test-key'}));assert.throws(()=>narrationRequest(s,page(),'apply',{jobId:JOB}));
  assert.deepEqual(narrationRequest(s,page(),'apply',{jobId:JOB,acknowledged:true}).body,{revision:5,expected_plan_sha256:SHA,acknowledged:true});
  for(const changes of [{dirty:true},{busy:true},{active:true},{canEdit:false},{project:{...s.project,archived:true}}])assert.throws(()=>narrationRequest({...s,...changes},page(),'prepare',{requestKey:'explicit-test-key'}));
});
test('panel performs no initial network or automatic edits and renders narrator text literally',async()=>{
  const h=harness();assert.equal(h.calls.length,0);await h.controller.load();assert.equal(h.calls.length,1);assert.equal(h.saved.length,0);
  assert.equal(h.root.querySelectorAll('audio')[0].src,`/api/projects/${PROJECT}/narration/${JOB}/audio`);const line=h.root.querySelectorAll('p').find(n=>n.textContent.includes('<script>'));
  assert.ok(line);assert.equal(line.innerHTML,undefined);assert.equal(h.button('Áp dụng thời lượng đã đo').disabled,true);
});
test('acknowledged apply sends exact saved plan only and requests reload without final approval',async()=>{
  const h=harness();await h.controller.load();await h.button('Áp dụng thời lượng đã đo').listeners.click();assert.equal(h.calls.filter(c=>c[1]).length,0);
  const ack=h.root.querySelectorAll('input')[0];ack.checked=true;ack.listeners.change();await h.button('Áp dụng thời lượng đã đo').listeners.click();
  assert.deepEqual(JSON.parse(h.calls.at(-1)[1].body),{revision:5,expected_plan_sha256:SHA,acknowledged:true});assert.equal(h.saved.length,1);assert.match(h.messages.at(-1)[0],/duyệt lại/);
});
test('lost preparation response retains exact explicit request key and never automatically resubmits',async()=>{
  const h=harness();h.handler(async()=>{throw new Error('Explicit uncertain fixture');});await h.button('Tạo lời đọc để xem trước').listeners.click();assert.equal(h.calls.length,1);assert.equal(h.saved.length,0);
  const first=h.calls[0][1].body;await h.button('Tạo lời đọc để xem trước').listeners.click();assert.equal(h.calls.length,2);assert.equal(h.calls[1][1].body,first);
});
test('late response cannot restore foreign results and read-only users retain safe audio review',async()=>{
  const h=harness();let release;h.handler(()=>new Promise(r=>release=r));const pending=h.controller.load();h.current.project={...h.current.project,id:'f'.repeat(32)};h.controller.sync();release(page());await pending;
  assert.equal(h.root.querySelectorAll('article').length,0);const read=harness();read.current.canEdit=false;await read.controller.load();assert.equal(read.button('Tạo lời đọc để xem trước').disabled,true);
  assert.equal(read.button('Áp dụng thời lượng đã đo').disabled,true);assert.equal(read.button('Tải kết quả lời đọc').disabled,false);assert.equal(read.root.querySelectorAll('audio').length,1);
});
