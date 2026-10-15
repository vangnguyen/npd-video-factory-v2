import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash,webcrypto} from 'node:crypto';
import {audioRole} from '../uploaded-audio-review.mjs';
import {getClip} from '../studio-utils.mjs';
import {sourceLinkedRead,initializeSqlSourceLinkedEdit} from '../sql-source-linked-edit.mjs';

// Actual standalone-router/owned SQLite responses. Source probe/ASR were
// deterministic fixtures. The transports, authority clock and asset/analysis
// projections below are explicit Node fixtures, without media/provider/UAT.
const code=readFileSync(new URL('../studio.js',import.meta.url),'utf8');
const bytes=readFileSync(new URL('./fixtures/source-linked-edit/asgi.json',import.meta.url));
const capture=JSON.parse(bytes),r=capture.responses;
const manifest=JSON.parse(readFileSync(new URL('./fixtures/source-linked-edit/manifest.json',import.meta.url)));
const clone=structuredClone;
function segment(a,b){const start=code.indexOf(a),end=code.indexOf(b,start);assert.ok(start>=0&&end>start);return code.slice(start,end);}
function state(){const timeline=clone(r.timeline_before.body),p=r.linked_put.body.receipt.source;
  const media={media_kind:'video',duration_seconds:p.duration_seconds,audio_codec:p.has_audio?'aac':null};
  const asset={asset_id:p.asset_id,workspace_id:timeline.workspace_id,project_id:timeline.project_id,asset_class:'source',
    kind:'video',content_type:'video/mp4',checksum_sha256:p.source_sha256,size_bytes:4096,object_key:p.object_key,
    provenance:{source_type:'user_upload',media_metadata:clone(media)}};
  const analysis={analysis_id:p.analysis_id,asset_id:p.asset_id,workspace_id:timeline.workspace_id,project_id:timeline.project_id,
    status:'succeeded',fingerprint:p.analysis_fingerprint,source_media:media,source_media_mutated:false,publish_requested:false,
    configuration:{asset_id:p.asset_id}};
  return {workspaceId:timeline.workspace_id,projectId:timeline.project_id,timeline,analysis,assets:[asset],analyses:[analysis],mediaPlans:[],
    principal:{...clone(r.session.body),expires_at:'2100-01-01T00:00:00Z'},busy:false,dirty:false,
    versions:clone(r.history_before.body),selectedClipId:'old-selection',undoStack:[1],redoStack:[1],playhead:99,
    preview:{status:'ready',valid_for_current_timeline:true},productionPackage:{current_for_timeline:true,
      approval:{status:'approved'},latest_review_render:{render_id:'old-review'},latest_final_render:{render_id:'old-final'}},activeProductionRender:null};
}
function selection(){const receipt=clone(r.linked_put.body.receipt);return {workspace_id:receipt.workspace_id,project_id:receipt.project_id,
  actor_ref:receipt.actor_ref,parent_version_id:receipt.parent_version_id,parent_version:receipt.parent_version,result_version:receipt.result_version,
  parent_timeline:clone(r.timeline_before.body),receipt,timeline:clone(r.linked_put.body.timeline),
  requested_operations:clone(receipt.requested_operations),applied_operations:clone(receipt.applied_operations)};}
