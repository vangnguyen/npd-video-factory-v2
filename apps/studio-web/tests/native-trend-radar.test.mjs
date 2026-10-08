import test from 'node:test';import assert from 'node:assert/strict';
import {radarViews,supportsTrendRadar,publicLink,validateRadarPage,radarCard,mountRadar,learningSummary} from '../trend-radar.mjs';
const WS='wsp_radar_fixture',ID='a'.repeat(32),SHA='b'.repeat(64);
function item(){return {id:ID,sha256:SHA,record_type:'assessment',workspace_id:WS,payload:{mock:true,automatic_production:false,cluster_id:'c'.repeat(32),signal_ids:[],
  cluster_snapshot:{payload:{topic:'AI <img onerror=fixture> educational video',lifecycle:'breakout',platforms:['youtube','tiktok'],signal_ids:['d'.repeat(32)],first_observed_at:'2026-10-01T00:00:00Z',last_observed_at:'2026-10-08T00:00:00Z'}},
  ranking:{estimated:true,recommendation_only:true,autonomous_execution:false,personalized_planning_score:72,history_state:'insufficient_data'},score:{total_score:72}}};}
function page(){return {schema_version:'native-trend-radar-page-v1',workspace_id:WS,items:[item()],automatic_production:false,publishing_enabled:false,next_offset:null};}
class Node{constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.attributes={};this.dataset={};this.checked=false;this._value='';}
  get value(){return this._value||(this.tagName==='SELECT'?this.children[0]?.value||'':'');}set value(v){this._value=String(v);}
  append(...children){this.children.push(...children);}replaceChildren(...children){this.children=children;}setAttribute(n,v){this.attributes[n]=String(v);}
  addEventListener(n,v){this.listeners[n]=v;}walk(){return [this,...this.children.flatMap(v=>v.walk())];}}
