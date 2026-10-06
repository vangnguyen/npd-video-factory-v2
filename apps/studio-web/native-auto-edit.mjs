import {escapeText as esc} from './shot-studio.mjs';

export const supportsNativeAnalysis = session => session?.capabilities?.native_auto_edit_analysis===true;
export const formatTime = value => Number(value).toFixed(2);
const factorLabels={speech_coverage:'lời nói',motion:'chuyển động',information_density:'mật độ thông tin',hook_keywords:'từ khóa',quality:'chất lượng hình ảnh',pixel_novelty:'thay đổi hình ảnh',audio_energy:'âm thanh'};
export function transcriptEdits(transcript, values) {
  return transcript.segments.filter(segment=>values[segment.segment_id]!==undefined&&values[segment.segment_id]!==segment.text)
    .map(segment=>({segment_id:segment.segment_id,text:values[segment.segment_id]}));
}
export function analysisMarkup(bundle) {
  if(!bundle?.analyses?.length)return '<p class="hint">Chưa có phân tích dựng nguồn. Tải video rồi chọn Đo cảnh & âm thanh.</p>';
  return bundle.analyses.map(item=>{
    const analysis=item.analysis, transcript=analysis.transcript;
    return `<article class="native-analysis" data-native-analysis="${esc(analysis.analysis_id)}"><h3>${esc(item.filename)}</h3>
      <p class="hint">Đã đo ${formatTime(analysis.source_media.duration_seconds)} giây · ${item.scenes.length} cảnh. Kết quả chưa áp dụng vào timeline. Video và âm thanh gốc được giữ nguyên.</p>
      ${transcript?`<details open><summary>Lời nói · bản ${transcript.version} · ${esc(transcript.language)}</summary>
      ${transcript.segments.map(segment=>`<label>${formatTime(segment.start_seconds)}–${formatTime(segment.end_seconds)}s
        <textarea data-auto-edit-control data-transcript-segment="${esc(segment.segment_id)}" rows="2" maxlength="4000">${esc(segment.text)}</textarea></label>
        <p class="hint">${segment.words.length?`${segment.words.length} từ có thời gian đo từ nguồn.`:'Đoạn này không có căn chỉnh từng từ; không suy đoán thời gian mới.'}</p>`).join('')}
      <button data-auto-edit-control data-save-transcript type="button" class="secondary">Lưu lời nói đã sửa</button>
      <details><summary>Lịch sử lời nói · ${item.transcript_history.length} bản</summary><label>Bản đã lưu<select data-auto-edit-control data-transcript-history>
      ${item.transcript_history.map(value=>`<option value="${esc(value.transcript_id)}">Bản ${value.version} · ${value.is_original_evidence?'nhận diện gốc':'bản chỉnh sửa'}</option>`).join('')}</select></label>
      <button data-auto-edit-control data-restore-transcript type="button" class="secondary">Khôi phục thành bản mới</button></details></details>`:
      '<p class="hint">Chưa có lời nói nhận diện. Có thể phân tích lời nói bằng kết nối ASR; chưa đề xuất cắt im lặng.</p>'}
      <details><summary>Cảnh & chất lượng · ${item.scenes.length}</summary>${item.scenes.map(scene=>`<section><strong>${formatTime(scene.start_seconds)}–${formatTime(scene.end_seconds)}s · ${esc(scene.semantic_label)}</strong>
        <p>${esc(scene.transcript_excerpt||'Chưa có mô tả ngữ nghĩa từ lời nói hoặc Vision.')}</p><p class="hint">Chuyển động: ${scene.motion_score===null?'chưa có dữ liệu':formatTime(scene.motion_score)} · Chất lượng đo từ khung hình: ${scene.quality_score===null?'chưa có dữ liệu':formatTime(scene.quality_score)}${scene.needs_attention?' · cần kiểm tra hình ảnh':''}</p></section>`).join('')}</details>
      <details><summary>Đề xuất im lặng · ${analysis.silence_decisions.length}</summary><p class="hint">Chỉ là quyết định không phá hủy nguồn; chưa cắt video. Khoảng có lời nói được bảo vệ.</p>
        ${analysis.silence_decisions.map(cut=>`<p>${formatTime(cut.start_seconds)}–${formatTime(cut.end_seconds)}s · ${cut.enabled?'có thể xem xét':'giữ lại'}${cut.conflicts_with_speech?' · trùng lời nói':''}</p>`).join('')||'<p>Chưa có khoảng cắt an toàn được đề xuất.</p>'}</details>
      <details><summary>Điểm nổi bật · Top 3 / Top 5</summary><label>Số gợi ý<select data-auto-edit-control data-highlight-count><option value="3">Top 3</option><option value="5">Top 5</option></select></label>
        ${item.highlights.map((value,index)=>`<section data-highlight-rank="${index+1}" ${index>=3?'hidden':''}><strong>${formatTime(value.recommended_start)}–${formatTime(value.recommended_end)}s · điểm ${formatTime(value.highlight_score)}</strong><p>Gợi ý theo ${esc(Object.entries(value.evidence.factors).filter(([,score])=>score!==null).map(([key])=>factorLabels[key]??key).join(', '))}. Hãy xem đoạn nguồn trước khi chọn.</p><p class="hint">Yếu tố chưa có dữ liệu: ${esc(value.evidence.missing_factors.map(key=>factorLabels[key]??key).join(', ')||'không có')}</p></section>`).join('')}</details>
    </article>`;
  }).join('');
}

