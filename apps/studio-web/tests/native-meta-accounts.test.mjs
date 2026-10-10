// Backend-derived public DTOs from actual local HTTP/DPAPI/SQLite with explicit platform/Owner mocks.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {initializeNativeOfficialAccounts,validateMetaAccount,validateMetaAccountRow} from '../native-official-accounts.mjs';
const fixture=JSON.parse(readFileSync(new URL('./fixtures/native-meta-account-v1.json',import.meta.url),'utf8'));
const copy=v=>structuredClone(v),scope=()=>({workspace_id:fixture.workspace_id,project:copy(fixture.project)});

function harness(canManage=true){
  const nodes=[];class Node{constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.events={};this.checked=false;this.value='';nodes.push(this);}
    append(...v){this.children.push(...v);}replaceChildren(...v){this.children=[...v];}addEventListener(k,f){this.events[k]=f;}}
  const card=new Node('details');card.id='native-official-accounts-card';const root={createElement:tag=>new Node(tag),getElementById:id=>nodes.find(x=>x.id===id)};
  const state={...scope(),canManage,busy:false,dirty:false,active:false},calls=[],messages=[];let handler;
  const api=async(path,body)=>{calls.push({path,body});if(handler)return handler(path,body);
    if(path==='/api/connections/official-accounts')return copy(fixture.states);
    if(path.includes('/verify'))return copy(fixture.queued.find(x=>path.includes(x.account_ref)));
    return{schema_version:'native-official-account-check-page-v1',workspace_id:state.workspace_id,project_id:state.project.id,
      items:copy(fixture.rows),next_cursor:null,publishing_enabled:false,token_returned:false};};
  const ui=initializeNativeOfficialAccounts({api,getState:()=>state,root,onMessage:(...v)=>messages.push(v),uuid:()=> 'explicit-meta-studio-request-key'});
  return{state,calls,messages,ui,get:id=>root.getElementById('native-account-'+id),handler:v=>{handler=v;}};
}

test('actual Meta Page and linked Instagram DTOs retain distinct readonly costs and explicit unverified permissions',()=>{
  assert.equal(fixture.explicit_mocks,true);assert.equal(fixture.provider_owner_browser_acceptance,false);
  for(const a of fixture.states.accounts){assert.equal(validateMetaAccount(a,scope()),a);assert.equal(a.publishing_enabled,false);assert.equal(a.provider_permissions_verified,false);}
  for(const r of [...fixture.queued,...fixture.rows])assert.equal(validateMetaAccountRow(r,scope()),r);
  const ig=fixture.rows.find(r=>r.snapshot.target.platform==='instagram_reels'),fb=fixture.rows.find(r=>r.snapshot.target.platform==='facebook');
  assert.equal(ig.result.meta.observations.length,2);assert.equal(fb.result.meta.observations.length,1);assert.equal(fb.result.meta.linked_instagram_match,null);
});

test('Meta public factories reject app/permission/publish promotion, foreign Page and raw private fields',()=>{
  const original=fixture.states.accounts.find(a=>a.target.platform==='facebook');
  for(const mutate of [a=>a.provider_permissions_verified=true,a=>a.app_eligibility_verified=true,a=>a.publishing_enabled=true,
    a=>a.profile.page_id='99999',a=>a.profile.login_type='instagram_login',a=>a.cipher_sha256=null,a=>a.token_file='C:/private/token',a=>a.profile.access_token='never returned']){
    const a=copy(original);mutate(a);assert.throws(()=>validateMetaAccount(a,scope()));
  }
});

test('Meta proof rejects wrong link, missing observations, borrowed costs, foreign scope and claimed provider permissions',()=>{
  const original=fixture.rows.find(r=>r.snapshot.target.platform==='instagram_reels');
  for(const mutate of [r=>r.result.meta.linked_instagram_match=null,r=>r.result.meta.instagram_account_id='99999',
    r=>r.result.meta.observations.pop(),r=>r.result.meta.observations[0].cost_operation_id=r.result.meta.observations[1].cost_operation_id,
    r=>r.result.meta.provider_permissions_verified=true,r=>r.result.meta.provider_permissions_verified=0,r=>r.workspace_id='wsp_foreign',
    r=>r.result.meta.declared_permissions=['instagram_basic'],r=>r.result.meta.declared_permissions.push('unknown'),r=>r.result.meta.token='never accepted']){
    const r=copy(original);mutate(r);assert.throws(()=>validateMetaAccountRow(r,scope()));
  }
});

