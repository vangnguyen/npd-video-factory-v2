import test from 'node:test';
import assert from 'node:assert/strict';
import {initializeSceneAssessments, validateSceneAssessments, sceneAssessmentPayload, reviewedHighlightPayload,
  reviewedShortsPayload, validateSceneAssessmentSave, validateReviewedShorts, highlightReasonSummary} from '../native-scene-assessments.mjs';

const copy = value => structuredClone(value);
const pid = '1'.repeat(32), ana = 'ana_'+'2'.repeat(24), tid = 'trn_'+'3'.repeat(24);
const assessment = 'nsci_'+'4'.repeat(32), asset = '5'.repeat(32)+'.mp4', highlight = 'hig_'+'6'.repeat(24);
function fixture() {
  const refs = {analysis_id:ana, asset_id:asset, asset_sha256:'a'.repeat(64), analysis_sha256:'b'.repeat(64),
    transcript_id:tid, transcript_version:1, transcript_sha256:'c'.repeat(64)};
  const factors = {speech_coverage:.7, motion:null, information_density:.6, hook_keywords:0,
    quality:null, pixel_novelty:null, audio_energy:null};
  const ranked = Array.from({length:5}, (_, index) => ({highlight_id:'hig_'+String(index+6).padStart(24,'0'),
    scene_ordinal:index, rank:index+1, highlight_score:.4, reason:'Saved transcript heuristic; motion unavailable',
    recommended_start:index*2, recommended_end:index*2+2, recommended_platform:'facebook_reels',
    evidence:{factors:copy(factors), contributions:{speech_coverage:.3, information_density:.1, hook_keywords:0},
      missing_factors:['motion','quality','pixel_novelty','audio_energy'], confidence:null}}));
  ranked[0].highlight_id = highlight;
  return {schema_version:'native-current-scene-page.v1', workspace_id:'wsp_scene_fixture', project_id:pid,
    revision:5, timeline_version:null, available_sources:[{...refs, filename:'Explicit saved-evidence fixture'}],
    items:[{assessment:{schema_version:'native-current-scene-assessment.v1', assessment_id:assessment,
      version:1, project_id:pid, workspace_id:'wsp_scene_fixture',
      source_revision:4, source_document_sha256:'9'.repeat(64), input_refs:refs, input_sha256:'d'.repeat(64), algorithm:'current-scene-assessment-v1',
      result:{scenes:[{scene_id:'scn_abcdef', ordinal:0, start_seconds:0, end_seconds:2,
        semantic_label:'Saved transcript label', description:'Saved speech', confidence:null, needs_attention:true, evidence:{}}],
        scene_ranking:ranked, highlights:copy(ranked), semantic_vision_used:false, semantic_vision_state:'NOT_CONFIGURED',
        prediction_confidence_calibrated:false,continuous_tracking_performed:false,decoded_source_pts_verified:false,
        recommendation_only:true,canonical_timeline_mutated:false,silence_decisions_mutated:false,
        publishing_authorized:false,owner_uat_accepted:false,provider_dispatches:0}, recommendation_only:true, semantic_vision_state:'NOT_CONFIGURED',
      actor_ref:'explicit-fixture-editor', created_at:'2026-10-13T00:00:00Z'}, sha256:'e'.repeat(64), current:true}],
    provider_calls:0, source_media_mutated:false, canonical_timeline_mutated:false, publishing_enabled:false};
}
const stateFor = value => ({workspace_id:value.workspace_id, project:{id:value.project_id, revision:value.revision}, canEdit:true,
  active:false, archived:false, dirty:false, busy:false});
