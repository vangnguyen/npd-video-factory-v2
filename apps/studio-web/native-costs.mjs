const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
export const vnd = value => value === null || value === undefined ? 'Chưa rõ' : /^\d{1,13}(\.\d{1,6})?$/.test(String(value)) ? `${Number(value).toLocaleString('vi-VN', {maximumFractionDigits:6})} ₫` : 'Chưa rõ';
const status = {dispatch_intent:'Đã giữ chỗ · chưa rõ kết quả',response_received:'Đã nhận phản hồi',outcome_unknown:'Chưa rõ kết quả',rejected:'Yêu cầu bị từ chối',needs_approval:'Chờ duyệt chi phí · chưa gửi'};
export function costSummaryHTML(summary) {
  if (!summary) return '<p class="hint">Chọn một dự án để xem chi phí.</p>';
  const records=Array.isArray(summary.records)?summary.records:[];
  return `<p><strong>Ước tính: ${esc(vnd(summary.estimated_cost_total))}</strong><br><strong>Đã tính phí: ${esc(vnd(summary.actual_cost_total))}</strong></p>`+
    `<p class="hint">${records.length} thao tác được ghi nhận. ${esc(summary.unknown_actual_cost_operations??0)} thao tác chưa có số tiền tính phí. Số đã biết: ${esc(vnd(summary.known_actual_cost_subtotal))}.</p>`+
    '<p class="hint">Tổng chỉ gồm thao tác được ghi nhận; chưa bao gồm đầy đủ lịch sử và chi phí máy chạy. Ước tính hoặc giữ chỗ ngân sách chưa phải số tiền đã tính phí.</p>'+
    (summary.needs_approval?'<p role="status">Cần kiểm tra và duyệt chi phí trước yêu cầu AI tiếp theo.</p>':'')+
    (summary.needs_attention?'<p role="status">Có yêu cầu chưa rõ kết quả. Kiểm tra nhà cung cấp trước khi gửi lại.</p>':'')+
    (records.length?`<details><summary>Xem từng thao tác</summary>${records.map(row=>`<p><strong>${esc(row.provider)} · ${esc(row.operation)}</strong><br>${esc(status[row.status]??'Chưa rõ trạng thái')}<br>Ước tính ${esc(vnd(row.estimated_cost))} · đã tính phí ${esc(vnd(row.actual_cost))}</p>`).join('')}</details>`:'');
}
