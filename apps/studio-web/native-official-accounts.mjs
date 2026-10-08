// Public account bindings and explicit read checks; no OAuth secret input or publishing action.
export function initializeNativeOfficialAccounts({api,getState,root=document,onMessage=()=>{},uuid=()=>crypto.randomUUID()}){
  const card=root.getElementById('native-official-accounts-card');card.replaceChildren();
  const node=(tag,text,id)=>{const n=root.createElement(tag);if(text)n.textContent=text;if(id)n.id='native-account-'+id;return n;};
  const button=(text,id,permission)=>{const n=node('button',text,id);n.type='button';n.className='secondary';n.dataset.vfPermission=permission;return n;};
  const summary=node('summary','Tài khoản nền tảng'),hint=node('p','Đọc cấu hình đã được chủ không gian cài đặt và xác minh tài khoản qua API chỉ đọc. Việc này không cấp quyền xuất bản.'),
    read=button('Đọc cấu hình','read','manage'),select=node('select',null,'select'),ack=node('input',null,'ack'),ackLabel=node('label','Tôi cho phép xác minh tài khoản chỉ đọc.'),
    verify=button('Xác minh tài khoản','verify','manage'),history=button('Đọc lịch sử xác minh','history-read','read'),more=button('Đọc trang tiếp','more','read'),
    status=node('p',null,'status'),list=node('div',null,'history'),detail=node('pre',null,'detail');
  ack.type='checkbox';ackLabel.append(ack);hint.className='hint';card.append(summary,hint,read,select,ackLabel,verify,history,status,list,more,detail);
  let scope='',generation=0,working=false,accounts=[],rows=[],cursor=null,selected=null;const keys=new Map();
  const context=()=>{const s=getState();return JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.canManage]);};
  const base=()=>'/api/projects/'+getState().project.id;
  function controls(){const s=getState(),blocked=working||s.busy,account=accounts.find(a=>a.account_ref===select.value);
    read.disabled=blocked||!s.canManage;history.disabled=blocked||!s.project;more.disabled=blocked||!cursor||rows.length>=500;
    verify.disabled=blocked||!s.canManage||!s.project||s.dirty||s.active||s.project.archived||!ack.checked||account?.status!=='CONFIGURED';
    select.disabled=blocked||!s.canManage;ack.disabled=blocked||!s.canManage;}
  function render(){list.replaceChildren();for(const row of rows){const n=node('p',`${row.snapshot.mock?'Mẫu kiểm tra':'API'} · ${row.status} · ${row.account_ref} · phiên bản ${row.snapshot.project_revision}`);list.append(n);}
    detail.textContent=selected?JSON.stringify(selected,null,2):'Đọc lịch sử để xem bằng chứng xác minh đã lưu.';
    status.textContent=accounts.length?`${accounts.length} tài khoản trong cấu hình. Xác minh chỉ đọc; xuất bản vẫn tắt.`:'Chưa đọc cấu hình hoặc chưa có tài khoản được cấu hình.';controls();}
  function sync(){const next=context();if(next!==scope){scope=next;generation++;working=false;accounts=[];rows=[];cursor=null;selected=null;select.replaceChildren();select.value='';ack.checked=false;}render();}
  const checksum=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
  function validateAccount(a){const s=getState(),target=a?.target;
    if(!/^npac_[a-f0-9]{32}$/.test(a?.account_ref??'')||target?.workspace_id!==s.workspace_id||!['youtube','tiktok'].includes(target.platform)
      ||!checksum(a.configuration_sha256)||!checksum(a.target_binding_sha256)||!['CONFIGURED','NOT_CONFIGURED'].includes(a.status)
      ||!['fixture','official'].includes(a.mode)||a.publishing_enabled!==false||a.token_returned!==false||a.account_verified!==false||a.credential_verified!==false
      ||typeof a.external_reads_enabled!=='boolean'||a.mode==='fixture'&&a.external_reads_enabled)throw new Error('Cấu hình tài khoản không đúng không gian hoặc trạng thái chỉ đọc.');return a;}
  function validateRow(r){const s=getState();
    if(r?.schema_version!=='native-official-account-check-v1'||r.workspace_id!==s.workspace_id||r.project_id!==s.project?.id||!/^nack_[a-f0-9]{32}$/.test(r.check_id??'')
      ||!checksum(r.request_fingerprint)||!checksum(r.snapshot_sha256)||r.publishing_enabled!==false||r.token_returned!==false
      ||r.snapshot?.workspace_id!==s.workspace_id||r.snapshot?.project_id!==s.project.id||r.snapshot?.account_ref!==r.account_ref||typeof r.snapshot.mock!=='boolean')throw new Error('Lịch sử xác minh không đúng dự án.');
    if(!['queued','running','succeeded','failed','not_configured','cancelled','outcome_unknown'].includes(r.status)||(r.status==='succeeded')!==Boolean(r.result))throw new Error('Trạng thái xác minh không hợp lệ.');
    if(r.result&&(r.result.schema_version!=='native-official-account-check-result-v1'||r.result.check_id!==r.check_id||r.result.project_id!==s.project.id||r.result.workspace_id!==s.workspace_id||r.result.account_match!==true
      ||r.result.read_only!==true||r.result.publishing_enabled!==false||r.result.token_returned!==false||r.result.mock!==r.snapshot.mock||typeof r.result.external_call!=='boolean'||r.result.external_call===r.result.mock))throw new Error('Bằng chứng xác minh tài khoản không hợp lệ.');return r;}
  async function invoke(fn){if(working)return;const version=generation,expected=context();working=true;controls();
    try{const apply=await fn();if(version===generation&&expected===context())apply();}
    catch(error){if(version===generation&&expected===context())onMessage(error.message,true);}
    finally{if(version===generation){working=false;render();}}}
  const readAccounts=()=>invoke(async()=>{if(!getState().canManage)throw new Error('Chỉ chủ không gian được đọc cấu hình kết nối.');const value=await api('/api/connections/official-accounts');
    if(value?.schema_version!=='native-official-accounts-v1'||value.workspace_id!==getState().workspace_id||value.publishing_enabled!==false||value.token_returned!==false||!Array.isArray(value.accounts)||value.accounts.length>50)throw new Error('Cấu hình kết nối không hợp lệ.');
    const validated=value.accounts.map(validateAccount);return()=>{accounts=validated;select.replaceChildren();for(const a of accounts){const option=node('option',`${a.mode==='fixture'?'Mẫu kiểm tra':'API'} · ${a.target.platform} · ${a.target.target_account_id} · ${a.status}`);option.value=a.account_ref;select.append(option);}select.value=accounts[0]?.account_ref??'';ack.checked=false;};});
  const readHistory=(next=false)=>invoke(async()=>{if(!getState().project)throw new Error('Chọn dự án để đọc lịch sử.');if(next&&!cursor)return()=>{};
    const value=await api(base()+'/account-checks?limit=25'+(next?'&cursor='+encodeURIComponent(cursor):''));
    if(value?.schema_version!=='native-official-account-check-page-v1'||value.workspace_id!==getState().workspace_id||value.project_id!==getState().project.id
      ||value.publishing_enabled!==false||value.token_returned!==false||!Array.isArray(value.items)||value.items.length>25||value.next_cursor!==null&&typeof value.next_cursor!=='string')throw new Error('Trang lịch sử không hợp lệ.');
    const validated=value.items.map(validateRow);return()=>{rows=[...new Map([...(next?rows:[]),...validated].map(r=>[r.check_id,r])).values()].slice(0,500);selected=validated[0]??selected;cursor=value.next_cursor;};});
  const execute=()=>invoke(async()=>{const s=getState(),account=accounts.find(a=>a.account_ref===select.value);
    if(!s.canManage||!s.project||s.busy||s.dirty||s.active||s.project.archived||!ack.checked||account?.status!=='CONFIGURED')throw new Error('Lưu dự án và xác nhận kiểm tra chỉ đọc với tài khoản đã cấu hình.');
    const intent={revision:s.project.revision,expected_configuration_sha256:account.configuration_sha256,acknowledged_read_only:true};
    const key=JSON.stringify([s.workspace_id,s.project.id,account.account_ref,intent]);if(!keys.has(key))keys.set(key,uuid());
    const value=validateRow(await api(base()+'/official-accounts/'+account.account_ref+'/verify',{...intent,request_key:keys.get(key)}));
    return()=>{keys.delete(key);selected=value;rows=[value,...rows.filter(r=>r.check_id!==value.check_id)];cursor=null;ack.checked=false;
      onMessage(value.status==='not_configured'?'API tài khoản chưa cấu hình.':'Đã lưu kiểm tra chỉ đọc. Đọc lịch sử để xem kết quả; chưa cấp quyền xuất bản.');};});
  read.addEventListener('click',()=>readAccounts());history.addEventListener('click',()=>readHistory());more.addEventListener('click',()=>readHistory(true));verify.addEventListener('click',()=>execute());
  ack.addEventListener('change',controls);select.addEventListener('change',()=>{ack.checked=false;controls();});sync();return{sync,controls,readAccounts,readHistory,execute};
}
