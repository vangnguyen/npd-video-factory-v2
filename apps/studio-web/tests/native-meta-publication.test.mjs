import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';
import {validateMetaPublishingFactory,validateMetaPublication,validateMetaDispatch,metaSourceMatches,metaOriginalJob} from '../native-meta-publication.mjs';
import {initializeNativeOfficialPublications} from '../native-official-publications.mjs';
import {initializeNativePublishingMedia,validatePublishingMediaFactory,validatePublishingMedia,validatePublishingMediaSelection} from '../native-publishing-media.mjs';
import {initializeNativeOfficialPublicationQueue} from '../native-official-publication-queue.mjs';
const fixture=JSON.parse(fs.readFileSync(new URL('./fixtures/native-meta-publication-v2.json',import.meta.url),'utf8')),copy=v=>structuredClone(v);
function dom(){const nodes=new Map();class Node{constructor(){this.children=[];this.value='';this.checked=false;this.dataset={};this.listeners={};}set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,v){this.listeners[k]=v;}}
  return{createElement:()=>new Node(),getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);}};}
function harness(platform){const f=fixture.platforms[platform],root=dom(),state={workspace_id:f.runtime.workspace_id,project:copy(f.project),canManage:true,dirty:false,busy:false,active:false},calls=[],messages=[];
  let index=-1,approved=false,created=false,delivered=false,handler,media=null;const row=()=>index>=0?f.stages[index].publication:approved?f.approved:f.created;
  const dispatch=()=>index>=0?f.stages[index].dispatch:f.prepared;
  const defaults=async(path,body)=>{if(path==='/api/connections/official-publishing')return copy(f.runtime);if(path==='/api/connections/publishing-media')return copy(f.media_runtime);
    if(path.includes('/account-checks?'))return copy(f.account_page);if(path.includes('/publications?')&&!path.includes('/official-publications?'))return copy(f.dry_run_page);
    if(path.includes('/media-deliveries?'))return{schema_version:'native-publishing-media-delivery-page-v1',workspace_id:state.workspace_id,project_id:f.project.id,publication_id:f.approved.publication_id,items:[copy(delivered?f.media:f.created_media)].map(r=>{delete r.idempotent_replay;return r;}),next_cursor:null,truncated:false,url_returned:false,publishing_authority:false};
    if(body){if(path.endsWith('/media-deliveries'))return copy(f.created_media);if(path.endsWith('/process')){delivered=true;return copy(f.media);}if(path.endsWith('/media-selection'))return copy(f.binding);
      if(path.endsWith('/approve'))approved=true;else if(path.endsWith('/step')||path.endsWith('/poll')){index++;return copy(dispatch());}else if(path.endsWith('/official-publications'))created=true;return copy(row());}
    if(path.includes('/media-deliveries/'))return copy(delivered?f.media:f.created_media);if(path.endsWith('/state'))return copy(dispatch());
    if(path.includes('/official-publications?'))return{schema_version:'native-official-publication-page-v1',workspace_id:state.workspace_id,project_id:f.project.id,items:created?[copy(row())]:[],next_cursor:null,automatic_publishing:false,token_returned:false,session_uri_returned:false};return copy(row());};handler=defaults;
  const api=async(path,body)=>{calls.push([path,copy(body)]);return handler(path,body);};let key=0;
  const controller=initializeNativeOfficialPublications({api,getState:()=>state,root,uuid:()=>`explicit-meta-studio-key-${++key}`,onMessage:(...v)=>messages.push(v),getMediaSelection:()=>media?.currentSelection()??null,onSelection:()=>media?.sync()});
  media=initializeNativePublishingMedia({api,getState:()=>state,getBinding:()=>controller.currentBinding(),root,uuid:()=>`explicit-meta-media-key-${++key}`,onMessage:(...v)=>messages.push(v),onSelection:()=>controller.controls()});
  return{f,root,state,calls,messages,controller,media,api,defaults,get:n=>root.getElementById('native-official-publish-'+n),getMedia:n=>root.getElementById('native-publishing-media-'+n),handler:v=>handler=v,index:v=>{index=v;approved=created=true;},row};}
async function review(h){await h.controller.readConfig();await h.controller.readSources();await h.controller.execute('create');h.get('ack').checked=true;await h.controller.execute('approve');await h.controller.readState();}
async function disclosure(h){await h.media.readConfig();h.getMedia('ack').checked=true;await h.media.execute('create');await h.media.execute('process');h.getMedia('selection-ack').checked=true;await h.media.execute('select');}

