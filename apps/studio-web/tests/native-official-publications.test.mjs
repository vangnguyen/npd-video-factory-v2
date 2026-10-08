import test from 'node:test';import assert from 'node:assert/strict';
import {initializeNativeOfficialPublications} from '../native-official-publications.mjs';
const id='a'.repeat(32),workspace='wsp_native_fixture',pub='nopu_'+'b'.repeat(32),dry='npub_'+'c'.repeat(32),check='nack_'+'d'.repeat(32),sha='e'.repeat(64);
const target=()=>({workspace_id:workspace,profile_id:'ppf_explicit_fixture',profile_version:1,platform:'youtube',provider_key:'youtube-data-api-publishing',target_account_id:'UC_<EXPLICIT>',credential_binding_sha256:sha});
const profile=()=>({schema_version:'native-official-publishing-factory-v1',target:target(),configuration_sha256:sha,target_binding_sha256:sha,status:'CONFIGURED',mock:true,
  gates:{publish_enabled:true,external_execution_enabled:true,owner_gate_enabled:true},external_actions_enabled:false,credential_verified:false,token_returned:false,automatic_publishing:false});
const configuration=()=>({schema_version:'native-official-publishing-factories-v1',workspace_id:workspace,profiles:[profile()],automatic_publishing:false,token_returned:false,separate_owner_publish_approval_required:true,
  session_vault:{schema_version:'native-official-session-vault-v1',workspace_id:workspace,status:'CONFIGURED',session_uri_returned:false,oauth_token_stored:false}});
const dryRow=()=>({schema_version:'native-publication-v1',workspace_id:workspace,project_id:id,publication_id:dry,status:'dry_run_succeeded',snapshot_sha256:sha,request_fingerprint:sha,mock:true,external_action:false,publish_enabled:false,
  receipt:{mode:'dry_run',mock:true,external_action:false,provider_key:'mock-publishing',request_fingerprint:sha,remote_post_id:null,remote_url:null},
  snapshot:{request:{revision:1,platform:'youtube',mode:'dry_run',metadata:{title:'<img src=x onerror=unsafe()> fixture',privacy:'private'}}}});
const accountRow=()=>({schema_version:'native-official-account-check-v1',workspace_id:workspace,project_id:id,check_id:check,status:'succeeded',snapshot_sha256:sha,token_returned:false,publishing_enabled:false,
  snapshot:{project_revision:1,mock:true,target:target()},result:{account_match:true,read_only:true,mock:true,external_call:false}});
const row=(status='awaiting_publish_approval')=>({schema_version:'native-official-publication-v1',publication_id:pub,workspace_id:workspace,project_id:id,snapshot_sha256:sha,request_fingerprint:sha,status,approval_id:null,
  mock:true,published:false,mock_publication_complete:false,token_returned:false,receipt:null,
  snapshot:{workspace_id:workspace,project_id:id,project_revision:1,mock:true,final_sha256:sha,configuration_sha256:sha,target:target(),metadata:{title:'<script>unsafe()</script>'},
    dry_run_receipt_is_publish_authority:false,account_check_is_publish_authority:false,separate_owner_publish_approval_required:true}});
const dispatch=(r,phase='prepared',version=1)=>({schema_version:'native-official-publish-dispatch-v1',publication_id:pub,workspace_id:workspace,project_id:id,snapshot_sha256:sha,mock:r.mock,published:r.published,
  mock_publication_complete:r.mock_publication_complete,receipt:r.receipt,token_returned:false,session_uri_returned:false,retry_not_before:null,
  dispatch:{phase,version,total_bytes:100,acknowledged_bytes:0,private_session_ref:null,remote_post_id:null,failure_code:null}});
