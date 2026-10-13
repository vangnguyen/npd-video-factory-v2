# Sửa từ và mốc thời gian transcript qua SQL API

API đã có `POST /api/v1/projects/{project_id}/analyses/{analysis_id}/transcript-words` cho Editor. Đây là phần tiếp tục Master Spec 22/28/39–44/55/64/80 và Wave 3B/3G/3I; toàn bộ Mode B và các wave vẫn chưa đủ nghiệm thu. Mã và bằng chứng được bổ sung từ HEAD `656744e799cac80435895b550924048d984b6d74`; commit cuối và bảo toàn nguồn của thay đổi này do root ghi khi chốt nhánh.

Endpoint dùng `WordReview/revised` chung, các bảng transcript/segment/word và repository timeline hiện có. Mỗi quyết định tường minh tạo revision mới; giữ nguyên transcript, từ, confidence và provenance ASR gốc. Actor lấy từ principal đã xác thực; body không được cấp actor hoặc confidence. Từ/câu sửa tay có confidence=null và `timing_independently_measured=false`. Xác nhận của Editor không phải phép đo độc lập, nghiệm thu của Owner hay duyệt video.

Request phải khớp phiên bản transcript mới nhất, ID transcript được chọn và phiên bản canonical timeline. Sau hoàn tác timeline, có thể phân nhánh từ transcript cũ đang được timeline chọn, nhưng số revision vẫn tăng theo lịch sử SQL mới nhất. Dự án, workspace, asset, analysis và checksum transcript được kiểm tra cùng nhau. Từ không được vượt nguồn, chồng lấn, đi qua gap được khai báo hoặc cắt nguồn đã giữ. Khoảng nguồn/tốc độ hiện có quyết định thời gian phụ đề; video, audio và B-roll không bị dựng lại.

Lưu transcript và cập nhật caption dùng cùng giao dịch SQL. Repository timeline hiện có làm stale preview/render và hủy hiệu lực duyệt cũ; lỗi giữa hai bước rollback toàn bộ. Track khóa được bảo vệ cả khi chỉ metadata của câu không sửa sẽ thay đổi. Caption ở track khác không bị nhân đôi. Layout đã move/delete/sửa tay trả conflict để giữ quyết định của người biên tập; hiện chưa có giao diện quyết định hòa giải layout đó.

Hai lượt trên mã cuối đạt:

| Lượt | Kết quả | Phạm vi |
| --- | --- | --- |
| `sql-transcript-word-review-new-final-n3.log` | 20 passed, 38.74s | Các ca mới của `test_transcript_word_editing.py` |
| `sql-transcript-word-review-regression-final-n4.log` | 75 passed, 2 skipped, 116.64s | 8 module API, gồm toàn bộ 20 ca mới |

Hai lượt chồng lặp, không cộng thành 95 kiểm thử. Hai ca bỏ qua ở `test_timeline_audio_preview.py:106` và `:189` vì WSL không có FFmpeg/FFprobe; không ghi chúng là kiểm chứng media/render thực tế. Log và SHA-256 byte chính xác nằm trong [bằng chứng](north-star/sql-transcript-word-review-evidence.json). Các thử lỗi n1/n2 được giữ, không dùng làm bằng chứng đạt; n4 kiểm chứng bản đã sửa các lỗi fixture và mapper.

SQLite trên file là thật: các ca kiểm tra ghi/read revision, lịch sử cũ, rollback, đồng thời hai transaction với cùng revision, production approval/render records, stale preview và metadata timeline. Race phải có một lần lưu, một conflict, đúng hai transcript và timeline version 2. Fixture dựng schema với `PRAGMA foreign_keys=ON`; implementation flush transcript cha, rồi segment, rồi word. Lượt này chưa có kiểm chứng PRAGMA trên từng connection hoặc ca FK âm riêng, nên không tuyên bố đã kiểm chứng toàn bộ chế độ FK hay PostgreSQL.

ASR, video đầu vào, metadata probe, danh tính và approval trong các ca này là fixture. HTTP dùng ASGITransport chạy API/auth thật trong tiến trình, không phải một server socket thực tế. Không gọi ASR lại, provider bên ngoài, GPU hay dịch vụ trả phí; không có video render/QC mới, publish, deploy hoặc Owner UAT từ lượt SQL này. Bằng chứng Native/ASR/media trước đó vẫn là bộ riêng.

Khoảng trống còn lại: SQL Studio chưa nối UI sửa mốc từ; endpoint chỉ nhận transcript thuộc AutoEditAnalysis, chưa có review cho standalone audio SQL; source clock không liên tục thiếu verified gap map bị chặn; hòa giải caption layout sửa tay, đánh giá ngữ nghĩa scene/highlight mới và PostgreSQL/FK/Docker/media/provider/Owner nghiệm thu vẫn cần bổ sung. Không có destructive migration hoặc sửa schema.

WAVE: 3B/3G/3I SQL component

STATUS: SQL_TRANSACTION_AND_MOCK_ASR_API_TESTS_PASS; full waves PARTIAL

HEAD SHA: source parent `656744e799cac80435895b550924048d984b6d74`; final commit/seal pending root

CAPABILITIES COMPLETED: scoped SQL word/timing endpoint, immutable revisions, canonical caption mapping, source/cut/lock/CAS guards, verified actor, atomic dependency invalidation and rollback

CAPABILITIES PARTIAL: SQL Studio UI, standalone audio review, layout reconciliation, discontinuous clock gap mapping, scene/highlight semantic refresh, PostgreSQL/FK and actual-media acceptance

TESTS: new20 PASS; regression75 PASS/2 SKIP, includes new20

REAL PROVIDER TESTS: none in this SQL component; file-backed SQLite transactions are real persistence tests, not provider acceptance

MOCK TESTS: ASR/video/probe/auth identity/listening acknowledgement/approval fixtures; real API/auth code through ASGITransport

EVIDENCE: [indexed logs and scope](north-star/sql-transcript-word-review-evidence.json)

REGRESSIONS: original ASR rows and timeline history unchanged; media tracks preserved; stale/foreign/checksum/cut/track-lock/manual-caption/concurrent guards pass; root rechecks accepted artifacts when sealing

EXTERNAL BLOCKERS: WSL FFmpeg/FFprobe absent for two skipped tests; PostgreSQL/production/provider/Owner gates remain outside this component

OWNER ACTION REQUIRED: none for continuing safe implementation; no approval or credential request raised here

NEXT WAVE: connect SQL editing UI, add audio/gap/layout workflows and stronger database/media acceptance alongside remaining North Star gaps

IMPLEMENTATION_COMPLETE=NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO; VIDEO_FACTORY_NORTH_STAR_READY=NO. This document does not change global capability counts or readiness.
