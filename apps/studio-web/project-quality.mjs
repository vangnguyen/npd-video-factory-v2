// Creation preferences are capability gated; reading an old project never opts it in.
export const newProjectQuality=session=>session?.capabilities?.north_star_quality===true
  ?{production_quality:true,...(session.capabilities.native_narrated_workflow===true?{narrated_workflow:true}:{})}:{};
export const usesNarratedWorkflow=project=>project?.document?.narrated_workflow?.id==='native-narrated-storyboard-workflow-v1'&&project.document.canonical_timeline?.snapshot?.metadata?.native_auto_edit_schema!=='native-auto-edit-timeline-v1';
export function narratedWorkflowGuide(project){
  const doc=project?.document;
  if(!usesNarratedWorkflow(project))return '';
  if(!doc.proposal)return 'Tạo và kiểm tra kịch bản, rồi chọn tư liệu cho từng cảnh.';
  if(!doc.prepared_narration)return 'Mở “Lời đọc & thời lượng đã đo”: duyệt nội dung để tạo lời đọc, nghe kết quả và áp dụng thời lượng từng cảnh.';
  if(!project.approval||project.approval.approval_scope==='narration_only')return 'Tạo preview có tiếng. Xem hình, nghe lời đọc và kiểm tra phụ đề, nhạc trước khi duyệt để render.';
  return 'Đã duyệt preview của phiên bản này. Chọn render, rồi xem và duyệt video cuối trước khi xuất bản.';
}
