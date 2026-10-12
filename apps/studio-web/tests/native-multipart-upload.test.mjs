import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import {initializeNativeMultipartUpload,validateNativeUpload,uploadDigest,nativeUploadOptionLabel} from '../native-multipart-upload.mjs';
import {filterAssets,assetCard,assetPreview} from '../asset-picker.mjs';
import {mediaLibrary} from '../native.mjs';
const fixture=JSON.parse(readFileSync(new URL('./fixtures/native-multipart-upload-sha-v1.json',import.meta.url),'utf8'));
const records=fixture.records,copy=v=>structuredClone(v),part=v=>copy(v);
const stable=v=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
function harness(record=records.find(r=>r.kind==='subtitle')){
  class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.dataset={};this.value='';this.checked=false;this.files=[];}
    append(...children){this.children.push(...children);}replaceChildren(...children){this.children=children;}addEventListener(name,fn){this.listeners[name]=fn;}}
  const card=new Node('details');card.id='native-multipart-upload-card';card.hidden=true;
  const walk=(n,id)=>n.id===id?n:n.children.map(x=>walk(x,id)).find(Boolean),root={createElement:tag=>new Node(tag),getElementById:id=>walk(card,id)};
  const state={workspace_id:record.initial.workspace_id,project:{id:record.initial.project_id,revision:record.initial.request.revision},canEdit:true,dirty:false,busy:false,active:false};
  const calls=[],messages=[],saved=[],slices=[];let sequence=0;const raw=new Uint8Array(Buffer.from(record.source_hex,'hex'));
  let responder=async(path,body)=>body&&path.endsWith('/complete')?part(record.completed):body?part(record.initial):path.endsWith('/uploads')?
    {schema_version:'native-multipart-upload-page-v1',workspace_id:state.workspace_id,project_id:state.project.id,items:[part(record.received)],truncated:false,publishing_enabled:false}:part(record.received);
  let chunkResponder=async()=>part(record.received);
  const controller=initializeNativeMultipartUpload({root,getState:()=>state,api:async(path,body)=>{calls.push({path,body});return responder(path,body);},
    binary:async(path,data,headers)=>{calls.push({path,bytes:data.byteLength,headers});assert.ok(data.byteLength<=1048576);assert.equal(headers['X-VF-SHA256'],await uploadDigest(data));return chunkResponder(path,data,headers);},
    onWorking:value=>{state.busy=value;},onMessage:(...v)=>messages.push(v),onSaved:async v=>{saved.push(v);state.project.revision++;},uuid:()=> 'owned-node-http-fixture-'+String(++sequence).padStart(3,'0')});
  const node=name=>root.getElementById('native-multipart-upload-'+name);
  function choose(bytes=raw){node('kind').value=record.kind;node('kind').listeners.change();node('mime').value=record.initial.request.content_type;
    node('file').files=[{name:record.initial.request.filename,size:bytes.length,slice:(a,b)=>{slices.push([a,b]);return{arrayBuffer:async()=>bytes.slice(a,b).buffer};}}];
    node('rights').checked=true;node('illustration').checked=record.initial.request.illustration;controller.controls();}
  return{state,card,controller,calls,messages,saved,slices,node,choose,raw,respond:fn=>{responder=fn;},chunk:fn=>{chunkResponder=fn;}};
}
test('fixture is captured from signed local HTTP and all six actual receipts validate without provider or UAT claims',async()=>{
  assert.equal(fixture.fixture_human,true);assert.equal(fixture.provider_calls,0);assert.equal(fixture.owner_uat,false);assert.equal(fixture.browser_rendered,false);
  assert.deepEqual(records.map(r=>r.kind),['video','audio','image','logo','music','subtitle']);
  for(const r of records){const s={workspace_id:r.initial.workspace_id,project:{id:r.initial.project_id}};
    for(const v of[r.initial,r.received,r.completed,r.duplicate])assert.equal(await validateNativeUpload(v,s),v);
    assert.equal(await uploadDigest(Buffer.from(r.source_hex,'hex')),r.completed.result.source_sha256);
    assert.equal(r.completed.result.asset.rights_status,'unknown');assert.equal(r.completed.publishing_enabled,false);assert.equal(r.duplicate.result.duplicate,true);}
});
test('initialization is inert; each of the six explicit uploads uses chunk hashes and the actual immutable receipt',async()=>{
  for(const record of records){const h=harness(record);assert.equal(h.calls.length,0);assert.equal(h.card.hidden,false);h.choose();await h.controller.createUpload();
    assert.equal(h.saved.length,1,JSON.stringify(h.messages));assert.equal(h.calls.length,3);assert.deepEqual(h.saved[0],record.completed);
    const create=h.calls[0].body;assert.equal(create.expected_sha256,record.completed.result.source_sha256);assert.equal(create.rights_confirmed,true);assert.equal(create.kind,record.kind);
    assert.equal(h.calls[1].headers['X-VF-Offset'],'0');assert.equal(h.calls[2].body.expected_parts_sha256,record.received.parts_sha256);
    assert.equal(h.node('rights').checked,false);assert.ok(h.slices.every(([a,b])=>b-a<=1048576));assert.equal(h.node('detail').innerHTML,undefined);}
});
test('pause keeps the persisted chunk and only explicit resume verifies the selected source before finalizing',async()=>{
  const r=records.find(r=>r.kind==='subtitle'),h=harness(r);h.choose();h.chunk(async()=>{h.node('pause').listeners.click();return part(r.received);});
  await h.controller.createUpload();assert.equal(h.saved.length,0);assert.equal(h.calls.length,2);assert.equal(h.controller.currentBinding().upload.status,'receiving');
  assert.match(h.node('status').textContent,/tạm dừng/);await h.controller.resumeUpload();assert.equal(h.saved.length,1,JSON.stringify(h.messages));
  assert.equal(h.calls.filter(c=>c.bytes).length,1);assert.equal(h.calls.filter(c=>c.path.endsWith('/complete')).length,1);assert.equal(h.slices.length,4);
});
test('reopening history cannot resume a same-size same-name source whose persisted prefix changed',async()=>{
  const h=harness();await h.controller.readHistory();const different=h.raw.slice();different[0]^=1;h.choose(different);await h.controller.resumeUpload();
  assert.equal(h.saved.length,0);assert.equal(h.calls.filter(c=>c.bytes||c.body).length,0);assert.match(h.messages.at(-1)[0],/toàn file khác upload/);
});
test('viewer, dirty, active and archived cannot mutate; missing rights prevents creation while history is readable',async()=>{
  for(const flag of ['canEdit','dirty','active','archived','rights']){const h=harness();h.choose();if(flag==='canEdit')h.state.canEdit=false;else if(flag==='archived')h.state.project.archived=true;
    else if(flag==='rights')h.node('rights').checked=false;else h.state[flag]=true;
    await h.controller.createUpload();assert.equal(h.calls.length,0,flag);await h.controller.readHistory();assert.equal(h.calls.length,1);
    if(flag!=='rights'){await h.controller.cancelUpload();assert.equal(h.calls.length,1,flag);}assert.equal(h.saved.length,0);}
});
test('lost create response retains the exact scoped idempotency key for a deliberate retry',async()=>{
  const r=records.find(r=>r.kind==='subtitle'),h=harness();h.choose();let lost=true;
  h.respond(async(path,body)=>{if(path.endsWith('/complete'))return part(r.completed);if(lost){lost=false;throw Error('Owned fixture lost response');}return part(r.initial);});
  await h.controller.createUpload();assert.equal(h.saved.length,0);await h.controller.createUpload();assert.equal(h.saved.length,1,JSON.stringify(h.messages));
  assert.deepEqual(h.calls[0].body,h.calls[1].body);assert.equal(h.calls.filter(c=>c.bytes).length,1);
});

