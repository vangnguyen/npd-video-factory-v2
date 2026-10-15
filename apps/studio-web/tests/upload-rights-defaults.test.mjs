import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

// Execute the shipped upload handler. Only the surrounding DOM/transport is a
// fixture; the actual emitted initialization body is the observation.
const source=readFileSync(new URL('../multi-input.mjs',import.meta.url),'utf8').replaceAll('\r\n','\n');
const start=source.indexOf('$("mvp-upload").addEventListener("change",');
const end=source.indexOf('$("mvp-draft").addEventListener',start);
assert.ok(start>=0&&end>start);
function harness(type,ack=true){
 const calls=[],listeners=new Map(),nodes={
  'mvp-upload':{files:[Object.assign(new Blob(['fixture-only'],{type}),{name:'source.bin'})],value:'chosen',
   addEventListener:(name,fn)=>listeners.set(name,fn)},
  'mvp-rights':{checked:ack},
 };
 let refreshes=0;
 const api=async(path,options)=>{calls.push({path,method:options.method,body:JSON.parse(options.body)});
  return path.endsWith('/init')?{upload_id:'upl_client_fixture',total_parts:1,part_size_bytes:65536}:{};};
 const uploadFetch=async(path,options)=>{calls.push({path,method:options.method,body:options.body});return {ok:true};};
 new Function('$','getState','api','uploadFetch','refresh','toast','guarded',source.slice(start,end))(
  id=>nodes[id],()=>({projectId:'prj_client_fixture'}),api,uploadFetch,async()=>{refreshes++;},()=>{},fn=>fn);
 return {calls,nodes,run:()=>listeners.get('change')(),refreshes:()=>refreshes};
}
for(const [mime,kind] of [['image/jpeg','image'],['image/png','image'],['video/mp4','video'],['audio/wav','music'],['audio/mpeg','music']]){
 test('generic right-to-use checkbox never asserts ownership: '+mime,async()=>{
  const h=harness(mime);assert.equal(h.calls.length,0);await h.run();
  assert.equal(h.calls[0].path,'/api/v1/uploads/init');
  assert.equal(h.calls[0].body.rights_status,'unknown');
  assert.equal(h.calls[0].body.media_kind,kind);
  assert.equal(h.calls.filter(c=>c.path.endsWith('/init')).length,1);
  assert.equal(h.refreshes(),1);assert.equal(h.nodes['mvp-upload'].value,'');
 });
}
test('generic upload still requires explicit right-to-use acknowledgement',async()=>{
 const h=harness('video/mp4',false);await assert.rejects(h.run(),/quyền/);assert.equal(h.calls.length,0);
});
