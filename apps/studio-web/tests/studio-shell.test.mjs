import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {mountStudioShell,loadStudioShellStyles,studioNavigation,studioPage,supportsStudioUX} from '../studio-shell.mjs';
import {installProductionShell,productionView,matchesStage,visibleProjects,visibleVideos,projectStage,libraryFacts,localVideoUrl} from '../production.mjs';
import {installIntelligenceShell,initialResearchRun,ideaStatusName} from '../intelligence.mjs';
import {installConnectionShell} from '../assemblyai.mjs';

// A small DOM fixture exercises actual moves, identity, focus attributes and idempotence.
// It intentionally implements only selectors used by this shell, without a browser/provider.
class Node {
  constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.parentNode=null;this.attributes={};this.dataset={};this.className='';this.textContent='';this.onclick=null;this.classList={add:(...names)=>this.className=[...new Set(this.className.split(' ').filter(Boolean).concat(names))].join(' '),remove:(...names)=>this.className=this.className.split(' ').filter(n=>!names.includes(n)).join(' '),contains:name=>this.className.split(' ').includes(name)};}
  get childNodes(){return this.children;}
  setAttribute(key,value){this.attributes[key]=String(value);if(key==='class')this.className=String(value);}
  getAttribute(key){return this.attributes[key]??null;}
  hasAttribute(key){return key in this.attributes;}
  removeAttribute(key){delete this.attributes[key];}
  remove(){if(this.parentNode){this.parentNode.children=this.parentNode.children.filter(n=>n!==this);this.parentNode=null;}}
  append(...nodes){for(const node of nodes){node.remove();node.parentNode=this;this.children.push(node);}}
  prepend(...nodes){for(const node of [...nodes].reverse()){node.remove();node.parentNode=this;this.children.unshift(node);}}
  replaceChildren(...nodes){for(const child of [...this.children])child.remove();this.append(...nodes);}
  descendants(){return this.children.flatMap(node=>[node,...node.descendants()]);}
  matches(selector){
    if(selector.endsWith(':not([for])'))return !this.hasAttribute('for')&&this.matches(selector.replace(':not([for])',''));
    const attr=selector.match(/\[([a-z-]+)\]$/);if(attr){const name=attr[1],value=name.startsWith('data-')?this.dataset[name.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]:this.getAttribute(name);if(value==null)return false;selector=selector.slice(0,attr.index);}
    const classes=[...selector.matchAll(/\.([a-z-]+)/g)].map(m=>m[1]);if(classes.some(c=>!this.classList.contains(c)))return false;
    const tag=selector.match(/^[a-z]+/);return !tag||this.tagName===tag[0].toUpperCase();
  }
  querySelectorAll(selector){return [...new Set(selector.split(',').flatMap(part=>{const direct=part.trim().startsWith(':scope >');const value=part.trim().replace(/^:scope >\s*/,'');return (direct?this.children:this.descendants()).filter(node=>node.matches(value));}))];}
  querySelector(selector){return this.querySelectorAll(selector)[0]??null;}
}
class Doc extends Node {
  constructor(){super('document');this.head=new Node('head');this.body=new Node('body');this.append(this.head,this.body);}
  createElement(tag){return new Node(tag);}
  createElementNS(_,tag){return new Node(tag);}
  getElementById(id){return this.descendants().find(n=>n.id===id)??null;}
}
function fixture(){
  const doc=new Doc(),add=(parent,tag,classes,id)=>{const node=doc.createElement(tag);node.className=classes||'';if(id)node.id=id;parent.append(node);return node;};
  const aside=add(doc.body,'aside','sidebar'),brand=add(aside,'a','brand'),oldNav=add(aside,'nav'),newProject=add(aside,'button','primary','new-project');
  const label=add(aside,'label','side-label');label.setAttribute('for','project-picker');
  const picker=add(aside,'select','','project-picker'),runtime=add(aside,'div','runtime-card','runtime-status'),footer=add(aside,'div','side-footer');
  const main=add(doc.body,'main','','studio-main'),header=add(main,'header','studio-header'),copy=add(header,'div'),h1=add(copy,'h1');h1.textContent='Current project';
  const actions=add(header,'div','studio-header-actions'),render=add(actions,'button','','render');
  return {doc,aside,brand,oldNav,newProject,picker,runtime,footer,main,header,actions,render,h1};
}

