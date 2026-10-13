// Review saved observations explicitly. Loading and freezing never dispatch a provider.
const projectId = /^[a-f0-9]{32}$/;
const analysisId = /^ana_[a-f0-9]{24}$/;
const transcriptId = /^trn_[a-f0-9]{24}$/;
const assessmentId = /^nsci_[a-f0-9]{32}$/;
const highlightId = /^hig_[a-f0-9]{24}$/;
const assetId = /^[a-f0-9]{32}(?:\.[a-z0-9]{1,16}){1,3}$/;
const sha256 = /^[a-f0-9]{64}$/;
const ratios = ['9:16', '16:9', '1:1', '4:5'];
const referenceKeys = ['analysis_id', 'asset_id', 'asset_sha256', 'analysis_sha256',
  'transcript_id', 'transcript_version', 'transcript_sha256'];
const factorLabels = {speech_coverage:'Lời nói', motion:'Chuyển động', information_density:'Mật độ thông tin',
  hook_keywords:'Từ khóa', quality:'Chất lượng hình ảnh', pixel_novelty:'Thay đổi hình ảnh', audio_energy:'Âm thanh'};
const integer = value => Number.isSafeInteger(value) && value >= 1;
const score = value => value === null || Number.isFinite(value) && value >= 0 && value <= 1;
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const sameReferences = (left, right) => referenceKeys.every(key => left?.[key] === right?.[key]);
const formatted = value => value === null || value === undefined ? 'Chưa có dữ liệu' : Number(value).toFixed(3);
const reasonLabels = new Map([
  ['saved text keyword/information-density heuristics', 'Từ khóa và mật độ thông tin trong nội dung đã lưu (ước lượng theo quy tắc)'],
  ['semantic text evidence unavailable', 'Chưa có bằng chứng ngữ nghĩa từ nội dung'],
  ['transcript coverage', 'Tỷ lệ cảnh có lời nói'],
  ['measured pixel-change proxy', 'Thay đổi giữa các khung hình mẫu (gợi ý chuyển động)'],
  ['legacy scene score (unverified motion)', 'Điểm cảnh cũ; chuyển động chưa được kiểm chứng'],
  ['measured audio energy', 'Cường độ âm thanh đã đo'],
  ['measured exposure heuristic', 'Ước lượng ánh sáng từ khung hình mẫu'],
  ['saved Vision quality', 'Chất lượng từ kết quả Vision đã lưu'],
]);

export function highlightReasonSummary(reason) {
  const labels = reason.split(';').map(value => value.trim()).filter(Boolean).map(value => {
    if (reasonLabels.has(value)) return reasonLabels.get(value);
    if (value.startsWith('hook keywords:')) return 'Từ khóa nổi bật: '+value.slice('hook keywords:'.length).trim();
    return 'Yếu tố khác trong bằng chứng đã lưu; xem chi tiết';
  });
  return [...new Set(labels)].join(' · ') || 'Chưa có giải thích trong bằng chứng đã lưu.';
}

function validateReferences(refs) {
  if (!object(refs) || !analysisId.test(refs.analysis_id) || !assetId.test(refs.asset_id)
    || !sha256.test(refs.asset_sha256) || !sha256.test(refs.analysis_sha256)
    || !(refs.transcript_id === null ? refs.transcript_version === null && refs.transcript_sha256 === null
      : transcriptId.test(refs.transcript_id) && integer(refs.transcript_version) && sha256.test(refs.transcript_sha256)))
    throw Error('Biên nhận nguồn cảnh không hợp lệ.');
}

