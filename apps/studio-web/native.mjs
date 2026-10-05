export const jobActive = project => project?.jobs?.some(j => ["queued", "running"].includes(j.status)) ?? false;
export const currentVideo = project => project?.approval ? project.jobs.find(j => j.kind === "render" && j.status === "succeeded" && j.revision === project.revision) : null;
export const canRender = (project, dirty, busy) => Boolean(project?.approval && project.approval.revision === project.revision && !dirty && !busy && !jobActive(project));

const errors = {
  HUMAN_APPROVAL_REQUIRED_BEFORE_TTS:"Cần duyệt đúng phiên bản nội dung trước khi tạo giọng đọc.",
  STALE_VERSION_RELOAD:"Phiên bản đã thay đổi. Làm mới để lấy bản mới nhất.",
  PROJECT_BUSY:"Dự án đang có job chạy. Chờ job hoàn tất trước khi sửa.",
  CONTENT_AND_IMAGE_REQUIRED:"Cần có đề xuất nội dung và ảnh trước khi duyệt.",
  HUMAN_REVIEW_REQUIRED:"Nhập tên người duyệt và xác nhận đã kiểm tra nội dung.",
  INTERRUPTED_NO_AUTOMATIC_REPLAY:"Job bị ngắt. Chưa tự chạy lại; kết quả bước đã gọi có thể chưa rõ.",
  INVALID_PROPOSAL_SCENE_COVERAGE:"Lời đọc các cảnh phải phủ đầy đủ nội dung, theo thứ tự.",
  IMAGE_RIGHTS_CONFIRMATION_REQUIRED:"Xác nhận quyền dùng ảnh trước khi lưu.",
  INVALID_IMAGE_JPEG_PNG_MAX_15MB_40MP_MIN_240PX:"Ảnh phải là JPEG/PNG, tối đa 15 MB, 40 megapixel và mỗi chiều từ 240 px.",
  LOCAL_SESSION_REQUIRED:"Phiên làm việc đã hết hạn. Tải lại trang để tiếp tục.",
  OPENAI_TIMEOUT_OUTCOME_UNKNOWN_NO_RETRY:"OpenAI hết thời gian chờ. Không tự gọi lại; lần gọi trước có thể đã xử lý.",
  AuthenticationError:"Key OpenAI bị từ chối.", RateLimitError:"OpenAI từ chối do giới hạn sử dụng. Job đã dừng.",
  TTS_CHILD_FAILED:"Tạo giọng đọc thất bại. Job đã dừng.", MEDIA_QC_FAILED:"Video chưa vượt qua kiểm tra chất lượng.",
};
const statusNames = {queued:"Đang chờ",running:"Đang chạy",awaiting_review:"Đề xuất sẵn sàng · cần bạn duyệt",succeeded:"Video đã render · hãy xem lại",failed:"Job đã dừng do lỗi",interrupted:"Job bị ngắt · chưa chạy lại"};
const stageNames = {starting:"Bắt đầu",content_request:"Đang tạo nội dung",locked_thuy_dung_tts:"Đang tạo giọng Thùy Dung",ffmpeg_render_and_qc:"Đang render và kiểm tra video"};

