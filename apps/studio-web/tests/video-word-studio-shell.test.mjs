import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const code=readFileSync(new URL('../studio.js',import.meta.url),'utf8');
const fixture=JSON.parse(readFileSync(new URL('./fixtures/sql-video-word-review/asgi.json',import.meta.url),'utf8'));
const historyBytes=readFileSync(new URL('./fixtures/sql-video-word-shell/history.json',import.meta.url));
const history=JSON.parse(historyBytes);
const clone=structuredClone;
function segment(begin,end){const a=code.indexOf(begin),b=code.indexOf(end,a);assert.ok(a>=0&&b>a);return code.slice(a,b);}
function state(){return {workspaceId:fixture.context.workspace_id,projectId:fixture.context.project_id,
  principal:{subject:fixture.context.actor_ref,token_id:'word-shell-fixture'},projectLoading:0,
  assets:[clone(fixture.asset)],analyses:[clone(fixture.responses.base.body)],timeline:clone(fixture.responses.timeline_before.body),
  versions:[],videoReviewSelection:{fixture:true},selectedSceneAssessmentId:'old-assessment',selectedClipId:'old-clip',
  undoStack:[1],redoStack:[1],preview:{status:'ready'},productionPackage:{current_for_timeline:true,
    approval:{status:'approved'},latest_review_render:{render_id:'historical-review'},latest_final_render:{render_id:'historical-final'}},
  activeProductionRender:{render_id:'historical-final'},busy:false,dirty:false};}
function receipt(){const a=clone(fixture.responses.edited.body);return {workspace_id:a.workspace_id,project_id:a.project_id,
  analysis_id:a.analysis_id,asset_id:a.asset_id,source_sha256:fixture.asset.checksum_sha256,
  base_transcript_id:fixture.responses.base.body.transcript.transcript_id,result_transcript_id:a.transcript.transcript_id,
  expected_timeline_version:fixture.responses.timeline_before.body.current_version,receipt:a};}
function refresh(s,handler){const effects=[],calls=[];let token='TRANSIENT_WORD_SHELL_FIXTURE',audio='audio-saved',production='production-saved';
  const policy=()=>({...s,analysis:s.analyses[0]});
  const h=new Function('state','videoWordEditorState','sessionToken','productionWorkbenchDraft','audioWorkbenchDraft','api',
    'stopPreviewPolling','stopProductionPolling','render',
    segment('function videoWordEditorBoundary(){','\nfunction narrationEditorBoundary(){')+'\nreturn {refreshVideoWordReceipt};')(
      s,policy,()=>token,()=>production,()=>audio,async path=>{calls.push(path);return handler?handler(path):
        path.endsWith('/versions')?clone(history.versions):clone(fixture.responses.timeline_after.body);},
      ()=>effects.push('stop-preview'),()=>effects.push('stop-production'),()=>effects.push('render'));
  return {...h,calls,effects,setToken:value=>{token=value;},setAudio:value=>{audio=value;},setProduction:value=>{production=value;}};
}
test('actual Studio admits only its current word receipt and invalidates preview/approval without another write',async()=>{
  assert.equal(createHash('sha256').update(historyBytes).digest('hex'),'923dd47a9dc8443caedb4469e8160f9d33e1b078e27f21fe54bac303e40039a6');
  assert.deepEqual(history.timeline,fixture.responses.timeline_after.body);
  const s=state(),source=JSON.stringify(s.assets),original=JSON.stringify(fixture.responses.base.body.transcript);
  const h=refresh(s);await h.refreshVideoWordReceipt(receipt());
  assert.equal(s.timeline.current_version,2);assert.equal(s.analyses[0].transcript.transcript_id,receipt().result_transcript_id);
  assert.equal(JSON.stringify(s.assets),source);assert.equal(JSON.stringify(fixture.responses.base.body.transcript),original);
  assert.equal(s.preview.status,'stale');assert.equal(s.productionPackage.current_for_timeline,false);
  assert.equal(s.productionPackage.approval,null);assert.equal(s.productionPackage.latest_review_render,null);
  assert.equal(s.productionPackage.latest_final_render,null);assert.equal(s.activeProductionRender,null);
  assert.equal(s.videoReviewSelection,null);assert.equal(s.selectedSceneAssessmentId,'');assert.equal(s.selectedClipId,null);
  assert.deepEqual(s.undoStack,[]);assert.deepEqual(s.redoStack,[]);
  assert.equal(h.calls.length,2);assert.deepEqual(h.effects,['stop-preview','stop-production','render']);
});
for(const change of ['newer','foreign-project','foreign-timeline','duplicate-version','duplicate-id','wrong-head-id','wrong-head-snapshot','missing-head','empty'])
  test(`actual word callback retains current state when final history is ${change}`,async()=>{
    const s=state(),before=JSON.stringify(s),versions=clone(history.versions);
    if(change==='newer')versions.unshift({...clone(versions[0]),version:3,timeline_version_id:'tlv_newer_concurrent_fixture'});
    if(change==='foreign-project')versions[0].project_id='prj_foreign_fixture';
    if(change==='foreign-timeline')versions[0].timeline_id='tml_foreign_fixture';
    if(change==='duplicate-version')versions.push({...clone(versions[1]),timeline_version_id:'tlv_duplicate_ordinal_fixture'});
    if(change==='duplicate-id')versions[1].timeline_version_id=versions[0].timeline_version_id;
    if(change==='wrong-head-id')versions[0].timeline_version_id='tlv_different_head_fixture';
    if(change==='wrong-head-snapshot')versions[0].snapshot.metadata.foreign_editorial_change=true;
    if(change==='missing-head')versions.shift();if(change==='empty')versions.length=0;
    const h=refresh(s,path=>path.endsWith('/versions')?versions:clone(fixture.responses.timeline_after.body));
    await assert.rejects(h.refreshVideoWordReceipt(receipt()),/Lịch sử timeline không khớp/);
    assert.equal(JSON.stringify(s),before);assert.deepEqual(h.effects,[]);assert.equal(h.calls.length,2);
  });
