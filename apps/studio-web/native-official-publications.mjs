// Explicit signed review and bounded provider actions. No secret input or automatic sends.
import {validateTikTokDraft} from './native-tiktok-creators.mjs';
import {validateTikTokPublishingFactory,validateTikTokPublication,validateTikTokDispatch,tikTokSourceMatches} from './native-tiktok-publication.mjs';
export function validateOfficialThumbnailStage(stage,row){
  const s=row?.snapshot,id=s?.metadata?.thumbnail_asset_id,sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
  if(id==null){if(s?.thumbnail!=null||stage!=null)throw new Error('Thumbnail không thuộc yêu cầu xuất bản.');return null;}
  const p=s?.thumbnail;
  if(!/^ast_rthumb_[a-f0-9]{32}$/.test(id)||p?.schema_version!=='native-publication-thumbnail-review-v1'||p.workspace_id!==row.workspace_id||p.project_id!==row.project_id
    ||p.thumbnail_asset_id!==id||p.render_job_id!==s.final_job_id||p.final_sha256!==s.final_sha256||p.document_sha256!==s.document_sha256||p.render_snapshot_sha256!==s.final_job_snapshot_sha256
    ||!sha(p.thumbnail_snapshot_sha256)||!sha(p.image?.sha256)||p.image.content_type!=='image/png'||p.image.rights_status!=='unknown'||p.image.license!==null
    ||p.status!=='passed'||p.scope!=='dry_run_metadata_review'||p.original_source_rights_review_still_required!==true||p.publishing_authorized!==false||p.rights_independently_verified!==false)
    throw new Error('Thumbnail đã duyệt không khớp video và ảnh gốc.');
  if(stage==null){if(row.receipt)throw new Error('Chưa có xác nhận thumbnail để hoàn tất.');return null;}
  const acknowledged=stage.status==='response_received';
  if(stage.schema_version!=='native-official-thumbnail-stage-v1'||['publication_id','workspace_id','project_id','snapshot_sha256','mock'].some(k=>stage[k]!==row[k])
    ||stage.image_sha256!==p.image.sha256||!['not_started','dispatch_intent','response_received','outcome_unknown'].includes(stage.status)
    ||stage.provider_response_acknowledged!==acknowledged||['remote_image_bytes_verified','rights_independently_verified','publishing_authorized','automatic_retry','token_returned'].some(k=>stage[k]!==false)
    ||stage.status!=='not_started'&&(!sha(stage.intent_sha256)||!/^[A-Za-z0-9_-]{11}$/.test(stage.remote_post_id??''))
    ||acknowledged&&(!sha(stage.response_sha256)||!sha(stage.result_sha256))||stage.response_sha256!==null&&!sha(stage.response_sha256)
    ||!acknowledged&&stage.result_sha256!==null||stage.status==='not_started'&&[stage.intent_sha256,stage.response_sha256,stage.result_sha256,stage.remote_post_id].some(v=>v!==null)
    ||row.receipt&&(!acknowledged||stage.remote_post_id!==row.receipt.remote_post_id))throw new Error('Nhật ký thumbnail chưa được xác nhận hoặc không đúng yêu cầu.');
  return stage;
}
export function initializeNativeOfficialPublications({api,getState,root=document,onMessage=()=>{},onWorking=()=>{},onSelection=()=>{},uuid=()=>crypto.randomUUID()}){
  const card=root.getElementById('native-official-publications-card');card.replaceChildren();
  const node=(tag,text,id)=>{const n=root.createElement(tag);if(text)n.textContent=text;if(id)n.id='native-official-publish-'+id;return n;};
  const button=(text,id,permission='manage')=>{const n=node('button',text,id);n.type='button';n.className='secondary';n.dataset.vfPermission=permission;return n;};
  const config=button('Đọc cấu hình','config'),sources=button('Đọc video và xác minh tài khoản','sources'),sourceMore=button('Đọc thêm nguồn','source-more'),
    profile=node('select',null,'profile'),dryRun=node('select',null,'dry-run'),account=node('select',null,'account'),scheduled=node('input',null,'scheduled'),create=button('Chuẩn bị review xuất bản','create'),
    history=button('Đọc lịch sử xuất bản','history-read','read'),more=button('Đọc trang tiếp','more','read'),read=button('Đọc trạng thái đã lưu','read','read'),
    ack=node('input',null,'ack'),ackLabel=node('label'),ackCaption=node('span'),approve=button('Duyệt xuất bản','approve'),renew=button('Duyệt tiếp phiên hiện tại','renew'),
    cancel=button('Hủy yêu cầu chưa gửi','cancel'),revoke=button('Dừng quyền gửi của yêu cầu này','revoke'),sendAck=node('input',null,'send-ack'),sendLabel=node('label'),sendCaption=node('span'),
    step=button('Gửi bước tiếp theo','step'),poll=button('Đọc xử lý tại nền tảng','poll'),status=node('p',null,'status'),list=node('div',null,'history'),detail=node('pre',null,'detail');
  ack.type='checkbox';sendAck.type='checkbox';ackLabel.append(ackCaption,ack);sendLabel.append(sendCaption,sendAck);
  scheduled.type='datetime-local';scheduled.step='1';
  const labeled=(text,control)=>{const label=node('label',text);label.append(control);return label;};
  const hint=node('p','Tự động đăng đang tắt. Chủ không gian cần cài cấu hình và duyệt riêng. Mỗi lần gửi chỉ thực hiện một bước; đọc lịch sử để kiểm tra kết quả.');hint.className='hint';
  const accountLabel=labeled('Xác minh tài khoản hiện tại',account),scheduleLabel=labeled('Giờ xuất bản (để trống để dùng metadata đã kiểm tra)',scheduled),
    scheduleHint=node('p','Giờ theo thiết bị: '+Intl.DateTimeFormat().resolvedOptions().timeZone+'. Lịch mới cần video có quyền riêng tư private.'),accountCaption=node('span','Xác minh tài khoản hiện tại');
  accountLabel.textContent='';accountLabel.replaceChildren(accountCaption,account);
  card.append(node('summary','Xuất bản qua API nền tảng'),hint,config,sources,sourceMore,labeled('Tài khoản xuất bản',profile),labeled('Video đã kiểm tra mô phỏng',dryRun),
    accountLabel,scheduleLabel,scheduleHint,create,history,list,more,read,status,ackLabel,approve,renew,cancel,revoke,sendLabel,step,poll,detail);
  let generation=0,scope='',working=false,profiles=[],vault=null,dryRows=[],accountRows=[],sourceCursors=[null,null],rows=[],cursor=null,selected=null,dispatch=null;
  const keys=new Map(),sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v),nopu=v=>typeof v==='string'&&/^nopu_[a-f0-9]{32}$/.test(v);
  const context=()=>{const s=getState();return JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.project?.archived,s.canManage,s.dirty,s.active]);};
  const base=s=>'/api/projects/'+s.project.id,endpoint=s=>base(s)+'/official-publications';
  const currentProfile=()=>profiles.find(p=>p.target.profile_id===profile.value),currentDry=()=>dryRows.find(r=>r.publication_id===dryRun.value),currentAccount=()=>accountRows.find(r=>(currentProfile()?.target.platform==='tiktok'?r.draft_id:r.check_id)===account.value);
  const targetSame=(a,b)=>['workspace_id','profile_id','profile_version','platform','provider_key','target_account_id','credential_binding_sha256'].every(k=>a?.[k]===b?.[k]);
  const ready=s=>s.canManage&&s.project&&!s.dirty&&!s.busy&&!s.active&&!s.project.archived;
  const current=s=>selected?.snapshot.project_revision===s.project?.revision;
  const originalJob=()=>selected?.snapshot.target.platform==='tiktok'&&dispatch?.provider_job&&['uploaded','reconciliation_required'].includes(dispatch.dispatch?.phase);
  const remoteReady=s=>Boolean(originalJob())&&s.canManage&&s.project&&!s.busy&&!s.project.archived;
  function controls(){const s=getState(),blocked=working||s.busy,p=currentProfile(),d=currentDry(),a=currentAccount(),phase=dispatch?.dispatch?.phase;
    config.disabled=blocked||!s.canManage;sources.disabled=blocked||!s.canManage||!s.project;sourceMore.disabled=blocked||!s.canManage||!sourceCursors.some(Boolean)||dryRows.length>=500||accountRows.length>=500;
    for(const select of [profile,dryRun,account])select.disabled=blocked||!s.canManage;
    const tiktok=p?.target.platform==='tiktok';scheduled.disabled=blocked||!s.canManage||tiktok;scheduleLabel.hidden=scheduleHint.hidden=tiktok;
    accountCaption.textContent=tiktok?'Draft TikTok đã duyệt cho video này':'Xác minh tài khoản hiện tại';sources.textContent=tiktok?'Đọc video và draft TikTok':'Đọc video và xác minh tài khoản';
    create.disabled=blocked||!ready({...s,busy:false})||p?.status!=='CONFIGURED'||vault?.status!=='CONFIGURED'||!d||!a;
    history.disabled=blocked||!s.project;more.disabled=blocked||!cursor||rows.length>=500;read.disabled=blocked||!selected;
    const mutate=!blocked&&ready({...s,busy:false})&&current(s),remote=!blocked&&remoteReady({...s,busy:false});
    approve.disabled=!mutate||selected?.status!=='awaiting_publish_approval'||!ack.checked;
    const thumbnailUnknown=['dispatch_intent','outcome_unknown'].includes(dispatch?.thumbnail_stage?.status);
    renew.disabled=!(mutate||remote)||thumbnailUnknown||!['queued','review_required'].includes(selected?.status)||!['prepared','uploading','reconciliation_required','uploaded'].includes(phase)||!ack.checked;
    cancel.disabled=!mutate||!(['awaiting_publish_approval','not_configured'].includes(selected?.status)||['queued','review_required'].includes(selected?.status)&&phase==='prepared'&&dispatch?.dispatch.private_session_ref===null);
    revoke.disabled=blocked||!s.canManage||!s.project||!selected?.approval_id||!['queued','running','review_required'].includes(selected?.status);
    ack.disabled=!(mutate||remote)||!['awaiting_publish_approval','queued','review_required'].includes(selected?.status);
    sendAck.disabled=!(mutate||remote)||selected?.status!=='queued'||!dispatch;
    const delayed=Boolean(dispatch?.retry_not_before&&Date.parse(dispatch.retry_not_before)>Date.now());
    step.disabled=!(mutate||remote&&phase==='reconciliation_required')||!sendAck.checked||selected?.status!=='queued'||!['prepared','uploading','reconciliation_required'].includes(phase)||delayed;
    poll.disabled=!(mutate||remote)||thumbnailUnknown||!sendAck.checked||selected?.status!=='queued'||phase!=='uploaded'||delayed;
    poll.textContent=dispatch?.thumbnail_stage?.status==='not_started'?'Gửi thumbnail đã duyệt':'Đọc xử lý tại nền tảng';
  }
  function render(){list.replaceChildren();for(const r of rows){const b=button(`${r.snapshot.target.platform} · ${r.mock?'Mô phỏng':'API thật'} · ${r.snapshot.metadata?.title??r.publication_id} · ${r.status}`,'row-'+r.publication_id,'read');
      b.disabled=working||getState().busy;b.addEventListener('click',()=>{if(working||getState().busy)return;selected=r;dispatch=null;ack.checked=false;sendAck.checked=false;render();});list.append(b);}
    status.textContent=selected?(selected.published?'Nền tảng đã xác nhận xuất bản qua API.':selected.mock_publication_complete?'Luồng mô phỏng hoàn tất. Video chưa được đăng thật.':
      `${selected.mock?'Mô phỏng':'API thật'} · ${selected.status} · ${dispatch?.dispatch?.phase??'Đọc trạng thái trước khi gửi bước tiếp theo.'}`):`${profiles.length} cấu hình đã đọc. Tự động đăng đang tắt.`;
    if(dispatch?.retry_not_before)status.textContent+=' · Có thể thử lại sau '+dispatch.retry_not_before;
    if(selected?.snapshot.target.platform==='tiktok'&&selected.receipt)status.textContent+=' · '+(selected.receipt.privacy_level==='SELF_ONLY'?'Chỉ mình tôi; không có ID công khai.':selected.receipt.public_post_ids.length?'ID công khai: '+selected.receipt.public_post_ids.join(', '):'Chưa có ID công khai.');
    if(originalJob()&&!current(getState()))status.textContent+=' · Theo dõi job gốc của phiên bản '+selected.snapshot.project_revision+'.';
    ackCaption.textContent=selected?.mock?'Tôi duyệt riêng luồng mô phỏng này; chưa đăng thật.':'Tôi duyệt xuất bản qua API thật tới tài khoản và video đã chọn.';
    sendCaption.textContent=selected?.mock?'Tôi cho phép thực hiện một bước mô phỏng.':'Tôi cho phép gửi một bước hoặc đọc xử lý qua API thật.';
    detail.textContent=selected?JSON.stringify({target:selected.snapshot.target,metadata:selected.snapshot.metadata,disclosures:selected.snapshot.disclosures,
      revision:selected.snapshot.project_revision,final_sha256:selected.snapshot.final_sha256,snapshot_sha256:selected.snapshot_sha256,
      status:selected.status,approval_id:selected.approval_id,thumbnail:selected.snapshot.thumbnail??null,thumbnail_stage:selected.thumbnail_stage??null,dispatch,receipt:selected.receipt},null,2):'Đọc cấu hình và chọn video hiện tại để chuẩn bị review.';controls();onSelection();}
  function sync(){const next=context();if(next!==scope){const prior=JSON.parse(scope||'[]'),s=getState(),keep=originalJob()&&prior[0]===s.workspace_id&&prior[1]===s.project?.id;
      scope=next;generation++;profiles=[];vault=null;dryRows=[];accountRows=[];rows=keep?rows:[];selected=keep?selected:null;dispatch=keep?dispatch:null;cursor=null;sourceCursors=[null,null];
      for(const select of [profile,dryRun,account]){select.replaceChildren();select.value='';}scheduled.value='';ack.checked=false;sendAck.checked=false;}render();}
  function validateProfile(p){const s=getState(),t=p?.target;
    if(p?.schema_version==='native-official-tiktok-publishing-factory-v1')return validateTikTokPublishingFactory(p,s.workspace_id);
    if(p?.schema_version!=='native-official-publishing-factory-v1'||t?.workspace_id!==s.workspace_id||t.platform!=='youtube'||t.provider_key!=='youtube-data-api-publishing'
      ||!/^ppf_[A-Za-z0-9_-]{4,60}$/.test(t.profile_id??'')||!Number.isInteger(t.profile_version)||t.profile_version<1||!sha(t.credential_binding_sha256)
      ||typeof t.target_account_id!=='string'||!t.target_account_id||t.target_account_id.length>255
      ||!sha(p.configuration_sha256)||!sha(p.target_binding_sha256)||!['CONFIGURED','NOT_CONFIGURED'].includes(p.status)||typeof p.mock!=='boolean'
      ||p.token_returned!==false||p.automatic_publishing!==false||p.credential_verified!==false||typeof p.external_actions_enabled!=='boolean'||p.mock&&p.external_actions_enabled
      ||!['publish_enabled','external_execution_enabled','owner_gate_enabled'].every(k=>typeof p.gates?.[k]==='boolean')||p.status==='CONFIGURED'&&!Object.values(p.gates).every(v=>v===true))throw new Error('Cấu hình xuất bản không đúng không gian.');return p;}
  function validateRow(r){const s=getState(),x=r?.snapshot;
    if(x?.schema_version==='native-official-tiktok-publication-snapshot-v1')return validateTikTokPublication(r,s);
    if(r?.schema_version!=='native-official-publication-v1'||!nopu(r.publication_id)||r.workspace_id!==s.workspace_id||r.project_id!==s.project?.id||!sha(r.snapshot_sha256)||!sha(r.request_fingerprint)
      ||typeof r.mock!=='boolean'||r.token_returned!==false||x?.workspace_id!==s.workspace_id||x.project_id!==s.project.id||x.mock!==r.mock||!sha(x.final_sha256)||!sha(x.configuration_sha256)
      ||x.target?.workspace_id!==s.workspace_id||x.target.platform!=='youtube'||x.dry_run_receipt_is_publish_authority!==false||x.account_check_is_publish_authority!==false||x.separate_owner_publish_approval_required!==true
      ||!Number.isInteger(x.project_revision)||x.project_revision<1||!['awaiting_publish_approval','not_configured','queued','running','cancelled','review_required','completed'].includes(r.status)
      ||r.published!==(r.status==='completed'&&!r.mock)||r.mock_publication_complete!==(r.status==='completed'&&r.mock)||Boolean(r.receipt)!==(r.status==='completed'))throw new Error('Yêu cầu xuất bản không đúng dự án hoặc trạng thái.');
    if(r.receipt&&(r.receipt.mock!==r.mock||r.receipt.external_action!==!r.mock||r.receipt.mode!=='live'||r.receipt.platform!=='youtube'||r.receipt.provider_key!=='youtube-data-api-publishing'
      ||r.receipt.request_fingerprint!==r.request_fingerprint||r.receipt.remote_url!==null||!/^[A-Za-z0-9_-]{11}$/.test(r.receipt.remote_post_id??'')))throw new Error('Bằng chứng xuất bản không hợp lệ.');validateOfficialThumbnailStage(r.thumbnail_stage,r);return r;}
  function validateDispatch(v,r){const s=getState(),d=v?.dispatch;
    if(r.snapshot.target.platform==='tiktok')return validateTikTokDispatch(v,r);
    if(v?.schema_version!=='native-official-publish-dispatch-v1'||v.workspace_id!==s.workspace_id||v.project_id!==s.project?.id||v.publication_id!==r.publication_id||v.snapshot_sha256!==r.snapshot_sha256
      ||v.mock!==r.mock||v.token_returned!==false||v.session_uri_returned!==false||v.published!==r.published||v.mock_publication_complete!==r.mock_publication_complete
      ||JSON.stringify(v.receipt)!==JSON.stringify(r.receipt)||v.retry_not_before!==null&&(typeof v.retry_not_before!=='string'||!Number.isFinite(Date.parse(v.retry_not_before))))throw new Error('Trạng thái xuất bản không khớp yêu cầu.');
    if(d&&(!Number.isInteger(d.version)||d.version<1||!Number.isInteger(d.total_bytes)||d.total_bytes<1||!Number.isInteger(d.acknowledged_bytes)||d.acknowledged_bytes<0||d.acknowledged_bytes>d.total_bytes
      ||d.private_session_ref!==null&&!/^nups_[a-f0-9]{32}$/.test(d.private_session_ref??'')))throw new Error('Tiến độ gửi không hợp lệ.');
    validateOfficialThumbnailStage(v.thumbnail_stage,r);
    if(JSON.stringify(v.thumbnail_stage)!==JSON.stringify(r.thumbnail_stage)||v.thumbnail_stage?.remote_post_id!=null&&v.thumbnail_stage.remote_post_id!==d?.remote_post_id)throw new Error('Thumbnail không khớp tiến độ video.');return v;}
  async function invoke(fn){if(working)return;const s=getState();if(s.busy)return onMessage('Chờ thao tác hiện tại hoàn tất.',true);const version=generation,expected=context();working=true;onWorking(true);controls();
    try{const apply=await fn(s);if(version===generation&&expected===context())apply();}
    catch(error){if(version===generation&&expected===context())onMessage(error.message,true);}
    finally{working=false;onWorking(false);render();}}
  const setOptions=(select,items,id,label)=>{const previous=select.value;select.replaceChildren();for(const item of items){const option=node('option',label(item));option.value=id(item);select.append(option);}select.value=items.some(r=>id(r)===previous)?previous:items[0]?id(items[0]):'';};
  function sourceOptions(){const p=currentProfile(),s=getState();if(p?.target.platform==='tiktok'){
      setOptions(account,accountRows.filter(r=>tikTokSourceMatches(r,null,p,s)),r=>r.draft_id,r=>r.snapshot.request.metadata.title+' · '+r.snapshot.request.choices.privacy_level);
      const draft=currentAccount();setOptions(dryRun,dryRows.filter(r=>draft&&tikTokSourceMatches(draft,r,p,s)),r=>r.publication_id,r=>r.snapshot.request.metadata.title);return;}
    setOptions(dryRun,dryRows.filter(r=>r.status==='dry_run_succeeded'&&r.snapshot.request.revision===s.project?.revision&&r.snapshot.request.platform==='youtube'),r=>r.publication_id,r=>r.snapshot.request.metadata.title);
    setOptions(account,accountRows.filter(r=>r.status==='succeeded'&&r.snapshot.project_revision===s.project?.revision&&r.snapshot.mock===p?.mock&&targetSame(r.snapshot.target,p?.target)),r=>r.check_id,r=>r.snapshot.target.target_account_id+' · '+r.check_id);}
  const readConfig=()=>invoke(async s=>{if(!s.canManage)throw new Error('Chỉ chủ không gian được đọc cấu hình xuất bản.');const v=await api('/api/connections/official-publishing');
    if(v?.schema_version!=='native-official-publishing-factories-v1'||v.workspace_id!==s.workspace_id||v.automatic_publishing!==false||v.token_returned!==false||v.separate_owner_publish_approval_required!==true
      ||!Array.isArray(v.profiles)||v.profiles.length>100||v.session_vault?.workspace_id!==s.workspace_id||!['CONFIGURED','NOT_CONFIGURED'].includes(v.session_vault.status)||v.session_vault.session_uri_returned!==false||v.session_vault.oauth_token_stored!==false)throw new Error('Cấu hình xuất bản không hợp lệ.');
    const values=v.profiles.map(validateProfile);if(new Set(values.map(p=>p.target.profile_id)).size!==values.length)throw new Error('Cấu hình tài khoản bị trùng.');
    return()=>{profiles=values;vault=v.session_vault;dryRows=[];accountRows=[];sourceCursors=[null,null];scheduled.value='';setOptions(profile,profiles,p=>p.target.profile_id,p=>`${p.target.platform} · ${p.mock?'Mô phỏng':'API thật'} · ${p.target.target_account_id} · ${p.status}`);sourceOptions();};});
  const readSources=(next=false)=>invoke(async s=>{if(!s.canManage||!s.project)throw new Error('Chọn dự án và dùng quyền chủ không gian.');
    const tiktok=currentProfile()?.target.platform==='tiktok',paths=[base(s)+'/publications',base(s)+(tiktok?'/tiktok-creators/drafts':'/account-checks')];const pages=await Promise.all(paths.map((path,i)=>next&&!sourceCursors[i]?null:api(path+'?limit=25'+(next?'&cursor='+encodeURIComponent(sourceCursors[i]):''))));
    const values=pages.map((v,i)=>{if(v===null)return[];const schema=i?(tiktok?'native-tiktok-creator-page-v1':'native-official-account-check-page-v1'):'native-publication-page-v1';
      if(v?.schema_version!==schema||v.workspace_id!==s.workspace_id||v.project_id!==s.project.id||!Array.isArray(v.items)||v.items.length>25||v.token_returned!==false&&i===1
        ||v.next_cursor!==null&&(typeof v.next_cursor!=='string'||v.next_cursor.length>2048))throw new Error('Nguồn review không đúng phạm vi.');
      if(i===1&&tiktok){if(v.kind!=='draft'||v.publishing_enabled!==false||typeof v.truncated!=='boolean'||v.truncated!==(v.next_cursor!==null)||v.next_cursor!==null&&!/^ntpd_[a-f0-9]{32}$/.test(v.next_cursor))throw new Error('Trang draft TikTok không đúng phạm vi.');return v.items.map(r=>validateTikTokDraft(r,s));}
      for(const r of v.items){if(r.workspace_id!==s.workspace_id||r.project_id!==s.project.id||!sha(r.snapshot_sha256))throw new Error('Nguồn review không đúng dự án.');
        if(i===0&&(r.schema_version!=='native-publication-v1'||!/^npub_[a-f0-9]{32}$/.test(r.publication_id??'')||r.mock!==true||r.external_action!==false||r.publish_enabled!==false||r.snapshot?.request?.mode!=='dry_run'))throw new Error('Nguồn video chưa được kiểm tra mô phỏng.');
        if(i===0&&r.status==='dry_run_succeeded'&&(!sha(r.request_fingerprint)||r.receipt?.request_fingerprint!==r.request_fingerprint||r.receipt.mode!=='dry_run'||r.receipt.mock!==true
          ||r.receipt.external_action!==false||r.receipt.provider_key!=='mock-publishing'||r.receipt.remote_post_id!==null||r.receipt.remote_url!==null))throw new Error('Bằng chứng mô phỏng nguồn không hợp lệ.');
        if(i===1&&(r.schema_version!=='native-official-account-check-v1'||!/^nack_[a-f0-9]{32}$/.test(r.check_id??'')||r.token_returned!==false||r.publishing_enabled!==false||typeof r.snapshot?.mock!=='boolean'
          ||r.status==='succeeded'&&(r.result?.account_match!==true||r.result.read_only!==true||r.result.mock!==r.snapshot.mock||r.result.external_call!==!r.snapshot.mock)))throw new Error('Nguồn xác minh tài khoản không hợp lệ.');}return v.items;});
    return()=>{dryRows=[...new Map([...(next?dryRows:[]),...values[0]].map(r=>[r.publication_id,r])).values()].slice(0,500);accountRows=[...new Map([...(next?accountRows:[]),...values[1]].map(r=>[tiktok?r.draft_id:r.check_id,r])).values()].slice(0,500);
      sourceCursors=pages.map((v,i)=>v?v.next_cursor:sourceCursors[i]);sourceOptions();};});
  const readHistory=(next=false)=>invoke(async s=>{if(!s.project)throw new Error('Chọn dự án để đọc lịch sử.');if(next&&!cursor)return()=>{};
    const v=await api(endpoint(s)+'?limit=25'+(next?'&cursor='+encodeURIComponent(cursor):''));
    if(v?.schema_version!=='native-official-publication-page-v1'||v.workspace_id!==s.workspace_id||v.project_id!==s.project.id||v.token_returned!==false||v.session_uri_returned!==false||v.automatic_publishing!==false
      ||!Array.isArray(v.items)||v.items.length>25||v.next_cursor!==null&&(typeof v.next_cursor!=='string'||v.next_cursor.length>2048))throw new Error('Lịch sử xuất bản không hợp lệ.');const values=v.items.map(validateRow);
    return()=>{rows=[...new Map([...(next?rows:[]),...values].map(r=>[r.publication_id,r])).values()].slice(0,500);selected=values[0]??selected;dispatch=null;cursor=v.next_cursor;ack.checked=false;sendAck.checked=false;};});
  const readState=()=>invoke(async s=>{if(!selected)throw new Error('Chọn yêu cầu để đọc trạng thái.');const identity=selected.publication_id;
    const r=validateRow(await api(endpoint(s)+'/'+identity)),d=validateDispatch(await api(endpoint(s)+'/'+identity+'/state'),r);
    return()=>{selected=r;dispatch=d;rows=rows.map(v=>v.publication_id===identity?r:v);ack.checked=false;sendAck.checked=false;};});
  const execute=action=>invoke(async s=>{const remote=remoteReady(s)&&(['renew','poll'].includes(action)||action==='step'&&dispatch.dispatch.phase==='reconciliation_required');
    if(action==='revoke'?!s.canManage||!s.project:!ready(s)&&!remote)throw new Error('Lưu dự án, chờ xử lý và dùng quyền chủ không gian.');let path=endpoint(s),body,key=null,identity=selected?.publication_id;
    if(!['create','approve','renew','revoke','cancel','step','poll'].includes(action))throw new Error('Thao tác xuất bản không hợp lệ.');
    if(action==='create'){const p=currentProfile(),d=currentDry(),a=currentAccount();if(p?.status!=='CONFIGURED'||vault?.status!=='CONFIGURED'||!d||!a)throw new Error('Chọn cấu hình, video đã kiểm tra và xác minh tài khoản hiện tại.');
      if(p.target.platform==='tiktok'){if(!tikTokSourceMatches(a,d,p,s)||scheduled.value)throw new Error('Chọn đúng draft/final/metadata đã duyệt; TikTok không nhận lịch thay thế ở bước này.');
        body={schema_version:'native-official-tiktok-publication-request-v1',revision:s.project.revision,dry_run_publication_id:d.publication_id,expected_dry_run_snapshot_sha256:d.snapshot_sha256,creator_draft_id:a.draft_id,expected_creator_draft_snapshot_sha256:a.snapshot_sha256,profile_id:p.target.profile_id,expected_configuration_sha256:p.configuration_sha256};}
      else body={revision:s.project.revision,dry_run_publication_id:d.publication_id,expected_dry_run_snapshot_sha256:d.snapshot_sha256,account_check_id:a.check_id,profile_id:p.target.profile_id,expected_configuration_sha256:p.configuration_sha256};
      if(scheduled.value){const at=new Date(scheduled.value);
        if(!/^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?$/.test(scheduled.value)||!Number.isFinite(at.getTime())||at.getTime()-Date.now()<60000||d.snapshot.request.metadata.privacy!=='private')throw new Error('Chọn giờ tương lai còn ít nhất một phút và metadata private.');
        body.metadata={...d.snapshot.request.metadata,scheduled_at:at.toISOString()};}
    }else{if(!selected||action!=='revoke'&&!current(s)&&!remote)throw new Error('Chọn yêu cầu đúng phiên bản hiện tại.');
      if(action==='revoke'&&(!selected.approval_id||!['queued','running','review_required'].includes(selected.status)))throw new Error('Chọn yêu cầu đã có quyền gửi để dừng.');
      path+='/'+identity+'/'+action;body={expected_snapshot_sha256:selected.snapshot_sha256};
      if(action==='approve'||action==='renew'){if(!ack.checked)throw new Error('Xác nhận duyệt riêng yêu cầu này.');body={...body,acknowledged_official_publication:true,valid_for_seconds:900};}
      if(action==='renew'||action==='step'||action==='poll'){if(!dispatch?.dispatch)throw new Error('Đọc trạng thái hiện tại trước.');body.expected_dispatch_version=dispatch.dispatch.version;}
      if(['renew','poll'].includes(action)&&['dispatch_intent','outcome_unknown'].includes(dispatch?.thumbnail_stage?.status))throw new Error('Kết quả gửi thumbnail chưa rõ. Cần kiểm tra riêng trước khi tiếp tục.');
      if(action==='step'||action==='poll'){const phase=dispatch?.dispatch?.phase;
        if(!sendAck.checked||selected.status!=='queued'||action==='step'&&!['prepared','uploading','reconciliation_required'].includes(phase)||action==='poll'&&phase!=='uploaded')throw new Error('Cho phép riêng bước hợp lệ trong trạng thái hiện tại.');
        if(dispatch.retry_not_before&&Date.parse(dispatch.retry_not_before)>Date.now())throw new Error('Chờ thời điểm thử lại đã lưu.');}
    }
    if(action==='create'||action==='renew'){key=JSON.stringify([s.workspace_id,s.project.id,action,identity,body]);if(!keys.has(key))keys.set(key,uuid());body.request_key=keys.get(key);}
    try{const v=await api(path,body);
      if(action!=='step')validateRow(v);
      if(key)keys.delete(key);
      const r=action==='step'?validateRow(await api(endpoint(s)+'/'+identity)):v;
      if(action==='step')validateDispatch(v,r);
      return()=>{selected=r;dispatch=null;rows=[r,...rows.filter(row=>row.publication_id!==r.publication_id)].slice(0,500);cursor=null;ack.checked=false;sendAck.checked=false;
        onMessage(action==='revoke'?'Đã dừng quyền gửi. Lịch sử và phiên tải được giữ; thao tác này không xóa bài tại nền tảng.':r.mock?'Đã lưu bước mô phỏng. Video chưa được đăng thật.':'Đã lưu kết quả. Đọc trạng thái trước khi thực hiện bước tiếp theo.');};
    }catch(error){if(action==='step'||action==='poll')dispatch=null;throw error;}});
  config.addEventListener('click',()=>readConfig());sources.addEventListener('click',()=>readSources());sourceMore.addEventListener('click',()=>readSources(true));history.addEventListener('click',()=>readHistory());more.addEventListener('click',()=>readHistory(true));read.addEventListener('click',()=>readState());
  for(const [control,action] of [[create,'create'],[approve,'approve'],[renew,'renew'],[cancel,'cancel'],[revoke,'revoke'],[step,'step'],[poll,'poll']])control.addEventListener('click',()=>execute(action));
  ack.addEventListener('change',controls);sendAck.addEventListener('change',controls);profile.addEventListener('change',()=>{generation++;dryRows=[];accountRows=[];sourceCursors=[null,null];selected=null;dispatch=null;scheduled.value='';sourceOptions();ack.checked=false;sendAck.checked=false;render();});
  for(const select of[dryRun,account])select.addEventListener('change',()=>{generation++;sourceOptions();ack.checked=false;sendAck.checked=false;controls();});sync();
  return{sync,controls,readConfig,readSources,readHistory,readState,execute,isWorking:()=>working,currentBinding:()=>({publication:selected,dispatch})};
}
