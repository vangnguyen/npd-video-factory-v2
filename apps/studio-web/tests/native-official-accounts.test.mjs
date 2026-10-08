import test from 'node:test';import assert from 'node:assert/strict';
import {initializeNativeOfficialAccounts} from '../native-official-accounts.mjs';
const id='a'.repeat(32),workspace='wsp_native_fixture',account='npac_'+'b'.repeat(32),check='nack_'+'c'.repeat(32),sha='d'.repeat(64);
const binding=()=>({account_ref:account,target:{workspace_id:workspace,platform:'youtube',target_account_id:'UC_<EXPLICIT>'},configuration_sha256:sha,target_binding_sha256:sha,
  status:'CONFIGURED',mode:'fixture',publishing_enabled:false,token_returned:false,account_verified:false,credential_verified:false,external_reads_enabled:false});
const row=()=>({schema_version:'native-official-account-check-v1',check_id:check,workspace_id:workspace,project_id:id,account_ref:account,status:'queued',request_fingerprint:sha,snapshot_sha256:sha,
  snapshot:{workspace_id:workspace,project_id:id,account_ref:account,project_revision:1,mock:true},result:null,publishing_enabled:false,token_returned:false});
function harness(){const nodes=new Map();class Node{constructor(){this.value='';this.checked=false;this.children=[];this.dataset={};this.listeners={};}
  set id(value){this._id=value;nodes.set(value,this);}get id(){return this._id;}append(...n){this.children.push(...n);}replaceChildren(){this.children=[];}addEventListener(name,fn){this.listeners[name]=fn;}}
  const root={createElement(){return new Node();},getElementById(value){if(!nodes.has(value))nodes.set(value,new Node());return nodes.get(value);}},get=name=>root.getElementById('native-account-'+name);
  const state={project:{id,revision:1},workspace_id:workspace,canManage:true,dirty:false,busy:false,active:false},calls=[],messages=[];let handler=async(path,body)=>body?row():path.includes('/connections/')?
    {schema_version:'native-official-accounts-v1',workspace_id:workspace,accounts:[binding()],publishing_enabled:false,token_returned:false}:
    {schema_version:'native-official-account-check-page-v1',workspace_id:workspace,project_id:id,items:[row()],next_cursor:null,publishing_enabled:false,token_returned:false};let key=0;
  const controller=initializeNativeOfficialAccounts({root,getState:()=>state,api:async(...args)=>{calls.push(args);return handler(...args);},onMessage:(...args)=>messages.push(args),uuid:()=> 'explicit-test-key-'+(++key)});
  return{state,calls,messages,root,get,controller,handler(value){handler=value;}};}
test('loads nothing automatically and one Owner click reads only public configuration',async()=>{const h=harness();assert.equal(h.calls.length,0);assert.equal(h.get('verify').disabled,true);
  await h.controller.readAccounts();assert.equal(h.calls.length,1);assert.equal(h.calls[0][1],undefined);assert.ok(h.get('select').children[0].textContent.includes('Mẫu kiểm tra'));
  assert.ok(h.get('select').children[0].textContent.includes('UC_<EXPLICIT>'));assert.equal(h.get('verify').disabled,true);});
test('explicit saved idle Owner intent sends no secret and starts no publishing action',async()=>{const h=harness();await h.controller.readAccounts();await h.controller.execute();assert.equal(h.calls.length,1);
  h.get('ack').checked=true;await h.controller.execute();assert.equal(h.calls.length,2);assert.equal(h.calls[1][0],`/api/projects/${id}/official-accounts/${account}/verify`);
  assert.deepEqual(h.calls[1][1],{revision:1,expected_configuration_sha256:sha,acknowledged_read_only:true,request_key:'explicit-test-key-1'});assert.equal(h.get('ack').checked,false);
  for(const flag of ['dirty','active','busy']){h.state[flag]=true;h.get('ack').checked=true;await h.controller.execute();assert.equal(h.calls.length,2);h.state[flag]=false;}
  h.state.project.archived=true;h.get('ack').checked=true;await h.controller.execute();assert.equal(h.calls.length,2);});
test('unknown outcome retains the same key on explicit retry, confirmed admission permits a fresh check',async()=>{const h=harness();await h.controller.readAccounts();let attempts=0;
  h.handler(async()=>{if(!attempts++)throw new Error('Explicit unknown result fixture');return row();});h.get('ack').checked=true;await h.controller.execute();
  h.get('ack').checked=true;await h.controller.execute();assert.equal(h.calls[1][1].request_key,h.calls[2][1].request_key);
  h.get('ack').checked=true;await h.controller.execute();assert.notEqual(h.calls[2][1].request_key,h.calls[3][1].request_key);});
test('viewer reads scoped history but cannot load protected connections or create work',async()=>{const h=harness();h.state.canManage=false;h.controller.sync();
  await h.controller.readAccounts();await h.controller.execute();assert.equal(h.calls.length,0);await h.controller.readHistory();assert.equal(h.calls.length,1);
  assert.equal(h.calls[0][0],`/api/projects/${id}/account-checks?limit=25`);assert.ok(h.get('history').children[0].textContent.startsWith('Mẫu kiểm tra'));assert.equal(h.get('verify').disabled,true);});
test('foreign workspace or publication-authority claims cannot populate the controls',async()=>{const h=harness();h.handler(async()=>({schema_version:'native-official-accounts-v1',workspace_id:workspace,
  accounts:[{...binding(),publishing_enabled:true}],publishing_enabled:false,token_returned:false}));await h.controller.readAccounts();assert.equal(h.get('select').children.length,0);
  h.handler(async()=>({schema_version:'native-official-account-check-page-v1',workspace_id:'wsp_foreign',project_id:id,items:[row()],next_cursor:null,publishing_enabled:false,token_returned:false}));
  await h.controller.readHistory();assert.equal(h.get('history').children.length,0);assert.equal(h.messages.length,2);});
test('late account configuration cannot cross workspace/project/role state changes',async()=>{const h=harness();let release;h.handler(()=>new Promise(resolve=>{release=resolve;}));
  const pending=h.controller.readAccounts();h.state.workspace_id='wsp_foreign';h.controller.sync();release({schema_version:'native-official-accounts-v1',workspace_id:workspace,
    accounts:[binding()],publishing_enabled:false,token_returned:false});await pending;assert.equal(h.get('select').children.length,0);assert.equal(h.messages.length,0);});