test('same filename and size with different source bytes receive distinct intents after a lost response',async()=>{
  const h=harness();h.respond(async()=>{throw Error('Owned lost create response fixture');});h.choose();await h.controller.createUpload();
  const changed=h.raw.slice();changed[changed.length-2]^=1;h.choose(changed);await h.controller.createUpload();
  assert.equal(h.calls.length,2);const[a,b]=h.calls.map(c=>c.body);
  assert.equal(a.filename,b.filename);assert.equal(a.total_bytes,b.total_bytes);assert.notEqual(a.expected_sha256,b.expected_sha256);assert.notEqual(a.request_key,b.request_key);assert.equal(h.saved.length,0);
});

test('history differentiates same-name uploads by known source SHA and labels legacy partial intent honestly',()=>{
  const a=copy(records.find(r=>r.kind==='subtitle').completed),b=copy(a);b.request.expected_sha256='a'.repeat(64);
  assert.notEqual(nativeUploadOptionLabel(a),nativeUploadOptionLabel(b));assert.match(nativeUploadOptionLabel(a),/Phụ đề SRT\/VTT · đã lưu/);
  const legacy=copy(a);legacy.request.expected_sha256=null;assert.equal(nativeUploadOptionLabel(legacy),nativeUploadOptionLabel(a));
  legacy.status='receiving';legacy.result=null;assert.match(nativeUploadOptionLabel(legacy),/chưa khóa toàn file/);
});