function harness(s=state(),handler,initialize=()=>null){let token='EXPLICIT_LINKED_NODE_TOKEN',audio='saved-audio',production='saved-production',now=Date.now();
  const calls=[],effects=[];let controller;
  const api=async(path,options)=>{calls.push({path,options});return handler?handler(path,calls.length,options):
    clone(path.endsWith('/versions')?r.history_after.body:r.linked_current.body);};
  const stable=new Function(segment('function sqlAudioStable(','\nfunction sqlAudioSourceValue(')+'\nreturn sqlAudioStable;')();
  const history=new Function(segment('function videoWordHistoryMatches(','\nasync function refreshVideoWordReceipt')+'\nreturn videoWordHistoryMatches;')();
  const own=new Function('state','sqlEditorState','reviewedAnalysis','variantFamilies','variantNarration','videoWordReview','sqlAudioProcessing',
    'audioRole','sessionToken','productionWorkbenchDraft','audioWorkbenchDraft','api','sqlAudioStable','sourceLinkedRead','videoWordHistoryMatches',
    'stopPreviewPolling','stopProductionPolling','render','getClip','initializeSqlSourceLinkedEdit','$','toast','Date','audioReview','stockReview','videoReview',
    "let sourceLinkedEditor=null;const sourceLinkedAdmission=Symbol('private-source-fixture');\n"+
    segment('function sourceLinkedEditorState(){','\nfunction activeAnalysis() {')+'\nreturn {refreshSourceLinkedReceipt,sourceLinkedEditorState};')(
      s,()=>s,()=>s.analysis,{isBusy:()=>false,isPending:()=>false,sync(){}},null,null,null,audioRole,()=>token,()=>production,()=>audio,
      api,stable,sourceLinkedRead,history,()=>effects.push('stop-preview'),()=>effects.push('stop-production'),
      ()=>{effects.push('render');controller?.sync();},getClip,options=>(controller=initialize(options)),()=>({}),()=>{},
      {parse:Date.parse,now:()=>now},{sync(){}},{sync(){}},{sync(){}});
  return {...own,calls,effects,setToken:v=>{token=v;},setAudio:v=>{audio=v;},setProduction:v=>{production=v;},setNow:v=>{now=v;}};
}
test('raw final component capture stays byte exact with its actual SQL/HTTP limits',()=>{
  assert.equal(createHash('sha256').update(bytes).digest('hex'),manifest.artifact_sha256);assert.equal(bytes.length,manifest.artifact_bytes);
  assert.equal(manifest.http_requests,11);assert.equal(manifest.logical_cas_mutations,1);assert.equal(manifest.exact_replays,1);
  assert.equal(manifest.stale_conflicts,1);assert.equal(manifest.whole_timeline_dtos_equal,5);
  assert.equal(capture.scope.actual_decode,false);assert.equal(capture.scope.local_model_inferences,0);assert.equal(capture.scope.owner_uat,false);
});
test('actual callback verifies three reads and immutable parent/head before installing exact result',async()=>{
  const s=state(),h=harness(s);await h.refreshSourceLinkedReceipt(selection());
  assert.deepEqual(s.timeline,r.linked_put.body.timeline);assert.deepEqual(s.versions,r.history_after.body);
  assert.equal(s.preview.status,'stale');assert.equal(s.productionPackage.approval,null);
  assert.equal(s.productionPackage.latest_review_render,null);assert.equal(s.productionPackage.latest_final_render,null);
  assert.equal(s.productionPackage.current_for_timeline,false);assert.equal(s.selectedClipId,null);
  assert.equal(s.playhead,s.timeline.snapshot.duration_seconds);assert.equal(h.calls.length,3);
  assert.deepEqual(h.effects,['stop-preview','stop-production','render']);
});
test('reload at exact installed result can use history parent when in-memory parent clone is absent',async()=>{
  const s=state(),v=selection();s.timeline=clone(v.timeline);v.parent_timeline=null;
  await harness(s).refreshSourceLinkedReceipt(v);
  const foreign=state();foreign.timeline=clone(v.timeline);foreign.timeline.current_version_id='tlv_foreign_same_number';
  const h=harness(foreign),before=clone(foreign);await assert.rejects(h.refreshSourceLinkedReceipt(v),/khớp nguồn/);
  assert.deepEqual(foreign,before);assert.equal(h.calls.length,0);
});
for(const change of ['actor','workspace','project','parent-id','parent-snapshot','result-id','requested','applied'])
  test(`preflight ${change} mismatch cannot read or rebase`,async()=>{
    const s=state(),v=selection(),before=clone(s),h=harness(s);
    if(change==='actor')v.actor_ref='usr:other';if(change==='workspace')v.workspace_id='wsp_other';
    if(change==='project')v.project_id='prj_other';if(change==='parent-id')v.parent_version_id='tlv_other';
    if(change==='parent-snapshot')v.parent_timeline.snapshot.metadata.other_editor=true;
    if(change==='result-id')v.timeline.timeline_id='tml_other';if(change==='requested')v.requested_operations=[];
    if(change==='applied')v.applied_operations=[];
    await assert.rejects(h.refreshSourceLinkedReceipt(v));assert.deepEqual(s,before);assert.equal(h.calls.length,0);
  });
for(const during of ['first','history','final'])for(const change of ['project','token','actor','expired','elapsed','role','write-off','timeline','analysis','asset','audio-draft','subtitle-draft'])
  test(`${change} during ${during} read cannot adopt a receipt`,async()=>{
    const s=state();let release;const stop={first:1,history:2,final:3}[during];
    const h=harness(s,(path,count)=>count===stop?new Promise(resolve=>{release=resolve;}):clone(path.endsWith('/versions')?r.history_after.body:r.linked_current.body));
    const work=h.refreshSourceLinkedReceipt(selection());await new Promise(resolve=>setImmediate(resolve));
    if(change==='project')s.projectId='prj_other';if(change==='token')h.setToken('changed-token');
    if(change==='actor')s.principal.subject='usr:other';if(change==='expired')s.principal.expires_at='2000-01-01T00:00:00Z';
    if(change==='elapsed')h.setNow(Date.parse(s.principal.expires_at)+1);
    if(change==='role'){s.principal.platform_role=null;s.principal.workspace_roles={[s.workspaceId]:'viewer'};}
    if(change==='write-off')s.principal.human_write_enabled=false;if(change==='timeline')s.timeline.snapshot.metadata.other_editor=true;
    if(change==='analysis')s.analysis.fingerprint='e'.repeat(64);if(change==='asset')s.assets[0].size_bytes++;
    if(change==='audio-draft')h.setAudio('edited-audio');if(change==='subtitle-draft')h.setProduction('edited-subtitle');
    const before=clone(s);release(clone(during==='history'?r.history_after.body:r.linked_current.body));
    await assert.rejects(work,/đã đổi/);assert.deepEqual(s,before);assert.deepEqual(h.effects,[]);
  });
