import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash,webcrypto} from 'node:crypto';
import {verifyVariantReceipt} from '../verified-variant-source.mjs';
import {videoAnalysisAssets,videoAnalysisPayload,validateVideoAnalysisJob,videoReviewSelection,selectedVideoReviewAnalysis,initializeVideoAnalysisJobs} from '../video-analysis-jobs.mjs';
import {transcriptEditPayload} from '../transcript-editor.mjs';

// Explicit contract fixtures. These checks do not infer ASR accuracy, model
// acceptance, a human review or real browser acceptance.
const clone=structuredClone,hash='a'.repeat(64),jobId='job_analysis_'+'b'.repeat(24),analysisId='ana_'+'c'.repeat(24),assetId='ast_owned_video';
function state(){return{workspaceId:'wsp_fixture',projectId:'prj_fixture',principal:{subject:'fixture-editor',token_id:'fixture-session',
  expires_at:'2100-01-01T00:00:00Z',platform_role:'editor'},busy:false,dirty:false,assets:[{asset_id:assetId,workspace_id:'wsp_fixture',
  project_id:'prj_fixture',asset_class:'source',kind:'video',content_type:'video/mp4',size_bytes:1024,checksum_sha256:hash,
  filename:'<img src=x onerror=alert(1)>',provenance:{source_type:'user_upload',media_metadata:{media_kind:'video',duration_seconds:3}}}]};}
function value(status='queued',s=state(),body=videoAnalysisPayload(s,assetId,3,'fixture-stable-intent')){
  return{schema_version:'auto-edit-analysis-job.v1',human_review_required:true,source_media_mutated:false,timeline_mutated:false,publishing_enabled:false,
    source_sha256:body.source_sha256,custody_sha256:'d'.repeat(64),job:{job_id:jobId,workspace_id:s.workspaceId,project_id:s.projectId,status,
      progress:status==='awaiting_review'?100:10,request:{kind:'auto_edit_analysis',analysis_id:analysisId,source_sha256:hash,provider_binding_sha256:'e'.repeat(64)}},
    analysis:{analysis_id:analysisId,workspace_id:s.workspaceId,project_id:s.projectId,asset_id:assetId,
      status:status==='awaiting_review'?'succeeded':status==='running'?'analyzing':status==='queued'?'pending':'failed',configuration:clone(body.configuration),
      provenance:{fixture:true},transcript:null,scenes:[],silence_decisions:[],highlights:[]}};}
function harness({s=state(),memory=new Map(),storage,handler}={}){
  class Element{constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.listeners={};this.value='';this.disabled=false;this.textContent='';}
    append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}setAttribute(k,v){this.attributes[k]=String(v);}
    addEventListener(k,v){this.listeners[k]=v;}}
  const dom={createElement:t=>new Element(t)},root=dom.createElement('div'),all=n=>[n,...n.children.flatMap(all)];
  const calls=[],messages=[],reviewed=[],timers=new Map();let clock=0;
  const api=async(path,options)=>{const c={path,method:options?.method??'GET',body:options?.body?JSON.parse(options.body):null};calls.push(c);
    if(handler)return handler(c,s);return c.method==='POST'?value(path.endsWith('/cancel')?'cancelled':'queued',s,c.body?.configuration?c.body:undefined):
      path.endsWith('/analysis-jobs')?[value('queued',s)]:value('awaiting_review',s);};
  const controller=initializeVideoAnalysisJobs({root,dom,api,getState:()=>s,onMessage:(...v)=>messages.push(v),onReview:async v=>reviewed.push(v),
    storage:storage??{getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)},
    newKey:()=>`fixture-intent-${++clock}`,setTimer:f=>{const id=++clock;timers.set(id,f);return id;},clearTimer:id=>timers.delete(id)});
  const get=name=>all(root).find(e=>Object.hasOwn(e.attributes,'data-video-job-'+name));
  return{s,root,calls,messages,reviewed,timers,memory,controller,get,click:name=>get(name).listeners.click(),
    tick:async()=>{const pair=timers.entries().next().value;assert.ok(pair);timers.delete(pair[0]);await pair[1]();}};
}
const captured=Object.fromEntries(['queued','running','awaiting_review','cancelled','needs_attention'].map(name=>[name,
  JSON.parse(readFileSync(new URL(`./fixtures/sql-video-jobs/${name}.json`,import.meta.url),'utf8'))]));
