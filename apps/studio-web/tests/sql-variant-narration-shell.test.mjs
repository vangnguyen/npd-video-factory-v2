import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const code=readFileSync(new URL('../studio.js',import.meta.url),'utf8');
const captured=JSON.parse(readFileSync(new URL('./fixtures/sql-variant-narration/asgi.json',import.meta.url),'utf8'));
const clone=structuredClone;
const segment=(start,end)=>{
  const first=code.indexOf(start),last=code.indexOf(end,first);
  assert.ok(first>=0&&last>first);return code.slice(first,last);
};
test('actual parent state blocks unsaved audio/subtitles and family operations without locking its own narration callback',()=>{
  const s={projectLoading:0,activeProductionRender:null,transcriptDrafts:new Map()};
  let draft='saved',pending=false,working=false,familyPending=false;
  const policies=new Function('state','multiInput','audioReview','stockReview','videoReview','multiInputBaseline','audioWorkbenchDraft',
    'productionBaseline','productionWorkbenchDraft','variantNarration','variantFamilies',
    segment('function sqlEditorState(){','\nconst variantFamilies =')+'\nreturn {sqlFamilyState,sqlNarrationState};')(
      s,{isBusy:()=>false},{isDirty:()=>false},{isPending:()=>false},{isPending:()=>false},null,()=>'',
      'saved',()=>draft,{isPending:()=>pending,isWorking:()=>working},{isPending:()=>familyPending,isBusy:()=>false});
  assert.equal(policies.sqlNarrationState().dirty,false);
  draft='edited voice or subtitle';assert.equal(policies.sqlNarrationState().dirty,true);assert.equal(policies.sqlFamilyState().dirty,true);
  draft='saved';working=true;pending=true;
  assert.equal(policies.sqlFamilyState().busy,true);assert.equal(policies.sqlFamilyState().dirty,true);
  assert.equal(policies.sqlNarrationState().busy,false);assert.equal(policies.sqlNarrationState().dirty,false);
  familyPending=true;assert.equal(policies.sqlNarrationState().dirty,true);
});
function state(){return{workspaceId:captured.context.workspace_id,projectId:captured.context.project_id,
  principal:{subject:captured.context.actor_ref,token_id:'explicit-shell-fixture'},
  timeline:clone(captured.timeline),productionPackage:clone(captured.package_before),assets:[],busy:false,dirty:false};}
