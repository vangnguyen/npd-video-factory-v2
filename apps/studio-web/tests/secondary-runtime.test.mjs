import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

class Element {
  constructor(id){this.id=id;this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.options=[];this.dataset={};this.listeners={};this.attributes={};this.classList={add(){},toggle(){},remove(){}};}
  set innerHTML(value){this.html=value;const options=[...value.matchAll(/<option value="([^"]*)"/g)].map(m=>({value:m[1]}));if(options.length){this.options=options;if(!options.some(o=>o.value===this.value))this.value=options[0].value;}}
  get innerHTML(){return this.html||'';}
  addEventListener(name,callback){this.listeners[name]=callback;}
  setAttribute(name,value){this.attributes[name]=value;}
  getAttribute(name){return this.attributes[name];}
  removeAttribute(name){delete this.attributes[name];}
  closest(){return {hidden:false};}
  matches(){return false;}
  querySelectorAll(){return [];}
}
async function withRuntime(page,setup,assertions){
  const html=await readFile(new URL('../'+page+'.html',import.meta.url),'utf8');
  const nodes=new Map([...html.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g)].map(m=>{const node=new Element(m[1]);node.hidden=/\bhidden\b/.test(m[0]);node.disabled=/\bdisabled\b/.test(m[0]);node.checked=/\bchecked\b/.test(m[0]);return [m[1],node];}));
  const globals=['document','window','fetch','location','sessionStorage','localStorage','history'];
  const originals=new Map(globals.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));
  const calls=[],stored=new Map(),context={nodes,calls,html};
  globalThis.document={body:new Element('body'),getElementById:id=>{assert.ok(nodes.has(id),'Missing actual control '+id);return nodes.get(id);},querySelector:()=>null,querySelectorAll:selector=>selector==='button'?[...nodes.values()]:[]};
  globalThis.window={addEventListener(){}};
  globalThis.sessionStorage={getItem:key=>stored.get(key)??null,setItem:(key,value)=>stored.set(key,value),removeItem:key=>stored.delete(key)};
  globalThis.localStorage=globalThis.sessionStorage;globalThis.history={replaceState(){}};globalThis.location={search:''};
  const handler=setup(context);
  globalThis.fetch=async(path,options={})=>{calls.push({path,method:options.method??'GET',headers:options.headers??{},body:options.body?JSON.parse(options.body):null});const result=await handler(path,options);return {ok:result.status===undefined||result.status===200,status:result.status??200,json:async()=>structuredClone(result.value)};};
  try{
    await import('../'+page+'.mjs?secondary-runtime='+Date.now()+'-'+Math.random());
    await assertions(context);
  }finally{for(const [key,descriptor] of originals){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];}}
}
async function settle(check){for(let i=0;i<100;i++){if(check())return;await new Promise(resolve=>setImmediate(resolve));}assert.fail('Page startup did not settle');}
function queueRow(){return {id:'queue-id',project_id:'project-id',title:'Saved <script> title',profile_id:'profile',profile_name:'Hồ sơ đã lưu',related_project:'Dự án',archived:false,stage:'SCRIPT_REVIEW',score:null,source_titles:[],updated_at:'2026-10-06T00:00:00Z',planning:{campaign:'October',planned_date:null,format:'9:16',duration_seconds:45,assigned_to:'',assigned_status:'UNASSIGNED',version:1},priority:{score:60,components:{relevance:60},weights:{relevance:1},duplicate_penalty:0},freshness:{status:'DATE_UNKNOWN',needs_revalidation:true,sources:[]},similarity:{warnings:[],override_current:false},binding_sha256:'fixture-binding'};}
function catalog(){return {profiles:[{id:'profile',name:'Hồ sơ đã lưu',target_audience:'Người xem',tone:'Thông tin',content_style:'Tin',preferred_formats:['9:16'],cta_types:['Xem thêm'],duration_seconds:[45],supported_aspect_ratios:['9:16'],brand_id:'brand',voice:{name:'Thùy Dung'}}],brand_templates:{brands:[{id:'brand',name:'Thương hiệu'}]},priority_configuration:{weights:{relevance:1},duplicate_penalty:20}};}
for(const view of ['dashboard','projects','queue','library']){
  test('Real Production boot opens '+view+' with read-only requests and original batch gates',async()=>{
    await withRuntime('production',()=>{
      globalThis.location.search='?view='+view;
      return path=>path==='/api/session'?{value:{csrf:'fixture-csrf'}}:path==='/api/production/profiles'?{value:catalog()}:path==='/api/production/queue'?{value:{items:[queueRow()]}}:path==='/api/projects?archived=include'?{value:[{id:'project-id',revision:2,document:{name:'Project <unsafe>',duration:45,proposal:{storyboard:[]}},updated_at:'2026-10-06T00:00:00Z'}]}:path==='/api/production/library'?{value:{items:[]}}:{status:404,value:{code:'NOT_FOUND'}};
    },async({nodes,calls})=>{
      await settle(()=>calls.some(c=>c.path==='/api/production/queue')&&!nodes.get('refresh').disabled);
      assert.equal(nodes.get(view+'-view').hidden,false);
      assert.equal(nodes.get('message').hidden,true);
      assert.equal(nodes.get('batch-scripts').disabled,true);assert.equal(nodes.get('batch-storyboards').disabled,true);
      assert.equal(calls.some(c=>c.method==='POST'),false,'Opening any view does not create or approve work');
      assert.equal(calls.some(c=>c.path==='/api/projects?archived=include'),['dashboard','projects'].includes(view));
      assert.equal(calls.some(c=>c.path==='/api/production/library'),view==='library');
      assert.equal(nodes.get('studio-main').attributes['aria-busy'],'false');
      if(view==='dashboard'){assert.match(nodes.get('dashboard-review').innerHTML,/&lt;script&gt;/);assert.match(nodes.get('dashboard-projects').innerHTML,/Project &lt;unsafe&gt;/);}
      if(view==='projects'){assert.match(nodes.get('projects-list').innerHTML,/Project &lt;unsafe&gt;/);assert.equal(nodes.get('projects-count').textContent,'1 dự án');}
      if(view==='library')assert.match(nodes.get('library-list').innerHTML,/Mở dự án/);
      if(view==='queue'){
        nodes.get('stage-filter').value='VIDEO_REVIEW';nodes.get('stage-filter').listeners.change();
        assert.match(nodes.get('queue-list').innerHTML,/Chưa có nội dung phù hợp/);
        nodes.get('stage-filter').value='SCRIPT_REVIEW';nodes.get('stage-filter').listeners.change();
        assert.match(nodes.get('queue-list').innerHTML,/Saved &lt;script&gt; title/);
      }
    });
  });
}

