// Extends the existing Studio, API, project and upload lifecycle; no provider client.
export function sceneSourceKind(scenes, assets) {
  return scenes.some(scene => assets.some(asset => asset.asset_id === scene.asset_id && asset.content_type.startsWith("video/")))
    ? "mixed" : "storyboard_media";
}

export function initializeMultiInput({api, getState, refresh, refreshProjects, toast, uploadFetch}) {
  const $ = id => document.getElementById(id);
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
  let version = null;
  let scenes = [];
  let busy = 1; // Initial project/session bootstrap must finish before editing.
  function syncControls() {
    $("multi-input-workbench").dataset.loading = busy ? "true" : "false";
    $("multi-input-workbench").querySelectorAll("input, textarea, select, button").forEach(control => {control.disabled=busy>0;});
  }
  function setBusy(active) {busy=Math.max(0,busy+(active?1:-1));syncControls();}
  syncControls();
  function captureScenes() {
    scenes = [...document.querySelectorAll(".mvp-scene")].map((row, index) => {
      const old = scenes[index];
      const choice = row.querySelector("[data-field=media]").value;
      const asset = getState().assets.find(a => a.asset_id === choice);
      const analysis = asset && getState().analyses.find(a => a.asset_id === asset.asset_id && a.status === "succeeded");
      return {...old, narration: row.querySelector("[data-field=narration]").value,
        visual_brief: row.querySelector("[data-field=visual]").value,
        duration_seconds: Number(row.querySelector("[data-field=duration]").value),
        fit: row.querySelector("[data-field=fit]").value,
        transition: row.querySelector("[data-field=transition]").value,
        architectural_render: row.querySelector("[data-field=render]").checked,
        media_strategy: asset ? "user_asset" : choice, asset_id: asset?.asset_id ?? null,
        analysis_id: analysis?.analysis_id ?? null, source_start: asset?.content_type.startsWith("video/") ? old.source_start ?? 0 : 0,
        original_audio: row.querySelector("[data-field=audio]").value, official_render: false};
    });
  }
  function renderScenes() {
    $("mvp-scenes").innerHTML = scenes.map((scene, index) => `
      <article class="mvp-scene" data-index="${index}">
        <strong>Cảnh ${index+1}</strong>
        <label>Lời đọc / phụ đề<textarea data-field="narration" maxlength="180">${escape(scene.narration)}</textarea></label>
        <label>Mô tả hình (không phải dữ kiện)<input data-field="visual" maxlength="500" value="${escape(scene.visual_brief)}"></label>
        <label>Nguồn hình<select data-field="media">
          <option value="motion_graphic">Motion graphic nội bộ (không AI)</option>
          <option value="ai_image">AI image — cần provider được duyệt</option>
          <option value="ai_video">AI video — cần provider được duyệt</option>
          ${getState().assets.filter(a => a.content_type.startsWith("image/") || a.content_type.startsWith("video/")).map(a => `<option value="${escape(a.asset_id)}">${escape(a.filename)}</option>`).join("")}
        </select></label>
        <label>Hiển thị (giây)<input data-field="duration" type="number" min="0.5" max="30" step="0.1" value="${scene.duration_seconds}"></label>
        <label>Khung hình<select data-field="fit"><option value="contain">Giữ toàn ảnh</option><option value="cover">Lấp khung/crop</option></select></label>
        <label>Chuyển cảnh<select data-field="transition"><option value="cut">Cut</option><option value="fade">Fade</option></select></label>
        <label><input data-field="render" type="checkbox" ${scene.architectural_render ? "checked" : ""}> Phối cảnh/kiến trúc (không tự xác nhận chính thức)</label>
        <label>Âm thanh video<select data-field="audio"><option value="mute">Tắt</option><option value="keep">Giữ âm thanh gốc</option></select></label>
        <button type="button" data-up="${index}">↑</button><button type="button" data-down="${index}">↓</button><button type="button" data-remove="${index}">Xóa cảnh</button>
      </article>`).join("");
    [...document.querySelectorAll(".mvp-scene")].forEach((row, index) => {
      const scene = scenes[index];
      row.querySelector("[data-field=media]").value = scene.asset_id ?? scene.media_strategy;
      row.querySelector("[data-field=fit]").value = scene.fit;
      row.querySelector("[data-field=transition]").value = scene.transition;
      row.querySelector("[data-field=audio]").value = scene.original_audio;
    });
    syncControls();
  }
  async function reload() {
    const state = getState();
    version = state.projectId ? await api(`/api/v1/projects/${state.projectId}/content`) : null;
    const doc = version?.snapshot.content;
    $("mvp-kind").value = doc?.input_kind ?? "script";
    $("mvp-original").value = doc?.original_text ?? "";
    $("mvp-script").value = doc?.script ?? "";
    scenes = structuredClone(doc?.scenes ?? []);
    renderScenes();
    $("mvp-video-analysis").innerHTML = state.assets.filter(a => a.content_type.startsWith("video/")).map(a => `<option value="${escape(a.asset_id)}">${escape(a.filename)}</option>`).join("");
    $("mvp-status").textContent = doc ? `${doc.input_kind === "prompt" && !doc.scenes.length ? "Prompt đã lưu; cần lời đọc/script. AI content chưa được cấu hình." : doc.approved ? "Đã duyệt nội dung" : "Draft deterministic cần duyệt"} · ${version.project_version_id} · Không phải kết quả AI` : "Nhập ảnh, video hoặc text; không bắt buộc video.";
    $("mvp-plan").textContent = doc ? JSON.stringify((await api(`/api/v1/projects/${state.projectId}/storyboard-media-plan`)).items.map(s => ({scene:s.scene_id,media:s.strategy,status:s.status})), null, 2) : "";
  }
  async function save(approved = false) {
    captureScenes();
    const state = getState();
    if (!state.projectId) throw new Error("Tạo/chọn project trước.");
    const original = $("mvp-original").value;
    const kind = $("mvp-kind").value;
    const document = {input_kind:kind, original_text:original, script:$("mvp-script").value,
      creative_instructions:kind === "prompt" ? original : "", scenes,
      approved, facts_needing_source:kind === "script" ? [] : ["Cần nguồn cho dữ kiện trong idea/prompt."], generator:"deterministic-user-draft"};
    version = await api(`/api/v1/projects/${state.projectId}/content`, {method:"PUT",body:JSON.stringify({expected_content_version_id:version?.project_version_id ?? null, document})});
    await refresh();
    toast(approved ? "Đã duyệt script/storyboard, chưa duyệt video final." : "Đã lưu phiên bản nội dung; approval cũ bị vô hiệu hóa.");
  }
  const guarded = fn => async event => {
    event?.preventDefault();setBusy(true);
    try {await fn(event);} catch(error) {toast(error.message,true);} finally {setBusy(false);}
  };
  $("mvp-project-form").addEventListener("submit", guarded(async () => {
    let workspace = getState().workspaceId;
    if (!workspace) {
      const created = await api("/api/v1/workspaces",{method:"POST",body:JSON.stringify({slug:`studio-${Date.now()}`,name:"Studio workspace",owner_ref:"studio-owner"})});
      workspace = created.workspace_id;
    }
    const project = await api(`/api/v1/workspaces/${workspace}/projects`,{method:"POST",body:JSON.stringify({slug:`project-${Date.now()}`,name:$("mvp-project-name").value,niche:"custom"})});
    window.localStorage.setItem("npd-studio-project",project.project_id);
    await refreshProjects();
  }));
  $("mvp-upload").addEventListener("change",guarded(async () => {
    if (!getState().projectId) throw new Error("Tạo project trước khi upload.");
    for (const file of $("mvp-upload").files) {
      if (!["image/jpeg","image/png","video/mp4","audio/wav","audio/mpeg"].includes(file.type)) throw new Error("Chỉ JPEG/PNG/MP4 và audio được allowlist.");
      const rights = $("mvp-rights").checked;
      if (!rights) throw new Error("Xác nhận quyền dùng media trước khi upload.");
      const upload = await api("/api/v1/uploads/init",{method:"POST",body:JSON.stringify({project_id:getState().projectId,filename:file.name,media_kind:file.type.startsWith("image/")?"image":file.type.startsWith("audio/")?"music":"video",content_type:file.type,size_bytes:file.size,rights_status:"owned"})});
      for (let part=1;part<=upload.total_parts;part++) {
        const body=file.slice((part-1)*upload.part_size_bytes,part*upload.part_size_bytes);
        const result = await uploadFetch(`/api/v1/uploads/${upload.upload_id}/parts/${part}`,{method:"PUT",body});
        if (!result.ok) throw new Error(`Upload part failed (${result.status}); không tự retry.`);
      }
      await api(`/api/v1/uploads/${upload.upload_id}/complete`,{method:"POST",body:"{}"});
    }
    $("mvp-upload").value="";
    await refresh();
    toast("Đã lưu media qua quarantine/validation hiện có.");
  }));
  $("mvp-draft").addEventListener("click",guarded(async () => {scenes=[];$("mvp-scenes").innerHTML=""; await save(false);}));
  $("mvp-from-media").addEventListener("click",guarded(async () => {
    const media = getState().assets.filter(a => a.asset_class === "source" && /^(image|video)\//.test(a.content_type));
    if (!media.length) throw new Error("Upload media trước. Draft này là caption nội bộ, không phải nội dung AI.");
    scenes = media.map((asset,index) => ({scene_id:`scene_media_${index}`,media_strategy:"user_asset",
      asset_id:asset.asset_id,analysis_id:getState().analyses.find(a => a.asset_id === asset.asset_id && a.status === "succeeded")?.analysis_id ?? null,
      narration:asset.content_type.startsWith("image/") ? "Ảnh minh họa do người dùng cung cấp." : "Video nguồn do người dùng cung cấp.",
      visual_brief:asset.filename,duration_seconds:asset.content_type.startsWith("video/") ? Math.min(30,asset.provenance.media_metadata.duration_seconds) : 6,
      source_start:0,fit:"contain",transition:"cut",architectural_render:false,official_render:false,original_audio:"mute"}));
    $("mvp-kind").value="script";
    $("mvp-original").value=$("mvp-script").value=scenes.map(s=>s.narration).join("\n");
    renderScenes();await save(false);
  }));
  $("mvp-save").addEventListener("click",guarded(() => save(false)));
  $("mvp-analyze-video").addEventListener("click",guarded(async () => {
    const assetId = $("mvp-video-analysis").value;
    if (!assetId) throw new Error("Upload/chọn video trước.");
    await api(`/api/v1/projects/${getState().projectId}/analyze`, {method:"POST", body:JSON.stringify({asset_id:assetId})});
    await refresh();toast("Đã lưu phân tích video. Video có audio vẫn cần ASR thực sự được cấu hình/phê duyệt.");
  }));
  $("mvp-approve").addEventListener("click",guarded(() => save(true)));
  $("mvp-add-scene").addEventListener("click",() => {captureScenes();scenes.push({scene_id:`scene_${Date.now()}`,narration:"",visual_brief:"",duration_seconds:4,media_strategy:"motion_graphic",asset_id:null,analysis_id:null,fit:"contain",transition:"cut",architectural_render:false,official_render:false,original_audio:"mute",source_start:0});renderScenes();});
  $("mvp-scenes").addEventListener("click",event => {
    const button=event.target.closest("button");if(!button)return;
    captureScenes();
    if(button.dataset.remove!==undefined)scenes.splice(Number(button.dataset.remove),1);
    const index=Number(button.dataset.up??button.dataset.down);
    const target=button.dataset.up!==undefined?index-1:index+1;
    if(button.dataset.remove===undefined&&target>=0&&target<scenes.length)[scenes[index],scenes[target]]=[scenes[target],scenes[index]];
    renderScenes();
  });
  $("mvp-timeline").addEventListener("click",guarded(async () => {
    if (!version?.snapshot.content.approved) throw new Error("Lưu và duyệt script/storyboard trước.");
    const state=getState();
    await api(`/api/v1/projects/${state.projectId}/timeline`,{method:"POST",body:JSON.stringify({source_kind:sceneSourceKind(version.snapshot.content.scenes,state.assets),content_version_id:version.project_version_id,expected_timeline_version:state.timeline?.current_version ?? null})});
    await refresh();toast("Timeline đã lưu. Tạo A/V review ở Production Workbench.");
  }));
  return {reload,setBusy};
}
