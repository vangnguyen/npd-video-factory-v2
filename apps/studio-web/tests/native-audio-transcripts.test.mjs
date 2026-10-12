import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import {initializeNativeAudioTranscripts,validateAudioTranscripts} from '../native-audio-transcripts.mjs';
import {mediaAnalysisPending} from '../native.mjs';
const fixture=JSON.parse(readFileSync(new URL('./fixtures/native-audio-transcripts.json',import.meta.url),'utf8')),copy=v=>structuredClone(v);
function harness(page=fixture.initial){
  class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.dataset={};this.value='';}
    append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(name,fn){this.listeners[name]=fn;}}
  const card=new Node('details');card.id='native-audio-transcripts-card';card.hidden=true;
  const walk=(n,id)=>n.id===id?n:n.children.map(c=>walk(c,id)).find(Boolean),root={getElementById:id=>walk(card,id),createElement:t=>new Node(t)};
  const state={workspace_id:page.workspace_id,project:{id:page.project_id,revision:page.revision},canEdit:true,dirty:false,busy:false,active:false};
  const calls=[],messages=[],saved=[];let respond=async(path,body)=>copy(body?fixture.changed:page);
  const controller=initializeNativeAudioTranscripts({root,getState:()=>state,api:async(path,body)=>{calls.push({path,body});return respond(path,body);},
    onWorking:v=>{state.busy=v;},onMessage:(...v)=>messages.push(v),onSaved:async v=>{saved.push(v);state.project.revision=v.revision;}});
  const node=n=>root.getElementById('native-audio-transcripts-'+n);
  return{card,state,controller,calls,messages,saved,node,respond:fn=>{respond=fn;},text(v=fixture.changed.items[0].current.segments[0].text){controller.fields.values().next().value.value=v;}};
}
test('saved actual HTTP fixtures are explicit mock recognition and validate original/edit/restore history',()=>{
  assert.equal(fixture.fixture_human,true);assert.equal(fixture.mock_ASR,true);assert.equal(fixture.real_provider_calls,0);assert.equal(fixture.owner_UAT,false);assert.equal(fixture.browser_rendered,false);
  for(const page of[fixture.initial,fixture.changed,fixture.restored,fixture.reopened])assert.equal(validateAudioTranscripts(page,{workspace_id:page.workspace_id,project:{id:page.project_id,revision:page.revision}}),page);
  assert.equal(fixture.changed.items[0].current.segments[0].words.length,0);assert.equal(fixture.restored.items[0].current.segments[0].words.length,2);
});

