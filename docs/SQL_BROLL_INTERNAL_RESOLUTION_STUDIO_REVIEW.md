# Phân giải B-roll nội bộ trong Studio

Ngày 2026-10-15; product `632b8171679375d9e2fddbccb5db21bab451f6af`. Phạm vi UI của Wave 3, chưa phải full Mode B hoặc Artifact A.

Người dùng chọn đề xuất/cảnh, đọc nguồn đã lưu, chọn asset có sẵn và xác nhận trước khi tạo job. Các thao tác theo dõi và retry dùng đúng request/job/body/key gốc. Nút internal legacy mở form review rồi dừng trước đường resolve/poll cũ. Không tạo job, đọc latest job, chạy timer hay gọi provider khi mount, đổi lựa chọn hoặc đọc.

Callback nhận kết quả kiểm tra exact job → current item context → exact job. Literal context JSON phải đúng SHA và projection; chỉ chuẩn hóa bốn field mà chính job được phép đổi. Nguồn, timeline, plan, candidate và quyền/custody khác phải giữ nguyên. Private synchronous guard chạy khi vào, sau mọi await/hash và ngay trước lần ghi state đầu tiên, có kiểm tra lại sau native getter.

Kết quả chỉ cài `status`, `updated_at`, `selected_media_asset_id`, `needs_attention` của item tương ứng. Không thay cả plan từ GET, thêm media asset/job, sửa timeline, preview hoặc approval. Asset vẫn cần bước placement có xác nhận riêng trước khi vào canonical timeline. Các form preparation/placement/internal và các editor khác khóa lẫn nhau đúng phạm vi, không tự chặn thao tác của chính controller.

Cold restore có nút mở đúng cảnh đang giữ: đọc bản ghi làm inventory hint, không network/removal/adoption. Lần đọc đầy đủ tiếp theo kiểm token/source/hash trước khi theo dõi/retry. Request failed/cancelled/UNKNOWN tiếp tục được giữ; backend và UI cho terminal settlement đang làm riêng. Không xóa cục bộ để mở khóa, không nhận lại job đang chạy bị gián đoạn.

## Bằng chứng

| Kiểm tra | Kết quả | Phạm vi |
| --- | --- | --- |
| 72 ca mới | PASS | Actual shipped controller → extracted Root, DOM/API/storage mocks |
| Affected 3 files | 229 PASS, 13.043,8737 ms | Gồm 72 internal + 61 placement + 96 preparation; overlap, không cộng lại |
| Full Studio tác giả | 1.915 PASS, 18.029,594 ms | 123 test files trên source9 frozen |
| Review độc lập | 4 PASS, 1.043,5047 ms | Chỉ bốn field, foreign pending microtask, native-get custody drift, cold 0POST/no timeline change |
| Current primary full Studio | **1.915 PASS, 0 fail/skip**, 17.980,7976 ms | Sau import vào source hiện tại, backend/controller giữ nguyên |
| Actual SQLite/ASGI capture N3 | 1 PASS, 7,59 s; 12 HTTP records | Capture riêng trước UI; thêm queued/resolved current context, synthetic metadata/bytes, 0 provider/egress |

Fixture `broll-internal-resolution-studio.json` 207.426 bytes, SHA256 `e8c4c57941fe074902074c098ed51b521a2f0fb37fabe0ccf324d3cd75ef59ca`, giữ nguyên cả physical/Git bằng attribute riêng `-text`. Toàn bộ capture N3 có IDs đồng bộ; không trộn receipt của N2. UI replay không được tính là HTTP/SQL mới.

Source9/ZIP12 đã kiểm pins/CRC. Bốn callback Word/Audio/Linked/Manual và callback placement giữ nguyên. Những lỗi harness trước đó do absent field thành `undefined`, thiếu explicit cold routing và matcher LF trên source CRLF đã được giữ raw; chỉ sửa harness/extraction, không nới assertion hoặc quyền ghi. Không dùng raw lỗi làm acceptance.

## Báo cáo

WAVE: 3

STATUS: Internal resolution UI integrated/preserved; full Wave 3 remains open.

HEAD SHA: `632b8171679375d9e2fddbccb5db21bab451f6af`; docs riêng sau đó.

CAPABILITIES COMPLETED: explicit internal asset selection/admission, exact-job observation/retry, scoped four-field adoption and reciprocal peer guards.

CAPABILITIES PARTIAL: terminal request settlement/UI, witness-aware preparation controller/UI, stock/generation/semantic Vision, browser/genuine-source/full A/B/C và các wave khác. Ma trận 5 REAL / 58 PARTIAL / 1 NOT_VERIFIED; 59 nhóm lớn chưa đóng.

TESTS: current primary full Studio1.915 PASS; independent4 PASS; các tập overlap ở bảng, không tổng hợp thành số case duy nhất.

REAL PROVIDER TESTS: none. Không ASR/TTS/media decode/render mới trong increment UI này.

MOCK TESTS: DOM/API/storage/clock replay actual N3 DTO; fixture auth/metadata, không browser acceptance.

EVIDENCE: [index](north-star/broll-internal-studio-evidence.json), source ZIP, raw fixture/capture, tests, reviews, narrow patch and bundles.

REGRESSIONS: previous callbacks/controllers/backend retained; full Studio PASS; no accepted media replacement, merge, migration or deployment.

EXTERNAL BLOCKERS: browser URL policy denied observation; no workaround. Provider/Owner/production acceptance remains separate.

OWNER ACTION REQUIRED: none for safe continuation; Owner listening/UAT deferred.

NEXT WAVE: reviewed known-terminal internal settlement, pending v2/witness controller and later their explicit UI controls; other safe Master Spec gaps.

SOURCE_PRESERVED=YES; PHASE10_TECHNICALLY_READY=YES; OWNER_UAT_REQUIRED=YES; PHASE10_READY=NO; IMPLEMENTATION_COMPLETE=NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO; VIDEO_FACTORY_NORTH_STAR_READY=NO.

Tác vụ xóa cache renderer bị cơ chế phê duyệt tự động chặn, không trả lý do chi tiết. Cache vẫn được giữ, không có dung lượng giải phóng được ghi nhận từ lần đó.
