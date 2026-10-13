import test from 'node:test';import assert from 'node:assert/strict';
import {initializeTranscriptWords,validateWordReview,wordReviewPayload} from '../native-transcript-words.mjs';
const copy=v=>structuredClone(v),id='1'.repeat(32),seg='seg_'+'2'.repeat(24),tid='trn_'+'3'.repeat(24),asset='4'.repeat(32)+'.mp4';
function fixture(){return {schema_version:'native-transcript-word-review.v1',workspace_id:'wsp_word_fixture',project_id:id,revision:5,timeline_version:null,
  items:[{kind:'video',identity:'ana_'+'5'.repeat(24),asset_id:asset,filename:'Explicit ASR/actor fixture',asset_sha256:'a'.repeat(64),analysis_sha256:'b'.repeat(64),
    source_url:`/api/projects/${id}/transcript-word-review/source/${asset}`,versions:[],current:{transcript_id:tid,version:1,is_original_evidence:true,
      segments:[{segment_id:seg,start_seconds:0,end_seconds:1,text:'Xin chào.',words:[{word_id:'wrd_'+'6'.repeat(24),text:'Xin',start_seconds:0,end_seconds:.4,confidence:.8},
        {word_id:'wrd_'+'7'.repeat(24),text:'chào.',start_seconds:.4,end_seconds:1,confidence:.8}]}]}}],source_media_mutated:false,provider_calls:0,publishing_enabled:false};}
