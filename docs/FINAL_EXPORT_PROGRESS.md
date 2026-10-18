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
- Bìa đã hỗ trợ upload kiểm tra magic/MIME/SHA256, dedupe; chọn frame, ảnh project hoặc thumbnail candidate đã lưu; crop theo tỷ lệ, JPG/PNG, chữ tiếng Việt và logo chỉ khi cấu hình hợp lệ. Bìa tải lên mặc định quyền unknown, không tự nâng thành owned.
- Caption đã có chọn bản lịch sử và tái tạo riêng variant từ Master/kịch bản bằng thao tác cục bộ; không giả là đã gọi AI hoặc đăng bài. History có thumbnail và so sánh thông số phiên bản.
- Tạo lại ZIP sinh delivery mới từ các file/hash của bản lịch sử, chạy lại QC, giữ nguyên bản trước kể cả ZIP trước hỏng. Lost response của thao tác này giữ đúng endpoint/key. History có đối chiếu/tiếp tục khi tab browser đã mất receipt; ngừng yêu cầu giữ nguyên file và chặn request-key cũ tự hồi sinh.
- Backup nhận biết export đang chuẩn bị và đếm các journal/cover/caption mới. Đã restore một export vào thư mục mới và kiểm tra lại manifest/video; đã thử child process thật thoát ngay sau handoff rồi đối chiếu lại cùng một export.
- P2 trên video nguồn và storyboard có giọng đã chuẩn bị: 24/25/30/60 FPS, 3 mức chất lượng allowlist, bật/tắt audio và burn-in. Cài đặt nằm trong canonical metadata, làm mất duyệt/preview cũ; projection không xóa hay sửa clip gốc. SRT riêng vẫn có khi không burn-in. UI chặn gói khi cài đặt chưa áp dụng. Các video chưa chuẩn bị giọng vẫn giữ giới hạn và cần chuẩn bị trước; không giả tạo audio.
- Bộ kiểm tra mới đã render thật narration 24 FPS/high và 25 FPS/small với âm thanh tắt/phụ đề không burn-in nhưng có SRT. Dùng PCM tổng hợp và approval fixture, không phát sinh suy luận TTS, không phải speech hay Owner UAT. Chỉnh shot giữ cài đặt xuất và làm mất duyệt cũ. UI đổi hình học dùng revision/hash mới trả về rồi mới lưu cài đặt, không dùng CAS cũ.
- Native có capability chế độ xuất thủ công; UI ẩn các console tài khoản/OAuth/publication/analytics/winner/learning đang hoãn. Adapter, API contract và dữ liệu lịch sử vẫn giữ nguyên.
- Đã lưu [gói kỹ thuật cục bộ và hash](../evidence/final-export-manual-publishing/delivery-package/retained-local-rehearsal.json), cùng [bản backup/restore](../evidence/final-export-manual-publishing/recovery/retained-local-restore.json). Media tổng hợp, approval bằng fixture, không phải 5 case Owner UAT. Lượt rehearsal đầu đặt đường secret vắng mặt bên trong data root nên backup từ chối đúng; n2 sửa riêng config cách ly, không ghi lại video/manifest đã tạo.

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
| QC geometry/final freeze | 30 pass / 1.52s, bao gồm bộ trailing trước đó | final-export-aspect-n2.log |
| Cover/recovery/media | 31 pass / 130.477s, có actual images/MP4 và fault injection; tập có overlap với 13/3 trước | final-export-recovery-cover-Native-n2.log |
| Resume và restore | 13 pass / 72.373s | final-export-history-resume-Native-n1.log |
| HTTP + backup regression | 22 pass / 46.315s | final-export-http-backup-Native-n1.log |
| Thoát process thật | 1 pass / 20.475s; owned child exit 86, lease được OS giải phóng, một export được đối chiếu | final-export-process-exit-Native-n1.log |
| UI mở rộng | 20 pass / 150.0543ms | final-export-history-resume-Studio-n2.log |
| Source export settings | 5 pass / 62.517s, có hai ca render thật 24/25 FPS; 21 Node / 234.3394ms; 9 renderer; typecheck pass | final-export-presentation-Native-n2.log; final-export-presentation-Studio-n2.log; final-export-encoder-renderer-n1.log |
| Narrated export + HTTP | 8 pass / 105.517s, có preview/render/QC/SRT thật cục bộ; 27 Node pass / 156.0184ms | final-export-narrated-variants-Native-n4.log; final-export-narrated-settings-Studio-n1.log |
| Full Studio hiện tại | 2119 pass, 0 fail/skip / 34129.3777ms | final-export-current-full-Studio-n2.log |

Studio baseline 66 lỗi do hàm kiểm tra dùng wall clock thay vì clock fixture. Đã sửa riêng injection clock trong harness, không nới kiểm tra phiên production. Full 2092 bài cũ và full 2107 bài có export đều pass.

Full API bị chặn collection 5 module trên Windows: thiếu NumPy ở SQL venv, thiếu websockets và Unix `grp`. Không sửa runtime đã khóa hoặc giả module hệ điều hành. Lượt tương thích còn lại đang chạy, đã xuất hiện failures và skip; chưa có tổng hoặc phân loại, không gọi đó là pass. Full Native vẫn đang chạy. Hai lượt rộng được khởi chạy trước phần mở rộng cover/recovery và QC geometry; kết quả sau cùng không tự chứng nhận những phần được thêm sau lúc khởi chạy. Docker/Linux E2E và toàn bộ Phase 8/9/10 acceptance chưa được tái chứng nhận ở chương trình này.

## Phần còn phải hoàn thành trước khi đánh dấu ready

| Ưu tiên | Trạng thái | Còn thiếu |
|---|---|---|
| P1 | PARTIAL | Bộ quality/cache-invalidation tổng hợp, các ca đích thật và kiểm tra tên/giọng bằng người |
| P2 | PARTIAL | Source và storyboard có prepared narration đã có FPS/quality/burn-in/audio gắn preview/render; còn video watermark khi cấu hình và UI acceptance 1366/1920/2560 |
| P3 | PARTIAL | Các chức năng cover/copy đã có và được kiểm thử cục bộ; còn UI acceptance thực tế, quyền nội dung và bundle UAT đích |
| P4 | PARTIAL | History/thumbnail/compare/recreate đã có; còn UI acceptance thực tế và các ca đích |
| P5 | PARTIAL | Export handoff/restart/collision/tamper/disk error/backup-restore đã có bằng chứng; còn restart giữa render, soak và tổng regression |
| P6 | NOT_STARTED trong chương trình này | Voice Library + character/casting theo project + per-line TTS + narrator optional + targeted regeneration + UI/QC |
| P7 | PENDING_OWNER_UAT | 5 case Owner UAT; không tự ghi nhận nghiệm thu |

Các preset 4 hình học có hard validation; gói phải khớp video đã duyệt. Đổi format từ Export Center áp dụng lại cấu hình dự án và cần preview/duyệt mới; video nguồn còn hỗ trợ FPS/quality/burn/audio. Không transcode âm thầm một MP4 đã duyệt thành file khác. Thư mục đầu ra do Native quản lý; chưa có chọn thư mục tùy ý. Không ghi những tùy chọn chưa hỗ trợ thành đã hoàn thành.

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
