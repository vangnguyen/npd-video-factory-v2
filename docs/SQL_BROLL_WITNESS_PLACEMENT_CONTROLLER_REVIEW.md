# Chứng thực yêu cầu và áp dụng B-roll trong Studio

Ngày 2026-10-15; product `9b9f3ed9292f34d86b34458e8d837c0acb4e8398`. Tiến độ Waves 3/8; full Mode A/B và Owner UAT chưa được nghiệm thu.

## Những phần được ghép

Studio có form áp dụng B-roll cố định, ngoài vùng nội dung thay đổi. Người dùng chọn đề xuất, đọc bản hiện tại, chọn cảnh đã có tư liệu, xác nhận tác động đến preview/duyệt cũ rồi gửi. Nút apply legacy mở form, không gửi lệnh trực tiếp. Shot view và giao diện này cùng dùng canonical timeline.

Sau PUT, callback kiểm tra GET hiện tại → history → GET hiện tại, đúng actor/receipt/parent/head và snapshot. Cold restore thiếu `parent_timeline` phải dùng bản cha thực trong history. Âm thanh, phụ đề, nguồn và các clip ngoài lựa chọn được giữ. Kết quả hợp lệ làm stale preview/approval/render cũ và xóa undo/redo cục bộ. Không tìm stock, resolve asset, gọi AI hoặc đăng bài ở bước này.

Private synchronous guard được gọi khi vào callback, sau mỗi await và ngay trước lần ghi state đầu tiên. Native storage getter thay token/asset hoặc yêu cầu khác xuất hiện sau response cuối đều ngăn nhận kết quả. Guard hết hiệu lực khi callback kết thúc. Những request không chứng minh được tiếp tục giữ; không xóa cục bộ để mở khóa.

Controller cho internal resolution đã được ghép riêng: explicit read/select/ack/admit, đọc đúng request/job và retry đúng body/key. Không timer, tự POST, lấy job mới nhất hoặc ghi timeline. Callback chỉ được cài các field kết quả của đúng item. Root UI cho controller này đang được làm tiếp; chưa suy diễn từ controller thành flow UI hoàn chỉnh.

Issuer và verifier cho authorization witness dùng HMAC-SHA256, purpose/version/key ID và literal claims được ký chung. Keyring dùng khóa riêng của Video Factory, SecretStr bị loại khỏi dump/repr, có active/verify-only/revoked và cửa sổ hiệu lực. Không dùng khóa Hub/webhook, token hash công khai hoặc khóa ngẫu nhiên mỗi process. Mặc định `broll_request_witness_enabled=false`, không có khóa được cấu hình thật: **NOT_CONFIGURED**.

Witness chỉ chứng minh authorization và request gốc, `execution_status=NOT_ASSERTED`; không chứng minh request đã/chưa chạy. Issuance/verification không ghi SQL hoặc chạy planner/provider. Sau SQL await phải xác minh lại quyền ghi, credential/roles, nguồn, key và thời hạn. Khóa verify-only còn hiệu lực có thể kiểm witness sau khi registry credential gốc đã được prune. Wrapper settlement trong cùng project lock và pending/UI v2 vẫn là phần tiếp theo; route recovery v1 cũ tiếp tục failclosed khi không có đủ chứng cứ. Không nới lỏng recovery legacy.

## Kiểm chứng

| Phạm vi | Kết quả | Giới hạn |
| --- | --- | --- |
| Witness tác giả | 47 PASS, 66,08 s | 22 crypto + 3 config/secret/process + 17 SQL/ASGI + 5 main; khóa ephemeral fixture |
| Witness độc lập | 2 PASS, 7,65 s | Key rotation/pruned credential và substituted key; SQL DML listener 0 write; đổi quyền khi issue bị chặn |
| Primary witness/recovery main | 10 PASS, 33,75 s tại `5520d40e` | Chứng minh mounts/auth coexist; không real secret hoặc witnessed settlement |
| Placement UI tác giả | 61 ca mới PASS; full Studio 1.819 PASS, 14.837 ms | Saved actual SQL DTO được replay qua DOM/transport/storage fixtures |
| Placement UI độc lập | 4 PASS | Actual shipped controller → extracted Root: normal, microtask foreign pending, native-get asset drift, cold actual-history parent |
| Internal controller tác giả | 24 ca mới PASS, 2.771,5172 ms; own full Studio 1.699 PASS, 10.341,3815 ms | Own base không chứa toàn bộ thay đổi mới của primary; không dùng con số này làm current primary count |
| Internal controller độc lập | 4 PASS, 380,3995 ms | Guard trước nhận kết quả; giữ foreign pending; cold exact job không POST/timeline mutation |
| Primary sau ghép controller + UI | **1.843 PASS, 0 fail/skip**, 16.725,0158 ms | Full Studio tại product `9b9f3ed9`; không cộng các tập có overlap thành số test duy nhất |

