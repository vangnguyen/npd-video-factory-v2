const fields = ['visual','narration','on_screen_text','subtitle','asset_id','duration','narration_enabled','crop_strategy','motion','source_start','transition'];
export const escapeText = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
export function projectShots(project) {
  const source=project?.shot_timeline?.shots;
  if(!source)return [];
  return source.map((s,i)=>({...s,shot_id:s.shot_id??s.id,scene:s.scene??i+1,narration:s.narration??s.narration_excerpt??'',on_screen_text:s.on_screen_text??'',subtitle:s.subtitle??s.narration??s.narration_excerpt??'',duration:Number(s.duration??s.duration_seconds??0),narration_enabled:s.narration_enabled!==false,crop_strategy:s.crop_strategy??'contain',motion:s.motion??'none',source_start:Number(s.source_start??0),transition:s.transition??'cut'}));
}
export function shotMutationAllowed(project,{dirty=false,busy=false}={}) {
  return Boolean(project?.id && project.shot_timeline && !project.archived && !dirty && !busy && !(project.jobs??[]).some(j=>['queued','running','retrying'].includes(j.status)));
}
export function changedShotValues(shot,values) {
  const result={};
  for(const key of fields)if(Object.hasOwn(values,key)&&values[key]!==shot[key])result[key]=values[key];
  if(Object.hasOwn(result,'duration')&&(!Number.isFinite(result.duration)||result.duration<0.1||result.duration>180))throw new Error('Thời lượng shot phải từ 0,1 đến 180 giây.');
  if(Object.hasOwn(result,'source_start')&&(!Number.isFinite(result.source_start)||result.source_start<0))throw new Error('Thời điểm bắt đầu video phải từ 0 giây.');
  return result;
}
export function reorderedShotIds(shots,id,offset) {
  const ids=shots.map(s=>s.shot_id),index=ids.indexOf(id),target=index+offset;
  if(index<0||target<0||target>=ids.length)return ids;
  ids.splice(index,1);ids.splice(target,0,id);return ids;
}
export function safeSuggestion(project,shotId,suggestion,suggestionRevision) {
  const knownIds=new Set(projectShots(project).map(s=>s.shot_id)),affected=suggestion?.affected_shot_ids;
  return Boolean(project?.revision===suggestionRevision && suggestion?.project_id===project.id && suggestion.revision===project.revision && suggestion.timeline_sha256===project.shot_timeline?.sha256 && suggestion?.requires_human_apply===true && suggestion.operation?.type==='update' && suggestion.operation.shot_id===shotId && Array.isArray(affected) && affected.includes(shotId) && new Set(affected).size===affected.length && affected.every(id=>knownIds.has(id)));
}
export function previewLabel(preview) {
  if(!preview||preview.status==='EMPTY')return 'Xem nhanh hình ảnh · chưa có giọng đọc';
  const labels={QUEUED:'Đang chờ preview',RUNNING:`Đang dựng ${preview.completed_shots??0}/${preview.total_shots??0} shot`,READY:'Xem nhanh hình ảnh · chưa có giọng đọc',STALE:'Preview đã cũ · cần tạo lại',FAILED:'Preview lỗi · thử lại khi đã sửa',CANCELLED:'Đã hủy preview'};
  return labels[preview.status]??'Chưa có preview';
}
export function previewTimingLabel(mediaMode) {
  return mediaMode==='final'?'Bản render dùng giọng Thùy Dung đã khóa. Phụ đề theo đoạn; các shot có lời đọc dùng thời lượng audio đo được.':'Preview hình ảnh chưa tạo hay đo audio; thời điểm phụ đề là ước tính theo thời lượng shot. Bản render dùng giọng Thùy Dung đã khóa.';
}
export function boundPreview(project,preview) {
  if(!preview)return null;
  if(preview.revision!==project?.revision||preview.timeline_sha256!==project?.shot_timeline?.sha256)return {...preview,status:'STALE',video_url:null};
  if(preview.status==='READY'&&(preview.audio_mode!=='silent_visual_proxy'||preview.final_approval_eligible!==false))return {...preview,status:'FAILED',video_url:null};
  return preview;
}
export function currentStudioRender(project) {
  return project?.approval&&project.approval.revision===project.revision&&!project.archived?(project.jobs??[]).find(j=>j.kind==='render'&&j.status==='succeeded'&&j.revision===project.revision)??null:null;
}
export function scriptReviewAllowed(project,{dirty=false,busy=false}={},acknowledged=false,reviewer='') {
  return Boolean(project?.document?.proposal?.narration && !project.archived && !dirty && !busy && acknowledged && reviewer.trim() && !(project.jobs??[]).some(j=>['queued','running','retrying'].includes(j.status)));
}
export function scriptStageReview(project) {
  if(!project?.document?.proposal)return {label:'Bắt đầu',detail:''};
  if(project.script_review?.current)return {label:'Đã duyệt',detail:`Kịch bản đã được ${project.script_review.reviewer} duyệt. Hình ảnh và video cần duyệt riêng.`};
  if(!project.archived&&project.approval&&project.approval.revision===project.revision)return {label:'Đã duyệt cùng nội dung',detail:`Kịch bản đã được ${project.approval.reviewer??'người duyệt'} duyệt cùng nội dung và cách dựng ở phiên bản này. Có thể ghi nhận duyệt riêng kịch bản bằng thao tác bên dưới.`};
  return {label:'Cần duyệt',detail:'Lưu chỉnh sửa trước khi duyệt. Thao tác này chỉ duyệt lời đọc, chưa tạo giọng đọc hoặc video.'};
}
export function readableSuggestion(values,project) {
  const labels={visual:'Hình ảnh',narration:'Lời đọc',on_screen_text:'Chữ trên video',subtitle:'Phụ đề',duration:'Thời lượng',asset_id:'Nguồn',narration_enabled:'Dùng lời đọc',crop_strategy:'Khung hình',motion:'Chuyển động ảnh',source_start:'Điểm bắt đầu video',transition:'Chuyển cảnh'};
  return Object.entries(values??{}).filter(([key])=>labels[key]).map(([key,value])=>`${labels[key]}: ${key==='asset_id'?(project.document.assets??[]).find(a=>a.id===value)?.filename??'Thay nguồn':key==='duration'||key==='source_start'?`${value} giây`:typeof value==='boolean'?(value?'Có':'Không'):value}`).join(' · ');
}

