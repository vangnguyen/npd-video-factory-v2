import test from 'node:test';import assert from 'node:assert/strict';
import {initializeNativeStock,stockSourceLink} from '../native-stock.mjs';
const WSP='wsp_stock_fixture',PROJECT='a'.repeat(32),JOB='nstk_'+'b'.repeat(32),DOWNLOAD='nstk_'+'d'.repeat(32),CANDIDATE='smc_'+'c'.repeat(24),SHA='e'.repeat(64);
const config=()=>({schema_version:'native-stock-providers-v1',workspace_id:WSP,ui_enablement_supported:false,automatic_attachment:false,
  items:[{provider:'pexels',status:'CONFIGURED',mode:'fixture',configuration_sha256:SHA},{provider:'pixabay',status:'NOT_CONFIGURED',mode:'official',configuration_sha256:null}]});
function row(kind='search',status='succeeded'){const result={stock_id:kind==='search'?JOB:DOWNLOAD,project_id:PROJECT,workspace_id:WSP,mock:true,canonical_timeline_mutated:false,
  automatic_attachment:false,paid_operations:0,real_provider_acceptance_complete:false,actual_provider_calls:0};
  if(kind==='search')Object.assign(result,{candidates:[{candidate_id:CANDIDATE,provider:'pexels',creator:'Vang Nguyễn <script>',width:320,height:240,license:'EXPLICIT MOCK LICENSE',
    source_reference:'https://www.pexels.com/photo/explicit-fixture-11/',production_eligible:false,semantic_score:null,provenance:{fixture:true}}],candidate_sha256:{[CANDIDATE]:SHA}});
  else result.asset={id:'f'.repeat(32)+'.jpg',kind:'image',sha256:SHA,rights_status:'unknown',needs_attention:true,production_eligible:false};
  return {schema_version:'native-stock-job-v1',stock_id:kind==='search'?JOB:DOWNLOAD,workspace_id:WSP,project_id:PROJECT,kind,status,request_fingerprint:SHA,result_sha256:status==='succeeded'?SHA:null,
    publish_enabled:false,automatic_attachment:false,snapshot:{workspace_id:WSP,project_id:PROJECT,provider:'pexels',provider_mode:'fixture',provider_configuration_sha256:SHA},
    result:status==='succeeded'?result:null,attachment:null};}
function page(values=[row()]){return {schema_version:'native-stock-page-v1',workspace_id:WSP,project_id:PROJECT,items:values,next_cursor:null,automatic_attachment:false};}
function harness(){class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.listeners={};this.value='';this.checked=false;}
  append(...values){this.children.push(...values);}replaceChildren(...values){this.children=values;}addEventListener(name,fn){this.listeners[name]=fn;}}
  const root=new Node('details'),dom={getElementById:()=>root,createElement:tag=>new Node(tag)},state={workspace_id:WSP,project:{id:PROJECT,revision:3},canManage:true,canEdit:true,dirty:false,busy:false,active:false};
  const calls=[],messages=[],saved=[],timers=[];let response=async path=>path==='/api/stock/providers'?config():page();
  const controller=initializeNativeStock({dom,getState:()=>state,api:async(path,body)=>{calls.push([path,body]);return response(path,body);},onSaved:async value=>saved.push(value),
    uuid:()=> 'explicit-fixture-uuid-001',onMessage:(...value)=>messages.push(value),setTimer:fn=>{timers.push(fn);return timers.length;},clearTimer:()=>{}});
  const [status,sources,read,providerLabel,queryLabel,typeLabel,orientationLabel,ackLabel,search,jobsLabel,candidateLabel,detail,download,cancel,importLabel,attach,more,preview]=root.children;
  return {controller,state,calls,messages,saved,timers,status,sources,read,provider:providerLabel.children[0],query:queryLabel.children[0],type:typeLabel.children[0],orientation:orientationLabel.children[0],
    ack:ackLabel.children[0],search,jobs:jobsLabel.children[0],candidates:candidateLabel.children[0],detail,download,cancel,importAck:importLabel.children[0],attach,preview,handler:value=>{response=value;}};}