Source6 UI, controller3 và bốn callback Word/Audio/Linked/Manual giữ đúng pins đã review. Hai lần broad test UI cũ có 4 lỗi do extracted factories thiếu idle globals; chỉ bổ sung binding fixture, giữ các assertion. Một helper tổng hợp bị lỗi regex Unicode sau khi raw log đã có 1.819 PASS và source before/after bằng nhau; report được lấy lại từ raw log, không chạy lại hoặc sửa log. Bằng chứng trước/sau được lưu.

Raw internal capture 161.766 bytes được giữ đúng cả physical và Git blob bằng attribute riêng `-text whitespace=cr-at-eol`. Commit author đầu đã canonicalize EOL được giữ nguyên trong lịch sử; commit attribute tiếp theo lưu lại đúng raw bytes, không amend. Python provenance/timeline hashes là opaque evidence trong literal context JSON đã xác minh; client không tạo SHA giả từ JSON có float được JS chuẩn hóa.

## Những việc còn mở

- Root UI chọn và theo dõi internal resolution, cùng reciprocal peer busy/dirty/held với các editor khác: P1, Wave 3. Acceptance: chọn rõ saved candidate, exact job proof, không thay timeline, không auto handoff/poll-adopt hoặc xóa UNKNOWN.
- Witnessed settlement trong cùng project SQL lock và pending/UI v2: P1, Waves 3/8. Acceptance: đổi credential cùng actor/exact roles, key restart/rotation/revocation, nguồn đổi giữa await, seal đúng namespace và chặn POST gốc đến muộn; recovery v1 giữ nguyên.
- Browser 1366/1920/2560: NOT_VERIFIED. Inventory đọc được nhưng cổng URL policy từ chối quyền quan sát tab; không thử raw CDP, alternate browser hoặc đường vòng. Node DOM không thay cho browser acceptance.
- Color fidelity: NOT_VERIFIED. Probe nguồn testsrc2 không có matrix/primaries/transfer tags; output BT709. Ép decode nguồn BT709 làm MAE giảm từ 16,7073 xuống 7,6324 tại 1 s, nhưng không chứng minh màu dự định của nguồn thiếu tag. Cần nguồn được gắn tag và kiểm Remotion/ingest riêng; video và raw failure cũ không bị sửa.
- Genuine footage/ASR/semantic Vision, stock/generation, full A/B/C, provider acceptance, production stack/soak và Owner UAT vẫn theo Master Spec. Chưa cấp quyền publish/deploy hoặc tăng ngân sách.

## Báo cáo trạng thái

WAVE: 3/8 (tiến độ tích hợp; chưa đóng toàn wave)

STATUS: reviewed placement UI, internal-job controller và witness issuer/verify đã ghép, kiểm thử và push.

HEAD SHA: `9b9f3ed9292f34d86b34458e8d837c0acb4e8398`; docs riêng sau đó.

CAPABILITIES COMPLETED: phạm vi mã nguồn và fixture/local SQL nêu trên.

CAPABILITIES PARTIAL: internal-job Root UI, witnessed settlement/UI, browser/media/provider/Owner/full Mode A/B và các wave còn lại. Ma trận 5 REAL / 58 PARTIAL / 1 NOT_VERIFIED, 59 nhóm lớn chưa đóng.

TESTS: primary Studio 1.843 PASS; primary witness/recovery main 10 PASS; các tập focused/independent được ghi riêng ở bảng.

REAL PROVIDER TESTS: không có lần gọi mới. Khóa witness chỉ là ephemeral fixture; không cấu hình khóa thật.

MOCK TESTS: Node DOM/transport/storage/clock; actual owned SQLite/ASGI/worker captures riêng; không browser acceptance.

EVIDENCE: [index](north-star/broll-witness-placement-controller-evidence.json), immutable ZIP/raw logs/reviews/source bundles/physical-Git pins.

REGRESSIONS: current primary full Studio PASS; callbacks và backend cũ được giữ; không thay accepted artifacts, main merge hoặc deployment.

EXTERNAL BLOCKERS: browser policy, real providers/keys và Owner acceptance tách riêng; không chặn các việc safe còn lại.

OWNER ACTION REQUIRED: không cần cho implementation hiện tại. Owner đã hoãn listening/UAT.

NEXT WAVE: internal-resolution UI và witnessed recovery wrapper được triển khai/review song song; tiếp tục các gap Master Spec.

SOURCE_PRESERVED=YES; PHASE10_TECHNICALLY_READY=YES; OWNER_UAT_REQUIRED=YES; PHASE10_READY=NO; IMPLEMENTATION_COMPLETE=NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO; VIDEO_FACTORY_NORTH_STAR_READY=NO.

Thao tác xóa cache renderer đã bị xét duyệt tự động chặn, không có lý do chi tiết; cache vẫn còn và không được tính là dung lượng đã giải phóng.
