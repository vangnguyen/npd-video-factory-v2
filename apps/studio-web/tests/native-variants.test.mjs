import test from 'node:test';
import assert from 'node:assert/strict';
import {supportsNativeVariants,initializeNativeVariants} from '../native-variants.mjs';
const master='a'.repeat(32),child='b'.repeat(32),workspace='wsp_native_fixture',batch='nsvb_'+'c'.repeat(32);
const profile={profile_ref:'youtube-shorts@1',label:'Shorts <script>',width:1080,height:1920,aspect_ratio:'9:16',platform:'youtube'};
const row=()=>({schema_version:'native-source-variant-batch-v1',batch_id:batch,workspace_id:workspace,master_project_id:master,external_provider_calls:0,
  snapshot:{master_revision:2},result:{master_project_mutated:false,publishing_enabled:false,variants:[{project_id:child,name:'<img src=x onerror=attack()>',profile,approval_inherited:false,render_dispatched:false,crop_needs_attention:true}]}});
const page=()=>({schema_version:'native-source-variant-page-v1',workspace_id:workspace,master_project_id:master,external_provider_calls:0,items:[row()],next_cursor:null});
function harness(){const nodes=new Map();class Node{constructor(tag='div'){this.tag=tag;this.value='';this.dataset={};this.listeners={};this.children=[];}
  addEventListener(name,fn){this.listeners[name]=fn;}replaceChildren(){this.children=[];}append(...children){this.children.push(...children);}
  querySelectorAll(tag){return this.children.flatMap(child=>[...(child.tag===tag?[child]:[]),...child.querySelectorAll(tag)]);}}
  const root={getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);},createElement(tag){return new Node(tag);}},get=id=>root.getElementById(id);
  const state={project:{id:master,revision:2,document:{canonical_timeline:{version:1,snapshot:{metadata:{native_auto_edit_schema:'native-auto-edit-timeline-v1'}}}}},workspace_id:workspace,canEdit:true,dirty:false,busy:false};
  let handler=async path=>path==='/api/auto-edit/variant-profiles'?{schema_version:'native-source-variant-catalog-v1',profiles:[profile]}:page();const calls=[],messages=[],opened=[];
  const controller=initializeNativeVariants({root,getState:()=>state,api:async(...args)=>{calls.push(args);return handler(...args);},onMessage:(...args)=>messages.push(args),onOpen:async id=>opened.push(id),uuid:()=> 'explicit-fixture'});
  return{get,state,calls,messages,opened,controller,handler(fn){handler=fn;}};
}
test('catalog and history reads are explicit with literal text and no creation or provider call',async()=>{
  const h=harness();assert.equal(supportsNativeVariants({}),false);assert.equal(supportsNativeVariants({capabilities:{native_source_variants:true}}),true);assert.equal(h.calls.length,0);
  await h.controller.catalog();assert.equal(h.get('native-variants-choices').children[0].textContent,'Shorts <script> ');await h.controller.read();
  const section=h.get('native-variants-history').children[0];assert.ok(section.children[2].textContent.startsWith('<img src=x onerror=attack()>'));
  await section.children[2].children[0].listeners.click();assert.deepEqual(h.opened,[child]);assert.equal(h.calls.length,2);assert.ok(h.calls.every(call=>call[1]===undefined));
});
test('selected variants have stable retry keys and require saved source timeline and editing permission',async()=>{
  const h=harness();await h.controller.catalog();h.handler(async()=>row());await h.controller.create();const payload=h.calls[1][1];
  assert.equal(payload.crop_policy,'center_attention');assert.deepEqual(payload.profile_refs,['youtube-shorts@1']);assert.equal(payload.expected_version,1);
  await h.controller.create();assert.equal(h.calls[2][1].request_key,payload.request_key);h.state.canEdit=false;await h.controller.create();assert.equal(h.calls.length,3);
  h.state.canEdit=true;h.state.dirty=true;await h.controller.create();assert.equal(h.calls.length,3);h.state.dirty=false;delete h.state.project.document.canonical_timeline;
  await h.controller.create();assert.equal(h.calls.length,3);
});
test('late project reads and inherited approval or real publishing contradictions reject',async()=>{
  const h=harness();let resolve;h.handler(()=>new Promise(done=>{resolve=done;}));const pending=h.controller.read();h.state.project={...h.state.project,id:'9'.repeat(32)};h.controller.sync();resolve(page());await pending;
  assert.equal(h.get('native-variants-history').children.length,0);h.state.project.id=master;h.controller.sync();
  for(const mutate of [value=>value.result.variants[0].approval_inherited=true,value=>value.result.publishing_enabled=true,value=>value.workspace_id='wsp_outside']){
    const value=row();mutate(value);h.handler(async()=>({...page(),items:[value]}));await h.controller.read();assert.equal(h.get('native-variants-history').children.length,0);assert.equal(h.messages.at(-1)[1],true);}
});
