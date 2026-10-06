import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {supportsProductionIntelligence,briefApprovalRequest} from '../intelligence.mjs';

test('Production Intelligence requires an explicit boolean runtime capability; missing legacy flags preserve original approval contract',()=>{
  for(const session of [undefined,{}, {capabilities:{}},{production_intelligence:'true'},{capabilities:{production_intelligence:false},production_intelligence:true}])assert.equal(supportsProductionIntelligence(session),false);
  assert.equal(supportsProductionIntelligence({capabilities:{production_intelligence:true}}),true);
  assert.equal(supportsProductionIntelligence({production_intelligence:true}),true);
  assert.deepEqual(briefApprovalRequest({id:'brief',version:4},false,null,'Fixture reviewer',true),{
    path:'/api/intelligence/briefs/brief/approve',body:{version:4,reviewer:'Fixture reviewer',acknowledged:true}});
  assert.deepEqual(briefApprovalRequest({id:'brief',version:4},true,{binding_sha256:'actual-binding'},'Fixture reviewer',true),{
    path:'/api/production/briefs/brief/approve',body:{version:4,reviewer:'Fixture reviewer',acknowledged:true,binding_sha256:'actual-binding'}});
});

class ElementFixture {
  constructor(id){this.id=id;this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.options=[];this.classList={toggle(){}};}
  set innerHTML(value){this.html=value;const options=[...value.matchAll(/<option value="([^"]*)"/g)].map(m=>({value:m[1]}));if(options.length){this.options=options;if(!options.some(o=>o.value===this.value))this.value=options[0].value;}}
  get innerHTML(){return this.html??'';}
}

async function exerciseRuntime(session){
  // Minimal DOM/HTTP fixtures execute the real module boot and approval callback.
  // These are UI transport contracts, not factual research or human acceptance.
  const html=await readFile(new URL('../intelligence.html',import.meta.url),'utf8');
  const nodes=new Map([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new ElementFixture(m[1])]));
  const navigation=Array.from({length:3},()=>new ElementFixture('phase10-nav'));
  const runId='a'.repeat(32),briefId='b'.repeat(32),sourceId='c'.repeat(32),calls=[];
  let bundle={run:{id:runId,generation:0,status:'IDEAS',query:'DOM fixture source review',context:{source_urls:['https://example.com/fixture'],profile:{id:'vietnam-property'},scoring:{weights:{relevance:1}}}},
    opportunity:{id:'d'.repeat(32),version:1,status:'REVIEWING',production_project_id:null},
    brief:{id:briefId,version:1,status:'DRAFT',approval:null,objective:'Fixture objective',audience:'Fixture audience',angle:'Fixture angle',hook:'Fixture hook',cta:'Fixture CTA',talking_points:['Fixture only'],constraints:['No actual claims'],key_facts:[],source_references:[sourceId]},
    sources:[{id:sourceId,title:'Explicit DOM fixture source',reference:'https://example.com/fixture',timestamp:null,retrieved_at:'2026-10-06T00:00:00Z',text:'Fixture text; not factual research'}],
    findings:[{kind:'UNCERTAIN',claim:'Explicit DOM fixture; not a real finding',timestamp_relevance:'Not evaluated',source_references:[{source_id:sourceId}]}],ideas:[],operations:[]};
  const fields=['document','window','fetch','location','history','localStorage'];
  const originals=new Map(fields.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));
  const supported=supportsProductionIntelligence(session);
  const stored=new Map();
  globalThis.document={getElementById:id=>{assert.ok(nodes.has(id),`Missing actual template element ${id}`);return nodes.get(id);},querySelectorAll:selector=>selector==='[data-phase10-only]'?navigation:selector==='input,select,textarea,button'?[...nodes.values()]:[]};
  globalThis.window={addEventListener(){}};
  globalThis.location={search:'?run='+runId};globalThis.history={replaceState(){}};
  globalThis.localStorage={getItem:key=>stored.get(key)??null,setItem:(key,value)=>stored.set(key,value),removeItem:key=>stored.delete(key)};
  globalThis.fetch=async(path,options={})=>{
    calls.push({path,method:options.method??'GET',body:options.body?JSON.parse(options.body):null});let value,status=200;
    if(path==='/api/session')value={csrf:'explicit-dom-fixture-csrf',...session};
    else if(path==='/api/intelligence/config')value={profiles:[{id:'vietnam-property',name:'Fixture profile',project_references:['https://example.com/fixture']}],scoring:{weights:{relevance:1}}};
    else if(path==='/api/intelligence/runs')value=[{id:runId,query:bundle.run.query}];
    else if(path==='/api/intelligence/runs/'+runId)value=bundle;
    else if(path==='/api/intelligence/queue')value=[];
    else if(path===`/api/production/briefs/${briefId}/preflight`&&supported)value={brief_id:briefId,brief_version:bundle.brief.version,binding_sha256:'fixture-current-binding',item_id:'e'.repeat(32),planning_version:0,human_override_required:false,
      freshness:{status:'DATE_UNKNOWN',needs_revalidation:true},similarity:{warnings:[],warning_sha256:'fixture-warning'},priority:{components:{relevance:50},weights:{relevance:1},score:50,duplicate_penalty:0}};
    else if(path===`/api/${supported?'production':'intelligence'}/briefs/${briefId}/approve`&&options.method==='POST'){
      bundle={...bundle,opportunity:{...bundle.opportunity,status:'APPROVED'},brief:{...bundle.brief,version:2,status:'APPROVED',approval:{reviewer:'DOM CONTRACT FIXTURE'}}};value=bundle;
    }else{status=404;value={code:'ROUTE_NOT_FOUND'};}
    return {ok:status===200,status,json:async()=>structuredClone(value)};
  };
  try{
    await import(`../intelligence.mjs?runtime-contract=${supported?'new':'legacy'}-${Date.now()}`);
    for(let i=0;i<50;i++){if(calls.some(c=>c.path==='/api/intelligence/queue')&&!nodes.get('ci-refresh').disabled)break;await new Promise(resolve=>setImmediate(resolve));}
    assert.equal(nodes.get('ci-message').textContent,undefined,'Boot must not fail on an unsupported optional endpoint');
    assert.equal(nodes.get('ci-brief-card').hidden,false);
    assert.equal(nodes.get('ci-save-brief').disabled,false,'Legacy brief editing remains available');
    assert.equal(nodes.get('ci-generate').disabled,false,'Legacy idea generation remains available');
    assert.equal(nodes.get('ci-production-preflight').hidden,!supported);
    assert.ok(navigation.every(link=>link.hidden===!supported));
    nodes.get('ci-reviewer').value='DOM CONTRACT FIXTURE';nodes.get('ci-reviewer').oninput();
    nodes.get('ci-ack').checked=true;nodes.get('ci-ack').onchange();
    assert.equal(nodes.get('ci-approve-brief').disabled,false,'Original human acknowledgment gate must remain usable');
    await nodes.get('ci-approve-brief').onclick();
    const request=calls.find(c=>c.method==='POST');
    assert.equal(request.path,`/api/${supported?'production':'intelligence'}/briefs/${briefId}/approve`);
    assert.equal(request.body.acknowledged,true);
    if(supported)assert.equal(request.body.binding_sha256,'fixture-current-binding');
    else{assert.equal('binding_sha256' in request.body,false);assert.equal(calls.some(c=>c.path.startsWith('/api/production/')),false,'An old runtime must receive zero Phase10 requests');}
    assert.equal(nodes.get('ci-send').disabled,false,'Approved brief can still enter the certified production bridge');
  }finally{
    for(const [key,descriptor] of originals){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];}
  }
}

test('Real CI module boot and approval preserve Phase9 when the session has no Phase10 capability',async()=>exerciseRuntime({}));
test('Real CI module enables Phase10 preflight only on an explicitly capable server',async()=>exerciseRuntime({capabilities:{production_intelligence:true}}));

test('CI keeps its original stylesheet and has no mandatory Production Intelligence module import',async()=>{
  const [html,css,script]=await Promise.all(['../intelligence.html','../native.css','../intelligence.mjs'].map(path=>readFile(new URL(path,import.meta.url),'utf8')));
  assert.match(html,/href="\/native\.css"/);
  for(const selector of ['sidebar','card','steps','check','hint','actions'])assert.ok(css.includes('.'+selector));
  assert.equal(/^import .*production\.mjs/m.test(script),false);
});
