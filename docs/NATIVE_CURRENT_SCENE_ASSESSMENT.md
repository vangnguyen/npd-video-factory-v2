# Đánh giá cảnh và điểm nổi bật từ bằng chứng hiện tại

Studio có thể lưu bản đánh giá từ phân tích nguồn, transcript đang chọn, thông tin audio và khung hình đã đo. Chức năng tiếp tục Master Spec 22–25/28/39–44/64/80 và Wave 3B/3C/3E/3I/8F/16. Đây là một thành phần của Auto Edit; toàn bộ Mode A/B và các wave vẫn PARTIAL.

Trong Assets, Editor đọc nguồn hiện tại, xác nhận dùng dữ liệu đã lưu và lưu đánh giá. Mỗi bản giữ ID, phiên bản, actor từ phiên đã xác thực, checksum nguồn, hash phân tích/transcript và phiên bản dự án gốc. Cùng đầu vào được tái sử dụng; thay đổi transcript làm bản cũ stale. Lịch sử được kiểm tra lại với project version và kết quả tính từ dữ liệu gốc trước khi ghi hoặc chọn. Lưu đánh giá không sửa timeline, điểm cắt im lặng, ASR gốc hoặc file nguồn. Duyệt cũ mất hiệu lực khi dự án đổi.

Ngữ nghĩa ở đây dùng quy tắc trên chữ đã lưu và các phép đo audio/pixel. Vision ngữ nghĩa được ghi NOT_CONFIGURED; confidence thiếu giữ null, độ tin cậy dự đoán chưa được hiệu chuẩn. Không gọi provider hoặc chạy lại ASR. Không coi thay đổi khung mẫu là theo dõi chủ thể liên tục hay chứng nhận clock/PTS nguồn. Các điểm thành phần có giải thích; chuỗi bằng chứng gốc nằm trong chi tiết đóng.

Sau khi xem đánh giá, Editor chọn riêng điểm nổi bật để tạo một phiên bản trên cùng canonical timeline, hoặc tạo Top 3/Top 5 Auto Shorts độc lập. Các bản con có ID/timeline/transcript dẫn xuất riêng, giữ đúng chữ và mốc nguồn đã lưu, lưu tham chiếu đánh giá của dự án gốc và lịch sử nguyên bản. Quyền chọn đánh giá và duyệt video không chuyển sang bản con. Thiếu ứng viên hợp lệ tạo ít hơn số yêu cầu, không bịa thêm. Crop giữa vẫn cần kiểm tra; preview và duyệt riêng vẫn bắt buộc.

Kiểm thử tích hợp phát hiện và sửa: nhân bản dự án chưa có timeline; hash/index và ID mapping của transcript sửa từ khi nhân bản; caption sửa bị đưa sang track khác; metadata caption thay đổi trong track khóa; tham chiếu đánh giá của bản Shorts bị đổi thành ID bản con. Giao diện từ chối biên nhận Shorts không đúng nguồn đã chọn. Bằng chứng lần thất bại được giữ, sau sửa chạy lại bằng tiến trình mới từ backup gốc.

Luồng browser dùng lời nói người thật từ mẫu FLEURS có giấy phép và kết quả CPU ASR thực đã lưu trước đó. Hình nguồn là test pattern sinh; Editor và các xác nhận xem là fixture. Browser lưu một đánh giá từ transcript bản 3, tạo 1/5 Short phù hợp và chọn điểm nổi bật để tạo timeline bản 6/dự án bản 11. ASR, file nguồn và job cũ không đổi. Timeline mới dài 13.2s chưa được preview/render/QC; video 10.5s/QC đạt ở mốc trước được tái sử dụng làm nguồn kiểm tra và còn trong lịch sử, không được trình bày là render mới của timeline bản 6.

DOM được kiểm tra tại 1366/1920/2560px và không tràn ngang. Screenshot do công cụ trả về có kích thước bitmap khác viewport, nên không chứng nhận ảnh chụp toàn viewport hoặc chất lượng hiển thị trên mọi thiết bị. Đây không phải nghiệm thu của người không chuyên, Owner hoặc phép đo chất lượng nhận diện.

WAVE: 3B/3C/3E/3G/3I/8F/16 component

STATUS: LOCAL_REAL_COMPONENT_PASS; full waves PARTIAL

HEAD SHA: parent 656744e799cac80435895b550924048d984b6d74; SQL component 2fa2de85ce67991ce726a8d9bab2e957cbaf6e81; final in recovery/20261007/current-scene-assessment-program-state.json

CAPABILITIES COMPLETED: saved-current-evidence assessment, immutable scoped history, stale-input rejection, explicit highlight selection and independent Shorts, Native Studio/HTTP integration, caption/copy custody fixes; scoped SQL word revisions described in [SQL_TRANSCRIPT_WORD_REVIEW.md](SQL_TRANSCRIPT_WORD_REVIEW.md)

CAPABILITIES PARTIAL: full Mode A/B, genuine uploaded footage/non-developer/Owner acceptance, comprehensive ASR/timing quality, semantic Vision/tracking/confidence/source clock acceptance, SQL Studio word UI and standalone-audio parity, all renderer values/chains, complete provider and production requirements

TESTS: final Native101/Studio811 PASS; SQL75 PASS/2 media skips, including20 new cases; targeted follow-ups overlap these batches and are not added to the total

REAL PROVIDER TESTS: no new provider or local-model inference; real saved CPU ASR/audio/media reused; actual local authenticated HTTP/browser/SQLite transactions and backup/restore are component evidence

MOCK TESTS: ASR/analysis/identity and review fixtures in unit/ASGI/HTTP tests; generated visual and browser Editor fixture; no Owner approval or audience data

EVIDENCE: [indexed evidence](north-star/current-scene-assessment-evidence.json), current browser backup, original/current project facts, events, screenshots and fresh-process restore report; failures retained separately

REGRESSIONS: original ASR/assets/jobs retained; malformed/stale/foreign/role/CSRF/query/body guards; no transferred approval; old accepted artifacts/live source are checked again at final preservation seal

EXTERNAL BLOCKERS: original provider/GPU/Owner/production gates remain; full quality/whole-flow acceptance remains incomplete

OWNER ACTION REQUIRED: none for continued safe implementation; listening/UAT remains deferred; no publishing/deployment approval requested

NEXT WAVE: remaining original Auto Edit, media resolution/cache/providers, platform parity and full North Star capabilities

The browser n2 process ended without its final export. After verifying its exact process and listener had stopped, its original retained state was exported offline, without restarting it. The source root is retained for recovery. Browser n1 and fresh cold roots use owned lifecycle cleanup. Eight older policy-blocked cleanup roots remain untouched; no rejected delete was retried or bypassed.

SOURCE_PRESERVED=YES is justified by the final branch/bundle seal. PHASE10_TECHNICALLY_READY=YES; OWNER_UAT_REQUIRED=YES; PHASE10_READY=NO. Matrix remains 5 IMPLEMENTED_REAL/58 PARTIAL/1 NOT_VERIFIED, 59 unclosed groups. IMPLEMENTATION_COMPLETE=NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO; VIDEO_FACTORY_NORTH_STAR_READY=NO.
