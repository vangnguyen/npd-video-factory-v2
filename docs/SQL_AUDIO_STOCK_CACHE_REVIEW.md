# Audio lời nói, lịch tìm stock và cache có giới hạn

Ba component tiếp theo đã được triển khai trên engine hiện có. Phạm vi North Star vẫn là toàn bộ Master Spec. Matrix giữ 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED, tức 59 nhóm chưa đủ điều kiện đóng; số này không phải phần trăm khối lượng còn lại.

SQL Studio có panel audio lời nói riêng, tải/chia phần/hash, yêu cầu nhận dạng tường minh, trạng thái/hủy, nghe file gốc, sửa đoạn/từ, lịch sử và khôi phục. Audio mặc định chưa cấu hình ASR. Tệp nghe tối đa 32 MiB, đọc có giới hạn và xác minh toàn bộ size/SHA/MIME trước Blob URL; abort/revoke khi đổi ngữ cảnh. Upload panel tối đa 64 MiB. Khóa tạo ASR được giữ trong sessionStorage qua tải lại; mất kho lưu khóa thì chặn trước dispatch. Yêu cầu sửa chưa rõ kết quả không được coi là thành công chỉ vì người khác đã lưu phiên bản cao hơn: giữ draft và đối chiếu actor, lineage và nội dung. Fixture nghe là WAV do test tạo, có silence và MockASR được ghi rõ; không phải bằng chứng chất lượng nhận dạng lời nói.

Audio được gắn bằng thao tác xác nhận riêng vào timeline canonical đã tồn tại. Khoảng nguồn/tốc độ quyết định thời lượng; không dùng audio làm video-analysis FK giả. Không thay phụ đề đang bật hoặc giọng cũ một cách ngầm định; mute original audio là lựa chọn riêng, track khóa được giữ. Sửa/khôi phục transcript và caption được ghi cùng giao dịch với phiên bản timeline, làm hết hiệu lực preview/approval/render cũ qua repository chung. Bản ASR gốc và file nguồn bất biến. Timing từ provider hoặc người sửa giữ đúng provenance; text mới bỏ word alignment. Voice trim/split/move/speed/disable reflow theo đồng hồ nguồn, từ cắt xuyên lời bị chặn. Caption manual/khác nguồn/khóa gây conflict và rollback; thao tác chỉ khóa voice giữ nguyên caption IDs/bytes. Sau undo chọn transcript cũ, phải khôi phục transcript tường minh để tiếp tục, không tự thay lựa chọn. Đây là mapping đã kiểm với SQL/fixture, chưa nghiệm thu non-developer/Owner hoặc audio thực trong trình duyệt.

Media Planner stock có snapshot binding nguồn/cấu hình/Vision/transcript/budget, checkpoint từng cảnh, lịch chờ, lease/claim và lịch sử append-only. Trạng thái/retry/cancel có API; API và worker dùng storage thực, worker chỉ tiếp tục stock read-only đến hạn. Mỗi lần tìm cảnh mới kiểm lại bytes/metadata và claim sau thao tác await. Nguồn đổi trong lần gọi đang chạy không thể gửi thêm cảnh hoặc commit kết quả sai nguồn. Chờ chưa gọi không tiêu hao chu kỳ wire; tối đa ba chu kỳ thất bại thực mỗi search. Cost chưa biết giữ null; usage failed chỉ dành cho thao tác external không trả phí được ghi rõ, không đổi reservation/paid flow. Migration 0029 chỉ bổ sung bảng. Chưa có panel lịch stock chuyên biệt hoặc nghiệm thu PostgreSQL/Redis/provider thật.

Cache JSON phản hồi stock giới hạn theo namespace workspace/config/mode/provider: mặc định 256 entries (gồm control files), 64 MiB, 24 giờ, tối đa khoảng 2 MiB mỗi entry; scan/lock cũng hữu hạn. Chỉ evict JSON v2 hợp lệ cùng binding; file lỗi, legacy, khác binding và media/evidence được giữ. Tổng tính cả file được bảo vệ; nếu không thể giữ giới hạn thì không lưu thêm. Lock không giữ qua wire/quota; Windows junction/hardlink/ancestor swap, long-path và nhiều process có kiểm tra thực. Phản hồi provider 200 hợp lệ vẫn được dùng khi ghi cache gặp scan/busy/I/O; không vượt giới hạn để lưu. Read corruption/path/config/control vẫn fail closed. Diagnostic chỉ code/count hữu hạn. Đây chưa phải giới hạn toàn bộ cache, global quota hoặc retention đầy đủ.

