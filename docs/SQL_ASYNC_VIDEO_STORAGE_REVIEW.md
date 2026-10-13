# Phân tích video nền, giới hạn tải dữ liệu và họ phiên bản SQL

Luồng SQL đã có tác vụ phân tích video bền vững: gửi trả 202, lưu yêu cầu/provider/nguồn đã đóng băng, claim/lease/heartbeat, hủy, lịch sử và xử lý kết quả không rõ. Kết quả transcript/cảnh và trạng thái cuối lưu cùng transaction. Hết lease sau thao tác SQL chờ vẫn rollback kết quả; không tự gọi lại provider hoặc sửa timeline. Metadata phân tích biến động không được công bố checksum giả; giá chưa biết vẫn null và ledger dùng provider đã đóng băng.

Studio có chọn nguồn đã tải lên, gửi, theo dõi, đọc tác vụ đã lưu, hủy và mở kết quả để kiểm tra. Khóa chống lặp được giữ khi mất phản hồi; đổi nguồn/quyền/phiên không nhận kết quả cũ. Khi Studio hết bận, tiếp tục GET thay vì gửi thêm phân tích. Kết quả B được chọn để review độc lập; canonical timeline A giữ nguyên cho tới thao tác sửa tường minh có kiểm tra phiên bản/nguồn. Bản nháp không bị tải lại. Shot view và timeline hiện có được giữ.

Storage có nền tảng tải hữu hạn cho local và S3 opt-in: kiểm đếm bytes thực, exact size/SHA/prefix, temporary file độc quyền, kiểm tra custody/rehash và atomic replace. Hủy hai lần vẫn chờ luồng sở hữu đóng trước khi trả. SDK opt-in dùng connect 5s/read 30s/total attempts 1. Giữ tương thích nguồn thiếu trả 404. Đây là nền tảng: consumer rollout đang triển khai riêng; đường S3 cũ không truyền bounds vẫn chưa giới hạn. Không suy từ MockSDK sang storage/provider production thật.

Họ SQL six-target S1 có contract, metadata đã đóng băng, reservation và receipt/idempotency/history với migration bổ sung. Sáu target trên bốn hình học được kiểm tra. S1 chưa tạo child project, copy asset, chuyển approval/rights, preview hoặc render; S2/S3 đang triển khai và chưa thuộc bản tích hợp này. Migration graph có một head 0032_ns_sql_variants, parent 0031_ns_video_jobs; chỉ đọc graph không chứng nhận upgrade schema hay contention PostgreSQL.

Đã chạy đúng một inference CPU offline mới qua actual upload bảy chunk, scan/SHA/FFprobe, queued job, run_analysis_queue, SQL claim và FFmpeg scene/silence/waveform/visual thật. Kết quả awaiting_review, original v1/23 từ; small/vi/CPU2 chạy 8,7940714 giây. Tổng nhánh kiểm chứng SQL hiện ba inference thật (hai lịch sử, một mới), không retry. Nguồn lời nói là FLEURS public CC-BY-4.0; hình do helper dựng và có ghi nhãn. ALAC integer encoding khác WAV float tối đa 1 LSB, không gọi là byte-identical audio. Không tạo UploadedAudio giả, timeline, approval, render hoặc publication. Kết quả model/raw/clock giữ nguyên; chưa nghiệm thu phát âm, độ chính xác, alignment hay footage/người dùng thật. FakeQueue chỉ mô phỏng handoff; SQL claim và worker entry thực. Runtime/model đã có trên máy; không tải model, gọi API hoặc phát sinh chi phí trả phí.

WAVE: 2/3B/7/8D — component continuation

STATUS: implemented and qualified components; full waves PARTIAL

HEAD SHA: source 1b61af14997f8c178598c760cbf2f0a55acd3e88; final documentation/source seal in recovery/20261007/sql-async-video-storage-program-state.json.

CAPABILITIES COMPLETED: durable SQL video analysis component; scoped queue/review UI; counted local/S3 opt-in download foundation; SQL six-target reservation; one genuine local CPU video ASR run.

CAPABILITIES PARTIAL: full original Mode A/B; broad VI/EN/auto quality and timing; full non-developer Studio; six-target child/analysis/transcript/audio/render/review/publication links; bounded download consumer rollout; real S3/PostgreSQL/Redis/Docker and external providers; full A/B/C bundles.

TESTS: current-source integrated backend 406 PASS / 1 SKIP in 926,58s across 20 modules; full Studio 922 PASS / 0 SKIP. Windows skip lacks file-symlink privilege; directory reparse tests run separately in the same batch. PostgreSQL contention is not qualified. Independent storage 4 PASS and UI fixes 2 PASS overlap the component graph; do not sum test batches. The original inventory command named a nonexistent test module and ran no tests; raw exit-4 log retained. Collect-only proof reuses exact node IDs after correcting a helper prefix; no repeat test run. Browser helper n3 had a newline syntax error before any create; preserved separately, fresh n4 fixed helper only.

REAL PROVIDER TESTS: one actual local offline small/vi CPU ASR call; actual local FFmpeg/FFprobe/SQLite. No paid/external provider calls, model downloads, genuine S3/PG/Redis production or Owner acceptance. Details: recovery/20261007/sql-video-real-asr-final-n1.json.

MOCK TESTS: explicit MockCPU/provider responses, MockSDK, owned MP4/PCM/metadata, queue transport, review identities and approvals in automated batches. Browser replays captured actual ASGI DTOs whose ASR/media semantics are fixtures; canonical A is a separate fixture, not a genuine project.

EVIDENCE: [portable index](north-star/sql-async-video-storage-evidence.json); exact source snapshots/archives, raw successful and failed logs, independent before/after reports, migration graph, browser requests/screenshots/layouts and separate genuine ASR custody report. Current browser n4 observes one create POST, two job GETs, busy/resume, selected B/canonical A, draft guards and logical 1366/1920/2560 fit. Owned loopback listener stopped with exit 0, tabs closed, viewport reset. It is a dedicated component rehearsal, not full Studio/Owner UAT.

REGRESSIONS: source/hash/clock, approval and prepared-audio 600-second contract retained; accepted historical artifacts and protected live source are checked again at final seal. Previous evidence/logs remain immutable. No main merge, production migration/deployment or real publication.

EXTERNAL BLOCKERS: deferred Owner UAT/listening; actual provider credentials/rights/quality and isolated production qualification. Continue safe work without waiting for these.

OWNER ACTION REQUIRED: none for continued safe implementation. Owner UAT stays deferred.

NEXT WAVE: complete SQL variant children and source-bound analysis/transcript/audio; bounded-download consumers; remaining original media/provider/platform and full acceptance gaps.

Matrix stays 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED: 59 broad groups unclosed, not percent completion. SOURCE_PRESERVED=YES only with fresh recovery seal; PHASE10_TECHNICALLY_READY=YES; OWNER_UAT_REQUIRED=YES; PHASE10_READY=NO. IMPLEMENTATION_COMPLETE=NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO; VIDEO_FACTORY_NORTH_STAR_READY=NO.

Cleanup: nine older policy-blocked roots, four older OS/browser roots and three retained newer locked roots remain untouched. No cleanup retry/bypass or freed-PC-byte claim. Evidence/runtime/model/accepted media still required are preserved.
