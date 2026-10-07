export const supportsNativeVariants=session=>session?.capabilities?.native_source_variants===true;
const dimensions={'16:9':[1920,1080],'9:16':[1080,1920],'1:1':[1080,1080],'4:5':[1080,1350]};
export function initializeNativeVariants({api,getState,root=document,onMessage=()=>{},onOpen=()=>{},onCreated=()=>{},uuid=()=>crypto.randomUUID()}){
  const $=id=>root.getElementById(id),element=(tag,text)=>{const node=root.createElement(tag);node.textContent=text;return node;};
  let scope='',sequence=0,working=false,profiles=[],rows=[],cursor=null;const selected=new Map(),keys=new Map();
  const context=()=>JSON.stringify([getState().workspace_id,getState().project?.id,getState().project?.revision]);
  const source=()=>getState().project?.document?.canonical_timeline?.snapshot?.metadata?.native_auto_edit_schema==='native-auto-edit-timeline-v1';
  function controls(){const state=getState(),blocked=working||state.busy;
    $('native-variants-profiles').disabled=blocked||!state.project;$('native-variants-read').disabled=blocked||!state.project;
    $('native-variants-more').disabled=blocked||!cursor;
    $('native-variants-create').disabled=blocked||!state.project||state.dirty||!state.canEdit||state.project.archived||!source()||![...selected.values()].some(input=>input.checked);
    for(const input of selected.values())input.disabled=blocked||!state.canEdit;
    for(const button of $('native-variants-history').querySelectorAll('button'))button.disabled=blocked||state.dirty;
  }
  function render(){const history=$('native-variants-history');history.replaceChildren();
    for(const row of rows){const section=element('section','');section.append(element('h3',`Bản dựng từ master phiên bản ${row.snapshot.master_revision}`));
      section.append(element('p','Mỗi bản cần kiểm tra crop, preview và duyệt riêng. Chưa render hoặc đăng; trạng thái lúc tạo là chưa duyệt.'));
      for(const variant of row.result.variants){const line=element('p',`${variant.name} · ${variant.profile.width}×${variant.profile.height} · crop cần kiểm tra `),button=element('button','Mở bản dựng');
        button.type='button';button.className='secondary';button.dataset.vfPermission='read';button.addEventListener('click',async()=>{
          if(getState().dirty||getState().busy||working)return onMessage('Lưu thay đổi và chờ thao tác hiện tại trước.',true);
          try{await onOpen(variant.project_id);}catch(error){onMessage(error.message,true);}});line.append(button);section.append(line);}history.append(section);}
    $('native-variants-status').textContent=source()?'Tạo các bản từ timeline đã lưu. Crop của mỗi bản chuyển về center crop cần kiểm tra; nguồn, lời nói và phân tích đã có được tái sử dụng.':'Lưu bản dựng từ video tải lên trước khi tạo các định dạng. Chưa hỗ trợ master lồng tiếng trong đường Native này.';controls();
  }
  function sync(){const next=context();if(next!==scope){scope=next;sequence++;working=false;profiles=[];rows=[];cursor=null;selected.clear();keys.clear();$('native-variants-choices').replaceChildren();}render();}
  function profile(value){const geometry=dimensions[value?.aspect_ratio];if(!/^[a-z][a-z0-9-]{2,60}@[1-9][0-9]*$/.test(value?.profile_ref??'')||!geometry
    ||value.width!==geometry[0]||value.height!==geometry[1]||typeof value.label!=='string'||value.label.length>100)throw new Error('Định dạng không hợp lệ.');return value;}
  function row(value){if(value?.schema_version!=='native-source-variant-batch-v1'||value.workspace_id!==getState().workspace_id||value.master_project_id!==getState().project?.id
    ||!/^nsvb_[a-f0-9]{32}$/.test(value.batch_id??'')||value.external_provider_calls!==0||value.result?.master_project_mutated!==false||value.result?.publishing_enabled!==false
    ||!Array.isArray(value.result?.variants)||value.result.variants.length<1||value.result.variants.length>6)throw new Error('Nhóm bản dựng không khớp phạm vi.');
    for(const item of value.result.variants){profile(item.profile);if(!/^[a-f0-9]{32}$/.test(item.project_id??'')||item.approval_inherited!==false||item.render_dispatched!==false||item.crop_needs_attention!==true)throw new Error('Bản dựng cần giữ duyệt riêng.');}return value;}
  async function perform(fn){sync();if(working||getState().busy)return;const captured=context(),own=sequence;working=true;controls();
    try{const apply=await fn();if(captured===context()&&own===sequence)apply();}catch(error){if(captured===context()&&own===sequence)onMessage(error.message,true);}
    finally{if(captured===context()&&own===sequence){working=false;render();}}
  }
  async function catalog(){return perform(async()=>{const value=await api('/api/auto-edit/variant-profiles');
    if(value?.schema_version!=='native-source-variant-catalog-v1'||!Array.isArray(value.profiles)||value.profiles.length>32)throw new Error('Danh mục định dạng không hợp lệ.');
    const values=value.profiles.map(profile);if(new Set(values.map(item=>item.profile_ref)).size!==values.length)throw new Error('Định dạng bị trùng.');
    return()=>{profiles=values;selected.clear();const choices=$('native-variants-choices');choices.replaceChildren();
      for(const item of profiles){const label=element('label',item.label+' '),input=element('input','');label.className='check';input.type='checkbox';input.checked=true;input.dataset.vfPermission='edit';
        input.addEventListener('change',controls);label.append(input);choices.append(label);selected.set(item.profile_ref,input);}};});}
  async function read(more=false){if(!getState().project)return;return perform(async()=>{const value=await api(`/api/projects/${getState().project.id}/variants?limit=25${more&&cursor?`&cursor=${encodeURIComponent(cursor)}`:''}`);
    if(value?.schema_version!=='native-source-variant-page-v1'||value.workspace_id!==getState().workspace_id||value.master_project_id!==getState().project?.id
      ||!Array.isArray(value.items)||value.items.length>25||(value.next_cursor!==null&&typeof value.next_cursor!=='string')||value.external_provider_calls!==0)throw new Error('Lịch sử bản dựng không hợp lệ.');
    const values=value.items.map(row);return()=>{rows=more?[...rows,...values.filter(item=>!rows.some(old=>old.batch_id===item.batch_id))]:values;cursor=value.next_cursor;};});}
  async function create(){const state=getState();if(!state.canEdit||state.dirty||!source())return onMessage('Cần quyền biên tập và timeline nguồn đã lưu.',true);
    return perform(async()=>{const refs=profiles.filter(item=>selected.get(item.profile_ref)?.checked).map(item=>item.profile_ref);if(!refs.length||refs.length>6)throw new Error('Chọn từ một đến sáu định dạng.');
      const payload={revision:state.project.revision,expected_version:state.project.document.canonical_timeline.version,profile_refs:refs,crop_policy:'center_attention'},signature=scope+JSON.stringify(payload);
      const key=keys.get(signature)??`native-variants-${uuid()}`;keys.set(signature,key);const value=row(await api(`/api/projects/${state.project.id}/variants`,{...payload,request_key:key}));
      return()=>{rows=[value,...rows.filter(old=>old.batch_id!==value.batch_id)];cursor=null;onMessage('Đã tạo các bản chưa duyệt. Kiểm tra crop, preview và duyệt từng bản trước khi render.');onCreated();};});}
  $('native-variants-profiles').addEventListener('click',catalog);$('native-variants-read').addEventListener('click',()=>read());
  $('native-variants-more').addEventListener('click',()=>read(true));$('native-variants-create').addEventListener('click',create);
  sync();return{sync,controls,catalog,read,create,isWorking:()=>working};
}