test('an unchanged received prefix cannot authorize a changed unsent tail',async()=>{
  const record=copy(records.find(r=>r.kind==='audio')),bytes=new Uint8Array(1048576+200);bytes.set(Buffer.from(record.source_hex,'hex'));
  record.source_hex=Buffer.from(bytes).toString('hex');record.initial.request.total_bytes=bytes.length;record.initial.request.expected_sha256=await uploadDigest(bytes);
  record.initial.request_sha256=await uploadDigest(new TextEncoder().encode(stable(record.initial.request)));
  record.received.request=copy(record.initial.request);record.received.request_sha256=record.initial.request_sha256;record.received.received_bytes=1048576;
  record.received.parts=[{ordinal:0,offset:0,bytes:1048576,sha256:await uploadDigest(bytes.subarray(0,1048576))}];record.received.parts_sha256=await uploadDigest(new TextEncoder().encode(stable(record.received.parts)));
  const h=harness(record);await h.controller.readHistory();const changed=bytes.slice();changed[changed.length-1]=9;h.choose(changed);await h.controller.resumeUpload();
  assert.equal(h.saved.length,0);assert.equal(h.calls.filter(c=>c.body||c.bytes).length,0);assert.match(h.messages.at(-1)[0],/toàn file khác upload/);
  assert.match(h.node('status').textContent,/toàn file khác upload/);
  assert.equal(h.controller.currentBinding().upload.received_bytes,1048576);assert.equal(h.controller.currentBinding().upload.request.expected_sha256,record.initial.request.expected_sha256);
});

test('changing the selected file clears the prior rights acknowledgement',()=>{
  const h=harness();h.choose();assert.equal(h.node('rights').checked,true);h.node('file').listeners.change();
  assert.equal(h.node('rights').checked,false);assert.equal(h.node('upload').disabled,true);assert.equal(h.calls.length,0);
});

test('pause and project changes during file hashing do not initialize or send upload bytes',async()=>{
  for(const change of['pause','project']){
    const h=harness();h.choose();const f=h.node('file').files[0],slice=f.slice;
    f.slice=(a,b)=>({arrayBuffer:async()=>{if(change==='pause')h.node('pause').listeners.click();else h.state.project={id:'e'.repeat(32),revision:1};return slice(a,b).arrayBuffer();}});
    await h.controller.createUpload();assert.equal(h.calls.length,0);assert.equal(h.saved.length,0);
    if(change==='pause')assert.match(h.node('status').textContent,/tạm dừng kiểm tra/);else assert.equal(h.node('rights').checked,false);
  }
});