test('AssemblyAI startup and refresh read status without credential/provider submissions',async()=>{
  await withRuntime('assemblyai',()=>path=>path==='/api/session'?{value:{csrf:'fixture-csrf'}}:path==='/api/connections/assemblyai'?{value:{credential_saved:false,connected:false}}:{status:404,value:{}},async({nodes,calls})=>{
    await settle(()=>calls.some(c=>c.path==='/api/connections/assemblyai')&&!nodes.get('connection-refresh').disabled);
    assert.equal(nodes.get('connect').disabled,false);assert.equal(nodes.get('verify-saved').hidden,true);
    assert.equal(nodes.get('connection-state').textContent,'Chưa có khóa');
    nodes.get('assemblyai-key').value='Sensitive fixture text only';
    nodes.get('connection-refresh').listeners.click();
    await settle(()=>calls.filter(c=>c.path==='/api/connections/assemblyai').length===2&&!nodes.get('connection-refresh').disabled);
    assert.equal(calls.every(c=>c.method==='GET'),true);
    assert.equal(nodes.get('connection-message').hidden,true);
  });
});

test('Unknown connection state keeps credential submissions disabled until a successful read',async()=>{
  await withRuntime('assemblyai',()=>path=>path==='/api/session'?{value:{csrf:'fixture-csrf'}}:{status:503,value:{code:'UNAVAILABLE'}},async({nodes,calls})=>{
    await settle(()=>calls.length>=2&&!nodes.get('connection-refresh').disabled);
    assert.equal(nodes.get('connect').disabled,true);
    assert.equal(nodes.get('connection-state').textContent,'Chưa đọc được trạng thái');
    assert.match(nodes.get('connection-message').textContent,/Bấm Làm mới/);
    assert.equal(calls.every(c=>c.method==='GET'),true);
  });
});

