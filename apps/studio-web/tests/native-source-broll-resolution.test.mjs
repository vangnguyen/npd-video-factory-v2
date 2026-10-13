import test from 'node:test';
import assert from 'node:assert/strict';
import {initializeSourceBrollResolution,sourceResolutionAction,sourceResolutionCreate,
  validateSourceResolution,validateSourceResolutionPage} from '../native-source-broll-resolution.mjs';

// Explicit UI protocol fixture: no stock/ASR/generation or human acceptance.
const clone=structuredClone, hash='a'.repeat(64), projectId='1'.repeat(32), resolutionId='nbr_'+'2'.repeat(32), planId='mpl_'+'3'.repeat(24);
const itemId='mpi_'+'4'.repeat(24);
function data(){
  const record={sha256:hash,plan:{media_plan_id:planId,version:1,items:[{media_plan_item_id:itemId,broll:{broll_intent:'AI giáo dục',search_query:'technology <script>private</script>'}}]}};
  const project={id:projectId,revision:1,document:{source_broll_plans:[record],canonical_timeline:{version:1,sha256:hash,
    snapshot:{metadata:{native_auto_edit_schema:'native-auto-edit-timeline-v1'}}}}};
  const state={workspace_id:'wsp_fixture',project,canEdit:true,canManage:true,dirty:false,busy:false,active:false};
  const session={schema_version:'native-source-broll-resolution.v1',resolution_id:resolutionId,project_id:projectId,
    workspace_id:state.workspace_id,version:1,snapshot_sha256:hash,state_sha256:hash,automatic_video_approval:false,publishing_enabled:false,provider_calls_at_creation:0,
    snapshot:{resolution_id:resolutionId,project_id:projectId,workspace_id:state.workspace_id,plan_sha256:hash,source_revision:1,
      source:{canonical_sha256:hash,canonical_version:1},priority:['user_asset','licensed_stock','internal_library','ai_image','ai_video'],items:{[itemId]:clone(record.plan.items[0])}},
    state:{status:'queued',expected:{revision:1,plan_version:1,plan_sha256:hash,document_sha256:hash},items:{[itemId]:{phase:'choose',attempts:[]}}}};
  const page={schema_version:'native-source-broll-resolution-page.v1',project_id:projectId,workspace_id:state.workspace_id,items:[session],provider_calls:0,publishing_enabled:false};
  return {record,state,session,page};
}
function harness(transport){
  class Node{constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.listeners={};this.checked=false;this.value='';}
    append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=[...nodes];}
    setAttribute(k,v){this.attributes[k]=String(v);}addEventListener(k,v){this.listeners[k]=v;}
    querySelectorAll(selector){return all(this).slice(1).filter(n=>selector==='input'?n.tagName==='input':false);}}
  const all=n=>[n,...n.children.flatMap(all)],dom={createElement:tag=>new Node(tag)},root=dom.createElement('details');
  const fixture=data(),calls=[],messages=[],updates=[];
  const api=async(path,body)=>{calls.push({path,body:body?clone(body):undefined});return transport?transport(path,body,fixture):clone(fixture.page);};
  const controller=initializeSourceBrollResolution({root,api,dom,getState:()=>fixture.state,newKey:()=> 'explicit-ui-key-0000001',
    onProject:value=>{updates.push(value);fixture.state.project=value;},onMessage:(...message)=>messages.push(message)});
  const get=name=>all(root).find(n=>Object.hasOwn(n.attributes,'data-broll-resolution-'+name));
  return {...fixture,root,calls,messages,updates,controller,get,all:()=>all(root)};
}
async function settle(){for(let i=0;i<8;i++)await Promise.resolve();}
test('payload uses frozen plan checksum and one canonical version without provider URI/payment authority',()=>{
  const {state,record,session}=data();const key='explicit-ui-key-0000001';
  const body=sourceResolutionCreate(state,record,[itemId],{requestKey:key});
  assert.equal(body.expected_plan_sha256,record.sha256);assert.equal(body.expected_timeline_version,1);
  assert.equal(body.external_acknowledged,false);assert.equal(body.fixture_acknowledged,false);
  assert.equal(body.download_url,undefined);assert.equal(body.max_ai_cost_vnd,undefined);
  assert.throws(()=>sourceResolutionCreate(state,record,[itemId,itemId],{requestKey:key}));
  assert.throws(()=>sourceResolutionCreate(state,record,[itemId],{requestKey:key,external:1}));
  const step=sourceResolutionAction(state,session,'step',{requestKey:key});assert.equal(step.expected_resolution_version,1);
  session.state.status='ready';assert.throws(()=>sourceResolutionAction(state,session,'apply',{requestKey:key,acknowledged:1}));
  assert.equal(sourceResolutionAction(state,session,'apply',{requestKey:key,acknowledged:true}).acknowledged,true);
});
test('roles dirty busy active archived and canonical/revision drift deny provider/canonical actions',()=>{
  for(const change of [s=>s.canEdit=false,s=>s.dirty=true,s=>s.busy=true,s=>s.active=true,s=>s.project.archived=true,
    s=>s.project.revision++,s=>s.project.document.canonical_timeline.sha256='b'.repeat(64),s=>s.canManage=false]){
    const {state,session}=data();change(state);assert.throws(()=>sourceResolutionAction(state,session,'step',{requestKey:'explicit-ui-key-0000001'}));
  }
  const {state,session}=data();state.canManage=false;session.state.status='ready';
  assert.doesNotThrow(()=>sourceResolutionAction(state,session,'apply',{requestKey:'explicit-ui-key-0000001',acknowledged:true}));
});
test('saved pages refuse foreign history or promotion to provider/publishing/video approval',()=>{
  const {state,page}=data();assert.doesNotThrow(()=>validateSourceResolutionPage(page,state));
  for(const change of [s=>s.workspace_id='foreign',s=>s.project_id='f'.repeat(32),s=>s.publishing_enabled=true,
    s=>s.automatic_video_approval=true,s=>s.provider_calls_at_creation=1,s=>s.snapshot.priority[0]='licensed_stock',s=>s.state.expected.revision=0]){
    const value=clone(page.items[0]);change(value);assert.throws(()=>validateSourceResolution(value,state));}
  const dup=clone(page);dup.items.push(clone(dup.items[0]));assert.throws(()=>validateSourceResolutionPage(dup,state));
});
test('all required source tiers may be configured in a different order',()=>{
  const {state,session}=data();session.snapshot.priority.reverse();assert.doesNotThrow(()=>validateSourceResolution(session,state));
  session.snapshot.priority.pop();assert.throws(()=>validateSourceResolution(session,state));
});
test('manager may explicitly observe a recovered child while parent attention remains',()=>{
  const {state,session}=data();session.state.status='recovery_required';
  assert.equal(sourceResolutionAction(state,session,'step',{requestKey:'explicit-ui-key-0000001'}).expected_resolution_version,1);
  state.canManage=false;assert.throws(()=>sourceResolutionAction(state,session,'step',{requestKey:'explicit-ui-key-0000001'}));
});
test('initialization performs zero I/O and source labels are text nodes',()=>{
  const h=harness();assert.equal(h.calls.length,0);
  assert.ok(h.all().every(n=>n.innerHTML===undefined));
  assert.match(h.all().map(n=>n.textContent??'').join(' '),/<script>private<\/script>/);
  assert.equal(h.get('step').disabled,true);assert.equal(h.get('apply').disabled,true);
});
test('read and context invalidation never advance a provider step',async()=>{
  const h=harness();h.get('read').listeners.click();await settle();
  assert.equal(h.calls.length,1);assert.equal(h.get('step').disabled,false);
  h.state.canManage=false;h.controller.sync();assert.equal(h.get('step').disabled,true);
  assert.equal(h.get('fixture').checked,false);assert.equal(h.calls.length,1);
});
test('unrelated transient loading blocks actions without discarding a verified saved session',async()=>{
  const h=harness();h.get('read').listeners.click();await settle();assert.equal(h.get('step').disabled,false);
  h.state.busy=true;h.controller.sync();assert.equal(h.get('step').disabled,true);assert.equal(h.get('choice').children.length,1);
  h.state.busy=false;h.controller.sync();assert.equal(h.get('step').disabled,false);assert.equal(h.calls.length,1);
});
test('late read after project switch cannot expose history or enable apply',async()=>{
  let finish;const h=harness(()=>new Promise(resolve=>finish=resolve));h.get('read').listeners.click();
  h.state.project.id='f'.repeat(32);h.controller.sync();finish(clone(h.page));await settle();
  assert.equal(h.get('choice').children.length,0);assert.equal(h.get('apply').disabled,true);assert.equal(h.updates.length,0);
});
test('ambiguous create retry preserves the exact original key and acknowledgement snapshot',async()=>{
  let count=0;const h=harness((path,body,f)=>{
    if(body){count++;if(count===1)throw Error('explicit interrupted response fixture');return clone(f.session);}
    return path.endsWith('/broll-resolutions')?clone(f.page):clone(f.state.project);
  });
  h.get('item').checked=true;h.get('external').checked=true;h.get('create').listeners.click();await settle();
  assert.equal(h.messages.length,1);h.get('external').checked=false;
  h.get('create').listeners.click();await settle();
  const writes=h.calls.filter(v=>v.body);assert.equal(writes.length,2);assert.deepEqual(writes[0],writes[1]);
  assert.equal(writes[1].body.external_acknowledged,true);assert.equal(h.updates.length,1);
});
test('an ambiguous step cannot be switched into another selected resolution',async()=>{
  const h=harness((path,body,f)=>{if(body)throw Error('explicit interrupted step response fixture');return clone(f.page);});
  const second=clone(h.session);second.resolution_id='nbr_'+'9'.repeat(32);second.snapshot.resolution_id=second.resolution_id;
  h.page.items.push(second);h.get('read').listeners.click();await settle();
  h.get('choice').value=resolutionId;h.get('choice').onchange();h.get('step').listeners.click();await settle();
  assert.equal(h.get('choice').disabled,true);
  h.get('choice').value=second.resolution_id;h.get('choice').onchange();
  assert.equal(h.get('choice').value,resolutionId);
  h.get('step').listeners.click();await settle();
  const writes=h.calls.filter(v=>v.body);assert.equal(writes.length,2);assert.deepEqual(writes[0],writes[1]);
  assert.ok(writes.every(v=>v.path.includes(resolutionId)&&!v.path.includes(second.resolution_id)));
});
