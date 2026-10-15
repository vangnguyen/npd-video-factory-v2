import {withIdleManualReframe} from './root-manual-reframe-idle-context.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash,webcrypto} from 'node:crypto';
import {audioRole} from '../uploaded-audio-review.mjs';
import {audioProcessingRead,initializeSqlTimelineAudioProcessing} from '../sql-timeline-audio-processing.mjs';

// Preserved actual main ASGI/owned SQLite capture. The UI transports/races
// below are explicit Node fixtures; no SQL, media, model or Owner acceptance.
const code=readFileSync(new URL('../studio.js',import.meta.url),'utf8');
const bytes=readFileSync(new URL('./fixtures/sql-audio-processing/asgi.json',import.meta.url));
const captured=JSON.parse(bytes),manifest=JSON.parse(readFileSync(new URL('./fixtures/sql-audio-processing/manifest.json',import.meta.url)));
const clone=structuredClone,r=captured.responses;
function segment(start,end){const a=code.indexOf(start),b=code.indexOf(end,a);assert.ok(a>=0&&b>a);return code.slice(a,b);}
function state(){return{workspaceId:captured.context.workspace_id,projectId:captured.context.project_id,
  principal:{...clone(r.session.body),expires_at:'2100-01-01T00:00:00Z'}, // explicit policy clock fixture, original DTO retained above
  timeline:clone(r.timeline_before.body),versions:clone(r.history_before.body),assets:[],analyses:[],mediaPlans:[],
  preview:{status:'ready',valid_for_current_timeline:true},productionPackage:{current_for_timeline:true,
    approval:{status:'approved'},latest_review_render:{render_id:'fixture-old-review'},latest_final_render:{render_id:'fixture-old-final'}},
  selectedClipId:'fixture-old-clip',undoStack:[1],redoStack:[1],activeProductionRender:null,busy:false,dirty:false};}
function selection(){const data=r.processing_put.body;return{workspace_id:captured.context.workspace_id,
  project_id:captured.context.project_id,actor_ref:captured.context.actor_ref,parent_version:2,result_version:3,
  ui_source_sha256:'a'.repeat(64),receipt:clone(data.receipt),timeline:clone(data.timeline)};}
function harness(s=state(),handler,initialize=()=>({})){const calls=[],effects=[];let token='EXPLICIT_TRANSIENT_STUDIO_CONTRACT',audio='saved-audio',production='saved-production',now=Date.now();
  const policy=()=>s;
  const api=async(path,options)=>{calls.push(path);return handler?handler(path,calls.length,options):clone(path.endsWith('/versions')?r.history_after.body:r.processing_current.body);};
  const history=withIdleManualReframe(segment('function videoWordHistoryMatches(','\nasync function refreshVideoWordReceipt')+'\nreturn videoWordHistoryMatches;')();
  const own=withIdleManualReframe('state','sqlEditorState','variantFamilies','variantNarration','videoWordReview','initializeSqlTimelineAudioProcessing',
    '$','api','sessionToken','toast','productionWorkbenchDraft','audioWorkbenchDraft','audioRole','audioProcessingRead',
    'videoWordHistoryMatches','stopPreviewPolling','stopProductionPolling','render','syncVideoWordPeers','Date','sourceLinkedHeld',
    "let sqlAudioProcessing=null;const audioProcessingAdmission=Symbol('private-fixture');\n"+
    segment('function sqlAudioEditorState(){','\nfunction videoWordEditorBoundary(){')+'\nreturn {refreshSqlAudioProcessing,sqlAudioEditorState};')(
      s,policy,{isBusy:()=>false,isPending:()=>false},null,null,initialize,()=>({}),api,()=>token,()=>{},
      ()=>production,()=>audio,audioRole,audioProcessingRead,history,()=>effects.push('stop-preview'),
      ()=>effects.push('stop-production'),()=>effects.push('render'),()=>{},{parse:Date.parse,now:()=>now},()=>false);
  return{...own,calls,effects,setToken:v=>{token=v;},setAudio:v=>{audio=v;},setProduction:v=>{production=v;},setNow:v=>{now=v;}};
}

