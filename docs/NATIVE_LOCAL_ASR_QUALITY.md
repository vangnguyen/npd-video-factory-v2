# Mô hình ASR local và kiểm tra với transcript tham chiếu

Đây là phần Wave 3B/8/16, tiếp tục yêu cầu ASR Việt/Anh/auto và transcript có phiên bản của Master Spec 22. Runtime v2 chọn rõ model_key đã được duyệt qua manifest, giữ runtime v1 và profile base cũ đúng hash. Mô hình chưa cấu hình không chuyển sang model khác/API. Studio chỉ hiện lựa chọn theo capability riêng; model lớn hơn có hướng dẫn về thời gian/bộ nhớ và timestamp ước lượng. Core, NPD live source và AssemblyAI mặc định không được thay môi trường hoặc config đang chạy.

Lựa chọn vận hành bổ sung là [SYSTRAN faster-whisper-small](https://huggingface.co/Systran/faster-whisper-small/tree/536b0662742c02347bc0e980a01041f333bce120): 486214370 byte, revision/blob/hash cố định, MIT metadata. Client chỉ chọn tên model trong allowlist, không gửi executable/path/graph hay prompt. Profile/model khác có snapshot/idempotency riêng; base v1 giữ đúng hash8f69904db4efb6b96b1bd355f7ac1de1c19cde746091bb6ed0421b9a4a773e64 của bằng chứng trước.

Benchmark dùng ba tệp WAV đầu tiên theo thứ tự archive test vi_vn của [Google FLEURS](https://huggingface.co/datasets/google/fleurs), revision70bb2e84b976b7e960aa89f1c648e09c59f894dd và CC BY4.0. Giữ attribution Conneau et al./Google/2022, audio gốc, reference gốc và hash. TSV được kiểm tra Git blob; đọc stream đúng1413120 byte đầu archive và chỉ giữ1831854 byte WAV. Không tải/lưu archive544139865 byte. Hash archive đầy đủ không được tuyên bố đã kiểm chứng; nguồn HTTPS/revision/LFS reference và prefix/file hashes được ghi riêng. Parser dùng quote-none vì TSV chứa dấu nháy nguyên văn; mẫu không chọn theo kết quả.

Model chỉ nhận PCM của cùng audio, không được cung cấp reference hay hotword/prompt. Normalizer đánh giá NFC/casefold/letters/numbers/whitespace, giữ dấu tiếng Việt, bỏ punctuation và so Levenshtein. Tỷ lệ token dùng token tách khoảng trắng, không tuyên bố là phân tách từ ngôn ngữ học tiếng Việt. Aggregate dùng tổng lỗi/tổng64 reference tokens; đánh giá ký tự bỏ khoảng trắng riêng. Không đổi transcript, không đánh giá timing/proper names và không cấp approval.

| Profile thử | Lỗi token /64 | Tỷ lệ token | Lỗi ký tự /209 | Tỷ lệ ký tự | Phạm vi |
| --- | ---: | ---: | ---: | ---: | --- |
| base hiện có |21|32.8125%|40|19.1388%|3 mẫu cố định |
| small bổ sung |13|20.3125%|20|9.5694%|Cùng3 mẫu |
| PhoWhisper experimental |44|68.75%|164|78.4689%|Không đạt, hallucinated tails |
| PhoWhisper no-timestamp/VAD thử lại |196|306.25%|726|347.3684%|Không đạt, không đưa vào vận hành |

Tỷ lệ có thể trên100% do sinh thêm nhiều token/ký tự. Small tốt hơn trên đúng ba mẫu này; chưa đạt kiểm chứng chất lượng toàn bộ tiếng Việt, tên riêng, các giọng/độ dài/nhiễu hoặc audio do người dùng tự upload. Không dùng sample score để tự nghiệm thu Phase10, ModeB hoặc thay nhà cung cấp mặc định.

Thử [VinAI PhoWhisper-small](https://huggingface.co/vinai/PhoWhisper-small/tree/a86b604c346caf7148c37512eafe783a16420adb) có BSD3 metadata, source weights967102729 byte được xác thực. Môi trường chuyển đổi CPU tạm dùng Torch2.8.0+cpu/Transformers4.55.4; CTranslate2_4.8.2 đầu tiên lỗi API dtype, được ghi log và dọn. Chuyển đổi lại bằng4.6.0 tạo int8 model251531738 byte nhưng kết quả reference quality không đạt. Cả hai môi trường chuyển đổi/trọng số nguồn đã dọn theo lifecycle. Runtime chặn model này trước đọc custody/dispatch; cấu hình cố bật vẫn không được dùng và không làm hỏng base/small. Manifest và dữ liệu thử vẫn được giữ để không xóa dấu vết thất bại.

Thử policy VAD/no timestamp chỉ là thử nghiệm bị cách ly. Raw kết quả và ước lượng word timing giữ nguyên; không thêm epsilon/khớp từ vào reference. Validation yêu cầu VAD dùng tọa độ input PCM gốc, duration sau VAD hợp lệ. Không sử dụng output không đạt để tạo approval hoặc source edit. PhoWhisper UI option luôn không cấu hình vì quarantine; base/small hoạt động độc lập.

Small Native actual flow dùng một mẫu lời nói người thật FLEURS với hình màu sinh, cùng hai luồng tiếng Anh/auto JFK benchmark. Ba ASR job → actual Auto Edit analysis → versioned CI transcript edit → backup/fresh-process exact restore pass;23/22/22 từ. Original transcripts/source giữ nguyên; quyền publishing của video dẫn xuất vẫn unknown, approval không được cấp. Có lời nói người thật trong mẫu nhưng không phải full video footage của người dùng, không browser/Owner acceptance.

51 Native PASS (11 ca mới: metric/model binding/runtime/coordinate/quarantine),789 Studio PASS (2 mới). Native ASR/CSRF/old identities/hardening/cached replay và UI được giữ. Những batch cũ chồng lặp không cộng thành unique total. Benchmark9 inference chính và3 thử VAD lỗi là evidence riêng; small Native3 inference/restore là integration evidence, không phải remote provider acceptance.

Thử dọn251531738 byte trọng số experimental không đạt tại C:/vfns-local-asr-c1/models/phowhisper-small-int8 bị automatic execution review từ chối: blocked by policy. Command không chạy; root vẫn tồn tại. Không retry hoặc bypass bằng cách khác; không xóa source/evidence hoặc15 accepted artifacts. Bảy mục cleanup bị policy chặn của chương trình tiếp tục được giữ; các temp lifecycle mới đã dọn.

WAVE:3B/8/16 component
STATUS:implemented/mock-tested/local-real reference comparison and Native integration; full waves PARTIAL
HEAD SHA:parentacfcb42a29d8d6a0ae09eadf03f28f9909f02d56; final in recovery/20261007/local-asr-quality-program-state.json
CAPABILITIES COMPLETED:approved explicit base/small selector, v1 preservation/v2 custody, frozen model identities, reference metrics, bounded licensed sampling, optional bad-model quarantine
CAPABILITIES PARTIAL:quality/calibrated timing/proper names/noise/other accents, actual new browser/non-developer/Owner/full ModeA/B/provider/production
TESTS:Native51/Studio789 PASS;11 new Native/2 new Studio
REAL PROVIDER TESTS:actual local CPU reference and small Native operations; no external ASR/API/budget/publishing
MOCK TESTS:role/auth guards, model corruption/scalar/runtime cases, fixture DOM and CI transcript review; generated visual only
EVIDENCE:north-star/local-asr-quality-evidence.json; local-asr-quality-evidence-n1.zip; original failures retained
REGRESSIONS:old base profile exact hash, missing/quarantined model cannot fallback or disable others, role/CSRF/transcript/history; seal verifies15 accepted artifacts/live source
EXTERNAL BLOCKERS:quality/genuine operator/Owner/real provider/Docker/production acceptance remain separate; rejected cleanup root retained
OWNER ACTION REQUIRED:none for continued safe implementation; UAT/listening deferred
NEXT WAVE:genuine-source/operator/transcript-word review and full original ModeA/B/media/Trend/Bridge/production scope

5 IMPLEMENTED_REAL/58 PARTIAL/1 NOT_VERIFIED;59 unclosed. IMPLEMENTATION_COMPLETE=NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO; VIDEO_FACTORY_NORTH_STAR_READY=NO.
