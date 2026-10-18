// Local export and manual posting materials. There is no platform transport here.
export const EXPORT_PROFILES = [
  ['vertical-short','Vertical Short · 1080×1920 · 9:16',1080,1920],
  ['landscape','Landscape Full HD · 1920×1080 · 16:9',1920,1080],
  ['square','Square · 1080×1080 · 1:1',1080,1080],
  ['portrait-feed','Portrait Feed · 1080×1350 · 4:5',1080,1350]
];
export function profileForVideo(video) {
  const raw=video?.result?.qc, qc=raw?.full_quality?.full_production_qc??raw;
  return EXPORT_PROFILES.find(p=>p[2]===qc?.width&&p[3]===qc?.height)?.[0]??null;
}
export function manualCaption(copy={}) {
  return [copy.caption,copy.cta,copy.hashtags].filter(x=>typeof x==='string'&&x.trim()).join('\n\n');
}
export function compareExports(a,b) {
  const fields=['project_revision','timeline_version','render_profile','video_sha256','duration_seconds','width','height'];
  return fields.filter(k=>a.binding?.[k]!==b.binding?.[k]).map(field=>({field,before:a.binding?.[field]??null,after:b.binding?.[field]??null}));
}
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const platforms=[['master','Master Copy'],['tiktok','TikTok'],['facebook-reels','Facebook Reels'],['instagram-reels','Instagram Reels'],['youtube-shorts','YouTube Shorts']];
const textFields=['title','caption','description','hashtags','cta'];
const errors={EXPORT_APPROVED_VERSION_CHANGED:'Phiên bản đã đổi. Xem preview và duyệt lại trước khi xuất.',
  HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED:'Xem và nghe video rồi duyệt bản cuối trước khi tạo gói.',
  EXPORT_MEASURED_QC_REQUIRED:'Bản dựng này cần chạy đầy đủ QC. Tạo bản render mới trước khi xuất.',
  RENDER_PROFILE_CANVAS_MISMATCH:'Định dạng chọn khác video đã duyệt. Đổi khung hình trong dự án, tạo preview và duyệt bản render mới.',
  EXPORT_DISK_SPACE_REQUIRED:'Ổ đĩa thiếu chỗ trống. Giải phóng dung lượng rồi thử lại cùng yêu cầu.',
  EXPORT_WRITE_FAILED:'Không ghi được thư mục đầu ra. Kiểm tra ổ đĩa và quyền ghi rồi thử lại.',
  EXPORT_FILE_CHANGED:'File xuất đã bị thay đổi. Giữ nguyên bản cũ và tạo phiên bản xuất mới.',
  EXPORT_CAPTION_VERSION_CHANGED:'Nội dung caption đã đổi. Làm mới lịch sử rồi lưu phiên bản mới.',
  EXPORT_QC_FAILED:'Video chưa đạt QC đầy đủ. Xem chi tiết kiểm tra và sửa bản dựng trước khi xuất.',
  EXPORT_OUTPUT_UNAVAILABLE:'Không tìm thấy thư mục hoặc tệp đầu ra. Kiểm tra ổ đĩa, khôi phục bản sao lưu hoặc tạo bản xuất mới.',
  EXPORT_COVER_IMAGE_OR_MIME_INVALID:'Ảnh bìa không hợp lệ. Chọn ảnh JPG, PNG hoặc WebP đúng định dạng.',
  EXPORT_COVER_SOURCE_CHANGED:'Ảnh bìa nguồn đã thay đổi. Chọn hoặc tải lại ảnh trước khi xuất.'};

