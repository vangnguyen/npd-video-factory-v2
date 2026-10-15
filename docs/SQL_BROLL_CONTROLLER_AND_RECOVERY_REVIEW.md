# Controller B-roll và phục hồi dữ liệu thử nghiệm

Ngày 2026-10-15. API và canonical engine đã có bằng chứng riêng tại [review backend](SQL_REVIEWED_BROLL_TIMELINE_API.md). Increment này thêm module controller và kiểm chứng khôi phục; việc nối controller vào giao diện Root vẫn còn mở.

Controller `sql-broll-timeline-review.mjs` chỉ làm việc qua GET/PUT reviewed B-roll. Người dùng phải đọc đúng kế hoạch, chọn item đã resolved và xác nhận. Thao tác giữ nguyên lựa chọn trước các lần chờ; GET mới phải khớp bản đã đọc. Yêu cầu được lưu trước PUT, có actor/project/source/media/form/session và cùng request key. Mất phản hồi giữ UNKNOWN; đối chiếu chỉ đọc, gửi lại chỉ khi chứng minh đúng bản cha chưa đổi và có thao tác rõ ràng.

Callback nhận hàm kiểm tra đồng bộ riêng, kiểm tra lại sau native storage getter và thu hồi sau callback. Chỉ xóa đúng bản ghi đang giữ bằng compare-and-remove. Root khi tích hợp phải kiểm tra literal true tại điểm vào, sau từng await và trước ghi trạng thái; đối chiếu current/history/current, parent/receipt và giữ mọi track không liên quan. Controller có sẵn chưa đồng nghĩa UI này đã hoàn tất.

## Kiểm thử controller

- 37 ca riêng đạt; dữ liệu fixture là toàn bộ capture actual main-ASGI 384.811 byte, SHA256 `0a9942826ccc131bf48dc112fc65f9c61bfd5ab1594a6cde49799ae50d19a53c`. Node replay không phải chạy SQL mới.
- Full Studio primary: **1.712 PASS, 0 FAIL, 0 SKIP**, 9.995,1632 ms. Tập 37 nằm trong tổng này, không cộng thêm. Full cùng nguồn trên nhánh tác giả cũng đạt 1.712.
- Root review độc lập: bảy tình huống hành vi và một kiểm tra source pins đạt, 517,3001 ms. Có final native getter đổi provider hoặc token trước callback, foreign request sau PUT, giữ nguyên mount/read, mất phản hồi đối chiếu không PUT lần hai, xóa đúng bản ghi và thu hồi guard, cold token khác không được đọc/xóa yêu cầu cũ. Không còn finding. Source3 trước/sau và ZIP5 gồm source3/contract/freeze khớp.

## Khôi phục trong tiến trình mới

Runner riêng dùng SQLite backup của bộ capture, sao chép đúng hai object, rồi tạo mới repository/service/main-ASGI và danh tính fixture trong tiến trình mới. Không chạy setup planner, resolve, provider hoặc DDL. Ba request GET current, GET history và PUT cùng request cũ trả đúng các DTO/receipt đã lưu.

Toàn bộ **91 bảng** giữ nguyên số dòng và hash nội dung trước/sau; nguồn DB giữ nguyên byte. Hai object giữ nguyên byte/hash. Timeline vẫn có hai version, không tạo version mới. Socket egress bị chặn, 0 attempt. ZIP phục hồi có DB, hai object và report; CRC/hash đều đạt. Đây là phục hồi bộ dữ liệu thử nghiệm, không phải PostgreSQL, full production backup hay nghiệm thu video thật.

Runner khôi phục N1 dừng ở import nhầm tên module trước thao tác file/DB; N2 dùng đúng import và đạt. Helper kiểm ZIP đầu tiên dừng ở giả định ba entry, sau đó đối chiếu đúng năm entry cùng metadata và đạt. Raw helper/source/log đều giữ trong evidence index, không sửa lại kết quả cũ.

## Trạng thái

Controller đã tích hợp source/test; Root UI/mount vẫn chưa nối. Server-backed UNKNOWN recovery của bước chuẩn bị B-roll là increment khác, đang review. Internal resolve/handoff/job observation, stock/generative flow, browser/genuine media/Owner UAT, PostgreSQL/Docker/production và original Mode A/B/A-B-C vẫn mở. Không có provider/render/paid/publish hoặc Owner approval mới. Ma trận giữ 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED; 59 nhóm lớn chưa khép kín.
