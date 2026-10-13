# ASR CPU, lịch tìm tư liệu và diễn tập audio SQL

Tiếp tục toàn bộ Master Spec, không thu hẹp Mode A/B. Provider ASR CPU cục bộ đã có đường cấu hình tường minh cho uploaded audio SQL; mặc định vẫn NOT_CONFIGURED. Studio có panel lịch stock đã lưu để đọc trạng thái/lịch sử, thử lại khi đến hạn, hủy và đối chiếu yêu cầu chưa rõ kết quả. Đây là các component; chưa đóng một nhóm North Star đầy đủ.

ASR dùng runtime/model base hoặc small đã được kiểm tra SHA, chạy CPU/int8 trong subprocess offline. Không tự tải model hoặc chọn PhoWhisper bị cách ly. Binding giữ runtime manifest, executable, decoder, model/revision/license, code, profile, language, giới hạn và chính sách đồng hồ nguồn. Source SHA và binding được kiểm lại trước/sau bước chạy. Decoder tạo PCM mono16 kHz và đo PTS thực; khoảng thiếu/chồng lấn bị từ chối. Mapping về nguồn giữ raw PCM/model result riêng, không cắt bounds, đổi tốc độ, sửa timing hoặc tự bù thời gian từ. Kết quả vẫn cần nghe và sửa; confidence không được coi là đã hiệu chuẩn.

SQLite.backup của SQL job thật được đọc qua ASGI chỉ đọc ở kho riêng: original/current v1, 23 từ, raw digest, 181440 PCM samples, nguồn, 3 events và sổ chi phí giữ nguyên; timeline v1 vẫn nháp. Các bảng trước/sau đọc bằng nhau. Bytes DB của backup khác bản gốc do SQLite.backup; không nhầm sự khác biệt container với thay đổi bản ghi. Khôi phục dùng ContractOnly provider, không tạo model, chạy worker/lifespan, nối Redis hoặc thêm inference/ASR rows. Hồ sơ 39 tệp gốc được kiểm tra lại nguyên vẹn.

Đã có một inference trực tiếp small/vi/CPU2 trên đoạn FLEURS tiếng Việt 11,34 giây, chạy 22,11 giây, trả 1 đoạn/23 từ. Nguồn CC-BY-4.0, hash và manifest được lưu. Model nhận sai “mộ lạc” so với reference “bộ lạc”; giữ nguyên raw, không tự nghiệm thu chất lượng. Hậu kiểm normalization consumer dùng kết quả đã lưu đạt, không chạy model lại. Một lần bổ sung qua UploadedAudioService/SQLite trên Windows chạy 19,68 giây, lưu original/current v1 với 23 từ và trạng thái awaiting_review. Raw canonical digest giống lần trực tiếp. Tổng inference thật là 2; không retry/recovery dispatch. SQL integrity/FK, nguồn đọc đủ bytes/SHA, clock, events và cost được kiểm tra; storyboard timeline vẫn v1/draft, chưa gắn transcript. Antivirus và script review trong helper là fixture CI, không phải production scanner hoặc Owner approval.

Studio stock chỉ thao tác lịch read-only đã có: không tự tạo Media Plan hoặc bắt đầu generative/paid/publishing. Đọc bốn DTO đã xác thực cùng binding/version trước thao tác; lưu pending trong bộ nhớ phiên trước POST; khi mất phản hồi vẫn giữ cùng tuple để đối chiếu. POST được nhận nhưng GET lỗi không làm mất pending. Đối chiếu chứng minh chuyển trạng thái đúng CAS và binding trong ngữ cảnh client, không chứng minh actor của HTTP request: backend stock event hiện chưa có request/actor correlation riêng. Chi phí thiếu giữ null. Quyền, phiên bản, source/config drift và draft chưa lưu được kiểm tra. Shot view và canonical timeline vẫn dùng engine hiện có.

Diễn tập audio trong trình duyệt dùng WAV im lặng do test tạo và MockASR tường minh, không phải nhận dạng lời nói thật. Upload/hash, nghe nguồn, thêm voice/caption, sửa thời gian từng từ và khôi phục lịch sử đã đi qua API/SQLite. Có 3 transcript versions và 5 timeline versions; nguồn giữ nguyên. Fixture viewer đọc được lịch sử và không có quyền mutation. Đã quan sát panel ở logical viewport 1366/1920/2560; chưa nghiệm thu toàn bộ Studio ở các kích thước này hoặc non-developer/Owner. Snapshot SQLite, source và objects được khôi phục trong kho riêng và đọc qua ASGI, không phát sinh inference. Listener diễn tập đã dừng, tab riêng đã đóng; giữ bản gốc và bản sao bằng chứng.