function lineage(page) {
  const original = page.items[0];
  return {schema_version:'native-current-scene-selection.v1', assessment_id:original.assessment.assessment_id,
    assessment_sha256:original.sha256, source_project_id:page.project_id,
    input_refs:copy(original.assessment.input_refs), input_sha256:original.assessment.input_sha256,
    recommendation_only:true, automatic_application:false, semantic_vision_state:'NOT_CONFIGURED',
    prediction_confidence_calibrated:false, owner_uat_accepted:false};
}
function shortsReceipt(page, request) {
  const child = '7'.repeat(32), checksum = 'f'.repeat(64);
  return {batch:{source_project_id:page.project_id, source_revision:page.revision,
    request_key:request.payload.request_key, analysis_id:ana, transcript_id:tid, aspect_ratio:request.payload.aspect_ratio,
    requested_count:request.payload.count, maximum_duration_seconds:60, provider_calls:0, paid_operations:0,
    parent_document_mutated:false, human_approval_required:true, generated_count:1,
    scene_evidence:{reviewed_local_scene_selection:lineage(page)},
    drafts:[{project_id:child, timeline_sha256:checksum, source_window:[0,2]}]},
    projects:[{id:child, revision:1, approval:null, document:{canonical_timeline:{sha256:checksum,
      snapshot:{metadata:{highlight_draft:{reviewed_local_scene_selection:lineage(page)}}}}}}]};
}
function harness() {
  class Node {
    constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.listeners = {}; this.value = ''; this.checked = false; }
    append(...children) { this.children.push(...children); }
    prepend(...children) { this.children.unshift(...children); }
    replaceChildren(...children) { this.children = children; }
    addEventListener(name, listener) { this.listeners[name] = listener; }
  }
  const card = new Node('details'); card.id = 'native-scene-assessments-card';
  const find = (node, name) => node.id === name ? node : node.children.map(child => find(child, name)).find(Boolean);
  const root = {getElementById:name => find(card, name), createElement:tag => new Node(tag)};
  const state = stateFor(fixture()), calls = [], messages = [], saved = [], drafts = [];
  let respond = async (path, body) => {
    if (path.endsWith('/shorts')) return shortsReceipt(fixture(), body);
    if (path.endsWith('/timeline')) return {id:pid, revision:6, approval:null,
      document:{canonical_timeline:{version:1, snapshot:{aspect_ratio:body.payload.aspect_ratio,
        metadata:{reviewed_local_scene_selection:lineage(fixture()),reviewed_highlight_id:body.payload.reviewed_highlight_id}}}}};
    const page = fixture(); if (body) page.revision++; return page;
  };
  const controller = initializeSceneAssessments({root, getState:() => state,
    api:async (path, body) => { calls.push({path, body}); return respond(path, body); },
    onMessage:(...value) => messages.push(value), onWorking:value => { state.busy = value; },
    onSaved:async value => { saved.push(value); state.project.revision = value.revision; },
    onDraftsCreated:async value => drafts.push(value)});
  const node = name => root.getElementById('native-scene-assessments-'+name);
  return {state, card, controller, calls, messages, saved, drafts, node, respond:value => { respond = value; }};
}

test('initialization is inert; explicit read displays saved confidence and missing factors without dispatch', async () => {
  const h = harness(); assert.equal(h.calls.length,0);
  await h.controller.load(); assert.equal(h.calls.length,1);
  assert.equal(h.calls[0].body,undefined); assert.equal(h.node('highlights').children.length,3);
  const strings = node => [node.textContent ?? '', ...node.children.flatMap(strings)];
  assert.match(strings(h.node('highlights')).join(' '),/Chuyển động: Chưa có dữ liệu/);
  assert.match(strings(h.node('highlights')).join(' '),/Độ tin cậy nguồn: Chưa có dữ liệu/);
  assert.equal(h.node('apply').disabled,true); assert.equal(h.node('shorts').disabled,true);
  h.node('top').value = '5'; h.node('top').listeners.change(); assert.equal(h.node('highlights').children.length,5);
});