for(const change of ['parent-id','parent-snapshot','head-actor','head-type','head-receipt','head-hash','source-flag','publish-flag','missing-parent','future'])
  test(`contradictory history ${change} cannot release a linked intent`,async()=>{
    const s=state(),before=clone(s),versions=clone(r.history_after.body),head=versions.find(v=>v.version===2),parent=versions.find(v=>v.version===1);
    if(change==='parent-id')parent.timeline_version_id='tlv_other';if(change==='parent-snapshot')parent.snapshot.metadata.other_editor=true;
    if(change==='head-actor')head.actor_ref='usr:other';if(change==='head-type')head.mutation.type='other';
    if(change==='head-receipt')delete head.mutation.receipt;if(change==='head-hash')head.mutation.receipt.request_sha256='e'.repeat(64);
    if(change==='source-flag')head.mutation.source_media_mutated=true;if(change==='publish-flag')head.mutation.publish_requested=true;
    if(change==='missing-parent')versions.splice(versions.indexOf(parent),1);if(change==='future')versions.push({...clone(head),version:3,timeline_version_id:'tlv_future'});
    const h=harness(s,path=>clone(path.endsWith('/versions')?versions:r.linked_current.body));
    await assert.rejects(h.refreshSourceLinkedReceipt(selection()),/Lịch sử timeline/);
    assert.deepEqual(s,before);assert.equal(h.calls.length,2);assert.deepEqual(h.effects,[]);
  });
for(const change of ['receipt-key','receipt-hash','snapshot'])test(`final ${change} drift keeps parent state untouched`,async()=>{
  const s=state(),before=clone(s),h=harness(s,(path,n)=>{
    if(path.endsWith('/versions'))return clone(r.history_after.body);const data=clone(r.linked_current.body);
    if(n===3){if(change==='receipt-key')data.receipt.request_key='another-request-key';
      if(change==='receipt-hash')data.receipt.request_sha256='e'.repeat(64);if(change==='snapshot')data.timeline.snapshot.metadata.other_editor=true;}
    return data;});
  await assert.rejects(h.refreshSourceLinkedReceipt(selection()));assert.deepEqual(s,before);assert.deepEqual(h.effects,[]);
});

for(const tampered of [false,true])test(`shipped controller→Root callback ${tampered?'retains UNKNOWN on bad history then reconciles':'completes exactly one PUT'} using raw DTOs`,async()=>{
  class Element{constructor(){this.children=[];this.attributes={};this.listeners={};this.disabled=false;this.textContent='';}
    append(...v){this.children.push(...v);}setAttribute(k,v){this.attributes[k]=v;}addEventListener(k,v){this.listeners[k]=v;}}
  const s=state(),memory=new Map(),root=new Element(),dom={createElement:()=>new Element()};let controller,committed=false,puts=0,bad=tampered;
  const h=harness(s,(path,_n,options)=>{
    if(options?.method==='PUT'){puts++;assert.deepEqual(JSON.parse(options.body),r.linked_put.request);committed=true;return clone(r.linked_put.body);}
    if(path.endsWith('/versions')){const rows=clone(r.history_after.body);if(bad)rows.find(v=>v.version===2).mutation.receipt.request_sha256='e'.repeat(64);return rows;}
    return clone(committed?r.linked_current.body:r.linked_before.body);
  },options=>(controller=initializeSqlSourceLinkedEdit({...options,root,dom,cryptoImpl:webcrypto,
    newRequestKey:()=>r.linked_put.request.request_key,storage:{getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v),
      compareAndRemoveItem:(k,v)=>{if(memory.get(k)!==v)return false;memory.delete(k);return true;}}})));
  const before=clone(s),result=await controller.runOperations(clone(r.linked_put.request.operations),{acknowledged:true});
  assert.equal(result,!tampered);assert.equal(puts,1);
  if(tampered){assert.equal(memory.size,1);assert.equal(controller.isPending(),true);assert.deepEqual(s,before);assert.deepEqual(h.effects,[]);
    bad=false;await controller.reconcile();assert.equal(puts,1);}
  assert.equal(memory.size,0);assert.equal(controller.isPending(),false);assert.deepEqual(s.timeline,r.linked_put.body.timeline);
  assert.equal(s.productionPackage.approval,null);assert.equal(s.preview.status,'stale');assert.equal(puts,1);
});
