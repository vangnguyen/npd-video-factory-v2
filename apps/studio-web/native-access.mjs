// Loaded only for an explicitly configured registry session. HTTP remains authoritative.
export const supportsNativeAccess = session => session?.access?.mode === 'registry';
const grants={owner:['read','edit','review','manage'],editor:['read','edit'],reviewer:['read','review'],viewer:['read']};
export const nativePermissions = session => supportsNativeAccess(session)
  ? (grants[session.access.role]??[]).filter(value=>session.access.permissions?.includes(value))
  : ['read','edit','review','manage'];
const readIDs=new Set(['refresh','project-picker','show-archived','load-history','load-artifacts','ci-refresh','ci-runs',
  'search','profile-filter','stage-filter','calendar-month','calendar-group','library-search','library-approved-only',
  'projects-search','projects-stage','projects-archived','approved-only',
  'cancel-preview','close-preview','close-planning','planning-cancel','native-logout']);
const reviewIDs=new Set(['approve','reject-content','approve-final','reject-final','review-check','final-watch','final-reviewer',
  'ci-approve-brief','ci-ack','ci-reviewer','ci-override-ack','ci-override-note']);
const manageIDs=new Set(['save-cost-policy','max-ai-cost','open-output']);
const actorIDs=new Set(['final-reviewer','ci-reviewer','reviewer','planning-reviewer','script-only-reviewer']);
export function nativeControlPermission(node) {
  const id=node.id??'',data=node.dataset??{},tag=node.tagName;
  if(id==='native-logout')return 'read';
  if(data.vfPermission)return ['read','edit','review','manage'].includes(data.vfPermission)?data.vfPermission:'edit';
  if(tag==='A'){
    const href=node.getAttribute('href')??'';
    if(href.startsWith('/settings/'))return 'manage';
    return href.startsWith('/')&&new URL(href,'http://studio.local').searchParams.get('new')==='1'?'edit':'read';
  }
  if(reviewIDs.has(id)||Object.hasOwn(data,'scriptControl'))return 'review';
  if(manageIDs.has(id))return 'manage';
  if(readIDs.has(id)||Object.hasOwn(data,'studioNav')||Object.hasOwn(data,'quickStage')||Object.hasOwn(data,'plan')
    ||Object.hasOwn(data,'assetPreview')||Object.hasOwn(data,'libraryQuery')||Object.hasOwn(data,'libraryKind')
    ||Object.hasOwn(data,'waveformSeek')||Object.hasOwn(data,'playhead')||Object.hasOwn(data,'zoom'))return 'read';
  return 'edit';
}

export function installNativeAccess(session,{document:doc=globalThis.document,fetcher=globalThis.fetch,
    location=globalThis.location,Observer=globalThis.MutationObserver}={}) {
  if(!supportsNativeAccess(session)||!doc)return null;
  const permissions=new Set(nativePermissions(session)),identity=session.access.display_name||session.access.role;
  const existing=doc.getElementById('native-access-bar');
  if(existing)return null; // One install per loaded page; role changes require a fresh login.
  const style=doc.createElement('link');style.rel='stylesheet';style.href='/native-access.css';doc.head.append(style);
  const bar=doc.createElement('section');bar.id='native-access-bar';bar.className='native-access-bar';bar.setAttribute('aria-label','Quyền truy cập Studio');
  const text=doc.createElement('p'),button=doc.createElement('button'),status=doc.createElement('p');
  const roles={owner:'Chủ không gian',editor:'Biên tập viên',reviewer:'Người duyệt',viewer:'Người xem'};
  text.textContent=`${identity} · ${roles[session.access.role]??'Chưa có quyền'}${permissions.has('edit')?'':' · Không chỉnh sửa dự án'}`;
  button.id='native-logout';button.type='button';button.textContent='Đăng xuất';status.setAttribute('role','status');
  bar.append(text,button,status);(doc.querySelector('main')??doc.body).prepend(bar);
  const enforce=()=>{
    for(const node of doc.querySelectorAll('button,input,select,textarea,a[href]')) {
      const permission=nativeControlPermission(node),denied=!permissions.has(permission);
      if(denied){
        if('disabled' in node && !node.disabled)node.disabled=true;
        if(node.dataset.vfDenied!=='true'){node.dataset.vfDenied='true';node.setAttribute('aria-disabled','true');node.title='Vai trò hiện tại không có quyền thực hiện thao tác này.';}
      }
      if(actorIDs.has(node.id)&&permissions.has(permission)) {
        if(node.value!==identity)node.value=identity;
        if(!node.readOnly)node.readOnly=true;
      }
    }
  };
  const capture=event=>{
    const control=event.target.closest?.('button,input,select,textarea,a[href]');
    if(control&&!permissions.has(nativeControlPermission(control))){event.preventDefault();event.stopImmediatePropagation();status.textContent='Vai trò hiện tại không có quyền thực hiện thao tác này.';}
  };
  for(const type of ['click','input','change','submit'])doc.addEventListener(type,capture,true);
  const observer=Observer?new Observer(enforce):null;
  observer?.observe(doc.body,{subtree:true,childList:true,attributes:true,attributeFilter:['disabled','readonly']});
  enforce();
  button.addEventListener('click',async()=>{
    button.disabled=true;status.textContent='Đang đăng xuất…';
    try {
      const response=await fetcher('/api/logout',{method:'POST',credentials:'same-origin',cache:'no-store',
        headers:{'Content-Type':'application/json','X-VF-CSRF':session.csrf},body:'{}'});
      if(!response.ok&&response.status!==401)throw new Error();
      location.assign('/login');
    } catch {status.textContent='Chưa đăng xuất được. Kiểm tra kết nối rồi thử lại.';}
    finally{button.disabled=false;}
  });
  return {enforce,permissions,dispose:()=>{observer?.disconnect();for(const type of ['click','input','change','submit'])doc.removeEventListener(type,capture,true);}};
}