Studio Dockerfile đã bổ sung các module ES trực tiếp; nginx cho phép playback Blob đã được xác minh. Test đóng gói/static đạt, Docker E2E chưa chạy. WAV fixture ban đầu bị quy tắc ignore media loại ra khỏi commit; đã thêm ngoại lệ đúng một tệp và commit fixture riêng trước seal, để checkout/bundle không mất dữ liệu kiểm tra.

WAVE: 3B/3I/5A/8D/15 components

STATUS: IMPLEMENTED_AND_MOCK_TESTED; real SQLite/files/process/HTTP custody; full waves PARTIAL

HEAD SHA: cache 6db04bce59f4b0763262550c462362ea47cb986a; planner b744c6b4cc1d2ec3541030b8d95e0f77037faecd; audio ed1949fb7bc9cd8fbef708e567d1ea5b34cffcb2; fixture 564138cb13f19d5d4e371ed524b57809ffd95598; final HEAD/recovery recorded in recovery/20261007/sql-audio-stock-cache-program-state.json

CAPABILITIES COMPLETED: scoped audio review panel; explicit canonical voice/caption binding and atomic revisions; exact retry/reconciliation guards; bounded source playback; scheduled read-only planner checkpoints/lease/history; truthful failed usage; scoped bounded stock response cache; Studio module packaging

CAPABILITIES PARTIAL: local CPU ASR runtime selection in SQL; full stock scheduler UI/global quota/cache/retention; perceptual/semantic/media/provider quality; genuine browser speech/non-developer/Owner; original Mode A/B and A/B/C; production hardening

TESTS: 85 SQL/worker PASS with 2 FFmpeg media skips in WSL; 11 final canonical/scheduler PASS after lock-only fix; 90 stock SQL PASS; 52 Native stock/cache PASS; 43 Native Phase10/voice/timeline PASS; 873 full Studio PASS. Batches overlap and must not be added.

REAL PROVIDER TESTS: none. No new ASR inference, external provider request, credentialed wire or paid operation. SQLite/file hashes, local ASGI and Windows process/path checks are real.

MOCK TESTS: ASR, stock HTTP, credentials, provider timing/quota, actor/review and long retry clocks are explicit fixtures. CI approvals are not Owner UAT. Two skipped WSL media cases are not passes.

EVIDENCE: [indexed evidence](north-star/sql-audio-stock-cache-evidence.json), raw Windows logs and portable archive. New captured UI read/history/source fixture is included in Git; no accepted video replaced. No new preview/final video, browser speech or Owner listening acceptance is claimed.

REGRESSIONS: source-race/unknown-write draft/lock-only defects found independently and corrected with regression evidence. Intermediate errors remain in logs: fixture source field, naive-vs-aware timestamp assertion, canonical test lacking storyboard source identity, mistyped test/module file names, cache long-path teardown, and ignored WAV fixture. Final successful runs are explicit.

EXTERNAL BLOCKERS: real provider/rights/quality acceptance, Docker/production isolation and separately approved deployment, deferred Owner UAT. These do not stop remaining safe work.

OWNER ACTION REQUIRED: none for continued safe implementation. Listening/UAT remains deferred. Publishing/deployment/new paid operations remain disabled.

NEXT WAVE: explicit local CPU ASR for SQL using approved runtime; actual audio UI rehearsal; planner scheduling UI; remaining original media/platform/acceptance gaps.

Cleanup: scoped rebuildable cache lifecycle is tested; no amount of freed PC disk space is claimed. A new long-path test root C:/vfct/sc-md_kygk6 remains after OS teardown failure, without retry. Automatic approval review blocked one cleanup of C:/vfct/audio-review-check-01 before execution with only “blocked by policy”; no retry/bypass. Nine policy-blocked roots total and the older OS/browser retained roots remain untouched. Ordinary fresh fixture teardown completed.

SOURCE_PRESERVED=YES is established by final Git/source seal. PHASE10_TECHNICALLY_READY=YES; OWNER_UAT_REQUIRED=YES; PHASE10_READY=NO. IMPLEMENTATION_COMPLETE=NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO; VIDEO_FACTORY_NORTH_STAR_READY=NO.