function validateResult(result) {
  if (!object(result) || !Array.isArray(result.scenes) || result.scenes.length > 2000
    || !Array.isArray(result.scene_ranking) || result.scene_ranking.length > 2000)
    throw Error('Biên nhận cảnh hoặc điểm nổi bật không hợp lệ.');
  if (result.semantic_vision_used !== false || result.semantic_vision_state !== 'NOT_CONFIGURED'
    || result.prediction_confidence_calibrated !== false || result.continuous_tracking_performed !== false
    || result.decoded_source_pts_verified !== false || result.recommendation_only !== true
    || result.canonical_timeline_mutated !== false || result.silence_decisions_mutated !== false
    || result.publishing_authorized !== false || result.owner_uat_accepted !== false || result.provider_dispatches !== 0)
    throw Error('Biên nhận không được nhận thêm năng lực hoặc quyền chưa kiểm chứng.');
  const sceneIds = new Set();
  for (const scene of result.scenes) {
    if (typeof scene.scene_id !== 'string' || !/^[A-Za-z0-9_-]{4,80}$/.test(scene.scene_id)
      || sceneIds.has(scene.scene_id) || !Number.isSafeInteger(scene.ordinal) || scene.ordinal < 0
      || !Number.isFinite(scene.start_seconds) || !Number.isFinite(scene.end_seconds)
      || scene.start_seconds < 0 || scene.end_seconds <= scene.start_seconds
      || typeof scene.semantic_label !== 'string' || typeof scene.description !== 'string'
      || !score(scene.confidence) || typeof scene.needs_attention !== 'boolean' || !object(scene.evidence))
      throw Error('Cảnh trong biên nhận không hợp lệ.');
    sceneIds.add(scene.scene_id);
  }
  const highlights = new Set();
  for (const item of result.scene_ranking) {
    const evidence = item.evidence;
    if (!highlightId.test(item.highlight_id) || highlights.has(item.highlight_id)
      || !Number.isFinite(item.highlight_score) || !score(item.highlight_score)
      || typeof item.reason !== 'string' || typeof item.recommended_platform !== 'string'
      || !Number.isFinite(item.recommended_start) || !Number.isFinite(item.recommended_end)
      || item.recommended_start < 0 || item.recommended_end <= item.recommended_start
      || !object(evidence) || !object(evidence.factors) || !object(evidence.contributions)
      || !Array.isArray(evidence.missing_factors) || evidence.missing_factors.some(key => typeof key !== 'string')
      || Object.values(evidence.factors).some(value => !score(value))
      || Object.values(evidence.contributions).some(value => !Number.isFinite(value) || value < 0 || value > 1)
      || !score(evidence.confidence))
      throw Error('Điểm nổi bật trong biên nhận không hợp lệ.');
    for (const key of evidence.missing_factors) {
      if (evidence.factors[key] !== null || key in evidence.contributions)
        throw Error('Yếu tố thiếu dữ liệu không được có điểm đóng góp.');
    }
    for (const [key, value] of Object.entries(evidence.factors)) {
      if (value === null && !evidence.missing_factors.includes(key))
        throw Error('Biên nhận không khai báo yếu tố còn thiếu.');
    }
    highlights.add(item.highlight_id);
  }
  if (result.highlights !== undefined && (!Array.isArray(result.highlights)
    || result.highlights.some(item => !highlights.has(item.highlight_id))))
    throw Error('Danh sách điểm nổi bật không khớp xếp hạng.');
}

export function validateSceneAssessments(value, state) {
  if (value?.schema_version !== 'native-current-scene-page.v1' || !projectId.test(value.project_id)
    || value.workspace_id !== state.workspace_id || value.project_id !== state.project?.id
    || value.revision !== state.project?.revision || !integer(value.revision)
    || !(value.timeline_version === null || integer(value.timeline_version))
    || !Array.isArray(value.available_sources) || value.available_sources.length > 250
    || !Array.isArray(value.items) || value.items.length > 500
    || value.provider_calls !== 0 || value.source_media_mutated !== false
    || value.canonical_timeline_mutated !== false || value.publishing_enabled !== false)
    throw Error('Nguồn, workspace hoặc phiên bản dự án đã thay đổi. Đọc lại.');
  const sources = new Set();
  for (const source of value.available_sources) {
    validateReferences(source);
    if (sources.has(source.analysis_id) || typeof source.filename !== 'string')
      throw Error('Biên nhận nguồn cảnh bị trùng hoặc thiếu tên.');
    sources.add(source.analysis_id);
  }
  const assessments = new Set();
  for (const item of value.items) {
    const assessment = item.assessment;
    if (assessment?.schema_version !== 'native-current-scene-assessment.v1'
      || !assessmentId.test(assessment?.assessment_id) || assessments.has(assessment.assessment_id)
      || !sha256.test(item.sha256) || typeof item.current !== 'boolean' || !integer(assessment.version)
      || assessment.project_id !== value.project_id || assessment.workspace_id !== value.workspace_id
      || !integer(assessment.source_revision) || assessment.source_revision > value.revision
      || !sha256.test(assessment.input_sha256) || !sha256.test(assessment.source_document_sha256) || typeof assessment.algorithm !== 'string'
      || typeof assessment.actor_ref !== 'string' || typeof assessment.created_at !== 'string'
      || assessment.recommendation_only !== true || assessment.semantic_vision_state !== 'NOT_CONFIGURED')
      throw Error('Biên nhận đánh giá cảnh không hợp lệ.');
    validateReferences(assessment.input_refs);
    validateResult(assessment.result);
    if (item.current && !value.available_sources.some(source => sameReferences(source, assessment.input_refs)))
      throw Error('Đánh giá cũ không được nhận là kết quả hiện tại.');
    assessments.add(assessment.assessment_id);
  }
  return value;
}