function callbacks(s,api){
  const effects=[];let token='transient-fixture-token';
  const value=new Function('state','sqlNarrationState','sessionToken','api','renderBrowser','renderSummary','renderProduction','startProductionPolling',
    segment('function narrationEditorBoundary(){','\ndocument.addEventListener')+'\nreturn {refreshNarrationAssets,refreshNarrationReview};')(
      s,()=>s,()=>token,api,...['browser','summary','production','poll'].map(name=>()=>effects.push(name)));
  return{...value,effects,setToken:v=>{token=v;}};
}
for(const drift of ['project','session','token','timeline','draft'])test(`actual Studio import callback rejects ${drift} drift during assets read`,async()=>{
  const s=state(),original=JSON.stringify(s.assets);let release;
  const h=callbacks(s,()=>new Promise(resolve=>{release=resolve;}));
  const pending=h.refreshNarrationAssets(clone(captured.receipt_read));
  if(drift==='project')s.projectId='prj_another_project';
  if(drift==='session')s.principal.token_id='another-session';
  if(drift==='token')h.setToken('changed-token');
  if(drift==='timeline')s.timeline.current_version++;
  if(drift==='draft')s.dirty=true;
  release([]);await assert.rejects(pending,/đã đổi/);
  assert.equal(JSON.stringify(s.assets),original);assert.deepEqual(h.effects,[]);
});
test('actual Studio import callback adopts only current child assets and never reloads editor or queues',async()=>{
  const s=state(),timeline=JSON.stringify(s.timeline);
  const asset={project_id:s.projectId,workspace_id:s.workspaceId,asset_id:'ast_fixture_narration'};
  const h=callbacks(s,async()=>[asset]);await h.refreshNarrationAssets(clone(captured.receipt_read));
  assert.deepEqual(s.assets,[asset]);assert.equal(JSON.stringify(s.timeline),timeline);assert.deepEqual(h.effects,['browser']);
});
test('actual Studio review callback adopts exact new review; a competing review cannot replace the displayed project',async()=>{
  for(const changed of [false,true]){
    const s=state(),before=JSON.stringify(s.productionPackage),render=clone(captured.review_response);
    const pack={...clone(s.productionPackage),latest_review_render:clone(render)};
    if(changed)pack.latest_review_render.render_id='rnd_other_review';
    const h=callbacks(s,async()=>pack),task=h.refreshNarrationReview(render);
    if(changed){await assert.rejects(task,/đã đổi/);assert.equal(JSON.stringify(s.productionPackage),before);assert.deepEqual(h.effects,[]);}
    else{await task;assert.equal(s.activeProductionRender.render_id,render.render_id);assert.deepEqual(h.effects,['summary','production','poll']);}
  }
});
test('actual Studio approval guard preserves approved history but refuses a new review with identical content versions',()=>{
  const current=new Function(segment('function currentProductionApproval(','\nfunction renderProduction()')+'\nreturn currentProductionApproval;')();
  const p=clone(captured.package_before),review=clone(captured.review_response);
  p.latest_review_render=review;
  p.approval={approval_id:'apr_fixture_history',project_id:p.project_id,package_id:p.package_id,
    preview_render_id:review.render_id,preview_version:review.version,status:'approved',
    timeline_version_id:p.timeline_version_id,timeline_version:p.timeline_version,
    subtitle_version_id:p.subtitle.subtitle_version_id,subtitle_version:p.subtitle.version,
    audio_version_id:p.audio_mix.audio_version_id,audio_version:p.audio_mix.version};
  assert.equal(current(p),p.approval);const saved=JSON.stringify(p.approval);
  p.latest_review_render={...review,render_id:'rnd_new_review_same_versions'};
  assert.equal(current(p),null);assert.equal(JSON.stringify(p.approval),saved);
  p.latest_review_render=review;p.current_for_timeline=false;assert.equal(current(p),null);
});
for(const change of ['project','token','render'])test(`actual Studio poll cannot adopt stale ${change} after package await`,async()=>{
  const s=state(),render=clone(captured.review_response);s.activeProductionRender=render;
  let token='old-token',release,calls=0;const effects=[];
  const poll=new Function('state','sessionToken','api','renderSummary','renderProduction','describeProductionRender','stopProductionPolling','toast',
    'let productionPollGeneration=0,productionPollInFlight=null;\n'+segment('function productionPollingBoundary(){','\nfunction stopProductionPolling()')+'\nreturn pollProductionRender;')(
      s,()=>token,async()=>{calls++;return calls===1?render:new Promise(resolve=>{release=resolve;});},
      ()=>effects.push('summary'),()=>effects.push('production'),()=>({terminal:true}),()=>effects.push('stop'),()=>effects.push('toast'));
  const pending=poll();await new Promise(resolve=>setImmediate(resolve));
  const before=JSON.stringify(s.productionPackage);
  if(change==='project')s.projectId='prj_another_fixture';
  if(change==='token')token='changed-token';
  if(change==='render')s.activeProductionRender={...render,render_id:'rnd_new_current'};
  release({...clone(s.productionPackage),latest_review_render:render});await pending;
  assert.equal(JSON.stringify(s.productionPackage),before);assert.deepEqual(effects,[]);
});
function pollHarness(s,api){const effects=[];
  const value=new Function('state','sessionToken','api','renderSummary','renderProduction','describeProductionRender','toast','window',
    'let productionPollGeneration=0,productionPollInFlight=null;\n'+
    segment('function productionPollingBoundary(){','\nasync function requestProductionApproval()')+
    '\nreturn {poll:pollProductionRender,stop:stopProductionPolling};')(
      s,()=> 'stable-fixture-session',api,()=>effects.push('summary'),()=>effects.push('production'),
      render=>({terminal:render.status==='awaiting_review',label:render.status}),()=>effects.push('toast'),{clearInterval(){effects.push('stop');}});
  return{...value,effects};
}
test('actual Studio serializes a delayed poll before accepting the next terminal status',async()=>{
  const s=state(),running={...clone(captured.review_response),status:'running',progress:10},terminal={...running,status:'awaiting_review',progress:100};
  s.activeProductionRender=running;s.productionPollTimer=100;let calls=0,release;
  const h=pollHarness(s,async()=>{calls++;if(calls===1)return running;
    if(calls===2)return new Promise(resolve=>{release=resolve;});
    return calls===3?terminal:{...clone(s.productionPackage),latest_review_render:terminal};});
  const first=h.poll();await new Promise(resolve=>setImmediate(resolve));
  await h.poll();assert.equal(calls,2);
  release({...clone(s.productionPackage),latest_review_render:running});await first;
  await h.poll();assert.equal(s.activeProductionRender.status,'awaiting_review');assert.equal(s.productionPollTimer,null);
  assert.equal(h.effects.filter(x=>x==='stop').length,1);
});
test('actual Studio stop/restart invalidates an older response for the same project, session and render',async()=>{
  const s=state(),running={...clone(captured.review_response),status:'running',progress:10},terminal={...running,status:'awaiting_review',progress:100};
  s.activeProductionRender=running;s.productionPollTimer=100;let calls=0,release;
  const h=pollHarness(s,async()=>{calls++;if(calls===1)return running;
    if(calls===2)return new Promise(resolve=>{release=resolve;});
    return calls===3?terminal:{...clone(s.productionPackage),latest_review_render:terminal};});
  const older=h.poll();await new Promise(resolve=>setImmediate(resolve));h.stop();s.productionPollTimer=200;
  await h.poll();assert.equal(s.activeProductionRender.status,'awaiting_review');
  const accepted=JSON.stringify(s.productionPackage);
  release({...clone(s.productionPackage),latest_review_render:running});await older;
  assert.equal(s.activeProductionRender.status,'awaiting_review');assert.equal(JSON.stringify(s.productionPackage),accepted);
});