export function initializeNativeAnalysis({api,getProject,onProject,onDirty,onMessage,getState}) {
  const region=document.getElementById('native-auto-edit-results');
  let bundle=null, identity=null, loading=false,editingAnalysis=null;
  async function refresh(reset=false) {
    const project=getProject(), key=project?`${project.id}:${project.revision}`:null;
    document.getElementById('native-auto-edit-panel').hidden=!project;
    if(!project){identity=null;bundle=null;loading=false;region.innerHTML='';return;}
    if(identity===key){if(reset&&bundle){editingAnalysis=null;region.innerHTML=analysisMarkup(bundle);}return;}
    identity=key;loading=true;editingAnalysis=null;bundle=null;region.innerHTML='<p class="hint">Đang đọc phân tích nguồn…</p>';
    try{const value=await api(`/api/projects/${project.id}/auto-edit`);if(identity!==key)return;bundle=value;region.innerHTML=analysisMarkup(value);}
    catch(error){if(identity===key){identity=null;onMessage(error.message,true);}}
    finally{if(identity===key||identity===null){loading=false;controls();}}
  }
  function controls() {
    const state=getState(), project=getProject();
    const blocked=loading||state.busy||(state.dirty&&state.dirtyPart!=='autoedit')||!project||project.archived||(project.jobs??[]).some(job=>['queued','running','retrying'].includes(job.status));
    region.querySelectorAll('[data-auto-edit-control]').forEach(element=>element.disabled=blocked||(editingAnalysis&&element.closest('[data-native-analysis]').dataset.nativeAnalysis!==editingAnalysis));
    document.getElementById('measure-auto-edit').disabled=blocked||state.dirty||!bundle?.pending_asset_ids?.length;
  }
  region.addEventListener('input',event=>{if(event.target.matches('[data-transcript-segment]')){editingAnalysis=event.target.closest('[data-native-analysis]').dataset.nativeAnalysis;onDirty('autoedit');}});
  region.addEventListener('change',event=>{if(event.target.matches('[data-highlight-count]')){
    event.target.closest('[data-native-analysis]').querySelectorAll('[data-highlight-rank]').forEach(element=>element.hidden=Number(element.dataset.highlightRank)>Number(event.target.value));
  }});
  region.addEventListener('click',async event=>{
    const button=event.target.closest('[data-save-transcript],[data-restore-transcript]');if(!button)return;
    const item=bundle?.analyses.find(value=>value.analysis.analysis_id===button.closest('[data-native-analysis]').dataset.nativeAnalysis);
    if(!item?.analysis.transcript)return;
    if(button.matches('[data-restore-transcript]')&&getState().dirty){onMessage('Lưu lời nói đang sửa trước khi khôi phục lịch sử.',true);return;}
    const article=button.closest('[data-native-analysis]'), current=item.analysis.transcript;
    let segments, base;
    if(button.matches('[data-restore-transcript]')){
      base=item.transcript_history.find(value=>value.transcript_id===article.querySelector('[data-transcript-history]').value);
      if(!base?.segments.length)return;
      segments=[{segment_id:base.segments[0].segment_id,text:base.segments[0].text}];
    }else{
      segments=transcriptEdits(current,Object.fromEntries([...article.querySelectorAll('[data-transcript-segment]')].map(element=>[element.dataset.transcriptSegment,element.value])));
      if(!segments.length){onMessage('Lời nói chưa thay đổi.');return;}
    }
    loading=true;controls();
    try{
      const project=getProject();
      await api(`/api/projects/${project.id}/auto-edit/${item.analysis.analysis_id}/transcript`,{
        revision:project.revision,edit:{expected_version:current.version,segments,
          ...(bundle.source_timeline_version?{expected_timeline_version:bundle.source_timeline_version}:{}),
          ...(base?{base_transcript_id:base.transcript_id}:{})}});
      identity=null;onProject(await api(`/api/projects/${project.id}`),true);
      onMessage('Đã lưu bản lời nói mới. Bản nhận diện gốc vẫn được giữ; phiên bản dự án cần duyệt lại.');
    }catch(error){onMessage(error.message,true);}
    finally{loading=false;controls();}
  });
  return {refresh,controls};
}
