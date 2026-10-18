# Báo cáo Export & Delivery

TASK: `VF-FINAL-EXPORT-MANUAL-PUBLISHING-FOCUS-01`

PRIORITY: P0–P6 triển khai và đóng kiểm thử; P7 chuẩn bị nghiệm thu.

STATUS: PARTIAL. Các chức năng dưới đã có mã và bằng chứng kỹ thuật. Lượt API đầy đủ đã kết thúc và có đối chiếu replay; năm ca UAT thật và nghiệm thu của Owner chưa hoàn tất.

HEAD SHA: `1cf600f737c1a52aa05e4a7a9619d361197148cf` tại checkpoint mã ứng dụng; các báo cáo sau checkpoint được ghi riêng. Nhánh `codex/vf-final-export-manual-01` đã push; không merge main.

CAPABILITIES COMPLETED: bốn định dạng xuất; FPS/chất lượng/burn-in/audio; duyệt gắn phiên bản; QC và kiểm hash; MP4/bìa/SRT/caption/ZIP/manifest; history/phân trang/so sánh/tạo gói mới; đối chiếu và tiếp tục sau mất phản hồi/restart; Voice Library/phân vai/từng câu/series/targeted take/người kể tùy chọn. Đây là trạng thái triển khai và kiểm thử, chưa thay cho Owner acceptance.

UI CHANGES: **Xuất video / EXPORT & DELIVERY**; lựa chọn định dạng, nội dung đăng theo nền tảng, bìa, tải file/mở thư mục, QC và lịch sử. **Nhân vật & giọng thoại** dùng chọn giọng thủ công, người kể mặc định tắt. Phân vai thiếu thông tin có hướng dẫn chọn giọng/quyền/câu thoại thay cho yêu cầu xem log. Console đăng API/analytics đang hoãn được ẩn ở chế độ này.

BACKEND CHANGES: immutable delivery versions, approved-artifact binding, physical Full QC, measured dialogue timing/speaker QC, scoped cache/receipt/lease/idempotency, versioned caption/cover/casting/takes/series and recovery. Các chốt quyền, phê duyệt và không tự lặp thao tác trả phí được giữ nguyên. Adapter/publishing/analytics nền tảng cũ còn nguyên.

TESTS: full Studio 2143 pass; renderer 52 pass và TypeScript typecheck pass. Các cohort Native/API có overlap được ghi trong [progress](FINAL_EXPORT_PROGRESS.md); không cộng thành số bài độc lập. Fixture API cũ đóng trong hai cohort 58 pass; Linux security 291 pass/2 root skip, rồi hai ca đó chạy bằng UID/GID 65534 thật đạt 2/2. Native closure 21/22/8 pass; hướng dẫn lỗi 20 pass. Media Linux với công cụ portable: variant 30 pass, uploaded/audio processing 26 pass, storyboard 11 pass, uploaded consumer/silence 14 pass, scene signals 5 pass; media skip replay 20 pass/5 OS skip, rồi đúng 5 ca đó trên Windows đạt 5/5. Ba ca rename dành cho Windows đạt 3/3. Mock TTS và actual WAV/FFmpeg/ZIP được phân biệt; không có inference giọng mới trong lượt này. [Đối chiếu 22 nhóm kiểm thử bắt buộc](FINAL_EXPORT_TEST_REQUIREMENT_MAP.md).

FULL REGRESSION: Native 2285 loaded/2264 run, 3 failure/2 error; 21 ca chưa chạy do shared setup đã replay đạt, các fixture khác được tái hiện/sửa/replay. Đây chưa phải một lượt full Native mới hoàn toàn xanh. Full Linux API **4376 ca: 4310 pass, 26 fail, 0 error, 40 skip / 7823.726s**; 630 file nguồn giữ nguyên. Cả 26 fail do thiếu FFmpeg/FFprobe đã đạt ở replay cùng source; 27 skip đã đạt trên Linux với tool portable, 10 skip đạt bằng UID/OS phù hợp. **Ba ca tranh chấp PostgreSQL thật còn chưa chạy**; không dùng SQLite để chứng nhận chúng. Không cộng replay thành một full pass mới. Docker E2E và production qualification chưa được chứng nhận. [Kết quả gốc](../evidence/final-export-manual-publishing/baseline/api-full-linux-n4.json), [đối chiếu qualification](../evidence/final-export-manual-publishing/baseline/api-full-linux-qualification-n4.json), [chi tiết Native](FINAL_EXPORT_REGRESSION_STATUS.md).