if (typeof document !== "undefined") {
  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
  let project = null, csrf = null, busy = false, dirty = false, dirtyPart = null, timer = null, pollFailures = 0;
  function message(text, error=false) {$("message").textContent=text;$("message").hidden=false;$("message").classList.toggle("error",error);}
  async function api(path, body) {
    const response = await fetch(path,{method:body?"POST":"GET",credentials:"same-origin",headers:body?{"Content-Type":"application/json","X-VF-CSRF":csrf}:{},body:body?JSON.stringify(body):undefined});
    const result=await response.json();
    if(!response.ok)throw new Error(`${errors[result.code] ?? result.code} (HTTP ${response.status})`);
    return result;
  }
  function controls() {
    const active=jobActive(project), blocked=busy||active;
    document.querySelectorAll("input,textarea,select,button").forEach(el=>el.disabled=blocked);
    $("refresh").disabled=busy;
    $("project-picker").disabled=busy||dirty;
    $("new-project").disabled=busy||dirty;
    $("project-name").disabled=Boolean(project)||busy;
    $("generate").disabled=!project||blocked||dirty;
    $("approve").disabled=!project?.document.proposal||!project?.document.asset||blocked||dirty||Boolean(project.approval);
    $("render").disabled=!canRender(project,dirty,busy);
    $("save-prompt").textContent=project?"Lưu yêu cầu":"Tạo dự án";
    $("save-proposal").disabled=!project?.document.proposal||blocked;
    if(dirtyPart==="proposal"){$("prompt").disabled=true;$("save-prompt").disabled=true;}
    if(dirtyPart==="prompt"){$("scenes").querySelectorAll("input,textarea").forEach(el=>el.disabled=true);$("save-proposal").disabled=true;}
    $("save-note").textContent=dirty?"Có chỉnh sửa chưa lưu. Lưu trước khi tạo nội dung hoặc duyệt.":project?.approval?`Đã duyệt bởi ${project.approval.reviewer}.`:project?"Mọi thay đổi được lưu sẽ cần duyệt lại.":"Lưu yêu cầu trước khi tạo đề xuất.";
  }
  function markDirty(part) {dirty=true;dirtyPart=part;$("review-check").checked=false;controls();}
  function readProposal() {
    const old=project.document.proposal;
    const scenes=[...document.querySelectorAll(".scene")].map((row,i)=>({scene:i+1,visual:row.querySelector("[data-visual]").value,on_screen_text:row.querySelector("[data-title]").value,narration_excerpt:row.querySelector("[data-narration]").value}));
    return {...old,visual_brief:scenes,narration:scenes.map(s=>s.narration_excerpt.trim()).join(" ")};
  }
  function renderProject(reset=true) {
    $("image-card").hidden=!project;
    const proposal=project?.document.proposal;
    $("proposal-card").hidden=!proposal;
    $("project-heading").textContent=project?.document.name??"Bắt đầu một video mới";
    $("version").textContent=project?`Phiên bản ${project.revision}`:"Bản nháp";
    if(reset){dirty=false;dirtyPart=null;if(project){$("project-name").value=project.document.name;$("prompt").value=project.document.prompt;}}
    if(reset)$("review-check").checked=false;
    const asset=project?.document.asset;
    $("source-image").hidden=!asset;$("image-empty").hidden=Boolean(asset);
    if(asset)$("source-image").src=`/api/projects/${project.id}/image?v=${project.revision}`;
    if(proposal&&reset) {
      $("scenes").innerHTML=proposal.visual_brief.map((scene,i)=>`<article class="scene"><strong>CẢNH ${i+1}</strong><label>Lời đọc<textarea data-narration rows="3" maxlength="1500">${esc(scene.narration_excerpt)}</textarea></label><div class="scene-grid"><label>Chữ trên video<input data-title maxlength="150" value="${esc(scene.on_screen_text)}"></label><label>Định hướng hình ảnh<textarea data-visual rows="2" maxlength="1200">${esc(scene.visual)}</textarea></label></div></article>`).join("");
      $("narration").textContent=proposal.narration;
      $("facts").innerHTML=proposal.facts_needing_source.map(f=>`<li>${esc(f)}</li>`).join("")||"<li>Đề xuất không liệt kê thêm nguồn. Bạn vẫn cần kiểm tra nội dung.</li>";
    }
    $("approval-state").textContent=project?.approval?"Đã duyệt phiên bản này":"Chờ bạn duyệt";
    const jobs=project?.jobs??[];
    $("job-empty").hidden=Boolean(jobs.length);
    $("jobs").innerHTML=jobs.slice(0,6).map(job=>`<div class="job ${job.error?"error":""}"><strong>${job.kind==="content"?"Nội dung":"Giọng đọc & video"}</strong><small>${new Date(job.created_at).toLocaleString("vi-VN")} · v${job.revision}</small>${esc(statusNames[job.status]??job.status)}${job.status==="running"?`<small>${esc(stageNames[job.stage]??job.stage)}</small>`:""}${job.error?`<small>${esc(errors[job.error.code]??job.error.code)}${job.error.http_status?` · HTTP ${job.error.http_status}`:""}</small>`:""}</div>`).join("");
    const video=currentVideo(project);
    $("video").hidden=!video;$("video-placeholder").hidden=Boolean(video);$("download").hidden=!video;
    if(video){if($("video").getAttribute("src")!==video.result.video_url)$("video").src=video.result.video_url;$("download").href=video.result.video_url;$("qc-note").textContent=`Đã qua kiểm tra video và âm thanh · ${video.result.qc.duration_seconds.toFixed(1)} giây. Bạn cần xem lại video cuối.`;}else{$("video").removeAttribute("src");$("download").removeAttribute("href");$("qc-note").textContent="";}
    const failed=jobs[0]&&["failed","interrupted"].includes(jobs[0].status);
    $("retry").hidden=!failed;$("retry-note").hidden=!failed;
    controls();
  }
  async function projects() {
    const list=await api("/api/projects");
    $("project-picker").innerHTML='<option value="">Chọn dự án…</option>'+list.map(p=>`<option value="${p.id}">${esc(p.document.name)}</option>`).join("");
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
  const guarded=fn=>async event=>{event?.preventDefault();if(busy)return;busy=true;controls();try{await fn();}catch(error){message(error.message,true);}finally{busy=false;controls();}};
  $("save-prompt").addEventListener("click",guarded(async()=>{
    if(!project)project=await api("/api/projects",{name:$("project-name").value,prompt:$("prompt").value});
    else project=await api(`/api/projects/${project.id}/draft`,{revision:project.revision,prompt:$("prompt").value});
    localStorage.setItem("vf-native-project",project.id);renderProject(true);await projects();message("Đã lưu dự án.");
  }));
  async function enqueue(kind,fresh=false) {
    if(dirty)throw new Error("Lưu chỉnh sửa trước khi chạy job.");
    const key=`vf-native-${project.id}-${project.revision}-${kind}`;
    let requestKey=sessionStorage.getItem(key);
    if(!requestKey||fresh){requestKey=crypto.randomUUID();sessionStorage.setItem(key,requestKey);}
    await api(`/api/projects/${project.id}/jobs`,{revision:project.revision,kind,request_key:requestKey});
    await reload(false);message(kind==="content"?"Đã gửi job tạo đề xuất. Bước tiếp theo cần bạn kiểm tra và duyệt.":"Đã gửi job tạo giọng đọc và render video.");
  }
  $("generate").addEventListener("click",guarded(()=>enqueue("content")));
  $("render").addEventListener("click",guarded(()=>enqueue("render")));
  $("retry").addEventListener("click",guarded(()=>enqueue(project.jobs[0].kind,true)));
  $("save-proposal").addEventListener("click",guarded(async()=>{project=await api(`/api/projects/${project.id}/draft`,{revision:project.revision,proposal:readProposal()});renderProject(true);message("Đã lưu nội dung. Phiên bản mới cần duyệt lại.");}));
  $("approve").addEventListener("click",guarded(async()=>{if(dirty)throw new Error("Lưu chỉnh sửa trước khi duyệt.");project=await api(`/api/projects/${project.id}/approve`,{revision:project.revision,reviewer:$("reviewer").value,acknowledged:$("review-check").checked});renderProject(true);message("Đã ghi nhận bạn duyệt phiên bản này. Có thể tạo giọng đọc và video.");}));
  $("upload-image").addEventListener("click",guarded(async()=>{
    if(dirty)throw new Error("Lưu chỉnh sửa nội dung trước khi lưu ảnh.");
    const file=$("image-file").files[0];if(!file)throw new Error("Chọn ảnh trước khi lưu.");if(file.size>15*1024*1024)throw new Error("Ảnh tối đa 15 MB.");
    const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(",")[1]);reader.onerror=()=>reject(new Error("Không đọc được ảnh."));reader.readAsDataURL(file);});
    project=await api(`/api/projects/${project.id}/image`,{revision:project.revision,image_base64:encoded,rights_confirmed:$("image-rights").checked,illustration:$("image-illustration").checked});$("image-file").value="";renderProject(true);message("Đã lưu ảnh. Phiên bản này cần duyệt trước khi render.");
  }));
  $("project-picker").addEventListener("change",guarded(async()=>{if(dirty)throw new Error("Lưu chỉnh sửa trước khi đổi dự án.");clearTimeout(timer);project=$("project-picker").value?await api(`/api/projects/${$("project-picker").value}`):null;if(project)localStorage.setItem("vf-native-project",project.id);renderProject(true);schedule();}));
  $("new-project").addEventListener("click",guarded(async()=>{if(dirty)throw new Error("Lưu chỉnh sửa trước khi tạo dự án mới.");clearTimeout(timer);project=null;localStorage.removeItem("vf-native-project");$("prompt").value=(await api("/api/defaults")).prompt;$("project-name").value="Vinhomes Green Paradise Cần Giờ";$("project-picker").value="";renderProject(true);}));
  $("refresh").addEventListener("click",guarded(()=>reload(!dirty)));
  $("prompt").addEventListener("input",()=>markDirty("prompt"));
  $("scenes").addEventListener("input",()=>{markDirty("proposal");$("narration").textContent=readProposal().narration;});
  window.addEventListener("beforeunload",event=>{if(dirty){event.preventDefault();event.returnValue="";}});
  (async()=>{busy=true;controls();try{csrf=(await api("/api/session")).csrf;$("prompt").value=(await api("/api/defaults")).prompt;await projects();const saved=localStorage.getItem("vf-native-project");if(saved&&[...$("project-picker").options].some(o=>o.value===saved))project=await api(`/api/projects/${saved}`);renderProject(true);await projects();schedule();}catch(error){message(error.message,true);}finally{busy=false;controls();}})();
}
