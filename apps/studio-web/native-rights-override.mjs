const HASH=/^[a-f0-9]{64}$/,ASSET=/^[a-f0-9]{32}\.(jpg|png|mp4|wav)$/,OVERRIDE=/^nro_[a-f0-9]{32}$/;
export function initializeNativeRightsOverride({api,getState,dom=document,onMessage=()=>{},onSaved=async()=>{},onWorking=()=>{},uuid=()=>crypto.randomUUID()}){
  const root=dom.getElementById('native-rights-override-panel'),node=(tag,text)=>{const value=dom.createElement(tag);value.textContent=text??'';return value;};
  const status=node('p','Chưa đọc ngoại lệ quyền của dự án.'),read=node('button','Đọc ngoại lệ của Owner'),choice=node('select'),detail=node('pre'),form=node('div');
  status.className='hint';detail.className='native-publication-evidence';form.className='scene-grid';
  const reason=node('input'),reference=node('input'),days=node('input'),publish=node('input'),ack=node('input');
  reason.type=reference.type='text';reason.maxLength=2000;reference.maxLength=1000;days.type='number';days.min='1';days.max='30';days.value='7';publish.type=ack.type='checkbox';
  function field(label,input){const wrapper=node('label',label);wrapper.append(input);return wrapper;}
  form.append(field('Lý do và căn cứ cho ngoại lệ',reason),field('Tham chiếu bằng chứng công khai (không chứa bí mật)',reference),field('Số ngày có hiệu lực (1–30)',days),
    field('Cho phép đưa tư liệu vào bước xét duyệt xuất bản; chưa cấp quyền đăng',publish));
  const label=node('label');label.className='check';label.append(ack,node('span','Tôi là Owner và quyết định ngoại lệ này. Quyền chưa được xác minh độc lập; lưu hoặc thu hồi sẽ yêu cầu duyệt lại dự án.'));
  const grant=node('button','Ghi ngoại lệ của Owner'),revoke=node('button','Thu hồi ngoại lệ');
  for(const button of [read,grant,revoke]){button.type='button';button.dataset.workspaceControl='';button.dataset.vfPermission=button===read?'read':'manage';}
  for(const input of [reason,reference,days,publish,ack]){input.dataset.workspaceControl='';input.dataset.vfPermission='manage';}
  choice.setAttribute?.('aria-label','Tư liệu cho ngoại lệ của Owner');root.append(status,read,choice,detail,form,label,grant,revoke);
  let scope='',serial=0,working=false,page=null,selected=null;const keys=new Map();
  const context=()=>JSON.stringify([getState().workspace_id,getState().project?.id,getState().project?.revision]);
  const blocked=()=>working||getState().busy;
  const previous=()=>page?.history.filter(row=>row.asset_id===selected?.asset_id&&row.request.action==='grant'
    &&!page.history.some(other=>other.request.action==='revoke'&&other.request.override_id===row.override_id)).at(-1);
  function controls(){const state=getState(),editable=!blocked()&&state.canManage&&state.project&&!state.dirty&&!state.active&&!state.project.archived&&selected&&HASH.test(selected.asset_sha256??'');
    read.disabled=blocked()||!state.project;choice.disabled=blocked()||!page?.items.length;
    for(const control of [reason,reference,ack])control.disabled=!editable;
    const canGrant=editable&&page.enabled===true&&!selected.fixture&&selected.rights_status!=='restricted';days.disabled=publish.disabled=!canGrant;
    grant.disabled=!canGrant||!ack.checked;revoke.disabled=!editable||!previous()||!ack.checked;
  }
  function render(){status.textContent=page?(page.enabled?'Ngoại lệ được bật bởi cấu hình Owner. Quyền chưa được xác minh; xuất bản vẫn cần duyệt riêng.':'Ngoại lệ đang tắt. Có thể đọc hoặc thu hồi bản ghi cũ; trình duyệt không thể bật tính năng.'):'Chưa đọc ngoại lệ quyền của dự án.';
    choice.replaceChildren();for(const row of page?.items??[]){const option=node('option',`${row.filename??row.asset_id} · ${row.rights_status}`);option.value=row.asset_id;choice.append(option);}
    choice.value=selected?.asset_id??'';detail.textContent=selected?JSON.stringify({asset:selected,history:page.history.filter(row=>row.asset_id===selected.asset_id)},null,2):'Chọn tư liệu để kiểm tra ngoại lệ.';controls();}
  function reset(){reason.value=reference.value='';days.value='7';publish.checked=ack.checked=false;}
  function sync(){if(context()!==scope){scope=context();serial++;page=selected=null;reset();}render();}
  function validateRecord(row,state){if(row?.schema_version!=='native-owner-rights-override-v1'||row.workspace_id!==state.workspace_id||row.project_id!==state.project.id
    ||!OVERRIDE.test(row.override_id??'')||!ASSET.test(row.asset_id??'')||!HASH.test(row.asset_sha256??'')||!HASH.test(row.sha256??'')
    ||row.rights_independently_verified!==false||row.publishing_authorized!==false||!['grant','revoke'].includes(row.request?.action)||row.request.acknowledged!==true)throw new Error('Bản ghi ngoại lệ không hợp lệ.');return row;}
  function validatePage(value,state){if(value?.schema_version!=='native-owner-rights-review-v1'||value.workspace_id!==state.workspace_id||value.project_id!==state.project.id
    ||value.revision!==state.project.revision||typeof value.enabled!=='boolean'||value.publishing_enabled!==false||value.rights_independently_verified!==false||value.external_calls!==0
    ||!Array.isArray(value.items)||value.items.length>100||!Array.isArray(value.history)||value.history.length>200)throw new Error('Phiên bản ngoại lệ không hợp lệ.');
    const ids=new Set();for(const row of value.items){if(!ASSET.test(row.asset_id??'')||ids.has(row.asset_id)||!HASH.test(row.rights_sha256??'')||typeof row.fixture!=='boolean'
      ||row.asset_sha256!==null&&row.asset_sha256!==undefined&&!HASH.test(row.asset_sha256))throw new Error('Tư liệu ngoại lệ không hợp lệ.');ids.add(row.asset_id);
      if(row.active_override){validateRecord(row.active_override,state);if(row.active_override.asset_id!==row.asset_id||row.active_override.asset_sha256!==row.asset_sha256)throw new Error('Ngoại lệ không thuộc tư liệu này.');}}
    for(const row of value.history)validateRecord(row,state);return value;}
  async function perform(fn){sync();if(blocked())return;const token=++serial,expected=context();working=true;onWorking();controls();
    try{const apply=await fn();if(token===serial&&expected===context())await apply?.();}
    catch(error){if(token===serial&&expected===context())onMessage(error.message,true);}
    finally{working=false;if(expected!==context())sync();else render();onWorking();}}
  async function load(){const state=getState();if(!state.project)return;return perform(async()=>{const value=validatePage(await api(`/api/projects/${state.project.id}/rights-overrides`),state);
    return()=>{page=value;selected=page.items.find(row=>row.asset_id===selected?.asset_id)??page.items[0]??null;reset();};});}
  async function record(action){controls();if((action==='grant'?grant:revoke).disabled)return;const state=getState(),row=selected,prior=previous();
    const validDays=Number(days.value);if(!reason.value.trim()||!reference.value.trim()||action==='grant'&&(!Number.isInteger(validDays)||validDays<1||validDays>30))return onMessage('Nhập lý do, tham chiếu và số ngày hợp lệ.',true);
    return perform(async()=>{const request={revision:state.project.revision,asset_sha256:row.asset_sha256,expected_rights_sha256:row.rights_sha256,action,
      reason:reason.value.trim(),evidence_reference:reference.value.trim(),valid_days:action==='grant'?validDays:7,
      allow_publishing_review:action==='grant'&&publish.checked,acknowledged:true,override_id:action==='revoke'?prior.override_id:null,expected_override_sha256:action==='revoke'?prior.sha256:null};
      const signature=scope+row.asset_id+JSON.stringify(request),key=keys.get(signature)??`native-owner-exception-${uuid()}`;keys.set(signature,key);
      const value=await api(`/api/projects/${state.project.id}/rights-overrides/${row.asset_id}`,{...request,request_key:key});validateRecord(value?.record,state);
      if(value.schema_version!=='native-owner-rights-override-v1'||value.workspace_id!==state.workspace_id||value.project_id!==state.project.id||value.revision!==state.project.revision+1
        ||value.approval_invalidated!==true||value.media_bytes_changed!==false||value.external_calls!==0||value.record.asset_id!==row.asset_id||value.record.asset_sha256!==row.asset_sha256
        ||Object.entries(request).some(([name,item])=>value.record.request[name]!==item))throw new Error('Biên nhận ngoại lệ không hợp lệ.');
      return async()=>{page=selected=null;reset();await onSaved(value);onMessage('Đã ghi quyết định của Owner. Dự án cần duyệt lại; xuất bản vẫn cần phê duyệt riêng.');};});
  }
  read.addEventListener('click',load);grant.addEventListener('click',()=>record('grant'));revoke.addEventListener('click',()=>record('revoke'));ack.addEventListener('change',controls);
  choice.addEventListener('change',()=>{selected=page?.items.find(row=>row.asset_id===choice.value)??null;reset();render();});
  sync();return{sync,controls,load,record,isWorking:()=>working};
}
