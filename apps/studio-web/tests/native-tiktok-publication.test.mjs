import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';
import {validateTikTokPublication,validateTikTokDispatch,validateTikTokPublishingFactory} from '../native-tiktok-publication.mjs';
import {initializeNativeOfficialPublications} from '../native-official-publications.mjs';
import {nativeTikTokDryRunIntent,initializeNativePublications} from '../native-publications.mjs';
import {initializeNativeOfficialAnalytics} from '../native-official-analytics.mjs';
import {initializeNativeOfficialRefresh} from '../native-official-refresh.mjs';
const fixture=JSON.parse(fs.readFileSync(new URL('./fixtures/native-tiktok-publication-v1.json',import.meta.url),'utf8')),copy=v=>structuredClone(v);
const stateFor=r=>({workspace_id:r.workspace_id,project:{id:r.project_id}}),page=items=>({schema_version:'native-official-publication-page-v1',workspace_id:items[0].workspace_id,project_id:items[0].project_id,items,next_cursor:null,automatic_publishing:false,token_returned:false,session_uri_returned:false});
function dom(){const nodes=new Map();class Node{constructor(){this.children=[];this.value='';this.checked=false;this.dataset={};this.listeners={};}set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,v){this.listeners[k]=v;}}
  return{createElement:()=>new Node(),getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);}};}
function harness({item=null,project=fixture.project}={}){const root=dom(),get=n=>root.getElementById('native-official-publish-'+n),calls=[],messages=[],state={workspace_id:project.id===fixture.project.id?fixture.runtime.workspace_id:item.publication.workspace_id,project:copy(project),canManage:true,canEdit:true,dirty:false,busy:false,active:false};
  let ordinal=0,key=0,handler;const stage=()=>item??fixture.stages[ordinal];
  const defaults=async(path,body)=>{if(path==='/api/connections/official-publishing')return copy(fixture.runtime);
    if(path.includes('/tiktok-creators/drafts?'))return copy(fixture.draft_page);if(path.includes('/publications?')&&!path.includes('/official-publications?'))return copy(fixture.dry_run_page);
    if(path.includes('/account-checks'))throw Error('TikTok must not load YouTube account checks');
    if(body){if(path.endsWith('/approve'))ordinal=1;else if(path.endsWith('/step')){ordinal++;return copy(stage().dispatch);}else if(path.endsWith('/poll'))ordinal++;return copy(stage().publication);}
    if(path.endsWith('/state'))return copy(stage().dispatch);if(path.includes('/official-publications?'))return page([copy(stage().publication)]);return copy(stage().publication);};handler=defaults;
  const api=async(path,body)=>{calls.push([path,copy(body)]);return handler(path,body);};
  const controller=initializeNativeOfficialPublications({api,getState:()=>state,root,onMessage:(...x)=>messages.push(x),uuid:()=>`explicit-tiktok-ui-key-${++key}`});
  return{controller,state,get,root,calls,messages,api,defaults,handler:v=>handler=v,ordinal:v=>ordinal=v};}
async function sources(h){await h.controller.readConfig();await h.controller.readSources();}
async function send(h,action){await h.controller.readState();h.get('send-ack').checked=true;h.controller.controls();await h.controller.execute(action);}