export function initializeManualDelivery({api,getState,getVideo,onMessage=()=>{},onWorking=()=>{},openFolder=false,
  document:doc=globalThis.document,storage=globalThis.sessionStorage,clipboard=globalThis.navigator?.clipboard,newKey=()=>globalThis.crypto.randomUUID(),onOpen=()=>{},uploadCoverFile=null}) {
  const root=doc.getElementById('native-delivery-center');if(!root)return null;
  root.hidden=false;
  root.innerHTML=`<p class="eyebrow">EXPORT & DELIVERY</p><h2>Xuất video</h2><p>MP4, ảnh bìa và nội dung để bạn đăng thủ công.</p>
    <p id="delivery-state" role="status" aria-live="polite"></p>
    <fieldset id="delivery-settings"><legend>Cài đặt xuất</legend><label>Định dạng<select id="delivery-profile">${EXPORT_PROFILES.map(p=>`<option value="${p[0]}">${p[1]}</option>`).join('')}</select></label>
    <label>Tên file MP4<input id="delivery-filename" value="final-video.mp4" maxlength="100"></label>
    <p id="delivery-bound-format" class="hint"></p><p class="hint">Gói giữ nguyên hình, âm thanh và phụ đề trong bản đã duyệt. Đổi định dạng hoặc cách dựng cần tạo preview, render và duyệt lại.</p>
    <label class="check"><input id="delivery-srt" type="checkbox" checked> Kèm SRT riêng khi video có phụ đề</label>
    <label class="check"><input id="delivery-cover" type="checkbox" checked> Tạo ảnh bìa JPG từ video</label>
    <label>Chọn khung bìa · giây<input id="delivery-cover-time" type="number" min="0" step="0.1" value="0"></label>
    <details><summary>Ảnh bìa · nguồn, crop và chữ</summary><label>Nguồn ảnh bìa<select id="delivery-cover-source"><option value="frame">Khung từ video đã duyệt</option></select></label>
    <label>Ảnh tải lên<input id="delivery-cover-file" type="file" accept="image/png,image/jpeg,image/webp"></label><button id="delivery-upload-cover" type="button" ${uploadCoverFile?'':'hidden'}>Tải ảnh bìa · tối đa 8 MB</button>
    <img id="delivery-cover-preview" alt="Nguồn ảnh bìa đã chọn" hidden>
    <label>File ảnh bìa<select id="delivery-cover-format"><option value="jpg">JPG</option><option value="png">PNG</option></select></label>
    <label>Tâm crop ngang · %<input id="delivery-cover-x" type="number" min="0" max="100" value="50"></label><label>Tâm crop dọc · %<input id="delivery-cover-y" type="number" min="0" max="100" value="50"></label>
    <label>Phóng to<input id="delivery-cover-zoom" type="number" min="1" max="4" step="0.1" value="1"></label><label>Chữ trên bìa<input id="delivery-cover-title" maxlength="160"></label>
    <label class="check"><input id="delivery-cover-logo" type="checkbox" disabled> Dùng logo thương hiệu đã cấu hình</label><p class="hint">Crop không kéo giãn ảnh. Kiểm tra bìa đã xuất trước khi đăng; quyền dùng ảnh bìa cần được duyệt riêng.</p></details></fieldset>
    <details open><summary>Caption & nội dung đăng</summary><label>Phiên bản nội dung<select id="delivery-copy-platform">${platforms.map(p=>`<option value="${p[0]}">${p[1]}</option>`).join('')}</select></label>
    ${[['title','Tiêu đề',300],['caption','Caption',10000],['description','Mô tả',10000],['hashtags','Hashtag',2000],['cta','CTA',1000]].map(([id,label,max])=>`<label>${label}<textarea id="delivery-copy-${id}" maxlength="${max}" rows="${id==='caption'?4:2}"></textarea></label>`).join('')}
    <div class="actions"><button id="delivery-save-copy" type="button">Lưu nội dung</button><button id="delivery-copy-caption-button" type="button" data-vf-permission="read">Copy caption</button><button id="delivery-download-copy" type="button" data-vf-permission="read">Tải nội dung TXT</button><button id="delivery-regenerate-copy" type="button">Tạo lại từ Master / kịch bản</button></div><label>Lịch sử nội dung<select id="delivery-copy-history" data-vf-permission="read"><option value="">Chọn bản đã lưu…</option></select></label><p id="delivery-copy-version" class="hint"></p></details>
    <div class="actions"><button id="delivery-create" type="button" class="primary">Tạo gói bàn giao</button><button id="delivery-retry" type="button" hidden>Thử lại cùng yêu cầu</button><button id="delivery-reset" type="button" hidden>Bỏ lần thử đang giữ</button><button id="delivery-refresh" type="button" data-vf-permission="read">Làm mới lịch sử</button></div>
    <div id="delivery-result" aria-live="polite"></div><details><summary>Kiểm tra trước khi đăng thủ công</summary><div id="delivery-checklist"></div><p class="hint">Danh sách lưu trong phiên làm việc này. Bạn tự chọn tài khoản và quyền riêng tư khi đăng.</p></details>
    <h3>Lịch sử xuất</h3><div id="delivery-history"></div>`;
  const $=id=>doc.getElementById(id),key=()=>`vf-manual-delivery-v1:${getState().workspace_id??'wsp_native_local'}:${getState().project?.id}`;
  let loaded=null,loadedProject=null,working=false,epoch=0,version=0,variants={},selected='master',copyDirty=false,copyReady=false,history=[],copyHistory=[];
  const context=()=>`${getState().workspace_id}:${getState().project?.id}:${getState().project?.revision}`;
  const current=c=>context()===c;
  const blocked=()=>working||getState().busy||getState().dirty||getState().active||!getState().project||getState().project.archived;
  const writeable=()=>!blocked()&&getState().canEdit!==false;
  const copy=()=>Object.fromEntries(textFields.map(k=>[k,$('delivery-copy-'+k).value]));
  const holdCopy=()=>{variants[selected]=copy();};
  const fillCopy=()=>{for(const k of textFields)$('delivery-copy-'+k).value=variants[selected]?.[k]??'';};
  function controls(){
    const video=getVideo(),approved=video?.final_review?.decision==='approve';
    $('delivery-create').disabled=!writeable()||!approved||copyDirty||!copyReady;
    $('delivery-settings').disabled=!writeable();$('delivery-save-copy').disabled=!writeable()||!copyReady;
    let pending=null;try{pending=storage?.getItem(key());}catch{}
    for(const id of ['delivery-retry','delivery-reset']){$(id).hidden=!pending;$(id).disabled=!writeable();}
    $('delivery-refresh').disabled=working||getState().busy||!getState().project;
    $('delivery-state').textContent=working?'Đang kiểm tra và tạo gói trên máy…':!video?'Tạo preview và render video trước khi xuất.':approved?'Video đã duyệt. Có thể tạo gói sau khi lưu nội dung đăng.':'Xem và nghe video ở trên rồi duyệt đúng bản cuối.';
    $('delivery-copy-version').textContent=`Nội dung v${version}${copyDirty?' · Có chỉnh sửa chưa lưu':''}`;
    const raw=video?.result?.qc,qc=raw?.full_quality?.full_production_qc??raw;
    $('delivery-bound-format').textContent=qc?`${qc.width??'—'}×${qc.height??'—'} · ${qc.fps??'—'} FPS · H.264 / AAC · QC ${qc.status==='passed'?'đạt':'cần kiểm tra'}`:'';
  }
  async function action(fn){if(blocked())return;working=true;onWorking(true);controls();try{await fn();}catch(e){const code=String(e.message).split(' (HTTP')[0];onMessage(errors[code]??e.message,true);}finally{working=false;onWorking(false);controls();}}
  function download(text,name){const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));const a=doc.createElement('a');a.href=url;a.download=name;a.click();URL.revokeObjectURL(url);}
  function links(value){const base=`/api/projects/${value.project_id}/exports/${value.export_id}/files/`;
    const names=value.files??[];return names.filter(n=>n===value.filename||['cover.jpg','cover.png','subtitle.srt'].includes(n)).map(n=>`<a class="download" download href="${base+encodeURIComponent(n)}">${n===value.filename?'Tải video MP4':n.startsWith('cover.')?'Tải ảnh bìa':'Tải phụ đề SRT'}</a>`).join('')+
      `<a class="download" download href="${base}delivery-package.zip">Tải gói ZIP</a>`;
  }
  function result(value){const m=value.manifest;const out=$('delivery-result');out.innerHTML=`<h3>Gói bàn giao sẵn sàng</h3><p>${escape(m.width)}×${escape(m.height)} · ${escape(m.duration_seconds)} giây · QC đạt</p>${links(value)}<p class="hint">${escape(value.output_location)}</p><details><summary>Chi tiết QC & manifest</summary><p>QC: ${escape(m.qc_result)} · ${escape(m.video_codec)} / ${escape(m.audio_codec)} · ${escape(m.fps)} FPS</p><p>Mã xác thực video: <code>${escape(m.video_sha256)}</code></p><a download href="/api/projects/${value.project_id}/exports/${value.export_id}/files/qc-report.json">Tải báo cáo QC</a> · <a download href="/api/projects/${value.project_id}/exports/${value.export_id}/files/delivery-manifest.json">Tải manifest</a></details>`;
    if(value.current_for_project===false){const note=doc.createElement('p');note.textContent='Đây là bản xuất của phiên bản cũ, đã duyệt tại thời điểm xuất.';out.append(note);}
    if(openFolder){const b=doc.createElement('button');b.textContent='Mở thư mục đầu ra';b.type='button';b.addEventListener('click',()=>action(()=>api(`/api/projects/${value.project_id}/exports/${value.export_id}/open-folder`,{})));out.append(b);}
  }
  function showHistory(){const area=$('delivery-history');area.replaceChildren();
    for(const item of history){const row=doc.createElement('section'),b=item.binding;row.innerHTML=`<strong>${escape(b.project_title)}</strong><p>${escape(item.profile)} · ${escape(b.width)}×${escape(b.height)} · ${escape(b.duration_seconds)} giây · ${escape(new Date(item.created_at).toLocaleString('vi-VN'))}</p><p>${item.status==='ready'?'QC đạt · Đã duyệt khi xuất':item.status==='failed'?'Chưa tạo được gói':'Đang chờ đối chiếu'}${item.current_for_project?'':' · Phiên bản cũ'}</p>`;
      if(item.status==='ready'&&item.cover_filename){const image=doc.createElement('img');image.src=`/api/projects/${item.project_id}/exports/${item.export_id}/files/${item.cover_filename}`;image.alt='Bìa bản xuất';image.loading='lazy';row.append(image);}
      const open=doc.createElement('button');open.type='button';open.textContent='Mở bản xuất';open.dataset.vfPermission='read';open.disabled=item.status!=='ready';open.addEventListener('click',()=>action(async()=>{if(item.project_id!==getState().project?.id)return;const c=context(),value=await api(`/api/projects/${item.project_id}/exports/${item.export_id}`);if(current(c))result(value);}));row.append(open);
      if(['preparing','failed'].includes(item.status)){
        const resume=doc.createElement('button');resume.type='button';resume.textContent='Đối chiếu / tiếp tục lần xuất';resume.disabled=getState().canEdit===false;resume.addEventListener('click',()=>action(async()=>{if(getState().canEdit===false||item.project_id!==getState().project?.id)return;const path=`/api/projects/${item.project_id}/exports/${item.export_id}/resume`;retain({schema_version:'manual-delivery-pending.v2',path,body:{}});await send({},path);}));row.append(resume);
        const abandon=doc.createElement('button');abandon.type='button';abandon.textContent='Ngừng lần xuất này · giữ file';abandon.disabled=getState().canEdit===false;abandon.addEventListener('click',()=>action(async()=>{if(getState().canEdit===false||item.project_id!==getState().project?.id)return;const c=context();await api(`/api/projects/${item.project_id}/exports/${item.export_id}/abandon`,{});if(current(c)){try{const held=JSON.parse(storage?.getItem(key())??'null');if((held?.body?.request_key??held?.request_key)===item.request_key||held?.path===`/api/projects/${item.project_id}/exports/${item.export_id}/resume`)storage.removeItem(key());}catch{}await refresh();onMessage('Đã ngừng lần xuất. Dự án và các file vẫn được giữ.');}}));row.append(abandon);
      }
      if(item.status==='ready'){const recreate=doc.createElement('button');recreate.type='button';recreate.textContent='Tạo lại gói thành bản mới';recreate.disabled=getState().canEdit===false;recreate.addEventListener('click',()=>action(async()=>{if(getState().canEdit===false||item.project_id!==getState().project?.id)return;const path=`/api/projects/${item.project_id}/exports/${item.export_id}/recreate-package`,body={expected_manifest_sha256:item.manifest_sha256,request_key:newKey()};retain({schema_version:'manual-delivery-pending.v2',path,body});await send(body,path);}));row.append(recreate);}
      const previous=history[history.indexOf(item)+1];if(previous){const compare=doc.createElement('details'),summary=doc.createElement('summary');summary.textContent='So với bản trước';compare.append(summary);const changes=compareExports(previous,item);for(const change of changes){const line=doc.createElement('p');const label={project_revision:'Phiên bản dự án',timeline_version:'Phiên bản timeline',render_profile:'Định dạng',video_sha256:'Mã xác thực',duration_seconds:'Thời lượng',width:'Chiều rộng',height:'Chiều cao'}[change.field];line.textContent=`${label}: ${change.before??'—'} → ${change.after??'—'}`;compare.append(line);}if(!changes.length)compare.append(doc.createTextNode('Cùng phiên bản video; gói hoặc nội dung đăng có thể khác.'));row.append(compare);}area.append(row);}
    if(!history.length)area.textContent='Chưa có bản xuất. Các bản mới sẽ được lưu riêng.';
  }
  async function refresh(){const c=context(),n=++epoch,p=getState().project;if(!p)return;
    const [copies,page,covers]=await Promise.all([api(`/api/projects/${p.id}/delivery-copy`),api(`/api/projects/${p.id}/exports`),api(`/api/projects/${p.id}/delivery-covers`)]);
    if(!current(c)||n!==epoch)return;
    copyReady=true;
    if(copies.items.length){version=copies.items[0].version;if(!copyDirty){variants=structuredClone(copies.items[0].variants);fillCopy();}}
    else if(!version)copyDirty=true;
    copyHistory=copies.items;$('delivery-copy-history').innerHTML='<option value="">Chọn bản đã lưu…</option>'+copyHistory.map(v=>`<option value="${v.version}">v${v.version} · ${escape(new Date(v.created_at).toLocaleString('vi-VN'))}</option>`).join('');
    const choices=[['frame','Khung từ video đã duyệt'],...(covers.uploads??[]).map(a=>['uploaded_cover:'+a.cover_id,a.filename]),...(covers.project_images??[]).map(a=>['project_image:'+a.id,'Tư liệu: '+a.filename]),...(covers.candidates??[]).filter(a=>a.render_job_id===getVideo()?.id).map((a,i)=>['render_thumbnail:'+a.id,'Candidate đã chọn '+(i+1)])];
    const selection=$('delivery-cover-source').value;$('delivery-cover-source').innerHTML=choices.map(([value,label])=>`<option value="${escape(value)}">${escape(label)}</option>`).join('');$('delivery-cover-source').value=choices.some(c=>c[0]===selection)?selection:'frame';
    $('delivery-cover-logo').disabled=!covers.logo_configured;
    history=page.items;showHistory();controls();
  }
  function retain(record){if(!storage)throw Error('Trình duyệt chưa lưu được yêu cầu.');if(storage.getItem(key()))throw Error('Thử lại hoặc bỏ lần thử đang giữ trước khi tạo yêu cầu mới.');const raw=JSON.stringify(record);storage.setItem(key(),raw);if(storage.getItem(key())!==raw)throw Error('Không giữ được yêu cầu xuất.');}
  async function send(body,endpoint=null){const c=context(),p=getState().project;
    const value=await api(endpoint??`/api/projects/${p.id}/exports`,body);if(!current(c))return;
    storage?.removeItem(key());result(value);await refresh();onMessage('Đã tạo gói bàn giao. Tải file và đăng thủ công.');
  }
  $('delivery-create').addEventListener('click',()=>action(async()=>{if(getState().canEdit===false)throw Error('Vai trò này chỉ có quyền xem.');if(copyDirty)throw Error('Lưu caption trước khi tạo gói.');
    const p=getState().project,v=getVideo();if(!copyReady)throw Error('Làm mới nội dung đăng trước khi xuất.');if(v?.final_review?.decision!=='approve')throw Error('HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED');
    const body={revision:p.revision,render_job_id:v.id,expected_video_sha256:v.result.qc.final_sha256,profile:$('delivery-profile').value,
      filename:$('delivery-filename').value,caption_version:version,separate_subtitle:$('delivery-srt').checked,cover:$('delivery-cover').checked,
      cover_at_seconds:Number($('delivery-cover-time').value),request_key:newKey()};
    const source=$('delivery-cover-source').value||'frame',[sourceType,sourceId]=source.split(':');
    body.cover_settings={source:sourceType,source_id:sourceId??null,format:$('delivery-cover-format').value||'jpg',center_x:Number($('delivery-cover-x').value||50)/100,center_y:Number($('delivery-cover-y').value||50)/100,
      zoom:Number($('delivery-cover-zoom').value||1),title:$('delivery-cover-title').value,logo:$('delivery-cover-logo').checked};
    retain(body);await send(body);
  }));
  $('delivery-retry').addEventListener('click',()=>action(async()=>{if(getState().canEdit===false)return;const raw=storage?.getItem(key());if(!raw)return;const held=JSON.parse(raw);
    if(held.schema_version==='manual-delivery-pending.v2'){const prefix=`/api/projects/${getState().project.id}/exports/`;if(typeof held.path!=='string'||!held.path.startsWith(prefix)||!/^nexp_[a-f0-9]{32}\/(recreate-package|resume)$/.test(held.path.slice(prefix.length)))throw Error('Yêu cầu đang giữ không thuộc dự án này.');await send(held.body,held.path);}else await send(held);
  }));
  $('delivery-reset').addEventListener('click',()=>{if(!writeable())return;storage?.removeItem(key());controls();});
  $('delivery-refresh').addEventListener('click',()=>action(refresh));
  $('delivery-copy-platform').addEventListener('change',()=>{holdCopy();selected=$('delivery-copy-platform').value;fillCopy();});
  $('delivery-copy-history').addEventListener('change',()=>{const old=copyHistory.find(v=>String(v.version)===$('delivery-copy-history').value);if(old){variants=structuredClone(old.variants);copyDirty=true;fillCopy();controls();}});
  $('delivery-regenerate-copy').addEventListener('click',()=>{if(!writeable())return;holdCopy();variants[selected]=selected==='master'?{title:getState().project.document.name,caption:getState().project.document.proposal?.narration??''}:structuredClone(variants.master??{});copyDirty=true;fillCopy();controls();});
  for(const field of textFields)$('delivery-copy-'+field).addEventListener('input',()=>{copyDirty=true;controls();});
  $('delivery-save-copy').addEventListener('click',()=>action(async()=>{if(getState().canEdit===false)return;holdCopy();const c=context(),p=getState().project;
    const value=await api(`/api/projects/${p.id}/delivery-copy`,{expected_version:version,request_key:newKey(),variants});
    if(current(c)){version=value.version;copyDirty=false;await refresh();controls();onMessage('Đã lưu phiên bản nội dung đăng.');}}));
  $('delivery-copy-caption-button').addEventListener('click',async()=>{try{if(!clipboard?.writeText)throw Error('Chọn nội dung caption và nhấn Ctrl+C để sao chép.');await clipboard.writeText(manualCaption(copy()));onMessage('Đã sao chép caption.');}catch(e){onMessage(e.message,true);}});
  $('delivery-download-copy').addEventListener('click',()=>download(textFields.map(k=>`${k.toUpperCase()}\n${copy()[k]}`).join('\n\n'),'noi-dung-dang.txt'));
  $('delivery-upload-cover').addEventListener('click',()=>action(async()=>{if(getState().canEdit===false||!uploadCoverFile)return;const file=$('delivery-cover-file').files?.[0];if(!file||file.size>8*1024*1024||!file.size)throw Error('Chọn ảnh JPG/PNG/WebP tối đa 8 MB.');const c=context(),p=getState().project;const value=await uploadCoverFile(file,p.id,p.revision);if(current(c)){await refresh();$('delivery-cover-source').value='uploaded_cover:'+value.cover_id;onMessage('Đã lưu ảnh bìa. Quyền sử dụng ảnh vẫn cần kiểm tra.');}}));
  const checklist=['Đúng file video','Đúng hướng và độ phân giải','Đã nghe toàn bộ âm thanh','Đã kiểm tra phụ đề','Đã kiểm tra tiêu đề','Đã kiểm tra caption','Đã kiểm tra hashtag và CTA','Đã duyệt quyền ảnh/video','Đã duyệt quyền nhạc','Đã duyệt quyền giọng','Đã xem video từ đầu đến cuối','Đã tự chọn đúng tài khoản đăng','Đã tự kiểm tra quyền riêng tư'];
  for(let i=0;i<checklist.length;i++){const label=doc.createElement('label');label.className='check';const box=doc.createElement('input');box.type='checkbox';box.dataset.vfPermission='read';box.addEventListener('change',()=>{try{storage?.setItem(key()+':check:'+i,String(box.checked));}catch{}});label.append(box,doc.createTextNode(checklist[i]));$('delivery-checklist').append(label);}
  const open=doc.getElementById('native-delivery-open');if(open)open.hidden=false;open?.addEventListener('click',()=>{onOpen();root.scrollIntoView?.({behavior:'smooth',block:'start'});});
  function sync(){const c=context();root.hidden=!getState().project;
    if(loaded!==c){loaded=c;epoch++;const p=getState().project,projectKey=key();
      if(loadedProject!==projectKey){loadedProject=projectKey;version=0;variants={};copyDirty=false;copyReady=false;selected='master';$('delivery-copy-platform').value='master';
        variants.master={title:p?.document?.name??'',caption:p?.document?.proposal?.narration??''};fillCopy();}
      $('delivery-profile').value=profileForVideo(getVideo())??'vertical-short';$('delivery-result').replaceChildren();history=[];showHistory();
      for(const [i,box] of [...$('delivery-checklist').querySelectorAll('input')].entries()){try{box.checked=storage?.getItem(key()+':check:'+i)==='true';}catch{box.checked=false;}}
      if(p)void refresh().catch(e=>onMessage(e.message,true));
    }controls();
  }
  return {sync,controls,isWorking:()=>working,refresh};
}