const imported=JSON.parse(readFileSync(new URL('./fixtures/sql-variant-import-review/read.json',import.meta.url),'utf8'));
const importedJobs=JSON.parse(readFileSync(new URL('./fixtures/sql-variant-import-review/video-jobs.json',import.meta.url),'utf8'));
function importedState(role='editor'){return{workspaceId:imported.context.workspace_id,projectId:imported.context.project_id,
  principal:{subject:imported.context.viewer_subject,token_id:'explicit-import-video-session',expires_at:'2100-01-01T00:00:00Z',platform_role:role},
  busy:false,dirty:false,assets:clone(imported.responses.assets.body),timeline:clone(imported.responses.timeline.body),analyses:clone(imported.responses.analyses.body)};}
test('actual derivative video picker uses verified receipt with current child source, never old upload or job alias',async()=>{
  const s=importedState(),asset=videoAnalysisAssets(s)[0];assert.ok(asset);assert.notEqual(asset.asset_id,asset.provenance.parent_asset_id);
  assert.throws(()=>videoAnalysisPayload(s,asset.asset_id,3,'explicit-new-video-only'),/biên nhận/);
  s.verifiedVariantReceipts=[await verifyVariantReceipt(imported.responses.receipt.body,s,asset,webcrypto)];
  const p=videoAnalysisPayload(s,asset.asset_id,5,'explicit-new-video-only');
  assert.equal(p.configuration.asset_id,asset.asset_id);assert.equal(p.source_sha256,asset.checksum_sha256);
  assert.equal(importedJobs.status,200);assert.deepEqual(importedJobs.body,[]);assert.equal(importedJobs.provider_calls,0);
  const before=JSON.stringify(s.timeline);assert.equal(selectedVideoReviewAnalysis(s,null,s.analyses[0]),s.analyses[0]);
  assert.equal(JSON.stringify(s.timeline),before);
});
test('derived video read loads receipt and shows imported scenes without new ASR POST or master job alias',async()=>{
  const s=importedState(),before=JSON.stringify(s),h=harness({s,handler:c=>
    c.path===imported.responses.receipt.path?clone(imported.responses.receipt.body):clone(importedJobs.body)});
  assert.equal(h.calls.length,0);h.controller.sync();assert.equal(h.calls.length,0);await h.click('read');
  assert.deepEqual(h.calls.map(c=>c.method),['GET','GET']);assert.match(h.get('status').textContent,/Cảnh và lời đã nhập/);
  assert.equal(h.get('saved').children.length,0);assert.equal(h.timers.size,0);assert.equal(h.get('review').disabled,true);
  assert.equal(JSON.stringify(s),before);assert.equal(h.get('start').textContent,'Gửi phân tích mới cho bản sao đã chọn');
});
test('only explicit derived video start sends one fresh child intent; blocked provider keeps key, no new result',async()=>{
  const s=importedState(),before=JSON.stringify(s.timeline),h=harness({s,handler:c=>{
    if(c.path===imported.responses.receipt.path)return clone(imported.responses.receipt.body);
    if(c.method==='POST')throw Error('EXPLICIT UI FIXTURE: VIDEO_PROVIDER_NOT_CONFIGURED; no backend/model dispatch');
    return clone(importedJobs.body);
  }});
  await h.click('read');assert.equal(h.calls.some(c=>c.method==='POST'),false);await h.click('start');
  const sent=h.calls.filter(c=>c.method==='POST');assert.equal(sent.length,1);
  assert.equal(sent[0].body.configuration.asset_id,s.assets.find(a=>a.kind==='video').asset_id);
  assert.equal(sent[0].body.source_sha256,s.assets.find(a=>a.kind==='video').checksum_sha256);
  assert.equal(h.controller.isPending(),true);assert.equal(h.memory.size,1);assert.equal(h.reviewed.length,0);
  assert.equal(JSON.stringify(s.timeline),before);assert.equal(h.timers.size,0);
});
test('missing/foreign origin, elevated receipt and role/draft/session drift never dispatch derived analysis',async()=>{
  for(const change of[s=>delete s.timeline.snapshot.metadata.sql_variant_derivative.family_id,s=>s.projectId='prj_foreign',
    s=>s.principal.platform_role='viewer',s=>s.dirty=true,s=>s.busy=true]){
    const s=importedState();change(s);const h=harness({s,handler:c=>clone(imported.responses.receipt.body)});
    await h.click('start');assert.equal(h.calls.some(c=>c.method==='POST'),false);
  }
  for(const late of[s=>s.principal.token_id='changed-session',s=>s.assets.find(a=>a.kind==='video').version++,s=>s.dirty=true]){
    const s=importedState(),h=harness({s,handler:c=>{late(s);return clone(imported.responses.receipt.body);}});
    await h.click('start');assert.equal(h.calls.some(c=>c.method==='POST'),false);assert.equal(h.memory.size,0);
  }
  const s=importedState(),r=clone(imported.responses.receipt.body);r.safety.approval_inherited=true;
  const h=harness({s,handler:()=>r});await h.click('start');assert.equal(h.calls.some(c=>c.method==='POST'),false);
});
test('closing derived video controller during receipt await forbids all new write and pending keys',async()=>{
  const s=importedState();let h;
  h=harness({s,handler:()=>{h.controller.dispose();return clone(imported.responses.receipt.body);}});
  await h.click('start');assert.equal(h.calls.some(c=>c.method==='POST'),false);assert.equal(h.memory.size,0);
});
function capturedState(c,role='viewer'){return{workspaceId:c.context.workspace_id,projectId:c.context.project_id,
  workspaceSlug:c.responses.workspace.body.slug,assets:clone(c.responses.assets.body),busy:false,dirty:false,
  principal:{subject:c.context.viewer_subject,token_id:'explicit-browser-fixture',expires_at:'2100-01-01T00:00:00Z',platform_role:role}};}
