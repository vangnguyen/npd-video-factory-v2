import {getClip,clipStyle,snapTime,pixelsPerSecond} from './studio-utils.mjs';
import {waveformPath} from './waveform.mjs';
import {timelineHistory} from './timeline-history.mjs';
import {sourceBrollRequest,sourceBrollMarkup} from './native-source-broll.mjs';
import {initializeSourceBrollReview} from './native-source-broll-review.mjs';

export const isSourceProject=p=>p?.document?.canonical_timeline?.snapshot?.metadata?.native_auto_edit_schema==='native-auto-edit-timeline-v1';
export const sourceState=p=>isSourceProject(p)?p.document.canonical_timeline:null;
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const num=value=>Number(value).toFixed(2);
export function sourceRequest(project,action,payload={}) {
  const state=sourceState(project);
  if(!state||!Number.isInteger(project.revision)||project.archived)throw new Error('Mở bản dựng nguồn đang hoạt động trước khi sửa.');
  return {revision:project.revision,action,payload:{...payload,expected_version:state.version}};
}
export function sourceVersions(versions) {
  const seen=new Set();
  return [...versions].sort((a,b)=>a.revision-b.revision).flatMap(record=>{
    const state=record.document?.canonical_timeline;
    if(state?.snapshot?.metadata?.native_auto_edit_schema!=='native-auto-edit-timeline-v1'||seen.has(state.version))return [];
    const saved=record.document.source_timeline_mutations?.find(item=>item.version===state.version);
    seen.add(state.version);return [{version:state.version,revision:record.revision,mutation:saved?.mutation??{type:'edit'}}];
  });
}
export function sourceClipAction(project,clipId,type,values={}) {
  const state=sourceState(project),found=getClip(state,clipId);
  if(!found)throw new Error('Clip đã thay đổi. Chọn lại clip.');
  const linked=found.track.kind==='source'&&found.track.type==='video';
  const operation={type,clip_id:clipId,...values};
  return sourceRequest(project,linked?'linked_edit':'edit',linked?{operation}:{operations:[operation]});
}
export function sourceAudioSettings(project,values) {
  return sourceRequest(project,'configure',{audio_processing:{
    ...(sourceState(project)?.snapshot.metadata.source_audio_processing??{}),...values}});
}
export function sourcePreviewSettings(project,mode) {
  if(!['lightweight','final_effects'].includes(mode))throw new Error('Chọn kiểu preview hợp lệ.');
  return sourceRequest(project,'configure',{preview_mode:mode});
}
export function sourceReframeRequest(project,{aspect_ratio,mode,points=[]}) {
  if(!['9:16','16:9','1:1','4:5'].includes(aspect_ratio)||!['center_crop','manual_override'].includes(mode))throw new Error('Chọn định dạng và cách crop hợp lệ.');
  if(mode==='manual_override'&&(!points.length||points.some(p=>![p.time,p.x,p.y,p.zoom].every(Number.isFinite)||p.time<0||p.x<0||p.x>1||p.y<0||p.y>1||p.zoom<1||p.zoom>4)||new Set(points.map(p=>p.time)).size!==points.length))throw new Error('Kiểm tra mốc nguồn, tâm crop và mức zoom; mỗi mốc cần khác nhau.');
  return sourceRequest(project,'reframe',{aspect_ratio,mode,points:mode==='manual_override'?points:[]});
}
const pointMarkup=(point,index,sourceDuration=600)=>`<fieldset class="scene-grid" data-source-crop-point><legend>Mốc ${index+1}</legend>${[['time','Giây trên nguồn',point.time,0,sourceDuration],['x','Tâm ngang (%)',point.x*100,0,100],['y','Tâm dọc (%)',point.y*100,0,100],['zoom','Zoom (%)',point.zoom*100,100,400]].map(([key,label,value,min,max])=>`<label>${label}<input data-crop-point="${key}" type="number" min="${min}" max="${max}" step="any" required value="${esc(value)}"></label>`).join('')}<button type="button" data-source-crop-remove>Xóa mốc</button></fieldset>`;
export function sourceReframeMarkup(project) {
  const snapshot=sourceState(project)?.snapshot;if(!snapshot)return '';
  const saved=snapshot.metadata.source_reframe_plan,plan=saved?.plan;
  const sourceDuration=saved?.source_duration_seconds??project.document.auto_edit_analyses?.find(r=>r.analysis.analysis_id===snapshot.metadata.source_analysis_id)?.analysis.source_media.duration_seconds??600;
  const points=saved?.manual_points?.length?[...saved.manual_points].sort((a,b)=>a.time-b.time):[{time:0,x:.5,y:.5,zoom:1}];
  return `<details><summary>Đường crop theo nguồn</summary><p class="hint">Tracking chưa được cấu hình; độ tin cậy theo dõi chưa có. Crop giữa cần kiểm tra chủ thể. Mốc thủ công dùng giây của video gốc, giữ nguyên âm thanh và phụ đề; preview đầy đủ mới thể hiện đường crop.</p>${plan?`<p>Đã lưu: ${plan.strategy==='manual_override'?'tọa độ thủ công':'crop giữa'} · ${esc(plan.aspect_ratio)} · ${plan.needs_attention?'cần kiểm tra':'vẫn cần xem và duyệt video'}</p>`:''}<form data-source-reframe-form data-source-duration-limit="${esc(sourceDuration)}"><label>Định dạng<select data-source-reframe-ratio>${['9:16','16:9','1:1','4:5'].map(r=>`<option ${r===snapshot.aspect_ratio?'selected':''}>${r}</option>`).join('')}</select></label><label>Cách crop<select data-source-reframe-mode><option value="center_crop" ${plan?.strategy!=='manual_override'?'selected':''}>Crop giữa · chưa có tracking</option><option value="manual_override" ${plan?.strategy==='manual_override'?'selected':''}>Đường crop thủ công</option></select></label><div data-source-crop-points ${plan?.strategy==='manual_override'?'':'hidden'}>${points.map((point,index)=>pointMarkup(point,index,sourceDuration)).join('')}<button type="button" data-source-crop-add>Thêm mốc</button></div><div class="actions"><button type="submit">Lưu đường crop</button><button type="button" data-source-reframe-discard>Bỏ chỉnh sửa crop</button></div></form></details>`;
}
export function sourceAdvancedMarkup(project,zoom=1,selectedId=null) {
  const state=sourceState(project);if(!state)return '';
  const width=Math.max(350,state.snapshot.duration_seconds*pixelsPerSecond(zoom));
  return state.snapshot.tracks.map(track=>`<section class="source-track"><div class="source-track-heading"><strong>${esc(track.label)}</strong>
    <button type="button" data-source-track="${esc(track.track_id)}" data-track-state="locked">${track.locked?'Mở khóa':'Khóa'}</button>
    ${track.type==='audio'?`<button type="button" data-source-track="${esc(track.track_id)}" data-track-state="muted">${track.muted?'Bật âm':'Tắt âm'}</button>`:''}
    <button type="button" data-source-track="${esc(track.track_id)}" data-track-state="disabled">${track.disabled?'Bật track':'Tắt track'}</button></div>
    <div class="source-lane" style="width:${width}px">${track.clips.map(clip=>{
      const style=clipStyle(clip,track.kind,zoom),wave=waveformPath(clip);
      return `<button type="button" class="source-timeline-clip" data-source-clip="${esc(clip.clip_id)}" aria-pressed="${clip.clip_id===selectedId}"
        style="left:${style.left};width:${style.width};background:${style.color};opacity:${style.opacity}"
        title="${esc(clip.label)} · ${num(clip.timeline_start)}–${num(clip.timeline_start+clip.duration)}s">
        <span>${esc(clip.label||clip.kind)}</span>${wave?`<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Biên độ âm thanh đo từ nguồn"><path d="${wave}"/></svg>`:''}</button>`;
    }).join('')}</div></section>`).join('');
}

