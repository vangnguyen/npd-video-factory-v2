import test from 'node:test';
import assert from 'node:assert/strict';
import {installNativeAccess,nativePermissions,nativeControlPermission} from '../native-access.mjs';
import {mountNativeLogin,submitNativeLogin} from '../native-login.mjs';

function session(role){const permissions={owner:['read','edit','review','manage'],editor:['read','edit'],reviewer:['read','review'],viewer:['read']}[role];return {csrf:'explicit-fixture-csrf',access:{mode:'registry',role,display_name:'<script>Identity fixture</script>',permissions}};}
class Node {
  constructor(tag,id='',data={}){this.tagName=tag.toUpperCase();this.id=id;this.dataset=data;this.children=[];this.attributes={};this.listeners={};this.value='';this.disabled=false;this.readOnly=false;this.hidden=false;}
  setAttribute(k,v){this.attributes[k]=v;}getAttribute(k){return this.attributes[k]??null;}
  append(...nodes){this.children.push(...nodes);}prepend(...nodes){this.children.unshift(...nodes);}
  addEventListener(k,fn){this.listeners[k]=fn;}removeEventListener(k){delete this.listeners[k];}
  closest(){return this;}
}
function dom(nodes=[]){const head=new Node('head'),body=new Node('body'),main=new Node('main'),listeners={};body.append(main);return {head,body,main,listeners,nodes,
  getElementById:id=>[...nodes,...main.children,...main.children.flatMap(n=>n.children)].find(n=>n.id===id),
  createElement:tag=>new Node(tag),querySelector:()=>main,
  querySelectorAll:()=>[...nodes,...main.children.flatMap(n=>n.children).filter(n=>n.tagName==='BUTTON')],
  addEventListener:(k,fn)=>listeners[k]=fn,removeEventListener:k=>delete listeners[k]};}
test('Legacy sessions do not load auth UI or make requests; configured unknown roles fail closed',()=>{
  const doc=dom();for(const value of [undefined,{}, {access:{mode:'loopback_owner',role:'owner'}}, {access:{mode:true}}])assert.equal(installNativeAccess(value,{document:doc}),null);
  assert.equal(doc.head.children.length,0);assert.deepEqual(nativePermissions(session('viewer')),['read']);
  assert.deepEqual(nativePermissions({access:{mode:'registry',role:'unexpected',permissions:['manage']}}),[]);
  assert.deepEqual(nativePermissions({access:{mode:'registry',role:'viewer',permissions:['read','manage']}}),['read']);
});
test('All four roles preserve reading and restrict edit, approval and settings controls independently',()=>{
  for(const role of ['owner','editor','reviewer','viewer']) {
    const read=new Node('button','refresh'),edit=new Node('button','upload-media'),review=new Node('button','approve'),manage=new Node('button','save-cost-policy'),actor=new Node('input','final-reviewer'),filter=new Node('input','projects-search');
    const doc=dom([read,edit,review,manage,actor,filter]);installNativeAccess(session(role),{document:doc,Observer:null});
    assert.equal(read.disabled,false);assert.equal(filter.disabled,false);
    assert.equal(edit.disabled,!['owner','editor'].includes(role));assert.equal(review.disabled,!['owner','reviewer'].includes(role));assert.equal(manage.disabled,role!=='owner');
    if(['owner','reviewer'].includes(role)){assert.equal(actor.readOnly,true);assert.equal(actor.value,session(role).access.display_name);}
    assert.match(doc.main.children[0].children[0].textContent,/<script>/,'Identity uses literal text, not HTML insertion');
  }
});
test('Dynamic controls and later page re-enabling stay denied; capture blocks their handlers',()=>{
  let callback,disconnected=false;
  class Observer{constructor(fn){callback=fn;}observe(){}disconnect(){disconnected=true;}}
  const button=new Node('button','render'),nav=new Node('button','', {studioNav:''}),doc=dom([button,nav]);
  const controller=installNativeAccess(session('viewer'),{document:doc,Observer});
  assert.equal(button.disabled,true);button.disabled=false;callback();assert.equal(button.disabled,true);
  const dynamic=new Node('button','', {sourceTrack:'track'});doc.nodes.push(dynamic);callback();assert.equal(dynamic.disabled,true);
  let prevented=false,stopped=false;doc.listeners.click({target:dynamic,preventDefault(){prevented=true;},stopImmediatePropagation(){stopped=true;}});
  assert.equal(prevented,true);assert.equal(stopped,true);assert.equal(nav.disabled,false);
  controller.dispose();assert.equal(disconnected,true);assert.equal(doc.listeners.click,undefined);
});
test('Navigation and source controls distinguish reading from new work without granting unknown controls',()=>{
  for(const href of ['/settings/assemblyai','/?new=1','/intelligence?new=1','/production?view=library']){const node=new Node('a');node.setAttribute('href',href);assert.equal(nativeControlPermission(node),href.startsWith('/settings')?'manage':href.includes('new=1')?'edit':'read');}
  assert.equal(nativeControlPermission(new Node('button','', {scriptControl:''})),'review');
  assert.equal(nativeControlPermission(new Node('button','', {assetPreview:'asset'})),'read');
  assert.equal(nativeControlPermission(new Node('button','unknown')),'edit');
});
test('Logout revokes the own session with CSRF and never sends a bearer token or retries',async()=>{
  const doc=dom(),calls=[],moves=[];installNativeAccess(session('viewer'),{document:doc,Observer:null,location:{assign:path=>moves.push(path)},fetcher:async(path,options)=>{calls.push({path,options});return {ok:true,status:200};}});
  await doc.getElementById('native-logout').listeners.click();
  assert.deepEqual(moves,['/login']);assert.equal(calls.length,1);assert.equal(calls[0].path,'/api/logout');
  assert.equal(calls[0].options.headers['X-VF-CSRF'],'explicit-fixture-csrf');assert.equal(calls[0].options.body,'{}');
});
test('Actual login form clears the credential before the request settles and uses a fixed Studio destination',async()=>{
  const form=new Node('form','native-login-form'),input=new Node('input','native-token'),button=new Node('button','native-login-submit'),message=new Node('p','native-login-message'),open=new Node('a','native-login-open'),doc=dom([form,input,button,message,open]);
  const calls=[],moves=[];let resolve;
  await mountNativeLogin(doc,async(path,options)=>{calls.push({path,options});if(path==='/api/session')return {ok:false,status:401};return await new Promise(r=>resolve=r);},{assign:path=>moves.push(path)});
  input.value='explicit fixture access credential';const pending=form.listeners.submit({preventDefault(){}});
  assert.equal(input.value,'');assert.equal(button.disabled,true);assert.equal(calls[1].path,'/api/login');assert.equal(calls[1].options.headers.Authorization,undefined);
  assert.deepEqual(JSON.parse(calls[1].options.body),{token:'explicit fixture access credential'});
  resolve({ok:true,status:200});await pending;assert.deepEqual(moves,['/']);assert.equal(button.disabled,false);
});
test('Rejected login never echoes server/private error content, retries, or sends credentials in URLs',async()=>{
  const calls=[];await assert.rejects(submitNativeLogin('explicit fixture',async(path,options)=>{calls.push({path,options});return {ok:false,status:401,json:()=>{throw Error('Private provider detail');}};}),/hết hạn/);
  assert.equal(calls.length,1);assert.equal(calls[0].path,'/api/login');assert.equal(calls[0].options.credentials,'same-origin');
});
