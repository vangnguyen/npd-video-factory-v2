# Sửa từ và mốc thời gian transcript trong Native Studio

Phần này tiếp tục Master Spec 21/22/24/28/39–44/55/64/80 và Wave 3B/3G/3I/6E/8F/16. Đây là kiểm chứng một phần Auto Edit; các wave và Mode A/B đầy đủ vẫn PARTIAL.

Trong Assets, người biên tập đọc transcript đã lưu, chọn nguồn và đoạn, phát file nguồn, sửa chữ hoặc mốc đầu/cuối, thêm/bỏ từ hoặc cụm, rồi xác nhận quyết định trước khi lưu. Danh sách có phân trang 25 từ. Không chạy lại ASR, không cấp duyệt video. Viewer chỉ đọc; Editor mới được lưu. Cookie, quyền và CSRF được kiểm tra trước body; file phát nằm trong đúng dự án và được kiểm tra checksum, hỗ trợ Range.

Mỗi lần lưu tạo phiên bản transcript mới và giữ ASR gốc. Chữ/mốc sửa tay có confidence=null, actor từ phiên đăng nhập, provenance và hash riêng; không được ghi là phép đo độc lập. Mốc ASR vẫn là ước lượng. Từ không được vượt nguồn, chồng lấn, đi qua khoảng audio thiếu hoặc điểm cắt đã giữ trên timeline. Phiên bản dự án, transcript và timeline cùng được kiểm tra. Sửa làm mất duyệt cũ. Không thay file nguồn, dữ liệu ASR hoặc phân tích gốc; ngữ nghĩa scene/highlight vẫn được đánh dấu cần cập nhật.

Phụ đề dẫn xuất cập nhật trên canonical timeline hiện có; video/audio/B-roll và bố trí phụ đề sửa riêng được giữ. Track khóa từ chối thay đổi cùng toàn bộ transaction. Khi chỉnh tốc độ/cắt shot tiếp, mốc từ đã lưu tiếp tục được dùng và bản sửa tay không bị gắn nhãn provider. Bản sửa chỉ chữ vẫn không có word alignment. SQL API hiện chưa có endpoint sửa mốc từ tương đương; không tuyên bố toàn bộ nền tảng đã đồng nhất khả năng này.

Kiểm tra render phát hiện hai lỗi nối với word review: làm tròn biên nguồn có thể bỏ mất từ đầu, và metadata dành cho sửa chỉ chữ đã loại word alignment. Đã sửa cả hai, giữ tọa độ nguồn tường minh, không thêm epsilon hoặc căn chỉnh giả. Phụ đề karaoke dùng đúng chữ/mốc đã lưu, còn bản sửa chỉ chữ tiếp tục bị chặn khi thiếu word alignment.

Luồng thực tế cục bộ dùng lời nói người thật từ mẫu FLEURS có giấy phép đã được cố định ở bằng chứng ASR trước; hình là test pattern sinh, danh tính và xác nhận nghe/duyệt đều là fixture CI. Browser lưu bản 2, sửa `tóc,` thành `lông,` và chọn mốc cuối từ đầu 1.8s. Sau sửa lỗi nối, một lần review CI tường minh tạo bản 3 để dựng lại phụ đề. Đây không phải nghe/nghiệm thu của Owner hay phép đo chính xác timing.

Nguồn 13.2s ban đầu bị QC chặn vì 3.02s im lặng cuối. Báo cáo lỗi được giữ, không giảm ngưỡng. Điểm cắt CI không phá hủy dữ liệu gốc giữ nguồn đến 10.5s, sau từ cuối 9.74s và hoạt động audio đo được đến 10.18s. Preview đủ hiệu ứng và render 1080×1920/30fps thực tế đạt QC; im lặng cuối 0.32s, không cấp final-video acceptance. Bản gốc 13.2s và ASR không đổi. Luồng audio riêng qua upload theo chunk và model small trên CPU tạo transcript gốc/phiên bản sửa; cả hai dự án phục hồi chính xác qua tiến trình mới, không gọi lại provider.

