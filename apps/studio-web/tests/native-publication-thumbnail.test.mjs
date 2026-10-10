// Original locally rendered PNG metadata, with an explicit synthetic final review.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {nativePublicationIntent,initializeNativePublications} from '../native-publications.mjs';
const fixture=JSON.parse(fs.readFileSync(new URL('./fixtures/native-render-thumbnail-rights-v1.json',import.meta.url)));
const values={platform:'youtube',title:'Explicit synthetic thumbnail distribution',description:'',caption:'',hashtags:'',privacy:'private',scheduled:''};
const copy=v=>structuredClone(v);
function state(){const p=copy(fixture.project),j=p.jobs.find(j=>j.kind==='render'&&j.status==='succeeded'&&j.revision===p.revision);
  j.final_review={id:'explicit-synthetic-final-review',decision:'approve',revision:p.revision,artifact_sha256:j.result.qc.final_sha256};
  return{project:p,workspace_id:fixture.selection.workspace_id,canEdit:true,canManage:true,dirty:false,busy:false};}
function row(s){const j=s.project.jobs[0];return{schema_version:'native-publication-v1',publication_id:'npub_'+'c'.repeat(32),project_id:s.project.id,
  mock:true,external_action:false,publish_enabled:false,status:'awaiting_publish_approval',request_fingerprint:'d'.repeat(64),approval:null,receipt:null,
  snapshot:{final_sha256:j.result.qc.final_sha256,request:{revision:s.project.revision,platform:'youtube',mode:'dry_run',metadata:{title:'Explicit synthetic thumbnail request',thumbnail_asset_id:fixture.selection.thumbnail_asset_id}},validation:{status:'passed'}}};}
function harness(){const nodes=new Map();class Node{constructor(){this.value='';this.checked=false;this.dataset={};this.listeners={};this.children=[];}
  addEventListener(n,f){this.listeners[n]=f;}replaceChildren(...v){this.children=v;}append(n){this.children.push(n);}}
  const root={getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);},createElement(){return new Node();}},get=id=>root.getElementById('native-publish-'+id);
  let thumbnail=copy(fixture.selection),rights=null,handler=async(path,body)=>body?row(s):{schema_version:'native-publication-page-v1',project_id:s.project.id,items:[row(s)],next_cursor:null},count=0;
  const s=state(),calls=[],messages=[];for(const[k,v]of Object.entries(values))get(k).value=v;
  const ui=initializeNativePublications({root,getState:()=>s,getThumbnailSelection:()=>thumbnail,getThumbnailRightsSelection:()=>rights,api:async(...args)=>{calls.push(args);return handler(...args);},onMessage:m=>messages.push(m),uuid:()=>`explicit-thumbnail-fixture-${++count}`});
  return{ui,get,s,calls,messages,handler:f=>{handler=f;},selection:v=>{thumbnail=v;},rights:v=>{rights=v;}};}

test('thumbnail inclusion requires an explicit raw boolean and exact workspace/project/final binding',()=>{
  const s=state(),request=nativePublicationIntent(s,{...values,useThumbnail:true,thumbnailSelection:copy(fixture.selection)},'explicit-thumbnail-intent-key');
  assert.equal(request.metadata.thumbnail_asset_id,fixture.selection.thumbnail_asset_id);assert.equal(request.mode,'dry_run');assert.equal(request.metadata.privacy,'private');
  for(const value of[1,'true',null])assert.throws(()=>nativePublicationIntent(s,{...values,useThumbnail:value,thumbnailSelection:fixture.selection},'fixture'));
  for(const change of[{workspace_id:'wsp_foreign'},{project:{...s.project,id:'a'.repeat(32)}},{dirty:true},{canEdit:false}])assert.throws(()=>nativePublicationIntent({...s,...change},{...values,useThumbnail:true,thumbnailSelection:fixture.selection},'fixture'));
  const wrong=copy(s);wrong.project.jobs[0].id='a'.repeat(32);assert.throws(()=>nativePublicationIntent(wrong,{...values,useThumbnail:true,thumbnailSelection:fixture.selection},'fixture'));
  const changed=copy(s);changed.project.jobs[0].result.qc.final_sha256='e'.repeat(64);changed.project.jobs[0].final_review.artifact_sha256='e'.repeat(64);
  assert.throws(()=>nativePublicationIntent(changed,{...values,useThumbnail:true,thumbnailSelection:fixture.selection},'fixture'));
});

