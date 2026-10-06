import {escapeText as esc} from './shot-studio.mjs';

export const supportsNativeAnalysis = session => session?.capabilities?.native_auto_edit_analysis===true;
export const formatTime = value => Number(value).toFixed(2);
const factorLabels={speech_coverage:'lời nói',motion:'chuyển động',information_density:'mật độ thông tin',hook_keywords:'từ khóa',quality:'chất lượng hình ảnh',pixel_novelty:'thay đổi hình ảnh',audio_energy:'âm thanh'};
export function transcriptEdits(transcript, values) {
  return transcript.segments.filter(segment=>values[segment.segment_id]!==undefined&&values[segment.segment_id]!==segment.text)
    .map(segment=>({segment_id:segment.segment_id,text:values[segment.segment_id]}));
}
export function sourceCreatePayload(project,item,{aspectRatio='9:16',highlightId='',silenceIds=[]}={}) {
  if(!project||project.document?.input_kind!=='media'||project.document.proposal||project.archived)throw new Error('Dựng nguồn cần một dự án video tải lên chưa có kịch bản lồng tiếng.');
  if(!['9:16','16:9','1:1','4:5'].includes(aspectRatio))throw new Error('Chọn định dạng đã hỗ trợ.');
  const safe=new Set(item.analysis.silence_decisions.filter(c=>c.enabled&&!c.conflicts_with_speech).map(c=>c.decision_id));
  if(new Set(silenceIds).size!==silenceIds.length||silenceIds.some(id=>!safe.has(id)))throw new Error('Khoảng cắt đã thay đổi hoặc trùng lời nói.');
  const highlight=highlightId?item.highlights.find(h=>h.highlight_id===highlightId):null;
  if(highlightId&&!highlight)throw new Error('Điểm nổi bật đã thay đổi. Đọc lại phân tích.');
  return {revision:project.revision,action:'create',payload:{analysis_id:item.analysis.analysis_id,
    transcript_id:item.analysis.transcript?.transcript_id??null,aspect_ratio:aspectRatio,silence_decision_ids:silenceIds,
    ...(project.document.canonical_timeline?{expected_version:project.document.canonical_timeline.version}:{}),
    ...(highlight?{source_window:[highlight.recommended_start,highlight.recommended_end]}:{})}};
}
export function analysisMarkup(bundle,{project=null,sourceEnabled=false}={}) {
  if(!bundle?.analyses?.length)return '<p class="hint">Chưa có phân tích dựng nguồn. Tải video rồi chọn Đo cảnh & âm thanh.</p>';
  return bundle.analyses.map(item=>{
    const analysis=item.analysis, transcript=analysis.transcript;
    return `<article class="native-analysis" data-native-analysis="${esc(analysis.analysis_id)}"><h3>${esc(item.filename)}</h3>
      <p class="hint">Đã đo ${formatTime(analysis.source_media.duration_seconds)} giây · ${item.scenes.length} cảnh. ${project?.document.canonical_timeline?.snapshot?.metadata?.source_analysis_id===analysis.analysis_id?'Bản dựng hiện tại sử dụng phân tích này; kiểm tra điểm cắt đã lưu trong timeline.':'Phân tích này chưa được chọn cho bản dựng hiện tại.'} Video và âm thanh gốc được giữ nguyên.</p>
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
        ${analysis.silence_decisions.map(cut=>`<p>${sourceEnabled?`<label class="check"><input type="checkbox" data-auto-edit-control data-source-silence="${esc(cut.decision_id)}" ${cut.enabled&&!cut.conflicts_with_speech?'':'data-unsafe="true" disabled'}>`:''}${formatTime(cut.start_seconds)}–${formatTime(cut.end_seconds)}s · ${cut.enabled?'có thể xem xét':'giữ lại'}${cut.conflicts_with_speech?' · trùng lời nói':''}${sourceEnabled?'</label>':''}</p>`).join('')||'<p>Chưa có khoảng cắt an toàn được đề xuất.</p>'}</details>
      <details><summary>Điểm nổi bật · Top 3 / Top 5</summary><label>Số gợi ý<select data-auto-edit-control data-highlight-count><option value="3">Top 3</option><option value="5">Top 5</option></select></label>
        ${item.highlights.map((value,index)=>`<section data-highlight-rank="${index+1}" ${index>=3?'hidden':''}><strong>${formatTime(value.recommended_start)}–${formatTime(value.recommended_end)}s · điểm ${formatTime(value.highlight_score)}</strong><p>Gợi ý theo ${esc(Object.entries(value.evidence.factors).filter(([,score])=>score!==null).map(([key])=>factorLabels[key]??key).join(', '))}. Hãy xem đoạn nguồn trước khi chọn.</p><p class="hint">Yếu tố chưa có dữ liệu: ${esc(value.evidence.missing_factors.map(key=>factorLabels[key]??key).join(', ')||'không có')}</p></section>`).join('')}</details>
      ${sourceEnabled&&project?.document.input_kind==='media'&&!project.document.proposal?`<details open><summary>Dựng video nguồn</summary><label>Lựa chọn<select data-auto-edit-control data-source-highlight><option value="">Toàn bộ video</option>${item.highlights.map(h=>`<option value="${esc(h.highlight_id)}">Điểm nổi bật ${h.rank??''} · ${formatTime(h.recommended_start)}–${formatTime(h.recommended_end)}s</option>`).join('')}</select></label><label>Định dạng<select data-auto-edit-control data-source-ratio>${['9:16','16:9','1:1','4:5'].map(r=>`<option>${r}</option>`).join('')}</select></label><p class="hint">Chỉ cắt các khoảng im lặng bạn đã tích chọn. Giữ nguyên video gốc. ${project.document.canonical_timeline?'Tạo lại sẽ lưu một bản timeline mới từ nguồn; chỉnh sửa hiện tại vẫn có trong lịch sử.':''}</p><button data-auto-edit-control data-create-source type="button">${project.document.canonical_timeline?'Tạo lại bản dựng từ lựa chọn':'Tạo bản dựng từ lựa chọn'}</button></details>`:''}
    </article>`;
  }).join('');
}

