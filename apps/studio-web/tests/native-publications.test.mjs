import test from 'node:test';
import assert from 'node:assert/strict';
import {nativePublicationIntent,initializeNativePublications,supportsNativePublications} from '../native-publications.mjs';

const id='a'.repeat(32), jobId='b'.repeat(32), publication='npub_'+'c'.repeat(32), hash='d'.repeat(64);
const state=()=>({project:{id,revision:2,document:{name:'Native mock fixture'},approval:{revision:2},jobs:[{id:jobId,kind:'render',status:'succeeded',revision:2,
  result:{qc:{final_sha256:hash}},final_review:{decision:'approve',revision:2,artifact_sha256:hash}}]},canEdit:true,canManage:true,dirty:false,busy:false});
const values={platform:'youtube',title:'Mock fixture',description:'',caption:'',hashtags:'#Video #KienThuc',privacy:'private',scheduled:''};
const row=()=>({schema_version:'native-publication-v1',publication_id:publication,project_id:id,mock:true,external_action:false,publish_enabled:false,
  status:'awaiting_publish_approval',request_fingerprint:hash,approval:null,receipt:null,snapshot:{final_sha256:hash,
    request:{revision:2,platform:'youtube',mode:'dry_run',metadata:{title:'<img src=x onerror=unsafe()>',privacy:'private'}},validation:{status:'passed'}}});

test('capability and exact final approval guard create an explicitly dry-run private request',()=>{
  assert.equal(supportsNativePublications({}),false);assert.equal(supportsNativePublications({capabilities:{native_publication_review:true}}),true);
  const request=nativePublicationIntent(state(),values,'native-owned-fixture-key');assert.equal(request.mode,'dry_run');
  assert.equal(request.metadata.privacy,'private');assert.equal(request.metadata.scheduled_at,null);assert.deepEqual(request.metadata.hashtags,['#Video','#KienThuc']);
  for(const change of [{dirty:true},{busy:true},{canEdit:false},{project:{...state().project,archived:true}},
    {project:{...state().project,jobs:[]}}, {project:{...state().project,approval:null}}])assert.throws(()=>nativePublicationIntent({...state(),...change},values,'fixture'));
  assert.throws(()=>nativePublicationIntent(state(),{...values,scheduled:'invalid'},'fixture'));
});

function harness(){const nodes=new Map();class Node{constructor(){this.value='';this.checked=false;this.dataset={};this.listeners={};this.children=[];}
  addEventListener(name,fn){this.listeners[name]=fn;}replaceChildren(){this.children=[];}append(child){this.children.push(child);}}
  const root={getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);},createElement(){return new Node();}};
  const get=id=>root.getElementById(id),current=state(),calls=[],messages=[];let count=0;
  for(const [key,value] of Object.entries(values))get('native-publish-'+key).value=value;
  let handler=async(path,body)=>body?row():{schema_version:'native-publication-page-v1',project_id:id,items:[row()],next_cursor:null};
  const controller=initializeNativePublications({root,getState:()=>current,api:async(...args)=>{calls.push(args);return handler(...args);},
    onMessage:message=>messages.push(message),uuid:()=>`fixture-${++count}`});
  return{controller,get,current,calls,messages,handler(fn){handler=fn;}};
}

test('reading and selecting saved requests do not approve, dispatch, edit or render markup',async()=>{
  const h=harness();assert.equal(h.calls.length,0);await h.controller.read();assert.equal(h.calls.length,1);assert.equal(h.calls[0][1],undefined);
  assert.equal(h.get('native-publish-history').children[0].textContent.includes('<img src=x onerror=unsafe()>'),true);
  assert.equal(h.get('native-publish-approve').disabled,true);assert.equal(h.get('native-publish-run').disabled,true);
  assert.equal(h.current.project.revision,2);
});

test('unknown create outcome reuses key and confirmed replay cannot create another duplicate intent',async()=>{
  const h=harness();h.handler(async()=>{throw new Error('lost reply');});await h.controller.execute('create');
  h.handler(async()=>row());await h.controller.execute('create');await h.controller.execute('create');
  assert.equal(h.calls[0][1].request_key,h.calls[1][1].request_key);assert.equal(h.calls[1][1].request_key,h.calls[2][1].request_key);
  assert.equal(h.calls.every(([,body])=>body.mode==='dry_run'),true);
});

test('owner review requires a separate checkbox and editor cannot approve',async()=>{
  const h=harness();await h.controller.read();await h.controller.execute('approve');assert.equal(h.calls.length,1);
  h.current.canManage=false;h.get('native-publish-ack').checked=true;await h.controller.execute('approve');assert.equal(h.calls.length,1);
  h.current.canManage=true;h.handler(async()=>({...row(),status:'queued',approval:{actor_ref:'fixture-owner'}}));
  await h.controller.execute('approve');assert.equal(h.calls.length,2);assert.equal(h.calls[1][1].acknowledged,true);
  assert.equal(h.calls[1][1].expected_artifact_sha256,hash);assert.equal(h.get('native-publish-ack').checked,false);
});

test('late read is discarded after changing project and contradictory live evidence is rejected',async()=>{
  const h=harness();let resolve;h.handler(()=>new Promise(done=>{resolve=done;}));const pending=h.controller.read();
  h.current.project={...h.current.project,id:'e'.repeat(32)};h.controller.sync();resolve({schema_version:'native-publication-page-v1',project_id:id,items:[row()],next_cursor:null});
  await pending;assert.equal(h.get('native-publish-history').children.length,0);
  const next=harness();next.handler(async()=>({...row(),external_action:true}));await next.controller.execute('create');
  assert.equal(next.get('native-publish-history').children.length,0);assert.match(next.messages[0],/khớp phạm vi/);
});

test('keyset history explicitly requests the next page without duplicate rows',async()=>{
  const h=harness();h.handler(async()=>({schema_version:'native-publication-page-v1',project_id:id,items:[row()],next_cursor:'scoped-cursor'}));
  await h.controller.read();await h.controller.read(true);assert.match(h.calls[1][0],/cursor=scoped-cursor/);
  assert.equal(h.get('native-publish-history').children.length,1);assert.equal(h.calls.every(([,body])=>body===undefined),true);
});