Lỗi helper đầu tiên thiếu provider registry làm cost ledger từ chối job; đã giữ lỗi và sửa seed riêng của fixture. Lỗi này không làm yếu guard sản phẩm. Review chéo phát hiện và sửa retry CAS kiểm ngoài claim transaction: hai database instances nay trả 409/không thêm wire khi worker đã defer hoặc cancel. Raw model/clock evidence bị mất khỏi SQL khi normalizer/projection từ chối trước return cũng đã sửa bằng typed exception gắn riêng từng invocation; service kiểm hash, finite JSON, source/binding và claim/lease/config/request trước ghi failure evidence. Không đọc singleton.raw_result để quyết định persistence; không tạo transcript normalized từ kết quả bị từ chối. Cancel/expired claim không ghi evidence muộn. Intermediate repro FAIL được giữ cạnh bản chạy lại PASS.

Panel stock được diễn tập trên trình duyệt ở ba logical viewport 1366/1920/2560, không tràn ngang, gồm đọc/retry/cancel/viewer. Riêng diễn tập stock chỉ phát lại DTO SQL đã lưu bằng helper localhost, không chạy thêm SQL job hoặc provider. Bằng chứng race/backend thật trong SQLite và bằng chứng hiển thị replay được ghi tách riêng.

Registry ban đầu suy ra configured từ settings mặc dù factory đã fallback vì runtime không hợp lệ; snapshot còn suy ra production_eligible. Đã sửa: lifespan tạo actual provider một lần trước seed và dùng cùng instance để chạy; GET không tạo provider/hash model. Runtime fallback là disabled/NOT_CONFIGURED; cấu hình hợp lệ vẫn degraded/unverified. Metadata yêu cầu production acceptance giữ production_eligible=false khi chưa có acceptance, không thay quyền chạy local an toàn hay các external/budget/Owner gates. Bằng chứng SQL thật tại commit c165320 là trước sửa registry; fingerprint và hồ sơ cũ giữ nguyên, không viết lại để coi là chạy mã mới.

WAVE: 3B/3I/5A/8E/15 component continuation

STATUS: IMPLEMENTED_AND_QUALIFIED_LOCAL_REAL_TESTED components; full waves remain PARTIAL

HEAD SHA: Studio component 684b06c; final source/recovery SHA is recorded in sql-local-asr-stock-ui-program-state.json after seal

CAPABILITIES COMPLETED: explicit CPU ASR architecture; stock schedule review UI; SQL audio browser review/edit/restore and cold read proof within fixture scope

CAPABILITIES PARTIAL: video ASR path; English/auto/base real tests; browser genuine speech, semantic/perceptual quality, event actor correlation, full Mode A/B and acceptance bundles A/B/C; SQL six-target variant family and cross-render TTS reuse

TESTS: 897 full Studio PASS, including 24 stock-panel cases; 113 final stock/media/provider backend PASS; 61 provider/audio SQL PASS after rejected-evidence fix; 24 planner/media PASS including atomic HTTP races; 32 registry/provider safety PASS; 53 Native voice/timeline PASS. Test batches overlap and must not be added.

REAL PROVIDER TESTS: 2 actual local CPU inferences: 1 direct and 1 SQL job. No external provider, paid operation, OAuth read or publishing. Provider billed cost is 0; electricity/hardware cost remains null. Isolated Windows SQL CI dependencies were installed as pinned official PyPI wheels; no model was downloaded.

MOCK TESTS: browser source is owned silence; text/timestamps/identity/stock transport and CI review are fixtures. They are not Owner approval.

EVIDENCE: [portable index](north-star/sql-local-asr-stock-ui-evidence.json); recovery/20261007/sql-local-asr-real-small-vi-n2; sql-local-asr-real-job-win-n1 with 39 custody files; sql-local-asr-real-job-cold-n1; sql-local-asr-real-consumer-n1; sql-audio-rehearsal-20261013; sql-stock-browser-replay-n1. Portable archive contains 181 files, each byte/hash verified. Final HEAD/source/recovery pair is in sql-local-asr-stock-ui-program-state.json after seal.

REGRESSIONS: intermediate failed probes and independent repros remain preserved; no accepted historical media was replaced

EXTERNAL BLOCKERS: deferred Owner listening/UAT; external provider/rights/quality acceptance; Docker/production isolation and separate deployment approval

OWNER ACTION REQUIRED: none for ongoing safe implementation; Owner listening remains deferred

NEXT WAVE: qualified cross-render SQL TTS artifact reuse on separate codex/vf-sql-tts-reuse-01 worktree, without rebuilding Native variants; then remaining original production/media/platform capabilities

Matrix remains 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED: 59 groups unclosed, not a percentage estimate. SOURCE_PRESERVED=YES at the last sealed milestone. PHASE10_TECHNICALLY_READY=YES; OWNER_UAT_REQUIRED=YES; PHASE10_READY=NO. IMPLEMENTATION_COMPLETE=NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO; VIDEO_FACTORY_NORTH_STAR_READY=NO.

Cleanup policy remains unchanged: nine policy-blocked roots and four older OS/browser retained roots are untouched, with no retry or bypass. No freed PC disk bytes are claimed. Approved model/runtime data is still needed for implementation and evidence.
