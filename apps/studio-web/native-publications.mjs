import {validateRenderThumbnail} from './native-render-thumbnail.mjs';
import {validateTikTokDraft} from './native-tiktok-creators.mjs';

export const supportsNativePublications = session => session?.capabilities?.native_publication_review === true;
const labels = {blocked:'Cần bổ sung bằng chứng',awaiting_publish_approval:'Chờ duyệt mô phỏng',queued:'Chờ mô phỏng',
  scheduled:'Mô phỏng đã lên lịch',dry_run_succeeded:'Mô phỏng hoàn tất · chưa đăng',cancelled:'Đã hủy'};

export function nativePublicationIntent(state, values, requestKey) {
  const p=state.project, job=p?.jobs?.find(row=>row.kind==='render'&&row.status==='succeeded'&&row.revision===p.revision);
  if(!p||p.archived||state.dirty||state.busy||!state.canEdit||!p.approval||!job||job.final_review?.decision!=='approve'
      ||job.final_review.revision!==p.revision||job.final_review.artifact_sha256!==job.result?.qc?.final_sha256)
    throw new Error('Lưu thay đổi, xem và duyệt video cuối hiện tại trước khi chuẩn bị phân phối.');
  if(!['youtube','tiktok','instagram_reels','facebook'].includes(values.platform)||!values.title?.trim()
      ||!['private','unlisted','public'].includes(values.privacy))throw new Error('Kiểm tra nền tảng, tiêu đề và quyền riêng tư.');
  let scheduled=null;
  if(values.scheduled){const date=new Date(values.scheduled);if(!Number.isFinite(date.getTime()))throw new Error('Giờ mô phỏng không hợp lệ.');scheduled=date.toISOString();}
  let thumbnail;
  if(values.useThumbnail!==undefined&&typeof values.useThumbnail!=='boolean')throw new Error('Xác nhận thumbnail không hợp lệ.');
  if(values.useThumbnail===true){const t=validateRenderThumbnail(values.thumbnailSelection,state);if(t.snapshot.request.render_job_id!==job.id||t.snapshot.request.revision!==p.revision||t.snapshot.input_binding.record.observation.rendered_video_sha256!==job.result.qc.final_sha256)throw new Error('Chọn thumbnail từ đúng video cuối hiện tại.');thumbnail=t.thumbnail_asset_id;}
  return {schema_version:'native-publication-request-v1',revision:p.revision,final_job_id:job.id,platform:values.platform,mode:'dry_run',
    metadata:{title:values.title.trim(),description:values.description??'',caption:values.caption??'',
      hashtags:(values.hashtags??'').split(/\s+/).filter(Boolean),privacy:values.privacy,scheduled_at:scheduled,...(thumbnail?{thumbnail_asset_id:thumbnail}:{})},request_key:requestKey};
}

