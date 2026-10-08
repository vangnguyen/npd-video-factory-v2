export const supportsNativeCosts = session => session?.capabilities?.native_cost_ledger===true;
export async function loadNativeCosts(session,loader=()=>import('./native-costs.mjs')) {
  return supportsNativeCosts(session)?await loader():null;
}
export const supportsShotStudio = session => session?.capabilities?.native_shot_studio===true || session?.native_shot_studio===true;
export const isSourceProject=p=>p?.document?.canonical_timeline?.snapshot?.metadata?.native_auto_edit_schema==='native-auto-edit-timeline-v1';
export const newProjectQuality = session => session?.capabilities?.north_star_quality===true ? {production_quality:true} : {};
export async function loadNativeShotStudio(session,loader=()=>import('./shot-studio.mjs')) {
  return supportsShotStudio(session)?await loader():null;
}
export function nativeLegacyLayout(dom) {
  dom.body.classList.remove('shot-studio');
  dom.querySelector('link[href="/shot-studio.css"]')?.remove();
  dom.querySelectorAll('[data-stage-panel],.stage-navigation,.studio-header-actions,.skip-link,.sidebar [data-stage],.sidebar a[href^="/production"]').forEach(el=>el.hidden=true);
  const workspace=dom.querySelector('.workspace');if(workspace)workspace.hidden=false;
  const timing=dom.getElementById('preview-timing-note');if(timing)timing.textContent='Giọng Thùy Dung đã khóa. Phụ đề theo đoạn, dựa trên thời lượng audio đo được.';
}

export const jobActive = project => project?.jobs?.some(j => ["queued", "running", "retrying"].includes(j.status)) ?? false;
export const currentVideo = project => project?.approval && !project.archived ? project.jobs.find(j => j.kind === "render" && j.status === "succeeded" && j.revision === project.revision) : null;
export const canRender = (project, dirty, busy) => Boolean(project?.approval && !project.archived && project.approval.revision === project.revision && !dirty && !busy && !jobActive(project));
export const mediaLibrary = doc => (doc?.assets ?? (doc?.asset ? [doc.asset] : [])).map(a=>({...a,kind:a.kind??"image",filename:a.filename??"Ảnh đã lưu"}));
export const mediaBindings = doc => doc?.scene_media ?? (doc?.asset ? (doc.proposal?.visual_brief??[]).map(s=>({scene:s.scene,asset_id:doc.asset.id})) : []);
export const mediaReady = doc => {
  const scenes=doc?.proposal?.visual_brief??[],assets=mediaLibrary(doc),bindings=mediaBindings(doc);
  return scenes.length>0 && bindings.length===scenes.length && scenes.every(s=>bindings.filter(b=>b.scene===s.scene).length===1 && assets.some(a=>a.id===bindings.find(b=>b.scene===s.scene)?.asset_id));
};
export const mediaType = file => ({jpg:"image/jpeg",jpeg:"image/jpeg",png:"image/png",mp4:"video/mp4",mov:"video/quicktime"})[file.name.split(".").pop().toLowerCase()] ?? "";
export const documentType = file => ({txt:"text/plain",md:"text/markdown",docx:"application/vnd.openxmlformats-officedocument.wordprocessingml.document"})[file.name.split(".").pop().toLowerCase()] ?? "";
export const mediaAnalysisPending = doc => mediaLibrary(doc).some(a=>!(doc?.media_analysis??[]).some(r=>r.asset_id===a.id&&r.source_sha256===a.sha256));
export const musicType = file => ({wav:"audio/wav",mp3:"audio/mpeg"})[file.name.split(".").pop().toLowerCase()] ?? "";
export const defaultSceneOptions = (scene, asset, plan) => ({scene,crop_strategy:plan?.crop_strategy??"contain",motion:asset?.kind==="video"?"none":plan?.motion??"none",source_start:asset?.kind==="video"?plan?.source_start??0:0,transition:plan?.transition??"cut"});
export const finalApproved = job => Boolean(job?.final_review?.decision==="approve"&&job.final_review.revision===job.revision&&job.final_review.artifact_sha256===job.result?.qc?.final_sha256);
export const musicSummary = project => project?.document.music ? `${project.document.music.filename} · ${project.document.music.duration_seconds.toFixed(1)} giây · ${isSourceProject(project)?`track nhạc trong timeline; chỉnh âm lượng, điểm cắt hoặc tắt âm tại Advanced Timeline${project.document.canonical_timeline.snapshot.metadata.source_audio_processing?.duck_music?'; đã bật ducking theo năng lượng nguồn, nghe preview để kiểm tra':''}`:'tự hạ nhạc khi có lời đọc'}` : 'Chưa có nhạc nền.';
export const scriptReviewLabel = project => !project?.document?.content_intelligence ? "" : project?.script_review?.current ? (project.approval ? "Lời đọc đã được duyệt." : "Lời đọc đã lưu được duyệt. Hình ảnh và cách dựng còn chờ bạn duyệt.") : project?.script_review ? "Lời đọc đã thay đổi; cần duyệt lại bản mới." : "Lời đọc đang chờ bạn duyệt.";