function harness(permissions=['read','edit','manage']){
  const root=new Node(),ids=['message','provider','query','country','language','fixture-ack','collect','collections','channel','platform','objective','learning','days','weights','similarity','gap','refresh','save-learning','learning-state','views','results','more','detail','reload','filter-platform','filter-niche','filter-format','source-state'];
  for(const id of ids){const node=new Node(['provider','channel','platform','objective','learning','filter-platform','filter-format'].includes(id)?'select':'div');node.id='radar-'+id;root.append(node);}
  const dom={createElement:t=>new Node(t),getElementById:id=>root.walk().find(v=>v.id===id)},$=id=>dom.getElementById('radar-'+id);
  $('platform').value='youtube';$('objective').value='awareness';$('days').value='30';$('similarity').value='.34';$('gap').value='7';
  const session={capabilities:{native_trend_radar:true},access:{workspace_id:WS,permissions}},calls=[],navigation=[];let override=null;
  const api=async(path,options)=>{calls.push([path,options]);if(override){const result=await override(path,options);if(result!==undefined)return result;}
    if(path==='/api/trends/providers')return {workspace_id:WS,providers:[{provider_key:'fixture-radar',display_name:'Explicit fixture',status:'healthy',authorized_access:true,source_type:'fixture'}]};
    if(path==='/api/channel-profiles')return {profiles:[{profile_ref:'ai-education-reference@1',name:'AI educational fixture'}]};
    if(path==='/api/trends/collections'||path==='/api/trends/learning')return {workspace_id:WS,items:[]};
    if(path.startsWith('/api/trends/radar?'))return page();if(path.startsWith('/api/trends/records/'))return {record:item(),sha256:SHA,signals:[]};
    if(path==='/api/trends/handoff')return {record_type:'handoff',workspace_id:WS,payload:{research_run_id:'e'.repeat(32),production_dispatch:false}};
    return {explicit_fixture:true};};
  const controller=mountRadar({dom,api,session,newKey:()=> 'explicit-radar-key-'+calls.length,navigate:url=>navigation.push(url)});
  return {root,dom,$,calls,navigation,controller,override:fn=>{override=fn;},choose:()=> $('results').children[0].children.find(v=>v.textContent==='Chọn để nghiên cứu & tạo ý tưởng')};
}
test('eight views strict capability scope estimates and HTTPS reference safety',()=>{
  assert.equal(radarViews.length,8);assert.equal(supportsTrendRadar({capabilities:{native_trend_radar:'true'}}),false);assert.equal(validateRadarPage(page(),WS).items.length,1);
  for(const mutate of [v=>v.workspace_id='wsp_other_fixture',v=>v.publishing_enabled=true,v=>v.items[0].payload.ranking.autonomous_execution=true,v=>v.items[0].payload.ranking.personalized_planning_score=NaN,v=>v.items[0].sha256='bad']){const v=page();mutate(v);assert.throws(()=>validateRadarPage(v,WS));}
  for(const link of ['javascript:alert(1)','https://user:secret@example.com','http://example.com','https://example.com/#private'])assert.equal(publicLink(link),null);
});
test('cards render provider topic literally and read-only selection cannot invoke callback',async()=>{
  let selected=0;const dom={createElement:t=>new Node(t)},card=radarCard(dom,item(),{onSelect:()=>selected++});assert.match(card.children[0].textContent,/<img onerror=fixture>/);assert.equal(card.children[0].innerHTML,undefined);
  const choose=card.children.at(-1);assert.equal(choose.disabled,true);await choose.listeners.click();assert.equal(selected,0);
});
test('page startup renders shared results using only reads and no implicit source collection',async()=>{
  const h=harness();assert.equal(h.calls.length,0);await h.controller.load();assert.ok(h.calls.length>=5);assert.equal(h.calls.filter(v=>v[1]?.method==='POST').length,0);
  assert.equal(h.$('views').children.length,8);assert.equal(h.choose().disabled,false);assert.equal(h.$('collect').disabled,true);assert.match(h.$('results').children[0].children[0].textContent,/<img/);h.controller.close();
});
test('explicit selection preserves exact request after lost reply and never automatically repeats',async()=>{
  const h=harness();await h.controller.load();let posts=0;h.override(async(path,options)=>{if(path==='/api/trends/handoff'&&options){posts++;if(posts===1)throw Error('EXPLICIT LOST REPLY FIXTURE');}});
  await h.choose().listeners.click();assert.equal(posts,1);assert.equal(h.navigation.length,0);const first=h.calls.find(v=>v[1]?.method==='POST')[1].body;
  await h.choose().listeners.click();assert.equal(posts,2);assert.equal(h.calls.filter(v=>v[1]?.method==='POST')[1][1].body,first);assert.deepEqual(JSON.parse(first),{assessment_id:ID,expected_sha256:SHA,acknowledged:true,request_key:JSON.parse(first).request_key});
  assert.deepEqual(h.navigation,['/intelligence?run='+'e'.repeat(32)]);h.controller.close();
});
test('viewer can inspect evidence but all mutation handlers refuse before network writes',async()=>{
  const h=harness(['read']);await h.controller.load();assert.equal(h.choose().disabled,true);
  for(const id of ['refresh','collect','save-learning']){await h.$(id).listeners.click();assert.equal(h.$(id).disabled,true);}
  assert.equal(h.calls.filter(v=>v[1]?.method==='POST').length,0);await h.$('results').children[0].children.at(-2).listeners.click();assert.equal(h.$('detail').hidden,false);h.controller.close();
});
test('changing views reads current channel platform and objective without making a production request',async()=>{
  const h=harness();await h.controller.load();await h.$('views').children[2].listeners.click();const path=h.calls.at(-1)[0];assert.match(path,/view=breakout/);assert.match(path,/target_platform=youtube/);assert.match(path,/objective=awareness/);
  assert.equal(h.calls.filter(v=>v[1]?.method==='POST').length,0);assert.equal(h.$('views').children[2].attributes['aria-selected'],'true');h.controller.close();
});
function learned(){return{schema_version:'native-trend-radar-record-v1',record_type:'learning',workspace_id:WS,id:'f'.repeat(32),payload:{schema_version:'native-qualified-learning-feedback-v1',scope:{mock:true,channel_profile_ref:'ai-education-reference@1',platform:'youtube'},mock:true,real_audience_observation:false,
  observation_count:6,recommendation_only:true,automatic_application:false,provider_calls:0,publishing_enabled:false,source_binding:{learning_id:'nols_'+'1'.repeat(32),learning_sha256:SHA}}};}
test('qualified and legacy summaries use their own bounded count and honest source labels',()=>{assert.deepEqual(learningSummary(learned(),WS),{count:6,label:'Mô phỏng API',qualified:true});const real=learned();real.payload.mock=real.payload.scope.mock=false;real.payload.real_audience_observation=true;assert.equal(learningSummary(real,WS).label,'Quan sát API nền tảng');
  const legacy={schema_version:'native-trend-radar-record-v1',record_type:'learning',workspace_id:WS,payload:{scope:{mock:true,real_audience_observation:false},observations:[],recommendation_only:true,autonomous_execution:false}};assert.deepEqual(learningSummary(legacy,WS),{count:0,label:'Thử nghiệm',qualified:false});});
test('qualified schema removal relabel source digest counts and provider or application flags fail closed',()=>{for(const change of[v=>delete v.payload.schema_version,v=>v.workspace_id='foreign',v=>v.payload.mock=1,v=>v.payload.real_audience_observation=true,v=>v.payload.observation_count='6',v=>v.payload.observation_count=101,v=>v.payload.provider_calls=1,v=>v.payload.automatic_application=true,v=>v.payload.source_binding.learning_sha256='bad']){const v=learned();change(v);assert.throws(()=>learningSummary(v,WS));}});
test('Radar loads qualified history without assuming legacy observations array or collecting signals',async()=>{const h=harness();h.override(async path=>path==='/api/trends/learning'?{workspace_id:WS,items:[learned()]}:undefined);await h.controller.load();assert.match(h.$('learning').children[1].textContent,/Mô phỏng API/);assert.match(h.$('learning').children[1].textContent,/6/);assert.equal(h.calls.filter(v=>v[1]?.method==='POST').length,0);h.controller.close();});