export function nativeTikTokDryRunIntent(state,draft,requestKey){
  const d=validateTikTokDraft(draft,state),r=d.snapshot.request,m=r.metadata;
  const body=nativePublicationIntent(state,{platform:'tiktok',title:m.title,description:m.description,caption:m.caption,hashtags:m.hashtags.join(' '),privacy:m.privacy,scheduled:'',useThumbnail:false},requestKey);
  if(body.revision!==r.revision||body.final_job_id!==r.final_job_id||state.project.jobs.find(j=>j.id===body.final_job_id)?.result?.qc?.final_sha256!==r.expected_final_sha256)
    throw new Error('Draft TikTok không thuộc video cuối hiện tại.');
  return {...body,metadata:structuredClone(m)};
}
export function initializeNativePublications({api,getState,getTikTokDraft=()=>null,getThumbnailSelection=()=>null,getThumbnailRightsSelection=()=>null,root=document,onMessage=()=>{},uuid=()=>crypto.randomUUID()}) {
  const $=id=>root.getElementById(id);let scope='',rows=[],selected=null,cursor=null,working=false,revision=0;
  const keys=new Map(),context=()=>{const p=getState().project,job=p?.jobs?.find(row=>row.kind==='render'&&row.status==='succeeded'&&row.revision===p.revision);
    const t=getThumbnailSelection(),r=getThumbnailRightsSelection();return JSON.stringify([p?.id,p?.revision,p?.archived,job?.id,job?.final_review?.id,job?.final_review?.decision,t?.thumbnail_asset_id,t?.snapshot_sha256,r?.override_id,r?.snapshot_sha256]);};
  const endpoint=()=>`/api/projects/${getState().project.id}/publications`;
  const values=()=>({platform:$('native-publish-platform').value,title:$('native-publish-title').value,
    description:$('native-publish-description').value,caption:$('native-publish-caption').value,
    hashtags:$('native-publish-hashtags').value,privacy:$('native-publish-privacy').value,scheduled:$('native-publish-scheduled').value,
    useThumbnail:$('native-publish-thumbnail').checked,thumbnailSelection:getThumbnailSelection()});
  function element(tag,text){const node=root.createElement(tag);node.textContent=text;return node;}
  function sync(){const next=context();if(next!==scope){const old=JSON.parse(scope||'[]')[0];scope=next;revision++;rows=[];selected=null;cursor=null;working=false;
    $('native-publish-ack').checked=false;$('native-publish-thumbnail').checked=false;if(old!==getState().project?.id)$('native-publish-title').value=getState().project?.document?.name??'';}render();}
  function controls(){if(context()!==scope){sync();return;}const state=getState(),blocked=working||state.busy||state.dirty;
    $('native-publish-thumbnail').disabled=blocked||!state.canEdit||!getThumbnailSelection();
    let ready=true;try{nativePublicationIntent({...state,busy:false},values(),'native-ready-probe');}catch{ready=false;}
    $('native-publish-create').disabled=blocked||!ready;
    const draft=getTikTokDraft();$('native-publish-tiktok-draft').hidden=!draft;
    let draftReady=false;try{nativeTikTokDryRunIntent({...state,busy:false},draft,'native-tiktok-ready-probe');draftReady=true;}catch{}
    $('native-publish-tiktok-draft').disabled=blocked||!draftReady;
    $('native-publish-read').disabled=working||state.busy||!state.project;
    $('native-publish-more').disabled=working||state.busy||!cursor;
    const same=selected?.snapshot?.request?.revision===state.project?.revision;
    $('native-publish-approve').disabled=blocked||!state.canManage||!same||selected?.status!=='awaiting_publish_approval'||!$('native-publish-ack').checked;
    $('native-publish-run').disabled=blocked||!state.canManage||!same||!['queued','scheduled'].includes(selected?.status);
    $('native-publish-cancel').disabled=working||state.busy||!state.canManage||!selected||['dry_run_succeeded','cancelled'].includes(selected.status);
    $('native-publish-ack').disabled=blocked||!state.canManage||!same||selected?.status!=='awaiting_publish_approval';}
  function render(){const list=$('native-publish-history');list.replaceChildren();
    for(const row of rows){const button=element('button',`${row.snapshot.request.platform} · ${row.snapshot.request.metadata.title} · ${labels[row.status]??row.status}`);
      button.type='button';button.className='secondary full';button.dataset.vfPermission='read';button.addEventListener('click',()=>{selected=row;$('native-publish-ack').checked=false;render();});list.append(button);}
    $('native-publish-detail').textContent=selected?JSON.stringify({status:labels[selected.status]??selected.status,
      metadata:selected.snapshot.request.metadata,validation:selected.snapshot.validation,fingerprint:selected.request_fingerprint,
      artifact_sha256:selected.snapshot.final_sha256,approval:selected.approval,receipt:selected.receipt,failure_code:selected.failure_code},null,2):'Chọn yêu cầu đã lưu để xem kiểm tra và review.';controls();}
  function validate(row){if(row?.schema_version!=='native-publication-v1'||row.project_id!==getState().project?.id
      ||row.mock!==true||row.external_action!==false||row.publish_enabled!==false||row.snapshot?.request?.mode!=='dry_run'
      ||!/^npub_[a-f0-9]{32}$/.test(row.publication_id??'')||!/^[a-f0-9]{64}$/.test(row.request_fingerprint??''))
    throw new Error('Bằng chứng phân phối không khớp phạm vi mô phỏng.');return row;}
  async function execute(action){sync();if(working)return;const state=getState(),captured=context(),ownRevision=revision;
    if(state.busy||state.dirty)return onMessage('Lưu thay đổi và chờ thao tác hiện tại.',true);
    let path=endpoint(),body;
    try{if(action==='create'||action==='create-tiktok'){const probe=action==='create-tiktok'?nativeTikTokDryRunIntent(state,getTikTokDraft(),'native-probe-key'):nativePublicationIntent(state,values(),'native-probe-key');delete probe.request_key;
        const signature=scope+JSON.stringify(probe),key=keys.get(signature)??`native-publish-${uuid()}`;keys.set(signature,key);body={...probe,request_key:key};}
      else {if(!selected||!state.canManage)throw new Error('Chọn yêu cầu và dùng quyền chủ không gian.');
        path+=`/${selected.publication_id}/${action}`;body={expected_fingerprint:selected.request_fingerprint};
        if(action==='approve'){if(!$('native-publish-ack').checked)throw new Error('Xác nhận review mô phỏng.');
          body={...body,expected_artifact_sha256:selected.snapshot.final_sha256,acknowledged:true};}}
      working=true;controls();const result=await api(path,body);
      if(captured!==context()||ownRevision!==revision)return;
      selected=validate(result);rows=[selected,...rows.filter(row=>row.publication_id!==selected.publication_id)];$('native-publish-ack').checked=false;
      onMessage(selected.status==='blocked'?'Yêu cầu đã lưu; bổ sung bằng chứng quyền/provenance hoặc định dạng được liệt kê.':'Đã lưu mô phỏng phân phối. Video chưa được đăng ra ngoài.');
    }catch(error){if(captured===context()&&ownRevision===revision)onMessage(error.message,true);}
    finally{if(captured===context()&&ownRevision===revision){working=false;render();}}
  }
  async function read(more=false){sync();const state=getState();if(working||state.busy||!state.project||(more&&!cursor))return;
    const captured=context(),ownRevision=revision,previous=more?cursor:null;working=true;controls();
    try{const value=await api(endpoint()+`?limit=25${previous?`&cursor=${encodeURIComponent(previous)}`:''}`);
      if(captured!==context()||ownRevision!==revision)return;
      if(value?.schema_version!=='native-publication-page-v1'||value.project_id!==state.project.id||!Array.isArray(value.items)||value.items.length>25
          ||(value.next_cursor!==null&&typeof value.next_cursor!=='string'))throw new Error('Trang lịch sử phân phối không hợp lệ.');
      const incoming=value.items.map(validate);rows=more?[...rows,...incoming.filter(row=>!rows.some(old=>old.publication_id===row.publication_id))]:incoming;
      cursor=value.next_cursor;selected=rows.find(row=>row.publication_id===selected?.publication_id)??rows[0]??null;$('native-publish-ack').checked=false;
    }catch(error){if(captured===context()&&ownRevision===revision)onMessage(error.message,true);}
    finally{if(captured===context()&&ownRevision===revision){working=false;render();}}
  }
  $('native-publish-create').addEventListener('click',()=>execute('create'));$('native-publish-read').addEventListener('click',()=>read());
  $('native-publish-tiktok-draft').addEventListener('click',()=>execute('create-tiktok'));
  $('native-publish-more').addEventListener('click',()=>read(true));$('native-publish-approve').addEventListener('click',()=>execute('approve'));
  $('native-publish-run').addEventListener('click',()=>execute('dry-run'));$('native-publish-cancel').addEventListener('click',()=>execute('cancel'));
  for(const id of ['native-publish-platform','native-publish-title','native-publish-description','native-publish-caption','native-publish-hashtags','native-publish-privacy','native-publish-scheduled','native-publish-thumbnail','native-publish-ack'])$(id).addEventListener('change',()=>{if(id!=='native-publish-ack'){$('native-publish-ack').checked=false;revision++;working=false;}controls();});
  sync();return {sync,controls,read,execute};
}