const errors = {
  AI_COST_APPROVAL_REQUIRED_BEFORE_DISPATCH:'Ước tính chưa rõ hoặc vượt giới hạn chi phí AI. Kiểm tra ngân sách và nhà cung cấp trước khi tạo yêu cầu mới.',
  COST_AMOUNT_INVALID:'Nhập số tiền không âm, tối đa 1.000 tỷ đồng và không quá 6 chữ số thập phân.',
  COST_OPERATION_ALREADY_DISPATCHED_NO_REPLAY:'Yêu cầu đã được ghi nhận. Kiểm tra kết quả trước khi tạo yêu cầu mới.',
  AUTO_EDIT_HUMAN_APPROVAL_REQUIRED_BEFORE_RENDER:'Xem preview hiện tại và duyệt bản dựng nguồn trước khi render.',
  AUTO_EDIT_CURRENT_PREVIEW_REVIEW_REQUIRED:'Preview chưa có hoặc đã thay đổi. Tạo và xem preview mới trước khi duyệt.',
  AUTO_EDIT_TIMELINE_VERSION_CHANGED:'Bản timeline đã thay đổi. Làm mới để lấy bản đang lưu.',
  AUTO_EDIT_LINKED_TRACK_LOCKED:'Một track hình, âm thanh hoặc phụ đề đang khóa. Mở khóa trước khi sửa shot nguồn.',
  AUTO_EDIT_MUSIC_TRACK_LOCKED:'Track nhạc đang khóa. Mở khóa trong Advanced Timeline trước khi thay nhạc.',
  AUTO_EDIT_AUDIO_TRACK_LOCKED:'Một track âm thanh đang khóa. Mở khóa trong Advanced Timeline trước khi đổi xử lý âm thanh.',
  AUTO_EDIT_LINKED_AUDIO_DIVERGED:'Âm thanh đã được chỉnh riêng. Giữ các chỉnh sửa đó hoặc khôi phục bản đồng bộ từ lịch sử trước khi sửa shot liên kết.',
  AUTO_EDIT_SPLIT_TOUCHES_SPOKEN_WORD:'Điểm tách đang nằm trong một từ đang nói. Chọn mốc giữa các từ.',
  AUTO_EDIT_LAST_SOURCE_CLIP_REQUIRED:'Bản dựng cần giữ ít nhất một clip nguồn.',
  AUTO_EDIT_TIMELINE_SOURCE_WINDOW_INVALID:'Điểm bắt đầu và kết thúc phải nằm trong thời lượng video nguồn.',
  AUTO_EDIT_MEDIA_QC_FAILED:'Video chưa vượt qua kiểm tra chất lượng. Kiểm tra báo cáo và sửa bản dựng trước khi render lại.',
  WORD_ALIGNMENT_UNAVAILABLE:'Đoạn lời nói không có căn chỉnh từng từ phù hợp. Chọn phụ đề theo câu.',
  TTS_PROPER_NAME_REVIEW_REQUIRED:"Tên riêng cần dùng cách viết chuẩn trong lời đọc. Sửa và duyệt lại trước khi tạo giọng.",
  PRODUCTION_QUALITY_POLICY_CHANGED_REVIEW_REQUIRED:"Quy tắc chất lượng đã thay đổi. Kiểm tra và duyệt lại phiên bản dự án.",
  NARRATION_DEAD_AIR_REVIEW_DURATION_REQUIRED:"Khoảng trống lời đọc quá dài. Chọn Khớp với lời đọc hoặc rút ngắn thời lượng cảnh rồi duyệt lại.",
  RENDER_PROFILE_CANVAS_MISMATCH:"Kích thước mẫu không khớp định dạng video đã chọn.",
  RENDER_PROFILE_UNKNOWN:"Định dạng render chưa được hỗ trợ.",
  HUMAN_APPROVAL_REQUIRED_BEFORE_TTS:"Cần duyệt đúng phiên bản nội dung trước khi tạo giọng đọc.",
  STALE_VERSION_RELOAD:"Phiên bản đã thay đổi. Làm mới để lấy bản mới nhất.",
  PROJECT_BUSY:"Dự án đang có job chạy. Chờ job hoàn tất trước khi sửa.",
  CONTENT_AND_IMAGE_REQUIRED:"Cần có đề xuất nội dung và ảnh trước khi duyệt.",
  HUMAN_REVIEW_REQUIRED:"Nhập tên người duyệt và xác nhận đã kiểm tra nội dung.",
  INTERRUPTED_NO_AUTOMATIC_REPLAY:"Job bị ngắt. Chưa tự chạy lại; kết quả bước đã gọi có thể chưa rõ.",
  INVALID_PROPOSAL_SCENE_COVERAGE:"Lời đọc các cảnh phải phủ đầy đủ nội dung, theo thứ tự.",
  IMAGE_RIGHTS_CONFIRMATION_REQUIRED:"Xác nhận quyền dùng ảnh trước khi lưu.",
  INVALID_IMAGE_JPEG_PNG_MAX_15MB_40MP_MIN_240PX:"Ảnh phải là JPEG/PNG, tối đa 15 MB, 40 megapixel và mỗi chiều từ 240 px.",
  EACH_SCENE_REQUIRES_ONE_IMAGE_OR_VIDEO:"Chọn một ảnh hoặc video cho mỗi cảnh rồi lưu trước khi duyệt.",
  SCENE_MEDIA_NOT_IN_PROJECT:"Nguồn đã chọn không thuộc thư viện dự án này.",
  INVALID_SCENE_MEDIA:"Mỗi cảnh chỉ được chọn một nguồn trong thư viện.",
  MEDIA_RIGHTS_CONFIRMATION_REQUIRED:"Xác nhận quyền sử dụng các ảnh/video đã chọn.",
  MEDIA_LIBRARY_LIMIT_50:"Mỗi dự án lưu tối đa 50 nguồn.",
  PROJECT_MEDIA_LIMIT_50:"Mỗi dự án lưu tối đa 50 nguồn.",
  MEDIA_FILE_TOO_LARGE_OR_TYPE_UNSUPPORTED:"Chọn ảnh JPEG/PNG ≤ 15 MB hoặc video MP4/MOV ≤ 250 MB.",
  MEDIA_FILE_TOO_LARGE_OR_EMPTY:"Ảnh tối đa 15 MB, video tối đa 250 MB; tệp phải có nội dung.",
  MEDIA_TYPE_NOT_SUPPORTED:"Chọn ảnh JPEG/PNG hoặc video MP4/MOV.",
  INVALID_VIDEO_MP4_MOV:"Video MP4/MOV không hợp lệ hoặc không đọc được.",
  VIDEO_LIMIT_10_MINUTES_40MP:"Video tối đa 10 phút và 40 megapixel, mỗi chiều từ 64 px.",
  VIDEO_DECODE_FAILED:"Video có lỗi khi đọc. Hãy chọn bản video khác.",
  SOURCE_MEDIA_CHANGED_OR_MISSING:"Ảnh/video đã chọn bị thay đổi hoặc mất. Cần lưu lại nguồn và duyệt lại.",
  MEDIA_VALIDATION_TIMEOUT:"Kiểm tra nguồn mất quá lâu. Hãy chọn tệp nhỏ hơn.",
  FFMPEG_SCENE_RENDER_FAILED:"Không render được một cảnh. Job đã dừng.",
  LOCAL_SESSION_REQUIRED:"Phiên làm việc đã hết hạn. Tải lại trang để tiếp tục.",
  OPENAI_TIMEOUT_OUTCOME_UNKNOWN_NO_RETRY:"OpenAI hết thời gian chờ. Không tự gọi lại; lần gọi trước có thể đã xử lý.",
  AuthenticationError:"Key OpenAI bị từ chối.", RateLimitError:"OpenAI từ chối do giới hạn sử dụng. Job đã dừng.",
  TTS_CHILD_FAILED:"Tạo giọng đọc thất bại. Job đã dừng.", MEDIA_QC_FAILED:"Video chưa vượt qua kiểm tra chất lượng.",
  ASR_PROVIDER_UNAVAILABLE_NO_TRANSCRIPT:"Phân tích video có lời nói trước khi tạo nội dung. Nếu chưa kết nối, mở Kết nối AssemblyAI. Chưa có transcript để dùng.",
  ASR_NO_UNANALYZED_MEDIA:"Các nguồn đã được phân tích hoặc chưa có nguồn để phân tích.",
  ASR_EXISTING_JOB_RESUME_REQUIRED:"Nguồn này đã có job nhận diện. Dùng Tiếp tục từ bước đã lưu; không tạo yêu cầu nhận diện trùng.",
  ASR_OUTCOME_UNKNOWN_NO_REPLAY:"Yêu cầu AssemblyAI chưa rõ kết quả. Hệ thống dừng để tránh tính phí lần nữa; cần kiểm tra job trong tài khoản.",
  EDITOR_VIDEO_TRIM_OR_MOTION_INVALID:"Thời điểm bắt đầu phải nằm trong video. Chuyển động pan/zoom chỉ dùng cho ảnh.",
  EDITOR_OPTIONS_INVALID:"Kiểm tra cách cắt khung, chuyển động và thời điểm của từng cảnh.",
  EDITOR_PLAN_CHANGED_OR_STALE:"Kế hoạch cảnh đã thay đổi. Lưu và duyệt lại trước khi tạo video.",
  MUSIC_RIGHTS_TYPE_SIZE_REQUIRED_MAX_25MB:"Xác nhận quyền dùng nhạc WAV/MP3, tối đa 25 MB.",
  MUSIC_AUDIO_INVALID_WAV_MP3_MAX_10_MINUTES:"Chọn bản nhạc WAV/MP3 hợp lệ, tối đa 10 phút.",
  MUSIC_ARTIFACT_CHANGED_OR_RIGHTS_MISSING:"Bản nhạc bị thay đổi hoặc thiếu quyền sử dụng. Lưu và duyệt lại.",
  PROJECT_ARCHIVED_RESTORE_FIRST:"Khôi phục dự án từ lưu trữ trước khi sửa hoặc tạo video.",
  HUMAN_FINAL_WATCH_LISTEN_REVIEW_REQUIRED:"Nhập người duyệt và xác nhận đã xem, nghe đúng video trước khi duyệt bản cuối.",
  FINAL_REVIEW_DECISION_REASON_INVALID:"Nhập lý do trả video để sửa (tối đa 2.000 ký tự).",
  REJECTION_NAME_REASON_REQUIRED:"Nhập tên người duyệt và lý do yêu cầu sửa.",
  HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED:"Video này cần được xem, nghe và duyệt làm bản cuối.",
  BRAND_TEMPLATE_CHOICE_REQUIRED:"Chọn thương hiệu và mẫu 30/45/60 giây trước khi áp dụng.",
  BRAND_TEMPLATE_SNAPSHOT_CHANGED_OR_INVALID:"Cấu hình thương hiệu/mẫu đã thay đổi. Áp dụng, lưu và duyệt lại.",
  BRANDED_RENDER_SCENE_PLAN_REQUIRED:"Đề xuất hoặc lưu cách dựng từng cảnh trước khi duyệt mẫu thương hiệu.",
  TEMPLATE_NARRATION_TOO_LONG_CHOOSE_LONGER_OR_EDIT:"Lời đọc dài hơn mẫu đã chọn. Chọn mẫu dài hơn hoặc rút gọn kịch bản; hệ thống giữ nguyên tốc độ giọng.",
  BRAND_HEADING_EXCEEDS_SAFE_AREA:"Tiêu đề vượt vùng chữ an toàn. Rút ngắn chữ trên cảnh này và duyệt lại.",
};
const statusNames = {queued:"Đang chờ",running:"Đang chạy",retrying:"Đang thử lại có giới hạn",awaiting_review:"Đề xuất sẵn sàng · cần bạn duyệt",succeeded:"Video đã render · hãy xem lại",failed:"Job đã dừng do lỗi",failed_qc:"Video chưa đạt kiểm tra chất lượng",interrupted:"Job bị ngắt · chưa chạy lại"};
const stageNames = {media_frame_local_pixel_sampling:"Đang lấy mẫu và đo khung hình trên máy",source_timeline_audio_and_captions:"Đang dựng âm thanh gốc và phụ đề",source_private_remotion_render:"Đang render video nguồn",source_full_media_qc:"Đang kiểm tra video nguồn",resuming_verified_source_render:"Đang khôi phục bản dựng nguồn đã kiểm chứng",starting:"Bắt đầu",prepare_existing_script:"Đang chuẩn bị kịch bản đã nhập",content_request:"Đang tạo nội dung",checking_scene_media:"Đang kiểm tra nguồn từng cảnh",locked_thuy_dung_tts:"Đang tạo giọng Thùy Dung",ffmpeg_render_and_qc:"Đang render và kiểm tra video",asr_local_media_analysis:"Đang phân tích cảnh nguồn",asr_extract_audio:"Đang tách âm thanh",asr_upload:"Đang gửi âm thanh đến AssemblyAI",asr_create_transcript:"Đang nhận diện lời nói",asr_observe_known_transcript:"Đang chờ kết quả nhận diện",resuming_verified_asr:"Đang khôi phục kết quả đã lưu",auto_edit_local_measurements:"Đang đo cảnh và âm thanh trên máy",resuming_verified_auto_edit_analysis:"Đang khôi phục kết quả dựng nguồn đã đo"};

