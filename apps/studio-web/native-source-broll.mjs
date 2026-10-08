// Saved recommendations and explicit placement over the canonical Source timeline.
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
export function sourceBrollPlans(project) {
  const latest=new Map();
  for(const record of project?.document?.source_broll_plans??[]) {
    const plan=record.plan;
    if(plan&&(!latest.has(plan.media_plan_id)||latest.get(plan.media_plan_id).version<plan.version))latest.set(plan.media_plan_id,plan);
  }
  return [...latest.values()];
}
export function sourceBrollRequest(project,action,{planId,itemId,assetId,replace=false}={}) {
  const state=project?.document?.canonical_timeline;
  if(!state||!Number.isInteger(project.revision)||project.archived)throw new Error('Mở bản dựng nguồn đang hoạt động trước khi sửa B-roll.');
  const payload={expected_version:state.version};
  if(action!=='create') {
    const plan=sourceBrollPlans(project).find(p=>p.media_plan_id===planId),item=plan?.items.find(i=>i.media_plan_item_id===itemId);
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
export function sourceBrollMarkup(project) {
  return `<details><summary>B-roll hỗ trợ</summary><p class="hint">Thêm ảnh/video tại Assets, rồi tạo kế hoạch. Xếp hạng theo tên, mô tả và tag; dùng điểm pixel sáng/nét đã đo khi mức liên quan bằng nhau. Điểm pixel chưa hiệu chuẩn; chưa có Vision ngữ nghĩa. Tư liệu stock/AI cần tìm hoặc tạo tại Assets, kiểm tra rồi thêm vào dự án. Mỗi gợi ý cần chọn và đặt riêng, giữ âm thanh gốc.</p>
    <button type="button" data-source-broll="create">Tạo kế hoạch B-roll</button>
    ${sourceBrollPlans(project).map(plan=>`<section><p>Kế hoạch v${plan.version} · ${esc(plan.provider_status.semantic_vision)} · ${plan.unresolved_items} gợi ý chưa chọn</p>${plan.items.map(item=>{
      const decision=item.broll,evidence=plan.media_assets.find(a=>a.media_asset_id===item.selected_media_asset_id);
      const candidates=item.provenance.supporting_candidates??[];
      return `<article data-broll-item="${esc(item.media_plan_item_id)}" data-broll-plan="${esc(plan.media_plan_id)}"><strong>${esc(decision.broll_intent)}</strong><p>${esc(decision.search_query)} · nguồn ${decision.placement_start_seconds.toFixed(2)}–${decision.placement_end_seconds.toFixed(2)}s · ${(decision.placement_end_seconds-decision.placement_start_seconds).toFixed(2)}s</p><p class="hint">Độ tin cậy heuristic: ${decision.confidence} · phân tích nguồn đã lưu. Crop mặc định; cần xem lại chủ thể.</p>
      <label>Tài sản<select data-broll-asset><option value="">Chọn trong thư viện dự án</option>${candidates.map(c=>`<option value="${esc(c.asset_id)}" ${item.source_asset_id===c.asset_id?'selected':''} ${['unknown','restricted'].includes(c.rights_status)?'disabled':''}>${esc(c.filename)} · ${c.relevance_score} · ${esc(c.license)}</option>`).join('')}</select></label>
      <button type="button" data-source-broll="select">Lưu lựa chọn</button>${evidence?`<p class="hint">Nguồn: ${esc(evidence.provider)} · ${esc(evidence.source_reference)} · ${esc(evidence.license)}. Quyền: xác nhận của người tải lên, chưa kiểm chứng độc lập.</p>`:''}
      <label class="check"><input type="checkbox" data-broll-replace> Thay clip đã đặt từ gợi ý này</label><button type="button" data-source-broll="apply" ${item.status==='resolved'?'':'disabled'}>Đặt vào timeline</button></article>`;
    }).join('')}</section>`).join('')}</details>`;
}
