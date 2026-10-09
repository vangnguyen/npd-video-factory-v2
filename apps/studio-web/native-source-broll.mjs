// Saved recommendations and explicit placement over the canonical Source timeline.
import {validateReviewedVisionContext,validateReviewedRequest} from './native-media-planner.mjs';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const same=(a,b)=>JSON.stringify(a,(k,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(key=>[key,v[key]])):v)===JSON.stringify(b,(k,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(key=>[key,v[key]])):v);
export function validateReviewedSourceBroll(plan,project,workspaceId){
  const p=plan.provenance??{};
  if(p.algorithm!=='native-source-broll-v2'&&p.reviewed_vision===undefined&&p.reviewed_input===undefined)return plan;
  const context=validateReviewedVisionContext(p.reviewed_vision,{workspace_id:workspaceId,project});
  if(p.algorithm!=='native-source-broll-v2'||p.reviewed_input?.schema_version!=='native-reviewed-source-broll-input-v1'
    ||!Number.isInteger(p.reviewed_input.source_revision)||p.reviewed_input.source_revision<1||!(/^[a-f0-9]{64}$/).test(p.reviewed_input.source_document_sha256??'')
    ||plan.project_id!=='prj_'+project.id||plan.workspace_id!=='native-local'||p.semantic_vision_used!==context.semantic_vision_used
    ||p.prediction_confidence_calibrated!==false||p.provider_dispatches!==0||p.recommendation_only!==true||p.requires_manual_selection_and_apply!==true
    ||plan.publishing_blocked!==true||!Array.isArray(plan.items)||plan.items.length>200)throw new Error('Kế hoạch B-roll không khớp bằng chứng Vision.');
  for(const item of plan.items)for(const candidate of item.provenance.supporting_candidates??[]){
    const asset=p.reviewed_input.assets?.[candidate.asset_id],original=context.items.find(v=>v.asset_id===asset?.provenance.native_asset_id);
    if(original){const expected={request:original.request,response_id:original.response_id,response_sha256:original.response_sha256,
        cost_operation_id:original.cost_operation_id,mock:original.mock,semantic_inference_performed:original.semantic_inference_performed,
        confidence_calibrated:false,full_evidence_in:'plan.provenance.reviewed_vision'};
      if(candidate.checksum_sha256!==original.source_sha256||candidate.confidence!==null||!same(candidate.reviewed_vision,expected)
        ||original.mock&&(candidate.score_basis!=='lexical overlap in saved filename, description and tags; not semantic Vision'
          ||!['uncalibrated sampled pixel sharpness/brightness heuristic',null].includes(candidate.quality_basis)))throw new Error('Điểm tư liệu không khớp Vision đã xem.');
    }else if(candidate.reviewed_vision!==undefined)throw new Error('Tư liệu chưa có kết quả Vision đã xem.');
  }
  return plan;
}
export function sourceBrollPlans(project,workspaceId) {
  const latest=new Map();
  for(const record of project?.document?.source_broll_plans??[]) {
    const plan=record.plan;
    if(plan)validateReviewedSourceBroll(plan,project,workspaceId);
    if(plan&&(!latest.has(plan.media_plan_id)||latest.get(plan.media_plan_id).version<plan.version))latest.set(plan.media_plan_id,plan);
  }
  return [...latest.values()];
}
export function sourceBrollRequest(project,action,{planId,itemId,assetId,replace=false,workspaceId,reviewedVision=[]}={}) {
  const state=project?.document?.canonical_timeline;
  if(!state||!Number.isInteger(project.revision)||project.archived)throw new Error('Mở bản dựng nguồn đang hoạt động trước khi sửa B-roll.');
  const payload={expected_version:state.version};
  if(action==='create'){
    if(!Array.isArray(reviewedVision)||reviewedVision.length>50)throw new Error('Chọn kết quả Vision hợp lệ.');
    if(new Set(reviewedVision.map(v=>v.vision_id)).size!==reviewedVision.length)throw new Error('Mỗi kết quả Vision chỉ được chọn một lần.');
    reviewedVision.forEach(validateReviewedRequest);
    if(reviewedVision.length)payload.reviewed_vision=structuredClone(reviewedVision);
  }
  if(action!=='create') {
    const plan=sourceBrollPlans(project,workspaceId).find(p=>p.media_plan_id===planId),item=plan?.items.find(i=>i.media_plan_item_id===itemId);
    if(!item)throw new Error('Gợi ý B-roll đã thay đổi. Tải lại dự án.');
    Object.assign(payload,{media_plan_id:plan.media_plan_id,expected_plan_version:plan.version});
    if(action==='select') {
      const candidate=(item.provenance.supporting_candidates??[]).find(c=>c.asset_id===assetId);
      if(!candidate||candidate.rights_status==='unknown'||candidate.rights_status==='restricted')throw new Error('Chọn tài sản đã xác nhận quyền sử dụng trong Assets.');
      Object.assign(payload,{item_id:itemId,asset_id:assetId});
    } else if(action==='apply') {
      if(item.status!=='resolved'||!item.selected_media_asset_id)throw new Error('Lưu lựa chọn tài sản trước khi đặt B-roll.');
      Object.assign(payload,{item_ids:[itemId],replace_plan_clips:Boolean(replace)});
    } else throw new Error('Thao tác B-roll không hợp lệ.');
  }
  return {revision:project.revision,action,payload};
}
export function sourceBrollMarkup(project,{workspaceId}={}) {
  return `<details><summary>B-roll hỗ trợ</summary><p class="hint">Thêm ảnh/video tại Assets, rồi tạo kế hoạch. Khi chưa chọn Vision ngữ nghĩa đã xem, xếp hạng theo tên, mô tả và tag; dùng điểm pixel sáng/nét đã đo khi mức liên quan bằng nhau. Điểm pixel chưa hiệu chuẩn. Tư liệu stock/AI cần tìm hoặc tạo tại Assets, kiểm tra rồi thêm vào dự án. Mỗi gợi ý cần chọn và đặt riêng, giữ âm thanh gốc.</p>
    <div data-broll-review-host></div>
    <button type="button" data-source-broll="create">Tạo kế hoạch B-roll</button>
    ${sourceBrollPlans(project,workspaceId).map(plan=>`<section><p>Kế hoạch v${plan.version} · ${plan.provenance?.reviewed_vision?(plan.provenance.semantic_vision_used?'Vision đã xem · dự đoán chưa hiệu chuẩn':'Mô phỏng đã xem · không bổ sung điểm nhận diện/chất lượng'):esc(plan.provider_status.semantic_vision)} · ${plan.unresolved_items} gợi ý chưa chọn</p>${plan.provenance?.reviewed_vision?`<p class="hint">${plan.provenance.reviewed_vision.items.map(v=>`${esc(v.asset_id)} · phản hồi ${esc(v.response_id)} · chi phí ${esc(v.cost_operation_id)} · ${v.mock?'mô phỏng':'dự đoán chưa hiệu chuẩn'}`).join('<br>')}. Nguồn gốc đầy đủ lưu trong kế hoạch; chưa có hóa đơn thực tế. Không thay thế quyền sử dụng, tracking, crop hoặc QC.</p>`:''}${plan.items.map(item=>{
      const decision=item.broll,evidence=plan.media_assets.find(a=>a.media_asset_id===item.selected_media_asset_id);
      const candidates=item.provenance.supporting_candidates??[];
      return `<article data-broll-item="${esc(item.media_plan_item_id)}" data-broll-plan="${esc(plan.media_plan_id)}"><strong>${esc(decision.broll_intent)}</strong><p>${esc(decision.search_query)} · nguồn ${decision.placement_start_seconds.toFixed(2)}–${decision.placement_end_seconds.toFixed(2)}s · ${(decision.placement_end_seconds-decision.placement_start_seconds).toFixed(2)}s</p><p class="hint">Độ tin cậy ${decision.provenance?.semantic_provider_used?'dự đoán chưa hiệu chuẩn':'heuristic'}: ${decision.confidence} · phân tích nguồn đã lưu. Crop mặc định; cần xem lại chủ thể.</p>
      <label>Tài sản<select data-broll-asset><option value="">Chọn trong thư viện dự án</option>${candidates.map(c=>`<option value="${esc(c.asset_id)}" ${item.source_asset_id===c.asset_id?'selected':''} ${['unknown','restricted'].includes(c.rights_status)?'disabled':''}>${esc(c.filename)} · ${c.relevance_score} · ${esc(c.license)}</option>`).join('')}</select></label>
      <button type="button" data-source-broll="select">Lưu lựa chọn</button>${evidence?`<p class="hint">Nguồn: ${esc(evidence.provider)} · ${esc(evidence.source_reference)} · ${esc(evidence.license)}. Quyền: xác nhận của người tải lên, chưa kiểm chứng độc lập.</p>`:''}
      <label class="check"><input type="checkbox" data-broll-replace> Thay clip đã đặt từ gợi ý này</label><button type="button" data-source-broll="apply" ${item.status==='resolved'?'':'disabled'}>Đặt vào timeline</button></article>`;
    }).join('')}</section>`).join('')}</details>`;
}