export function initializeShotStudio({api,getProject,getGuards,onProject,onDirty,onMessage,onWorking=()=>{}}) {
  const $=id=>document.getElementById(id),esc=escapeText;
  let stage='script',selectedId=null,shotDirty=false,working=false,loadedKey=null,loadingKey=null,preview=null,previewTimer=null,mediaMode='shot',suggestion=null,suggestionRevision=null,draggedId=null,shownProjectId=null;
  const suggestions=new Map();
  const move=(selector,target)=>{const el=document.querySelector(selector);if(el)$(target).append(el);};
  move('#brief-card','script-stage-body');move('.editor>section:not([id])','script-stage-body');move('#proposal-card','script-stage-body');move('#image-card','assets-stage-body');move('.output-card','video-stage-body');move('#final-review-panel','video-review-body');move('#open-output','video-review-body');move('.job-card','video-review-body');
  const canvas=document.createElement('div');canvas.className='preview-canvas';
  const output=document.querySelector('.output-card');output.insertBefore(canvas,$('video-placeholder'));
  canvas.append($('video-placeholder'),$('video'));
  const image=document.createElement('img');image.id='shot-preview-image';image.alt='Nguồn của shot đang chọn';image.hidden=true;canvas.append(image);
  const proxy=document.createElement('video');proxy.id='shot-preview-video';proxy.controls=true;proxy.playsInline=true;proxy.hidden=true;proxy.preload='metadata';canvas.append(proxy);
  const caption=document.createElement('span');caption.id='shot-preview-caption';caption.className='preview-caption';caption.hidden=true;canvas.append(caption);
  const finalButton=document.createElement('button');finalButton.type='button';finalButton.id='show-final-preview';finalButton.className='secondary';finalButton.dataset.studioNav='';finalButton.textContent='Xem bản render để duyệt';finalButton.hidden=true;output.append(finalButton);
  const previewShortcut=document.createElement('button');previewShortcut.type='button';previewShortcut.id='toolbar-preview';previewShortcut.className='secondary';previewShortcut.dataset.shotControl='';previewShortcut.textContent='Preview';document.querySelector('.studio-header-actions').append(previewShortcut,$('render'));
  const sceneDetails=document.createElement('details');sceneDetails.id='all-scene-fields';const summary=document.createElement('summary');summary.textContent='Chỉnh sửa toàn bộ kịch bản / cảnh';sceneDetails.append(summary);$('scenes').before(sceneDetails);sceneDetails.append($('scenes'));
  const brandPanel=$('brand-select').closest('details');brandPanel.id='brand-panel';
  const thumbnail=assetId=>`/api/projects/${getProject().id}/media/${encodeURIComponent(assetId)}/thumbnail`;
  const assets=()=>getProject()?.document.assets??(getProject()?.document.asset?[getProject().document.asset]:[]);
  const selected=()=>projectShots(getProject()).find(s=>s.shot_id===selectedId);
  const guard=()=>({...getGuards(),busy:getGuards().busy||working});
  const message=(text,error=false)=>onMessage(text,error);
  const suggestionKey=(project,shotId)=>`${project.id}:${project.revision}:${shotId}`;
  function showSuggestion(value){suggestion=value??null;suggestionRevision=suggestion?.revision??null;const shots=projectShots(getProject()),dependencies=(suggestion?.affected_shot_ids??[]).filter(id=>id!==selectedId).map(id=>shots.find(s=>s.shot_id===id)?.scene).filter(Boolean);$('shot-ai-result').textContent=suggestion?[suggestion.rationale??'Đề xuất đã sẵn sàng.',readableSuggestion(suggestion.operation?.values,getProject()),dependencies.length?`Thời gian/âm thanh liên quan: shot ${dependencies.join(', ')}`:'',suggestion.uncertainty??''].filter(Boolean).join(' · '):'';$('shot-ai-apply').hidden=!safeSuggestion(getProject(),selectedId,suggestion,suggestionRevision);}
  function showStage(value){if(!['script','assets','storyboard','video'].includes(value))return;stage=value;document.querySelectorAll('[data-stage-panel]').forEach(el=>el.hidden=el.dataset.stagePanel!==stage);document.querySelectorAll('.stage-navigation [data-stage]').forEach(el=>{if(el.dataset.stage===stage)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current');});if(stage!=='video'){$('video').pause();proxy.pause();}}
  function setDirty(value){shotDirty=value;onDirty(value);$('studio-save-state').textContent=value?'Shot chưa lưu':getProject()?`Đã lưu · v${getProject().revision}`:'Chưa có dự án';controls();}
  function controls(){
    const project=getProject(),g=guard(),blocked=!project?.shot_timeline||project.archived||g.busy||(project.jobs??[]).some(j=>['queued','running','retrying'].includes(j.status))||(g.dirty&&!shotDirty),has=Boolean(selected());
    document.querySelectorAll('[data-shot-control]').forEach(el=>el.disabled=blocked||(!has&&!['create-preview','cancel-preview','toolbar-preview'].includes(el.id)));
    document.querySelectorAll('[data-studio-nav]').forEach(el=>el.disabled=false);
    const usedAssets=new Set((project?.document.scene_media??[]).map(b=>b.asset_id));
    document.querySelectorAll('[data-asset-control]').forEach(el=>el.disabled=!project||project.archived||g.busy||g.dirty||((project.jobs??[]).some(j=>['queued','running','retrying'].includes(j.status)))||(el.dataset.assetAction==='remove'&&usedAssets.has(el.dataset.assetId)));
    const previewShots=projectShots(project);
    $('create-preview').disabled=blocked||g.dirty||shotDirty||!previewShots.length||previewShots.some(s=>!s.asset_id)||['QUEUED','RUNNING'].includes(preview?.status);
    $('toolbar-preview').disabled=$('create-preview').disabled;
    $('cancel-preview').hidden=!['QUEUED','RUNNING'].includes(preview?.status);$('cancel-preview').disabled=working;
    for(const id of ['shot-earlier','shot-later','shot-duplicate','shot-delete','shot-regenerate','shot-revert','shot-ai-suggest','shot-ai-apply'])$(id).disabled=blocked||!has||shotDirty||g.dirty;
    const shots=projectShots(project),index=shots.findIndex(s=>s.shot_id===selectedId);
    $('shot-earlier').disabled||=index<=0;$('shot-later').disabled||=index===shots.length-1;
    $('shot-delete').disabled||=shots.length<=1;$('shot-duplicate').disabled||=shots.length>=20;$('shot-save').disabled=blocked||!has||!shotDirty;
    $('shot-regenerate').disabled||=assets().filter(a=>a.id!==selected()?.asset_id).length===0;
    $('shot-discard').disabled=working||!shotDirty;
    const kind=assets().find(a=>a.id===$('shot-asset').value)?.kind??'image';$('shot-source-start').disabled=blocked||kind!=='video';$('shot-motion').disabled=blocked||kind==='video';
    $('shot-ai-apply').disabled||=!safeSuggestion(project,selectedId,suggestion,suggestionRevision);
    document.querySelectorAll('[data-script-control]').forEach(el=>el.disabled=!project?.document.proposal||project.archived||g.busy||g.dirty||(project.jobs??[]).some(j=>['queued','running','retrying'].includes(j.status)));
    $('approve-script-only').disabled=!scriptReviewAllowed(project,{...g,busy:g.busy},$('script-only-ack').checked,$('script-only-reviewer').value)||Boolean(project?.script_review?.current);
  }
  function fillEditor(){const shot=selected();$('shot-editor-form').hidden=!shot;$('shot-editor-empty').hidden=Boolean(shot);$('shot-editor-title').textContent=shot?`Shot ${shot.scene}`:'Chọn một shot';$('shot-version').textContent=getProject()?.shot_timeline?`Timeline v${getProject().shot_timeline.version}`:'—';if(!shot)return;
    for(const [id,key] of [['shot-visual','visual'],['shot-narration','narration'],['shot-on-screen','on_screen_text'],['shot-subtitle','subtitle'],['shot-duration','duration'],['shot-source-start','source_start'],['shot-crop','crop_strategy'],['shot-motion','motion'],['shot-transition','transition']])$(id).value=shot[key]??'';
    $('shot-narration-enabled').checked=shot.narration_enabled;
    $('shot-asset').innerHTML='<option value="">Chọn nguồn…</option>'+assets().map(a=>`<option value="${esc(a.id)}">${a.kind==='video'?'Video':'Ảnh'} · ${esc(a.filename??a.id)}</option>`).join('');$('shot-asset').value=shot.asset_id??'';
    $('shot-restore-revision').value=Math.max(1,(getProject()?.revision??1)-1);showSuggestion(suggestions.get(suggestionKey(getProject(),selectedId)));
  }
  function renderMedia(){const shot=selected(),project=getProject(),final=currentStudioRender(project),ready=preview?.status==='READY'&&preview.video_url;
    $('show-final-preview').hidden=!final;
    $('video').hidden=!(mediaMode==='final'&&final);proxy.hidden=!(mediaMode==='proxy'&&ready);image.hidden=!(mediaMode==='shot'&&shot?.asset_id);
    if($('video').hidden)$('video').pause();if(proxy.hidden)proxy.pause();
    if(!image.hidden)image.src=thumbnail(shot.asset_id);if(!proxy.hidden){const firstAsset=projectShots(project).find(s=>s.asset_id)?.asset_id;if(firstAsset)proxy.poster=thumbnail(firstAsset);else proxy.removeAttribute('poster');if(proxy.getAttribute('src')!==preview.video_url)proxy.src=preview.video_url;}
    $('video-placeholder').hidden=!($('video').hidden&&proxy.hidden&&image.hidden);
    caption.hidden=mediaMode==='final';caption.textContent=mediaMode==='proxy'?'Xem nhanh hình ảnh · chưa có giọng đọc':shot?`Shot ${shot.scene} · ${shot.duration.toFixed(1)} giây · nguồn chưa render`:'Chọn shot hoặc tạo preview';
    $('final-review-panel').hidden=!final||mediaMode!=='final';$('download').hidden=!final||mediaMode!=='final';$('qc-note').hidden=!final||mediaMode!=='final';
    $('preview-state').textContent=previewLabel(preview);
    $('preview-timing-note').textContent=previewTimingLabel(mediaMode==='final'&&final?'final':'proxy');
  }
  function renderCards(){const project=getProject(),shots=projectShots(project);$('shot-count').textContent=`${shots.length} shot`;const card=s=>`<button class="shot-card ${s.asset_id?'':'error'}" data-shot="${esc(s.shot_id)}" draggable="true" aria-pressed="${s.shot_id===selectedId}" aria-label="Chọn shot ${s.scene}, ${s.duration.toFixed(1)} giây"><strong>SHOT ${s.scene}</strong>${s.asset_id?`<img src="${thumbnail(s.asset_id)}" alt="" loading="lazy">`:'<div class="shot-no-source">Chưa có nguồn</div>'}<small>${s.duration.toFixed(1)}s · ${s.narration_enabled?'Có lời đọc':'Không lời đọc'}</small><small>${assets().find(a=>a.id===s.asset_id)?.kind==='video'?'Video':'Ảnh'} · ${s.asset_id?'Đã chọn nguồn':'Cần chọn nguồn'}</small></button>`;
    $('shot-strip').innerHTML=shots.map(card).join('')||'<p class="hint">Tạo và lưu kịch bản để bắt đầu biên tập shot.</p>';
    $('storyboard-grid').innerHTML=shots.map(s=>`<article class="storyboard-card">${s.asset_id?`<img src="${thumbnail(s.asset_id)}" alt="Nguồn shot ${s.scene}" loading="lazy">`:''}<h3>Shot ${s.scene} · ${s.duration.toFixed(1)} giây</h3><p>${esc(s.narration||'Không có lời đọc')}</p><p class="hint">${esc(s.visual)}</p><button class="secondary" data-storyboard-shot="${esc(s.shot_id)}" data-studio-nav>Mở Shot Editor</button></article>`).join('')||'<p class="hint">Storyboard sẽ xuất hiện sau khi có đề xuất nội dung.</p>';
    const snapshot=project?.shot_timeline?.snapshot;
    $('advanced-tracks').innerHTML=(snapshot?.tracks??[]).map(t=>`<div class="advanced-track"><strong>${esc(t.label??t.type)}</strong><div class="track-clips">${(t.clips??[]).map(c=>{const id=c.metadata?.shot_id??shots.find(s=>s.scene===c.metadata?.scene)?.shot_id;return `<button data-track-shot="${esc(id??'')}" data-track-duration="${Math.max(.1,Number(c.duration??1))}" data-studio-nav title="${esc(c.label??c.kind)} · ${Number(c.timeline_start??0).toFixed(1)}s · ${Number(c.duration??0).toFixed(1)}s">${esc(c.label??c.kind)} · ${Number(c.duration??0).toFixed(1)}s</button>`;}).join('')}</div></div>`).join('')||'<p class="hint">Chưa có timeline cho dự án này.</p>';
    document.querySelectorAll('[data-track-duration]').forEach(el=>el.style.flexGrow=el.dataset.trackDuration);
  }
  function progress(){const project=getProject(),doc=project?.document,review=scriptStageReview(project); $('studio-title').textContent=doc?.name??'Tạo video của bạn';$('studio-title').title=$('studio-title').textContent;$('studio-save-state').textContent=getGuards().dirty?'Có chỉnh sửa chưa lưu':project?`Đã lưu · v${project.revision}`:'Chưa có dự án';$('stage-script-state').textContent=review.label;$('stage-assets-state').textContent=assets().length?`${assets().length} nguồn`:'Chưa có nguồn';$('stage-storyboard-state').textContent=projectShots(project).length?`${projectShots(project).length} shot`:'Chưa có shot';$('stage-video-state').textContent=project?.jobs?.some(j=>j.kind==='render'&&j.status==='succeeded'&&j.revision===project.revision)?'Đã dựng':preview?.status==='READY'?'Có preview':'Chưa dựng';$('script-only-review').hidden=!doc?.proposal;$('script-only-state').textContent=review.detail;}
  async function loadView(){const project=getProject();if(!project)return;const key=`${project.id}:${project.revision}`;if(loadingKey===key)return;loadingKey=key;try{const value=await api(`/api/projects/${project.id}/shots`);if(getProject()?.id===project.id&&getProject()?.revision===project.revision){loadedKey=key;onProject(value,false);render(true);await loadPreview();}}catch(error){message(error.message,true);}finally{if(loadingKey===key)loadingKey=null;}}
  function decorateAssets(){
    const project=getProject();if(!project)return;
    const used=new Set((project.document.scene_media??[]).map(b=>b.asset_id));
    document.querySelectorAll('#media-library .media-tile').forEach((tile,i)=>{const asset=assets()[i];if(!asset)return;tile.querySelector('.asset-details')?.remove();const extra=document.createElement('div');extra.className='asset-details';extra.innerHTML=`<small class="${used.has(asset.id)?'asset-used':'asset-unused'}">${used.has(asset.id)?'Đang dùng trong storyboard':'Chưa dùng trong storyboard'}</small><small>${esc(asset.provenance?.source_type??'Nguồn tải lên')} · ${asset.rights_confirmed?'Đã xác nhận quyền':'Kiểm tra quyền nguồn'}</small><label>Nhãn<input class="asset-tags" data-asset-tags="${esc(asset.id)}" data-asset-control value="${esc((asset.tags??project.document.asset_tags?.[asset.id]??[]).join(', '))}" placeholder="Dự án, phối cảnh…"></label><div class="asset-actions"><button type="button" class="secondary" data-asset-action="tag" data-asset-id="${esc(asset.id)}" data-asset-control>Lưu nhãn</button><button type="button" class="secondary" data-asset-action="remove" data-asset-id="${esc(asset.id)}" data-asset-control ${used.has(asset.id)?'disabled':''}>Gỡ khỏi dự án</button></div><small>Gỡ nguồn giữ nguyên tệp gốc. Thay nguồn ở shot trước khi gỡ nguồn đang dùng.</small>`;tile.querySelector('figcaption').append(extra);});
  }
  function render(reset=false){const project=getProject(),shots=projectShots(project);if(project?.id!==shownProjectId){shownProjectId=project?.id??null;mediaMode=project?.approval?'final':'shot';preview=null;showStage(project?.document.proposal?'video':'script');}if(!project){loadedKey=null;selectedId=null;preview=null;clearTimeout(previewTimer);}if(project?.shot_timeline&&!shots.some(s=>s.shot_id===selectedId)){selectedId=shots[0]?.shot_id??null;reset=true;}if(reset){$('script-only-ack').checked=false;if(!shotDirty)fillEditor();}renderCards();decorateAssets();progress();renderMedia();controls();if(project&&!project.shot_timeline)void loadView();}
  async function selectShot(id){if(shotDirty){message('Lưu hoặc bỏ chỉnh sửa shot trước khi chọn shot khác.',true);return;}if(!projectShots(getProject()).some(s=>s.shot_id===id))return;selectedId=id;mediaMode='shot';fillEditor();render(false);[...document.querySelectorAll('[data-shot]')].find(el=>el.dataset.shot===id)?.focus();}
  async function run(fn){if(working)return;working=true;onWorking();controls();try{await fn();}catch(error){message(error.message,true);}finally{working=false;onWorking();controls();}}
  async function mutate(operation,{save=false}={}){const project=getProject(),guards=guard();if(!shotMutationAllowed(project,{...guards,dirty:save?guards.dirty&&!shotDirty:guards.dirty,busy:getGuards().busy}))throw new Error('Lưu chỉnh sửa và chờ tác vụ hoàn tất trước khi cập nhật shot.');const value=await api(`/api/projects/${project.id}/shots`,{revision:project.revision,operation});setDirty(false);loadedKey=`${value.id}:${value.revision}`;onProject(value,true);const changed=value.shot_timeline?.scope?.preview_invalidated!==false;if(changed){preview=preview?{...preview,status:'STALE',video_url:null}:null;mediaMode='shot';}render(true);message(changed?'Đã lưu phiên bản shot mới. Preview và phê duyệt cũ cần cập nhật.':'Shot đã trùng với phiên bản đang lưu.');}
  function formValues(){return {visual:$('shot-visual').value,narration:$('shot-narration').value,on_screen_text:$('shot-on-screen').value,subtitle:$('shot-subtitle').value,asset_id:$('shot-asset').value||null,duration:Number($('shot-duration').value),narration_enabled:$('shot-narration-enabled').checked,crop_strategy:$('shot-crop').value,motion:$('shot-motion').value,source_start:Number($('shot-source-start').value),transition:$('shot-transition').value};}
  async function loadPreview(){const project=getProject();if(!project)return;const value=await api(`/api/projects/${project.id}/preview`);if(getProject()?.id!==project.id)return;preview=boundPreview(getProject(),value);if(preview.status==='READY'&&!$('message').classList.contains('error')&&$('message').textContent==='Đã lưu phiên bản shot mới. Preview và phê duyệt cũ cần cập nhật.')message(getProject().approval?'Preview hình ảnh đã sẵn sàng · chưa có giọng đọc.':'Preview hình ảnh đã sẵn sàng. Nội dung và cách dựng vẫn cần duyệt trước khi tạo giọng đọc và video.');renderMedia();progress();controls();clearTimeout(previewTimer);if(['QUEUED','RUNNING'].includes(preview.status))previewTimer=setTimeout(()=>loadPreview().catch(e=>message(e.message,true)),1200);}
  document.querySelectorAll('[data-stage]').forEach(el=>el.addEventListener('click',()=>{showStage(el.dataset.stage);if(el.hasAttribute('data-open-brand')){brandPanel.open=true;brandPanel.scrollIntoView({block:'center',behavior:'smooth'});}}));
  $('shot-strip').addEventListener('click',event=>{const button=event.target.closest('[data-shot]');if(button)void selectShot(button.dataset.shot);});
  $('storyboard-grid').addEventListener('click',event=>{const button=event.target.closest('[data-storyboard-shot]');if(button){showStage('video');void selectShot(button.dataset.storyboardShot);}});
  $('advanced-tracks').addEventListener('click',event=>{const button=event.target.closest('[data-track-shot]');if(button?.dataset.trackShot)void selectShot(button.dataset.trackShot);});
  $('advanced-toggle').addEventListener('click',()=>{$('advanced-timeline').hidden=!$('advanced-timeline').hidden;$('advanced-toggle').setAttribute('aria-expanded',String(!$('advanced-timeline').hidden));});
  $('shot-editor-form').addEventListener('input',event=>{if(event.target.id!=='shot-restore-revision')setDirty(true);});
  $('shot-asset').addEventListener('change',()=>{$('shot-motion').value='none';$('shot-source-start').value=0;setDirty(true);});
  $('shot-editor-form').addEventListener('submit',event=>{event.preventDefault();void run(async()=>{const shot=selected(),values=changedShotValues(shot,formValues());if(!Object.keys(values).length){setDirty(false);return;}await mutate({type:'update',shot_id:selectedId,values},{save:true});});});
  $('shot-discard').addEventListener('click',()=>{setDirty(false);fillEditor();render(false);});
  for(const [id,type] of [['shot-duplicate','duplicate'],['shot-delete','delete'],['shot-regenerate','regenerate']])$(id).addEventListener('click',()=>void run(()=>mutate({type,shot_id:selectedId})));
  $('shot-revert').addEventListener('click',()=>void run(()=>mutate({type:'revert',shot_id:selectedId,restore_revision:Number($('shot-restore-revision').value)})));
  for(const [id,offset] of [['shot-earlier',-1],['shot-later',1]])$(id).addEventListener('click',()=>void run(()=>mutate({type:'reorder',shot_ids:reorderedShotIds(projectShots(getProject()),selectedId,offset)})));
  $('shot-strip').addEventListener('dragstart',event=>{const card=event.target.closest('[data-shot]');if(!card||!shotMutationAllowed(getProject(),guard())||shotDirty){event.preventDefault();return;}draggedId=card.dataset.shot;event.dataTransfer.setData('text/plain',draggedId);card.classList.add('dragging');});
  $('shot-strip').addEventListener('dragover',event=>{if(draggedId)event.preventDefault();});
  $('shot-strip').addEventListener('dragend',()=>{draggedId=null;document.querySelectorAll('.dragging').forEach(el=>el.classList.remove('dragging'));});
  $('shot-strip').addEventListener('drop',event=>{event.preventDefault();const card=event.target.closest('[data-shot]'),id=draggedId;if(!card||!id||id===card.dataset.shot)return;const shots=projectShots(getProject()),ids=shots.map(s=>s.shot_id);ids.splice(ids.indexOf(id),1);ids.splice(ids.indexOf(card.dataset.shot),0,id);draggedId=null;void run(()=>mutate({type:'reorder',shot_ids:ids}));});
  $('create-preview').addEventListener('click',()=>void run(async()=>{const p=getProject();if(!shotMutationAllowed(p,getGuards()))throw new Error('Lưu chỉnh sửa trước khi tạo preview.');preview=await api(`/api/projects/${p.id}/preview`,{revision:p.revision,action:'generate'});mediaMode='proxy';renderMedia();await loadPreview();}));
  $('cancel-preview').addEventListener('click',()=>void run(async()=>{const p=getProject();preview=await api(`/api/projects/${p.id}/preview`,{revision:p.revision,action:'cancel'});await loadPreview();}));
  $('show-final-preview').addEventListener('click',()=>{mediaMode='final';proxy.pause();renderMedia();});
  $('toolbar-preview').addEventListener('click',()=>{showStage('video');$('create-preview').click();});
  $('render').addEventListener('click',()=>{mediaMode='final';showStage('video');});
  $('shot-ai-suggest').addEventListener('click',()=>void run(async()=>{const p=getProject(),requestedShotId=selectedId;if(!shotMutationAllowed(p,getGuards())||shotDirty)throw new Error('Lưu shot trước khi yêu cầu gợi ý.');const instruction=$('shot-ai-input').value.trim();if(!instruction)throw new Error('Nhập yêu cầu chỉnh sửa cho shot.');const value=await api(`/api/projects/${p.id}/ai-edit`,{revision:p.revision,shot_id:requestedShotId,instruction,request_key:crypto.randomUUID()});suggestions.set(suggestionKey(p,requestedShotId),value);if(getProject()?.id===p.id&&getProject()?.revision===p.revision&&selectedId===requestedShotId)showSuggestion(value);else message('Đề xuất đã lưu cho shot vừa yêu cầu. Chọn lại shot đó để xem.');controls();}));
  $('shot-ai-apply').addEventListener('click',()=>void run(async()=>{if(!safeSuggestion(getProject(),selectedId,suggestion,suggestionRevision))throw new Error('Đề xuất đã cũ hoặc ảnh hưởng ngoài shot đang chọn. Hãy yêu cầu lại.');await mutate(suggestion.operation);}));
  $('media-library').addEventListener('click',event=>{const button=event.target.closest('[data-asset-action]');if(!button)return;void run(async()=>{const p=getProject();if(getGuards().dirty||getGuards().busy||p.archived)throw new Error('Lưu chỉnh sửa trước khi thay đổi thư viện.');const input=[...document.querySelectorAll('[data-asset-tags]')].find(el=>el.dataset.assetTags===button.dataset.assetId);const value=await api(`/api/projects/${p.id}/asset-association`,{revision:p.revision,asset_id:button.dataset.assetId,action:button.dataset.assetAction,tags:(input?.value??'').split(',').map(v=>v.trim()).filter(Boolean)});onProject(value,true);render(true);message('Đã cập nhật nguồn của dự án; tệp gốc được giữ nguyên.');});});
  $('new-project').addEventListener('click',()=>showStage('script'));
  for(const id of ['script-only-ack','script-only-reviewer'])$(id).addEventListener('input',controls);
  $('approve-script-only').addEventListener('click',()=>void run(async()=>{const p=getProject(),reviewer=$('script-only-reviewer').value;if(!scriptReviewAllowed(p,getGuards(),$('script-only-ack').checked,reviewer))throw new Error('Lưu kịch bản, nhập tên người duyệt và xác nhận đã kiểm tra.');const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(p.document.proposal.narration));const script_sha256=[...new Uint8Array(bytes)].map(b=>b.toString(16).padStart(2,'0')).join('');const value=await api(`/api/projects/${p.id}/script-review`,{revision:p.revision,reviewer,acknowledged:true,script_sha256});$('script-only-ack').checked=false;onProject(value,true);render(true);message('Đã duyệt riêng kịch bản đã lưu. Kiểm tra hình ảnh và cách dựng trước khi duyệt sản xuất.');}));
  showStage(stage);render(true);
  return {refresh:render,controls,isDirty:()=>shotDirty,isWorking:()=>working,showStage};
}