test('actual reason summary is Vietnamese while raw explanation stays in collapsed evidence details', async () => {
  const raw='saved text keyword/information-density heuristics; transcript coverage; measured pixel-change proxy; '
    +'measured audio energy; measured exposure heuristic; hook keywords: mới, bí mật';
  const h=harness(); h.respond(async()=>{const page=fixture(); page.items[0].assessment.result.scene_ranking[0].reason=raw; return page;});
  await h.controller.load(); const section=h.node('highlights').children[0];
  assert.match(section.children[1].textContent,/Từ khóa và mật độ thông tin/);
  assert.match(section.children[1].textContent,/khung hình mẫu/);
  assert.match(section.children[1].textContent,/Cường độ âm thanh đã đo/);
  assert.match(section.children[1].textContent,/Từ khóa nổi bật: mới, bí mật/);
  assert.doesNotMatch(section.children[1].textContent,/saved text|measured pixel|Vision/);
  const details=section.children.find(value=>value.tagName==='DETAILS');
  assert.equal(details.open,undefined); assert.equal(details.children[1].textContent,raw);
  assert.equal(h.calls.length,1); assert.equal(h.controller.currentBinding().assessment.assessment.result.scene_ranking[0].evidence.factors.motion,null);
  assert.equal(highlightReasonSummary('new-unconfigured-signal'), 'Yếu tố khác trong bằng chứng đã lưu; xem chi tiết');
});

test('freezing binds exact current transcript and source hashes, acknowledgement and CAS, then requires separate apply review', async () => {
  const h = harness(); await h.controller.load(); await h.controller.freeze(); assert.equal(h.calls.length,1);
  assert.match(h.messages.at(-1)[0],/Xác nhận/);
  h.node('freeze-ack').checked = true; await h.controller.freeze(); assert.equal(h.saved.length,1);
  const body = h.calls[1].body;
  assert.deepEqual(body, {revision:5, analysis_id:ana, asset_sha256:'a'.repeat(64), analysis_sha256:'b'.repeat(64),
    expected_transcript_id:tid, expected_transcript_version:1, expected_transcript_sha256:'c'.repeat(64),
    expected_timeline_version:null, acknowledged_saved_evidence:true});
  assert.equal(h.state.project.revision,6); assert.equal(h.controller.currentBinding().page.revision,6);
  assert.equal(h.node('reviewed').checked,false); assert.equal(h.node('apply').disabled,true);
});

test('cached freeze permits unchanged revision; wrong transcript or timeline receipt is not installed', () => {
  const page = fixture(), state = stateFor(page), source = page.available_sources[0];
  assert.equal(validateSceneAssessmentSave(copy(page),state,page,source).revision,5);
  const changed = copy(page); changed.revision = 6; changed.timeline_version = 1;
  assert.throws(() => validateSceneAssessmentSave(changed,state,page,source));
  const transcript = copy(page); transcript.revision = 6; transcript.items[0].assessment.input_refs.transcript_sha256 = 'f'.repeat(64);
  assert.throws(() => validateSceneAssessmentSave(transcript,state,page,source));
});

test('apply uses only original reviewed highlight identifier with no client window override or publishing authority', async () => {
  const h = harness(); await h.controller.load(); await h.controller.apply(); assert.equal(h.calls.length,1);
  h.node('reviewed').checked = true; await h.controller.apply(); assert.equal(h.saved.length,1);
  assert.equal(h.calls[1].path,`/api/projects/${pid}/auto-edit/timeline`);
  assert.deepEqual(h.calls[1].body,{revision:5, action:'create', payload:{analysis_id:ana, transcript_id:tid, aspect_ratio:'9:16',
    reviewed_local_scene:{assessment_id:assessment,expected_assessment_sha256:'e'.repeat(64),acknowledged:true}, reviewed_highlight_id:highlight}});
  assert.equal(h.calls[1].body.payload.source_window,undefined); assert.equal(h.calls[1].body.payload.publishing_enabled,undefined);
});

