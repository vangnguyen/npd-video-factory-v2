// Optional UX shell. Call only after the runtime advertises native_studio_ux.
export const supportsStudioUX = session => session?.capabilities?.native_studio_ux === true;
export const studioNavigation = [
  {id:'create',label:'TẠO NỘI DUNG',items:[{id:'create',label:'Video mới',href:'/?new=1',icon:'plus'}]},
  {id:'work',label:'CÔNG VIỆC',items:[
    {id:'dashboard',label:'Sản xuất',href:'/production?view=dashboard',icon:'grid'},
    {id:'projects',label:'Dự án',href:'/production?view=projects',icon:'folder'},
    {id:'intelligence',label:'Nghiên cứu & ý tưởng',href:'/intelligence',icon:'idea'},
    {id:'calendar',label:'Lịch nội dung',href:'/production?view=calendar',icon:'calendar'}]},
  {id:'library',label:'THƯ VIỆN',items:[
    {id:'assets',label:'Tư liệu',href:'/?view=assets',icon:'image'},
    {id:'library',label:'Video hoàn chỉnh',href:'/production?view=library',icon:'video'},
    {id:'brands',label:'Thương hiệu & mẫu',href:'/?view=brands',icon:'palette'}]},
  {id:'system',label:'HỆ THỐNG',items:[
    {id:'profiles',label:'Hồ sơ nội dung',href:'/production?view=profiles',icon:'profile'},
    {id:'settings',label:'Cài đặt',href:'/settings/assemblyai',icon:'settings'}]}
];
export function studioPage(page, href = '') {
  const url = new URL(href || '/', 'http://studio.local');
  const view = url.searchParams.get('view');
  if (page === 'project') return url.searchParams.get('new') === '1' ? 'create' : ['assets','brands'].includes(view) ? view : 'projects';
  return page === 'queue' ? 'dashboard' : page;
}
const paths = {
  plus:'M12 5v14M5 12h14',grid:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  folder:'M3 7V5h6l2 2h10v13H3z',idea:'M9 18h6M10 21h4M8 14a6 6 0 1 1 8 0l-1 3H9z',
  calendar:'M4 5h16v16H4zM8 3v4M16 3v4M4 10h16',image:'M3 3h18v18H3zM3 17l6-6 4 4 3-3 5 5M16 7h.01',
  video:'M3 6h13v12H3zM16 10l5-3v10l-5-3',palette:'M12 3a9 9 0 1 0 0 18h2a2 2 0 0 0 0-4h-1a2 2 0 0 1 0-4h5a3 3 0 0 0 3-3 9 9 0 0 0-9-7z',
  profile:'M8 8a4 4 0 1 0 8 0 4 4 0 0 0-8 0M4 21v-2a8 8 0 0 1 16 0v2',
  settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2'
};
function icon(doc, name) {
  const svg = doc.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');svg.setAttribute('focusable','false');
  const path = doc.createElementNS('http://www.w3.org/2000/svg','path');
  path.setAttribute('d',paths[name] || paths.grid);svg.append(path);return svg;
}
function element(doc, tag, className, text) {
  const node=doc.createElement(tag);if(className)node.className=className;if(text)node.textContent=text;return node;
}
export function loadStudioShellStyles(doc = document) {
  if(doc.querySelector('link[data-studio-shell-style]'))return;
  const link=doc.createElement('link');link.rel='stylesheet';link.href='/studio-shell.css';link.dataset.studioShellStyle='true';doc.head.append(link);
}
export function mountStudioShell({page='project',context='Không gian sản xuất video',title,document:doc=globalThis.document}={}) {
  if(!doc)return null;
  const main=doc.getElementById('studio-main') || doc.querySelector('main'),sidebar=doc.querySelector('aside.sidebar');
  if(!main || !sidebar)return null;
  if(sidebar.dataset.studioShell==='true')return {main,sidebar,topbar:main.querySelector('.app-topbar'),header:main.querySelector('.page-header')};
  doc.body.classList.add('studio-ux');doc.body.dataset.studioPage=page;main.id='studio-main';main.classList.add('studio-main');
  if(!main.hasAttribute('tabindex'))main.setAttribute('tabindex','-1');
  const current=studioPage(page,globalThis.location?.href || '');
  const newProject=doc.getElementById('new-project');
  if(newProject)newProject.remove(); // Preserve this exact node and its already registered handlers.
  sidebar.querySelectorAll(':scope > nav,:scope > a.brand,:scope > a.wordmark,:scope > a.nav,:scope > .nav-label,:scope > .side-label:not([for])').forEach(node=>node.remove());
  const preserved=[...sidebar.childNodes];const brand=element(doc,'a','studio-brand');brand.href='/';
  brand.append(element(doc,'span','studio-brand-mark','N'),element(doc,'span','studio-brand-name','NPD VIDEO STUDIO'));
  const nav=element(doc,'nav','studio-navigation');nav.setAttribute('aria-label','Điều hướng Studio');
  for(const group of studioNavigation) {
    const section=element(doc,'section','studio-nav-group');section.dataset.navGroup=group.id;
    section.append(element(doc,'h2','studio-nav-label',group.label));
    for(const item of group.items) {
      const node=item.id==='create'&&newProject?newProject:element(doc,'a');
      if(node.tagName==='A')node.href=item.href;
      node.className='studio-nav-item'+(item.id==='create'?' studio-create':'')+(item.id===current?' active':'');
      node.dataset.studioPage=item.id;
      if(item.id===current)node.setAttribute('aria-current','page');else node.removeAttribute('aria-current');
      node.replaceChildren(icon(doc,item.icon),element(doc,'span','',item.id==='create'&&newProject?'Dự án mới':item.label));
      section.append(node);
    }
    nav.append(section);
  }
  const sidebarContext=element(doc,'div','studio-sidebar-context');
  for(const node of preserved)sidebarContext.append(node);
  const diagnostics=element(doc,'details','studio-diagnostics');
  diagnostics.append(element(doc,'summary','','Chẩn đoán & trạng thái'));
  sidebarContext.querySelectorAll('.runtime-card,.runtime-detail,.side-footer,.sidebar-foot').forEach(node=>diagnostics.append(node));
  if(diagnostics.children.length>1)sidebarContext.append(diagnostics);
  sidebar.replaceChildren(brand,nav,sidebarContext);sidebar.dataset.studioShell='true';
  let header=main.querySelector(':scope > header');
  if(header){header.classList.add('page-header');header.querySelector(':scope > div')?.classList.add('page-header-copy');
    const h1=header.querySelector('h1');if(title&&h1)h1.textContent=title;
    let actions=header.querySelector('.studio-header-actions,.header-actions,.page-actions');
    if(!actions){actions=element(doc,'div','page-actions');for(const node of [...header.children])if(node.tagName==='BUTTON')actions.append(node);header.append(actions);}
    actions.classList.add('page-actions');
    const ciNew=doc.getElementById('ci-new');if(ciNew){ciNew.classList.remove('secondary');ciNew.classList.add('primary');actions.append(ciNew);}
  }
  const topbar=element(doc,'div','app-topbar');topbar.setAttribute('aria-label','Ngữ cảnh Studio');
  topbar.append(element(doc,'span','app-topbar-name','NPD Video Studio'),element(doc,'span','app-topbar-context',context),element(doc,'span','app-topbar-local','Lưu trên PC của bạn'));
  main.prepend(topbar);
  if(!doc.querySelector('.skip-link')){const skip=element(doc,'a','skip-link','Đến nội dung chính');skip.href='#studio-main';doc.body.prepend(skip);}
  return {main,sidebar,header,topbar};
}


