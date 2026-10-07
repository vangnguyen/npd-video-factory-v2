const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[char]);

export const supportsMediaFrames=session=>session?.capabilities?.native_media_frame_analysis===true;
const number=value=>Number.isFinite(value)?value.toFixed(2):'chưa có dữ liệu';
export function frameImageUrl(projectId,frameId){
  if(!/^[a-f0-9]{32}$/.test(projectId)||!/^mfr_[a-f0-9]{24}$/.test(frameId))throw new Error('Mã khung hình không hợp lệ.');
  return `/api/projects/${projectId}/media-frames/${frameId}/image`;
}
export function framesMarkup(bundle){
  if(!bundle?.observations?.length)return '<p class="hint">Chưa có khung hình đã đo. Lưu nguồn rồi chọn “Đo khung hình”.</p>';
  return bundle.observations.map(item=>`<article><h3>Khung hình nguồn · ${esc(item.asset_id)}</h3>
    <p class="hint">Đo pixel trên máy; chưa có nhận diện đối tượng, chữ, hành động hoặc chủ thể. Gợi ý thumbnail chỉ theo độ nét/sáng đã lấy mẫu, cần bạn kiểm tra nội dung và quyền sử dụng.</p>
    ${item.identity_rebinding?'<p class="hint">Tái sử dụng phép đo từ dự án gốc, giữ nguyên tệp bằng chứng; chưa đo lại.</p>':''}
    <p>Quyền sử dụng: ${item.rights_status==='owner_upload_attestation'?'do người tải nguồn xác nhận; chưa xác minh độc lập':'chưa rõ'}. Độ tin cậy AI: chưa có.</p>
    <details open><summary>Gợi ý thumbnail · ${item.thumbnail_candidate_ids.length}</summary>
      ${item.frames.filter(frame=>item.thumbnail_candidate_ids.includes(frame.frame_id)).map(frame=>frameMarkup(bundle.project_id,frame)).join('')||'<p>Không có mẫu phù hợp; kiểm tra nguồn.</p>'}</details>
    <details><summary>Tất cả mẫu · ${item.frames.length}</summary>${item.frames.map(frame=>frameMarkup(bundle.project_id,frame)).join('')}</details>
  </article>`).join('');
}
function frameMarkup(projectId,frame){
  const facts=frame.pixel_facts;
  return `<figure><img loading="lazy" src="${frameImageUrl(projectId,frame.frame_id)}" alt="Mẫu nguồn tại ${number(frame.timestamp_seconds)} giây" width="240" height="160" style="object-fit:contain;max-width:100%;background:#131923">
    <figcaption>${number(frame.timestamp_seconds)}s · ${frame.width}×${frame.height} · sáng trung bình ${number(facts.luma_mean)}/255 · độ nét pixel ${number(facts.laplacian_variance)}
    ${facts.black_sample?' · mẫu đen':''}${frame.duplicate_sample_of?' · giống hệt một mẫu trước (không kết luận video bị đứng)':''}</figcaption></figure>`;
}
export function initializeMediaFrames({api,getProject,getState,onWorking,onMessage}){
  const panel=document.getElementById('native-media-frames-panel'),region=document.getElementById('native-media-frames-results');
  let identity=null,bundle=null,loading=false,sequence=0;
  function controls(){
    const project=getProject(),state=getState();
    document.getElementById('measure-media-frames').disabled=!project||project.archived||loading||state.busy||state.dirty||
      project.jobs?.some(job=>['queued','running','retrying'].includes(job.status))||!bundle?.pending_asset_ids?.length;
  }
  async function refresh(){
    const project=getProject(),key=project?`${project.id}:${project.revision}`:null;
    panel.hidden=!project;
    if(!project){sequence++;identity=null;loading=false;bundle=null;region.innerHTML='';return;}
    if(identity===key)return;
    const request=++sequence;identity=key;loading=true;bundle=null;region.innerHTML='<p class="hint">Đang đọc khung hình đã đo…</p>';onWorking();
    try{const value=await api(`/api/projects/${project.id}/media-frames`);
      if(request!==sequence)return;bundle=value;region.innerHTML=framesMarkup(value);
    }catch(error){if(request===sequence){identity=null;region.textContent='Không đọc được bằng chứng khung hình. Thử tải lại dự án.';onMessage(error.message,true);}}
    finally{if(request===sequence){loading=false;controls();onWorking();}}
  }
  return {refresh,controls,isWorking:()=>loading};
}