test('timeline receipt from foreign project or stale revision cannot reach project callback', async () => {
  const h = harness(); await h.controller.load(); h.node('reviewed').checked = true;
  h.respond(async () => ({id:'f'.repeat(32),revision:6,document:{canonical_timeline:{version:1,snapshot:{aspect_ratio:'9:16'}}}}));
  await h.controller.apply(); assert.equal(h.saved.length,0); assert.match(h.messages.at(-1)[0],/Biên nhận timeline/);
});

test('same-project timeline must preserve exact assessment and selected highlight lineage', async () => {
  for (const mutate of [value=>{value.input_sha256='f'.repeat(64);}, value=>{value.input_refs.transcript_sha256='f'.repeat(64);},
    value=>{value.owner_uat_accepted=true;}]) {
    const h=harness(); await h.controller.load(); h.node('reviewed').checked=true;
    h.respond(async(path,body)=>{const proof=lineage(fixture()); mutate(proof);
      return {id:pid,revision:6,approval:null,document:{canonical_timeline:{version:1,snapshot:{aspect_ratio:'9:16',
        metadata:{reviewed_local_scene_selection:proof,reviewed_highlight_id:body.payload.reviewed_highlight_id}}}}};});
    await h.controller.apply(); assert.equal(h.saved.length,0); assert.match(h.messages.at(-1)[0],/đúng nguồn/);
  }
  const h=harness(); await h.controller.load(); h.node('reviewed').checked=true;
  h.respond(async()=>({id:pid,revision:6,approval:null,document:{canonical_timeline:{version:1,snapshot:{aspect_ratio:'9:16',
    metadata:{reviewed_local_scene_selection:lineage(fixture()),reviewed_highlight_id:'hig_'+'a'.repeat(24)}}}}}));
  await h.controller.apply(); assert.equal(h.saved.length,0);
});

test('stale assessments remain visible only as history and fail explicit apply', async () => {
  const h = harness(); h.respond(async () => { const page=fixture(); page.items[0].current=false;
    page.available_sources[0].transcript_version=2; return page; });
  await h.controller.load(); assert.match(h.node('status').textContent,/cũ/); assert.equal(h.node('reviewed').disabled,true);
  h.node('reviewed').checked=true; await h.controller.apply(); assert.equal(h.calls.length,1);
  assert.match(h.messages.at(-1)[0],/hiệu lực/);
});

test('history remains reviewable when its original source is no longer available', async () => {
  const h=harness(); h.respond(async()=>{const page=fixture(); page.available_sources=[]; page.items[0].current=false; return page;});
  await h.controller.load(); assert.equal(h.controller.currentBinding().source,null);
  assert.equal(h.node('scenes').children.length,1); assert.match(h.node('status').textContent,/cũ/);
  assert.equal(h.node('freeze').disabled,true); assert.equal(h.node('apply').disabled,true);
});

test('viewer dirty active archived scopes cannot freeze apply or create drafts', async () => {
  for (const mutation of [state=>{state.canEdit=false;}, state=>{state.dirty=true;}, state=>{state.active=true;},
    state=>{state.archived=true;}, state=>{state.project.archived=true;}]) {
    const h=harness(); await h.controller.load(); mutation(h.state);
    h.node('freeze-ack').checked=true; h.node('reviewed').checked=true;
    await h.controller.freeze(); await h.controller.apply(); await h.controller.createShorts();
    assert.equal(h.calls.length,1);
  }
});

test('late workspace project revision permission and dirty changes discard read results', async () => {
  for (const mutation of [state=>{state.workspace_id='wsp_other';}, state=>{state.project={id:'f'.repeat(32),revision:1};},
    state=>{state.project.revision++;},state=>{state.canEdit=false;},state=>{state.dirty=true;}]) {
    const h=harness(); let complete; h.respond(()=>new Promise(resolve=>{complete=resolve;}));
    const pending=h.controller.load(); mutation(h.state); complete(fixture()); await pending;
    assert.equal(h.controller.currentBinding().page,null);
  }
});