for(const page of ['production','native','intelligence','assemblyai']){
  test('Explicit '+page+' Refresh recovers a rotated local session with GET only and keeps write intent explicit',async()=>{
    await withRuntime(page,context=>{
      let valid=false,generation=1;
      context.restart=()=>{valid=false;generation++;};
      return (path,options)=>{
        if(path==='/api/session'){valid=true;return {value:{csrf:'session-fixture-'+generation}};}
        if(!valid)return {status:401,value:{code:'LOCAL_SESSION_REQUIRED'}};
        if(path==='/api/production/profiles')return {value:catalog()};
        if(path==='/api/production/queue')return {value:{items:[{...queueRow(),title:'Queue generation '+generation}]}};
        if(path==='/api/projects'){
          if(options.method==='POST')return {value:{id:'p'.repeat(32),revision:1,document:{name:'Explicit fixture',prompt:'Retained unsaved prompt',input_kind:'prompt',proposal:null,assets:[],documents:[],scene_media:[]},jobs:[],approval:null}};
          return {value:[]};
        }
        if(path==='/api/defaults')return {value:{prompt:'Startup fixture prompt'}};
        if(path==='/api/runtime-status')return {value:{openai_key_saved:false,assemblyai:{connected:false}}};
        if(path==='/api/brand-templates')return {value:{brands:[],templates:[]}};
        if(path==='/api/intelligence/config')return {value:{profiles:[{id:'fixture',name:'Fixture',project_references:[]}],scoring:{weights:{relevance:1}}}};
        if(path==='/api/intelligence/runs'||path==='/api/intelligence/queue')return {value:[]};
        if(path==='/api/connections/assemblyai')return {value:{credential_saved:false,connected:generation===2}};
        return {status:404,value:{code:'FIXTURE_ROUTE_NOT_FOUND'}};
      };
    },async({nodes,calls,restart})=>{
      const refresh=nodes.get(page==='intelligence'?'ci-refresh':page==='assemblyai'?'connection-refresh':'refresh');
      const dataPath=page==='production'?'/api/production/queue':page==='native'?'/api/brand-templates':page==='intelligence'?'/api/intelligence/queue':'/api/connections/assemblyai';
      await settle(()=>calls.some(c=>c.path===dataPath)&&!refresh.disabled);
      assert.equal(calls.filter(c=>c.path==='/api/session').length,1);
      if(page==='native'){nodes.get('prompt').value='Retained unsaved prompt';nodes.get('prompt').listeners.input();}
      const before=calls.length;restart();
      await (refresh.onclick??refresh.listeners.click)();
      await settle(()=>calls.length>before+1&&!refresh.disabled);
      const recovered=calls.slice(before);
      assert.equal(recovered[0].path,'/api/session');
      assert.ok(recovered.length>=2);assert.equal(recovered.every(c=>c.method==='GET'),true,'Refresh must not replay a write/provider/render');
      assert.equal(calls.filter(c=>c.path==='/api/session').length,2);
      if(page==='production')assert.match(nodes.get('queue-list').innerHTML,/Queue generation 2/);
      if(page==='assemblyai')assert.equal(nodes.get('connection-state').textContent,'Đã xác thực kết nối');
      if(page!=='assemblyai')assert.equal(nodes.get(page==='intelligence'?'ci-message':'message').textContent,'Đã làm mới dữ liệu.');
      if(page==='native'){
        assert.equal(nodes.get('prompt').value,'Retained unsaved prompt');
        assert.equal(nodes.get('save-note').textContent,'Có chỉnh sửa chưa lưu. Lưu trước khi tạo nội dung hoặc duyệt.');
        nodes.get('project-name').value='Explicit fixture';
        await nodes.get('save-prompt').listeners.click();
        const explicit=calls.find(c=>c.method==='POST');
        assert.equal(explicit.path,'/api/projects');assert.equal(explicit.headers['X-VF-CSRF'],'session-fixture-2');
        assert.equal(calls.filter(c=>c.method==='POST').length,1,'Only subsequent explicit user action may write');
      }
    });
  });
}



