import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash,webcrypto} from 'node:crypto';
import {initializeSqlVariantNarration,validateNarrationProposal,validateNarrationReceipt,
  validateNarrationAvailability,narrationReusePayload,narrationReviewPayload,narrationReceiptIds} from '../sql-variant-narration.mjs';

const captured=JSON.parse(readFileSync(new URL('./fixtures/sql-variant-narration/asgi.json',import.meta.url),'utf8'));
const clone=structuredClone;
function state(){return{workspaceId:captured.context.workspace_id,projectId:captured.context.project_id,
  projects:[clone(captured.project)],timeline:clone(captured.timeline),productionPackage:clone(captured.package_before),
  busy:false,dirty:false,principal:{subject:captured.context.actor_ref,token_id:'explicit-ui-fixture',
    expires_at:'2100-01-01T00:00:00Z',workspace_roles:{[captured.context.workspace_id]:'editor'}}};}
function harness({transport,storageMap=new Map(),storageImpl,cryptoImpl=webcrypto,onImported}={}){
  class Element{constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.listeners={};this.disabled=false;this.checked=false;}
    setAttribute(k,v){this.attributes[k]=v;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,v){this.listeners[k]=v;}}
  const dom={createElement:tag=>new Element(tag)},root=dom.createElement('section'),s=state(),calls=[],messages=[],imported=[],reviewed=[];
  let token='vf1.synthetic-ui-fixture.'+'x'.repeat(36),keys=0;
  const api=async(path,options={})=>{const body=options.body?JSON.parse(options.body):null;
    calls.push({path,method:options.method??'GET',body});
    const changed=await transport?.(path,body,s);if(changed!==undefined)return changed;
    if(path.endsWith('/narration-reuse-availability'))return clone(captured.availability);
    if(path.endsWith('/narration-reuse-proposal'))return clone(captured.proposal);
    if(path.includes('/narration-receipts/'))return clone(captured.receipt_read);
    if(path.endsWith('/narration-reuse'))return clone(captured.import_response);
    if(path.endsWith('/narration-review-render'))return clone(captured.review_response);
    throw Error('UNEXPECTED_FIXTURE_ENDPOINT');};
  const controller=initializeSqlVariantNarration({root,api,getState:()=>s,dom,cryptoImpl,
    newKey:()=>{keys++;return captured.import_request.request_key;},getSessionToken:()=>token,
    onMessage:(...v)=>messages.push(v),onImported:async v=>{imported.push(v);await onImported?.(s);},
    onReviewQueued:async v=>reviewed.push(v),storage:storageImpl??{getItem:k=>storageMap.get(k)??null,
      setItem:(k,v)=>storageMap.set(k,v),removeItem:k=>storageMap.delete(k)}});
  const all=e=>[e,...e.children.flatMap(all)],get=n=>all(root).find(e=>Object.hasOwn(e.attributes,'data-narration-'+n));
  const click=async n=>{await get(n).listeners.click();};
  const ack=n=>{get(n+'-ack').checked=true;get(n+'-ack').listeners.change();};
  return{state:s,controller,calls,messages,storageMap,imported,reviewed,get,click,ack,keys:()=>keys,
    token:()=>token,setToken:v=>{token=v;}};
}

