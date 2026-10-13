# Nhận diện video CPU và giữ âm thanh đã duyệt

Đã nối provider CPU offline vào luồng phân tích video SQL với cấu hình tường minh, runtime/model/decoder/code được đóng dấu SHA và nguồn video tải lên đã kiểm tra. Audio và video dùng đúng adapter riêng; không tạo audio job hoặc FK giả cho video. Mặc định vẫn NOT_CONFIGURED, cấu hình hợp lệ vẫn cần kiểm tra chất lượng và không đủ điều kiện production. API khởi động chọn một instance cho mỗi scope rồi dùng cùng instance để seed registry và chạy; đọc registry không tạo provider hoặc hash model.

Cache nhận diện bind model, ngôn ngữ, runtime, source và profile. Kiểm tra đủ bytes/SHA trước cache hit, trước/sau inference và trước persistence; raw model/PCM clock/result bị từ chối được lưu riêng theo invocation khi đủ custody. Word intervals không được cắt, bù epsilon, sửa tốc độ hoặc bịa alignment. Kết quả không rõ hoặc đã thất bại không tự chạy lại. Hủy và lỗi sibling drain các tác vụ do luồng sở hữu trước khi kết thúc staging. Luồng video này còn synchronous; durable async queue, lease, cancel/recovery UI là hạng mục tiếp theo.

Video vật lý do kiểm thử tạo đã đi qua FFprobe/FFmpeg, upload trust và SQL với CPU provider giả lập tường minh. Đây là kiểm tra giải mã, source clock và persistence thật, không phải nhận dạng giọng nói/model thật. Tổng ASR thật lịch sử vẫn là hai lần đã chứng nhận ở mốc trước, không chạy thêm model hoặc tải weights trong mốc này.

SQL TTS có cache raw PCM opt-in cho VieNeu, cùng workspace/project/content và fingerprint công khai. Entry pending/unknown/corrupt không trở thành cache miss hoặc tự gọi lại provider. Raw PCM và bằng chứng gốc được giữ nguyên; hit có receipt mới gắn đúng timeline, subtitle, audio và render đích. Canvas khác vẫn cần review riêng. Bốn canvas được kiểm thử; full SQL six-target variant family chưa được triển khai.

Bản sửa riêng giữ hợp đồng render cũ đến 600 giây: PCM stereo 480/600 giây được kiểm tra vật lý theo stream, copy SQL source/hash đúng, chặn 601 giây và header/truncation/clock không hợp lệ. Không dùng giới hạn 90 MB để thu hẹp video YouTube dài. Download admission dựa trên frozen size; giới hạn bytes thực trong SDK stream còn là gap platform riêng, không suy từ metadata admission.

Bản xuất cuối dùng narration/audio-mix/raw-unit/caption schedule chính xác từ review đã duyệt, không đọc profile, secret, health, preflight hoặc gọi provider. Frozen asset proof bao gồm workspace/project/version/class/storage/object/SHA/provenance; thay bytes, checksum hoặc lineage đều bị chặn. Thay nội dung qua cả ContentService và public version API cũng phải bị chặn. Kiểm tra completion thực hiện cùng transaction thay vì chỉ kiểm lúc tải âm thanh. Các lỗi ban đầu và ca tái hiện trước/sau được giữ trong archive; không suy từ SQLite sang PostgreSQL production.

Cost ledger gốc giữ nguyên, cả giá trị chưa biết. Hit và final ghi chi phí provider phát sinh thêm bằng 0 và không có inference mới; điện/hardware vẫn null. TTS reuse/final được kiểm tra bằng SQLite, PCM do test tạo và MockTransport, không nghiệm thu DSP, pixels/renderer thật, model, phát âm, pháp lý hoặc Owner.

Đã mở bản cold SQL của transcript thật trong viewer chỉ đọc: original v1, 23 từ và source 11,34 giây phát được; toàn bộ source bytes/SHA và các bảng SQL giữ nguyên. Panel được quan sát ở logical viewport 1366/1920/2560. Đây là dedicated fixture viewer, không phải nghiệm thu toàn bộ Studio hoặc người dùng không kỹ thuật. Giữ nguyên lỗi model “mộ lạc”; không tự sửa transcript hoặc chấp nhận độ chính xác/alignment. Listener riêng đã dừng, tab riêng đã đóng. Lỗi allowlist capabilities của helper đầu tiên đã giữ riêng trước khi sửa helper.