test('explicit scoped stock read shows literal creators, source links and fixture label with no automatic search/download/attachment',async()=>{
  const h=harness();assert.equal(h.calls.length,0);await h.controller.load();assert.equal(h.calls.length,2);assert.match(h.status.textContent,/MÔ PHỎNG/);
  assert.match(h.candidates.children[0].textContent,/Vang Nguyễn <script>/);assert.equal(h.candidates.children[0].innerHTML,undefined);assert.equal(h.download.disabled,true);
  assert.equal(h.sources.children[0].href,'https://www.pexels.com/');h.state.canManage=false;h.ack.checked=true;await h.controller.execute('download');assert.equal(h.calls.length,2);
  assert.throws(()=>stockSourceLink('javascript:alert(1)','pexels'));assert.throws(()=>stockSourceLink('https://evil.example/photo','pexels'));assert.throws(()=>stockSourceLink('https://u:p@pexels.com/photo','pexels'));
});
test('exact saved candidate and server digest support stable lost-reply download key without client URL or rights fields',async()=>{
  const h=harness();await h.controller.load();h.ack.checked=true;let lost=true;
  h.handler(async(path,body)=>{if(lost)throw new Error('EXPLICIT LOST REPLY');return row('download','queued');});
  await h.controller.execute('download');lost=false;await h.controller.execute('download');const writes=h.calls.filter(([,body])=>body);
  assert.equal(writes.length,2);assert.deepEqual(writes[0][1],writes[1][1]);assert.equal(writes[0][1].candidate_id,CANDIDATE);assert.equal(writes[0][1].expected_candidate_sha256,SHA);
  assert.equal(writes[0][1].expected_result_sha256,SHA);assert.equal(writes[0][1].fixture_acknowledged,true);assert.equal(writes[0][1].external_acknowledged,false);
  assert.equal(writes[0][1].download_url,undefined);assert.equal(writes[0][1].license,undefined);assert.equal(writes[0][1].rights_status,undefined);assert.equal(h.saved.length,0);assert.equal(h.ack.checked,false);
});
test('editor reviews only local media before explicit attachment and receipt cannot grant rights or auto-edit timeline',async()=>{
  const h=harness();h.state.canManage=false;h.handler(async path=>path==='/api/stock/providers'?config():page([row('download')]));await h.controller.load();
  assert.equal(h.preview.children[1].src,`/api/projects/${PROJECT}/stock/${DOWNLOAD}/file`);assert.equal(h.preview.children[1].tagName,'IMG');assert.equal(h.attach.disabled,true);
  h.importAck.checked=true;h.handler(async()=>({schema_version:'native-stock-import-v1',stock_id:DOWNLOAD,workspace_id:WSP,project_id:PROJECT,revision:4,asset_sha256:SHA,
    approval_invalidated:true,rights_independently_verified:false,canonical_timeline_auto_edited:false,external_calls:0}));await h.controller.execute('import');
  assert.equal(h.saved.length,1);assert.equal(h.calls.at(-1)[0],`/api/projects/${PROJECT}/stock/${DOWNLOAD}/import`);assert.match(h.messages.at(-1)[0],/duyệt lại/);
});
test('read-only, dirty, busy, archived and active project controls never issue stock mutation',async()=>{
  for(const mutate of [state=>{state.canEdit=false;state.canManage=false;},state=>state.dirty=true,state=>state.busy=true,state=>state.project.archived=true,state=>state.active=true]){
    const h=harness();h.handler(async path=>path==='/api/stock/providers'?config():page([row('download')]));await h.controller.load();h.importAck.checked=true;mutate(h.state);h.controller.controls();
    await h.controller.execute('import');assert.equal(h.calls.length,2);assert.equal(h.saved.length,0);assert.equal(h.attach.disabled,true);
  }
});
test('foreign or late workspace responses and promoted fixture results do not restore choices or start polling/actions',async()=>{
  const h=harness();let release;h.handler(async path=>path==='/api/stock/providers'?config():new Promise(resolve=>{release=resolve;}));const first=h.controller.load();
  h.state.project={id:'9'.repeat(32),revision:1};h.controller.sync();release(page());await first;assert.equal(h.candidates.children.length,0);assert.equal(h.controller.isWorking(),false);
  h.state.project={id:PROJECT,revision:3};h.controller.sync();const promoted=row();promoted.result.mock=false;
  h.handler(async path=>path==='/api/stock/providers'?config():page([promoted]));await h.controller.load();assert.equal(h.candidates.children.length,0);assert.equal(h.messages.at(-1)[1],true);
});
