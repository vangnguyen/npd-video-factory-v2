import test from'node:test';import assert from'node:assert/strict';import{initializeNativeChannelAdmin,validateChannelAdmin,channelAdminRequest}from'../native-channel-admin.mjs';
const H='a'.repeat(64),workspace='wsp_channel_ui';
function profile(){return{profile_ref:'ai-education-reference@1',name:'AI <script> literal',content_profile_id:'ai-education',niche_profile:{profile_ref:'technology-education@1',niche:'technology',name:'Công nghệ',language:'vi',country:'VN',locale:'vi-VN',target_audience:'Người học',tone:'Dễ hiểu',keywords:['AI']},brand_id:'vf-ai-education',video_template_id:'ai-education-30',source_preferences:{subtitle_template_ref:'sentence-clean@v1',audio_processing:{normalize_original_audio:false,normalize_music:false,duck_music:false,original_target_lufs:-16,music_target_lufs:-24,duck_threshold:.02,duck_ratio:8,duck_attack_ms:20,duck_release_ms:250}},publishing_profile:{enabled:false,credentials_configured:false,platforms:['youtube']},analytics_profile:{enabled:false}};}
function page(items=[]){return{schema_version:'native-channel-profile-admin-v1',workspace_id:workspace,items,publishing_enabled:false,external_dispatches:0,choices:{content_profiles:[{id:'ai-education',name:'AI'}],brands:[{id:'vf-ai-education',name:'AI'}],templates:[{id:'ai-education-30',name:'Giải thích'}],subtitle_templates:[{template_ref:'sentence-clean@v1',name:'Câu'}]}};}
class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.value='';this.checked=false;this.open=false;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}setAttribute(k,v){this[k]=v;}addEventListener(k,f){this.listeners[k]=f;}showModal(){this.open=true;}close(){this.open=false;}}
function harness(){const nodes={'native-channel-admin-dialog':new Node('dialog'),'manage-channel-profiles':new Node('button')},dom={getElementById:k=>nodes[k],createElement:t=>new Node(t)},state={workspace_id:workspace,canManage:true,busy:false},calls=[],messages=[];let handler=async(path,body)=>path==='/api/channel-profiles'?{selections:[{profile:profile()}]}:page();
 const ui=initializeNativeChannelAdmin({dom,getState:()=>state,api:async(p,b)=>{calls.push({path:p,body:b});return handler(p,b);},onSaved:async()=>{},onMessage:(...v)=>messages.push(v),newKey:()=> 'owned-ui-profile-request1'});return{ui,state,nodes,calls,messages,handler:f=>handler=f};}