test('actual word callback compares snapshot values regardless of metadata object key order',async()=>{
  const s=state(),versions=clone(history.versions);
  versions[0].snapshot.metadata=Object.fromEntries(Object.entries(versions[0].snapshot.metadata).reverse());
  const h=refresh(s,path=>path.endsWith('/versions')?versions:clone(fixture.responses.timeline_after.body));
  await h.refreshVideoWordReceipt(receipt());assert.equal(s.timeline.current_version,2);assert.equal(h.effects.length,3);
});
for(const during of ['timeline','versions'])for(const drift of ['project','session','token','source','canonical','audio-draft','subtitle-draft','other-dirty'])
  test(`actual word callback preserves current state after ${drift} changes during ${during} read`,async()=>{
    const s=state();let release;
    const h=refresh(s,path=>path.endsWith('/versions')?(during==='versions'?new Promise(r=>{release=r;}):[]):
      during==='timeline'?new Promise(r=>{release=r;}):clone(fixture.responses.timeline_after.body));
    const work=h.refreshVideoWordReceipt(receipt());await new Promise(r=>setImmediate(r));
    if(drift==='project')s.projectId='prj_foreign_fixture';
    if(drift==='session')s.principal.token_id='refreshed-session';
    if(drift==='token')h.setToken('TRANSIENT_CHANGED_FIXTURE');
    if(drift==='source')s.assets[0].checksum_sha256='a'.repeat(64);
    if(drift==='canonical')s.timeline.current_version++;
    if(drift==='audio-draft')h.setAudio('unsaved-workbench');
    if(drift==='subtitle-draft')h.setProduction('unsaved-subtitle');
    if(drift==='other-dirty')s.dirty=true;
    const current=JSON.stringify(s);release(during==='timeline'?clone(fixture.responses.timeline_after.body):[]);
    await assert.rejects(work,/đã đổi/);assert.equal(JSON.stringify(s),current);assert.deepEqual(h.effects,[]);
  });
for(const mismatch of ['version','project','workspace','analysis','transcript','missing'])
  test(`actual word callback refuses ${mismatch} timeline instead of rebasing retained CAS`,async()=>{
    const s=state(),before=JSON.stringify(s),t=clone(fixture.responses.timeline_after.body);
    if(mismatch==='version')t.current_version++;
    if(mismatch==='project')t.project_id='prj_foreign';
    if(mismatch==='workspace')t.workspace_id='wsp_foreign';
    if(mismatch==='analysis')t.source_analysis_id='ana_foreign';
    if(mismatch==='transcript')t.snapshot.metadata.transcript_revision.transcript_id='trn_foreign';
    const h=refresh(s,()=>mismatch==='missing'?null:t);
    await assert.rejects(h.refreshVideoWordReceipt(receipt()),/Timeline chưa/);
    assert.equal(JSON.stringify(s),before);assert.deepEqual(h.effects,[]);assert.equal(h.calls.length,1);
  });