test('Shared navigation is stable across page contexts and New starts an explicit fresh project',()=>{
  assert.deepEqual(studioNavigation.map(g=>g.id),['create','work','library','system']);
  const items=studioNavigation.flatMap(g=>g.items);
  assert.equal(items.find(i=>i.id==='create').href,'/?new=1');
  for(const [id,href] of [['dashboard','/production?view=dashboard'],['projects','/production?view=projects'],['assets','/?view=assets'],['brands','/?view=brands'],['settings','/settings/assemblyai']])assert.equal(items.find(i=>i.id===id).href,href);
  assert.equal(studioPage('project','http://studio.local/?view=assets'),'assets');
  assert.equal(studioPage('project','http://studio.local/?project=kept'),'projects');
  assert.equal(studioPage('queue'),'dashboard');
  assert.equal(studioPage('project','http://studio.local/?new=1'),'create');
  assert.equal(initialResearchRun(new URLSearchParams('new=1'),'prior-run'),null);
  assert.equal(initialResearchRun(new URLSearchParams('run=explicit&new=1'),'prior-run'),'explicit');
  assert.equal(ideaStatusName('SELECTED'),'Đã chọn');
});

test('Shell moves certified Native nodes without duplicating controls or losing handlers',()=>{
  const f=fixture();let clicks=0;f.newProject.onclick=()=>clicks++;
  const result=mountStudioShell({page:'project',document:f.doc});
  assert.equal(result.main,f.main);assert.equal(f.doc.getElementById('new-project'),f.newProject);
  assert.equal(f.doc.getElementById('project-picker'),f.picker);assert.equal(f.doc.getElementById('runtime-status'),f.runtime);
  assert.equal(f.header.querySelector('.studio-header-actions'),f.actions);assert.equal(f.render.parentNode,f.actions);
  f.newProject.onclick();assert.equal(clicks,1);
  assert.equal(f.oldNav.parentNode,null);assert.equal(f.brand.parentNode,null);
  assert.equal(f.runtime.parentNode.className,'studio-diagnostics');assert.equal(f.footer.parentNode,f.runtime.parentNode);
  assert.equal(f.runtime.parentNode.hasAttribute('open'),false,'Diagnostics start collapsed without deleting runtime IDs');
  assert.equal(f.main.getAttribute('tabindex'),'-1');assert.equal(f.h1.textContent,'Current project');
  assert.equal(f.doc.querySelector('.skip-link').href,'#studio-main');
  assert.equal(f.doc.querySelector('.studio-nav-item.active').getAttribute('aria-current'),'page');
  const count=f.doc.descendants().length;
  mountStudioShell({page:'project',document:f.doc});assert.equal(f.doc.descendants().length,count);
  assert.equal(f.doc.descendants().filter(n=>n.id==='new-project').length,1);
  loadStudioShellStyles(f.doc);loadStudioShellStyles(f.doc);
  assert.equal(f.doc.head.children.length,1);assert.equal(f.doc.head.children[0].href,'/studio-shell.css');
});

test('CI primary action moves into PageHeader using the original callback node',()=>{
  const f=fixture(),newResearch=f.doc.createElement('button');newResearch.id='ci-new';newResearch.className='secondary';f.aside.append(newResearch);
  let count=0;newResearch.onclick=()=>count++;
  mountStudioShell({page:'intelligence',document:f.doc});
  assert.equal(newResearch.parentNode,f.actions);newResearch.onclick();assert.equal(count,1);
  assert.equal(newResearch.classList.contains('primary'),true);
});

test('Every secondary page makes zero optional imports/styles on a legacy or false capability',async()=>{
  for(const installer of [installProductionShell,installIntelligenceShell,installConnectionShell]){
    for(const session of [undefined,{}, {capabilities:{}},{capabilities:{native_studio_ux:false}},{capabilities:{native_studio_ux:'true'}}]){
      let imports=0;assert.equal(await installer(session,{},async()=>{imports++;throw Error('Must not load');}),false);assert.equal(imports,0);
    }
  }
  assert.equal(supportsStudioUX({capabilities:{native_studio_ux:true}}),true);
});