export function initializeSourceEditor({api,getProject,getGuards,getReviewedVision=()=>null,getSelected,getPreview,getPlayers,onProject,onDirty,onMessage,onWorking}) {
  const $=id=>document.getElementById(id);
  const host=document.createElement('section');host.id='native-source-inspector';host.hidden=true;
  $('shot-editor-form').after(host);
  const review=document.querySelector('#proposal-card .review'),marker=document.createComment('source review original position');review.before(marker);
  const reviewHome=document.createElement('section');reviewHome.id='source-review-home';reviewHome.hidden=true;$('video-review-body').prepend(reviewHome);
  const reviewLabel=review.querySelector('.check'),originalReviewText=reviewLabel.lastChild.textContent;
  const toolbar=document.createElement('div');toolbar.className='source-timeline-toolbar';toolbar.hidden=true;
  toolbar.innerHTML='<button type="button" data-source-history="undo">Hoàn tác</button><button type="button" data-source-history="redo">Làm lại</button><label>Zoom<input data-source-zoom type="range" min="0.5" max="4" step="0.25" value="1"></label><label class="check"><input data-source-snap type="checkbox" checked> Bám mốc 0,25s</label><label>Playhead (s)<input data-source-playhead type="number" min="0" step="0.01" value="0"></label><output data-source-position>0.00s</output>';
  $('advanced-tracks').before(toolbar);
  if(!document.querySelector('link[data-source-editor-style]')){const link=document.createElement('link');link.rel='stylesheet';link.href='/native-source-editor.css';link.dataset.sourceEditorStyle='true';document.head.append(link);}
  let working=false,dirty=false,dirtyForm=null,selectedId=null,zoom=1,playhead=0,versions=[],historyKey=null,catalog=null,shownKey=null;
  const state=()=>sourceState(getProject());
  const selected=()=>getClip(state(),selectedId);
  const locked=()=>selected()?.track.locked;
  const blocked=()=>working||getGuards().canEdit===false||getGuards().busy||getProject()?.archived||(getGuards().dirty&&!dirty)||(getProject()?.jobs??[]).some(j=>['queued','running','retrying'].includes(j.status));
  const reviewRoot=document.createElement('section');
  const brollReview=initializeSourceBrollReview({root:reviewRoot,getReviewedVision,onMessage,getState:()=>({project:getProject(),
    workspace_id:getGuards().workspace_id??'wsp_native_local',canEdit:getGuards().canEdit!==false,dirty:dirty||getGuards().dirty,
    busy:working||getGuards().busy,active:(getProject()?.jobs??[]).some(j=>['queued','running','retrying'].includes(j.status))})});
  function controls(){
    host.querySelectorAll('input,select,button').forEach(el=>el.disabled=blocked());
    if(locked())host.querySelectorAll('[data-source-form] input,[data-source-form] button,[data-source-action],[data-source-placement],[data-source-speed],[data-source-volume],[data-source-crop]').forEach(el=>el.disabled=true);
    const manual=host.querySelector('[data-source-reframe-mode]')?.value==='manual_override';
    host.querySelectorAll('[data-source-crop-point]').forEach(el=>el.disabled=!manual||blocked()||dirtyForm==='trim');
    if(dirtyForm)host.querySelectorAll('[data-source-form],[data-source-reframe-form]').forEach(form=>{
      if((form.hasAttribute('data-source-reframe-form')?'reframe':'trim')!==dirtyForm)form.querySelectorAll('input,select,button').forEach(el=>el.disabled=true);
    });
    const history=timelineHistory(versions,state()?.version??0);
    toolbar.querySelectorAll('[data-source-history]').forEach(el=>el.disabled=blocked()||dirty||!history[el.dataset.sourceHistory].length);
    $('advanced-tracks').querySelectorAll('[data-source-track]').forEach(el=>el.disabled=blocked()||dirty);
    if(!selected())host.querySelectorAll('[data-source-action]').forEach(el=>el.disabled=true);
    const captionButton=host.querySelector('[data-source-config="caption"]');if(captionButton&&!catalog)captionButton.disabled=true;
    host.querySelectorAll('[data-source-broll="apply"]').forEach(el=>{
      const itemId=el.closest('[data-broll-item]').dataset.brollItem;
      const planId=el.closest('[data-broll-plan]').dataset.brollPlan;
      const record=(getProject()?.document.source_broll_plans??[]).filter(r=>r.plan.media_plan_id===planId).at(-1);
      if(record?.plan.items.find(i=>i.media_plan_item_id===itemId)?.status!=='resolved')el.disabled=true;
    });
    brollReview.sync();
  }
  function renderAdvanced(){
    toolbar.hidden=!isSourceProject(getProject());
    if(!toolbar.hidden)$('advanced-tracks').innerHTML=sourceAdvancedMarkup(getProject(),zoom,selectedId);
    controls();
  }
  async function history(){
    const p=getProject(),key=p?`${p.id}:${p.revision}`:null;if(!isSourceProject(p)||historyKey===key)return;
    if(!historyKey?.startsWith(`${p.id}:`))versions=[];
    historyKey=key;
    try{const values=await api(`/api/projects/${p.id}/versions`);if(historyKey!==key||getProject()?.id!==p.id)return;versions=sourceVersions(values);controls();}
    catch(error){if(historyKey===key){historyKey=null;onMessage(error.message,true);}}
  }
  function renderSelected(force=false){
    const p=getProject(),source=isSourceProject(p),key=source?`${p.id}:${p.revision}:${selectedId}`:null;
    host.hidden=!source;reviewHome.hidden=!source;toolbar.hidden=!source;
    if(source){reviewHome.append(review);reviewLabel.lastChild.textContent=' Tôi đã xem preview hiện tại, kiểm tra điểm cắt, âm thanh nguồn, lời nói và quyền sử dụng. Tôi duyệt bản dựng này để render; video cuối vẫn cần xem, nghe và duyệt riêng.';}
    else{marker.after(review);reviewLabel.lastChild.textContent=originalReviewText;shownKey=null;return;}
    if(!force&&(dirty||shownKey===key)){controls();return;}shownKey=key;
    const found=selected(),clip=found?.clip,track=found?.track;
    host.innerHTML=`<p class="hint">Điểm cắt shot nguồn giữ âm thanh và phụ đề đồng bộ. Chỉnh từng track trong Advanced Timeline sẽ giữ lựa chọn riêng của track.</p>
      ${clip?`<h3>${esc(clip.label)}</h3><p class="hint">${esc(track.label)} · ${num(clip.duration)}s${track.locked?' · đã khóa':''}</p>
      <form data-source-form>${clip.kind==='image'?`<label>Thời lượng ảnh (s)<input data-source-duration type="number" min="0.05" step="any" value="${clip.duration}"></label>`:`<div class="scene-grid"><label>Nguồn từ (s)<input data-source-start type="number" min="0" step="any" value="${clip.source_start}"></label><label>Nguồn đến (s)<input data-source-end type="number" min="0.05" step="any" value="${clip.source_end??clip.duration}"></label></div>`}
      <div class="actions"><button type="submit">Lưu điểm cắt</button><button type="button" data-source-discard>Bỏ chỉnh sửa</button></div></form>
      <label>${track.kind==='source'?'Mốc sắp xếp shot (s)':'Vị trí timeline (s)'}<input data-source-placement type="number" min="0" step="any" value="${clip.timeline_start}"></label><button type="button" data-source-action="placement">Lưu vị trí</button>${track.kind==='source'?'<p class="hint">Di chuyển shot sẽ sắp xếp lại và nối liền các shot nguồn, cùng âm thanh và phụ đề. Vị trí của các track khác được giữ nguyên; kiểm tra lại B-roll.</p>':''}
      ${['source','original_audio'].includes(track.kind)?`<label>Tốc độ phát<select data-source-speed>${[.5,.75,1,1.25,1.5,2].map(rate=>`<option value="${rate}" ${rate===clip.speed?'selected':''}>${rate}×</option>`).join('')}</select></label><button type="button" data-source-action="speed">Lưu tốc độ</button>`:''}
      ${track.type==='audio'?`<label>Âm lượng<input data-source-volume type="number" min="0" max="2" step="0.05" value="${clip.volume}"></label><button type="button" data-source-action="gain">Lưu âm lượng</button>`:''}
      ${track.type==='video'?`<details><summary>Crop thủ công (%)</summary><div class="scene-grid">${['x','y','width','height'].map(key=>`<label>${{x:'Trái',y:'Trên',width:'Rộng',height:'Cao'}[key]}<input data-source-crop="${key}" type="number" min="${['width','height'].includes(key)?1:0}" max="100" value="${clip.crop[key]*100}" step="any"></label>`).join('')}</div><button type="button" data-source-action="crop">Lưu crop</button></details>`:''}
      <div class="actions"><button type="button" data-source-action="split">Tách tại playhead</button><button type="button" data-source-action="duplicate">Nhân đôi</button><button type="button" data-source-action="disable">${clip.disabled?'Bật clip':'Tắt clip'}</button><button type="button" data-source-action="delete">Xóa clip</button></div>
      ${track.kind==='source'?'<div class="actions"><button type="button" data-source-action="earlier">← Trước</button><button type="button" data-source-action="later">Sau →</button></div>':''}`:'<p>Chọn shot hoặc clip trong Advanced Timeline.</p>'}
      <details><summary>Xử lý âm thanh nguồn & nhạc</summary>${[['normalize_original_audio','Cân mức âm thanh nguồn'],['normalize_music','Cân mức nhạc trước âm lượng clip'],['duck_music','Hạ nhạc theo năng lượng âm thanh nguồn']].map(([key,label])=>`<label class="check"><input type="checkbox" data-source-audio="${key}" ${state().snapshot.metadata.source_audio_processing?.[key]?'checked':''}> ${label}</label>`).join('')}<div class="scene-grid"><label>Mức nguồn (LUFS)<input type="number" data-source-audio="original_target_lufs" min="-24" max="-12" value="${state().snapshot.metadata.source_audio_processing?.original_target_lufs??-16}"></label><label>Mức nhạc (LUFS)<input type="number" data-source-audio="music_target_lufs" min="-35" max="-16" value="${state().snapshot.metadata.source_audio_processing?.music_target_lufs??-24}"></label></div><button type="button" data-source-config="audio">Lưu xử lý âm thanh</button><p class="hint">Âm lượng clip vẫn được giữ sau cân mức. Ducking theo tín hiệu nguồn, chưa nhận diện riêng giọng nói. Tạo preview mới và nghe lại sau khi đổi.</p></details>
      <details><summary>Preview</summary><label>Kiểu preview<select data-source-preview-mode><option value="lightweight" ${state().snapshot.metadata.source_preview_mode!=='final_effects'?'selected':''}>Nhẹ · âm thanh và điểm cắt</option><option value="final_effects" ${state().snapshot.metadata.source_preview_mode==='final_effects'?'selected':''}>Đầy đủ · phụ đề, crop và hiệu ứng</option></select></label><button type="button" data-source-config="preview">Lưu kiểu preview</button><p class="hint">Preview đầy đủ dùng hiệu ứng và âm thanh của renderer cuối, ở độ phân giải thấp để xem nhanh hơn. Vẫn cần xem, nghe và duyệt video cuối sau khi render. Tạo preview mới sau khi lưu.</p></details>
      <details><summary>Khung hình & phụ đề</summary><label>Định dạng<select data-source-format>${['9:16','16:9','1:1','4:5'].map(r=>`<option ${r===state().snapshot.aspect_ratio?'selected':''}>${r}</option>`).join('')}</select></label><button type="button" data-source-config="format">Lưu định dạng</button>
      <label>Mẫu phụ đề<select data-source-caption>${(catalog?.templates??[]).map(t=>`<option value="${esc(t.template_ref)}" ${t.template_ref===state().snapshot.metadata.subtitle_style?.template_ref?'selected':''}>${esc(t.name??t.label??t.template_ref)}${t.requires_word_timestamps?' · cần thời gian từng từ':''}</option>`).join('')}</select></label><label>Từ khóa nổi bật (phân cách bằng dấu phẩy)<input data-source-keywords value="${esc((state().snapshot.metadata.subtitle_style?.keywords??[]).join(', '))}" maxlength="1000"></label><button type="button" data-source-config="caption" ${catalog?'':'disabled'}>Lưu mẫu phụ đề</button><p class="hint">Sửa lời nói tại Assets. Đoạn đã sửa cần dùng phụ đề theo câu khi không còn căn chỉnh từng từ. Bản dựng nguồn hiện dùng âm thanh gốc; nhạc nền cần được thêm vào timeline riêng.</p></details>`;
    host.insertAdjacentHTML('beforeend',sourceBrollMarkup(p,{workspaceId:getGuards().workspace_id??'wsp_native_local'}));
    host.querySelector('[data-broll-review-host]').append(reviewRoot);
    host.insertAdjacentHTML('beforeend',sourceReframeMarkup(p));
    void history();renderAdvanced();controls();
  }
  async function run(fn,{allowDirty=false}={}){
    if(blocked()||(!allowDirty&&dirty)){onMessage('Lưu hoặc bỏ chỉnh sửa trước khi thao tác.',true);return;}
    working=true;onWorking();controls();
    try{await fn();}catch(error){onMessage(error.message,true);}finally{working=false;onWorking();controls();}
  }
  async function send(body){
    const p=getProject();const value=await api(`/api/projects/${p.id}/auto-edit/timeline`,body);
    dirty=false;dirtyForm=null;onDirty(false);shownKey=null;historyKey=null;onProject(value,true);
    onMessage('Đã lưu bản dựng mới. Preview và phê duyệt cũ cần cập nhật.');renderSelected(true);
  }
  host.addEventListener('input',event=>{const form=event.target.closest('[data-source-form],[data-source-reframe-form]');if(form){dirty=true;dirtyForm=form.hasAttribute('data-source-reframe-form')?'reframe':'trim';onDirty(true);controls();}});
  host.addEventListener('change',event=>{if(event.target.matches('[data-source-reframe-mode]'))host.querySelector('[data-source-crop-points]').hidden=event.target.value!=='manual_override';});
  host.addEventListener('submit',event=>{
    if(!event.target.matches('[data-source-reframe-form]'))return;event.preventDefault();
    if(dirtyForm==='trim'){onMessage('Lưu hoặc bỏ chỉnh sửa điểm cắt trước khi crop.',true);return;}
    void run(async()=>{
      const points=[...host.querySelectorAll('[data-source-crop-point]')].map(row=>Object.fromEntries([...row.querySelectorAll('[data-crop-point]')].map(el=>[el.dataset.cropPoint,Number(el.value)/(el.dataset.cropPoint==='time'?1:100)])));
      await send(sourceReframeRequest(getProject(),{aspect_ratio:host.querySelector('[data-source-reframe-ratio]').value,mode:host.querySelector('[data-source-reframe-mode]').value,points}));
    },{allowDirty:true});
  });
  host.addEventListener('click',event=>{
    const add=event.target.closest('[data-source-crop-add]'),remove=event.target.closest('[data-source-crop-remove]'),discard=event.target.closest('[data-source-reframe-discard]');
    if(!add&&!remove&&!discard)return;
    if(blocked()||dirtyForm==='trim'){onMessage('Lưu hoặc bỏ chỉnh sửa điểm cắt trước khi crop.',true);return;}
    if(discard){dirty=false;dirtyForm=null;onDirty(false);renderSelected(true);return;}
    if(add){const rows=[...host.querySelectorAll('[data-source-crop-point]')],count=rows.length;if(count>=200)return;const latest=Math.max(0,...rows.map(row=>Number(row.querySelector('[data-crop-point="time"]').value)));add.insertAdjacentHTML('beforebegin',pointMarkup({time:Math.min(Number(add.closest('[data-source-reframe-form]').dataset.sourceDurationLimit),latest+.25),x:.5,y:.5,zoom:1},count,Number(add.closest('[data-source-reframe-form]').dataset.sourceDurationLimit)));}
    else remove.closest('[data-source-crop-point]').remove();
    dirty=true;dirtyForm='reframe';onDirty(true);controls();
  });
  host.addEventListener('submit',event=>{if(!event.target.matches('[data-source-form]'))return;event.preventDefault();if(dirtyForm==='reframe'){onMessage('Lưu hoặc bỏ chỉnh sửa crop trước khi sửa điểm cắt.',true);return;}void run(async()=>{
    const p=getProject(),clip=selected().clip;
    await send(sourceClipAction(p,clip.clip_id,'trim',clip.kind==='image'?{duration:Number(host.querySelector('[data-source-duration]').value)}:{source_start:Number(host.querySelector('[data-source-start]').value),source_end:Number(host.querySelector('[data-source-end]').value)}));
  },{allowDirty:true});});
  host.addEventListener('click',event=>{
    const broll=event.target.closest('[data-source-broll]');
    if(broll){let body;const p=getProject(),item=broll.closest('[data-broll-item]'),workspaceId=getGuards().workspace_id??'wsp_native_local';
      try{body=sourceBrollRequest(p,broll.dataset.sourceBroll,{
        planId:item?.dataset.brollPlan,itemId:item?.dataset.brollItem,
        assetId:item?.querySelector('[data-broll-asset]').value,replace:item?.querySelector('[data-broll-replace]').checked,workspaceId,
        reviewedVision:broll.dataset.sourceBroll==='create'?brollReview.references():[]});
      }catch(error){onMessage(error.message,true);return;}
      void run(async()=>{
      const value=await api(`/api/projects/${p.id}/auto-edit/broll`,body);
      if(getProject()?.id!==p.id||getProject()?.revision!==p.revision||getGuards().canEdit===false||getGuards().dirty
        ||(getGuards().workspace_id??'wsp_native_local')!==workspaceId)return;
      dirty=false;dirtyForm=null;onDirty(false);shownKey=null;historyKey=null;onProject(value,true);
      onMessage(body.action==='apply'?'Đã đặt B-roll vào bản dựng mới. Tạo preview và kiểm tra crop, âm thanh, điểm cắt.':'Đã lưu kế hoạch/lựa chọn. Timeline chỉ đổi sau khi đặt B-roll.');renderSelected(true);
    });return;}
    const discard=event.target.closest('[data-source-discard]');if(discard){dirty=false;dirtyForm=null;onDirty(false);renderSelected(true);return;}
    const action=event.target.closest('[data-source-action]'),config=event.target.closest('[data-source-config]');
    if(!action&&!config)return;
    void run(async()=>{
      const p=getProject(),found=selected();
      if(config){
        const kind=config.dataset.sourceConfig;
        const body=kind==='preview'?sourcePreviewSettings(p,host.querySelector('[data-source-preview-mode]').value):kind==='audio'?sourceAudioSettings(p,Object.fromEntries([...host.querySelectorAll('[data-source-audio]')].map(el=>[el.dataset.sourceAudio,el.type==='checkbox'?el.checked:Number(el.value)]))):sourceRequest(p,'configure',kind==='format'?{aspect_ratio:host.querySelector('[data-source-format]').value}:{subtitle_template_ref:host.querySelector('[data-source-caption]').value,keywords:host.querySelector('[data-source-keywords]').value.split(',').map(v=>v.trim()).filter(Boolean)});
        await send(body);return;
      }
      let type=action.dataset.sourceAction,values={};
      if(type==='earlier'||type==='later'){values.target_index=Math.max(0,Math.min(found.track.clips.length-1,found.index+(type==='earlier'?-1:1)));type='reorder';}
      if(type==='split')values.at_seconds=snapTime(playhead,toolbar.querySelector('[data-source-snap]').checked);
      if(type==='disable')values.disabled=!found.clip.disabled;
      if(type==='placement'){type='move';values.timeline_start=snapTime(host.querySelector('[data-source-placement]').value,toolbar.querySelector('[data-source-snap]').checked);}
      if(type==='speed'){type='set_clip_properties';values.speed=Number(host.querySelector('[data-source-speed]').value);}
      if(type==='gain'){type='set_clip_properties';values.volume=Number(host.querySelector('[data-source-volume]').value);}
      if(type==='crop'){type='set_clip_properties';values.crop=Object.fromEntries([...host.querySelectorAll('[data-source-crop]')].map(el=>[el.dataset.sourceCrop,Number(el.value)/100]));}
      await send(sourceClipAction(p,found.clip.clip_id,type,values));
    });
  });
  toolbar.addEventListener('input',event=>{
    if(event.target.matches('[data-source-zoom]')){zoom=Number(event.target.value);renderAdvanced();}
    if(event.target.matches('[data-source-playhead]')){
      playhead=Math.min(state()?.snapshot.duration_seconds??0,snapTime(event.target.value,toolbar.querySelector('[data-source-snap]').checked));
      toolbar.querySelector('[data-source-position]').value=`${num(playhead)}s`;
      const player=getPlayers().find(el=>!el.hidden&&Number.isFinite(el.duration));if(player)player.currentTime=Math.min(playhead,player.duration);
    }
  });
  toolbar.addEventListener('click',event=>{const button=event.target.closest('[data-source-history]');if(!button)return;void run(async()=>{
    const target=timelineHistory(versions,state().version)[button.dataset.sourceHistory].at(-1),record=versions.find(v=>v.version===target);
    if(record)await send(sourceRequest(getProject(),'restore',{restore_revision:record.revision}));
  });});
  $('advanced-tracks').addEventListener('click',event=>{
    const clip=event.target.closest('[data-source-clip]'),track=event.target.closest('[data-source-track]');
    if(clip){if(dirty){onMessage('Lưu hoặc bỏ chỉnh sửa clip trước khi chọn clip khác.',true);return;}selectedId=clip.dataset.sourceClip;renderSelected(true);}
    if(track)void run(()=>{const saved=state().snapshot.tracks.find(t=>t.track_id===track.dataset.sourceTrack),key=track.dataset.trackState;
      return send(sourceRequest(getProject(),'edit',{operations:[{type:'set_track_state',track_id:saved.track_id,[key]:!saved[key]}]}));});
  });
  for(const player of getPlayers())player.addEventListener('timeupdate',()=>{if(!isSourceProject(getProject())||player.hidden)return;playhead=player.currentTime;toolbar.querySelector('[data-source-position]').value=`${num(playhead)}s`;});
  void api('/api/auto-edit/subtitle-templates').then(value=>{catalog=value;shownKey=null;if(isSourceProject(getProject())&&!dirty)renderSelected(true);}).catch(error=>onMessage(error.message,true));
  return {selectShot(id){selectedId=id;renderSelected();},renderAdvanced,controls,isWorking:()=>working,
    readyForApproval:()=>isSourceProject(getProject())&&getPreview()?.status==='READY'&&getPreview()?.timeline_sha256===state().sha256,
    render:()=>renderSelected()};
}
