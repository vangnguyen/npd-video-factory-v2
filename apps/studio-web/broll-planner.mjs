export function compatibleBrollPlans(plans, analysis) {
  return (plans??[]).filter(plan=>plan.configuration?.purpose==='supporting_broll' && plan.status==='draft'
    && plan.analysis_id===analysis?.analysis_id && plan.provenance?.transcript_id===(analysis?.transcript?.transcript_id??null));
}

export function selectedBrollAsset(item, assetId) {
  const candidate=(item?.provenance?.supporting_candidates??[]).find(value=>value.asset_id===assetId);
  if(!candidate)throw new Error('Chọn tư liệu từ danh sách đã lưu của đề xuất này.');
  return {asset_id:candidate.asset_id};
}

export function brollApplyPayload(timeline, plan, itemIds, replacePlanClips=false) {
  if(!timeline || plan?.analysis_id!==timeline.source_analysis_id)throw new Error('B-roll phải dùng cùng nguồn với timeline.');
  if(plan.provenance?.transcript_id!==(timeline.snapshot.metadata?.transcript_revision?.transcript_id??null))
    throw new Error('Transcript đã thay đổi. Tạo đề xuất mới trước khi áp dụng.');
  const unique=[...new Set(itemIds)];
  if(!unique.length || unique.length!==itemIds.length || unique.some(id=>!plan.items.some(item=>item.media_plan_item_id===id&&item.status==='resolved')))
    throw new Error('Chọn ít nhất một đề xuất đã có tư liệu sẵn sàng.');
  return {expected_version:timeline.current_version,item_ids:unique,replace_plan_clips:replacePlanClips};
}
