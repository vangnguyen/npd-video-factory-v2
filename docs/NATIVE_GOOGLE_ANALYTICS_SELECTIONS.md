# Kết nối OAuth chỉ đọc cho Native Analytics

Phạm vi: thành phần Wave 8/10/15. Chưa chứng nhận toàn bộ Analytics, Mode A/B hay North Star; chưa kiểm thử tài khoản thật, duyệt Owner hoặc triển khai production.

Native Studio có thẻ **Kết nối dùng để đọc thống kê**. Owner đọc cấu hình và quyền OAuth đã cấp, chọn quyền `analytics`, xác nhận riêng việc đọc danh tính kênh và việc chọn kết nối, chuẩn bị rồi bấm xác minh. Xác minh gửi một GET `channels.mine` bằng chính grant đã chọn; kết quả phải là đúng một kênh đã cấu hình. Không tự thu thập thống kê sau thao tác này. Lịch sử và thao tác ngừng dùng kết nối giữ bằng chứng gốc; ngừng dùng là thay đổi cục bộ, không gọi endpoint thu hồi của Google.

## Cấu hình và quyền

Các cờ sau mặc định tắt và độc lập:

- `--enable-google-oauth`: thao tác cấp/làm mới OAuth đã có, cần quyền riêng.
- `--enable-google-analytics-selections`: chuẩn bị/xác minh lựa chọn chỉ đọc.
- `--enable-official-account-reads`: quyền đọc ở account factory; tài khoản cũng phải có `read_enabled=true`.
- `--enable-official-analytics`: bộ thu thập receipt-bound đã có, cần consent mỗi lượt.
- Quyền scheduled refresh và publishing vẫn theo cờ/consent riêng của chúng.

Google grant phải có `youtube.readonly` và `yt-analytics.readonly`. Query doanh thu cần thêm `yt-analytics-monetary.readonly`; thiếu scope bị chặn trước request báo cáo. Xem [Google OAuth cho ứng dụng đã cài](https://developers.google.com/youtube/reporting/guides/authorization/installed-apps) và [Reports.query](https://developers.google.com/youtube/analytics/reference/reports/query).

Account registry giữ schema `native-official-account-registry-v1`. Kiểu `Account` dùng `token_file` cũ giữ nguyên JSON và hash. Kiểu mới `OAuthAccount` yêu cầu explicit `credential_source="google_oauth_selection"`, `google_oauth_slot_id`, alias và target khớp slot `analytics`; không nhận thêm `token_file`. Resolver được nối một lần vào service đúng workspace/root/purpose. Đọc registry, khởi động server, discovery, history và availability không giải mã token. Grant mô phỏng không được gắn vào client mạng thật.

Không có cờ request body để đổi purpose hay bật đọc/xuất bản. Các POST cần current Owner và CSRF trước khi đọc body. UI vẫn cho đọc lịch sử theo quyền đọc; thao tác chọn/ngừng dùng cần Owner. UI tách ID và trạng thái khỏi lựa chọn publishing, chống phản hồi muộn gắn vào dự án khác, giữ idempotency key khi chưa rõ kết quả và không gửi lại tự động.

## Lưu trữ và runtime

`NativeGoogleOAuthSelections` dùng policy purpose cố định khi khởi tạo. Publishing tiếp tục dùng bảng/prefix/schema cũ; analytics dùng bảng `native_google_analytics_selections`, prefix `ngasel_` và schema `native-google-analytics-selection-*-v1`. Mỗi bảng có một lựa chọn active cho mỗi target/workspace; chọn hoặc ngừng dùng analytics không thay đổi lựa chọn publishing của cùng kênh. Không có migration xóa dữ liệu hay sửa journal cũ.

Snapshot giữ source operation/result, slot/client/target, private ciphertext receipt, grant proof, consent Owner, document và request hashes. Kết quả liên kết exact response hash và cost intent trước wire. Tiền không được suy diễn: paid=false và chi phí chưa cung cấp giữ null. Unknown/timeout/crash có journal `outcome_unknown`, không tự chạy lại.

`valid_for_seconds` 60–900 giây là khoảng hoàn tất bước xác minh, không phải TTL mới cho token. Sau khi chọn, runtime tiếp tục kiểm tra current Owner, grant còn hơn 90 giây, ciphertext, slot/target, archive, source/cost và refresh supersession. Đọc availability dùng snapshot WAL chỉ đọc riêng để hoạt động khi publication/analytics đang giữ writer. Private load được kiểm tra lại trước sử dụng. Refresh không tự chọn grant mới và không gia hạn consent thu thập analytics.

Account factory mới cấp đúng `AnalyticsOAuthCredential` cho bộ thu thập đã có. Bộ thu thập vẫn yêu cầu publication receipt đủ điều kiện, query/Owner consent riêng, kiểm tra quyền trước mỗi wire, xác minh kênh/video, giữ zero khác null, lưu snapshot lịch sử và chỉ retry trong consent hữu hạn đã được cấp. Fixture integration kiểm tra selected Bearer, revoke/expiry/private-load/refresh fences, metrics lịch sử và rate-limit backoff; fixture publication là media không phát được và không chứng minh chất lượng video hay khán giả thật.

## API

- `GET /api/connections/google-oauth-analytics-selections`
- `GET /api/projects/<id>/google-oauth/analytics-selections[?limit=25&cursor=ngasel_…]`
- `GET /api/projects/<id>/google-oauth/analytics-selections/<ngasel_id>`
- `POST /api/projects/<id>/google-oauth/analytics-selections`
- `POST /api/projects/<id>/google-oauth/analytics-selections/<ngasel_id>/verify`
- `POST /api/projects/<id>/google-oauth/analytics-selections/<ngasel_id>/revoke`

Create yêu cầu revision, source operation/result hash, hai raw ACK độc lập, ACK mô phỏng nếu phù hợp, thời hạn xác minh và request key. Verify/revoke nhận snapshot hash gốc. Pages bị chặn ở 1–100 bản ghi; cursor khác purpose bị từ chối. Token, callback code, verifier và client secret không xuất hiện trong DTO/UI/log/backup công khai.

## Bằng chứng và giới hạn

Chỉ mục kiểm thử/hashes nằm ở [google-analytics-selection-evidence.json](north-star/google-analytics-selection-evidence.json). Fixture được tạo từ SQLite/DPAPI và protocol mock thực thi, có public backup loại private ciphertext, phục hồi 27 bảng và lịch sử exact trong tiến trình mới không có khóa. Publishing fixture cũ được đọc lại trong tiến trình mới; không thay thế artifact đã chấp nhận.

Kiểm thử DOM/HTTP không phải nghiệm thu browser hay Owner. Docker, tài khoản/provider thật, audience data, các platform khác, production secret custody/ACL/TLS, Windows recovery/retention/soak và toàn bộ luồng A/B/C vẫn là yêu cầu riêng. `IMPLEMENTATION_COMPLETE`, `REAL_PROVIDER_ACCEPTANCE_COMPLETE`, `PRODUCTION_DEPLOYED` và `VIDEO_FACTORY_NORTH_STAR_READY` vẫn NO.