test('actual API fixture checksums retain synthetic provenance and literal server-only source/profile pins',()=>{
  const manifest=JSON.parse(readFileSync(new URL('./fixtures/sql-variant-narration/manifest.json',import.meta.url),'utf8'));
  for(const row of manifest.files){const bytes=readFileSync(new URL('./fixtures/sql-variant-narration/'+row.name,import.meta.url));
    assert.equal(bytes.length,row.bytes);assert.equal(createHash('sha256').update(bytes).digest('hex'),row.sha256);}
  assert.match(captured.fixture_notice,/synthetic.*not genuine/i);assert.equal(manifest.provider_calls,0);
  assert.equal(manifest.real_renderer_calls,0);assert.equal(manifest.owner_uat_accepted,false);
  const s=state();assert.equal(validateNarrationProposal(captured.proposal,s),captured.proposal);
  assert.deepEqual(narrationReusePayload(captured.proposal,s,captured.import_request.request_key,true),captured.import_request);
  assert.deepEqual(narrationReviewPayload(captured.receipt_read,s,true),captured.review_request);
});
test('initialization and sync perform no read, import, queue, inference or automatic approval',()=>{
  const h=harness();h.controller.sync();assert.equal(h.calls.length,0);assert.equal(h.keys(),0);
  assert.equal(h.get('reuse').disabled,true);assert.equal(h.get('review').disabled,true);
});
test('explicit Prepare then separately acknowledged Reuse follows real typed API and preserves source hashes literally',async()=>{
  const h=harness();await h.click('prepare');assert.equal(h.calls.length,2);assert.equal(h.calls.every(v=>v.method==='GET'),true);
  await h.click('reuse');assert.equal(h.calls.filter(v=>v.method==='POST').length,0);
  h.ack('import');await h.click('reuse');const post=h.calls.find(v=>v.method==='POST');
  assert.deepEqual(post.body,captured.import_request);assert.equal(h.imported.length,1);assert.equal(h.controller.isPending(),false);
  assert.equal(h.reviewed.length,0);assert.equal(h.get('review').disabled,true);
  assert.equal([...h.storageMap.values()].some(v=>v.includes(h.token())),false);
});
test('ready import requires a separate review intent and existing child package; no master approval field is submitted',async()=>{
  const h=harness();await h.click('prepare');h.ack('import');await h.click('reuse');h.ack('review');await h.click('review');
  const posts=h.calls.filter(v=>v.method==='POST');assert.equal(posts.length,2);assert.deepEqual(posts[1].body,captured.review_request);
  assert.equal(Object.hasOwn(posts[1].body,'approval_id'),false);assert.equal(Object.hasOwn(posts[1].body,'actor_ref'),false);
  assert.equal(h.reviewed.length,1);assert.equal(h.reviewed[0].approval_id,null);
});
test('foreign scopes, promoted safety, guessed profiles and added provider/actor fields reject before any write',()=>{
  for(const change of[p=>p.workspace_id='wsp_foreign',p=>p.child_project_id='prj_foreign_fixture',
    p=>p.approval_transferred=true,p=>p.provider_calls=1,p=>p.request_template.voice_config.language='en',
    p=>p.request_template.actor_ref='forged',p=>p.request_template.expected_profile_sha256s=['fake'],
    p=>p.request_template.source_url='http://private-fixture.invalid']){
    const p=clone(captured.proposal);change(p);assert.throws(()=>validateNarrationProposal(p,state()));}
  for(const change of[r=>r.member_id='vfm_'+'f'.repeat(32),r=>r.result.approval_transferred=true,
    r=>Object.values(r.result.copies)[0].object_key='workspaces/foreign/object.wav']){
    const r=clone(captured.receipt_read);change(r);assert.throws(()=>validateNarrationReceipt(r,state(),captured.import_request));}
});
test('viewer, dirty, busy and expired sessions cannot prepare import or review via forged clicks',async()=>{
  for(const change of[s=>s.principal.workspace_roles[s.workspaceId]='viewer',s=>s.dirty=true,s=>s.busy=true,
    s=>s.principal.expires_at='2000-01-01T00:00:00Z']){
    const h=harness();change(h.state);await h.click('prepare');h.ack('import');await h.click('reuse');h.ack('review');await h.click('review');
    assert.equal(h.calls.filter(v=>v.method==='POST').length,0);assert.equal(h.keys(),0);
  }
});
test('missing/default-disabled proposal endpoints never turn into generated speech or another provider path',async()=>{
  const h=harness({transport:path=>{if(path.endsWith('/narration-reuse-proposal'))throw Object.assign(Error('NOT_CONFIGURED'),{status:503});}});
  await h.click('prepare');h.ack('import');await h.click('reuse');assert.equal(h.calls.filter(v=>v.method==='POST').length,0);
  assert.equal(h.imported.length,0);assert.equal(h.controller.current().proposal,null);
  assert.equal(h.calls.every(v=>v.path.includes('/narration-reuse-')),true);
});
test('last proposal await after session rotation/dispose/current timeline drift cannot be adopted or submitted',async()=>{
  for(const change of[h=>h.setToken(h.token()+'rotation'),h=>h.controller.dispose(),h=>h.state.timeline.current_version++,h=>h.state.dirty=true]){
    let finish,entered;const started=new Promise(r=>entered=r);
    const h=harness({transport:path=>path.endsWith('/narration-reuse-proposal')?new Promise(r=>{finish=r;entered();}):undefined});
    const preparing=h.click('prepare');await started;change(h);finish(clone(captured.proposal));await preparing;h.ack('import');await h.click('reuse');
    assert.equal(h.calls.filter(v=>v.method==='POST').length,0);assert.equal(h.controller.current().proposal,null);
  }
});
test('the proposal snapshot is frozen before later caller object mutation',async()=>{
  const response=clone(captured.proposal),h=harness({transport:path=>path.endsWith('/narration-reuse-proposal')?response:undefined});
  await h.click('prepare');response.request_template.expected_source_manifest_sha256='f'.repeat(64);
  h.ack('import');await h.click('reuse');assert.equal(h.calls.filter(v=>v.method==='POST').length,0);
  assert.equal(h.controller.isPending(),true); // Fresh GET differs; original stored intent remains exact.
  const pending=JSON.parse([...h.storageMap.values()].find(v=>v.includes('sql-narration-ui-pending')));
  assert.equal(pending.body.expected_source_manifest_sha256,captured.import_request.expected_source_manifest_sha256);
});
test('same source late freshness-hash drift holds exact old key/body and calls no import',async()=>{
  let changed=false;
  const h=harness({transport:path=>{if(changed&&path.endsWith('/narration-reuse-proposal'))return{...clone(captured.proposal),proposal_sha256:'f'.repeat(64)};}});
  await h.click('prepare');changed=true;h.ack('import');await h.click('reuse');
  assert.equal(h.calls.filter(v=>v.method==='POST').length,0);assert.equal(h.controller.isPending(),true);assert.equal(h.keys(),1);
  await h.click('retry');assert.equal(h.keys(),1);assert.equal(h.calls.filter(v=>v.method==='POST').length,0);
});
test('lost import response retains exact body/key; explicit retry uses the original request',async()=>{
  let posts=0;const h=harness({transport:(path,body)=>{if(path.endsWith('/narration-reuse')&&body&&++posts===1)throw Error('fixture lost response');}});
  await h.click('prepare');h.ack('import');await h.click('reuse');assert.equal(h.controller.isPending(),true);
  const first=h.calls.find(v=>v.method==='POST');await h.click('retry');const sent=h.calls.filter(v=>v.method==='POST');
  assert.equal(sent.length,2);assert.deepEqual(sent[1].body,first.body);assert.equal(h.keys(),1);assert.equal(h.controller.isPending(),false);
});
test('successful import followed by failed receipt GET retains locator/key and later read resolves without another POST',async()=>{
  let lost=true;const h=harness({transport:path=>{if(lost&&path.includes('/narration-receipts/'))throw Error('fixture saved read unavailable');}});
  await h.click('prepare');h.ack('import');await h.click('reuse');assert.equal(h.controller.isPending(),true);assert.equal(h.imported.length,0);
  const saved=JSON.parse([...h.storageMap.values()].find(v=>v.includes('sql-narration-ui-pending')));
  assert.equal(saved.receipt_id,captured.receipt_read.receipt_id);lost=false;await h.click('read');
  assert.equal(h.calls.filter(v=>v.method==='POST').length,1);assert.equal(h.controller.isPending(),false);
  assert.equal(h.controller.current().receipt.state,'ready');
});
test('storage failure before import prevents wire; raw token is never persisted in retry data',async()=>{
  const h=harness({storageImpl:{getItem:()=>null,setItem:()=>{throw Error('fixture storage denied');},removeItem(){}}});
  await h.click('prepare');h.ack('import');await h.click('reuse');assert.equal(h.calls.filter(v=>v.method==='POST').length,0);
});
test('restored durable intent cannot rebind token credential rotation under same actor/id/expiry',async()=>{
  const map=new Map();let fail=true;
  const h=harness({storageMap:map,transport:(_path,body)=>{if(body&&fail)throw Error('fixture lost response');}});
  await h.click('prepare');h.ack('import');await h.click('reuse');h.controller.dispose();
  const restored=harness({storageMap:map});restored.setToken(restored.token()+'rotation');await restored.click('retry');
  assert.equal(restored.calls.filter(v=>v.method==='POST').length,0);assert.equal(map.size,1);fail=false;
});
test('last receipt read after role/draft/timeline/session changes keeps saved request and avoids stale adoption',async()=>{
  for(const change of[h=>h.state.dirty=true,h=>h.state.timeline.current_version++,h=>h.setToken(h.token()+'rotation')]){
    let finish,entered;const started=new Promise(r=>entered=r);
    const h=harness({transport:path=>path.includes('/narration-receipts/')?new Promise(r=>{finish=r;entered();}):undefined});
    await h.click('prepare');h.ack('import');const submitting=h.click('reuse');await started;change(h);
    finish(clone(captured.receipt_read));await submitting;assert.equal(h.imported.length,0);
    assert.equal(h.calls.filter(v=>v.method==='POST').length,1);assert.equal([...h.storageMap.values()].some(v=>v.includes('sql-narration-ui-pending')),true);
  }
});
test('unknown handoff result is kept as an ambiguous render intent and never triggers a new automatic job',async()=>{
  const response=clone(captured.review_response);response.manifest.variant_narration_handoff.state='unknown';
  const h=harness({transport:(path,body)=>path.endsWith('/narration-review-render')&&body?response:undefined});
  await h.click('prepare');h.ack('import');await h.click('reuse');h.ack('review');await h.click('review');
  assert.equal(h.controller.isPending(),true);assert.equal(h.reviewed.length,0);assert.equal(h.calls.filter(v=>v.method==='POST').length,2);
  await h.click('retry');const posts=h.calls.filter(v=>v.method==='POST');assert.equal(posts.length,3);assert.deepEqual(posts[1].body,posts[2].body);
  assert.equal(h.controller.isPending(),true);assert.equal(h.reviewed.length,0);
});
test('wrong review receipt, transferred approval and child versions cannot be accepted as a queued current review',async()=>{
  for(const change of[v=>v.approval_id='apr_master_approved',v=>v.project_id='prj_foreign_child',
    v=>v.manifest.variant_narration_request.input_sha256='f'.repeat(64),v=>v.audio_version++]){
    const response=clone(captured.review_response);change(response);
    const h=harness({transport:(path,body)=>path.endsWith('/narration-review-render')&&body?response:undefined});
    await h.click('prepare');h.ack('import');await h.click('reuse');h.ack('review');await h.click('review');
    assert.equal(h.reviewed.length,0);assert.equal(h.controller.isPending(),true);
  }
});
test('read-only disabled availability keeps historical receipt visible and never enables reuse/review',async()=>{
  const h=harness({transport:path=>path.endsWith('/narration-reuse-availability')?{...clone(captured.availability),state:'NOT_CONFIGURED',reason_code:'SQL_VARIANT_NARRATION_DISABLED'}:undefined});
  await h.click('read');assert.equal(h.get('reuse').disabled,true);assert.equal(h.get('review').disabled,true);
  assert.equal(h.calls.filter(v=>v.method==='POST').length,0);assert.equal(validateNarrationAvailability(captured.availability),captured.availability);
});
test('copied source proof cannot disagree with its object checksum, class or frozen content version',()=>{
  for(const change of[p=>p.checksum_sha256='f'.repeat(64),p=>p.asset_class='source',p=>p.project_version_id='pver_foreign']){
    const r=clone(captured.receipt_read);change(Object.values(r.result.copies)[0].asset_proof);
    assert.throws(()=>validateNarrationReceipt(r,state(),captured.import_request));
  }
});
test('import response cannot bind a different captured source input hash to the saved proposal',async()=>{
  const changed=clone(captured.import_response);changed.receipt.input_sha256='f'.repeat(64);changed.receipt.result.input_sha256='f'.repeat(64);
  const h=harness({transport:(path,body)=>path.endsWith('/narration-reuse')&&body?changed:
    path.includes('/narration-receipts/')?changed.receipt:undefined});
  await h.click('prepare');h.ack('import');await h.click('reuse');
  assert.equal(h.imported.length,0);assert.equal(h.controller.isPending(),true);
});
test('cold controller reads an actual server-owned copied receipt without browser storage or new provider/import request',async()=>{
  const h=harness();h.state.assets=clone(captured.assets_after_import);h.controller.sync();
  assert.deepEqual(narrationReceiptIds(h.state),[captured.receipt_read.receipt_id]);await h.click('read');
  assert.equal(h.calls.filter(v=>v.method==='POST').length,0);assert.equal(h.controller.current().receipt.state,'ready');
  assert.equal(h.get('review').disabled,true);assert.equal(h.keys(),0);
  const viewer=harness();viewer.state.assets=clone(captured.assets_after_import);viewer.state.principal.workspace_roles[viewer.state.workspaceId]='viewer';
  await viewer.click('read');assert.equal(viewer.controller.current().receipt.state,'ready');assert.equal(viewer.get('review').disabled,true);
});
test('copied asset discovery rejects foreign, unverified or arbitrary URL receipt references',()=>{
  for(const change of[a=>a.workspace_id='wsp_foreign',a=>a.provenance.source_bytes_verified=false,
    a=>a.provenance.parent_project_id='prj_other_master',a=>a.provenance.narration_receipt_id='http://fixture.invalid/foreign']){
    const s=state();s.assets=clone(captured.assets_after_import).filter(a=>a.kind==='variant-narration-source');change(s.assets[0]);
    assert.deepEqual(narrationReceiptIds(s),[]);
  }
});
test('durable unresolved request blocks the cold parent dirty guard before any GET or trust restoration',async()=>{
  const map=new Map(),h=harness({storageMap:map,transport:(_path,body)=>{if(body)throw Error('fixture lost');}});
  await h.click('prepare');h.ack('import');await h.click('reuse');h.controller.dispose();
  const cold=harness({storageMap:map});assert.equal(cold.controller.isPending(),true);
  assert.equal(cold.calls.length,0);assert.equal(cold.get('prepare').disabled,true);
});
test('already imported exact narration never creates another intent through a forged duplicate click',async()=>{
  const h=harness();await h.click('prepare');h.ack('import');await h.click('reuse');
  assert.equal(h.get('reuse').disabled,true);await h.click('reuse');assert.equal(h.keys(),1);
  assert.equal(h.calls.filter(v=>v.method==='POST').length,1);
});
test('explicit saved narration selection wins over an older browser-known receipt',async()=>{
  // UI-only second metadata record; no claim of another real source/provider result.
  const second='vfr_'+'f'.repeat(32),alternate=clone(captured.receipt_read);alternate.receipt_id=second;
  for(const c of Object.values(alternate.result.copies)){c.object_key=c.object_key.replace(captured.receipt_read.receipt_id,second);c.asset_proof.object_key=c.object_key;}
  const h=harness({transport:path=>path.endsWith('/narration-receipts/'+second)?alternate:undefined});
  await h.click('prepare');h.ack('import');await h.click('reuse');h.state.assets=clone(captured.assets_after_import);
  const asset=clone(h.state.assets.find(a=>a.kind==='variant-narration-source'));
  asset.provenance.narration_receipt_id=second;asset.object_key=asset.object_key.replace(captured.receipt_read.receipt_id,second);h.state.assets.push(asset);
  h.controller.sync();h.get('saved').value=second;h.get('saved').listeners.change();await h.click('read');
  assert.equal(h.controller.current().receipt.receipt_id,second);
  assert.equal(h.calls.at(-1).path.endsWith('/'+second),true);
});