export function sceneAssessmentPayload(page, source, acknowledged) {
  if (acknowledged !== true) throw Error('Xác nhận dùng bằng chứng đã lưu trước khi tạo đánh giá.');
  if (!page.available_sources.some(candidate => sameReferences(candidate, source)))
    throw Error('Nguồn phân tích đã thay đổi. Đọc lại.');
  return {revision:page.revision, analysis_id:source.analysis_id, asset_sha256:source.asset_sha256,
    analysis_sha256:source.analysis_sha256, expected_transcript_id:source.transcript_id,
    expected_transcript_version:source.transcript_version, expected_transcript_sha256:source.transcript_sha256,
    expected_timeline_version:page.timeline_version, acknowledged_saved_evidence:true};
}

export function reviewedHighlightPayload(page, item, {aspectRatio='9:16', selectedHighlightId, acknowledged=false}={}) {
  if (!item?.current || !page.items.includes(item)
    || !page.available_sources.some(source => sameReferences(source, item.assessment.input_refs)))
    throw Error('Đánh giá chưa còn hiệu lực với nguồn hiện tại. Đọc lại.');
  if (acknowledged !== true) throw Error('Xem lý do và bằng chứng rồi xác nhận lựa chọn trước khi dựng.');
  if (!ratios.includes(aspectRatio)) throw Error('Chọn định dạng được hỗ trợ.');
  const refs = item.assessment.input_refs;
  const payload = {analysis_id:refs.analysis_id, transcript_id:refs.transcript_id, aspect_ratio:aspectRatio,
    ...(page.timeline_version === null ? {} : {expected_version:page.timeline_version}),
    reviewed_local_scene:{assessment_id:item.assessment.assessment_id, expected_assessment_sha256:item.sha256, acknowledged:true}};
  if (selectedHighlightId !== undefined) {
    if (!item.assessment.result.scene_ranking.some(highlight => highlight.highlight_id === selectedHighlightId))
      throw Error('Điểm nổi bật đã thay đổi. Đọc lại.');
    payload.reviewed_highlight_id = selectedHighlightId;
  }
  return {revision:page.revision, action:'create', payload};
}

export function reviewedShortsPayload(page, item, options={}) {
  const {count=3, requestKey, ...selection} = options;
  const body = reviewedHighlightPayload(page, item, selection);
  if (![3,5].includes(count) || !projectId.test(requestKey)) throw Error('Số bản hoặc mã yêu cầu Auto Shorts không hợp lệ.');
  return {revision:body.revision, payload:{...body.payload, request_key:requestKey, count, maximum_duration_seconds:60}};
}

export function validateSceneAssessmentSave(response, state, page, source) {
  if (![page.revision, page.revision+1].includes(response?.revision))
    throw Error('Biên nhận lưu không khớp phiên bản dự án.');
  const verified = validateSceneAssessments(response, {...state, project:{...state.project, revision:response.revision}});
  if (verified.timeline_version !== page.timeline_version || !verified.items.some(item => item.current
    && sameReferences(item.assessment.input_refs, source)))
    throw Error('Biên nhận không có đánh giá hiện tại đúng nguồn đã gửi.');
  return verified;
}

export function validateSceneSelectionLineage(value, page, request) {
  const selection = request.payload.reviewed_local_scene;
  const original = page.items.find(item => item.assessment.assessment_id === selection.assessment_id
    && item.sha256 === selection.expected_assessment_sha256);
  if (!original || !object(value) || value.schema_version !== 'native-current-scene-selection.v1'
    || value.assessment_id !== original.assessment.assessment_id || value.assessment_sha256 !== original.sha256
    || value.source_project_id !== page.project_id || value.input_sha256 !== original.assessment.input_sha256
    || !sameReferences(value.input_refs, original.assessment.input_refs) || value.recommendation_only !== true
    || value.automatic_application !== false || value.semantic_vision_state !== 'NOT_CONFIGURED'
    || value.prediction_confidence_calibrated !== false || value.owner_uat_accepted !== false)
    throw Error('Biên nhận không giữ đúng nguồn đánh giá đã review.');
  return value;
}