test('actual legacy-v1 signed UI review remains readable and cannot dispatch or disclose media',async()=>{
  const r=fixture.legacy.publication,d=fixture.legacy.dispatch,state={workspace_id:r.workspace_id,project:{id:r.project_id,revision:r.snapshot.project_revision}};
  validateMetaPublication(r,state);validateMetaDispatch(d,r);assert.equal(metaOriginalJob(r,d),false);
  const h=harness('instagram_reels');h.state.project=state.project;h.handler(async path=>path.endsWith('/state')?copy(d):path.includes('/official-publications?')?{schema_version:'native-official-publication-page-v1',workspace_id:r.workspace_id,project_id:r.project_id,items:[copy(r)],next_cursor:null,automatic_publishing:false,token_returned:false,session_uri_returned:false}:copy(r));
  await h.controller.readHistory();await h.controller.readState();h.get('send-ack').checked=true;h.controller.controls();assert.equal(h.get('step').disabled,true);await h.controller.execute('step');assert.ok(h.calls.every(([,body])=>!body));assert.equal(h.root.getElementById('native-publishing-media-card').hidden,true);
});

for(const[platform,f]of Object.entries(fixture.platforms)){
  const state={workspace_id:f.runtime.workspace_id,project:f.project};
  test(platform+' actual retained backend factory, source, lifecycle and immutable media DTOs validate',()=>{
    assert.equal(fixture.real_provider_calls,0);assert.equal(fixture.owner_uat,false);validateMetaPublishingFactory(f.runtime.profiles[0],state.workspace_id);
    validateMetaPublication(f.created,state);validateMetaPublication(f.approved,state);validateMetaDispatch(f.prepared,f.approved);
    for(const s of f.stages){validateMetaPublication(s.publication,state);validateMetaDispatch(s.dispatch,s.publication);}
    assert.equal(metaSourceMatches(f.account_page.items[0],f.dry_run_page.items[0],f.runtime.profiles[0],state),true);
    validatePublishingMediaFactory(f.media_runtime,state.workspace_id);validatePublishingMedia(f.created_media,f.approved);validatePublishingMedia(f.media,f.approved);validatePublishingMediaSelection(f.binding,f.approved);
  });
  test(platform+' altered account, configuration, permission, media and provider facts fail closed',()=>{
    for(const mutate of [v=>v.target.workspace_id='foreign',v=>v.profile.page_id='999',v=>v.execution_supported=false,v=>v.media_configuration_sha256='wrong',v=>v.token='secret',v=>v.disclosures.provider_permissions_verified=true,v=>v.mock=false]){const v=copy(f.runtime.profiles[0]);mutate(v);assert.throws(()=>validateMetaPublishingFactory(v,state.workspace_id));}
    for(const mutate of [v=>v.snapshot.meta_account_proof.result_sha256='f'.repeat(64),v=>v.snapshot.meta_profile.page_id='999',v=>v.snapshot.request.expected_media_configuration_sha256='f'.repeat(64),v=>v.snapshot.meta_account_proof.snapshot.meta.cipher_sha256='f'.repeat(64),v=>v.snapshot.execution_supported=false,v=>v.published=true]){const v=copy(f.approved);mutate(v);assert.throws(()=>validateMetaPublication(v,state));}
    for(const mutate of [v=>v.provider_job.provider_job_id='98765',v=>v.processing_observations[0].data.outcome.provider_job_id='98765',v=>v.dispatch.total_bytes++,v=>v.provider_job.upload_url='private',v=>v.processing_observations[0].data.outcome.processing_progress=101]){const v=copy(f.stages.at(-1).dispatch);mutate(v);assert.throws(()=>validateMetaDispatch(v,f.stages.at(-1).publication));}
  });
  test(platform+' media scope, version, disclosure and exact binding mutations are rejected',()=>{
    for(const mutate of [v=>v.snapshot.scope.final_sha256='f'.repeat(64),v=>v.result.verified_object.scope.size_bytes++,v=>v.result.verified_object.version_id='',v=>v.result.verified_object.object_key='../foreign',v=>v.result.url='https://private.invalid/signed',v=>v.operations[0].response.credential_file='private-secret-file',v=>v.snapshot.request.acknowledged_external_media_delivery=false,v=>v.operations[0].delivery_id='nmd_'+'f'.repeat(32),v=>v.result.mock=false]){const v=copy(f.media);mutate(v);assert.throws(()=>validatePublishingMedia(v,f.approved));}
    const binding=copy(f.binding);binding.binding.request.media_delivery_id='nmd_'+'f'.repeat(32);assert.throws(()=>validatePublishingMediaSelection(binding,f.approved));
  });
  test(platform+' UI never auto-loads or sends and requires distinct publication/media/selection acknowledgements',async()=>{
    const h=harness(platform);assert.equal(h.calls.length,0);await h.controller.readConfig();await h.controller.readSources();assert.equal(h.get('scheduled').disabled,true);assert.equal(h.get('create').disabled,false);
    await h.controller.execute('create');await h.controller.execute('approve');assert.equal(h.calls.some(([p])=>p.endsWith('/approve')),false);h.get('ack').checked=true;await h.controller.execute('approve');await h.controller.readState();
    h.get('send-ack').checked=true;await h.controller.execute('step');assert.equal(h.calls.some(([p])=>p.endsWith('/step')),false);
    await h.media.readConfig();await h.media.execute('create');assert.equal(h.calls.some(([p])=>p.endsWith('/media-deliveries')),false);h.getMedia('ack').checked=true;await h.media.execute('create');assert.equal(h.getMedia('ack').checked,false);
    await h.media.execute('process');await h.media.execute('select');assert.equal(h.calls.some(([p])=>p.endsWith('/media-selection')),false);h.getMedia('selection-ack').checked=true;await h.media.execute('select');assert.ok(h.media.currentSelection());assert.equal(h.getMedia('selection-ack').checked,false);
    const request=h.calls.find(([p])=>p.endsWith('/official-publications'))[1];assert.equal(request.schema_version,'native-official-meta-publication-request-v2');assert.equal(request.expected_account_result_sha256,f.account_page.items[0].result_sha256);assert.equal(request.expected_media_configuration_sha256,f.media_runtime.configuration_sha256);
  });
  test(platform+' same shared controller completes original asynchronous job with honest mock receipt',async()=>{
    const h=harness(platform);await review(h);await disclosure(h);
    const actions=platform==='facebook'?['step','step','poll','step','poll']:['step','poll','step'];
    for(const action of actions){await h.controller.readState();h.get('send-ack').checked=true;h.controller.controls();assert.equal(h.get(action).disabled,false,JSON.stringify(h.messages));await h.controller.execute(action);assert.equal(h.get('send-ack').checked,false);}
    assert.equal(h.controller.currentBinding().publication.mock_publication_complete,true);assert.equal(h.controller.currentBinding().publication.published,false);assert.equal(h.messages.some(v=>v[1]),false,JSON.stringify(h.messages));
  });
  test(platform+' original processing job remains readable/finishable after edits, workspace change clears it',async()=>{
    const h=harness(platform),ordinal=platform==='facebook'?1:0;h.index(ordinal);await h.controller.readHistory();await h.controller.readState();assert.equal(metaOriginalJob(h.controller.currentBinding().publication,h.controller.currentBinding().dispatch),true);
    h.state.project.revision++;h.state.dirty=true;h.controller.sync();assert.ok(h.controller.currentBinding().publication);h.get('send-ack').checked=true;h.controller.controls();assert.equal(h.get('poll').disabled,false);
    await h.controller.execute('poll');assert.ok(h.calls.find(([p])=>p.endsWith('/poll')));h.state.workspace_id='foreign';h.controller.sync();assert.equal(h.controller.currentBinding().publication,null);
  });
  test(platform+' viewer, stale context and altered selection response cannot authorize work',async()=>{
    const h=harness(platform);h.state.canManage=false;await h.controller.readConfig();await h.media.readConfig();assert.equal(h.calls.length,0);h.state.canManage=true;await review(h);await disclosure(h);
    h.state.dirty=true;h.media.sync();assert.equal(h.media.currentSelection(),null);const count=h.calls.length;h.getMedia('selection-ack').checked=true;await h.media.execute('select');assert.equal(h.calls.length,count);
    h.state.dirty=false;h.media.sync();await h.media.readConfig();h.getMedia('ack').checked=true;await h.media.execute('create');await h.media.execute('process');h.getMedia('selection-ack').checked=true;
    h.handler(async(path,body)=>{if(path.endsWith('/media-selection')){const v=copy(f.binding);v.binding.request.expected_dispatch_version++;return v;}return h.defaults(path,body);});await h.media.execute('select');assert.equal(h.media.currentSelection(),null);
  });
  test(platform+' response arriving after project switch is discarded and cannot select media',async()=>{
    const h=harness(platform);await review(h);let release;const pending=new Promise(resolve=>release=resolve);h.handler(async(path,body)=>path==='/api/connections/publishing-media'?pending:h.defaults(path,body));
    const read=h.media.readConfig();h.state.project.id='f'.repeat(32);h.media.sync();release(copy(f.media_runtime));await read;assert.equal(h.getMedia('create').disabled,true);assert.equal(h.media.currentSelection(),null);
  });
  test(platform+' bounded queue retains original remote job after edit and still requires separate plan consent',async()=>{
    const h=harness(platform);h.index(platform==='facebook'?1:0);await h.controller.readHistory();await h.controller.readState();h.state.project.revision++;h.state.dirty=true;h.controller.sync();
    const queue=initializeNativeOfficialPublicationQueue({api:h.api,getState:()=>h.state,getBinding:()=>h.controller.currentBinding(),root:h.root});const runtime={schema_version:'native-official-publish-queue-runtime-v1',workspace_id:h.state.workspace_id,enabled:true,default_enabled:false,separate_owner_plan_approval_required:true,automatic_consent_renewal:false,remote_deletion_enabled:false,token_returned:false,session_uri_returned:false};
    h.handler(async(path,body)=>path==='/api/connections/official-publish-queue'?runtime:h.defaults(path,body));await queue.readConfig();const ack=h.root.getElementById('native-official-queue-ack');assert.equal(ack.disabled,false);assert.equal(h.root.getElementById('native-official-queue-create').disabled,true);ack.checked=true;queue.controls();assert.equal(h.root.getElementById('native-official-queue-create').disabled,false);
  });
}