test('actual captured viewer ASGI five-state DTO bytes and source scopes match UI contract',()=>{
  const manifest=JSON.parse(readFileSync(new URL('./fixtures/sql-video-jobs/manifest.json',import.meta.url),'utf8'));
  assert.equal(manifest.model_inferences,0);assert.equal(manifest.real_provider_calls,0);assert.equal(manifest.owner_acceptance,false);
  for(const f of manifest.files){const raw=readFileSync(new URL(`./fixtures/sql-video-jobs/${f.name}`,import.meta.url));
    assert.equal(raw.length,f.bytes);assert.equal(createHash('sha256').update(raw).digest('hex'),f.sha256);}
  for(const [name,c]of Object.entries(captured)){const s=capturedState(c),v=c.responses.job.body;
    assert.equal(c.fixture.model_inferences,0);assert.equal(c.fixture.provider_wire_calls,0);
    assert.equal(c.fixture.owner_acceptance,false);assert.equal(validateVideoAnalysisJob(v,s),v);
    assert.equal(v.job.status,name);assert.equal(videoAnalysisAssets(s).length,1);
    assert.throws(()=>videoAnalysisPayload(s,c.context.asset_id,3,'viewer-cannot-write'));}
});
test('same-context actual SQL queued/running/ready DTO replay drives UI without model dispatch',async()=>{
  const s=capturedState(captured.queued,'editor');let details=0;
  const h=harness({s,handler:c=>c.method==='POST'?clone(captured.queued.responses.job.body):
    clone(captured[++details===1?'running':'awaiting_review'].responses.job.body)});
  assert.equal(h.calls.length,0);await h.click('start');assert.equal(h.controller.isPending(),false);
  assert.equal(h.calls[0].body.source_sha256,captured.queued.context.source_sha256);
  await h.tick();assert.match(h.get('status').textContent,/Đang phân tích/);await h.tick();
  assert.match(h.get('status').textContent,/cần kiểm tra/);assert.equal(h.get('review').disabled,false);
  assert.deepEqual(h.calls.map(c=>c.method),['POST','GET','GET']);assert.equal(h.reviewed.length,0);assert.equal(h.timers.size,0);
});
test('a busy Studio tick pauses reads and sync resumes active GET polling with no new POST',async()=>{const h=harness();
  await h.click('start');h.s.busy=true;await h.tick();assert.equal(h.timers.size,0);assert.equal(h.calls.length,1);
  h.s.busy=false;h.controller.sync();assert.equal(h.timers.size,1);await h.tick();
  assert.deepEqual(h.calls.map(c=>c.method),['POST','GET']);assert.match(h.get('status').textContent,/cần kiểm tra/);
});
test('selected B review uses B while canonical A and immutable source remain unchanged',()=>{
  const s=capturedState(captured.awaiting_review,'editor'),b=clone(captured.awaiting_review.responses.job.body);
  const a=clone(b.analysis);a.analysis_id='ana_'+'9'.repeat(24);s.analyses=[a,clone(b.analysis)];
  s.timeline={source_analysis_id:a.analysis_id,current_version:3,snapshot:{metadata:{},tracks:[]}};
  const before=JSON.stringify(s.timeline),selection=videoReviewSelection(s,b);
  assert.equal(selectedVideoReviewAnalysis(s,selection,a),s.analyses[1]);assert.equal(JSON.stringify(s.timeline),before);
  const segment=b.analysis.transcript.segments[0];
  assert.throws(()=>transcriptEditPayload(b.analysis,s.timeline,segment.segment_id,segment.text),/phân tích khác/);
  assert.equal(selectedVideoReviewAnalysis(s,null,a),a);
  s.assets[0].checksum_sha256='f'.repeat(64);assert.equal(selectedVideoReviewAnalysis(s,selection,a),null);
  assert.equal(JSON.stringify(s.timeline),before);
});
test('selected review cannot adopt a missing, foreign or failed analysis and does not fall back silently',()=>{
  const s=capturedState(captured.awaiting_review,'editor'),b=clone(captured.awaiting_review.responses.job.body),selection=videoReviewSelection(s,b),fallback={analysis_id:'canonical-A'};
  for(const patch of[{project_id:'prj_foreign'},{workspace_id:'wsp_foreign'},{asset_id:'ast_foreign_video'},{status:'failed'}]){
    s.analyses=[{...clone(b.analysis),...patch}];assert.equal(selectedVideoReviewAnalysis(s,selection,fallback),null);}
  s.analyses=[];assert.equal(selectedVideoReviewAnalysis(s,selection,fallback),null);
  assert.throws(()=>videoReviewSelection(capturedState(captured.queued,'editor'),captured.queued.responses.job.body));
});