EXPORT ARTIFACTS: [Studio kiểm tra](http://127.0.0.1:62684/native.html) có gói rehearsal riêng, tải MP4/bìa 1080×1920/caption/SRT/ZIP thực tế khớp manifest/hash/CRC. Đây là media và approval fixture, không phải năm ca UAT thật. [Bản nháp hai nhân vật](http://127.0.0.1:62684/native.html?project=67f86fb7112d4d26aace281f31b408e1) chưa chọn giọng/quyền/audio/hình/approval.

RECOVERY EVIDENCE: full baseline Git bundle và các incremental đã verify; code đã push. Checkpoint cuối được ghi riêng trong [source-checkpoint-n7](../evidence/final-export-manual-publishing/recovery/source-checkpoint-n7.json), cần baseline `4162bc32260521277737f7c9ee118b5ba55b3f9b` và full bundle ban đầu. **69 file** log/JSON/XML/script kiểm thử đã đóng gói trong `recovery/20261007/final-export-regression-evidence-n1.zip`: 435990 byte, SHA256 `519881368b6138d6b241fbb98d63368be150357f4c2a2caf824428c17b4d0d12`, CRC và mọi entry hash đạt. [Biên nhận archive](../evidence/final-export-manual-publishing/recovery/regression-evidence-archive-n1.json). Backup review có cả hai dự án: `recovery/20261007/final-export-review-with-drama-draft-n1.zip`, SHA256 `d9e3af93e3a71a8e675e6136e80ccd32366c8445b06dbcbe99c83b080df6c8a0`; restore sang root mới và tải lại MP4 đúng hash. [Biên nhận restore](../evidence/final-export-manual-publishing/recovery/review-with-draft-restore-n3.json). Bản nháp vẫn chưa được duyệt. Không thay video lịch sử.

OWNER ACTION REQUIRED: theo P6, Owner cần tự chọn hai giọng đã cấu hình và khai báo quyền sử dụng để chuẩn bị ca thoại thật; chưa có lựa chọn hoặc quyền nào được suy ra. Sau đó chuẩn bị/duyệt năm ca và kiểm tra UI thực tế/phát âm. Lượt nghe mẫu tên riêng trước đây vẫn được để sau theo chỉ đạo của Owner. [Kế hoạch năm ca](../evidence/final-export-manual-publishing/owner-uat/README.md), [hướng dẫn thao tác](FINAL_EXPORT_USER_GUIDE_VI.md).

NEXT PRIORITY: chuẩn bị năm gói UAT thật sau khi có dự án/tư liệu có quyền, hai lựa chọn giọng và các phê duyệt thực tế; kiểm tra UI 1366/1920/2560 và nghe các bản đích. Ba ca PostgreSQL cần database kiểm thử riêng trước khi có thể chứng nhận. Không tự ghi nhận nghiệm thu hoặc sử dụng database production.

| Trạng thái | Giá trị |
|---|---|
| SOURCE_PRESERVED | YES — checkpoint n7 đã push và bundle verify |
| ACCEPTED_ARTIFACTS_PRESERVED | YES — rehash 15 MP4 sau khi dọn scratch, không đổi |
| RECOVERY_BUNDLE_VALID | YES — n7: 277381 byte, SHA256 `2d41f75c4745029830357a2986b3c57cb3d6b8643f1d20c2bb9ccf671adb150f` |
| FINAL_VIDEO_QUALITY_READY | NO |
| EXPORT_CENTER_READY | NO |
| DELIVERY_PACKAGE_READY | NO |
| EXPORT_HISTORY_READY | NO |
| DRAMA_VOICE_CASTING_READY | NO |
| OWNER_EXPORT_UAT_COMPLETE | NO |
| OWNER_VOICE_UAT_REQUIRED | YES |
| IMPLEMENTATION_COMPLETE | NO — chưa chốt toàn bộ validation/UAT |
| REAL_PROVIDER_ACCEPTANCE_COMPLETE | NO |
| PLATFORM_API_PUBLISHING | DEFERRED |
| ANALYTICS | DEFERRED |
| FULL_TREND_RADAR | DEFERRED |
| PRODUCTION_DEPLOYED | NO |

Dọn sáu thư mục fixture API đã dùng xong bị kiểm duyệt tự động từ chối trước khi chạy (`blocked by policy`, không nêu thêm lý do). Không xóa file hoặc thử cách xóa khác đối với các mục đó. [Biên nhận](../evidence/final-export-manual-publishing/recovery/temporary-fixture-cleanup-denied-n1.json).

Đã dọn tám thư mục scratch Linux riêng sau khi mọi test kết thúc và archive được xác minh: **4524814523 byte logic**. Không tuyên bố dung lượng Windows/VHD vật lý đã giảm; không compact VHD, shutdown WSL, thay dịch vụ hoặc đụng thư mục Windows bị từ chối. Model, venv, tool portable, project, review server và accepted media được giữ. [Biên nhận dọn dữ liệu tạm](../evidence/final-export-manual-publishing/recovery/linux-finished-scratch-cleanup-n1.json).