const page=items=>({schema_version:'native-official-publication-page-v1',workspace_id:workspace,project_id:id,items,next_cursor:null,automatic_publishing:false,token_returned:false,session_uri_returned:false});
function harness(){const nodes=new Map();class Node{constructor(){this.children=[];this.value='';this.checked=false;this.dataset={};this.listeners={};}
  set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}append(...n){this.children.push(...n);}replaceChildren(...n){this.children=[...n];}addEventListener(k,fn){this.listeners[k]=fn;}}
  const root={createElement:()=>new Node(),getElementById(v){if(!nodes.has(v))nodes.set(v,new Node());return nodes.get(v);}},get=name=>root.getElementById('native-official-publish-'+name),
    state={workspace_id:workspace,project:{id,revision:1},canManage:true,dirty:false,busy:false,active:false},calls=[],messages=[],working=[];let current=row(),phase='prepared',version=1,key=0,handler;
  const defaultHandler=async(path,body)=>{if(path.includes('/connections/'))return configuration();
    if(path.includes('/account-checks'))return{schema_version:'native-official-account-check-page-v1',workspace_id:workspace,project_id:id,items:[accountRow()],next_cursor:null,token_returned:false};
    if(path.includes('/publications?'))return{schema_version:'native-publication-page-v1',workspace_id:workspace,project_id:id,items:[dryRow()],next_cursor:null};
    if(body){if(path.endsWith('/approve')||path.endsWith('/renew'))current={...row('queued'),approval_id:'nopa_'+'f'.repeat(32)};
      else if(path.endsWith('/cancel'))current=row('cancelled');else if(path.endsWith('/step')){version++;phase='uploading';return dispatch(current,phase,version);}return current;}
    if(path.endsWith('/state'))return dispatch(current,phase,version);if(path.includes('/official-publications?'))return page([current]);return current;};handler=defaultHandler;
  const controller=initializeNativeOfficialPublications({root,getState:()=>({...state}),api:async(...args)=>{calls.push(args);return handler(...args);},uuid:()=> 'explicit-request-key-'+(++key),onMessage:(...v)=>messages.push(v),onWorking:value=>{working.push(value);state.busy=value;}});
  return{controller,state,calls,messages,get,nodes,working,handler(fn){handler=fn;},defaultHandler,current(r){current=r;},phase(value){phase=value;}};}
async function create(h){await h.controller.readConfig();await h.controller.readSources();await h.controller.execute('create');}
async function queued(h){await create(h);h.get('ack').checked=true;await h.controller.execute('approve');await h.controller.readState();}
test('initialization makes no request and explicit configuration exposes only labelled bindings',async()=>{const h=harness();assert.equal(h.calls.length,0);assert.equal(h.get('create').disabled,true);await h.controller.readConfig();
  assert.deepEqual(h.calls,[['/api/connections/official-publishing']]);assert.match(h.get('profile').children[0].textContent,/Mô phỏng/);assert.match(h.get('profile').children[0].textContent,/UC_<EXPLICIT>/);
  assert.equal(h.get('create').disabled,true);assert.deepEqual(h.working,[true,false]);assert.equal(h.state.busy,false);});
test('review creation freezes selected current dry run and account proof without granting approval',async()=>{const h=harness();await create(h);const [path,body]=h.calls.at(-1);assert.equal(path,`/api/projects/${id}/official-publications`);
  assert.deepEqual(body,{revision:1,dry_run_publication_id:dry,expected_dry_run_snapshot_sha256:sha,account_check_id:check,profile_id:'ppf_explicit_fixture',expected_configuration_sha256:sha,request_key:'explicit-request-key-1'});
  assert.match(h.get('history').children[0].textContent,/<script>unsafe\(\)<\/script>/);assert.equal(h.get('step').disabled,true);assert.equal(h.get('approve').disabled,true);
  assert.equal(h.get('dry-run').children[0].textContent,'<img src=x onerror=unsafe()> fixture');assert.equal(h.get('history').children[0].innerHTML,undefined);});
test('separate approval never sends and each explicit step needs fresh saved state and acknowledgement',async()=>{const h=harness();await create(h);const before=h.calls.length;await h.controller.execute('approve');assert.equal(h.calls.length,before);
  h.get('ack').checked=true;await h.controller.execute('approve');assert.equal(h.calls.length,before+1);assert.equal(h.calls.at(-1)[0].endsWith('/approve'),true);assert.equal(h.get('ack').checked,false);
  await h.controller.execute('step');assert.equal(h.calls.length,before+1);await h.controller.readState();h.get('send-ack').checked=true;h.controller.controls();assert.equal(h.get('step').disabled,false);
  await h.controller.execute('step');assert.equal(h.calls.at(-2)[0].endsWith('/step'),true);assert.deepEqual(h.calls.at(-2)[1],{expected_snapshot_sha256:sha,expected_dispatch_version:1});
  assert.equal(h.get('send-ack').checked,false);assert.equal(h.get('step').disabled,true);const count=h.calls.length;await h.controller.execute('step');assert.equal(h.calls.length,count);});
