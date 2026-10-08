const HASH=/^[a-f0-9]{64}$/,ID=/^[a-f0-9]{32}\.(jpg|png|mp4|wav|music\.wav)$/;
export const supportsNativeRights=session=>session?.capabilities?.native_rights_review===true;

export function initializeNativeRights({api,getState,dom=document,onMessage=()=>{},onSaved=async()=>{},onWorking=()=>{},uuid=()=>crypto.randomUUID()}){
  const root=dom.getElementById('native-rights-panel'),node=(tag,text)=>{const value=dom.createElement(tag);value.textContent=text??'';return value;};
  const status=node('p','Chưa đọc nguồn và quyền của dự án.'),read=node('button','Đọc nguồn & quyền'),choice=node('select'),detail=node('pre');
  status.className='hint';detail.className='native-publication-evidence';
  const fields={};
  function field(name,label,options,maxLength){const control=node(options?'select':'input');control.dataset.workspaceControl='';control.dataset.vfPermission='manage';
    if(options)for(const [value,text]of options){const option=node('option',text);option.value=value;control.append(option);}else{control.type='text';control.maxLength=maxLength;}
    const wrapper=node('label',label);wrapper.append(control);fields[name]=control;return wrapper;}
  const form=node('div');form.className='scene-grid';form.append(
    field('claimed_source_type','Nguồn được khai báo',[['user_upload','Tư liệu tải lên'],['stock','Kho media có giấy phép'],['internal_library','Thư viện nội bộ'],['ai_generated','Tạo bằng AI']]),
    field('claimed_rights','Quyền được khai báo',[['unknown','Chưa rõ'],['owned','Tôi sở hữu'],['licensed','Có giấy phép'],['restricted','Hạn chế sử dụng']]),
    field('license','Giấy phép / điều khoản sử dụng',null,2000),field('provider','Đơn vị cung cấp',null,100),
    field('source_reference','Tham chiếu nguồn công khai (không chứa khóa hoặc mật khẩu)',null,2000),
    field('creator','Tác giả',null,200),field('attribution_requirement','Yêu cầu ghi nguồn',null,1000));
  const ack=node('input');ack.type='checkbox';ack.dataset.vfPermission='manage';
  const acknowledgement=node('label');acknowledgement.className='check';acknowledgement.append(ack,node('span','Tôi xác nhận đây là khai báo của tôi; quyền sử dụng chưa được xác minh. Lưu sẽ yêu cầu duyệt lại dự án.'));
  const save=node('button','Lưu khai báo cần kiểm tra');
  for(const control of [read,choice,ack,save]){control.dataset.workspaceControl='';if(control.tagName==='BUTTON')control.type='button';}
  read.dataset.vfPermission='read';save.dataset.vfPermission='manage';choice.setAttribute?.('aria-label','Nguồn cần kiểm tra quyền');
  root.append(status,read,choice,detail,form,acknowledgement,save);
  let scope='',serial=0,working=false,page=null,selected=null;const keys=new Map();
  const context=()=>JSON.stringify([getState().workspace_id,getState().project?.id,getState().project?.revision]);
  const blocked=()=>working||getState().busy;
  function controls(){const state=getState();read.disabled=blocked()||!state.project;choice.disabled=blocked()||!page?.items.length;
    const editable=!blocked()&&state.canManage&&state.project&&!state.dirty&&!state.project.archived&&!state.active&&selected&&HASH.test(selected.asset_sha256??'');
    for(const control of Object.values(fields))control.disabled=!editable;ack.disabled=!editable;save.disabled=!editable||!ack.checked;
  }
  function render(){status.textContent=page?'Quyền chưa rõ chặn xuất bản. Khai báo của người dùng chưa phải xác minh giấy phép.':'Chưa đọc nguồn và quyền của dự án.';
    choice.replaceChildren();for(const row of page?.items??[]){const option=node('option',`${row.filename??row.asset_id} · ${row.rights_status}`);option.value=row.asset_id;choice.append(option);}
    choice.value=selected?.asset_id??'';
    detail.textContent=selected?JSON.stringify({source_type:selected.source_type,rights_status:selected.rights_status,license:selected.license,
      provider:selected.provider,source_reference:selected.source_reference,generation_provenance:selected.generation_provenance,
      latest_declaration:selected.declaration},null,2):'Chọn tư liệu để xem nguồn và khai báo.';controls();
  }
  function resetFields(){for(const [name,control]of Object.entries(fields))control.value=selected?.declaration?.request?.[name]??(name==='claimed_source_type'?'user_upload':name==='claimed_rights'?'unknown':'');ack.checked=false;}
  function sync(){if(context()!==scope){scope=context();serial++;page=null;selected=null;resetFields();}render();}
  function validatePage(value,captured){if(value?.schema_version!=='native-rights-review-v1'||value.workspace_id!==captured.workspace_id||value.project_id!==captured.project.id
    ||value.revision!==captured.project.revision||value.external_calls!==0||value.unknown_rights_block_publishing!==true||value.owner_override_enabled!==false
    ||!Array.isArray(value.items)||value.items.length>100)throw new Error('Nguồn hoặc phiên bản quyền không hợp lệ.');
    const ids=new Set();for(const row of value.items){if(!ID.test(row.asset_id??'')||ids.has(row.asset_id)||row.human_assertion_is_provider_verification!==false
      ||(row.asset_sha256!==null&&row.asset_sha256!==undefined&&!HASH.test(row.asset_sha256))
      ||(row.declaration&&(row.declaration.schema_version!=='native-rights-declaration-v1'||row.declaration.project_id!==captured.project.id
        ||row.declaration.workspace_id!==captured.workspace_id||row.declaration.asset_id!==row.asset_id||row.declaration.asset_sha256!==row.asset_sha256
        ||row.declaration.verified!==false||row.declaration.owner_override_recorded!==false||!HASH.test(row.declaration.sha256))))throw new Error('Khai báo không thuộc tư liệu hiện tại.');ids.add(row.asset_id);}return value;
  }
  async function perform(fn){sync();if(blocked())return;const token=++serial,expected=context();working=true;onWorking();controls();
    try{const apply=await fn();if(token===serial&&expected===context())await apply?.();}
    catch(error){if(token===serial&&expected===context())onMessage(error.message,true);}
    finally{working=false;if(expected!==context())sync();else render();onWorking();}}
  async function load(){const state=getState();if(!state.project)return;return perform(async()=>{const value=validatePage(await api(`/api/projects/${state.project.id}/rights`),state);
    return()=>{page=value;selected=page.items.find(row=>row.asset_id===selected?.asset_id)??page.items[0]??null;resetFields();};});}
  async function declare(){const state=getState();if(!state.canManage||!state.project||state.dirty||state.active||state.project.archived||!selected||!ack.checked||blocked())return;
    const row=selected;return perform(async()=>{const request={revision:state.project.revision,asset_sha256:row.asset_sha256,acknowledged:true};
      for(const [name,control]of Object.entries(fields))request[name]=control.value.trim()||null;
      const signature=scope+row.asset_id+JSON.stringify(request),key=keys.get(signature)??`native-rights-${uuid()}`;keys.set(signature,key);
      const result=await api(`/api/projects/${state.project.id}/rights/${row.asset_id}`,{...request,request_key:key}),record=result?.declaration;
      if(result?.schema_version!=='native-rights-declaration-v1'||result.workspace_id!==state.workspace_id||result.project_id!==state.project.id
        ||result.revision!==state.project.revision+1||result.approval_invalidated!==true||result.media_bytes_changed!==false||result.external_calls!==0
        ||record?.asset_id!==row.asset_id||record.asset_sha256!==row.asset_sha256||record.verified!==false||record.owner_override_recorded!==false
        ||record.workspace_id!==state.workspace_id||record.project_id!==state.project.id||!HASH.test(record.sha256)
        ||record.schema_version!=='native-rights-declaration-v1'||!/^nrd_[a-f0-9]{32}$/.test(record.declaration_id??'')
        ||record.effective_rights_status!==(request.claimed_rights==='restricted'?'restricted':'unknown')
        ||Object.entries(request).some(([name,value])=>record.request?.[name]!==value))throw new Error('Biên nhận quyền không hợp lệ.');
      return async()=>{ack.checked=false;page=null;selected=null;await onSaved(result);
        onMessage('Đã lưu khai báo chưa xác minh. Dự án cần duyệt lại; quyền chưa rõ vẫn chặn xuất bản.');};});
  }
  read.addEventListener('click',load);save.addEventListener('click',declare);ack.addEventListener('change',controls);
  choice.addEventListener('change',()=>{selected=page?.items.find(row=>row.asset_id===choice.value)??null;resetFields();render();});
  sync();return {sync,controls,load,declare,isWorking:()=>working};
}
