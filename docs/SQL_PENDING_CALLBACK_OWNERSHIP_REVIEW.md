# Giữ đúng yêu cầu đang chờ khi nhận kết quả chỉnh sửa

Ngày 2026-10-15. Product commit `35999c1bbcc542cdebcae70f362465060e6e004a`.

Bốn luồng sửa từ, xử lý âm thanh, chỉnh shot liên kết và crop thủ công đã có ràng buộc đồng bộ riêng giữa controller và callback Studio. Nếu yêu cầu B thay thế yêu cầu A trong lúc callback đang chờ đọc bằng chứng, kết quả A không được cài vào giao diện, hủy preview hoặc xóa undo trước khi controller phát hiện B.

## Thay đổi

Controller giữ bucket, nguyên văn bản ghi, ticket, nguồn và phiên xác thực của lần gửi. Hàm kiểm tra chỉ sống trong bộ nhớ, đọc lại đúng bản ghi rồi kiểm tra lại toàn bộ phạm vi sau thao tác lưu trữ. Callback phải nhận hàm riêng này và kết quả phải là literal `true`; thiếu hàm, Promise, false hoặc exception đều dừng trước khi đọc hay đổi trạng thái. Hàm bị thu hồi trong `finally` sau callback.

Mỗi callback kiểm tra tại điểm vào, sau từng `await` và ngay trước lần ghi trạng thái đầu tiên. Không thêm trường vào DTO, HTTP, session storage hoặc database. Human approval và publishing vẫn giữ mặc định. B-roll có cơ chế riêng; khôi phục yêu cầu B-roll và reviewed B-roll apply tiếp tục được triển khai riêng.

## Bằng chứng và kiểm thử

- Năm ca tái hiện thực thi controller và hàm Root trên nguồn 347f13 trước sửa: Manual hai giai đoạn, Linked, Audio và Word. Các ca ghi nhận timeline A bị cài trước khi phát hiện yêu cầu B. Raw trước sửa được giữ.
- Tại feature commit `89ca05cc44779663cb89860895ecc96068264e17`, năm ca sửa đạt và xác nhận bản ghi B thực sự xuất hiện, số lượt GET đúng, không adoption/render và B được giữ. Tám suite liên quan đạt 438; full Studio trên base347 đạt 1.585. Các tập này chồng lặp.
- Review độc lập đạt: tám ca mới kiểm tra thay đổi ở lần đọc native cuối và thu hồi hàm kiểm tra; 16 ca chọn lọc literal-true/false/Promise đạt, chồng lặp tập tác giả. Report `processing-callback-pending-review-n1.json` không còn finding.
- Primary giữ nguyên B-roll mới bằng cách chỉ thay bốn hàm Root và chèn bảy ca kiểm thử manual; 11 tệp còn lại được đối chiếu ancestor. Full Studio primary đạt **1.675 PASS, 0 FAIL, 0 SKIP**, 9.226,065 ms. Đây là Node/controller/DOM/transport/storage fixtures dùng DTO SQL đã lưu; không phải chạy browser hay SQL mới.

## Bảo toàn và giới hạn

13 tệp feature, source ZIP, raw trước/sau, review, merge hẹp và Git bundles nằm trong index bằng chứng bên cạnh. Primary đã push lên `codex/vf-north-star-completion-01`, không merge main. Lần chạy helper bảo toàn đầu dừng ở phép đếm nhầm toàn bộ tracked files với audited subset; lần tiếp theo commit/push thành công nhưng Git từ chối bundle chỉ có SHA không có named ref. Helper tiếp tục chỉ tạo và verify bundle bằng branch ref; không reset hay commit lại. Raw helper logs được giữ.

Không có provider/model/render/paid/Owner UAT hoặc production mới từ increment này. Full Mode A/B và A/B/C chưa được nghiệm thu. Ma trận giữ 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED; 59 nhóm lớn chưa khép kín. Owner listening/UAT tiếp tục deferred theo chỉ đạo.