test('historical nullable-SHA completed receipts remain readable but a different file cannot reuse them',async()=>{
  const old=JSON.parse(readFileSync(new URL('./fixtures/native-multipart-upload.json',import.meta.url),'utf8')).records.find(r=>r.kind==='subtitle');
  const h=harness(old);h.respond(async(path)=>path.endsWith('/uploads')?{schema_version:'native-multipart-upload-page-v1',workspace_id:h.state.workspace_id,project_id:h.state.project.id,items:[copy(old.completed)],truncated:false,publishing_enabled:false}:copy(old.completed));
  await h.controller.readHistory();h.choose();await h.controller.resumeUpload();assert.equal(h.calls.filter(c=>c.body||c.bytes).length,0);assert.match(h.node('status').textContent,/đã hoàn tất/);
  const changed=h.raw.slice();changed[0]^=1;h.choose(changed);await h.controller.resumeUpload();assert.equal(h.calls.filter(c=>c.body||c.bytes).length,0);assert.match(h.messages.at(-1)[0],/toàn file khác upload/);
});
test('late history from a former project is discarded without installing assets or saved upload selection',async()=>{
  const r=records.find(r=>r.kind==='subtitle'),h=harness();let resolve;h.respond(()=>new Promise(done=>{resolve=done;}));
  const work=h.controller.readHistory();await Promise.resolve();h.state.project={id:'a'.repeat(32),revision:1};h.controller.sync();
  resolve({schema_version:'native-multipart-upload-page-v1',workspace_id:r.initial.workspace_id,project_id:r.initial.project_id,items:[part(r.received)],truncated:false,publishing_enabled:false});
  await work;assert.equal(h.controller.currentBinding().upload,null);assert.equal(h.saved.length,0);assert.equal(h.node('detail').textContent,'');
});
test('foreign scope, altered request/parts, private fields and substituted completed receipts are rejected',async()=>{
  const r=records.find(r=>r.kind==='subtitle'),s={workspace_id:r.initial.workspace_id,project:{id:r.initial.project_id}};
  const mutations=[v=>v.workspace_id='foreign',v=>v.project_id='a'.repeat(32),v=>v.publishing_enabled=true,v=>v.request.revision++,v=>v.request.extra='unapproved',
    v=>v.parts[0].sha256='a'.repeat(64),v=>v.parts[0].offset=1,v=>v.received_bytes--,v=>v.result.asset.source_sha256='a'.repeat(64),
    v=>v.result.asset.id='../private.wav',v=>v.result.asset.canonical_role='music',v=>v.result.source_bytes++,v=>v.result.publishing_enabled=true,
    v=>v.result.asset.access_token='NEVER',v=>v.idempotent_replay=1,v=>v.deadline='invalid'];
  for(const mutate of mutations){const v=part(r.completed);mutate(v);await assert.rejects(validateNativeUpload(v,s));}
});
test('a mismatched chunk reply is rejected before finalize or canonical project reload',async()=>{
  const r=records.find(r=>r.kind==='subtitle'),h=harness();h.choose();h.chunk(async()=>({...part(r.received),upload_id:'nup_'+'a'.repeat(32)}));
  await h.controller.createUpload();assert.equal(h.saved.length,0);assert.equal(h.calls.length,2);assert.match(h.messages.at(-1)[0],/không đúng upload/);
});
test('source confirmation survives a full received journal after reload while a new project clears upload choice',async()=>{
  const h=harness();await h.controller.readHistory();h.choose();await h.controller.resumeUpload();assert.equal(h.saved.length,1,JSON.stringify(h.messages));
  assert.equal(h.calls.filter(c=>c.bytes).length,0);h.state.project={id:'f'.repeat(32),revision:1};h.controller.sync();assert.equal(h.controller.currentBinding().upload,null);
  assert.equal(h.node('rights').checked,false);assert.equal(h.node('detail').textContent,'');
});
test('all six actual upload assets remain browsable while scene-source filters exclude audio and subtitles',()=>{
  const assets=records.map(r=>r.completed.result.asset);assert.equal(filterAssets(assets).length,6);
  assert.equal(filterAssets(assets,{kind:'visual'}).length,3);assert.equal(filterAssets(assets,{kind:'audio'}).length,2);
  assert.equal(filterAssets(assets,{kind:'subtitle'}).length,1);assert.equal(mediaLibrary({assets}).length,3);
  for(const kind of ['audio','subtitle']){const a=assets.find(a=>a.kind===kind),card=assetCard(a,{thumbnail:'/unused'});
    assert.doesNotMatch(card,/<img/);assert.match(card,/data-asset-choose=[^>]+disabled/);}
});
test('audio uses an audio player and Vietnamese subtitle preview escapes text while preserving actual cue evidence',()=>{
  const a=records.find(r=>r.kind==='audio').completed.result.asset,s=records.find(r=>r.kind==='subtitle').completed.result.asset;
  assert.match(assetPreview(a,'/api/assets/'+a.id+'/file'),/<audio controls/);assert.doesNotMatch(assetPreview(a,'/api/assets/'+a.id+'/file'),/<img|<video/);
  assert.match(assetPreview(s,'/unused'),/Cần Giờ/);assert.doesNotMatch(assetPreview(s,'/unused'),/<img|<video|<audio/);
  const unsafe=copy(s);unsafe.cues[0].text='<script>alert(1)</script>';assert.doesNotMatch(assetPreview(unsafe,'/unused'),/<script>/);
  assert.match(assetPreview(unsafe,'/unused'),/&lt;script&gt;/);
});