test('raw actual main fixture preserves original DB/source/history and records one logical metadata CAS',()=>{
  assert.equal(createHash('sha256').update(bytes).digest('hex'),manifest.actual_asgi_capture.sha256);
  assert.equal(bytes.length,manifest.actual_asgi_capture.bytes);
  assert.equal(manifest.http_requests,11);assert.equal(manifest.successful_metadata_cas_operations,1);
  assert.equal(manifest.exact_replay_operations,1);assert.equal(manifest.stale_rejections,1);
  assert.equal(manifest.non_timeline_tables_unchanged,true);assert.equal(manifest.original_timeline_history_unchanged,true);
  assert.equal(manifest.protected_seed.before_sha256,manifest.protected_seed.after_sha256);
  assert.equal(manifest.schema_sha256_before,manifest.schema_sha256_after);
  assert.equal(r.processing_before.body.configuration.duck_music,false);
  assert.equal(r.processing_before.body.configuration.duck_threshold,.02);
  assert.equal(r.processing_put.body.timeline.current_version,3);
  assert.deepEqual(r.processing_replay.body.receipt,r.processing_put.body.receipt);
  assert.equal(r.processing_stale.status,409);
  assert.equal(Object.hasOwn(r.session.body,'token_id'),false);
  assert.equal(captured.scope.new_model_calls,0);assert.equal(captured.scope.media_bytes_read,0);
  assert.equal(captured.scope.owner_approval,false);
});
test('actual callback installs only exact current receipt/history and invalidates old review without a write',async()=>{
  const s=state(),h=harness(s),original=JSON.stringify(r.history_before.body);
  await h.refreshSqlAudioProcessing(selection());
  assert.deepEqual(s.timeline,r.processing_put.body.timeline);assert.deepEqual(s.versions,r.history_after.body);
  assert.equal(s.preview.status,'stale');assert.equal(s.productionPackage.current_for_timeline,false);
  assert.equal(s.productionPackage.approval,null);assert.equal(s.productionPackage.latest_review_render,null);
  assert.equal(s.productionPackage.latest_final_render,null);assert.equal(s.activeProductionRender,null);
  assert.deepEqual(s.undoStack,[]);assert.deepEqual(s.redoStack,[]);assert.equal(s.selectedClipId,null);
  assert.equal(JSON.stringify(r.history_before.body),original);
  assert.equal(h.calls.length,3);assert.ok(h.calls.every(path=>!path.includes('render')&&!path.includes('publish')));
  assert.deepEqual(h.effects,['stop-preview','stop-production','render']);
});
test('exact already-installed result can reconcile while another same-number version cannot',async()=>{
  const s=state();s.timeline=clone(r.processing_put.body.timeline);const h=harness(s);
  await h.refreshSqlAudioProcessing(selection());assert.equal(h.calls.length,3);
  const foreign=state();foreign.timeline=clone(r.processing_put.body.timeline);foreign.timeline.current_version_id='tlv_same_number_foreign';
  const f=harness(foreign),before=JSON.stringify(foreign);
  await assert.rejects(f.refreshSqlAudioProcessing(selection()),/khớp đúng nguồn/);
  assert.equal(JSON.stringify(foreign),before);assert.equal(f.calls.length,0);
});
for(const mismatch of ['actor','workspace','project','timeline','parent','result','source'])
  test(`receipt ${mismatch} mismatch cannot install or even start reads`,async()=>{
    const s=state(),v=selection(),h=harness(s),before=JSON.stringify(s);
    if(mismatch==='actor')v.actor_ref='usr:foreign-editor';
    if(mismatch==='workspace')v.workspace_id='wsp_foreign';if(mismatch==='project')v.project_id='prj_foreign';
    if(mismatch==='timeline')v.timeline.timeline_id='tml_foreign';if(mismatch==='parent')v.parent_version--;
    if(mismatch==='result')v.result_version++;if(mismatch==='source')v.timeline.snapshot.metadata.foreign_source=true;
    await assert.rejects(h.refreshSqlAudioProcessing(v),/khớp đúng nguồn/);
    assert.equal(JSON.stringify(s),before);assert.deepEqual(h.calls,[]);assert.deepEqual(h.effects,[]);
  });
for(const during of ['first','history','final'])for(const drift of ['project','token','principal','expiry','role','write-off','canonical','audio-draft','subtitle-draft','asset'])
  test(`${drift} drift during ${during} read preserves current state`,async()=>{
    const s=state();let release;const target={first:1,history:2,final:3}[during];
    const h=harness(s,(path,count)=>count===target?new Promise(resolve=>{release=resolve;}):
      clone(path.endsWith('/versions')?r.history_after.body:r.processing_current.body));
    const work=h.refreshSqlAudioProcessing(selection());await new Promise(resolve=>setImmediate(resolve));
    if(drift==='project')s.projectId='prj_foreign';if(drift==='token')h.setToken('changed-literal-token');
    if(drift==='principal')s.principal.subject='usr:other-editor';if(drift==='expiry')s.principal.expires_at='2000-01-01T00:00:00Z';
    if(drift==='role'){s.principal.platform_role=null;s.principal.workspace_roles={[s.workspaceId]:'viewer'};}
    if(drift==='write-off')s.principal.human_write_enabled=false;if(drift==='canonical')s.timeline.current_version++;
    if(drift==='audio-draft')h.setAudio('edited-unsaved-audio');if(drift==='subtitle-draft')h.setProduction('edited-unsaved-subtitle');
    if(drift==='asset')s.assets.push({asset_id:'explicit-new-asset-fixture'});
    const before=JSON.stringify(s);release(clone(during==='history'?r.history_after.body:r.processing_current.body));
    await assert.rejects(work,/đã đổi/);assert.equal(JSON.stringify(s),before);assert.deepEqual(h.effects,[]);
  });