function change(ui,key,value){const f=ui.fields[key];if(typeof value==='boolean'){f.checked=value;f.listeners.change();}else{f.value=value;f.listeners.input();}}
function savedItem(){const p=profile();p.profile_ref='owned-ai@1';return{profile_key:'owned-ai',revision:1,version:1,archived:false,binding_sha256:H,record:{workspace_id:workspace,profile_key:'owned-ai',version:1,profile:p}};}
test('admin DTO refuses foreign scope, enabled publication and malformed bindings',()=>{
 assert.equal(validateChannelAdmin(page(),workspace).items.length,0);for(const mutate of[v=>v.workspace_id='wsp_foreign',v=>v.publishing_enabled=true,v=>v.external_dispatches=1]){const v=page();mutate(v);assert.throws(()=>validateChannelAdmin(v,workspace));}
 const item=savedItem();item.binding_sha256='wrong';assert.throws(()=>validateChannelAdmin(page([item]),workspace));
});
test('owner form uses literal labels and sends one complete scoped draft with source DSP preferences',async()=>{
 const h=harness();await h.ui.load();change(h.ui,'key','owned-ai');change(h.ui,'name','Kênh <img>');change(h.ui,'audience','Người học mới');change(h.ui,'normalize_music',true);change(h.ui,'ack',true);
 let payload;h.handler(async(path,body)=>{if(body){payload=body;const item=savedItem();item.record.profile=body.profile;return{schema_version:'native-channel-profile-mutation-v1',workspace_id:workspace,action:'save',publishing_enabled:false,external_dispatches:0,item};}return path==='/api/channel-profiles'?{selections:[{profile:profile()}]}:page();});await h.ui.mutate('save');assert.equal(payload.profile.profile_ref,'owned-ai@1');assert.equal(payload.profile.name,'Kênh <img>');assert.equal(payload.profile.niche_profile.target_audience,'Người học mới');assert.equal(payload.profile.source_preferences.audio_processing.normalize_music,true);assert.equal(payload.profile.publishing_profile.enabled,false);
 assert.equal(h.calls.filter(v=>v.body).length,1);assert.equal(h.ui.isDirty(),false);
});
test('editor/viewer and busy state cannot mutate or expose owner management',async()=>{
 const h=harness();h.state.canManage=false;h.ui.controls();assert.equal(h.nodes['manage-channel-profiles'].hidden,true);await h.ui.load();assert.equal(h.calls.length,0);assert.throws(()=>channelAdminRequest(h.state,null,profile(),'save','key'));
 h.state.canManage=true;h.state.busy=true;assert.throws(()=>channelAdminRequest(h.state,null,profile(),'save','key'));
});
test('saved revisions use exact binding and lifecycle never carries a profile body',()=>{
 const item=savedItem(),s={workspace_id:workspace,canManage:true};const body=channelAdminRequest(s,item,null,'archive','owned-request');assert.equal(body.expected_revision,1);assert.equal(body.expected_binding_sha256,H);assert.equal(body.profile,null);
});
test('dirty draft cannot be replaced by another list selection and uncertain acknowledgement cannot replay',async()=>{
 const h=harness();h.handler(async path=>path==='/api/channel-profiles'?{selections:[{profile:profile()}]}:page([savedItem()]));await h.ui.load();change(h.ui,'key','owned-ai');change(h.ui,'name','Draft');h.ui.list.value='owned-ai';h.ui.list.listeners.change();assert.equal(h.ui.fields.name.value,'Draft');assert.equal(h.messages.at(-1)[1],true);
 change(h.ui,'ack',true);h.handler(async()=>{throw new Error('Unknown write outcome');});await h.ui.mutate('save');const writes=h.calls.filter(v=>v.body).length;assert.equal(writes,1);await h.ui.mutate('save');assert.equal(h.calls.filter(v=>v.body).length,writes);assert.equal(h.ui.save.disabled,true);
});
test('workspace or permission change discards private profile data and ignores a late read',async()=>{
 const h=harness();let finish;h.handler(path=>path==='/api/channel-profiles'?Promise.resolve({selections:[{profile:profile()}]}):new Promise(done=>{finish=done;}));const loading=h.ui.load();h.state.workspace_id='wsp_next';h.ui.controls();finish(page());await loading;assert.equal(h.ui.draft instanceof Function,true);assert.throws(()=>h.ui.draft());assert.equal(h.nodes['native-channel-admin-dialog'].open,false);
});
test('reload and direct save preserve an unconfirmed dirty draft',async()=>{
 const h=harness();await h.ui.load();change(h.ui,'key','owned-ai');change(h.ui,'name','Unsaved owner draft');const reads=h.calls.length;await h.ui.load();assert.equal(h.calls.length,reads);assert.equal(h.ui.fields.name.value,'Unsaved owner draft');await h.ui.mutate('save');assert.equal(h.calls.filter(v=>v.body).length,0);assert.equal(h.ui.isDirty(),true);
});
test('unsafe or foreign write acknowledgements fence the draft until an explicit reload',async()=>{
 for(const corrupt of[v=>v.publishing_enabled=true,v=>v.external_dispatches=1,v=>v.item.record.workspace_id='wsp_foreign',v=>v.item.version=2]){
  const h=harness();await h.ui.load();change(h.ui,'key','owned-ai');change(h.ui,'name','Draft');change(h.ui,'ack',true);
  h.handler(async()=>{const value={schema_version:'native-channel-profile-mutation-v1',workspace_id:workspace,action:'save',publishing_enabled:false,external_dispatches:0,item:savedItem()};corrupt(value);return value;});await h.ui.mutate('save');assert.equal(h.ui.isDirty(),true);assert.equal(h.ui.save.disabled,true);assert.equal(h.calls.filter(v=>v.body).length,1);await h.ui.mutate('save');assert.equal(h.calls.filter(v=>v.body).length,1);
 }
});
