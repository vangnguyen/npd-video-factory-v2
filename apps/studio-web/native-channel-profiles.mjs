export function selections(value){
  if(value?.schema_version!=='native-channel-profile-catalog-v1'||value.publishing_enabled!==false||value.external_dispatches!==0||!Array.isArray(value.selections)||value.selections.length>50)throw new Error('Hồ sơ kênh chưa hợp lệ.');
  const refs=new Set();
  for(const item of value.selections){
    const profile=item?.profile;
    if(item.schema_version!=='native-channel-selection-v1'||item.publishing_enabled!==false||item.external_dispatches!==0||item.paid_operations!==0||
       typeof profile?.profile_ref!=='string'||!/^[a-z][a-z0-9-]{2,60}@[1-9][0-9]*$/.test(profile.profile_ref)||refs.has(profile.profile_ref)||
       typeof profile.name!=='string'||typeof profile.niche_profile?.niche!=='string'||typeof profile.niche_profile?.name!=='string'||
       profile.publishing_profile?.enabled!==false||profile.publishing_profile.credentials_configured!==false||profile.analytics_profile?.enabled!==false||
       profile.analytics_profile.provider_status!=='NOT_CONFIGURED'||item.brand_template?.brand?.id!==profile.brand_id||item.brand_template?.template?.id!==profile.video_template_id)throw new Error('Hồ sơ kênh chưa hợp lệ.');
    refs.add(profile.profile_ref);
  }
  return value.selections;
}

export function defaults(item){
  const profile=item.profile;
  return {content_profile_id:profile.content_profile_id,brand_id:profile.brand_id,template_id:profile.video_template_id,
    aspect_ratio:item.brand_template.template.aspect_ratio,duration_mode:profile.duration_mode};
}

export function initializeNativeChannels({api,dom=document,getState,onDefaults,onMessage}){
  const grid=dom.querySelector('#new-project-options .scene-grid');
  const label=dom.createElement('label');label.textContent='Hồ sơ kênh';
  const select=dom.createElement('select');select.id='new-channel-profile';select.dataset.workspaceControl='';label.append(select);grid.prepend(label);
  const note=dom.createElement('p');note.className='hint';note.id='channel-profile-summary';grid.parentElement.after(note);
  let values=[],epoch=0,previousProject=null;
  function option(text,value){const element=dom.createElement('option');element.textContent=text;element.value=value;return element;}
  select.append(option('Tùy chỉnh riêng',''));
  function controls(){const state=getState();select.disabled=Boolean(state.project)||state.busy||!state.canEdit;}
  function sync(){
    const project=getState().project;
    if(project){select.value=project.document?.channel_profile?.profile?.profile_ref??'';note.textContent=project.document?.channel_profile?`Hồ sơ kênh: ${project.document.channel_profile.profile.name} · ${project.document.channel_profile.profile.niche_profile.name}. Các lựa chọn được lưu với dự án.`:'';}
    else {if(previousProject)select.value='';note.textContent=select.value?'Hồ sơ điền mẫu và phụ đề cho dự án mới. Bạn có thể điều chỉnh trước khi tạo.':'Chọn hồ sơ kênh hoặc tự chọn nội dung, thương hiệu và mẫu.';}
    previousProject=project?.id??null;
    controls();
  }
  select.addEventListener('change',()=>{
    if(getState().project||getState().busy||!getState().canEdit)return;
    const selected=values.find(item=>item.profile.profile_ref===select.value);
    if(selected)onDefaults(defaults(selected));sync();
  });
  async function load(){
    const revision=++epoch;
    try {const value=selections(await api('/api/channel-profiles'));if(revision!==epoch)return;values=value;select.replaceChildren(option('Tùy chỉnh riêng',''),...values.map(item=>option(item.profile.name,item.profile.profile_ref)));sync();}
    catch(error){if(revision===epoch)onMessage(error.message,true);}
  }
  function request(){const state=getState();if(state.project||!state.canEdit)return {};const ref=select.value;if(!ref)return {};if(!values.some(item=>item.profile.profile_ref===ref))throw new Error('Chọn hồ sơ kênh đang có.');return {channel_profile_ref:ref};}
  function clear(){if(!getState().project)select.value='';sync();}
  return {load,controls,sync,request,clear};
}