test('actual backend mock private public moderation multiple-ID and unknown-chunk DTOs validate',()=>{
  assert.equal(fixture.real_provider_calls,0);assert.equal(fixture.paid_operations,0);assert.equal(fixture.owner_uat,false);validateTikTokPublishingFactory(fixture.runtime.profiles[0],fixture.runtime.workspace_id);
  for(const s of[...fixture.stages,fixture.public_single.waiting,fixture.public_single.completed,fixture.public_multiple.waiting,fixture.public_multiple.completed,fixture.reconciliation]){
    validateTikTokPublication(s.publication,stateFor(s.publication));validateTikTokDispatch(s.dispatch,s.publication);}
  validateTikTokPublication(fixture.renewal.response,stateFor(fixture.renewal.response));validateTikTokDispatch(fixture.renewal.dispatch_after,fixture.renewal.response);
});
test('factory gates scope mock flags and private fields cannot create publishing authority',()=>{
  for(const change of[v=>v.gates.publish_enabled=1,v=>v.target.platform='youtube',v=>v.target.workspace_id='wsp_foreign',v=>v.mock='true',v=>v.external_actions_enabled=true,v=>v.execution_supported=false,v=>v.token='EXPLICIT_PRIVATE',v=>v.cipher_sha256=null,v=>v.credential_present=false]){
    const v=copy(fixture.runtime.profiles[0]);change(v);assert.throws(()=>validateTikTokPublishingFactory(v,fixture.runtime.workspace_id));}
});
test('publication keeps original draft target final metadata choices and honest completion labels',()=>{
  for(const change of[r=>r.project_id='f'.repeat(32),r=>r.snapshot.metadata.title='Changed',r=>r.snapshot.choices.disable_comment=false,r=>r.snapshot.final_sha256='f'.repeat(64),r=>r.snapshot.target.target_account_id='FOREIGN',r=>r.snapshot.creator_draft.snapshot.source.final_bytes++,r=>r.snapshot.credential_cipher_sha256='f'.repeat(64),r=>r.published=true,r=>r.receipt.remote_post_id=r.receipt.provider_job_id,r=>r.snapshot.upload_url='EXPLICIT_PRIVATE']){
    const r=copy(fixture.stages.at(-1).publication);change(r);assert.throws(()=>validateTikTokPublication(r,stateFor(fixture.stages.at(-1).publication)));}
  const r=copy(fixture.renewal.response);r.renewal.publication_id='nopu_'+'f'.repeat(32);assert.throws(()=>validateTikTokPublication(r,stateFor(r)));
});
test('dispatch binds original job observation IDs receipt nullability and exact byte bounds',()=>{
  const r=fixture.stages.at(-1).publication;
  for(const change of[v=>v.provider_job.provider_job_id='FORGED',v=>v.provider_job.session_ref='nups_'+'f'.repeat(32),v=>v.dispatch.acknowledged_bytes++,v=>v.processing_observations[0].uploaded_bytes='59',v=>v.processing_observations[0].external_call=true,v=>v.receipt.provider_job_id='FORGED',v=>v.processing_observations.at(-1).public_post_ids=['123'],v=>v.provider_job.upload_url='EXPLICIT_PRIVATE',v=>v.provider_job.expires_at=v.provider_job.created_at]){
    const v=copy(fixture.stages.at(-1).dispatch);change(v);assert.throws(()=>validateTikTokDispatch(v,r));}
  const multi=copy(fixture.public_multiple.completed.publication);multi.receipt.remote_post_id=multi.receipt.public_post_ids[0];assert.throws(()=>validateTikTokPublication(multi,stateFor(multi)));
});
test('initialization and reading TikTok sources make no sends or YouTube account reads',async()=>{
  const h=harness();assert.equal(h.calls.length,0);await sources(h);assert.equal(h.calls.length,3);assert.ok(h.calls.some(([p])=>p.includes('/tiktok-creators/drafts')));
  assert.equal(h.calls.some(([p])=>p.includes('/account-checks')),false);assert.equal(h.get('create').disabled,false);assert.equal(h.get('scheduled').disabled,true);assert.equal(h.calls.some(([,body])=>body),false);
});
test('create freezes tagged reviewed draft dry-run and factory without metadata overrides or approval',async()=>{
  const h=harness();await sources(h);await h.controller.execute('create');const body=h.calls.at(-1)[1],s=fixture.stages[0].publication.snapshot;
  assert.deepEqual(body,{...s.request,request_key:'explicit-tiktok-ui-key-1'});assert.equal(Object.hasOwn(body,'metadata'),false);assert.equal(Object.hasOwn(body,'account_check_id'),false);assert.equal(h.get('approve').disabled,true);assert.equal(h.get('step').disabled,true);
});
test('actual private stages require separate grant state reads and acknowledgement at every send',async()=>{
  const h=harness();await sources(h);await h.controller.execute('create');let count=h.calls.length;await h.controller.execute('approve');assert.equal(h.calls.length,count);
  h.get('ack').checked=true;await h.controller.execute('approve');assert.equal(h.get('ack').checked,false);count=h.calls.length;await h.controller.execute('step');assert.equal(h.calls.length,count);
  for(const action of['step','step','poll','poll']){await send(h,action);assert.equal(h.get('send-ack').checked,false);assert.equal(h.get('poll').disabled,true);}
  const r=h.controller.currentBinding().publication;assert.equal(r.mock_publication_complete,true);assert.equal(r.published,false);assert.equal(r.receipt.remote_post_id,null);assert.match(h.get('status').textContent,/Chỉ mình tôi/);
  assert.equal(h.calls.filter(([p,b])=>b&&p.endsWith('/step')).length,2);assert.equal(h.calls.filter(([p,b])=>b&&p.endsWith('/poll')).length,2);
});
test('missing current draft configuration final or metadata never enables review creation',async()=>{
  for(const change of[v=>v.draft_page.items[0].snapshot.creator_check.snapshot.factory.configuration_sha256='f'.repeat(64),v=>v.dry_run_page.items[0].snapshot.request.metadata.title='Changed',v=>v.dry_run_page.items[0].snapshot.final_sha256='f'.repeat(64)]){
    const h=harness(),v=copy(fixture);change(v);h.handler(async(p,b)=>p.includes('/tiktok-creators/drafts')?v.draft_page:p.includes('/publications?')?v.dry_run_page:h.defaults(p,b));await sources(h);
    assert.equal(h.get('create').disabled,true);const count=h.calls.length;await h.controller.execute('create');assert.equal(h.calls.length,count);
  }
});
test('raw private page fields wrong cursors and wrong workspace fail before source selection',async()=>{
  for(const change of[v=>v.next_cursor='npub_'+'f'.repeat(32),v=>v.workspace_id='wsp_foreign',v=>v.token_returned=true,v=>v.items[0].upload_url='EXPLICIT_PRIVATE']){
    const h=harness(),v=copy(fixture.draft_page);change(v);h.handler(async(p,b)=>p.includes('/tiktok-creators/drafts')?v:h.defaults(p,b));await sources(h);assert.equal(h.get('create').disabled,true);assert.equal(h.controller.currentBinding().publication,null);
  }
});
test('default-off factory and vault can be reviewed but cannot create or grant a send',async()=>{
  for(const off of['factory','vault']){const h=harness(),config=copy(fixture.runtime);if(off==='vault')config.session_vault.status='NOT_CONFIGURED';else{config.profiles[0].status='NOT_CONFIGURED';config.profiles[0].gates.publish_enabled=false;}
    h.handler(async(p,b)=>p==='/api/connections/official-publishing'?config:h.defaults(p,b));await sources(h);assert.equal(h.get('create').disabled,true);const n=h.calls.length;await h.controller.execute('create');assert.equal(h.calls.length,n);}
});
test('viewer dirty busy active or archived state never creates a publication',async()=>{
  for(const change of[{canManage:false},{dirty:true},{busy:true},{active:true},{project:{...fixture.project,archived:true}}]){const h=harness();await sources(h);Object.assign(h.state,copy(change));h.controller.controls();const n=h.calls.length;await h.controller.execute('create');assert.equal(h.calls.length,n);assert.equal(h.get('create').disabled,true);}
});
test('public moderation and multiple actual IDs remain distinct from private completion',async()=>{
  for(const item of[fixture.public_single.waiting,fixture.public_multiple.completed]){const project={...fixture.project,id:item.publication.project_id,revision:item.publication.snapshot.project_revision},h=harness({item,project});await h.controller.readHistory();await h.controller.readState();
    assert.equal(h.controller.currentBinding().publication.published,false);if(item===fixture.public_single.waiting)assert.equal(h.controller.currentBinding().publication.receipt,null);else{assert.match(h.get('status').textContent,/1234567890123456789, 2234567890123456789/);assert.equal(h.controller.currentBinding().publication.receipt.remote_post_id,null);}}
});
test('uploaded original job survives local revision edits while new-byte actions remain blocked',async()=>{
  const h=harness();h.ordinal(3);await h.controller.readHistory();await h.controller.readState();h.state.project.revision++;h.state.dirty=true;h.controller.sync();
  assert.equal(h.controller.currentBinding().publication.publication_id,fixture.stages[3].publication.publication_id);assert.match(h.get('status').textContent,/job gốc/);h.get('send-ack').checked=true;h.controller.controls();assert.equal(h.get('poll').disabled,false);assert.equal(h.get('step').disabled,true);
  let n=h.calls.length;await h.controller.execute('step');assert.equal(h.calls.length,n);await h.controller.execute('poll');assert.equal(h.calls.length,n+1);assert.equal(h.calls.at(-1)[1].expected_dispatch_version,fixture.stages[3].dispatch.dispatch.version);
});
test('original-job renewal uses actual signed HTTP renewal DTO after timeline edits',async()=>{
  const f=fixture.renewal,h=harness({item:f.before,project:f.project_after});h.handler(async(p,b)=>b&&p.endsWith('/renew')?copy(f.response):h.defaults(p,b));await h.controller.readHistory();await h.controller.readState();h.state.dirty=true;h.get('ack').checked=true;h.controller.controls();assert.equal(h.get('renew').disabled,false);await h.controller.execute('renew');
  assert.equal(h.calls.at(-1)[1].expected_dispatch_version,f.before.dispatch.dispatch.version);assert.equal(h.controller.currentBinding().publication.approval_id,f.response.approval_id);assert.equal(h.get('ack').checked,false);assert.equal(h.controller.currentBinding().dispatch,null);
});
test('unknown chunks after edits expose reconcile on original job rather than a new init or poll',async()=>{
  const item=fixture.reconciliation,h=harness({item,project:{...fixture.project,id:item.publication.project_id,revision:item.publication.snapshot.project_revision+1}});await h.controller.readHistory();await h.controller.readState();h.get('send-ack').checked=true;h.controller.controls();assert.equal(h.get('step').disabled,false);assert.equal(h.get('poll').disabled,true);
  const n=h.calls.length;await h.controller.execute('poll');assert.equal(h.calls.length,n);assert.match(h.get('detail').textContent,/reconciliation_required/);
});
test('uncertain create preserves exact idempotency key and unsupported schedule cannot override draft',async()=>{
  const h=harness();await sources(h);h.get('scheduled').value='2035-01-01T12:00';let n=h.calls.length;await h.controller.execute('create');assert.equal(h.calls.length,n);h.get('scheduled').value='';let attempts=0;
  h.handler(async(p,b)=>{if(b&&!attempts++)throw Error('Explicit lost response');return h.defaults(p,b);});await h.controller.execute('create');await h.controller.execute('create');assert.equal(h.calls.at(-1)[1].request_key,h.calls.at(-2)[1].request_key);
});
test('profile changes invalidate old draft cursors acknowledgements and late source responses',async()=>{
  const h=harness();await h.controller.readConfig();let release;h.handler(p=>p.includes('/tiktok-creators/drafts')?new Promise(r=>release=r):h.defaults(p));const pending=h.controller.readSources();await new Promise(r=>setImmediate(r));h.get('profile').value='missing';h.get('profile').listeners.change();release(copy(fixture.draft_page));await pending;assert.equal(h.get('account').value,'');assert.equal(h.get('create').disabled,true);
});
test('rereading configuration discards prior source choices until fresh scoped source pages are read',async()=>{
  const h=harness();await sources(h);assert.equal(h.get('create').disabled,false);await h.controller.readConfig();assert.equal(h.get('account').value,'');assert.equal(h.get('dry-run').value,'');assert.equal(h.get('create').disabled,true);
  await h.controller.readSources();assert.equal(h.get('create').disabled,false);
});
test('exact reviewed TikTok draft creates only a dry run without trusting edited form metadata',()=>{
  const state={workspace_id:fixture.runtime.workspace_id,project:fixture.project,canEdit:true,dirty:false,busy:false},draft=fixture.draft_page.items[0],body=nativeTikTokDryRunIntent(state,draft,'explicit-draft-dry-run-key');
  assert.equal(body.mode,'dry_run');assert.equal(body.platform,'tiktok');assert.deepEqual(body.metadata,draft.snapshot.request.metadata);assert.equal(body.final_job_id,draft.snapshot.request.final_job_id);
  for(const change of[{dirty:true},{canEdit:false},{project:{...fixture.project,revision:fixture.project.revision+1}}])assert.throws(()=>nativeTikTokDryRunIntent({...state,...change},draft,'explicit-draft-dry-run-key'));
});
test('draft handoff in actual dry-run controller still needs explicit review and sends no live request',async()=>{
  const root=dom(),state={workspace_id:fixture.runtime.workspace_id,project:copy(fixture.project),canManage:true,canEdit:true,dirty:false,busy:false},calls=[],draft=fixture.draft_page.items[0];
  const c=initializeNativePublications({root,getState:()=>state,getTikTokDraft:()=>draft,uuid:()=> 'explicit-draft-controller-key',api:async(p,b)=>{calls.push([p,b]);return fixture.dry_run_page.items[0];}});
  assert.equal(calls.length,0);assert.equal(root.getElementById('native-publish-tiktok-draft').disabled,false);await c.execute('create-tiktok');assert.equal(calls.length,1);assert.deepEqual(calls[0][1].metadata,draft.snapshot.request.metadata);assert.ok(calls[0][0].endsWith('/publications'));assert.equal(root.getElementById('native-publish-ack').checked,false);
});
test('TikTok receipts reject YouTube date-report bindings before analytics or refresh dispatch',async()=>{
  for(const[k,initialize]of[['analytics',initializeNativeOfficialAnalytics],['refresh',initializeNativeOfficialRefresh]]){const root=dom(),calls=[],messages=[],item=fixture.stages.at(-1).publication,state={workspace_id:item.workspace_id,project:fixture.project,canManage:true,dirty:false,busy:false,active:false};
    const c=initialize({root,getState:()=>state,getBinding:()=>({publication:item}),onMessage:(...v)=>messages.push(v),api:async(...args)=>{calls.push(args);return {schema_version:'native-official-analytics-publication-binding-v1',target:{platform:'youtube'}};}});
    assert.equal(root.getElementById('native-official-'+k+'-source').disabled,false);await c.readSource();assert.equal(calls.length,1);assert.equal(messages.length,1);
    assert.equal(root.getElementById('native-official-'+k+'-create').disabled,true);await (k==='analytics'?c.createRead():c.createPlan());assert.equal(calls.length,1);assert.ok(calls.every(([,body])=>!body));
  }
});
test('mixed TikTok and legacy YouTube configuration history and source choices preserve both routes',async()=>{
  // Explicit thin legacy UI fixture; TikTok rows remain the actual backend DTOs above.
  const h=harness(),tt=fixture.stages[0].publication,sha=tt.snapshot_sha256,target={...tt.snapshot.target,platform:'youtube',provider_key:'youtube-data-api-publishing',profile_id:'ppf_youtube_ui_fixture',target_account_id:'UC_EXPLICIT_UI_FIXTURE'};
  const yy={schema_version:'native-official-publishing-factory-v1',target,configuration_sha256:sha,target_binding_sha256:sha,status:'CONFIGURED',mock:true,gates:{publish_enabled:true,external_execution_enabled:true,owner_gate_enabled:true},external_actions_enabled:false,credential_verified:false,token_returned:false,automatic_publishing:false};
  const row={schema_version:'native-official-publication-v1',publication_id:'nopu_'+'f'.repeat(32),workspace_id:tt.workspace_id,project_id:tt.project_id,snapshot_sha256:sha,request_fingerprint:sha,status:'awaiting_publish_approval',approval_id:null,mock:true,published:false,mock_publication_complete:false,token_returned:false,receipt:null,
    snapshot:{workspace_id:tt.workspace_id,project_id:tt.project_id,project_revision:tt.snapshot.project_revision,mock:true,final_sha256:sha,configuration_sha256:sha,target,metadata:{title:'Explicit legacy UI'},dry_run_receipt_is_publish_authority:false,account_check_is_publish_authority:false,separate_owner_publish_approval_required:true}};
  const config={...copy(fixture.runtime),profiles:[fixture.runtime.profiles[0],yy]},dry=copy(fixture.dry_run_page);dry.items[0].snapshot.request.platform='youtube';
  const account={schema_version:'native-official-account-check-v1',workspace_id:tt.workspace_id,project_id:tt.project_id,check_id:'nack_'+'f'.repeat(32),status:'succeeded',snapshot_sha256:sha,token_returned:false,publishing_enabled:false,snapshot:{project_revision:tt.snapshot.project_revision,mock:true,target},result:{account_match:true,read_only:true,mock:true,external_call:false}};
  h.handler(async(p,b)=>p==='/api/connections/official-publishing'?config:p.includes('/official-publications?')?page([tt,row]):p.includes('/account-checks?')?{schema_version:'native-official-account-check-page-v1',workspace_id:tt.workspace_id,project_id:tt.project_id,items:[account],next_cursor:null,token_returned:false}:p.includes('/publications?')?dry:h.defaults(p,b));
  await h.controller.readConfig();assert.equal(h.get('profile').children.length,2);await h.controller.readHistory();assert.equal(h.get('history').children.length,2);
  h.get('profile').value=target.profile_id;h.get('profile').listeners.change();await h.controller.readSources();assert.equal(h.get('create').disabled,false);assert.equal(h.get('scheduled').disabled,false);assert.equal(h.get('account').value,account.check_id);
});