WAVE: 2/3B/6B/7/8D component continuation

STATUS: IMPLEMENTED_AND_QUALIFIED_COMPONENTS; full waves remain PARTIAL

HEAD SHA: source parent 05f2a68bb17f44cd38e422e0c114ee8687ae6f4f; final source/recovery SHA in sql-video-tts-reuse-program-state.json after seal

CAPABILITIES COMPLETED: explicit CPU video adapter/custody/SQL evidence; qualified raw-TTS cache; provider-neutral approved-audio final; VieNeu bootstrap row; audio time display; readonly browser playback of historical genuine SQL speech

CAPABILITIES PARTIAL: async video jobs; English/auto/base genuine ASR; calibrated timing/quality; SQL six-target family; real TTS/DSP/provider/Owner; full original Mode A/B and bundles A/B/C

TESTS (batches overlap, không cộng):

* current_integration_repaired_cases: 8 PASS, 0 SKIP.
* full_Studio_unchanged_UI_source: 898 PASS, 0 SKIP.
* audio_display_scoped: 51 PASS, 0 SKIP.
* VieNeu_registry_prior_component: 40 PASS, 0 SKIP.
* video_current_affected: 50 PASS, 0 SKIP.
* video_double_cancel: 5 PASS, 0 SKIP.
* prepared_PCM_contract_480_600: 7 PASS, 0 SKIP.
* TTS_completion_current_control: 4 PASS, 0 SKIP.

Root integration: 206 cases collected, 203 distinct cases qualified and 3 PostgreSQL skips. Initial run had 198 PASS, 2 FAIL and 6 setup/teardown errors affecting three additional cases; these were Windows test-path/test-ID failures. Eight targeted cases passed after shorter fresh staging and bounded parameter labels, including three overlaps with the initial pass set. Entire test AST is identical after removing the new IDs, and production source did not change during resolution. No single all-PASS batch is claimed. Exact graph/counts, initial raw log and rerun are in integration-resolution-n1.json; other batches overlap this graph.

REAL PROVIDER TESTS: zero new model/external/paid calls. Historical two CPU audio inferences remain preserved. No real video ASR or TTS inference in this increment.

MOCK TESTS: explicit MockCPU video text/timing, owned PCM, MockTransport, synthetic render/QC and reviewer identities. PostgreSQL contention/barrier skips remain unverified; no production migration or stack action.

EVIDENCE: [portable index](north-star/sql-video-tts-reuse-evidence.json), 105 exact byte/SHA entries; earlier audio/stock archive remains unchanged and referenced separately. ASGI and renderer-pause repros preserve intermediate failures and fixed checks.

REGRESSIONS: accepted historical media retained; final current-source checks are in the index. No silent replacement, main merge or production deployment.

EXTERNAL BLOCKERS: deferred Owner listening/UAT, genuine provider/rights/quality acceptance and isolated PostgreSQL/Redis/Docker production qualification.

OWNER ACTION REQUIRED: none for remaining safe implementation; listening/UAT remains deferred.

NEXT WAVE: durable async video analysis and original SQL variant family/production/media/platform gaps; full North Star scope retained.

Matrix remains 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED: 59 groups unclosed. SOURCE_PRESERVED=YES at the fresh seal; PHASE10_TECHNICALLY_READY=YES; OWNER_UAT_REQUIRED=YES; PHASE10_READY=NO. IMPLEMENTATION_COMPLETE=NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO; VIDEO_FACTORY_NORTH_STAR_READY=NO.

Cleanup: nine older policy-blocked roots and four older OS/browser roots remain untouched. New independent-review root C:/vfct/tg-5zzqe5i2 and two owned double-cancel repro roots trusted-video-99zp9gab/bcr59vnr are retained after Windows file-lock failure, with no cleanup retry or bypass. Their exact paths are in the evidence index. No freed PC bytes are claimed; runtime/model/evidence are still required.