export function validateReviewedTimeline(response, page, request) {
  const timeline = response?.document?.canonical_timeline;
  if (response?.id !== page.project_id || response.revision !== page.revision+1 || response.approval != null
    || timeline?.version !== (page.timeline_version ?? 0)+1
    || timeline.snapshot?.aspect_ratio !== request.payload.aspect_ratio
    || timeline.snapshot?.metadata?.reviewed_highlight_id !== request.payload.reviewed_highlight_id)
    throw Error('Biên nhận timeline không khớp lựa chọn hiện tại.');
  validateSceneSelectionLineage(timeline.snapshot.metadata.reviewed_local_scene_selection, page, request);
  return response;
}

export function validateReviewedShorts(response, page, request) {
  const batch = response?.batch;
  if (!object(batch) || batch.source_project_id !== page.project_id || batch.source_revision !== page.revision
    || batch.request_key !== request.payload.request_key || batch.analysis_id !== request.payload.analysis_id
    || batch.transcript_id !== request.payload.transcript_id || batch.aspect_ratio !== request.payload.aspect_ratio
    || batch.requested_count !== request.payload.count || batch.maximum_duration_seconds !== 60
    || batch.provider_calls !== 0 || batch.paid_operations !== 0 || batch.parent_document_mutated !== false
    || batch.human_approval_required !== true || !Array.isArray(batch.drafts) || !Array.isArray(response.projects)
    || batch.generated_count !== batch.drafts.length || batch.drafts.length > batch.requested_count
    || response.projects.length !== batch.drafts.length)
    throw Error('Biên nhận Auto Shorts không khớp yêu cầu.');
  validateSceneSelectionLineage(batch.scene_evidence?.reviewed_local_scene_selection, page, request);
  const children = new Set();
  for (const draft of batch.drafts) {
    const project = response.projects.find(value => value.id === draft.project_id);
    if (!projectId.test(draft.project_id) || draft.project_id === page.project_id || children.has(draft.project_id)
      || !sha256.test(draft.timeline_sha256) || !Array.isArray(draft.source_window) || draft.source_window.length !== 2
      || !Number.isFinite(draft.source_window[0]) || !Number.isFinite(draft.source_window[1])
      || draft.source_window[0] < 0 || draft.source_window[1] <= draft.source_window[0]
      || !project || project.document?.canonical_timeline?.sha256 !== draft.timeline_sha256 || project.approval != null)
      throw Error('Bản Short phải có timeline riêng và chưa được duyệt.');
    validateSceneSelectionLineage(project.document.canonical_timeline.snapshot?.metadata?.highlight_draft?.reviewed_local_scene_selection, page, request);
    children.add(draft.project_id);
  }
  return response;
}