test('unknown review outcome retains exact idempotency key and unknown upload requires state read',async()=>{const h=harness();await h.controller.readConfig();await h.controller.readSources();let attempts=0;
  h.handler(async(path,body)=>{if(body&&!attempts++)throw new Error('Explicit uncertain response');return h.defaultHandler(path,body);});await h.controller.execute('create');await h.controller.execute('create');
  assert.equal(h.calls.at(-2)[1].request_key,h.calls.at(-1)[1].request_key);await h.controller.execute('create');assert.notEqual(h.calls.at(-2)[1].request_key,h.calls.at(-1)[1].request_key);
  await h.controller.readState();h.current(row('queued'));await h.controller.readState();h.get('send-ack').checked=true;h.handler(async()=>{throw new Error('Explicit uncertain upload');});await h.controller.execute('step');
  const count=h.calls.length;h.get('send-ack').checked=true;await h.controller.execute('step');assert.equal(h.calls.length,count);assert.equal(h.get('step').disabled,true);});
test('viewer can read scoped history but cannot load connections or grant any provider action',async()=>{const h=harness();h.state.canManage=false;h.controller.sync();await h.controller.readConfig();await h.controller.readSources();await h.controller.execute('create');
  assert.equal(h.calls.length,0);await h.controller.readHistory();assert.equal(h.calls.length,1);await h.controller.readState();assert.equal(h.calls.length,3);h.get('ack').checked=true;h.get('send-ack').checked=true;
  for(const action of ['approve','renew','cancel','step','poll'])await h.controller.execute(action);assert.equal(h.calls.length,3);assert.equal(h.get('approve').disabled,true);});
test('saved idle project guards and authoritative target filtering reject stale or foreign sources',async()=>{const h=harness();await h.controller.readConfig();h.handler(async(path)=>path.includes('/account-checks')?
  {schema_version:'native-official-account-check-page-v1',workspace_id:workspace,project_id:id,items:[{...accountRow(),snapshot:{...accountRow().snapshot,target:{...target(),target_account_id:'FOREIGN'}}}],next_cursor:null,token_returned:false}:
  {schema_version:'native-publication-page-v1',workspace_id:workspace,project_id:id,items:[{...dryRow(),snapshot:{request:{...dryRow().snapshot.request,revision:2}}}],next_cursor:null});
  await h.controller.readSources();assert.equal(h.get('account').children.length,0);assert.equal(h.get('dry-run').children.length,0);await h.controller.execute('create');assert.equal(h.calls.length,3);
  h.handler(h.defaultHandler);await h.controller.readSources();for(const flag of ['dirty','busy','active']){h.state[flag]=true;const count=h.calls.length;await h.controller.execute('create');assert.equal(h.calls.length,count);h.state[flag]=false;}
  h.state.project.archived=true;const count=h.calls.length;await h.controller.execute('create');assert.equal(h.calls.length,count);});
test('foreign configuration, corrupted dispatch and relabelled mock receipt are rejected',async()=>{const h=harness();h.handler(async()=>({...configuration(),workspace_id:'wsp_foreign'}));await h.controller.readConfig();assert.equal(h.get('profile').children.length,0);
  h.handler(h.defaultHandler);await queued(h);h.handler(async path=>path.endsWith('/state')?{...dispatch(row('queued')),session_uri_returned:true}:row('queued'));await h.controller.readState();assert.match(h.messages.at(-1)[0],/khớp/);
  const bad={...row('completed'),published:true,mock_publication_complete:false,receipt:{mock:false,external_action:true}};h.handler(async()=>page([bad]));await h.controller.readHistory();assert.match(h.messages.at(-1)[0],/trạng thái/);
  assert.equal(h.get('step').disabled,true);});