for(const change of ['newer','foreign','missing','head-id','snapshot','duplicate'])
  test(`contradictory ${change} history cannot authorize current audio receipt`,async()=>{
    const s=state(),versions=clone(r.history_after.body),before=JSON.stringify(s);
    if(change==='newer')versions.unshift({...clone(versions[0]),version:4,timeline_version_id:'tlv_future_history'});
    if(change==='foreign')versions[0].project_id='prj_foreign';if(change==='missing')versions.shift();
    if(change==='head-id')versions[0].timeline_version_id='tlv_other_head';
    if(change==='snapshot')versions[0].snapshot.metadata.other_editor=true;
    if(change==='duplicate')versions.push(clone(versions[0]));
    const h=harness(s,path=>clone(path.endsWith('/versions')?versions:r.processing_current.body));
    await assert.rejects(h.refreshSqlAudioProcessing(selection()),/Lịch sử timeline/);
    assert.equal(JSON.stringify(s),before);assert.equal(h.calls.length,2);assert.deepEqual(h.effects,[]);
  });
for(const change of ['actor','mutation-missing','mutation-type','receipt-missing','receipt-actor','receipt-key','receipt-hash',
  'receipt-parent','receipt-result','receipt-config','source-flag','publish-flag','missing-flags'])
  test(`contradictory current head ${change} cannot authorize audio receipt`,async()=>{
    const s=state(),versions=clone(r.history_after.body),head=versions[0],before=JSON.stringify(s);
    if(change==='actor')head.actor_ref='usr:foreign-editor';
    if(change==='mutation-missing')delete head.mutation;
    if(change==='mutation-type')head.mutation.type='foreign-mutation';
    if(change==='receipt-missing')delete head.mutation.receipt;
    if(change==='receipt-actor')head.mutation.receipt.actor_ref='usr:foreign-editor';
    if(change==='receipt-key')head.mutation.receipt.request_key='another_fixture_key';
    if(change==='receipt-hash')head.mutation.receipt.request_sha256='f'.repeat(64);
    if(change==='receipt-parent')head.mutation.receipt.parent_version=1;
    if(change==='receipt-result')head.mutation.receipt.result_version=4;
    if(change==='receipt-config')head.mutation.receipt.configuration.duck_ratio=9;
    if(change==='source-flag')head.mutation.source_media_mutated=true;
    if(change==='publish-flag')head.mutation.publish_requested=true;
    if(change==='missing-flags'){delete head.mutation.source_media_mutated;delete head.mutation.publish_requested;}
    const h=harness(s,path=>clone(path.endsWith('/versions')?versions:r.processing_current.body));
    await assert.rejects(h.refreshSqlAudioProcessing(selection()),/Lịch sử timeline/);
    assert.equal(JSON.stringify(s),before);assert.equal(h.calls.length,2);assert.deepEqual(h.effects,[]);
  });
for(const change of ['receipt-key','receipt-hash','current-version','configuration'])
  test(`${change} at final reread leaves exact pending source untouched`,async()=>{
    const s=state(),before=JSON.stringify(s);
    const h=harness(s,(path,count)=>{if(path.endsWith('/versions'))return clone(r.history_after.body);
      const data=clone(r.processing_current.body);if(count===3){
        if(change==='receipt-key')data.receipt.request_key='another_fixture_key';
        if(change==='receipt-hash')data.receipt.request_sha256='f'.repeat(64);
        if(change==='current-version')data.timeline.current_version++;
        if(change==='configuration'){data.configuration.duck_ratio=9;data.receipt.configuration.duck_ratio=9;data.timeline.snapshot.metadata.source_audio_processing.duck_ratio=9;}
      }return data;});
    await assert.rejects(h.refreshSqlAudioProcessing(selection()));assert.equal(JSON.stringify(s),before);
    assert.equal(h.calls.length,3);assert.deepEqual(h.effects,[]);
  });
