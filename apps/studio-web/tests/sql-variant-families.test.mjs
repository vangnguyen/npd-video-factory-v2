import {withIdleManualReframe} from './root-manual-reframe-idle-context.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {initializeSqlVariantFamilies,validateSqlVariantAvailability,validateSqlVariantFamily,
  validateSqlVariantReceipt,sqlVariantReservePayload,sqlVariantDerivePayload} from '../sql-variant-families.mjs';
const raw=readFileSync(new URL('./fixtures/sql-variant-families/asgi.json',import.meta.url));
const captured=JSON.parse(raw),dto=captured.dto,clone=structuredClone;
function state(role='editor'){const b=dto.availability.availability.binding;return{projectId:captured.master_project_id,workspaceId:captured.workspace_id,
  principal:{subject:'fixture-ui-editor',token_id:'fixture-ui-session',expires_at:'2100-01-01T00:00:00Z',platform_role:role},busy:false,dirty:false,
  timeline:{project_id:captured.master_project_id,workspace_id:captured.workspace_id,current_version:b.timeline_version,current_version_id:b.timeline_version_id,
    snapshot:{metadata:{explicit_fixture:true},tracks:[]}}};}
function harness({s=state(),memory=new Map(),storage,handler}={}){
  class Element{constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.listeners={};this.value='';this.checked=false;this.disabled=false;this.textContent='';}
    append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}setAttribute(k,v){this.attributes[k]=String(v);}addEventListener(k,v){this.listeners[k]=v;}}
  const dom={createElement:t=>new Element(t)},root=dom.createElement('div'),all=n=>[n,...n.children.flatMap(all)],calls=[],opened=[],messages=[];let count=0;
  const api=async(path,options)=>{const c={path,method:options?.method??'GET',body:options?.body?JSON.parse(options.body):null};calls.push(c);
    if(handler)return handler(c,s);
    if(c.method==='POST')return clone(path.endsWith('/derive')?dto.derived_receipt_mutation: dto.reserved_family_mutation);
    if(path.endsWith('/availability'))return clone(dto.availability);
    if(path.includes('?limit='))return clone(dto.page);
    return clone(dto.current_family);};
  const controller=initializeSqlVariantFamilies({root,dom,api,getState:()=>s,onMessage:(...v)=>messages.push(v),onChild:async v=>opened.push(v),
    storage:storage??{getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)},newKey:()=>`fixture-stable-intent-${++count}`});
  const get=name=>all(root).find(e=>Object.hasOwn(e.attributes,'data-sql-variant-'+name));
  return{s,controller,root,calls,memory,opened,messages,get};
}
const reserve=dto.reserved_family_mutation.family,current=dto.current_family,memberId=reserve.members[0].member_id;
const selected=dto.availability.availability.catalog.profiles.map(p=>p.profile_ref);
test('captured actual ASGI five DTO bytes remain exact and explicitly no model/provider/Owner acceptance',()=>{
  assert.equal(raw.length,64206);assert.equal(createHash('sha256').update(raw).digest('hex'),'b8a67d8879e911cbcc29e9a11b8844ed25baf98ee72c5fcba6068b26e0b6c1c7');
  assert.equal(captured.model_results_used,false);assert.equal(captured.provider_calls,0);assert.equal(captured.renderer_calls,0);assert.equal(captured.owner_uat,false);
  assert.equal(validateSqlVariantAvailability(dto.availability,state()),dto.availability);
  for(const f of[reserve,current,...dto.page.items])assert.equal(validateSqlVariantFamily(f,state()),f);
  assert.equal(validateSqlVariantReceipt(dto.derived_receipt_mutation.receipt,state(),reserve,memberId),dto.derived_receipt_mutation.receipt);
});
test('initialization and synchronization perform no I/O and do not mutate the canonical timeline',()=>{
  const h=harness(),before=JSON.stringify(h.s.timeline);h.controller.sync();assert.deepEqual(h.calls,[]);assert.equal(JSON.stringify(h.s.timeline),before);
});
test('captured actual reserved family builds a scoped explicit draft request and no body actor',()=>{
  const body=sqlVariantReservePayload(state(),dto.availability,selected,'fixture-stable-request-key',true);
  assert.deepEqual(body.profile_refs,selected);assert.equal(body.acknowledge_draft_derivation,true);assert.equal(Object.hasOwn(body,'actor_ref'),false);
  assert.equal(body.expected_timeline_version,state().timeline.current_version);
  const derive=sqlVariantDerivePayload(state(),reserve,memberId,'fixture-stable-derive-key',true);
  assert.equal(derive.schema_version,'sql-variant-storyboard-derive.v1');assert.equal(derive.expected_version,reserve.version);assert.equal(derive.acknowledge_unapproved_child,true);
});
for(const role of['viewer',null])test(`readers ${role} cannot construct mutations`,()=>{
  assert.throws(()=>sqlVariantReservePayload(state(role),dto.availability,selected,'fixture-stable-intent-key',true),/quyền/);
  assert.throws(()=>sqlVariantDerivePayload(state(role),reserve,memberId,'fixture-stable-intent-key',true),/quyền/);
});
for(const field of['dirty','busy'])test(`${field} workbench refuses writes before storing an intent or submitting`,async()=>{
  const h=harness();await h.controller.load();h.get('ack').checked=true;h.s[field]=true;
  await assert.rejects(h.controller.create());assert.equal(h.calls.filter(c=>c.method==='POST').length,0);assert.equal(h.memory.size,0);
});
test('a changed canonical version prevents a reservation without replacing selected review evidence',()=>{
  const s=state();s.timeline.current_version++;s.selectedReviewAnalysis={analysis_id:'explicit-B-fixture'};const before=JSON.stringify(s);
  assert.throws(()=>sqlVariantReservePayload(s,dto.availability,selected,'fixture-stable-intent-key',true),/Timeline/);assert.equal(JSON.stringify(s),before);
});
test('draft acknowledgement is a boolean and duplicate or foreign formats cannot be submitted',()=>{
  for(const ack of[false,1,'true',null])assert.throws(()=>sqlVariantReservePayload(state(),dto.availability,selected,'fixture-stable-intent-key',ack));
  for(const choices of[[],[selected[0],selected[0]],['foreign-platform@1']])assert.throws(()=>sqlVariantReservePayload(state(),dto.availability,choices,'fixture-stable-intent-key',true));
});
test('source drift, foreign member or a created child cannot start another draft',()=>{
  const old=clone(reserve);old.source_current=false;assert.throws(()=>sqlVariantDerivePayload(state(),old,memberId,'fixture-stable-intent-key',true));
  assert.throws(()=>sqlVariantDerivePayload(state(),reserve,'vfm_'+'0'.repeat(32),'fixture-stable-intent-key',true));
  assert.throws(()=>sqlVariantDerivePayload(state(),current,current.members.find(m=>m.child_project_id).member_id,'fixture-stable-intent-key',true));
});
test('saved uploaded evidence selects the uploaded contract and an unsupported unanalysed source fails closed',()=>{
  const f=clone(reserve);f.snapshot.binding.records.push({table:'auto_edit_analyses',count:1});
  assert.equal(sqlVariantDerivePayload(state(),f,memberId,'fixture-stable-intent-key',true).schema_version,'sql-variant-uploaded-derive.v1');
  f.snapshot.binding.records=f.snapshot.binding.records.filter(r=>!['auto_edit_analyses','uploaded_audio_transcriptions'].includes(r.table));f.snapshot.binding.source_mode='mixed';
  assert.throws(()=>sqlVariantDerivePayload(state(),f,memberId,'fixture-stable-intent-key',true),/phân tích/);
});
test('cross-workspace families and substituted child identities or authority flags are rejected',()=>{
  for(const alter of[f=>{f.workspace_id='wsp_foreign';},f=>{f.members[0].child_project_id='prj_foreign_child';},f=>{f.safety.approval_inherited=true;}]){
    const f=clone(current);alter(f);assert.throws(()=>validateSqlVariantFamily(f,state()));}
  const receipt=clone(dto.derived_receipt_mutation.receipt);receipt.result.child_project_id='prj_foreign_child';assert.throws(()=>validateSqlVariantReceipt(receipt,state(),reserve,memberId));
});
test('create and derive replay captured SQL DTOs without opening or approving a child implicitly',async()=>{
  const h=harness(),before=JSON.stringify(h.s.timeline);await h.controller.load();h.get('ack').checked=true;await h.controller.create();
  assert.equal(h.controller.current().state,'reserved');await h.controller.derive();assert.equal(h.controller.current().state,'needs_attention');
  assert.deepEqual(h.calls.filter(c=>c.method==='POST').map(c=>c.body.schema_version),['sql-variant-family-reserve.v1','sql-variant-storyboard-derive.v1']);
  assert.equal(h.controller.isPending(),false);assert.equal(h.opened.length,0);assert.equal(h.memory.size,0);assert.equal(JSON.stringify(h.s.timeline),before);
});
test('storage failure blocks POST before an intent can be lost',async()=>{
  const h=harness({storage:{getItem:()=>null,setItem:()=>{throw Error('fixture storage unavailable');}}});await h.controller.load();h.get('ack').checked=true;
  await assert.rejects(h.controller.create(),/storage/);assert.equal(h.calls.filter(c=>c.method==='POST').length,0);
});
test('a lost reservation response keeps the key and a saved read cannot invent successful write evidence',async()=>{
  let writes=0;const h=harness({handler:c=>{if(c.method==='POST'){if(++writes===1)throw Error('fixture lost response');return clone(dto.reserved_family_mutation);}
    return clone(c.path.endsWith('/availability')?dto.availability:c.path.includes('?limit=')?dto.page:dto.current_family);}});
  await h.controller.load();h.get('ack').checked=true;await assert.rejects(h.controller.create(),/lost/);assert.equal(h.controller.isPending(),true);
  const body=clone(h.calls.find(c=>c.method==='POST').body);await h.controller.load();assert.equal(h.controller.isPending(),true);await h.controller.retry();
  assert.deepEqual(h.calls.filter(c=>c.method==='POST').map(c=>c.body),[body,body]);assert.equal(h.controller.isPending(),false);
});
test('a lost derive reply retries the frozen old version after current family has advanced',async()=>{
  let derives=0;const h=harness({handler:c=>{if(c.method==='POST'){
    if(c.path.endsWith('/derive')){if(++derives===1)throw Error('fixture lost derive');return clone(dto.derived_receipt_mutation);}return clone(dto.reserved_family_mutation);}
    return clone(c.path.endsWith('/availability')?dto.availability:c.path.includes('?limit=')?dto.page:dto.current_family);}});
  await h.controller.load();h.get('ack').checked=true;await h.controller.create();await assert.rejects(h.controller.derive(),/lost/);
  const before=clone(h.calls.find(c=>c.path.endsWith('/derive')).body);await h.controller.load();assert.equal(h.controller.current().version,current.version);
  await h.controller.retry();assert.deepEqual(h.calls.filter(c=>c.path.endsWith('/derive')).map(c=>c.body),[before,before]);assert.equal(before.expected_version,reserve.version);
});
test('restored pending JSON corruption is held and never submitted',async()=>{
  const memory=new Map();const first=harness({memory,handler:c=>{if(c.method==='POST')throw Error('fixture lost');return clone(c.path.endsWith('/availability')?dto.availability:dto.page);}});
  await first.controller.load();first.get('ack').checked=true;await assert.rejects(first.controller.create());const [key,raw]=[...memory][0],pending=JSON.parse(raw);
  pending.body.expected_project_version+=1;memory.set(key,JSON.stringify(pending));const second=harness({memory});
  await assert.rejects(second.controller.retry(),/đối chiếu/);assert.equal(second.calls.filter(c=>c.method==='POST').length,0);assert.equal(memory.size,1);
});
test('a project switch during a write ignores the old response and retains its original recovery key',async()=>{
  let release;const h=harness({handler:c=>c.method==='POST'?new Promise(r=>{release=r;}):clone(c.path.endsWith('/availability')?dto.availability:dto.page)});
  await h.controller.load();h.get('ack').checked=true;const task=h.controller.create();assert.equal(h.memory.size,1);h.s.projectId='prj_different_context';h.controller.sync();
  release(clone(dto.reserved_family_mutation));await task;assert.equal(h.controller.current(),null);assert.equal(h.memory.size,1);assert.equal(h.opened.length,0);
});
test('explicit opening uses only the proven current child and preserves the master timeline',async()=>{
  const h=harness({s:state('viewer')}),before=JSON.stringify(h.s.timeline);await h.controller.load();const m=current.members.find(m=>m.child_project_id);
  h.get('member').value=m.member_id;h.controller.sync();await h.controller.open();assert.equal(h.opened[0].child_project_id,m.child_project_id);
  assert.equal(h.calls.filter(c=>c.method==='POST').length,0);assert.equal(JSON.stringify(h.s.timeline),before);
  h.s.dirty=true;await assert.rejects(h.controller.open(),/Lưu/);assert.equal(h.opened.length,1);
});
test('a new project or principal must acknowledge draft review again',async()=>{
  const h=harness();await h.controller.load();h.get('ack').checked=true;
  h.s.principal.token_id='another-fixture-session';h.controller.sync();assert.equal(h.get('ack').checked,false);assert.equal(h.controller.current(),null);
});
for(const ratio of['9:16','16:9','1:1','4:5'])test(`actual Studio callback selects ${ratio} final profile even for storyboard without source analysis`,async()=>{
  const {reframeProfiles}=await import('../reframe.mjs');
  const code=readFileSync(new URL('../studio.js',import.meta.url),'utf8');const start=code.indexOf('function renderReframe(){'),end=code.indexOf('\nfunction renderAnalysisReview',start);
  assert.ok(start>=0&&end>start);const profile={value:'vertical-1080x1920',dataset:{}},review={hidden:false};
  const s={timeline:{source_analysis_id:null,snapshot:{metadata:{reframe:{aspect_ratio:ratio}}}}};
  withIdleManualReframe('state','$','activeAnalysis','reframeProfiles','matchingVision',code.slice(start,end)+'\nrenderReframe();')(
    s,selector=>selector==='#final-profile'?profile:review,()=>null,reframeProfiles,()=>[]);
  assert.equal(profile.value,reframeProfiles(s.timeline.snapshot).final);assert.equal(review.hidden,true);
});
for(const change of['draft','principal'])test(`actual Studio child-open callback preserves master when ${change} changes during project read`,async()=>{
  const code=readFileSync(new URL('../studio.js',import.meta.url),'utf8'),start=code.indexOf('const variantFamilies = initializeSqlVariantFamilies('),end=code.indexOf('\nconst unsubscribeVideoBusy',start);
  assert.ok(start>=0&&end>start);const s=state(),before=JSON.stringify(s.timeline),select={value:s.projectId,innerHTML:''},writes=[];let release,dirty=false,loads=0;
  const options=withIdleManualReframe('state','$','initializeSqlVariantFamilies','api','toast','sqlFamilyState','escapeHtml','window','loadProject',
    code.slice(start,end)+'\nreturn variantFamilies;')(s,()=>select,v=>v,()=>new Promise(r=>{release=r;}),()=>{},()=>({busy:false,dirty}),
    v=>v,{localStorage:{setItem:(...v)=>writes.push(v)}},async()=>{loads++;});
  const m=current.members.find(m=>m.child_project_id),task=options.onChild({workspace_id:s.workspaceId,master_project_id:s.projectId,child_project_id:m.child_project_id});
  if(change==='draft')dirty=true;else s.principal.token_id='changed-while-project-list-waits';
  release([{project_id:m.child_project_id,workspace_id:s.workspaceId,name:'Explicit fixture child'}]);
  if(change==='draft')await assert.rejects(task,/Lưu/);else await task;
  assert.equal(s.projectId,captured.master_project_id);assert.equal(JSON.stringify(s.timeline),before);assert.equal(loads,0);assert.deepEqual(writes,[]);
});