test('actual word callback keeps absent canonical timeline and does not create one for a source-only revision',async()=>{
  const s=state();s.timeline=null;s.preview=null;s.productionPackage=null;
  const value=receipt();value.expected_timeline_version=null;
  const h=refresh(s,async()=>{throw Object.assign(Error('source-only fixture 404'),{status:404});});
  await h.refreshVideoWordReceipt(value);assert.equal(s.timeline,null);assert.equal(h.calls.length,1);
  assert.equal(s.analyses[0].transcript.transcript_id,value.result_transcript_id);
});
test('actual word callback rejects a foreign receipt before a single read',async()=>{
  const s=state(),value=receipt(),before=JSON.stringify(s);value.source_sha256='a'.repeat(64);
  const h=refresh(s);await assert.rejects(h.refreshVideoWordReceipt(value),/khớp nguồn/);
  assert.equal(JSON.stringify(s),before);assert.deepEqual(h.calls,[]);assert.deepEqual(h.effects,[]);
});
test('actual Studio closes all other writes while word draft, work or UNKNOWN exists but permits scoped word writes and GET',async()=>{
  let held=false;const calls=[],permit=Symbol('only-word-controller');
  const api=new Function('authenticatedFetch','videoWordsHeld','videoWordAdmission','audioProcessingHeld','audioProcessingAdmission','sourceLinkedHeld','sourceLinkedAdmission',
    segment('class ApiError extends Error {','\nfunction toast(')+'\nreturn api;')(
      async(path,options)=>{calls.push({path,options});return {ok:true,status:204};},()=>held,permit,()=>false,Symbol('unused-audio-controller'),()=>false,Symbol('unused-source-controller'));
  for(const reason of ['draft','working','unknown']){
    held=true;const before=calls.length;
    for(const method of ['POST','PUT','PATCH','DELETE'])await assert.rejects(api('/api/v1/projects/current/timeline',{method,body:'{}'}),/sửa từ/);
    await assert.rejects(api('/api/v1/projects/current/analyses/current/transcript-words',{method:'POST',videoWordAdmission:Symbol('foreign')}),/sửa từ/);
    assert.equal(calls.length,before,reason);
    await api('/api/v1/projects/current/timeline');
    await api('/api/v1/projects/current/analyses/current/transcript-words',{method:'POST',body:'{}',videoWordAdmission:permit});
    assert.equal(calls.length,before+2);assert.ok(!Object.hasOwn(calls.at(-1).options,'videoWordAdmission'));
  }
  held=false;await api('/api/v1/projects/current/timeline',{method:'PUT',body:'{}'});assert.equal(calls.at(-1).options.method,'PUT');
});
test('actual word state excludes its own busy/pending and includes peer drafts, analysis selection and private transient getter',()=>{
  const base={busy:false,dirty:false},analysis={analysis_id:'chosen-analysis'};
  let familyBusy=false,familyPending=false,narrationBusy=false,narrationPending=false;
  const own=new Function('sqlEditorState','reviewedAnalysis','variantFamilies','variantNarration','sqlAudioProcessing','sourceLinkedEditor','sourceLinkedHeld',
    segment('function videoWordEditorState(){','\nfunction syncVideoWordPeers()')+'\nreturn videoWordEditorState;')(
      ()=>base,()=>analysis,{isBusy:()=>familyBusy,isPending:()=>familyPending},
      {isWorking:()=>narrationBusy,isPending:()=>narrationPending},null,null,()=>false);
  assert.deepEqual(own(),{busy:false,dirty:false,analysis});familyBusy=true;assert.equal(own().busy,true);
  familyBusy=false;narrationBusy=true;assert.equal(own().busy,true);narrationBusy=false;
  familyPending=true;assert.equal(own().dirty,true);familyPending=false;narrationPending=true;assert.equal(own().dirty,true);
  assert.match(code,/getState:videoWordEditorState,getSessionToken:sessionToken/);
  assert.match(code,/videoWordReview\?\.dispose\(\)/);
});
