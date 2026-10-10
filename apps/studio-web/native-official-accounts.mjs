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
    if(!/^npac_[a-f0-9]{32}$/.test(a?.account_ref??'')||target?.workspace_id!==s.workspace_id||!['youtube','tiktok','facebook','instagram_reels'].includes(target.platform)
      ||!checksum(a.configuration_sha256)||!checksum(a.target_binding_sha256)||!['CONFIGURED','NOT_CONFIGURED'].includes(a.status)
      ||!['fixture','official'].includes(a.mode)||a.publishing_enabled!==false||a.token_returned!==false||a.account_verified!==false||a.credential_verified!==false
      ||typeof a.external_reads_enabled!=='boolean'||a.mode==='fixture'&&a.external_reads_enabled)throw new Error('Cấu hình tài khoản không đúng không gian hoặc trạng thái chỉ đọc.');
    if(['facebook','instagram_reels'].includes(target.platform))validateMetaAccount(a,s);return a;}
  function validateRow(r){const s=getState();
    if(r?.schema_version!=='native-official-account-check-v1'||r.workspace_id!==s.workspace_id||r.project_id!==s.project?.id||!/^nack_[a-f0-9]{32}$/.test(r.check_id??'')
      ||!checksum(r.request_fingerprint)||!checksum(r.snapshot_sha256)||r.publishing_enabled!==false||r.token_returned!==false
      ||r.snapshot?.workspace_id!==s.workspace_id||r.snapshot?.project_id!==s.project.id||r.snapshot?.account_ref!==r.account_ref||typeof r.snapshot.mock!=='boolean')throw new Error('Lịch sử xác minh không đúng dự án.');
    if(!['queued','running','succeeded','failed','not_configured','cancelled','outcome_unknown'].includes(r.status)||(r.status==='succeeded')!==Boolean(r.result))throw new Error('Trạng thái xác minh không hợp lệ.');
    if(r.result&&(r.result.schema_version!=='native-official-account-check-result-v1'||r.result.check_id!==r.check_id||r.result.project_id!==s.project.id||r.result.workspace_id!==s.workspace_id||r.result.account_match!==true
      ||r.result.read_only!==true||r.result.publishing_enabled!==false||r.result.token_returned!==false||r.result.mock!==r.snapshot.mock||typeof r.result.external_call!=='boolean'||r.result.external_call===r.result.mock))throw new Error('Bằng chứng xác minh tài khoản không hợp lệ.');
    if(['facebook','instagram_reels'].includes(r.snapshot?.target?.platform))validateMetaAccountRow(r,s);return r;}
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

const metaSha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v),metaId=v=>typeof v==='string'&&/^[1-9][0-9]{0,31}$/.test(v);
function metaPublic(value){let nodes=0;const walk=(v,depth)=>{if(++nodes>3000||depth>20)throw Error('Bằng chứng Meta vượt giới hạn.');if(v&&typeof v==='object')for(const[k,x]of Object.entries(v)){if(/^(token|access_token|refresh_token|token_file|authorization|headers|upload_url|upload_uri)$/i.test(k))throw Error('Bằng chứng Meta có trường riêng tư.');walk(x,depth+1);}};walk(value,0);}
function metaProfile(p,target){
  const fields=['workspace_id','profile_id','profile_version','platform','provider_key','target_account_id','credential_binding_sha256'];
  if(p?.schema_version!=='native-meta-publishing-profile-v1'||fields.some(k=>p.target?.[k]!==target?.[k])||!metaId(p.page_id)
    ||!/^v[1-9][0-9]{0,2}\.0$/.test(p.api_version??'')||p.login_type!=='facebook_login'||!metaId(target?.target_account_id)
    ||target.provider_key!==({facebook:'facebook-graph-api-publishing',instagram_reels:'instagram-graph-api-publishing'})[target.platform]
    ||target.platform==='facebook'&&p.page_id!==target.target_account_id)throw Error('Liên kết Page/Instagram không đúng cấu hình.');
}
export function validateMetaAccount(a,s){
  metaPublic(a);
  if(a?.schema_version!=='native-meta-account-factory-v1'||a.target?.workspace_id!==s.workspace_id
    ||a.provider_permissions_verified!==false||a.app_eligibility_verified!==false||a.account_verified!==false||a.credential_verified!==false
    ||a.publishing_enabled!==false||a.token_returned!==false||a.real_provider_tested!==false||!metaSha(a.configuration_sha256)
    ||!metaSha(a.target_binding_sha256)||a.cipher_sha256!==null&&!metaSha(a.cipher_sha256)
    ||a.status==='CONFIGURED'&&(a.credential_present!==true||a.cipher_sha256===null))throw Error('Xác minh chỉ đọc không cấp quyền đăng Meta.');
  metaProfile(a.profile,a.target);return a;
}
export function validateMetaAccountRow(r,s){
  metaPublic(r);
  const m=r?.snapshot?.meta,target=r?.snapshot?.target;
  if(r.workspace_id!==s.workspace_id||r.project_id!==s.project?.id||target?.workspace_id!==s.workspace_id
    ||m?.schema_version!=='native-meta-account-source-v1'||m.cipher_sha256!==null&&!metaSha(m.cipher_sha256)
    ||!Number.isFinite(Date.parse(m.consented_at))||Date.parse(m.deadline)-Date.parse(m.consented_at)!==900000)throw Error('Bằng chứng Meta không đúng phạm vi hoặc cửa sổ đọc.');
  metaProfile(m.profile,target);
  if(r.result){const p=r.result.meta,ig=target.platform==='instagram_reels',ops=ig?['page_identity','instagram_identity']:['page_identity'];
    const required=ig?['instagram_basic','instagram_content_publish','pages_read_engagement']:['pages_manage_posts','pages_read_engagement'];
    if(p?.schema_version!=='native-meta-account-proof-v1'||m.cipher_sha256===null||p.page_id!==m.profile.page_id
      ||p.instagram_account_id!==(ig?target.target_account_id:null)||p.token_page_match!==true||p.linked_instagram_match!==(ig?true:null)
      ||p.provider_permissions_verified!==false||p.app_eligibility_verified!==false||p.publishing_enabled!==false||p.read_only!==true
      ||!Array.isArray(p.declared_permissions)||p.declared_permissions.length>7||new Set(p.declared_permissions).size!==p.declared_permissions.length
      ||required.some(x=>!p.declared_permissions.includes(x))||p.declared_permissions.some(x=>!['pages_read_engagement','pages_manage_posts','pages_show_list','instagram_basic','instagram_content_publish','ads_read','ads_management'].includes(x))
      ||!Array.isArray(p.observations)||p.observations.length!==ops.length||p.observations.some((x,i)=>x.operation!==ops[i]||x.response_status!==200||!metaSha(x.request_sha256)||!metaSha(x.response_sha256)||!metaSha(x.cost_operation_id))
      ||new Set(p.observations.map(x=>x.cost_operation_id)).size!==ops.length||r.result.cost_operation_id!==p.observations.at(-1).cost_operation_id||r.result.response_sha256!==p.observations.at(-1).response_sha256)
      throw Error('Bằng chứng Page/Instagram thiếu hoặc bị thay đổi.');
  }return r;
}
