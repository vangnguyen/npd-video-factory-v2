# Đối chiếu 22 nhóm kiểm thử Export

Áp dụng cho `VF-FINAL-EXPORT-MANUAL-PUBLISHING-FOCUS-01`. Đây là bản đồ yêu cầu tới mã kiểm thử, không phải biên bản Owner acceptance. Kết quả, lỗi ban đầu và replay nằm trong [regression status](FINAL_EXPORT_REGRESSION_STATUS.md). Các cohort trùng nhau không được cộng thành số bài độc lập.

Các đường dẫn dưới nằm trong `services/windows_native/tests/`, trừ khi ghi rõ API. Fixture dùng âm thanh tone, nội dung tự tạo và approval kiểm thử được phân biệt với giọng/nội dung/approval thật.

| # | Yêu cầu kiểm thử | Mã kiểm thử chính | Giới hạn còn phải xác minh |
|---:|---|---|---|
| 1 | Output profile validation | `test_export_encoder.py`, `test_narrated_export_settings.py`, `test_narrated_canvas.py` | Bốn hình học đã có encode/QC cục bộ; xem bản đích trong UAT |
| 2 | Proper-name TTS | `test_north_star_quality.py`, `test_dialogue_plan.py` | Chuẩn hóa đủ ba tên; mẫu giọng thật lịch sử chưa có phán quyết nghe của Owner |
| 3 | Timeline/audio duration binding | `test_north_star_quality.py`, `test_dialogue_audio.py`, `test_dialogue_runtime.py` | PCM thật đo thời lượng, giọng nhiều nhân vật là mock; cần nghe thoại thật |
| 4 | Trailing silence QC | `test_north_star_quality.py`; API `test_final_export_quality.py` | Đuôi AAC ba giây phải fail; âm lượng đo được không tự chứng minh lời nói rõ |
| 5 | Stale audio invalidation | `test_source_audio_cache.py`, `test_dialogue_audio.py`, `test_dialogue_plan.py` | Thay giọng/câu/provider/quyền phải kiểm lại; không có inference giọng mới trong đợt này |
| 6 | Stale preview invalidation | `test_narration_preview.py`, `test_dialogue_runtime.py` | Có canonical edit, byte/pixel evidence và quyền giọng thay đổi |
| 7 | Stale final export invalidation | `test_manual_delivery.py`, `test_drama_http.py`, `test_narrated_export_settings.py` | Lịch sử giữ bản đã duyệt khi xuất; không duyệt thay cho phiên bản hiện tại |
| 8 | Subtitle sync | `test_narrated_media_captions.py`, `test_dialogue_qc.py`, `test_manual_delivery.py` | ASS/SRT/Vietnamese và cửa sổ người nói có kiểm; cần xem chữ/nghe giọng thật, không giả word alignment |
| 9 | Aspect-ratio validation | `test_north_star_quality.py`, `test_export_encoder.py`; API `test_final_export_quality.py` | Geometry/SAR/rotation/crop phải hợp lệ; kiểm crop ngữ nghĩa trên ca đích còn mở |
| 10 | Export versioning | `test_manual_delivery.py`, `test_export_history_pagination.py` | Bản mới không ghi đè file/bản duyệt cũ; UI thực tế chưa nghiệm thu |
| 11 | Delivery package creation | `test_manual_delivery.py`, `test_delivery_recovery.py` | Có rehearsal tải HTTP thực tế; chưa phải năm gói UAT thật |
| 12 | Manifest integrity | `test_manual_delivery.py`, `test_delivery_recovery.py` | Hash/byte length/ZIP CRC và chống sửa handoff; không chứa secrets |
| 13 | Cover export | `test_delivery_covers.py` | Magic/MIME/hash/crop/JPG/PNG/provenance; logo chỉ khi cấu hình hợp lệ, Owner đánh giá bìa đích |
| 14 | Caption variant persistence | `test_manual_delivery.py`, `test_export_history_pagination.py` | CAS, idempotency, lịch sử Master/platform copy; không đăng caption lên nền tảng |
| 15 | Output-folder failure | `test_manual_delivery.py`, `test_delivery_recovery.py` | Thư mục Native quản lý; không tuyên bố có tùy chọn đường dẫn tùy ý |
| 16 | Duplicate export prevention | `test_manual_delivery.py`, `test_delivery_recovery.py` | Exact replay và concurrent request giữ một output/version |
| 17 | Restart recovery | `test_export_render_recovery.py`, `test_delivery_recovery.py`, `test_dialogue_runtime.py` | Có child process thật thoát giữa/sau checkpoint; restore review sang root mới đã kiểm |
| 18 | Disk/write errors | `test_manual_delivery.py`, `test_delivery_recovery.py` | Lỗi disk/write/partial/collision/corruption được tiêm trong vùng test; không làm đầy ổ production |
| 19 | Drama casting | `test_drama_casting.py`, `test_drama_http.py` | Library/version/rights và project cast riêng; Owner chưa chọn hai giọng thật |
| 20 | Optional narrator | `test_dialogue_plan.py`, `test_dialogue_runtime.py` | Mặc định tắt; flow mock hai người qua render/QC/package không cần narrator |
| 21 | Per-line TTS | `test_dialogue_audio.py`, `test_dialogue_vieneu.py`, `test_dialogue_runtime.py` | Adapter local có pin/custody và mocked child transport; giọng thật hai nhân vật chưa được tạo/duyệt |
| 22 | Targeted regeneration | `test_dialogue_audio.py`, `test_dialogue_reuse.py`, `test_dialogue_runtime.py` | Đổi một giọng/take giữ clip khác và visual; unknown outcome không tự lặp inference |

Full Studio kiểm logic điều khiển và lỗi có hướng dẫn; HTTP kiểm auth/origin/CSRF/RBAC và tải bytes. Chúng không thay cho quan sát browser ở 1366/1920/2560 hoặc thao tác của người dùng. Lần quan sát browser bị policy từ chối được giữ là giới hạn, không dùng kênh khác để vượt chặn.

P7 vẫn cần năm gói đích: NPD dọc, ngang, SRT riêng, burn-in, hai nhân vật khác giọng/người kể tắt. Không tự tạo approval hay khai báo quyền thay Owner. [Kế hoạch UAT và Studio riêng](../evidence/final-export-manual-publishing/owner-uat/README.md).

`OWNER_EXPORT_UAT_COMPLETE=NO`; `PLATFORM_API_PUBLISHING=DEFERRED`; `ANALYTICS=DEFERRED`; `FULL_TREND_RADAR=DEFERRED`; `PRODUCTION_DEPLOYED=NO`.