test('Capable secondary startup installs a single shared style/header shell and degrades safely when unavailable',async()=>{
  const calls=[];const importer=async()=>({loadStudioShellStyles:()=>calls.push('styles'),mountStudioShell:options=>calls.push(options)});
  assert.equal(await installProductionShell({capabilities:{native_studio_ux:true}},{page:'projects'},importer),true);
  assert.equal(calls[1].page,'projects');assert.equal(calls[0],'styles');
  for(const installer of [installProductionShell,installIntelligenceShell,installConnectionShell])assert.equal(await installer({capabilities:{native_studio_ux:true}},{},async()=>{throw Error('Optional resource unavailable');}),false);
});

test('Production view/filter state distinguishes dashboard, projects and exact human review steps',()=>{
  for(const view of ['dashboard','projects','queue','calendar','library','profiles'])assert.equal(productionView(view),view);
  assert.equal(productionView('unknown'),'queue');
  assert.equal(matchesStage('SCRIPT_REVIEW','@review'),true);assert.equal(matchesStage('VIDEO_REVIEW','@review'),true);
  assert.equal(matchesStage('SCRIPT_DRAFT','@in_progress'),true);assert.equal(matchesStage('PRODUCED','@in_progress'),false);
  assert.equal(matchesStage('VIDEO_REVIEW','SCRIPT_REVIEW'),false);
  const project={id:'p',revision:2,document:{name:'Cần Giờ',proposal:{storyboard:[]}},approval:{revision:1}};
  assert.equal(projectStage(project),'SCRIPT_REVIEW','Stale combined approval is not current production readiness');
  assert.equal(projectStage({...project,approval:{revision:2}}),'READY_TO_PRODUCE');
  assert.equal(projectStage({...project,archived:true},{stage:'PRODUCED'}),'ARCHIVED');
  const projects=[project,{...project,id:'archived',archived:true}],before=JSON.stringify(projects);
  assert.equal(visibleProjects(projects,[],{search:'CẦN GIỜ'}).length,1);
  assert.equal(visibleProjects(projects,[],{archived:true}).length,2);assert.equal(JSON.stringify(projects),before);
});

test('Final Videos displays measured saved resolution only and approved local files stay authoritative',()=>{
  assert.equal(libraryFacts({format:'9:16',duration_seconds:45}),'45.0 giây · 9:16');
  assert.equal(libraryFacts({format:'16:9',duration_seconds:60,width:1920,height:1080}),'60.0 giây · 16:9 · 1920×1080');
  assert.doesNotMatch(libraryFacts({format:'9:16',width:null,height:null}),/1080|1920/);
  assert.equal(localVideoUrl('/api/production/videos/saved-id'),'/api/production/videos/saved-id');
  for(const url of ['javascript:alert(1)','https://example.com/video','/api/production/videos/../../secret',undefined])assert.equal(localVideoUrl(url),null);
  const items=[{title:'Current',profile_name:'Hồ sơ',campaign:'October',approved:true},{title:'Pending',approved:false}];
  assert.deepEqual(visibleVideos(items,{search:'hồ SƠ'}).map(r=>r.title),['Current']);
  assert.deepEqual(visibleVideos(items,{approvedOnly:false}).map(r=>r.title),['Current','Pending']);
});

test('Secondary HTML has no unconditional dependency on assets unavailable from the accepted old server',async()=>{
  for(const page of ['production','intelligence','assemblyai']){
    const [html,script]=await Promise.all(['../'+page+'.html','../'+page+'.mjs'].map(file=>readFile(new URL(file,import.meta.url),'utf8')));
    assert.doesNotMatch(html,/href="\/studio-shell\.css"/);
    assert.doesNotMatch(script,/import\s+[^\n]+from\s+['"]\.\/studio-shell/);
    assert.match(script,/capabilities\?\.native_studio_ux !== true/);
    assert.match(html,/<main id="studio-main" tabindex="-1">/);
    assert.match(html,/page-header/);
  }
  const css=await readFile(new URL('../studio-shell.css',import.meta.url),'utf8');
  assert.match(css,/--content-max:1720px/);assert.match(css,/studio-main>:not\(\.app-topbar\).*max-width:var\(--content-max\)/);
  assert.match(css,/--text-muted:var\(--muted\)/);assert.match(css,/focus-visible/);
});