test('private admission permits only its controller while peer-held writers stay closed and flags never reach fetch',async()=>{
  let audioHeld=true,wordHeld=false;const calls=[],audioPermit=Symbol('audio-only'),wordPermit=Symbol('word-only');
  const api=withIdleManualReframe('authenticatedFetch','videoWordsHeld','videoWordAdmission','audioProcessingHeld','audioProcessingAdmission','sourceLinkedHeld','sourceLinkedAdmission',
    segment('class ApiError extends Error {','\nfunction toast(')+'\nreturn api;')(
      async(path,options)=>{calls.push({path,options});return{ok:true,status:204};},()=>wordHeld,wordPermit,()=>audioHeld,audioPermit,()=>false,Symbol('unused-source-controller'));
  for(const method of ['POST','PUT','PATCH','DELETE'])await assert.rejects(api('/api/v1/projects/current/timeline',{method}),/cấu hình âm thanh/);
  assert.equal(calls.length,0);await api('/api/v1/projects/current/timeline');
  await api('/api/v1/projects/current/timeline/audio-processing',{method:'PUT',body:'{}',audioProcessingAdmission:audioPermit});
  assert.equal(Object.hasOwn(calls.at(-1).options,'audioProcessingAdmission'),false);
  wordHeld=true;await assert.rejects(api('/api/v1/projects/current/timeline/audio-processing',{method:'PUT',audioProcessingAdmission:audioPermit}),/sửa từ/);
  audioHeld=false;await api('/api/v1/projects/current/analyses/current/transcript-words',{method:'POST',videoWordAdmission:wordPermit});
  assert.equal(Object.hasOwn(calls.at(-1).options,'videoWordAdmission'),false);
});

for(const during of ['first','history','final'])test(`elapsed expiry during ${during} read cannot install despite unchanged principal and token`,async()=>{
  const s=state();let release;const target={first:1,history:2,final:3}[during];
  const h=harness(s,(path,count)=>count===target?new Promise(resolve=>{release=resolve;}):
    clone(path.endsWith('/versions')?r.history_after.body:r.processing_current.body));
  const work=h.refreshSqlAudioProcessing(selection());await new Promise(resolve=>setImmediate(resolve));
  const before=JSON.stringify(s);h.setNow(Date.parse(s.principal.expires_at)+1);
  release(clone(during==='history'?r.history_after.body:r.processing_current.body));
  await assert.rejects(work,/đã đổi/);assert.equal(JSON.stringify(s),before);assert.deepEqual(h.effects,[]);
});

test('shipped controller and actual Studio callback complete one explicit fixture PUT using raw actual SQL DTOs',async()=>{
  class Element{
    constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.listeners={};this.value='';this.checked=false;this.disabled=false;this.textContent='';}
    append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}
    setAttribute(k,v){this.attributes[k]=String(v);}addEventListener(k,v){this.listeners[k]=v;}
  }
  const dom={createElement:tag=>new Element(tag)},root=dom.createElement('section'),memory=new Map();let controller,committed=false,puts=0;
  const all=e=>[e,...e.children.flatMap(all)],get=name=>all(root).find(e=>Object.hasOwn(e.attributes,'data-audio-processing-'+name));
  const s=state(),h=harness(s,(path,_count,options)=>{
    if(options?.method==='PUT'){
      puts++;assert.deepEqual(JSON.parse(options.body),r.processing_put.request);committed=true;return clone(r.processing_put.body);
    }
    return clone(path.endsWith('/versions')?r.history_after.body:committed?r.processing_current.body:r.processing_before.body);
  },options=>{
    controller=initializeSqlTimelineAudioProcessing({...options,root,dom,
      cryptoImpl:{...webcrypto,subtle:webcrypto.subtle,randomUUID:()=> 'fixture_audio_processing_01'},
      storage:{getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v),
        compareAndRemoveItem:(k,v)=>{if(memory.get(k)!==v)return false;memory.delete(k);return true;}}});
    return controller;
  });
  assert.equal(h.calls.length,0);await get('read').listeners.click();assert.equal(h.calls.length,1);
  for(const [name,v] of Object.entries(r.processing_put.request.configuration)){
    const input=get(name);if(typeof v==='boolean'){input.checked=v;input.listeners.change();}
    else{input.value=String(v);input.listeners.input();}
  }
  get('ack').checked=true;get('ack').listeners.change();await get('save').listeners.click();
  assert.equal(puts,1);assert.equal(h.calls.length,5);assert.equal(memory.size,0);
  assert.equal(controller.isPending(),false);assert.equal(controller.isDirty(),false);
  assert.deepEqual(s.timeline,r.processing_put.body.timeline);assert.equal(s.productionPackage.approval,null);
  assert.equal(s.preview.status,'stale');assert.equal(get('ack').checked,false);assert.equal(get('save').disabled,true);
});
