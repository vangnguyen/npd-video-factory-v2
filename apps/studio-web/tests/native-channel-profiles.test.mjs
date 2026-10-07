import test from 'node:test';
import assert from 'node:assert/strict';
import {selections,defaults,initializeNativeChannels} from '../native-channel-profiles.mjs';
function catalog(){const profile={profile_ref:'ai-education-reference@1',name:'AI <script> · Tiếng Việt',content_profile_id:'ai-education',niche_profile:{niche:'technology',name:'Công nghệ'},
  brand_id:'vf-ai-education',video_template_id:'ai-education-30',duration_mode:'fit_narration_preserve_voice_speed',
  publishing_profile:{enabled:false,credentials_configured:false},analytics_profile:{enabled:false,provider_status:'NOT_CONFIGURED'}};
  return {schema_version:'native-channel-profile-catalog-v1',publishing_enabled:false,external_dispatches:0,selections:[{schema_version:'native-channel-selection-v1',profile,publishing_enabled:false,external_dispatches:0,paid_operations:0,
    brand_template:{brand:{id:profile.brand_id},template:{id:profile.video_template_id,aspect_ratio:'9:16'}}}]};}
function harness(){class Node{constructor(){this.value='';this.listeners={};this.children=[];this.dataset={};this.parentElement={after:node=>{note=node;}};}
  append(...children){this.children.push(...children);}prepend(...children){this.children.unshift(...children);}replaceChildren(...children){this.children=children;}addEventListener(name,fn){this.listeners[name]=fn;}}
  let note;const grid=new Node(),dom={querySelector:()=>grid,createElement:()=>new Node()},state={project:null,busy:false,canEdit:true},calls=[],updates=[],messages=[];
  let handle=async()=>catalog();const controller=initializeNativeChannels({dom,getState:()=>state,api:async path=>{calls.push(path);return handle();},onDefaults:value=>updates.push(value),onMessage:(...value)=>messages.push(value)});
  return {controller,state,calls,updates,messages,select:grid.children[0].children[0],note:()=>note,handler:value=>{handle=value;}};
}
test('profile read and literal names require explicit selection before default application or creation payload',async()=>{
  const h=harness();assert.equal(h.calls.length,0);assert.deepEqual(h.controller.request(),{});await h.controller.load();assert.deepEqual(h.calls,['/api/channel-profiles']);assert.deepEqual(h.updates,[]);
  assert.equal(h.select.children[1].textContent,'AI <script> · Tiếng Việt');h.select.value='ai-education-reference@1';h.select.listeners.change();
  assert.deepEqual(h.updates,[defaults(catalog().selections[0])]);assert.deepEqual(h.controller.request(),{channel_profile_ref:'ai-education-reference@1'});
  h.controller.clear();assert.deepEqual(h.controller.request(),{});assert.equal(h.calls.length,1);
});
test('busy read-only and saved project controls never apply defaults or send selected project mutation',async()=>{
  const h=harness();await h.controller.load();h.select.value='ai-education-reference@1';h.state.canEdit=false;h.controller.controls();h.select.listeners.change();assert.equal(h.select.disabled,true);assert.deepEqual(h.updates,[]);assert.deepEqual(h.controller.request(),{});
  h.state.canEdit=true;h.state.busy=true;h.select.listeners.change();assert.deepEqual(h.updates,[]);h.state.busy=false;
  h.state.project={id:'saved',document:{channel_profile:catalog().selections[0]}};h.controller.sync();h.select.listeners.change();assert.deepEqual(h.updates,[]);assert.deepEqual(h.controller.request(),{});assert.match(h.note().textContent,/AI <script>/);
  h.state.project=null;h.controller.sync();assert.equal(h.select.value,'');assert.deepEqual(h.controller.request(),{});
});
test('late older catalogs and publishing or analytics contradictions cannot create new channel choices',async()=>{
  const h=harness();let resolve;h.handler(()=>new Promise(done=>{resolve=done;}));const first=h.controller.load();h.handler(async()=>({...catalog(),selections:[]}));await h.controller.load();resolve(catalog());await first;assert.equal(h.select.children.length,1);
  for(const mutate of [value=>value.publishing_enabled=true,value=>value.selections[0].profile.publishing_profile.enabled=true,
    value=>value.selections[0].profile.analytics_profile.enabled=true,value=>value.selections[0].paid_operations=1]){
    const value=catalog();mutate(value);assert.throws(()=>selections(value));h.handler(async()=>value);await h.controller.load();assert.equal(h.select.children.length,1);assert.equal(h.messages.at(-1)[1],true);
  }
});