test('human-reviewed initial audio evidence is labelled derived and retains its provider candidate reference',()=>{
  const page=copy(fixture.initial);
  for(const t of [page.items[0].original,page.items[0].current,page.items[0].versions[0]]){t.is_original_evidence=false;t.provenance.human_edit=true;t.provenance.provider_original_candidate_sha256='a'.repeat(64);}
  const state={workspace_id:page.workspace_id,project:{id:page.project_id,revision:page.revision}};assert.equal(validateAudioTranscripts(page,state),page);
  for(const t of [page.items[0].original,page.items[0].current,page.items[0].versions[0]])delete t.provenance.provider_original_candidate_sha256;
  assert.throws(()=>validateAudioTranscripts(page,state));
});
test('initialization is inert and explicit read edits the actual source without rendering HTML from transcript',async()=>{
  const h=harness();assert.equal(h.calls.length,0);assert.equal(h.card.hidden,false);await h.controller.load();assert.equal(h.calls.length,1);
  assert.equal(h.controller.fields.values().next().value.value,fixture.initial.items[0].current.segments[0].text);
  h.text();await h.controller.save();assert.equal(h.saved.length,1,JSON.stringify(h.messages));const body=h.calls[1].body;
  assert.equal(body.asset_sha256,fixture.initial.items[0].asset_sha256);assert.equal(body.analysis_sha256,fixture.initial.items[0].analysis_sha256);
  assert.equal(body.edit.base_transcript_id,fixture.initial.items[0].current.transcript_id);assert.equal(body.edit.expected_version,1);assert.equal(body.edit.expected_timeline_version,null);
  assert.equal(h.node('segments').innerHTML,undefined);assert.equal(h.saved[0].publishing_enabled,false);
});
test('explicit restoration derives the next version from preserved original words without ASR dispatch',async()=>{
  const h=harness(fixture.changed);h.respond(async(path,body)=>copy(body?fixture.restored:fixture.changed));await h.controller.load();await h.controller.restore();
  assert.equal(h.saved.length,1,JSON.stringify(h.messages));assert.equal(h.calls.length,2);assert.equal(h.calls[1].body.edit.expected_version,2);
  assert.equal(h.calls[1].body.edit.base_transcript_id,fixture.initial.items[0].original.transcript_id);assert.equal(h.saved[0].items[0].current.version,3);
  assert.equal(h.calls.some(c=>c.path.includes('/jobs')),false);
});
test('viewer, dirty, active, archived and blank text cannot write through controller methods',async()=>{
  for(const flag of['canEdit','dirty','active','archived','blank']){const h=harness();if(flag==='canEdit')h.state.canEdit=false;else if(flag==='archived')h.state.project.archived=true;else if(['dirty','active'].includes(flag))h.state[flag]=true;
    await h.controller.load();if(flag==='blank')h.text(' ');await h.controller.save();await h.controller.restore();assert.equal(h.calls.length,1,flag);assert.equal(h.saved.length,0);}
});
test('foreign page, stale revision, changed original, invalid words and private fields cannot install recognition',()=>{
  const page=fixture.initial,s={workspace_id:page.workspace_id,project:{id:page.project_id,revision:page.revision}};
  const changes=[v=>v.workspace_id='foreign',v=>v.project_id='a'.repeat(32),v=>v.revision++,v=>v.provider_calls=1,v=>v.publishing_enabled=true,v=>v.source_media_mutated=true,
    v=>v.items[0].original.version=2,v=>v.items[0].versions[0].segments[0].words[0].end_seconds=4,v=>v.items[0].current.transcript_id='trn_other',
    v=>v.items[0].current.provenance.access_token='NEVER',v=>v.items[0].analysis_sha256='bad'];
  for(const change of changes){const v=copy(page);change(v);assert.throws(()=>validateAudioTranscripts(v,s));}
});
test('late former-project response is discarded before installing transcript or editable fields',async()=>{
  const h=harness();let resolve;h.respond(()=>new Promise(r=>{resolve=r;}));const work=h.controller.load();await Promise.resolve();
  h.state.project={id:'a'.repeat(32),revision:1};h.controller.sync();resolve(copy(fixture.initial));await work;
  assert.equal(h.controller.currentBinding().selected,null);assert.equal(h.controller.fields.size,0);assert.equal(h.saved.length,0);
});
test('changed write receipt, unexpected text or false word alignment cannot trigger project reload',async()=>{
  for(const change of[v=>v.items[0].asset_sha256='a'.repeat(64),v=>v.items[0].current.version=4,
    v=>{v.items[0].current.segments[0].text='Unasked text';v.items[0].versions[1].segments[0].text='Unasked text';}]){
    const h=harness();await h.controller.load();h.text();const bad=copy(fixture.changed);change(bad);h.respond(async()=>bad);await h.controller.save();
    assert.equal(h.calls.length,2);assert.equal(h.saved.length,0);assert.ok(h.messages.length);}
});
test('ASR availability follows speech audio while music and subtitle uploads remain outside analysis',()=>{
  const raw={id:'a',kind:'audio',canonical_role:'audio',sha256:'a'.repeat(64)};
  assert.equal(mediaAnalysisPending({assets:[raw]}),true);assert.equal(mediaAnalysisPending({assets:[{...raw,canonical_role:'music'}]}),false);
  assert.equal(mediaAnalysisPending({assets:[{...raw,kind:'subtitle',canonical_role:'subtitle'}]}),false);
  assert.equal(mediaAnalysisPending({assets:[raw],media_analysis:[{asset_id:'a',source_sha256:raw.sha256}]}),false);
});