test('constructor and sync send no requests and uploaded filenames stay literal',()=>{const h=harness();h.controller.sync();
  assert.deepEqual(h.calls,[]);assert.equal(h.get('source').children[0].textContent,h.s.assets[0].filename);
  assert.equal(h.get('cancel').disabled,true);assert.equal(h.get('review').disabled,true);});
test('video picker excludes wrong tenant, generated files, invalid hashes and unsupported clocks',()=>{const s=state(),a=s.assets[0];
  for(const patch of[{project_id:'prj_other'},{workspace_id:'wsp_other'},{kind:'audio'},{size_bytes:0},{checksum_sha256:'unknown'},
    {provenance:{source_type:'ai_generated',media_metadata:a.provenance.media_metadata}},
    {provenance:{source_type:'user_upload',media_metadata:{media_kind:'video',duration_seconds:1801}}}])s.assets.push({...clone(a),...patch});
  assert.equal(videoAnalysisAssets(s).length,1);});
test('viewer, dirty workbench and active project bootstrap cannot submit by forged events',async()=>{
  for(const change of[s=>s.principal.platform_role='viewer',s=>s.dirty=true,s=>s.busy=true]){const s=state();change(s);const h=harness({s});
    await h.click('start');assert.equal(h.calls.length,0);assert.equal(h.memory.size,0);assert.ok(h.messages.length);}});
test('payload binds exact source and strict provider words, no approval or publication authority',()=>{const s=state(),p=videoAnalysisPayload(s,assetId,5,'fixture-idempotent-key');
  assert.deepEqual(Object.keys(p).sort(),['configuration','idempotency_key','source_sha256']);assert.equal(p.source_sha256,hash);
  assert.equal(p.configuration.top_highlights,5);assert.equal(p.configuration.word_timing_policy,'strict_provider_intervals');
  assert.throws(()=>videoAnalysisPayload(s,assetId,4,'fixture-idempotent-key'));});
