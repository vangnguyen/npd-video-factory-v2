# Giao thức thumbnail YouTube

Giao thức thuần đã được triển khai và kiểm thử mô phỏng. Chưa có thao tác đăng thật, credential thật hoặc tích hợp intent/response bền vững vào Native worker; cổng `YOUTUBE_THUMBNAIL_STAGE_REQUIRED` của video upload vẫn giữ nguyên.

API chính thức dùng POST `thumbnails.set` riêng, với `videoId` và binary image. Phản hồi chứa `items` gồm bản đồ các biến thể thumbnail; width/height có thể thiếu, ảnh trả về có thể được resize. Nguồn đã kiểm tra ngày 2026-10-10: [thumbnails.set](https://developers.google.com/youtube/v3/docs/thumbnails/set), [thumbnail resource](https://developers.google.com/youtube/v3/docs/thumbnails).

`apps/api/app/youtube_thumbnail.py` chỉ nhận PNG RGB/RGBA 8-bit không interlace theo profile nội bộ của các frame QC gốc: tối đa 4 MiB, mỗi cạnh 3–960 px. Đây là giới hạn của ứng dụng, không phải giới hạn của YouTube. Kiểm tra magic, SHA256, IHDR, thứ tự/chunk/CRC, palette, reserved bit và giải nén giới hạn xác nhận scanlines hoàn chỉnh. Không nhận JPEG hoặc thay đổi ảnh, không suy diễn chất lượng/ngữ nghĩa của ảnh.

Request giữ nguyên binary PNG, fixed official HTTPS origin/path/query, Bearer/header riêng tư và Content-Length chính xác. Không tự tạo idempotency header không có trong hợp đồng provider. Response chỉ được ghi nhận khi HTTP 200, JSON không có duplicate key, cấu trúc đúng và CDN references thuộc đúng video trong profile nội bộ. URL/etag chỉ xuất hiện dưới dạng digest; không fetch ảnh từ response. Metrics/dimensions thiếu giữ null. Acknowledgement không xác minh remote pixels, quyền source/nhạc, giấy phép hoặc quyền đăng.

Phản hồi lỗi, timeout hoặc cấu trúc chưa xác nhận giữ uncertain. Helper không có transport tự kích hoạt, retry hoặc quyền phê duyệt. `OfficialHTTPClient` hiện có giữ network tắt mặc định, không redirect/retry/proxy/cookie ngầm.

Kiểm thử API: 59/59 PASS trong 0.97s, gồm 24 kiểm thử mới cùng hồi quy YouTube upload/wire. Hai lỗi setup đầu xuất phát từ pytest dùng tên chứa fixture bytes quá dài cho biến môi trường Windows; đã đặt ID ngắn. Một test mutation ban đầu dùng `dataclasses.replace` với MappingProxy headers; đã dùng dict copy trong test. Log n2 giữ assertion failure, log n3 là kết quả cuối. Không sửa guard video upload để ép test đạt.

Retainer `scripts/north_star_youtube_thumbnail_protocol.py` đọc PNG gốc 540×960, 28,845 bytes, SHA256 `f25b3161f47cbf5587a8c593d021d05cb3ae4251589853a8e7f0d991cf9dac50` từ clone đã khôi phục của mốc trước. Một POST mock thành công, hai mock 429/timeout mỗi lần đúng một POST; không tự gửi lại. Toàn bộ cây file/database/media/journals gốc khớp hash trước/sau, không render hoặc sao chép media mới. Video ID/token/response đều là fixture tổng hợp; external calls và paid operations bằng 0.

Bằng chứng: `docs/north-star/youtube-thumbnail-protocol-evidence.json`; retained `recovery/20261007/youtube-thumbnail-protocol-flow-n1`. Bước kế tiếp là intent/response/cost/receipt bền vững với phê duyệt Owner hữu hạn, scope chính xác của ảnh/render/video và recovery không phát lại. Official activation, quyền source, final approval, xác nhận publish, Owner UAT và triển khai production tiếp tục độc lập. Các adapter còn lại và toàn bộ North Star chưa hoàn tất.