export function initializeNativeAnalysis({api,getProject,onProject,onDirty,onMessage,getState,sourceEnabled=false,onSourceCreated=()=>{},onWorking=()=>{}}) {
  const region=document.getElementById('native-auto-edit-results');
  let bundle=null, identity=null, loading=false,editingAnalysis=null;
  const markup=value=>analysisMarkup(value,{project:getProject(),sourceEnabled});
  async function refresh(reset=false) {
    const project=getProject(), key=project?`${project.id}:${project.revision}`:null;
    document.getElementById('native-auto-edit-panel').hidden=!project;
    if(!project){identity=null;bundle=null;loading=false;region.innerHTML='';return;}
    if(identity===key){if(reset&&bundle){editingAnalysis=null;region.innerHTML=markup(bundle);}return;}
    identity=key;loading=true;editingAnalysis=null;bundle=null;region.innerHTML='<p class="hint">Đang đọc phân tích nguồn…</p>';
    try{const value=await api(`/api/projects/${project.id}/auto-edit`);if(identity!==key)return;bundle=value;region.innerHTML=markup(value);}
    catch(error){if(identity===key){identity=null;onMessage(error.message,true);}}
    finally{if(identity===key||identity===null){loading=false;onWorking();controls();}}
  }
  function controls() {
    const state=getState(), project=getProject();
    const blocked=loading||state.busy||(state.dirty&&state.dirtyPart!=='autoedit')||!project||project.archived||(project.jobs??[]).some(job=>['queued','running','retrying'].includes(job.status));
    region.querySelectorAll('[data-auto-edit-control]').forEach(element=>element.disabled=blocked||element.dataset.unsafe==='true'||(element.matches('[data-create-source]')&&state.dirty)||(editingAnalysis&&element.closest('[data-native-analysis]').dataset.nativeAnalysis!==editingAnalysis));
    document.getElementById('measure-auto-edit').disabled=blocked||state.dirty||!bundle?.pending_asset_ids?.length;
  }
  region.addEventListener('input',event=>{if(event.target.matches('[data-transcript-segment]')){editingAnalysis=event.target.closest('[data-native-analysis]').dataset.nativeAnalysis;onDirty('autoedit');}});
  region.addEventListener('change',event=>{if(event.target.matches('[data-highlight-count]')){
    event.target.closest('[data-native-analysis]').querySelectorAll('[data-highlight-rank]').forEach(element=>element.hidden=Number(element.dataset.highlightRank)>Number(event.target.value));
  }});
  region.addEventListener('click',async event=>{
    const create=event.target.closest('[data-create-source]');
    if(create){
      if(loading||getState().dirty||getState().busy)return;
      const project=getProject(),article=create.closest('[data-native-analysis]'),item=bundle?.analyses.find(value=>value.analysis.analysis_id===article.dataset.nativeAnalysis);
      if(!item)return;
      loading=true;onWorking();controls();
      try{const request=sourceCreatePayload(project,item,{aspectRatio:article.querySelector('[data-source-ratio]').value,
        highlightId:article.querySelector('[data-source-highlight]').value,silenceIds:[...article.querySelectorAll('[data-source-silence]:checked')].map(el=>el.dataset.sourceSilence)});
        const value=await api(`/api/projects/${project.id}/auto-edit/timeline`,request);
        if(getProject()?.id!==project.id||getProject()?.revision!==project.revision)return;
        identity=null;onProject(value,true);onSourceCreated();onMessage('Đã lưu bản dựng nguồn. Xem shot, chỉnh timeline và tạo preview trước khi duyệt render.');
      }catch(error){onMessage(error.message,true);}finally{loading=false;onWorking();controls();}return;
    }
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
    loading=true;onWorking();controls();
    try{
      const project=getProject();
      await api(`/api/projects/${project.id}/auto-edit/${item.analysis.analysis_id}/transcript`,{
        revision:project.revision,edit:{expected_version:current.version,segments,
          ...(bundle.source_timeline_version?{expected_timeline_version:bundle.source_timeline_version}:{}),
          ...(base?{base_transcript_id:base.transcript_id}:{})}});
      identity=null;onProject(await api(`/api/projects/${project.id}`),true);
      onMessage('Đã lưu bản lời nói mới. Bản nhận diện gốc vẫn được giữ; phiên bản dự án cần duyệt lại.');
    }catch(error){onMessage(error.message,true);}
    finally{loading=false;onWorking();controls();}
  });
  return {refresh,controls,isWorking:()=>loading};
}