export function initializeSceneAssessments({api, getState, root=document, onMessage=()=>{}, onWorking=()=>{},
  onSaved=async()=>{}, onDraftsCreated=async()=>{}}) {
  const card = root.getElementById('native-scene-assessments-card');
  if (!card) throw Error('Thiếu vùng review đánh giá cảnh.');
  card.hidden = false;
  card.replaceChildren();
  const node = (tag, text, name) => {
    const element = root.createElement(tag);
    if (text) element.textContent = text;
    if (name) element.id = 'native-scene-assessments-'+name;
    return element;
  };
  const button = (text, name) => {
    const element = node('button', text, name);
    element.type = 'button'; element.className = 'secondary'; return element;
  };
  const read = button('Đọc bằng chứng cảnh đã lưu', 'read');
  const source = node('select', null, 'source');
  const freeze = button('Lưu đánh giá cảnh hiện tại', 'freeze');
  const freezeAck = node('input', null, 'freeze-ack'); freezeAck.type = 'checkbox';
  const freezeLabel = node('label', 'Tôi chọn dùng phân tích và transcript đang lưu, không chạy thêm provider.');
  freezeLabel.prepend(freezeAck);
  const assessmentChoice = node('select', null, 'assessment');
  const top = node('select', null, 'top');
  for (const count of [3,5]) { const option = node('option', 'Top '+count); option.value = String(count); top.append(option); }
  top.value = '3';
  const ratio = node('select', null, 'ratio');
  for (const value of ratios) { const option = node('option', value); option.value = value; ratio.append(option); }
  ratio.value = '9:16';
  const highlightChoice = node('select', null, 'highlight');
  const reviewed = node('input', null, 'reviewed'); reviewed.type = 'checkbox';
  const reviewedLabel = node('label', 'Tôi đã xem cảnh, điểm nổi bật và yếu tố thiếu dữ liệu; đồng ý dựng lựa chọn này.');
  reviewedLabel.prepend(reviewed);
  const apply = button('Dựng điểm nổi bật đã chọn', 'apply');
  const shorts = button('Tạo Auto Shorts chưa duyệt', 'shorts');
  const status = node('p', 'Đọc phân tích đã lưu trước. Chưa có đánh giá được áp dụng vào timeline.', 'status');
  const sceneRegion = node('div', null, 'scenes');
  const highlightRegion = node('div', null, 'highlights');
  const labeled = (text, element) => { const label = node('label', text); label.append(element); return label; };
  card.append(node('summary', 'Cảnh & điểm nổi bật từ bằng chứng hiện tại'),
    node('p', 'Điểm số là gợi ý từ dữ liệu đã lưu. Vision ngữ nghĩa chưa cấu hình; dữ liệu thiếu không được suy đoán. '
      +'Lưu đánh giá không duyệt video. Mỗi lần dựng cần lựa chọn riêng.'), read, labeled('Nguồn phân tích', source), freezeLabel, freeze,
    labeled('Bản đánh giá', assessmentChoice), status, sceneRegion, labeled('Số gợi ý', top), highlightRegion,
    labeled('Điểm nổi bật sẽ dựng', highlightChoice), labeled('Định dạng', ratio), reviewedLabel, apply, shorts);
  let working = false, generation = 0, scope = '', page = null, selectedSource = null, selected = null, pendingShorts = null;
  const context = () => {
    const state = getState();
    return JSON.stringify([state.workspace_id, state.project?.id, state.project?.revision, state.canEdit,
      state.active, state.archived, state.project?.archived, state.dirty]);
  };
  function mayEdit(state) {
    return state.canEdit && !state.dirty && !state.active && !state.archived && !state.project?.archived;
  }
  function controls() {
    const state = getState(), blocked = working || state.busy;
    const edit = !blocked && mayEdit(state);
    read.disabled = blocked || !state.project || state.dirty;
    source.disabled = blocked || !page;
    freezeAck.disabled = !edit || !selectedSource;
    freeze.disabled = !edit || !selectedSource || !freezeAck.checked;
    assessmentChoice.disabled = blocked || !page;
    top.disabled = blocked || !selected;
    ratio.disabled = !edit || !selected?.current;
    highlightChoice.disabled = !edit || !selected?.current;
    reviewed.disabled = !edit || !selected?.current;
    apply.disabled = !edit || !selected?.current || !reviewed.checked || !highlightChoice.value;
    shorts.disabled = !edit || !selected?.current || !reviewed.checked || !selected.assessment.result.scene_ranking.length;
  }
  function clear() {
    page = null; selectedSource = null; selected = null; pendingShorts = null;
    for (const element of [source, assessmentChoice, highlightChoice, sceneRegion, highlightRegion]) element.replaceChildren();
    freezeAck.checked = false; reviewed.checked = false;
    status.textContent = 'Nguồn hoặc phiên bản đã thay đổi. Đọc lại bằng chứng đã lưu.';
  }
  function sync() {
    const current = context();
    if (scope !== current) { scope = current; generation++; clear(); }
    controls();
  }
  function renderAssessment() {
    selected = page?.items.find(item => item.assessment.assessment_id === assessmentChoice.value) ?? null;
    sceneRegion.replaceChildren(); highlightRegion.replaceChildren(); highlightChoice.replaceChildren(); reviewed.checked = false;
    pendingShorts = null;
    if (!selected) { status.textContent = 'Chưa có đánh giá lưu cho nguồn đã chọn.'; controls(); return; }
    const assessment = selected.assessment;
    status.textContent = `Bản ${assessment.version} · ${selected.current ? 'hiện tại' : 'cũ, chỉ xem lịch sử'} · `
      +`${assessment.result.scenes.length} cảnh · độ tin cậy chưa được hiệu chuẩn · Vision: chưa cấu hình.`;
    for (const scene of assessment.result.scenes) {
      const section = node('section');
      section.append(node('strong', `${scene.start_seconds.toFixed(2)}–${scene.end_seconds.toFixed(2)}s · ${scene.semantic_label}`),
        node('p', scene.description || 'Chưa có mô tả từ transcript.'),
        node('p', `Độ tin cậy nguồn: ${formatted(scene.confidence)}${scene.needs_attention ? ' · Cần kiểm tra' : ''}`));
      const evidence = node('details');
      evidence.append(node('summary', 'Cơ sở đánh giá cảnh'));
      for (const [key, label] of [['quality_basis','Chất lượng'], ['motion_basis','Chuyển động'], ['confidence_basis','Độ tin cậy']]) {
        evidence.append(node('p', `${label}: ${typeof scene.evidence[key] === 'string' ? scene.evidence[key] : 'Chưa có dữ liệu'}`));
      }
      section.append(evidence);
      sceneRegion.append(section);
    }
    for (const highlight of assessment.result.scene_ranking) {
      const option = node('option', `${highlight.recommended_start.toFixed(2)}–${highlight.recommended_end.toFixed(2)}s · ${formatted(highlight.highlight_score)}`);
      option.value = highlight.highlight_id; highlightChoice.append(option);
    }
    highlightChoice.value = assessment.result.scene_ranking[0]?.highlight_id ?? '';
    renderHighlights(); controls();
  }
  function renderHighlights() {
    highlightRegion.replaceChildren();
    for (const highlight of selected?.assessment.result.scene_ranking.slice(0, Number(top.value)) ?? []) {
      const section = node('section');
      section.append(node('strong', `${highlight.recommended_start.toFixed(2)}–${highlight.recommended_end.toFixed(2)}s · Điểm ${formatted(highlight.highlight_score)}`),
        node('p', highlightReasonSummary(highlight.reason)), node('p', `Nền tảng gợi ý: ${highlight.recommended_platform} · Độ tin cậy nguồn: ${formatted(highlight.evidence.confidence)}`));
      const explanation = node('details');
      explanation.append(node('summary', 'Giải thích gốc từ bằng chứng đã lưu'), node('p', highlight.reason));
      section.append(explanation);
      for (const [key, value] of Object.entries(highlight.evidence.factors)) {
        section.append(node('p', `${factorLabels[key] ?? key}: ${formatted(value)} · Đóng góp: ${formatted(highlight.evidence.contributions[key])}`));
      }
      section.append(node('p', 'Thiếu dữ liệu: '+(highlight.evidence.missing_factors.map(key => factorLabels[key] ?? key).join(', ') || 'không có')));
      highlightRegion.append(section);
    }
  }
  function selectSource() {
    selectedSource = page?.available_sources.find(item => item.analysis_id === source.value) ?? null;
    freezeAck.checked = false; assessmentChoice.replaceChildren();
    const matches = page?.items.filter(item => item.assessment.input_refs.analysis_id === source.value) ?? [];
    for (const item of matches) {
      const option = node('option', `Bản ${item.assessment.version} · ${item.current ? 'hiện tại' : 'cũ'}`);
      option.value = item.assessment.assessment_id; assessmentChoice.append(option);
    }
    assessmentChoice.value = (matches.findLast(item => item.current) ?? matches.at(-1))?.assessment.assessment_id ?? '';
    renderAssessment();
  }
  function install(value, desiredSource) {
    page = value; source.replaceChildren();
    const choices = new Map(value.available_sources.map(item => [item.analysis_id, item.filename]));
    for (const item of value.items) {
      const analysis = item.assessment.input_refs.analysis_id;
      if (!choices.has(analysis)) choices.set(analysis, `Nguồn cũ · đánh giá bản ${item.assessment.version}`);
    }
    for (const [analysis, filename] of choices) { const option = node('option', filename); option.value = analysis; source.append(option); }
    source.value = choices.has(desiredSource) ? desiredSource : choices.keys().next().value ?? '';
    selectSource();
  }
  async function run(operation) {
    sync(); const state = getState();
    if (working || state.busy || !state.project) return;
    const expected = context(), ticket = ++generation;
    working = true; onWorking(true); controls();
    const accept = () => expected === context() && ticket === generation;
    try { await operation(state, accept); }
    catch (error) { if (accept()) onMessage(error.message, true); }
    finally { working = false; onWorking(false); sync(); }
  }
  async function load() {
    await run(async (state, accept) => {
      if (state.dirty) throw Error('Lưu hoặc hủy bản sửa đang mở trước khi đọc lại.');
      const response = await api(`/api/projects/${state.project.id}/auto-edit/scene-assessments`);
      if (accept()) install(validateSceneAssessments(response, state));
    });
  }
  async function freezeCurrent() {
    await run(async (state, accept) => {
      if (!mayEdit(state) || !page || !selectedSource) throw Error('Dự án hiện không cho phép lưu đánh giá.');
      const before = page, chosen = selectedSource;
      const body = sceneAssessmentPayload(before, chosen, freezeAck.checked);
      const response = await api(`/api/projects/${state.project.id}/auto-edit/scene-assessments`, body);
      if (!accept()) return;
      validateSceneAssessmentSave(response, state, before, chosen);
      await onSaved(response);
      if (getState().project?.id !== response.project_id || getState().workspace_id !== response.workspace_id) return;
      if (getState().project?.revision === response.revision) { scope = context(); install(response, chosen.analysis_id); }
      onMessage('Đã lưu đánh giá từ bằng chứng hiện tại. Kiểm tra các cảnh rồi chọn cách dựng; video chưa được duyệt.');
    });
  }
  async function applyHighlight() {
    await run(async (state, accept) => {
      if (!mayEdit(state) || !page) throw Error('Dự án hiện không cho phép dựng lựa chọn.');
      const before = page;
      const body = reviewedHighlightPayload(before, selected, {aspectRatio:ratio.value, selectedHighlightId:highlightChoice.value, acknowledged:reviewed.checked});
      const response = await api(`/api/projects/${state.project.id}/auto-edit/timeline`, body);
      if (!accept()) return;
      validateReviewedTimeline(response, before, body);
      reviewed.checked = false; await onSaved(response);
      onMessage('Đã tạo bản timeline từ điểm nổi bật đã review. Kiểm tra shot, crop và preview trước khi duyệt.');
    });
  }
  async function createShorts() {
    await run(async (state, accept) => {
      if (!mayEdit(state) || !page) throw Error('Dự án hiện không cho phép tạo Auto Shorts.');
      const before = page;
      const selection = reviewedHighlightPayload(before, selected, {aspectRatio:ratio.value, acknowledged:reviewed.checked});
      const key = JSON.stringify([before.project_id, before.revision, selection.payload, Number(top.value)]);
      if (pendingShorts?.key !== key) pendingShorts = {key, body:reviewedShortsPayload(before, selected, {
        aspectRatio:ratio.value, acknowledged:true, count:Number(top.value), requestKey:globalThis.crypto.randomUUID().replaceAll('-','')})};
      const response = await api(`/api/projects/${state.project.id}/auto-edit/shorts`, pendingShorts.body);
      if (!accept()) return;
      validateReviewedShorts(response, before, pendingShorts.body);
      pendingShorts = null; reviewed.checked = false; await onDraftsCreated(response);
      onMessage(`Đã tạo ${response.batch.generated_count}/${response.batch.requested_count} bản Short phù hợp, chưa duyệt. Mở từng bản để kiểm tra.`);
    });
  }
  read.addEventListener('click', load); freeze.addEventListener('click', freezeCurrent);
  apply.addEventListener('click', applyHighlight); shorts.addEventListener('click', createShorts);
  source.addEventListener('change', selectSource); assessmentChoice.addEventListener('change', renderAssessment);
  top.addEventListener('change', () => { reviewed.checked = false; pendingShorts = null; renderHighlights(); controls(); });
  for (const element of [ratio, highlightChoice]) element.addEventListener('change', () => { reviewed.checked = false; pendingShorts = null; controls(); });
  for (const element of [freezeAck, reviewed]) element.addEventListener('change', controls);
  sync();
  return {load, freeze:freezeCurrent, apply:applyHighlight, createShorts, sync, controls, isWorking:()=>working,
    currentBinding:()=>({page, source:selectedSource, assessment:selected})};
}