test('queue submission returns immediately, persists key before POST and polls GET only',async()=>{const memory=new Map(),h=harness({memory,handler:c=>{
  if(c.method==='POST'){assert.equal(memory.size,1);return value('queued',state(),c.body);}return value('awaiting_review');}});
  await h.click('start');assert.equal(h.calls.length,1);assert.equal(h.calls[0].method,'POST');assert.equal(h.memory.size,0);
  assert.equal(h.get('cancel').disabled,false);assert.equal(h.get('review').disabled,true);await h.tick();
  assert.deepEqual(h.calls.map(c=>c.method),['POST','GET']);assert.match(h.get('status').textContent,/cần kiểm tra/);
  assert.equal(h.get('review').disabled,false);assert.equal(h.timers.size,0);assert.equal(h.reviewed.length,0);
  await h.click('review');assert.equal(h.reviewed.length,1);assert.equal(h.calls.length,2);});
test('cancel sends only explicit selected job and never edits timeline',async()=>{const h=harness();await h.click('read');await h.click('cancel');
  assert.equal(h.calls[1].path,`/api/v1/projects/prj_fixture/analysis-jobs/${jobId}/cancel`);assert.deepEqual(h.calls[1].body,{});
  assert.match(h.get('status').textContent,/Đã hủy/);assert.equal(h.timers.size,0);assert.equal(h.memory.size,0);});
test('lost create response keeps exact intent; read does not infer an older job was that write',async()=>{let first=true;const h=harness({handler:c=>{
  if(c.method==='POST'&&first){first=false;throw Error('Fixture dropped response');}return c.method==='POST'?value('queued',state(),c.body):[value('queued')];}});
  await h.click('start');const sent=clone(h.calls[0].body);assert.equal(h.controller.isPending(),true);assert.equal(h.memory.size,1);
  await h.click('start');assert.equal(h.calls.length,1);await h.click('read');assert.equal(h.calls.length,2);
  assert.equal(h.controller.isPending(),true);assert.equal(h.get('start').disabled,true);await h.click('retry');
  assert.deepEqual(h.calls[2].body,sent);assert.equal(h.controller.isPending(),false);assert.equal(h.memory.size,0);});
test('reload in a new controller preserves old key and does not dispatch automatically',async()=>{const memory=new Map();
  const old=harness({memory,handler:()=>{throw Error('Lost response');}});await old.click('start');const sent=clone(old.calls[0].body);old.controller.dispose();
  const fresh=harness({memory});assert.equal(fresh.calls.length,0);await fresh.click('read');assert.equal(fresh.controller.isPending(),true);
  await fresh.click('retry');assert.deepEqual(fresh.calls[1].body,sent);});
test('storage failure blocks POST before provider admission',async()=>{const h=harness({storage:{getItem:()=>null,setItem:()=>{throw Error('No quota');}}});
  await h.click('start');assert.equal(h.calls.length,0);assert.match(h.messages[0][0],/Chưa lưu/);});
test('malformed or elevated response remains uncertain and cannot generate a new key',async()=>{const h=harness({handler:c=>{
  const v=value('queued',state(),c.body);v.publishing_enabled=true;return v;}});await h.click('start');
  assert.equal(h.controller.isPending(),true);assert.equal(h.memory.size,1);await h.click('start');assert.equal(h.calls.length,1);});
test('scope change while POST waits keeps original receipt and discards stale adoption',async()=>{let finish;const h=harness({handler:c=>new Promise(resolve=>finish=()=>resolve(value('queued',state(),c.body)))});
  const request=h.click('start');await Promise.resolve();h.s.projectId='prj_next';h.controller.sync();finish();await request;
  assert.equal(h.memory.size,1);assert.equal(h.get('saved').children.length,0);assert.equal(h.timers.size,0);});
test('actual source hash drift while POST waits blocks stale result and retains original key',async()=>{let finish;const h=harness({handler:c=>new Promise(resolve=>finish=()=>resolve(value('queued',state(),c.body)))});
  const request=h.click('start');await Promise.resolve();h.s.assets[0].checksum_sha256='f'.repeat(64);finish();await request;
  assert.equal(h.controller.isPending(),true);assert.equal(h.get('saved').children.length,0);await h.click('retry');assert.equal(h.calls.length,1);});