test('default unchecked selection leaves the optional field out of the original request shape',async()=>{
  const h=harness();assert.equal(h.calls.length,0);assert.equal(h.get('thumbnail').checked,false);assert.equal(h.get('ack').checked,false);
  await h.ui.execute('create');assert.equal('thumbnail_asset_id'in h.calls[0][1].metadata,false);
  h.get('thumbnail').checked=true;h.get('thumbnail').listeners.change();await h.ui.execute('create');assert.equal(h.calls[1][1].metadata.thumbnail_asset_id,fixture.selection.thumbnail_asset_id);
  assert.notEqual(h.calls[0][1].request_key,h.calls[1][1].request_key);assert.equal(h.calls.every(([,b])=>b.mode==='dry_run'),true);
});

test('changing the original selected image resets use/publish acknowledgements and fences a late create',async()=>{
  const h=harness();h.get('thumbnail').checked=true;h.get('ack').checked=true;let reply;h.handler(()=>new Promise(r=>{reply=r;}));const pending=h.ui.execute('create');
  const next=copy(fixture.selection);next.thumbnail_asset_id='ast_rthumb_'+'a'.repeat(32);next.snapshot_sha256='a'.repeat(64);h.selection(next);h.ui.controls();
  assert.equal(h.get('thumbnail').checked,false);assert.equal(h.get('ack').checked,false);reply(row(h.s));await pending;
  assert.equal(h.get('history').children.length,0);assert.equal(h.messages.length,0);assert.equal(h.get('read').disabled,false);
});

test('metadata change fences late success/error while the original intent remains recoverable through history',async()=>{
  for(const failure of[false,true]){const h=harness();h.get('thumbnail').checked=true;let resolve,reject;h.handler(()=>new Promise((r,j)=>{resolve=r;reject=j;}));const pending=h.ui.execute('create');
    const originalKey=h.calls[0][1].request_key;h.get('title').value='Explicit changed draft';h.get('title').listeners.change();
    if(failure)reject(new Error('late private failure'));else resolve(row(h.s));await pending;assert.equal(h.messages.length,0);assert.equal(h.get('history').children.length,0);
    h.handler(async()=>({schema_version:'native-publication-page-v1',project_id:h.s.project.id,items:[row(h.s)],next_cursor:null}));await h.ui.read();assert.equal(h.get('history').children.length,1);
    h.handler(async()=>row(h.s));await h.ui.execute('create');assert.notEqual(h.calls.at(-1)[1].request_key,originalKey);assert.equal(h.calls.at(-1)[1].metadata.title,'Explicit changed draft');}
});

test('unknown thumbnail-create outcome retries the same key but never carries final or publication authority',async()=>{
  const h=harness();h.get('thumbnail').checked=true;h.handler(async()=>{throw new Error('unknown fixture reply');});await h.ui.execute('create');h.handler(async()=>row(h.s));await h.ui.execute('create');
  assert.equal(h.calls[0][1].request_key,h.calls[1][1].request_key);const b=h.calls[1][1];assert.equal(b.metadata.thumbnail_asset_id,fixture.selection.thumbnail_asset_id);
  for(const k of['publish_enabled','acknowledged','owner_exception','final_review','rights_status','provider_authorized'])assert.equal(k in b,false);
  assert.equal(h.get('ack').checked,false);assert.equal(h.get('approve').disabled,true);
});

test('a new reviewed rights record starts a fresh explicitly selected review without rewriting the prior blocked request',async()=>{
  const h=harness();h.get('thumbnail').checked=true;h.handler(async()=>({...row(h.s),status:'blocked'}));await h.ui.execute('create');const originalKey=h.calls[0][1].request_key;
  h.get('ack').checked=true;h.rights(copy(fixture.rights[0]));h.ui.controls();assert.equal(h.get('thumbnail').checked,false);assert.equal(h.get('ack').checked,false);assert.equal(h.get('history').children.length,0);
  h.get('thumbnail').checked=true;h.get('thumbnail').listeners.change();await h.ui.execute('create');assert.notEqual(h.calls[1][1].request_key,originalKey);
  assert.equal(h.calls[1][1].metadata.thumbnail_asset_id,fixture.selection.thumbnail_asset_id);assert.equal('owner_exception'in h.calls[1][1],false);
});

test('saved thumbnail request still requires a separate Owner mock publish review and remains read-only for editors',async()=>{
  const h=harness();await h.ui.read();await h.ui.execute('approve');assert.equal(h.calls.length,1);h.get('ack').checked=true;h.s.canManage=false;await h.ui.execute('approve');assert.equal(h.calls.length,1);
  h.s.canManage=true;h.handler(async()=>({...row(h.s),status:'queued'}));await h.ui.execute('approve');assert.equal(h.calls.at(-1)[1].acknowledged,true);assert.equal(h.get('ack').checked,false);
  h.selection(null);h.ui.controls();assert.equal(h.get('thumbnail').disabled,true);assert.equal(h.get('thumbnail').checked,false);
});