if (typeof document !== "undefined") {
  nativeLegacyLayout(document);
  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
  let project = null, csrf = null, busy = false, dirty = false, dirtyPart = null, timer = null, pollFailures = 0, shotStudio = null, nativeAnalysis=null, mediaFrames=null, workspaceUI=null,brandCatalog=null,projectQuality={};
  let costRequest = 0, costUI = null, canManage = true, publicationUI = null, analyticsUI = null, visionUI = null, variantsUI = null, channelUI=null,bridgeUI=null,rightsUI=null,stockUI=null,generationUI=null,rightsOverrideUI=null,mediaPlannerUI=null;
  async function refreshCosts() {
    if(!costUI||!$('cost-summary'))return;
    const serial=++costRequest, identifier=project?.id;
    if(!identifier){$('cost-summary').innerHTML=costUI.costSummaryHTML(null);return;}
    try {
      const value=await api(`/api/projects/${identifier}/cost-summary`);
      if(serial===costRequest && project?.id===identifier)$('cost-summary').innerHTML=costUI.costSummaryHTML(value);
    } catch {
      if(serial===costRequest && project?.id===identifier)$('cost-summary').textContent='Chưa tải được chi phí. Làm mới để kiểm tra; không giả định chi phí bằng 0.';
    }
  }
  function message(text, error=false) {$("message").textContent=text;$("message").hidden=false;$("message").classList.toggle("error",error);}
  async function api(path, body) {
    const response = await fetch(path,{method:body?"POST":"GET",credentials:"same-origin",headers:body?{"Content-Type":"application/json","X-VF-CSRF":csrf}:{},body:body?JSON.stringify(body):undefined});
    const result=await response.json();
    if(response.status===401 && result.code==='NATIVE_AUTH_SESSION_REQUIRED')location.assign('/login');
    if(response.status===403 && result.code==='NATIVE_AUTH_FORBIDDEN')throw new Error('Vai trò hiện tại không có quyền thực hiện thao tác này.');
    if(!response.ok)throw new Error(`${errors[result.code] ?? result.failure?.action ?? result.code} (HTTP ${response.status})`);
    return result;
  }
  function controls() {
    bridgeUI?.controls();
    $("prompt").closest('label').hidden=Boolean(workspaceUI)&&$("input-kind").value==='media';
    const active=jobActive(project), shotWorking=(shotStudio?.isWorking()??false)||(nativeAnalysis?.isWorking()??false)||(mediaFrames?.isWorking()??false)||(rightsUI?.isWorking()??false)||(stockUI?.isWorking()??false)||(generationUI?.isWorking()??false)||(rightsOverrideUI?.isWorking()??false)||(mediaPlannerUI?.isWorking()??false), blocked=busy||shotWorking||active||project?.archived;
    document.querySelectorAll("input,textarea,select,button").forEach(el=>{if(!el.matches('[data-shot-control],[data-script-control],[data-asset-control],[data-workspace-control],[data-auto-edit-control],[data-studio-nav],[data-shot],[data-storyboard-shot],[data-track-shot]'))el.disabled=blocked;});
    $("refresh").disabled=busy||shotWorking;
    $("project-picker").disabled=busy||shotWorking||dirty;
    $("new-project").disabled=busy||shotWorking||dirty;
    $("show-archived").disabled=busy||shotWorking||dirty;
    $("duplicate-project").disabled=!project||blocked||dirty;
    $("archive-project").disabled=!project||busy||shotWorking||active||dirty;
    $("archive-project").textContent=project?.archived?"Khôi phục":"Lưu trữ";
    $("load-history").disabled=!project||busy;
    $("apply-brand").disabled=!project||blocked||dirty;
    if($('save-cost-policy'))$('save-cost-policy').disabled=!costUI||!project||blocked||(dirty&&dirtyPart!=='cost');
    if($('max-ai-cost'))$('max-ai-cost').disabled=!costUI||!project||blocked||(dirty&&dirtyPart!=='cost');
    $("brand-select").disabled=!project||blocked||dirty;
    $("template-select").disabled=!project||blocked||dirty;
    $("project-name").disabled=Boolean(project)||busy;
    $("generate").disabled=!project||blocked||dirty;
    $("generate").textContent=project?.document.input_kind==="script"||project?.input?.metadata.workflow==="REVIEW_TRANSCRIPT"?"Chuẩn bị kịch bản để bạn duyệt":"Tạo đề xuất nội dung ↗";
    $("upload-documents").disabled=!project||blocked||dirty;
    $("approve").disabled=!(isSourceProject(project)?shotStudio?.sourceReady():mediaReady(project?.document))||blocked||dirty||Boolean(project.approval);
    $("upload-media").disabled=!project||blocked||dirty;
    $("analyze-media").disabled=!project||blocked||dirty||!mediaAnalysisPending(project.document);
    $("auto-plan").disabled=!project?.document.proposal||!mediaLibrary(project?.document).length||blocked||dirty;
    $("upload-music").disabled=!project||blocked||dirty;
    $("music-enabled").disabled=!project?.document.music||!project.document.proposal||blocked||dirtyPart==="prompt";
    document.querySelectorAll(".scene").forEach(row=>{const asset=mediaLibrary(project?.document).find(a=>a.id===row.querySelector("[data-media]").value);row.querySelector("[data-start]").disabled=blocked||dirtyPart==="prompt"||asset?.kind!=="video";row.querySelector("[data-motion]").disabled=blocked||dirtyPart==="prompt"||asset?.kind!=="image";});
    document.querySelectorAll(".scene").forEach(row=>{row.querySelector('[data-move="-1"]').disabled=blocked||dirtyPart==="prompt"||!row.previousElementSibling;row.querySelector('[data-move="1"]').disabled=blocked||dirtyPart==="prompt"||!row.nextElementSibling;});
    $("render").disabled=!canRender(project,dirty,busy||shotWorking);
    if(project?.archived)$("render").disabled=true;
    $("reject-content").disabled=!project?.document.proposal||blocked||dirty;
    const video=currentVideo(project);
    $("approve-final").disabled=!video||finalApproved(video)||blocked||dirty||(Boolean(workspaceUI)&&(!$("final-watch").checked||!$("final-reviewer").value.trim()));
    $("reject-final").disabled=!video||blocked||dirty||(Boolean(workspaceUI)&&!$("final-reviewer").value.trim());
    $("load-artifacts").disabled=!video||busy;
    $("open-output").disabled=!video||busy||project?.archived;
    $("save-prompt").textContent=project?"Lưu yêu cầu":"Tạo dự án";
    $("save-proposal").disabled=!project?.document.proposal||blocked;
    if(dirtyPart==="proposal"){$("prompt").disabled=true;$("save-prompt").disabled=true;}
    if(dirtyPart==="prompt"){$("scenes").querySelectorAll("input,textarea,select").forEach(el=>el.disabled=true);$("save-proposal").disabled=true;}
    if(dirtyPart==="shot"){
      document.querySelectorAll('#brief-card input,#brief-card textarea,#brief-card select,#brief-card button,#proposal-card input,#proposal-card textarea,#proposal-card select,#proposal-card button,#image-card input,#image-card select,#image-card button').forEach(el=>el.disabled=true);
    }
    if(isSourceProject(project))for(const id of ['generate','apply-brand','brand-select','template-select','music-enabled','save-prompt','input-kind','prompt','upload-documents'])$(id).disabled=true;
    $("save-note").textContent=dirty?"Có chỉnh sửa chưa lưu. Lưu trước khi tạo nội dung hoặc duyệt.":project?.approval?`Đã duyệt bởi ${project.approval.reviewer}.`:project?"Mọi thay đổi được lưu sẽ cần duyệt lại.":"Lưu yêu cầu trước khi tạo đề xuất.";
    shotStudio?.controls();
    nativeAnalysis?.controls();
    mediaFrames?.controls();
    publicationUI?.controls();
    analyticsUI?.controls();
    visionUI?.controls();
    rightsUI?.controls();
    stockUI?.controls();
    generationUI?.controls();
    mediaPlannerUI?.controls();
    rightsOverrideUI?.controls();
    variantsUI?.controls();
    channelUI?.controls();
  }
  function markDirty(part) {dirty=true;dirtyPart=part;$("review-check").checked=false;controls();}
  function readProposal() {
    const old=project.document.proposal;
    const scenes=[...document.querySelectorAll(".scene")].map((row,i)=>({scene:i+1,visual:row.querySelector("[data-visual]").value,on_screen_text:row.querySelector("[data-title]").value,narration_excerpt:row.querySelector("[data-narration]").value}));
    return {...old,visual_brief:scenes,narration:scenes.map(s=>s.narration_excerpt.trim()).join(" ")};
  }
  function readBindings() {
    return [...document.querySelectorAll(".scene")].flatMap((row,i)=>row.querySelector("[data-media]").value?[{scene:i+1,asset_id:row.querySelector("[data-media]").value}]:[]);
  }
  function readOptions() {return [...document.querySelectorAll(".scene")].map((row,i)=>({scene:i+1,crop_strategy:row.querySelector("[data-crop]").value,motion:row.querySelector("[data-motion]").value,source_start:Number(row.querySelector("[data-start]").value),transition:row.querySelector("[data-transition]").value}));}
  function editorControls(scene) {
    const asset=mediaLibrary(project.document).find(a=>a.id===mediaBindings(project.document).find(b=>b.scene===scene.scene)?.asset_id);
    const plan=project.document.edit_plan?.scenes.find(s=>s.scene===scene.scene);
    const option=defaultSceneOptions(scene.scene,asset,plan);
    const select=(attribute,label,choices,value)=>`<label>${label}<select ${attribute}>${choices.map(([v,t])=>`<option value="${v}" ${v===value?"selected":""}>${t}</option>`).join("")}</select></label>`;
    return `<details class="scene-edit"><summary>Cách dựng cảnh</summary><div class="scene-grid">${select("data-crop","Khung hình",[["contain","Giữ toàn ảnh/video"],["cover","Lấp đầy khung hình"]],option.crop_strategy)}${select("data-motion","Chuyển động ảnh",[["none","Giữ yên"],["zoom_in","Zoom chậm"],["pan_left","Pan sang trái"],["pan_right","Pan sang phải"]],option.motion)}<label>Video bắt đầu từ giây<input data-start type="number" min="0" step="0.01" max="${asset?.duration_seconds??600}" value="${option.source_start}"></label>${select("data-transition","Chuyển cảnh",[["cut","Cắt thẳng"],["fade","Mờ nhẹ"]],option.transition)}</div><p class="hint">Video ngắn sẽ lặp sau lượt phát đầu. Thời lượng cảnh chốt theo giọng đọc; phụ đề theo đoạn. Chữ chừa khoảng cho giao diện mạng xã hội, cần xem lại trên nền tảng.</p>${plan?`<p class="hint">${plan.asset_candidates.find(c=>c.asset_id===plan.selected_asset)?.reason==="transcript_token_overlap"?"Nguồn được gợi ý theo lời nói nhận diện.":"Nguồn được gợi ý theo thứ tự thư viện; cần kiểm tra hình."}</p>`:""}</details>`;
  }
  const thumbnail = asset => `/api/projects/${project.id}/media/${asset.id}/thumbnail`;
  const sourceLabel = asset => `${asset.kind==="video"?"Video":"Ảnh"} · ${asset.filename}${asset.kind==="video"?` · ${Number(asset.duration_seconds).toFixed(1)} giây`:""}`;
  function scenePreview(row) {
    const asset=mediaLibrary(project.document).find(a=>a.id===row.querySelector("[data-media]").value);
    const img=row.querySelector("[data-preview]");img.hidden=!asset;
    if(asset){img.src=thumbnail(asset);img.alt=asset.filename;}else img.removeAttribute("src");
    const fit=row.querySelector("[data-crop]")?.value==="cover"?"Lấp đầy khung hình":"Giữ toàn ảnh/video";
    row.querySelector("[data-media-note]").textContent=asset?.kind==="video"?`${fit} · tắt âm thanh gốc · clip ngắn lặp sau lượt phát đầu.`:asset?`${fit} · kiểm tra bố cục trong bản xem trước.`:"Chọn một nguồn cho cảnh này trước khi duyệt.";
  }
  function renderProject(reset=true) {
    channelUI?.sync();
    publicationUI?.sync();
    analyticsUI?.sync();
    visionUI?.sync();
    rightsUI?.sync();
    stockUI?.sync();
    generationUI?.sync();
    mediaPlannerUI?.sync();
    rightsOverrideUI?.sync();
    variantsUI?.sync();
    if(reset&&$('max-ai-cost'))$('max-ai-cost').value=project?.document?.cost_policy?.max_ai_cost_vnd??'';
    refreshCosts();
    const origin=project?.document.content_intelligence;
    $("intelligence-origin").hidden=!origin;
    $("intelligence-origin").innerHTML=origin?`Từ brief đã duyệt bởi ${esc(origin.brief.approval.reviewer)} · <a href="/intelligence?run=${esc(origin.run.id)}">Xem nghiên cứu & ý tưởng nguồn</a>`:"";
    $("image-card").hidden=workspaceUI?false:!project;
    $("new-project-options").hidden=!workspaceUI||Boolean(project);$("duration-mode-field").hidden=!workspaceUI;
    const proposal=project?.document.proposal;
    $("proposal-card").hidden=!proposal;
    $("project-heading").textContent=project?.document.name??"Bắt đầu một video mới";
    $("version").textContent=project?`Phiên bản ${project.revision}`:"Bản nháp";
    if(reset){dirty=false;dirtyPart=null;if(project){$("project-name").value=project.document.name;$("prompt").value=project.document.prompt;$("input-kind").value=project.document.input_kind??"prompt";}}
    if(reset){$("brand-select").value=project?.document.brand_template?.brand.id??"vf-reference";$("template-select").value=project?.document.brand_template?.template.id??"";$("duration-mode").value=project?.document.brand_template?.template.duration_policy??"preserve_voice_speed_hold_cta_to_target_refuse_overflow";}
    $("brand-note").textContent=project?.document.brand_template?`${project.document.brand_template.brand.name} · ${project.document.brand_template.template.name}. Thay đổi cần duyệt lại.`:"Đang dùng bố cục MVP đã có. Chọn và áp dụng mẫu để thay đổi.";
    $("document-list").innerHTML=(project?.document.documents??[]).map(d=>`<p><strong>${esc(d.filename)}</strong> · ${d.extracted_text.length.toLocaleString("vi-VN")} ký tự</p>`).join("")||'<p class="hint">Chưa có tài liệu nguồn.</p>';
    if(reset){$("review-check").checked=false;$("final-watch").checked=false;$("history-list").textContent="";$("artifact-list").textContent="";}
    const assets=mediaLibrary(project?.document),bindings=mediaBindings(project?.document);
    $("music-note").textContent=musicSummary(project);
    const musicHint=$('music-intake-hint');if(musicHint)musicHint.textContent=isSourceProject(project)?'Nhạc có quyền sử dụng được lặp đến cuối timeline, giữ âm thanh nguồn và tạo bản dựng mới cần duyệt. Chỉnh track nhạc tại Advanced Timeline; bật cân mức và ducking trong bảng Xử lý âm thanh nguồn & nhạc rồi nghe preview. WAV/MP3 ≤ 25 MB, tối đa 10 phút.':'Nhạc được hạ âm lượng khi có lời đọc. WAV/MP3 ≤ 25 MB, tối đa 10 phút.';
    if(reset)$("music-enabled").checked=Boolean(project?.document.music)&&project.document.music_enabled!==false;
    $("media-count").textContent=`${assets.length} nguồn`;
    $("asset-empty-state").hidden=assets.length>0;
    $("asset-create-first").hidden=Boolean(project);
    const usedAssets=new Set(bindings.map(b=>b.asset_id));
    $("media-library").classList.toggle('asset-grid',Boolean(workspaceUI));
    $("media-library").innerHTML=workspaceUI?assets.map(a=>workspaceUI.assetCard({...a,tags:project?.document.asset_tags?.[a.id]??a.tags??[]},{thumbnail:thumbnail(a),used:usedAssets.has(a.id),attached:true})).join(''):assets.map(a=>`<figure class="media-tile"><img src="${thumbnail(a)}" alt="${esc(a.filename)}" loading="lazy"><figcaption><span>${a.kind==="video"?"▷ VIDEO":"ẢNH"}</span><strong>${esc(a.filename)}</strong>${a.kind==="video"?`<small>${Number(a.duration_seconds).toFixed(1)} giây · âm thanh gốc tắt</small>`:""}<small>${a.illustration?"Phối cảnh minh họa":"Nguồn của bạn"}</small></figcaption></figure>`).join("")||'<p class="hint">Chưa có nguồn. Chọn ảnh/video để thêm vào thư viện.</p>';
    $("media-analysis").innerHTML=(project?.document.media_analysis??[]).map(r=>{
      const asset=assets.find(a=>a.id===r.asset_id&&a.sha256===r.source_sha256);if(!asset)return "";
      const words=(r.transcript?.segments??[]).flatMap(s=>s.words);
      return `<article><h4>${esc(asset.filename)}</h4><p class="hint">${r.media.width} × ${r.media.height}${r.media.duration_seconds?` · ${Number(r.media.duration_seconds).toFixed(1)} giây · ${r.media.shots.length} cảnh nguồn`:""}. Mô tả dựa trên thông số hình ảnh; nội dung hình ảnh cần bạn kiểm tra.</p>${r.transcript?`<p>${esc(r.transcript.segments.map(s=>s.text).join(" "))}</p><details><summary>Thời gian từng từ · ${words.length} từ</summary><p>${words.map(w=>`${esc(w.text)} (${w.start_seconds.toFixed(2)}–${w.end_seconds.toFixed(2)}s)`).join(" · ")}</p></details><p class="hint">AssemblyAI · tiếng Việt · thời gian từng từ từ provider. Đây là lời nói nhận diện, chưa phải nội dung đã duyệt.</p>`:'<p class="hint">Nguồn này không có transcript lời nói.</p>'}</article>`;
    }).join("");
    if(proposal&&reset) {
      $("scenes").innerHTML=proposal.visual_brief.map((scene,i)=>`<article class="scene"><strong>CẢNH ${i+1}</strong><div class="scene-source"><img data-preview hidden alt="Nguồn của cảnh"><div><label>Nguồn cho cảnh ${i+1}<select data-media aria-label="Nguồn cho cảnh ${i+1}"><option value="">Chọn một ảnh hoặc video…</option>${assets.map(a=>`<option value="${esc(a.id)}" ${bindings.some(b=>b.scene===scene.scene&&b.asset_id===a.id)?"selected":""}>${esc(sourceLabel(a))}</option>`).join("")}</select></label><p data-media-note class="hint"></p></div></div><label>Lời đọc<textarea data-narration rows="3" maxlength="1500">${esc(scene.narration_excerpt)}</textarea></label><div class="scene-grid"><label>Chữ trên video<input data-title maxlength="150" value="${esc(scene.on_screen_text)}"></label><label>Định hướng hình ảnh<textarea data-visual rows="2" maxlength="1200">${esc(scene.visual)}</textarea></label></div></article>`).join("");
      document.querySelectorAll(".scene").forEach((row,i)=>{row.insertAdjacentHTML("beforeend",editorControls(proposal.visual_brief[i])+`<div class="actions"><button data-move="-1" class="text-button" aria-label="Đưa cảnh lên">↑ Lên</button><button data-move="1" class="text-button" aria-label="Đưa cảnh xuống">↓ Xuống</button></div>`);scenePreview(row);});
      $("narration").textContent=proposal.narration;
      $("facts").innerHTML=proposal.facts_needing_source.map(f=>`<li>${esc(f)}</li>`).join("")||"<li>Đề xuất không liệt kê thêm nguồn. Bạn vẫn cần kiểm tra nội dung.</li>";
    }
    $("approval-state").textContent=project?.approval?"Đã duyệt phiên bản này":"Chờ bạn duyệt";
    $("script-review-state").textContent=scriptReviewLabel(project);
    $("script-review-state").hidden=!scriptReviewLabel(project);
    const jobs=project?.jobs??[];
    $("job-empty").hidden=Boolean(jobs.length);
    $("jobs").innerHTML=jobs.slice(0,6).map(job=>`<div class="job ${job.error?"error":""}"><strong>${job.kind==="media_frames"?"Khung hình nguồn & gợi ý thumbnail":job.kind==="auto_edit_analysis"?"Đo cảnh & âm thanh trên máy":job.kind==="asr"?"Phân tích nguồn & lời nói":job.kind==="content"?"Nội dung":job.snapshot?.document?.canonical_timeline?.snapshot?.metadata?.native_auto_edit_schema?"Dựng video nguồn":"Giọng đọc & video"}</strong><small>${new Date(job.created_at).toLocaleString("vi-VN")} · v${job.revision}</small>${esc(["asr","auto_edit_analysis","media_frames"].includes(job.kind)&&job.status==="succeeded"?"Kết quả phân tích sẵn sàng · hãy kiểm tra":statusNames[job.status]??job.status)}${["running","retrying"].includes(job.status)?`<small>${esc(stageNames[job.stage]??job.stage)}</small>`:""}${job.error?`<small>${esc(errors[job.error.code]??job.failure?.action??job.error.code)}${job.error.http_status?` · HTTP ${job.error.http_status}`:""}</small>`:""}${["failed","failed_qc","interrupted"].includes(job.status)&&job.revision===project.revision?`<button data-resume="${esc(job.id)}">Tiếp tục từ bước đã lưu</button>`:""}</div>`).join("");
    const video=currentVideo(project);
    $("final-review-panel").hidden=!video;
    $("open-output").hidden=!video;
    $("final-review-state").textContent=finalApproved(video)?`Đã duyệt bản cuối bởi ${video.final_review.reviewer}. Mã xác thực gắn với đúng tệp đã xem.`:"Bản xem trước đã render. Xem và nghe trước khi duyệt làm bản cuối; bản cuối giữ nguyên tệp đã kiểm chứng.";
    $("video").hidden=!video;$("video-placeholder").hidden=Boolean(video);$("download").hidden=!video;
    if(video){if($("video").getAttribute("src")!==video.result.video_url)$("video").src=video.result.video_url;$("download").href=finalApproved(video)?`/api/jobs/${video.id}/final`:video.result.video_url;$("download").textContent=finalApproved(video)?"Tải video cuối MP4 ↓":"Tải bản xem trước MP4 ↓";$("qc-note").textContent=`Đã qua kiểm tra video và âm thanh · ${video.result.qc.duration_seconds.toFixed(1)} giây. Bạn cần xem lại video cuối.`;}else{$("video").removeAttribute("src");$("download").removeAttribute("href");$("qc-note").textContent="";}
    const failed=jobs[0]&&jobs[0].kind!=="asr"&&["failed","failed_qc","interrupted"].includes(jobs[0].status);
    $("retry").hidden=!failed;$("retry-note").hidden=!failed;
    shotStudio?.refresh(reset);
    nativeAnalysis?.refresh(reset);
    mediaFrames?.refresh();
    controls();
  }
  async function projects() {
    const list=await api($("show-archived").checked?"/api/projects?archived=include":"/api/projects");
    $("project-picker").innerHTML='<option value="">Chọn dự án…</option>'+list.map(p=>`<option value="${p.id}">${esc(p.document.name)}${p.archived?" · Đã lưu trữ":""}</option>`).join("");
    $("project-picker").value=project?.id??"";
  }
  async function reload(reset=false) {
    if(project){const latest=await api(`/api/projects/${project.id}`);if(dirty&&latest.revision!==project.revision)throw new Error("Phiên bản đã được sửa ở cửa sổ khác. Giữ bản đang nhập; tải lại trang sau khi lưu lại nội dung cần giữ.");project=latest;}
    renderProject(reset);await projects();schedule();
  }
  function schedule() {
    clearTimeout(timer);
    if(!jobActive(project))return;
    timer=setTimeout(async()=>{
      const wasActive=jobActive(project);
      try {await reload(false);pollFailures=0;if(wasActive&&!jobActive(project))renderProject(true);}
      catch(error){pollFailures++;message(`Không đọc được trạng thái: ${error.message}. Job không được tự gửi lại.`,true);if(pollFailures<3)schedule();}
    },1500);
  }
  const guarded=fn=>async event=>{event?.preventDefault();if(busy)return;busy=true;controls();try{await fn(event);}catch(error){message(error.message,true);}finally{busy=false;controls();}};
  async function initializeSupportedStudio(session){
    canManage=session.access?.mode!=='registry'||session.access.permissions?.includes('manage')===true;
    if(session.capabilities?.native_bridge_operator===true){
      const bridge=await import('./native-bridge.mjs');$('native-bridge-card').hidden=false;
      bridgeUI=bridge.initializeNativeBridge({api,getState:()=>({busy,canManage,workspace_id:session.access?.workspace_id??'wsp_native_local'}),onMessage:message});
    }
    if(session.capabilities?.native_source_variants===true){
      const variants=await import('./native-variants.mjs');$('native-variants-card').hidden=false;
      variantsUI=variants.initializeNativeVariants({api,getState:()=>({project,dirty,busy,
        canEdit:session.access?.mode!=='registry'||session.access.permissions?.includes('edit')===true,
        workspace_id:session.access?.workspace_id??'wsp_native_local'}),onMessage:message,onCreated:()=>void projects().catch(error=>message(error.message,true)),
        onOpen:async id=>{if(dirty||busy)throw new Error('Lưu thay đổi và chờ thao tác hiện tại trước.');
          project=await api(`/api/projects/${id}`);localStorage.setItem('vf-native-project',project.id);renderProject(true);await projects();schedule();}});
    }
    if(session.capabilities?.native_vision_review===true){
      const vision=await import('./native-vision.mjs');$('native-vision-panel').hidden=false;
      visionUI=vision.initializeNativeVision({api,getState:()=>({project,dirty,busy,canManage,
        workspace_id:session.access?.workspace_id??'wsp_native_local'}),onMessage:message});
    }
    if(session.capabilities?.native_rights_review===true){
      const rights=await import('./native-rights.mjs');$('native-rights-panel').hidden=false;
      rightsUI=rights.initializeNativeRights({api,getState:()=>({project,dirty,busy:busy||(shotStudio?.isWorking()??false)||(nativeAnalysis?.isWorking()??false)||(mediaFrames?.isWorking()??false)||(generationUI?.isWorking()??false)||(rightsOverrideUI?.isWorking()??false)||(mediaPlannerUI?.isWorking()??false),canManage,active:jobActive(project),
        workspace_id:session.access?.workspace_id??'wsp_native_local'}),onMessage:message,onWorking:controls,onSaved:async()=>{await reload(true);}});
    }
    if(session.capabilities?.native_stock_media===true){
      const stock=await import('./native-stock.mjs');$('native-stock-panel').hidden=false;
      stockUI=stock.initializeNativeStock({api,getState:()=>({project,dirty,busy:busy||(shotStudio?.isWorking()??false)||(nativeAnalysis?.isWorking()??false)||(mediaFrames?.isWorking()??false)||(rightsUI?.isWorking()??false)||(generationUI?.isWorking()??false)||(rightsOverrideUI?.isWorking()??false)||(mediaPlannerUI?.isWorking()??false),canManage,
        canEdit:session.access?.mode!=='registry'||session.access.permissions?.includes('edit')===true,active:jobActive(project),workspace_id:session.access?.workspace_id??'wsp_native_local'}),
        onMessage:message,onWorking:controls,onSaved:async()=>{await reload(true);}});
    }
    if(session.capabilities?.native_owner_rights_override_review===true){
      const overrides=await import('./native-rights-override.mjs');$('native-rights-override-panel').hidden=false;
      rightsOverrideUI=overrides.initializeNativeRightsOverride({api,getState:()=>({project,dirty,busy:busy||(shotStudio?.isWorking()??false)||(nativeAnalysis?.isWorking()??false)||(mediaFrames?.isWorking()??false)||(rightsUI?.isWorking()??false)||(stockUI?.isWorking()??false)||(generationUI?.isWorking()??false)||(mediaPlannerUI?.isWorking()??false),canManage,active:jobActive(project),
        workspace_id:session.access?.workspace_id??'wsp_native_local'}),onMessage:message,onWorking:controls,onSaved:async()=>{await reload(true);}});
    }
    if(session.capabilities?.native_generation_media===true){
      const generation=await import('./native-generation.mjs');$('native-generation-panel').hidden=false;
      generationUI=generation.initializeNativeGeneration({api,getState:()=>({project,dirty,busy:busy||(shotStudio?.isWorking()??false)||(nativeAnalysis?.isWorking()??false)||(mediaFrames?.isWorking()??false)||(rightsUI?.isWorking()??false)||(stockUI?.isWorking()??false)||(rightsOverrideUI?.isWorking()??false)||(mediaPlannerUI?.isWorking()??false),
        canEdit:session.access?.mode!=='registry'||session.access.permissions?.includes('edit')===true,active:jobActive(project),workspace_id:session.access?.workspace_id??'wsp_native_local'}),
        onMessage:message,onWorking:controls,onSaved:async()=>{await reload(true);}});
    }
    if(session.capabilities?.native_storyboard_media_planner===true){
      const planner=await import('./native-media-planner.mjs');
      mediaPlannerUI=planner.initializeNativeMediaPlanner({api,getState:()=>({project,dirty,busy:busy||(shotStudio?.isWorking()??false)||(nativeAnalysis?.isWorking()??false)||(mediaFrames?.isWorking()??false)||(rightsUI?.isWorking()??false)||(stockUI?.isWorking()??false)||(generationUI?.isWorking()??false)||(rightsOverrideUI?.isWorking()??false),
        canEdit:session.access?.mode!=='registry'||session.access.permissions?.includes('edit')===true,active:jobActive(project),workspace_id:session.access?.workspace_id??'wsp_native_local'}),
        onMessage:message,onWorking:controls,onSaved:async()=>{await reload(true);}});
    }
    if(session.capabilities?.native_analytics_review===true){
      const analytics=await import('./native-analytics.mjs');$('native-analytics-card').hidden=false;
      analyticsUI=analytics.initializeNativeAnalytics({api,getState:()=>({project,dirty,busy,canManage,
        workspace_id:session.access?.workspace_id??'wsp_native_local'}),onMessage:message});
    }
    if(session.capabilities?.native_publication_review===true){
      const publications=await import('./native-publications.mjs');$('native-publication-card').hidden=false;
      publicationUI=publications.initializeNativePublications({api,getState:()=>({project,dirty,busy,canManage,
        canEdit:session.access?.mode!=='registry'||session.access.permissions?.includes('edit')===true}),onMessage:message});
    }
    if(session.access?.mode==='registry'){
      const access=await import('./native-access.mjs');access.installNativeAccess(session);
    }
    if($('cost-card')){
      $('cost-card').hidden=!supportsNativeCosts(session);
      try {costUI=await loadNativeCosts(session);}
      catch {costUI=null;$('cost-summary').textContent='Chưa tải được bảng chi phí. Làm mới để kiểm tra.';}
    }
    projectQuality=newProjectQuality(session);
    if(session.capabilities?.native_media_frame_analysis===true){
      const frames=await import('./native-media-frames.mjs');
      mediaFrames=frames.initializeMediaFrames({api,getProject:()=>project,getState:()=>({dirty,busy:busy||(shotStudio?.isWorking()??false)||(nativeAnalysis?.isWorking()??false)||(mediaPlannerUI?.isWorking()??false)}),onWorking:controls,onMessage:message});
    }
    if(session.capabilities?.native_auto_edit_analysis===true){
      const analysis=await import('./native-auto-edit.mjs');
      const stylesheet=document.createElement('link');stylesheet.rel='stylesheet';stylesheet.href='/native-auto-edit.css';document.head.append(stylesheet);
      nativeAnalysis=analysis.initializeNativeAnalysis({api,getProject:()=>project,getState:()=>({dirty,dirtyPart,busy:busy||(shotStudio?.isWorking()??false)||(mediaPlannerUI?.isWorking()??false)}),
        onProject:(value,reset)=>{const changed=project?.id!==value?.id;project=value;if(changed&&value){localStorage.setItem('vf-native-project',value.id);void projects().catch(error=>message(error.message,true));}renderProject(reset);},onDirty:markDirty,onMessage:message,
        sourceEnabled:session.capabilities?.native_source_timeline===true,onSourceCreated:()=>shotStudio?.showStage('video'),onWorking:controls,onDraftsCreated:projects});
    }
    let module;
    try{module=await loadNativeShotStudio(session);}catch{nativeLegacyLayout(document);message('Đang dùng giao diện Studio hiện hành. Không tải được không gian biên tập mới.',true);return;}
    if(!module)return;
    document.body.classList.add('shot-studio');
    const stylesheet=document.createElement('link');stylesheet.rel='stylesheet';stylesheet.href='/shot-studio.css';document.head.append(stylesheet);
    if(session.capabilities?.native_studio_ux===true){
      const [preview,assets,shell]=await Promise.all([import('./video-preview.mjs'),import('./asset-picker.mjs'),import('./studio-shell.mjs')]);
      workspaceUI={...preview,...assets};
      document.body.classList.add('studio-ux');
      $("project-name").value='Video mới';
      for(const href of ['/studio-shell.css','/studio-workspace.css']){const link=document.createElement('link');link.rel='stylesheet';link.href=href;document.head.append(link);}
      shell.mountStudioShell({page:['assets','brands'].includes(new URLSearchParams(location.search).get('view'))?new URLSearchParams(location.search).get('view'):'project',context:'Không gian sản xuất video'});
      document.querySelector('.asset-workspace-toolbar').hidden=false;
      if(session.capabilities?.native_channel_profiles===true){
        const channels=await import('./native-channel-profiles.mjs');
        channelUI=channels.initializeNativeChannels({api,getState:()=>({project,busy:busy||(mediaPlannerUI?.isWorking()??false),canEdit:session.access?.mode!=='registry'||session.access.permissions?.includes('edit')===true}),
          onDefaults:value=>{$('new-content-profile').value=value.content_profile_id;$('new-brand').value=value.brand_id;$('new-video-format').value=value.aspect_ratio;creationTemplates();$('new-template').value=value.template_id;$('new-duration-mode').value=value.duration_mode;},onMessage:message});
        $('new-content-profile').addEventListener('change',()=>channelUI?.clear());
      }
    }
    document.querySelectorAll('.stage-navigation,.studio-header-actions,.skip-link,.sidebar [data-stage],.sidebar a[href^="/production"]').forEach(el=>el.hidden=false);
    const sourceUI=session.capabilities?.native_source_timeline===true?await import('./native-source-editor.mjs'):null;
    shotStudio=module.initializeShotStudio({api,ui:workspaceUI,sourceUI,capabilities:session.capabilities??{},getProject:()=>project,getGuards:()=>({dirty,busy:busy||(mediaPlannerUI?.isWorking()??false)}),onDirty:value=>{dirty=value;dirtyPart=value?'shot':null;$("review-check").checked=false;controls();},onProject:(value,reset)=>{project=value;renderProject(reset);},onMessage:message,onWorking:controls});
  }
  $("save-prompt").addEventListener("click",guarded(async()=>{
    const creating=!project;
    if(!project){project=await api("/api/projects",{name:$("project-name").value,prompt:$("prompt").value,input_kind:$("input-kind").value,...projectQuality,...(workspaceUI&&$("new-content-profile").value?{content_profile_id:$("new-content-profile").value}:{}),...(channelUI?.request()??{})});if(workspaceUI&&$("new-template").value)project=await api(`/api/projects/${project.id}/brand-template`,{revision:project.revision,brand_id:$("new-brand").value,template_id:$("new-template").value,duration_mode:$("new-duration-mode").value});}
    else project=await api(`/api/projects/${project.id}/draft`,{revision:project.revision,prompt:$("prompt").value,input_kind:$("input-kind").value});
    localStorage.setItem("vf-native-project",project.id);if(workspaceUI&&creating){const url=new URL(location.href);url.searchParams.delete('new');url.searchParams.set('project',project.id);history.replaceState(null,'',url);document.querySelectorAll('.sidebar [data-studio-page]').forEach(el=>{const current=el.dataset.studioPage==='projects';el.classList.toggle('active',current);if(current)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});}renderProject(true);await projects();if(creating)shotStudio?.showStage(workspaceUI?.nextProjectStage(project)??'script');message("Đã lưu dự án. Thêm tư liệu tại Assets rồi chọn hình cho từng shot.");
  }));
  async function enqueue(kind,fresh=false) {
    if(dirty)throw new Error("Lưu chỉnh sửa trước khi chạy job.");
    const key=`vf-native-${project.id}-${project.revision}-${kind}`;
    let requestKey=sessionStorage.getItem(key);
    if(!requestKey||fresh){requestKey=crypto.randomUUID();sessionStorage.setItem(key,requestKey);}
    await api(`/api/projects/${project.id}/jobs`,{revision:project.revision,kind,request_key:requestKey});
    await reload(false);message(kind==="media_frames"?"Đã gửi job đo khung hình trên máy. Kiểm tra các mẫu và gợi ý thumbnail; bản dựng giữ nguyên.":kind==="auto_edit_analysis"?"Đã gửi job đo cảnh và âm thanh trên máy. Hãy kiểm tra lời nói, cảnh và điểm nổi bật.":kind==="asr"?"Đã gửi job phân tích nguồn và nhận diện lời nói. Hãy kiểm tra transcript khi hoàn tất.":kind==="content"?"Đã gửi job tạo đề xuất. Bước tiếp theo cần bạn kiểm tra và duyệt.":isSourceProject(project)?'Đã gửi job render video nguồn với âm thanh và phụ đề đã lưu.':'Đã gửi job tạo giọng đọc và render video.');
  }
  $("generate").addEventListener("click",guarded(()=>enqueue("content")));
  $("analyze-media").addEventListener("click",guarded(()=>enqueue("asr")));
  $("measure-auto-edit").addEventListener("click",guarded(()=>enqueue("auto_edit_analysis")));
  $("measure-media-frames").addEventListener("click",guarded(()=>enqueue("media_frames")));
  $("render").addEventListener("click",guarded(()=>enqueue("render")));
  $("retry").addEventListener("click",guarded(()=>enqueue(project.jobs[0].kind,true)));
  $("save-proposal").addEventListener("click",guarded(async()=>{const proposal=readProposal(),bindings=readBindings();project=await api(`/api/projects/${project.id}/draft`,{revision:project.revision,proposal,scene_media:bindings,scene_options:mediaReady({...project.document,proposal,scene_media:bindings})?readOptions():undefined,music_enabled:$("music-enabled").checked});renderProject(true);message("Đã lưu nội dung và cách dựng từng cảnh. Phiên bản mới cần duyệt lại.");}));
  $("auto-plan").addEventListener("click",guarded(async()=>{project=await api(`/api/projects/${project.id}/auto-plan`,{revision:project.revision});renderProject(true);message("Đã đề xuất nguồn và cách dựng. Kiểm tra từng cảnh, đổi nguồn nếu cần rồi duyệt.");}));
  $("apply-brand").addEventListener("click",guarded(async()=>{project=await api(`/api/projects/${project.id}/brand-template`,{revision:project.revision,brand_id:$("brand-select").value,template_id:$("template-select").value,...(workspaceUI?{duration_mode:$("duration-mode").value}:{})});renderProject(true);message("Đã lưu cấu hình thương hiệu và mẫu vào phiên bản này. Kiểm tra cách dựng, nội dung và duyệt lại trước khi tạo video.");}));
  $('save-cost-policy')?.addEventListener('click',guarded(async()=>{
    const value=$('max-ai-cost').value.trim();
    project=await api(`/api/projects/${project.id}/cost-policy`,{revision:project.revision,max_ai_cost_vnd:value||null});
    renderProject(true);message('Đã lưu giới hạn chi phí. Kiểm tra và duyệt lại phiên bản trước khi sản xuất.');
  }));
  $('max-ai-cost')?.addEventListener('input',()=>markDirty('cost'));
  $("duplicate-project").addEventListener("click",guarded(async()=>{project=await api(`/api/projects/${project.id}/duplicate`,{revision:project.revision});localStorage.setItem("vf-native-project",project.id);renderProject(true);await projects();message("Đã tạo bản sao chưa duyệt; giữ nguyên nội dung và nguồn, cần kiểm tra và duyệt lại.");}));
  $("archive-project").addEventListener("click",guarded(async()=>{const archived=!project.archived;project=await api(`/api/projects/${project.id}/archive`,{revision:project.revision,archived});$("show-archived").checked=archived||$("show-archived").checked;renderProject(true);await projects();message(archived?"Đã lưu trữ dự án. Có thể khôi phục; tệp và lịch sử được giữ nguyên.":"Đã khôi phục dự án.");}));
  $("show-archived").addEventListener("change",guarded(projects));
  $("load-history").addEventListener("click",guarded(async()=>{const list=await api(`/api/projects/${project.id}/versions`);$("history-list").innerHTML=list.map(v=>`<details><summary>Phiên bản ${v.revision} · ${new Date(v.created_at).toLocaleString("vi-VN")}</summary><p>${esc(v.document.proposal?.narration??v.document.prompt)}</p><small>${esc(v.components.script_version)}</small></details>`).join("");}));
  $("reject-content").addEventListener("click",guarded(async()=>{project=await api(`/api/projects/${project.id}/reject`,{revision:project.revision,reviewer:$("reviewer").value,note:$("content-rejection").value});renderProject(true);message("Đã trả nội dung để sửa. Chỉnh sửa, lưu và duyệt lại trước khi tạo video.");}));
  async function reviewFinal(decision){const video=currentVideo(project);project=await api(`/api/jobs/${video.id}/review`,{revision:project.revision,reviewer:$("final-reviewer").value,acknowledged:$("final-watch").checked,decision,note:$("final-note").value});renderProject(true);message(decision==="approve"?"Đã duyệt đúng tệp đã xem làm bản cuối. Có thể tải MP4.":"Đã trả video để sửa. Sửa cảnh/nội dung, lưu và duyệt lại trước khi tạo bản mới.");}
  $("approve-final").addEventListener("click",guarded(()=>reviewFinal("approve")));
  $("reject-final").addEventListener("click",guarded(()=>reviewFinal("reject")));
  $("final-watch").addEventListener('change',controls);$("final-reviewer").addEventListener('input',controls);
  $("load-artifacts").addEventListener("click",guarded(async()=>{const value=await api(`/api/jobs/${currentVideo(project).id}/artifacts`);$("artifact-list").innerHTML=`<p>Phiên bản ${value.revision} · kiểm tra ${value.qc.passed?"đạt":"chưa đạt"}</p><p>${esc(value.output_directory)}</p>`+value.artifacts.map(a=>`<p><strong>${esc(a.path)}</strong> · ${a.bytes.toLocaleString("vi-VN")} byte<br><small>${esc(a.sha256)}</small></p>`).join("");}));
  $("open-output").addEventListener("click",guarded(async()=>{await api(`/api/jobs/${currentVideo(project).id}/open-folder`,{});message("Đã mở thư mục chứa video và các tệp kiểm tra.");}));
  $("upload-music").addEventListener("click",guarded(async()=>{const file=$("music-file").files[0];if(!file||!musicType(file)||!file.size||file.size>25*1024*1024||!$("music-rights").checked)throw new Error(errors.MUSIC_RIGHTS_TYPE_SIZE_REQUIRED_MAX_25MB);const response=await fetch(`/api/projects/${project.id}/music`,{method:"POST",credentials:"same-origin",headers:{"Content-Type":musicType(file),"X-VF-CSRF":csrf,"X-VF-Revision":String(project.revision),"X-VF-Rights":"confirmed","X-VF-Filename":encodeURIComponent(file.name)},body:file});const result=await response.json();if(!response.ok)throw new Error(errors[result.code]??result.code);project=result;$("music-file").value="";renderProject(true);message("Đã lưu nhạc nền. Kiểm tra và duyệt lại trước khi render.");}));
  $("music-enabled").addEventListener("change",()=>markDirty("proposal"));
  $("approve").addEventListener("click",guarded(async()=>{if(dirty)throw new Error("Lưu chỉnh sửa trước khi duyệt.");project=await api(`/api/projects/${project.id}/approve`,{revision:project.revision,reviewer:$("reviewer").value,acknowledged:$("review-check").checked});renderProject(true);message(isSourceProject(project)?'Đã duyệt bản dựng nguồn hiện tại. Có thể render và kiểm tra video cuối.':"Đã ghi nhận bạn duyệt phiên bản này. Có thể tạo giọng đọc và video.");}));
  $("upload-media").addEventListener("click",guarded(async()=>{
    if(dirty)throw new Error("Lưu chỉnh sửa trước khi tải nguồn.");
    const files=[...$("media-files").files];if(!files.length)throw new Error("Chọn các ảnh/video trước khi tải.");
    if(!$("media-rights").checked)throw new Error(errors.MEDIA_RIGHTS_CONFIRMATION_REQUIRED);
    if(mediaLibrary(project.document).length+files.length>50)throw new Error(errors.MEDIA_LIBRARY_LIMIT_50);
    for(const file of files){const type=mediaType(file);if(!type)throw new Error(`${file.name}: ${errors.MEDIA_TYPE_NOT_SUPPORTED}`);if(!file.size||file.size>(type.startsWith("video/")?250:15)*1024*1024)throw new Error(`${file.name}: ${errors.MEDIA_FILE_TOO_LARGE_OR_EMPTY}`);}
    let saved=0;
    try {
      for(const file of files){$("upload-progress").textContent=`Đang tải và kiểm tra ${saved+1}/${files.length}: ${file.name}`;
        const response=await fetch(`/api/projects/${project.id}/media`,{method:"POST",credentials:"same-origin",headers:{"Content-Type":mediaType(file),"X-VF-CSRF":csrf,"X-VF-Revision":String(project.revision),"X-VF-Rights":"confirmed","X-VF-Illustration":String($("media-illustration").checked),"X-VF-Filename":encodeURIComponent(file.name)},body:file});
        const result=await response.json();if(!response.ok)throw new Error(`${file.name}: ${errors[result.code]??result.code} (HTTP ${response.status})`);
        project=result;saved++;renderProject(true);
      }
      $("media-files").value="";$("upload-progress").textContent=`Đã lưu ${saved} nguồn. Chọn nguồn cho từng cảnh bên dưới.`;message("Đã lưu thư viện ảnh/video. Chọn một nguồn cho mỗi cảnh, lưu và duyệt trước khi render.");
    } catch(error) {$("upload-progress").textContent=`Đã lưu ${saved}/${files.length} nguồn. Khi thử lại, chỉ chọn các tệp chưa lưu.`;throw error;}
  }));
  $("project-picker").addEventListener("change",guarded(async()=>{if(dirty)throw new Error("Lưu chỉnh sửa trước khi đổi dự án.");clearTimeout(timer);project=$("project-picker").value?await api(`/api/projects/${$("project-picker").value}`):null;if(project)localStorage.setItem("vf-native-project",project.id);renderProject(true);schedule();}));
  $("new-project").addEventListener("click",guarded(async()=>{if(dirty)throw new Error("Lưu chỉnh sửa trước khi tạo dự án mới.");if(workspaceUI){location.assign('/?new=1');return;}clearTimeout(timer);project=null;localStorage.removeItem("vf-native-project");$("input-kind").value="prompt";$("prompt").value=(await api("/api/defaults")).prompt;$("project-name").value="Vinhomes Green Paradise Cần Giờ";$("project-picker").value="";$("new-video-format").value='9:16';$("new-duration-mode").value='fit_narration_preserve_voice_speed';creationTemplates();renderProject(true);}));
  $("refresh").addEventListener("click",guarded(async()=>{const session=await api("/api/session");csrf=session.csrf;await reload(!dirty);message("Đã làm mới dữ liệu.");}));
  $("jobs").addEventListener("click",guarded(async event=>{const button=event.target.closest("[data-resume]");if(!button)return;if(dirty)throw new Error("Lưu chỉnh sửa trước khi tiếp tục.");await api(`/api/jobs/${button.dataset.resume}/resume`,{});await reload(true);schedule();message("Đang tiếp tục job từ bước đã kiểm chứng.");}));
  $("prompt").addEventListener("input",()=>markDirty("prompt"));
  $("input-kind").addEventListener("change",()=>{if($("input-kind").value==="media")$("prompt").value="";markDirty("prompt");});
  $("upload-documents").addEventListener("click",guarded(async()=>{const files=[...$("document-files").files];if(!project||dirty||!files.length)throw new Error("Lưu dự án và chọn tài liệu trước khi tải lên.");for(const file of files){const type=documentType(file);if(!type||file.size>5*1024*1024)throw new Error("Chọn TXT, Markdown hoặc DOCX không quá 5 MB.");const response=await fetch(`/api/projects/${project.id}/documents`,{method:"POST",credentials:"same-origin",headers:{"Content-Type":type,"X-VF-CSRF":csrf,"X-VF-Revision":String(project.revision),"X-VF-Filename":encodeURIComponent(file.name)},body:file});const result=await response.json();if(!response.ok)throw new Error(result.failure?.action??result.code);project=result;renderProject(true);}await projects();$("document-files").value="";message("Đã lưu file gốc và nội dung trích xuất. Hãy kiểm tra tài liệu trước khi duyệt.");}));
  $("scenes").addEventListener("input",()=>{markDirty("proposal");$("narration").textContent=readProposal().narration;});
  $("scenes").addEventListener("click",event=>{const button=event.target.closest("[data-move]");if(!button||busy||jobActive(project)||project.archived)return;const row=button.closest(".scene"),target=Number(button.dataset.move)<0?row.previousElementSibling:row.nextElementSibling;if(!target)return;if(Number(button.dataset.move)<0)target.before(row);else target.after(row);document.querySelectorAll(".scene").forEach((r,i)=>{r.querySelector("strong").textContent=`CẢNH ${i+1}`;const media=r.querySelector("[data-media]");media.setAttribute("aria-label",`Nguồn cho cảnh ${i+1}`);media.parentElement.firstChild.textContent=`Nguồn cho cảnh ${i+1}`;});markDirty("proposal");$("narration").textContent=readProposal().narration;message("Đã đổi thứ tự cảnh. Lời đọc sẽ theo thứ tự mới; lưu và duyệt lại trước khi tạo giọng đọc.");});
  $("scenes").addEventListener("change",event=>{if(event.target.matches("input,select,textarea")){const row=event.target.closest(".scene");if(event.target.matches("[data-media]")){row.querySelector("[data-motion]").value="none";row.querySelector("[data-start]").value="0";}scenePreview(row);markDirty("proposal");}});
  window.addEventListener("beforeunload",event=>{if(dirty){event.preventDefault();event.returnValue="";}});
  async function runtimeStatus(){if(!canManage){$("runtime-status").textContent='Chẩn đoán kết nối dành cho chủ không gian.';return;}const status=await api("/api/runtime-status");$("runtime-status").textContent=`Nội dung: ${status.openai_key_saved?"key đã lưu; chưa kiểm tra bằng yêu cầu mới":"chưa có key"}. Giọng Thùy Dung: sẵn sàng. FFmpeg: sẵn sàng. AssemblyAI: ${status.assemblyai.connected?"đã xác minh kết nối":"chưa kết nối"}.`;}
  function creationTemplates(){if(!brandCatalog)return;const format=$("new-video-format").value,selected=$("new-template").value;const values=brandCatalog.templates.filter(t=>t.aspect_ratio===format);$("new-template").innerHTML=values.map(t=>`<option value="${esc(t.id)}">${esc(t.name)}</option>`).join('');$("new-template").value=values.some(t=>t.id===selected)?selected:values.find(t=>t.purpose==='property_presentation'&&t.duration_seconds===30)?.id??values[0]?.id??'';}
  $("new-video-format").addEventListener('change',creationTemplates);
  async function loadBrandCatalog(){const values=await api(shotStudio?"/api/brand-templates?formats=all":"/api/brand-templates");brandCatalog=values;$("brand-select").innerHTML=values.brands.map(b=>`<option value="${esc(b.id)}">${esc(b.name)}</option>`).join("");$("template-select").innerHTML='<option value="">Bố cục MVP hiện có</option>'+values.templates.map(t=>`<option value="${esc(t.id)}">${esc(t.name)}</option>`).join("");$("brand-select").value=project?.document.brand_template?.brand.id??"vf-reference";$("template-select").value=project?.document.brand_template?.template.id??"";if(workspaceUI){$("new-brand").innerHTML=values.brands.map(b=>`<option value="${esc(b.id)}">${esc(b.name)}</option>`).join('');creationTemplates();const {profiles}=await api('/api/intelligence/config');$("new-content-profile").innerHTML='<option value="">Nội dung khác</option>'+profiles.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');}}
  (async()=>{busy=true;controls();try{const session=await api("/api/session");csrf=session.csrf;await initializeSupportedStudio(session);runtimeStatus().catch(()=>{$("runtime-status").textContent="Chưa đọc được trạng thái. Làm mới Studio để kiểm tra.";});$("prompt").value=(await api("/api/defaults")).prompt;await projects();const saved=new URLSearchParams(location.search).get("new")==="1"?null:new URLSearchParams(location.search).get("project")??localStorage.getItem("vf-native-project");if(saved&&[...$("project-picker").options].some(o=>o.value===saved))project=await api(`/api/projects/${saved}`);await loadBrandCatalog();await channelUI?.load();renderProject(true);await projects();schedule();}catch(error){message(error.message,true);}finally{busy=false;controls();}})();
}