function harness(){
  class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.dataset={};this.value='';this.checked=false;}
    append(...v){this.children.push(...v);}prepend(...v){this.children.unshift(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,fn){this.listeners[k]=fn;}}
  const card=new Node('details');card.id='native-transcript-words-card';
  const find=(n,name)=>n.id===name?n:n.children.map(c=>find(c,name)).find(Boolean);
  const root={getElementById:name=>find(card,name),createElement:tag=>new Node(tag)};
  const state={project:{id,revision:5},workspace_id:'wsp_word_fixture',canEdit:true,active:false,archived:false,dirty:false};
  const calls=[],messages=[],saved=[];let respond=async(path,body)=>{
    const result=fixture();if(body){result.revision++;const current=result.items[0].current;current.version++;current.transcript_id='trn_'+'8'.repeat(24);current.is_original_evidence=false;
      current.provenance={derived_from_transcript_id:tid,word_timestamp_policy:'human_supplied_source_intervals',timing_independently_measured:false,
        segment_id_mapping:{[seg]:'seg_'+'9'.repeat(24)}};
      current.segments[0]={...copy(body.review.segments[0]),segment_id:'seg_'+'9'.repeat(24),confidence:null,
        text:body.review.segments[0].words.map(w=>w.text.trim().normalize('NFC')).join(' '),
        words:body.review.segments[0].words.map((w,i)=>({...w,word_id:'wrd_'+String(i+1).repeat(24),confidence:null}))};}
    return result;};
  const controller=initializeTranscriptWords({root,getState:()=>state,api:async(path,body)=>{calls.push({path,body});return respond(path,body);},
    onWorking:v=>{state.busy=v;},onDirty:v=>{state.dirty=v;state.dirtyPart=v?'transcript_words':null;},
    onMessage:(...v)=>messages.push(v),onSaved:async value=>{saved.push(value);state.project.revision=value.revision;}});
  return {card,state,controller,calls,messages,saved,node:name=>root.getElementById('native-transcript-words-'+name),respond:fn=>respond=fn};
}
test('word editor initialization is inert and source playback uses scoped receipt URL',async()=>{
  const h=harness();assert.equal(h.calls.length,0);await h.controller.load();assert.equal(h.calls.length,1);
  assert.equal(h.controller.fields.size,2);assert.equal(h.node('player').children[0].src,fixture().items[0].source_url);
});
test('manual save requires acknowledgement, preserves explicit times and provider claims are absent',async()=>{
  const h=harness();await h.controller.load();h.controller.fields.get(0).text.value='Vang Nguyễn';
  await h.controller.save();assert.equal(h.calls.length,1);assert.match(h.messages.at(-1)[0],/xác nhận/);
  h.node('ack').checked=true;await h.controller.save();assert.equal(h.saved.length,1);
  const body=h.calls[1].body;assert.equal(body.review.segments[0].words[0].text,'Vang Nguyễn');assert.equal(body.review.segments[0].words[0].start_seconds,0);
  assert.equal(body.review.expected_transcript_id,tid);assert.equal(body.review.acknowledged,true);assert.equal(body.review.segments[0].words[0].confidence,undefined);
});
test('unrelated dirty viewer and active scopes cannot submit and late results cannot install',async()=>{
  const h=harness();await h.controller.load();h.node('ack').checked=true;h.state.canEdit=false;await h.controller.save();assert.equal(h.calls.length,1);
  h.state.canEdit=true;h.controller.sync();await h.controller.load();h.node('ack').checked=true;h.state.dirty=true;h.state.dirtyPart='shots';await h.controller.save();assert.equal(h.calls.length,2);
  h.state.dirty=false;let complete;h.respond(()=>new Promise(resolve=>complete=resolve));const pending=h.controller.load();
  h.state.project={id:'f'.repeat(32),revision:1};complete(fixture());await pending;assert.equal(h.controller.currentBinding().value,null);
});
test('numeric ordering nonfinite empty and acknowledgement errors do not become valid timing',()=>{
  const value=fixture(),item=value.items[0],segment=item.current.segments[0];
  assert.throws(()=>wordReviewPayload(value,item,segment,segment.words,{start:0,end:1,acknowledged:false}));
  assert.throws(()=>wordReviewPayload(value,item,segment,[{text:'a',start_seconds:NaN,end_seconds:1}],{start:0,end:1,acknowledged:true}));
  assert.throws(()=>wordReviewPayload(value,item,segment,[{text:'a',start_seconds:.8,end_seconds:.2}],{start:0,end:1,acknowledged:true}));
  const state={workspace_id:value.workspace_id,project:{id,revision:5}};
  assert.equal(validateWordReview(value,state),value);
  const bad=copy(value);bad.items[0].identity='../publish';assert.throws(()=>validateWordReview(bad,state));
});
test('empty segment bounds cannot silently become zero and cancel discards the draft',async()=>{
  const h=harness();await h.controller.load();h.node('start').value='';h.node('ack').checked=true;
  await h.controller.save();assert.equal(h.calls.length,1);assert.match(h.messages.at(-1)[0],/không hợp lệ/);
  h.controller.fields.get(0).text.value='Changed';h.controller.fields.get(0).text.listeners.input();
  assert.equal(h.node('read').disabled,true);h.node('cancel').listeners.click();
  assert.equal(h.state.dirty,false);assert.equal(h.controller.fields.get(0).text.value,'Xin');
});
test('rehashed-looking save with different returned word intervals is not accepted',async()=>{
  const h=harness();await h.controller.load();h.node('ack').checked=true;
  h.respond(async(path,body)=>{const result=fixture();result.revision++;const current=result.items[0].current;
    current.version++;current.transcript_id='trn_'+'8'.repeat(24);current.is_original_evidence=false;
    current.provenance={derived_from_transcript_id:tid,word_timestamp_policy:'human_supplied_source_intervals',timing_independently_measured:false,
      segment_id_mapping:{[seg]:seg}};current.segments[0].confidence=null;current.segments[0].text='Xin chào.';
    for(const word of current.segments[0].words)word.confidence=null;
    current.segments[0].words[0].end_seconds=.3;return result;});
  await h.controller.save();assert.equal(h.saved.length,0);assert.match(h.messages.at(-1)[0],/đúng chữ hoặc mốc/);
});