test('forged current references, nonfinite scores, fabricated missing factor and foreign workspace receipts reject', () => {
  const page=fixture(), state=stateFor(page);
  assert.equal(validateSceneAssessments(page,state),page);
  for (const mutate of [value=>{value.items[0].assessment.input_refs.analysis_sha256='f'.repeat(64);},
    value=>{value.items[0].assessment.result.scene_ranking[0].highlight_score=NaN;},
    value=>{value.items[0].assessment.result.scene_ranking[0].evidence.factors.motion=0;},
    value=>{value.workspace_id='wsp_other';},value=>{value.items[0].assessment.recommendation_only=false;},
    value=>{value.provider_calls=1;}]) {
    const bad=copy(page); mutate(bad); assert.throws(()=>validateSceneAssessments(bad,state));
  }
});

test('source and selected highlight switches revoke review; Top 5 and supported aspect bind to Shorts request', async () => {
  const h=harness(); await h.controller.load(); h.node('reviewed').checked=true;
  h.node('ratio').value='4:5'; h.node('ratio').listeners.change(); assert.equal(h.node('reviewed').checked,false);
  h.node('top').value='5'; h.node('top').listeners.change(); h.node('reviewed').checked=true;
  await h.controller.createShorts(); assert.equal(h.drafts.length,1); assert.equal(h.saved.length,0);
  assert.equal(h.calls[1].body.payload.count,5); assert.equal(h.calls[1].body.payload.aspect_ratio,'4:5');
  assert.equal(h.calls[1].body.payload.maximum_duration_seconds,60); assert.equal(h.calls[1].body.payload.reviewed_highlight_id,undefined);
  assert.equal(h.node('reviewed').checked,false); assert.equal(h.state.project.revision,5);
});

test('lost Shorts response retries with the same idempotency key without granting approval', async () => {
  const h=harness(); await h.controller.load(); h.node('reviewed').checked=true;
  let attempt=0; h.respond(async(path,body)=>{ if (++attempt===1) throw Error('connection interrupted'); return shortsReceipt(fixture(),body); });
  await h.controller.createShorts(); await h.controller.createShorts();
  assert.equal(h.calls[1].body.payload.request_key,h.calls[2].body.payload.request_key); assert.equal(h.drafts.length,1);
  const forged=shortsReceipt(fixture(),h.calls[2].body); forged.projects[0].approval={accepted:true};
  assert.throws(()=>validateReviewedShorts(forged,fixture(),h.calls[2].body));
});

test('Shorts batch and each child must retain original-parent recommendation lineage', () => {
  const page=fixture(), request=reviewedShortsPayload(page,page.items[0],{acknowledged:true,requestKey:'a'.repeat(32)});
  const receipt=shortsReceipt(page,request); assert.equal(validateReviewedShorts(receipt,page,request),receipt);
  const batch=copy(receipt); batch.batch.scene_evidence.reviewed_local_scene_selection.assessment_sha256='f'.repeat(64);
  assert.throws(()=>validateReviewedShorts(batch,page,request));
  const child=copy(receipt); child.projects[0].document.canonical_timeline.snapshot.metadata.highlight_draft
    .reviewed_local_scene_selection.source_project_id=child.projects[0].id;
  assert.throws(()=>validateReviewedShorts(child,page,request));
});

test('payload helpers refuse unsupported format foreign selection and missing explicit review', () => {
  const page=fixture(), item=page.items[0];
  assert.throws(()=>sceneAssessmentPayload(page,{...page.available_sources[0],asset_sha256:'f'.repeat(64)},true));
  assert.throws(()=>reviewedHighlightPayload(page,item,{acknowledged:true,selectedHighlightId:'hig_'+'f'.repeat(24)}));
  assert.throws(()=>reviewedHighlightPayload(page,item,{acknowledged:true,aspectRatio:'3:2'}));
  assert.throws(()=>reviewedHighlightPayload(page,item,{acknowledged:false}));
  assert.throws(()=>reviewedShortsPayload(page,item,{acknowledged:true,count:4,requestKey:'a'.repeat(32)}));
});
