# SQL storyboard variants và tải media hữu hạn

SQL S2 tạo sáu dự án con từ storyboard hiện có, trên bốn hình học. Nội dung, asset, timeline và định danh scene/clip được ánh xạ riêng. Narration giữ cấu trúc track; crop cần kiểm tra được đánh dấu. Child được tạo cùng transaction với receipt/history; source, bytes và lease được kiểm tra lại sau các thao tác SQL chờ cuối. Hủy hai lần chờ luồng copy đóng. Hết lease hoặc asset đổi bytes rollback child và trạng thái ready. Idempotency không tự copy lại trạng thái không rõ.

Approval và quyền sử dụng không được kế thừa. Child là draft, rights unknown, không có UploadSession hay bằng chứng phân tích giả. Kiểm tra độc lập actual SQLite/Local xác nhận publishing bị chặn, child edit không sửa master, evidence/history ban đầu giữ nguyên, và sửa trái phép trạng thái child bị phát hiện. S2 hiện dùng storyboard image/audio; source upload/video/transcript/audio graph S3, HTTP/Studio và render sáu target còn mở. Copier hữu hạn 64 MiB/file, 256 MiB/tổng, 120 giây; S3 và contention PostgreSQL thật chưa kiểm chứng.

Đã tích hợp helper lấy metadata/namespace/provider/custody đã đóng băng rồi truyền size/SHA/prefix/byte limit vào storage. Các consumer source video custody, uploaded audio, production asset và SQL TTS reuse hiện dùng giới hạn này, kiểm tra trạng thái hiện hành sau các thao tác chờ cuối. Raw audio 20 MB và prepared PCM 600 giây giữ nguyên. Không retry bằng download không giới hạn khi adapter không hỗ trợ.

Batch ghép ban đầu có 243 PASS/3 FAIL. Một lỗi hủy ở adapter generic dùng thread và hai lỗi public audio source-change được sửa riêng. Adapter chưa chứng minh drain được shield/chờ hoàn tất I/O; chỉ class có khai báo riêng đã kiểm chứng mới nhận cancellation. Hai lớp local/S3 native có khai báo; subclass override không tự kế thừa chứng nhận. Size/hash/path đổi giữ AUDIO_SOURCE_CHANGED. 21 ca kiểm tra hẹp đều PASS, gồm ba ca từng fail và một ca claim mới; 17 ca chồng với batch cũ. Có 247 ca khác nhau đạt qua các batch, không có một lần chạy toàn bộ 247 PASS. Log lỗi gốc giữ nguyên; assertions hồi quy không bị làm yếu.

WAVE: 3/7/8D — component continuation

STATUS: implemented and qualified components; full waves PARTIAL

HEAD SHA: source af38819e6ec89b56f95fa1a3307fed1dbd5d7566; documentation seal/recovery recorded separately.

CAPABILITIES COMPLETED: SQL S2 storyboard child derivation; selected bounded media/TTS consumers; generic cancellation and audio error compatibility repairs.

CAPABILITIES PARTIAL: seven remaining download callers (four services, three artifact routes), uploaded/mixed variant graph S3, variant API/Studio/review/render, real S3/PostgreSQL/Redis/Docker and full Mode A/B/A-B-C. Three scoped teams continue safe implementation concurrently.

TESTS: S2 primary 73 PASS/1 Windows privilege SKIP; author affected 88 PASS/1 SKIP and independent trust checks preserved. Bounded initial 243 PASS/3 FAIL, narrow repair21 PASS, component affected32 PASS. Batches overlap; do not sum. Studio922 PASS and backend406 PASS/1 SKIP belong to the prior checkpoint, not a newly repeated all-current run. No tests added to reproduce the implementation only; fixes retain existing cancellation/custody requirements.

REAL PROVIDER TESTS: no new inference/provider/render in this checkpoint. Prior one real offline small/vi video ASR at source1b61af is preserved as historical evidence, not a genuine inference on this later source. No external/paid/production/provider acceptance.

MOCK TESTS: mock SDK/provider/render transport and synthetic asset metadata; actual SQLite/local I/O and thread cancellation. Human approvals/rights remain fixtures in testing and confer no publishing authority.

EVIDENCE: [portable index](north-star/sql-storyboard-bounded-consumers-evidence.json), exact reviewed source archives/commits, independent before/after reports, original fail logs and narrow repair logs, cleanup custody/result.

REGRESSIONS: no accepted artifact replaced; no history rewritten; no main merge, production migration/deployment or real publication. Source pushed on the completion branch and locally bundled per component; full source/evidence seal follows this review.

EXTERNAL BLOCKERS: deferred Owner UAT/listening, genuine provider credentials/rights/quality and isolated production qualification. They do not block continued safe implementation.

OWNER ACTION REQUIRED: none for this work. Owner UAT remains deferred.

NEXT WAVE: integrate the four bounded services, three artifact routes and source-bound uploaded variant graph; finish original UI/media/platform/E2E requirements.

Cleanup removed only five reproducible synthetic WAV fixtures inside three verified owned subtrees:460,865,762 logical bytes (about440 MiB). Whole test root, junctions, hardlinks, evidence/source/runtime/model/accepted media and protected old roots remain. Disk-space delta is recorded but not exclusively attributed; no RAM or precise physical-byte gain claimed.

Matrix remains5 IMPLEMENTED_REAL/58 PARTIAL/1 NOT_VERIFIED;59 groups unclosed. SOURCE_PRESERVED=YES; PHASE10_TECHNICALLY_READY=YES; OWNER_UAT_REQUIRED=YES; PHASE10_READY=NO. IMPLEMENTATION_COMPLETE=NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO; VIDEO_FACTORY_NORTH_STAR_READY=NO.
