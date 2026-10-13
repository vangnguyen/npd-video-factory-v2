# Audio SQL, stock SQL và B-roll nguồn

Ba phần được triển khai song song, nối vào engine hiện có và lưu thành ba commit riêng. Toàn bộ North Star giữ nguyên phạm vi. Đây là hoàn thiện các component của Wave 3/5/8/15; chưa nghiệm thu toàn bộ các wave hoặc Mode A/B.

Audio tải lên có schema độc lập, hàng đợi, claim/lease/heartbeat và lịch sử transcript bất biến. API cho đọc file gốc, sửa đoạn/từ, chọn lại phiên bản và hủy. Hash, MIME, metadata intake, workspace và cấu hình được kiểm trước xử lý và trước hoàn tất. Kết quả đến muộn không thể ghi đè claim mới hoặc tác vụ đã hủy; provider chỉ được dispatch một lần cho mỗi thao tác ASR. Mặc định chưa cấu hình provider. File nghe hỗ trợ byte Range, xác minh nội dung trước streaming, không cache, không chặn event loop khi đọc/hash và dọn file tạm khi mất kết nối. Audio đã gắn với caption canonical sẽ trả conflict và rollback; mapping audio/caption cùng panel Studio SQL vẫn còn mở.

Stock SQL dùng guard bền vững tại cả API và worker với session factory thật. API/CDN có lease riêng; cache hợp lệ không gọi wire. Quota/cooldown được lưu theo cấu hình và workspace; ngân sách nằm trong audit, không được dùng để né quota bằng cách đổi budget. Chờ chưa gọi diễn ra trước safety reservation và không mất retry cycle. Giới hạn ba chu kỳ gọi thực, fencing cho running/failure/completion/deferral và giữ terminal cancellation. Lịch định kỳ chỉ đưa lại tác vụ stock miễn phí đã có bằng chứng chờ và đã đến hạn; không redispatch generation trả phí. Migration chỉ bổ sung bảng. Planner search bị quota hiện lưu plan failed, chưa có UX hẹn lại. Global quota, cache giới hạn dung lượng/eviction/retention và PostgreSQL/Redis production còn mở.

Thứ tự B-roll nguồn mặc định là tư liệu tải lên → stock có giấy phép → thư viện → ảnh AI → video AI; cấu hình server có thể đổi thứ tự và phải giữ đủ năm tier. Phiên đóng băng source/ASR/transcript/plan/asset inventory/provider/budget, dùng lại job/import/cost engine hiện có, mỗi bước chỉ thực hiện một chuyển trạng thái. Kết quả chưa rõ phải được xử lý qua cơ chế recovery của child rồi quan sát lại; không tự gửi lại yêu cầu tạo tư liệu. Quyền unknown giữ trạng thái cần kiểm tra hoặc dùng fallback hợp lệ. Đặt B-roll và biên nhận dùng cùng giao dịch canonical timeline, không trao quyền duyệt video hay publishing.

Plan Vision đã review tạo derivative có identity mới và giữ nguyên bytes/hash của lịch sử gốc. Không cấp review Vision cho tài sản mới. Khi nhân bản dự án, plan reviewed và derivative được lưu nguyên văn trong lịch sử không mang thẩm quyền; child cần plan/review mới. UI có chọn gợi ý, phiên tìm tư liệu, đọc trạng thái, xử lý/quan sát một bước và đặt tường minh. Đã sửa thử lại nhầm phiên, bước quan sát recovery bị khóa và tải phụ trợ làm mất lựa chọn. Backend giữ CAS/quyền ngay cả khi trình duyệt đổi ngữ cảnh.

