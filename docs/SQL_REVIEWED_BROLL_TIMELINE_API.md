# Áp dụng B-roll có đối chiếu trên canonical timeline

Ngày 2026-10-15. Product `ce74fa5008a85488df4115d925409fd4f8d91f1d`.

API mới `GET/PUT /api/v1/projects/{project_id}/timeline/broll-review/{media_plan_id}` cho người có quyền đọc/chỉnh sửa dự án. GET chỉ đọc ngữ cảnh. PUT yêu cầu xác nhận rõ, đúng timeline/version/context, request key, danh sách item duy nhất và lựa chọn thay clip cũ. Không gọi provider hoặc tự resolve tư liệu.

## Hành vi

Một giao dịch SQL giữ đúng project, analysis, timeline, plan, item, provenance và asset. Hash ngữ cảnh ràng buộc snapshot cha, nguồn/transcript hiện hành, cấu hình và toàn bộ kế hoạch, thông tin quyền, storage provider/object/version/size/checksum/provenance của nguồn và tư liệu. Tư liệu video cần thời lượng đo dương hữu hạn, không nhận bool; hình học và bằng chứng đã lưu phải thống nhất. Transcript_id None theo hợp đồng kế hoạch cũ vẫn hợp lệ; ID khai báo rõ phải khớp bản đã materialize.

Thay đổi sử dụng `place_broll` và `commit_mutation_in_session` hiện có: giữ timeline là nguồn chỉnh sửa chuẩn, mapping vị trí qua trim/move/speed, giữ âm thanh gốc, cấm chồng clip và track khóa, lưu đúng một version/receipt rồi hủy hiệu lực preview/approval/render cũ trong cùng giao dịch. Không sửa nguồn, plan, file hoặc cho phép đăng. Tư liệu quyền unknown chỉ dùng review, publishing_allowed vẫn false.

Gửi lại cùng key/nội dung/người sửa khi version còn hiện hành trả đúng biên nhận, không tạo version mới. Đổi nội dung/người sửa, nguồn hoặc metadata; version bị thay thế; biên nhận sai workspace/parent đều bị từ chối. GET kế hoạch B không trả biên nhận kế hoạch A. Biên nhận của media binding cũ không chứng nhận một lần đọc mới. Reader phải giữ UNKNOWN khi không chứng minh được lần gửi trước.

## Kiểm chứng

- Bộ cuối N3: **39 PASS**, 93,19s = 34 ca mới và 5 hồi quy B-roll cũ. Có CAS/replay/song song, drift storage/size/version/provenance, quyền/license/checksum/scope, unknown review-only, thay clip rõ ràng, rollback cả history/preview/receipt khi lỗi, corrupt receipt và route actual main/auth/no-store. Không bỏ qua ca.
- Review độc lập N1 phát hiện 3 P2 với 6 expected-good FAIL/3 PASS: receipt khác plan, các identity khai báo mâu thuẫn và thời lượng bool/zero. Raw nguồn, ZIP, log trước sửa giữ nguyên. N2 chạy lại đúng 9 assertions trên SQL/main-ASGI mới: **9 PASS**, 34,87s; AST assertions giữ nguyên, source4/ZIP4 trước/sau khớp. Không còn finding.
- Capture `broll-timeline-review-actual-asgi-n1.json`: năm request qua actual main (GET context, PUT apply, GET current, GET history, PUT replay), version1→2 và một mutation; replay bằng đúng response đã lưu, chỉ replayed thay đổi. Đầy đủ project/analysis/resolved plan/assets/DTO và source pins. Socket egress sau setup bị chặn, 0 attempt.

N1 bộ tác giả có 30 PASS/2 FAIL do hai lỗi test mới: tên field preview sai và fixture foreign project dùng NULL bị schema chặn. N2 có 31 PASS/1 FAIL do kiểm tra giữ nguyên nhầm cả track B-roll vốn phải đổi. N3 sửa các fixture/assertions này, giữ kiểm tra mọi track khác. Hardening source sau review là thay đổi riêng có raw/pins; không relabel kết quả cũ.

## Phạm vi còn mở

Đây là source/API/SQL fixtures với byte tư liệu, probe/ASR và danh tính mô phỏng; setup đã resolve internal media fixture. Không decode/render video mới, browser, provider thật, Owner hoặc PostgreSQL acceptance. Lock order và làm mới ORM đã được review nhưng chưa chạy PostgreSQL. Endpoint cũ được giữ tương thích; Studio mới/controller đang triển khai riêng, legacy resolve/polling và B-roll UNKNOWN recovery vẫn mở. Không suy ra Mode A/B hoặc A/B/C hoàn tất từ increment này.

Source4, Git bundle, actual capture, review và raw failures nằm trong index bên cạnh. Nhánh an toàn đã push; không merge main, deploy hay đăng ngoài. Ma trận vẫn 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED; 59 nhóm lớn chưa khép kín.