test('foreign job, lineage mutation, invalid progress and premature ready never pass read validation',()=>{
  for(const change of[v=>v.job.project_id='prj_other',v=>v.analysis.workspace_id='wsp_other',v=>v.job.request.analysis_id='ana_'+'f'.repeat(24),
    v=>v.source_sha256='f'.repeat(64),v=>v.custody_sha256='unknown',v=>v.job.progress=101,v=>v.job.status='awaiting_review',
    v=>v.human_review_required=false,v=>v.timeline_mutated=true]){const v=value();change(v);assert.throws(()=>validateVideoAnalysisJob(v,state()));}});
test('poll reply cannot regress a later explicit saved read',async()=>{let oldReply,detailCalls=0;const h=harness({handler:c=>{
  if(c.method==='POST')return value('queued',state(),c.body);
  if(c.path.endsWith('/analysis-jobs'))return[value('awaiting_review')];
  detailCalls++;return new Promise(resolve=>oldReply=()=>resolve(value('running')));}});
  await h.click('start');const old=h.tick();await Promise.resolve();await h.click('read');oldReply();await old;
  assert.equal(detailCalls,1);assert.match(h.get('status').textContent,/cần kiểm tra/);assert.equal(h.get('review').disabled,false);assert.equal(h.timers.size,0);});
test('needs-attention recovery does not schedule inference, approval or automatic replay',async()=>{const h=harness({handler:()=>[value('needs_attention')]});
  await h.click('read');assert.equal(h.calls.length,1);assert.equal(h.calls[0].method,'GET');assert.equal(h.timers.size,0);
  assert.equal(h.get('cancel').disabled,true);assert.equal(h.get('review').disabled,true);assert.match(h.get('status').textContent,/không tự chạy lại/);});
test('same source active or ambiguous job blocks forged new intent even if highlight count changes',async()=>{
  for(const status of['queued','running','needs_attention']){const h=harness({handler:()=>[value(status)]});await h.click('read');
    assert.equal(h.get('start').disabled,true);h.get('top').value='5';h.get('top').listeners.change();await h.click('start');
    assert.equal(h.calls.length,1);assert.equal(h.calls[0].method,'GET');assert.equal(h.memory.size,0);
    assert.equal(h.get('saved').children[0].textContent.startsWith(h.s.assets[0].filename),true);}});
test('disposing controller cancels timer and late results cannot change view',async()=>{let finish;const h=harness({handler:c=>{
  if(c.method==='POST')return value('queued',state(),c.body);return new Promise(resolve=>finish=()=>resolve(value('awaiting_review')));}});
  await h.click('start');const pending=h.tick();await Promise.resolve();h.controller.dispose();finish();await pending;
  assert.equal(h.timers.size,0);assert.match(h.get('status').textContent,/Đang chờ/);});
test('Studio integration replaces synchronous analyze, preserves busy and dirty guards, disposes polling',()=>{
  const multi=readFileSync(new URL('../multi-input.mjs',import.meta.url),'utf8'),studio=readFileSync(new URL('../studio.js',import.meta.url),'utf8'),
    html=readFileSync(new URL('../studio.html',import.meta.url),'utf8');
  assert.equal(multi.includes('/analyze`'),false);assert.match(html,/id="video-analysis-jobs"/);
  assert.match(multi,/control\.closest\('#video-analysis-jobs'\)/);assert.match(studio,/multiInput\.isBusy\(\)/);
  assert.match(studio,/multiInput\.onBusyChanged/);assert.match(studio,/await videoReview\.reload\(\)/);
  assert.match(studio,/videoReview\.dispose\(\)/);assert.match(studio,/unsubscribeVideoBusy\(\)/);});
test('Studio review binds the selected DTO and transcript forms, leaving canonical source selection separate',()=>{
  const source=readFileSync(new URL('../studio.js',import.meta.url),'utf8');
  assert.match(source,/onReview: async value =>[\s\S]*?videoReviewSelection\(state,value\)[\s\S]*?state\.videoReviewSelection=selection/);
  assert.match(source,/function reviewedAnalysis\(\)\{return selectedVideoReviewAnalysis/);
  assert.match(source,/function renderAnalysisReview\(\)\{\s*const analysis=reviewedAnalysis\(\)/);
  assert.match(source,/data-analysis-id="\$\{escapeHtml\(analysis\.analysis_id\)\}"/);
  assert.match(source,/state\.analyses\.find\(a=>a\.analysis_id===form\.dataset\.analysisId/);
  assert.match(source,/expected_timeline_version: state\.timeline\?\.current_version \?\? null/);
});