test('typed source keeps the exact fifteen minute interval and accepts harmless target key order',()=>{
  const row=copy(fixture.rows[0]);row.snapshot.meta.deadline=row.snapshot.meta.consented_at;assert.throws(()=>validateMetaAccountRow(row,scope()));
  const a=copy(fixture.states.accounts[0]);a.profile.target=Object.fromEntries(Object.entries(a.profile.target).reverse());assert.doesNotThrow(()=>validateMetaAccount(a,scope()));
});

test('Studio starts inert and admits only explicit saved Owner readonly Meta intents without private fields',async()=>{
  const h=harness();assert.equal(h.calls.length,0);await h.ui.readAccounts();assert.equal(h.get('select').children.length,2);
  assert.ok(h.get('select').children.some(n=>n.textContent.includes('instagram_reels')));await h.ui.execute();assert.equal(h.calls.length,1);const rejected=h.messages.filter(x=>x[1]===true).length;
  h.get('ack').checked=true;await h.ui.execute();assert.equal(h.calls.length,2);const intent=h.calls[1];
  assert.equal(intent.path,`/api/projects/${h.state.project.id}/official-accounts/${fixture.states.accounts[0].account_ref}/verify`);
  assert.deepEqual(Object.keys(intent.body).sort(),['acknowledged_read_only','expected_configuration_sha256','request_key','revision']);
  assert.equal(intent.body.acknowledged_read_only,true);assert.equal(h.get('ack').checked,false);assert.equal(h.messages.filter(x=>x[1]===true).length,rejected);
});

test('keyless viewer reads original Meta proof history without configuration reads or new provider work',async()=>{
  const h=harness(false);await h.ui.readAccounts();assert.equal(h.calls.length,0);await h.ui.readHistory();assert.equal(h.calls.length,1);
  assert.equal(h.get('history').children.length,2);assert.ok(h.get('detail').textContent.includes('"provider_permissions_verified": false'));
  h.get('ack').checked=true;await h.ui.execute();assert.equal(h.calls.length,1);assert.equal(h.get('verify').disabled,true);
});

test('permission relabeling and private fields never populate Meta history or configuration controls',async()=>{
  const h=harness();const states=copy(fixture.states);states.accounts[0].provider_permissions_verified=true;h.handler(async()=>states);
  await h.ui.readAccounts();assert.equal(h.get('select').children.length,0);const r=copy(fixture.rows[0]);r.result.meta.access_token='never returned';
  h.handler(async()=>({schema_version:'native-official-account-check-page-v1',workspace_id:h.state.workspace_id,project_id:h.state.project.id,
    items:[r],next_cursor:null,publishing_enabled:false,token_returned:false}));await h.ui.readHistory();assert.equal(h.get('history').children.length,0);
  assert.equal(h.messages.filter(x=>x[1]===true).length,2);
});

test('Meta selection and late scope changes cannot retain a previous readonly acknowledgement',async()=>{
  const h=harness();await h.ui.readAccounts();h.get('ack').checked=true;h.get('select').value=fixture.states.accounts[1].account_ref;h.get('select').events.change();
  assert.equal(h.get('ack').checked,false);let resolve;h.handler(()=>new Promise(r=>{resolve=r;}));const promise=h.ui.readHistory();
  h.state.workspace_id='wsp_foreign';h.ui.sync();resolve({schema_version:'native-official-account-check-page-v1',workspace_id:fixture.workspace_id,
    project_id:fixture.project.id,items:copy(fixture.rows),next_cursor:null,publishing_enabled:false,token_returned:false});await promise;
  assert.equal(h.get('history').children.length,0);assert.equal(h.get('ack').checked,false);
});