92 Native, 795 Studio và 16 API đạt; các batch Native 11 linked và 14 source-track/HTTP kiểm tra thêm sau sửa chồng lặp nên không cộng thành tổng mới. B-roll tái dùng nguồn không nhân đôi hoặc thay đổi phụ đề của track nguồn chính. Bằng chứng có HTTP thực tế với danh tính fixture, DOM/browser tại 1366/1920/2560 không tràn ngang, actual CPU ASR, preview/render/QC và cold restore. Không tuyên bố typography/perceptual/non-developer usability hoặc đầy đủ Mode B đã được nghiệm thu. Các thử lỗi của helper, guard word alignment và trailing silence được giữ riêng.

Tiến trình phục vụ browser kết thúc mà không có export cuối; state gốc được kiểm tra và export offline, không khởi động lại mù. Các thư mục tạm mới của media/restore đã dọn theo lifecycle. Xóa thư mục browser `C:/Users/PC/AppData/Local/Temp/vf-word-browser-_v8y_jnm` bị automatic execution review từ chối, lý do `blocked by policy`; thư mục giữ nguyên, không retry/bypass. Đây là hành động cleanup bị chặn thứ 8; không xóa các root đã bị chặn trước, source hay 15 artifact lịch sử.

WAVE: 3B/3G/3I/6E/8F/16 component

STATUS: LOCAL_REAL_COMPONENT_PASS; full waves PARTIAL

HEAD SHA: parent 536b69452d9bea9ee313e24f89c5de38dcc8bb28; final in recovery/20261007/native-transcript-word-review-program-state.json

CAPABILITIES COMPLETED: scoped Native word/timing UI and HTTP, immutable version/hash/actor history, canonical caption mapping, word-safe cut guards, source playback, selected transcript render evidence, scoped actual media/restore proof

CAPABILITIES PARTIAL: SQL API word-edit parity, automatic calibrated alignment, comprehensive language/name/noise quality, full transcript segment restructuring, refresh of scene/highlight semantics, genuine user footage/non-developer/Owner/full Mode A/B/production acceptance

TESTS: Native92/Studio795/API16 PASS; Native11 overlapping linked and Native14 source-track/HTTP follow-ups PASS

REAL PROVIDER TESTS: 2 actual local small-model CPU inferences across browser-source and audio-source cases; actual FFmpeg/renderer; no remote-provider acceptance

MOCK TESTS: identity, listening acknowledgement and approval fixtures; ASR fixtures in unit/HTTP regressions; generated visual and fixture DOM; no fabricated benchmark ASR result

EVIDENCE: [indexed evidence](north-star/native-transcript-word-review-evidence.json); portable ZIP, browser state backup, original/current transcript, canonical timeline, preview/final, subtitles, audio, QC, job events, costs and exact two-project cold restore

REGRESSIONS: original ASR/assets/accepted artifacts preserved; locked/dirty/stale/foreign/CSRF/source-change guards; text-only caption guard; final video still requires separate review; final seal rechecks historical artifacts and live source

EXTERNAL BLOCKERS: original Owner/provider/GPU/Docker/production gates remain; source quality and whole-flow acceptance remain incomplete; one new temporary-root cleanup denied

OWNER ACTION REQUIRED: none for continued safe implementation; UAT/listening remains deferred; no publishing or deployment approval requested

NEXT WAVE: genuine source/operator/quality acceptance and remaining original Mode A/B, media, profiles, Trend, publishing/analytics/learning, Agent Hub and production requirements

SOURCE_PRESERVED=YES is established by the final preservation seal. PHASE10_TECHNICALLY_READY=YES; OWNER_UAT_REQUIRED=YES; PHASE10_READY=NO. Matrix remains 5 IMPLEMENTED_REAL/58 PARTIAL/1 NOT_VERIFIED, 59 unclosed groups. IMPLEMENTATION_COMPLETE=NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO; VIDEO_FACTORY_NORTH_STAR_READY=NO.