Tài liệu Pexels hiện liệt kê `/v1/videos/search` và `/v1/videos/videos/:id`; đã đối chiếu [tài liệu chính thức](https://www.pexels.com/api/documentation/) và giữ đường dẫn hiện có. Đây là kiểm tra tài liệu, không phải nghiệm thu API có credential thật.

WAVE: 3B/3H/5A/8F/15 components

STATUS: IMPLEMENTED_AND_MOCK_TESTED; actual local file/SQLite/HTTP/browser/renderer/restore evidence; full waves PARTIAL

HEAD SHA: audio dbc457d621d2bc739da433c866793815ab66ba0b; stock bdb50722ba94542e50379aed06c7ea9443a8533e; B-roll 3ff8e2c5dd33f981dd8c89be12239ba40b122cf9; final preservation HEAD recorded in recovery/20261007/parallel-media-program-state.json

CAPABILITIES COMPLETED: independent uploaded-audio SQL workflow/immutable review/source playback; SQL wire quota and due-only stock recovery; five-tier configurable Source resolver; atomic canonical Apply; rights-safe fallback; reviewed derivative/duplication custody; scoped Source UI and backup counts

CAPABILITIES PARTIAL: SQL audio Studio/canonical caption mapping/local CPU runtime; scheduled planner-search retry; global quota/cache limits/retention/health; broad semantic relevance; configured generation budgets/rights/quality; real provider, non-developer, Owner, full original A/B/C and production acceptance

TESTS: batches below overlap; do not add them. Full Studio suite is a new run.

| Batch | PASS | Scope |
|---|---:|---|
| Audio + source file | 56 | 27 audio +29 delivery; SQLite/WAV + ASR fixture |
| API/worker adjacent | 44 | transcript/models/migration + queue integration |
| SQL/shared stock | 74 | quota/parser/cache/planner/resolver/migration |
| Native Phase 10/auth/quality | 66 | protected HTTP and quality regression |
| Native shared stock | 40 | actual Windows component regression |
| Native B-roll priority | 35 |13 resolver + Source/Vision/HTTP |
| Native duplication | 6 |2 derivative custody +4 existing duplication |
| Studio | 822 |11 new B-roll UI cases included |

REAL PROVIDER TESTS: no new inference, provider API, credentialed request or paid operation. Saved licensed benchmark audio/local ASR is reused; original source/ASR records remain exact. CPU encoding, checksum, SQLite and local HTTP are real.

MOCK TESTS: ASR API, stock/generation/Vision responses, quotas, credentials, identity and review are explicit fixtures; long waits use fixture clocks, not wall-clock production soak.

EVIDENCE: [indexed evidence](north-star/parallel-media-evidence.json),61-file portable archive. Separate offline rehearsal produces full-effects preview and final1080×1920 video10.5s/QC PASS, with exact231-entry cold restore in a new process. Browser creates/resolves/applies one owned-asset suggestion into canonical v6 with no approval; this browser timeline has no new preview/render/QC. DOM1366/1920/2560 fits horizontally; exported screenshot dimensions differ from logical viewport. This is not Owner usability acceptance.

REGRESSIONS: immutable original transcripts, source bytes, non-B-roll tracks and previously accepted artifacts preserved. Intermediate failures are retained: an outdated strict Phase10 capability expectation, helper blocking Windows asyncio loopback, and helper treating receipt entry count as an array. Corrected runs pass. Missing agent `/tmp` logs were not fabricated; actual final logs were written to the Windows recovery directory.

EXTERNAL BLOCKERS: genuine provider credential/rights/quality acceptance, separate Owner UAT and production approval remain. They do not block remaining safe implementation.

OWNER ACTION REQUIRED: none for continued implementation. Deferred listening/UAT remains deferred; no publishing, new spending or production deployment enabled.

NEXT WAVE: SQL audio UI and canonical caption review; planner retry scheduling and full cache limits/retention; remaining original media/provider/platform/acceptance gaps.

Normal lifecycle cleanup completed for the new short media/cold/browser roots. One earlier cold helper encountered Windows long-path cleanup failure; its exact retained root and read-only inventory are recorded. That root was not retried or deleted. Eight previously policy-blocked roots and the older retained OS/browser roots were not touched.

SOURCE_PRESERVED=YES is established only by final source seal. PHASE10_TECHNICALLY_READY=YES; OWNER_UAT_REQUIRED=YES; PHASE10_READY=NO. Matrix remains5 IMPLEMENTED_REAL/58 PARTIAL/1 NOT_VERIFIED,59 unclosed groups. IMPLEMENTATION_COMPLETE=NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO; VIDEO_FACTORY_NORTH_STAR_READY=NO.