test('late response cannot cross project workspace revision or role changes and busy ends once',async()=>{for(const change of [s=>s.project={id:'f'.repeat(32),revision:1},s=>s.workspace_id='wsp_foreign',s=>s.project.revision=2,s=>s.canManage=false]){
  const h=harness();let release;h.handler(()=>new Promise(resolve=>{release=resolve;}));const pending=h.controller.readConfig();assert.equal(h.controller.isWorking(),true);
  change(h.state);h.controller.sync();release(configuration());await pending;assert.equal(h.get('profile').children.length,0);assert.equal(h.messages.length,0);assert.equal(h.state.busy,false);assert.deepEqual(h.working,[true,false]);}});
test('durable backoff prevents repeated step and poll and uploaded processing remains distinct',async()=>{const h=harness();await queued(h);const r=row('queued');h.phase('uploaded');await h.controller.readState();h.get('send-ack').checked=true;h.controller.controls();
  assert.equal(h.get('step').disabled,true);assert.equal(h.get('poll').disabled,false);const count=h.calls.length;await h.controller.execute('step');assert.equal(h.calls.length,count);
  h.handler(async path=>path.endsWith('/state')?{...dispatch(r,'uploaded'),retry_not_before:new Date(Date.now()+60000).toISOString()}:r);await h.controller.readState();h.get('send-ack').checked=true;
  await h.controller.execute('poll');assert.equal(h.calls.length,count+2);assert.equal(h.get('poll').disabled,true);});
test('confirmed mock receipt keeps real published false and reads do not perform writes',async()=>{const h=harness();const r={...row('completed'),mock_publication_complete:true,
  receipt:{mode:'live',platform:'youtube',provider_key:'youtube-data-api-publishing',request_fingerprint:sha,mock:true,external_action:false,remote_post_id:'FIXTURE0001',remote_url:null}};
  h.current(r);await h.controller.readHistory();await h.controller.readState();assert.match(h.get('status').textContent,/chưa được đăng thật/);assert.equal(h.get('step').disabled,true);assert.equal(h.get('approve').disabled,true);
  assert.ok(h.calls.every(([,body])=>body===undefined));assert.equal(h.get('history').children[0].innerHTML,undefined);});
test('explicit local schedule normalizes to UTC and leaves ordinary request fields unchanged',async()=>{const h=harness();await h.controller.readConfig();await h.controller.readSources();
  const date=new Date(Date.now()+3600000),pad=v=>String(v).padStart(2,'0'),local=`${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  h.get('scheduled').value=local;await h.controller.execute('create');const body=h.calls.at(-1)[1];assert.equal(body.metadata.scheduled_at,new Date(local).toISOString());assert.equal(body.metadata.privacy,'private');assert.equal(body.dry_run_publication_id,dry);
  assert.equal(h.calls.filter(([,body])=>body).length,1);assert.equal(h.get('step').disabled,true);});
test('past malformed or nonprivate schedules do not create requests and scope resets draft time',async()=>{const h=harness();await h.controller.readConfig();await h.controller.readSources();const count=h.calls.length;
  for(const value of ['2020-01-01T12:00:00','not-a-date','2030-01-01T12:00:00Z']){h.get('scheduled').value=value;await h.controller.execute('create');assert.equal(h.calls.length,count);}
  h.handler(async(path,body)=>path.includes('/publications?')?{schema_version:'native-publication-page-v1',workspace_id:workspace,project_id:id,items:[{...dryRow(),snapshot:{request:{...dryRow().snapshot.request,metadata:{...dryRow().snapshot.request.metadata,privacy:'public'}}}}],next_cursor:null}:h.defaultHandler(path,body));
  await h.controller.readSources();h.get('scheduled').value='2030-01-01T12:00:00';const before=h.calls.length;await h.controller.execute('create');assert.equal(h.calls.length,before);
  h.state.project.revision=2;h.controller.sync();assert.equal(h.get('scheduled').value,'');assert.equal(h.get('create').disabled,true);});
