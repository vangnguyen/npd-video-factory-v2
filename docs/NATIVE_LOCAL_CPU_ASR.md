# Nhận diện lời nói bằng CPU local

Master Spec 22 / Wave 3B yêu cầu TranscriptionProvider độc lập nhà cung cấp, Việt/Anh/tự phát hiện, dấu câu, timestamp và transcript có phiên bản. Lựa chọn mới dùng cùng job ASR, ingest, media_analysis và Auto Edit hiện có. Không tạo database/timeline riêng hay thay AssemblyAI mặc định.

LocalCpuTranscriptionProvider trả các ProviderTranscript/Segment/Word có sẵn. Mô hình [SYSTRAN faster-whisper-base](https://huggingface.co/Systran/faster-whisper-base/tree/a80717a3a48b1b28aa687bca146cb7301feae1b1) cố định revision và hash năm tệp, 147884936 byte, metadata license MIT. [Runtime chính thức](https://github.com/SYSTRAN/faster-whisper) dùng phiên bản 1.2.1 trong virtualenv riêng C:/vfns-local-asr-c1. Không cài thêm vào runtime NPD đang chạy. Các phiên bản dependency thực tế được ghi riêng; trọng số không đưa vào Git hoặc backup dự án.

Mặc định local runtime chưa cấu hình. Config.local_asr_manifest chỉ tham chiếu manifest ngoài state/UI; manifest được kiểm tra schema, enabled, interpreter SHA, path không symlink/reparse, model revision/hash, CPU threads 1–4 và timeout 30–600 giây. Client không được gửi model path, executable hoặc graph. Toàn bộ model được kiểm tra hash trước/sau inference. subprocess dùng stdin JSON, Python -I, môi trường không mang credentials, CPU int8/local_files_only và chặn socket; không tự tải mô hình hoặc gửi âm thanh đến API. Tải model/package công khai là bước chuẩn bị riêng, có bằng chứng hash, không phải zero-network setup.

Native bind lựa chọn provider=local-whisper và vi/en/auto vào snapshot/idempotency. Các yêu cầu AssemblyAI cũ giữ chính xác binding cũ. HTTP tiếp tục kiểm tra vai trò, cookie/CSRF trước mutation; thiếu runtime local không chuyển qua provider từ xa. Worker đọc PCM mono16k đã trích xuất, lưu raw kết quả và checkpoint, nối mapping đồng hồ nguồn có sẵn, rồi lưu normalized transcript và phân tích scene/silence/highlight. Checkpoint hợp lệ được đọc lại không inference. Lịch sử gốc không bị thay bằng chỉnh sửa; bản sửa theo phiên bản không tự có lại word alignment.

Timestamp từng từ là ước lượng mô hình, không phải căn chỉnh đã đo hoặc đã được con người kiểm chứng. Không thêm epsilon, không bỏ từ có độ dài zero: boundary được giữ và consumer yêu cầu khoảng dương tiếp tục từ chối. Word probability được giữ, confidence cấp segment/transcript và phí thực tế không có hóa đơn là null. Forced-language không được ghi thành language-detection confidence; auto giữ xác suất mô hình thực sự trả. Mọi kết quả cần review; số từ probability dưới 0.5 được ghi. Không có diarization.

Studio hiện ba lựa chọn CPU local khi capability cấu hình khả dụng; lựa chọn không cấu hình bị từ chối. Hướng dẫn nói rõ xử lý trên máy, không phí API và timing ước lượng. Editor vẫn dùng transcript/shot/timeline cũ. 787 Studio tests pass; đây là controller/contract evidence, chưa phải browser/UAT cho lựa chọn CPU mới.

Bằng chứng actual local ở local-asr-real-native-n2: ba job Việt/Anh/auto đọc mẫu lời nói, lưu 31/22/22 từ và tiếp tục actual Auto Edit analysis. Mẫu Việt tái sử dụng WAV TTS đã có, mẫu Anh là JFK benchmark từ repository chính thức OpenAI Whisper (Git blob kiểm chứng riêng); phần hình là màu sinh bằng FFmpeg. Cả ba bản sửa transcript CI tăng version và giữ nguyên original; ba project khôi phục chính xác ở interpreter mới, không gọi provider. Temp state được dọn theo lifecycle; source và evidence cũ giữ nguyên, quyền publishing vẫn unknown. Không có video uploaded của người dùng hoặc Owner legal/UAT acceptance.

Chất lượng tiếng Việt của base model chưa đạt: thử WAV gốc nhận sai nhiều từ/tên riêng; qua video có 8/31 từ probability thấp. Mẫu Anh có 22 từ, zero low-confidence words và auto trả en, nhưng không suy rộng thành chất lượng mọi nguồn. Không dùng kết quả này tự nghiệm thu proper-name, speech alignment, full Mode B hoặc Phase10. Actual inference là local-real; external provider acceptance vẫn riêng.

40 Native tests (11 mới và ASR/hardening liên quan), 30 consumer/static và 787 Studio pass. Batch có thể chồng lặp; không cộng thành unique total. Lỗi đầu gồm harness prompt không phù hợp media, thuộc tính test/Fake status sai, test directory/node và tên module static; lỗi adapter lưu ngôn ngữ từng chỉ hỗ trợ AssemblyAI đã sửa để kiểm tra local provider/model/profile/dedicated nonpaid provenance. Tất cả log/candidate thất bại được giữ.

Runner: python -X utf8 scripts/north_star_local_asr.py --output <fresh-folder> --runtime-manifest <private-manifest> --vietnamese-wav <existing-speech> --english-audio <benchmark-or-authorized-audio>. Chuẩn bị runtime cần tệp JSON local-asr-runtime.v1 với enabled, python/python_sha256, model_root/model_manifest_sha256, cpu_threads, timeout_seconds. Không nhận cấu hình này từ UI/client. CPU/GPU/core khác tiếp tục hoạt động nếu local ASR không cấu hình. Không sửa config deployment/live NPD.

WAVE: 3B/3C/8/16 component
STATUS: implemented / mock-tested / local-real CPU tested; original full waves PARTIAL
HEAD SHA: parent20f76d6d554689e0df5691dc4eca79e25e121647; final in recovery/20261007/local-cpu-asr-program-state.json
CAPABILITIES COMPLETED: configured local CPU ASR choice, normalized VI/EN/auto/model words, frozen jobs, raw/checkpoint/cost/history, versioned edits, exact process restore
CAPABILITIES PARTIAL: VI quality/proper names, genuine uploaded human sources/alignment, diarization, browser/Owner/full Mode A/B and production
TESTS: Native40 / consumers30 / Studio787 PASS; 11 new cases
REAL PROVIDER TESTS: actual local CPU inference3; external AssemblyAI/OpenAI/provider calls none
MOCK TESTS: signed identities, inference guards, fixture DOM; actual integration uses generated visuals and CI edits
EVIDENCE: north-star/local-cpu-asr-evidence.json; local-cpu-asr-evidence-n1.zip; retained attempts and setup hashes
REGRESSIONS: legacy identities, ASR/Auto Edit/transcript/CSRF/immutability/static/Studio preserved; seal rechecks15 accepted artifacts/live source
EXTERNAL BLOCKERS: genuine source/quality/rights/provider/Owner/Docker/production acceptance remains separate
OWNER ACTION REQUIRED: none for safe implementation; original listening/UAT deferred
NEXT WAVE: genuine source/quality/word review and full original Mode A/B/media/production gaps

5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED;59 groups unclosed. IMPLEMENTATION_COMPLETE=NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO; VIDEO_FACTORY_NORTH_STAR_READY=NO.


Latest approved base/small selection, fixed licensed reference comparison, failed experimental-model quarantine and exact scope: [NATIVE_LOCAL_ASR_QUALITY.md](NATIVE_LOCAL_ASR_QUALITY.md). Original v1/base evidence remains unchanged; no whole-program readiness change.
