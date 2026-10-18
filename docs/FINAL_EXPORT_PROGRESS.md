# Xuất video và bàn giao để đăng thủ công

Chương trình `VF-FINAL-EXPORT-MANUAL-PUBLISHING-FOCUS-01`, bắt đầu 2026-10-18. [Baseline và phục hồi nguồn](FINAL_EXPORT_BASELINE.md).

## Phần đã triển khai

- **P0 hoàn thành:** source branch riêng, Git bundle đầy đủ đã verify, archive riêng 11 file sửa dở, rehash 15 video nghiệm thu. Không thay checkout đang dùng hoặc video cũ.
- **P1 đang đóng:** QC dùng chung đo đoạn im lặng cuối, mặc định quá 2 giây là fail; thiếu phép đo cũng fail. Policy Native, binding thời lượng thực, tên riêng, phụ đề và source-render hiện có được tái kiểm thử. Chưa có Owner listening/UAT mới.
- **P2–P5 bản đầu trên Windows Native:** mục **Xuất video**, caption theo nền tảng, gói MP4/cover/SRT/copy/QC/rights/manifest/ZIP, lịch sử, download, mở thư mục Windows. Export chỉ sao chép đúng byte MP4 đã qua duyệt cuối và chạy lại FullProductionQC trên file giao thực tế.
- Manifest giữ version của dự án/timeline/script/audio/subtitle, profile, hash preview/final, hash approvals, metadata media, caption version và hash từng file. Không có post ID hoặc trạng thái đã đăng.
- Thay đổi project làm bản xuất cũ mang nhãn phiên bản cũ; vẫn tải được bản lịch sử đã bàn giao sau kiểm tra toàn vẹn. Tạo bản mới không thay tệp cũ.
- Exact request key + fingerprint, lease giữa thread/process, thư mục staging riêng, ghi hash custody trước handoff, đối chiếu lại approval/quyền trước ready. Retry sau mất phản hồi/restart dùng lại cùng export; không tự ghi đè output lỗi hoặc đã đổi.
- Caption có CAS/version history, Master/TikTok/Facebook Reels/Instagram Reels/YouTube Shorts; sửa, copy clipboard và tải TXT. Caption không được gửi đến nền tảng.
- Checklist đăng thủ công chỉ lưu trong phiên browser; không xác minh quyền hay tự đăng.

## Kiểm thử đã xác nhận

Các tập dưới có overlap; không cộng thành số lượng bài duy nhất.

| Tập | Kết quả | Log trong recovery/20261007 |
|---|---|---|
| API baseline trước sửa | 52 pass / 51.61s | final-export-baseline-API-n1.log |
| Native baseline trước sửa | 32 pass / 196.937s | final-export-baseline-Native-n1.log |
| Shared trailing QC mới | 22 pass / 1.06s, gồm MP4/AAC thật tổng im lặng <30% nhưng tail 3s bị chặn | final-export-tail-n1.log |
| Native quality sau sửa | 32 pass / 147.322s | final-export-quality-Native-n1.log |
| Native delivery | 13 pass / 25.471s, media thật cục bộ, human approval là fixture | final-export-delivery-Native-n2.log |
| HTTP Native có xác thực | 3 pass / 27.082s, download byte thật, role/CSRF/origin/strict fields/folder action | final-export-delivery-http-n2.log |
| UI delivery bằng Node/fake DOM | 15 pass / 110.6928ms | final-export-delivery-Studio-n2.log |
| Full Studio | 2107 pass, 0 fail/skip / 30.597s | final-export-current-full-Studio-n1.log |
| Renderer | 7 file / 48 pass; TypeScript typecheck pass | final-export-renderer-tests-n1.log; final-export-renderer-typecheck-n1.log |

Studio baseline 66 lỗi do hàm kiểm tra dùng wall clock thay vì clock fixture. Đã sửa riêng injection clock trong harness, không nới kiểm tra phiên production. Full 2092 bài cũ và full 2107 bài có export đều pass.

Full API bị chặn collection 5 module trên Windows: thiếu NumPy ở SQL venv, thiếu websockets và Unix `grp`. Không sửa runtime đã khóa hoặc giả module hệ điều hành. Đang chạy phần còn lại với 5 module nêu rõ được loại khỏi lượt tương thích; không gọi đó là full API pass. Full Native đang chạy; chưa có kết quả tổng. Docker/Linux E2E và toàn bộ Phase 8/9/10 acceptance chưa được tái chứng nhận ở chương trình này.

## Phần còn phải hoàn thành trước khi đánh dấu ready

| Ưu tiên | Trạng thái | Còn thiếu |
|---|---|---|
| P1 | PARTIAL | Bộ quality/cache-invalidation tổng hợp, các ca đích thật và kiểm tra tên/giọng bằng người |
| P2 | PARTIAL | Tùy chọn FPS/quality/burn-in/audio/watermark gắn vào preview/render mới; chọn format phải tạo và duyệt bản tương ứng; UI acceptance 1366/1920/2560 |
| P3 | PARTIAL | Cover upload/candidate/crop/overlay, tái tạo riêng copy variant, duyệt lịch sử caption qua UI |
| P4 | PARTIAL | Thumbnail trong history, xem manifest và so sánh phiên bản qua UI hoàn chỉnh, recreate-package UX |
| P5 | PARTIAL | Chaos/restart thật trong render, mất output folder, staging/collision/tamper giữa handoff và restart; soak và tổng regression |
| P6 | NOT_STARTED trong chương trình này | Voice Library + character/casting theo project + per-line TTS + narrator optional + targeted regeneration + UI/QC |
| P7 | PENDING_OWNER_UAT | 5 case Owner UAT; không tự ghi nhận nghiệm thu |

Các preset 4 hình học đã có hard validation; export bản đầu yêu cầu profile khớp video đã duyệt. Chọn landscape cho MP4 portrait bị từ chối rõ ràng, không transcode âm thầm. FPS/hình/tiếng/phụ đề hiện giữ nguyên bản đã duyệt. Thư mục đầu ra do Native quản lý; chưa có chọn thư mục tùy ý. Hiện không ghi những tùy chọn chưa hỗ trợ thành đã hoàn thành.

Quan sát browser từng bị URL policy từ chối; Node/fake DOM và HTTP không thay cho quan sát UI hoặc Owner UAT. Không dùng browser/CDP khác để vượt chặn. Dọn cache từng bị policy từ chối cũng chưa thực hiện; dữ liệu và artifacts vẫn giữ nguyên.

## Trạng thái công bố

`FINAL_VIDEO_QUALITY_READY = NO`  
`EXPORT_CENTER_READY = NO`  
`DELIVERY_PACKAGE_READY = NO`  
`EXPORT_HISTORY_READY = NO`  
`DRAMA_VOICE_CASTING_READY = NO`  
`OWNER_EXPORT_UAT_COMPLETE = NO`  
`OWNER_VOICE_UAT_REQUIRED = YES`  
`PLATFORM_API_PUBLISHING = DEFERRED`  
`ANALYTICS = DEFERRED`  
`FULL_TREND_RADAR = DEFERRED`  
`PRODUCTION_DEPLOYED = NO`

Owner action hiện không cần cho các phần cài đặt an toàn đang chạy. Listening và UAT vẫn để Owner xem sau theo chỉ đạo trước. Không merge main, không deploy production, không gọi API đăng bài, không mở rộng analytics/winner/learning/trend.
