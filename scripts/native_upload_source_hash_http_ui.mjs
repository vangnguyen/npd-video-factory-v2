// Actual signed loopback controller. Fixture DOM/identity; no browser/Owner claim.
import {readFileSync} from 'node:fs';import assert from 'node:assert/strict';
import {initializeNativeMultipartUpload,uploadDigest} from '../apps/studio-web/native-multipart-upload.mjs';
const config=JSON.parse(readFileSync(process.argv[2],'utf8')),calls=[],messages=[],saved=[];
class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.dataset={};this.value='';this.checked=false;this.files=[];}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(n,f){this.listeners[n]=f;}}
const card=new Node('details');card.id='native-multipart-upload-card';const walk=(n,id)=>n.id===id?n:n.children.map(c=>walk(c,id)).find(Boolean),root={getElementById:id=>walk(card,id),createElement:t=>new Node(t)};
const node=name=>root.getElementById('native-multipart-upload-'+name);
const state={workspace_id:config.workspace_id,project:{id:config.project_id,revision:config.revision},canEdit:true,busy:false,active:false,dirty:false};
async function request(path,body,headers={}){const response=await fetch(config.base+path,{method:body===undefined?'GET':'POST',headers:{Cookie:'vf_native_session='+config.cookie,'X-VF-CSRF':config.csrf,'Content-Type':'application/json',...headers},body:body===undefined?undefined:headers['Content-Type']==='application/octet-stream'?body:JSON.stringify(body)});const value=await response.json();assert.equal(response.status,200,JSON.stringify(value));return value;}
const api=async(path,body)=>{calls.push({method:body===undefined?'GET':'POST',path,source_sha256:body?.expected_sha256??null});return request(path,body);};
const binary=async(path,data,headers)=>{calls.push({method:'POST',path,bytes:data.byteLength});return request(path,data,{'Content-Type':'application/octet-stream',...headers});};
const ui=initializeNativeMultipartUpload({api,binary,root,getState:()=>state,onWorking:v=>state.busy=v,onMessage:(...v)=>messages.push(v),onSaved:async v=>{saved.push(v);const value=await request('/api/projects/'+config.project_id);state.project.revision=value.revision;}});
function choose(raw){node('kind').value='subtitle';node('kind').listeners.change();node('mime').value='application/x-subrip';node('file').files=[{name:config.filename,size:raw.byteLength,slice:(a,b)=>({arrayBuffer:async()=>raw.slice(a,b).buffer})}];node('rights').checked=true;ui.controls();}
const first=new Uint8Array(Buffer.from(config.subtitle_hex,'hex')),second=first.slice();second[second.length-2]=second[second.length-2]===46?63:46;assert.equal(first.byteLength,second.byteLength);
const firstSha=await uploadDigest(first),secondSha=await uploadDigest(second);assert.notEqual(firstSha,secondSha);
assert.equal(calls.length,0);choose(first);await ui.createUpload();assert.equal(saved.length,1,JSON.stringify(messages));assert.equal(saved[0].request.expected_sha256,firstSha);assert.equal(saved[0].result.source_sha256,firstSha);const prior=saved[0];
choose(second);await ui.createUpload();assert.equal(saved.length,2,JSON.stringify(messages));assert.equal(saved[1].request.expected_sha256,secondSha);assert.equal(saved[1].result.source_sha256,secondSha);assert.notEqual(saved[1].upload_id,prior.upload_id);assert.notEqual(saved[1].result.asset.id,prior.result.asset.id);
choose(first);await ui.createUpload();assert.equal(saved.length,3,JSON.stringify(messages));assert.equal(saved[2].result.asset.id,prior.result.asset.id);assert.equal(saved[2].result.duplicate,true);assert.equal(saved[2].result.source_sha256,firstSha);
assert.equal(messages.length,0,JSON.stringify(messages));assert.ok(calls.filter(c=>c.source_sha256).every(c=>[firstSha,secondSha].includes(c.source_sha256)));
process.stdout.write(JSON.stringify({scope:'actual_signed_local_HTTP_fixture_DOM_controller',fixture_human:true,browser_rendered:false,Owner_UAT:false,
  same_filename_and_size:true,whole_source_hashes:[firstSha,secondSha],distinct_selected_sources:2,new_assets:saved.filter(r=>!r.result.duplicate).length,same_file_replay_verified:true,calls,receipts:saved,provider_calls:0}));
