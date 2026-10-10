# Chọn Google OAuth credential cho worker publishing Native

Increment này nối grant OAuth có purpose `publishing` đã được lưu với đúng kênh YouTube và resolver của worker. Đây là kiểm chứng thành phần bằng protocol mock và tài nguyên Windows local. Publishing toàn phần, provider thật, nghiệm thu UI trong browser, Owner UAT và North Star vẫn chưa hoàn tất.

## Luồng và quyền

Owner đọc cấu hình và lịch sử quyền đã cấp, chọn đúng operation thành công, xác nhận riêng việc chọn credential và việc đọc danh tính kênh. Request giữ project revision/document, source operation/result, slot/client/target, grant receipt/proof, current Owner và cửa sổ 60–900 giây. Lựa chọn được ghi trước khi giải mã hoặc gọi provider. Một thao tác riêng `verify` mới thực hiện GET `channels.list?mine=true` bằng chính publishing grant; kết quả phải chứa đúng một kênh khớp target.

Sau khi xác minh, resolver có thể trả `PublishingOAuthCredential` trong memory. Không có token trong API, SQLite, logs, Studio, fixture public hoặc backup. Mỗi lần lấy credential kiểm tra lại Owner, project archive, slot, encrypted-file hashes, hạn token và trạng thái nguồn refresh; kiểm tra lần nữa sau private load. Refresh không tự chọn grant mới. Một refresh claim hoặc kết quả chưa rõ chặn grant cũ; grant mới cần lựa chọn và xác minh riêng. Thu hồi lựa chọn là thao tác local, không revoke token tại Google và không xóa bài.

Việc chọn credential không bật publishing, không gia hạn consent của từng publication, không thay thế rights/QC/platform/account/approval gates, không tạo queue và không gọi upload. Analytics purpose không được dùng thay publishing purpose. Lựa chọn publishing cũng không cung cấp credential cho analytics.

## Cấu hình

Registry publishing giữ schema v1 và contract `Binding` cũ với `token_file` nguyên vẹn. Binding mới phải có tag `credential_source: google_oauth_selection`, `google_oauth_slot_id`, exact profile/credential alias và ba publishing gates. Không được trộn tag mới với token file. Resolver được gắn đúng một lần sau khi runtime OAuth đã khởi tạo; thiếu slot/grant giữ `NOT_CONFIGURED`. Registry bytes, target, root, workspace, database, runtime/client/transport và private receipt được pin.

`--enable-google-oauth-selections` tắt mặc định; khi bật cần runtime OAuth đã bật và cấu hình dedicated client hợp lệ. Flags này cho phép bước chọn và đọc danh tính kênh, không bật `--enable-official-publishing`. Publishing registry gates, protected session custody, xác minh tài khoản hiện có và phê duyệt từng video vẫn bắt buộc. Startup, discovery và history không giải mã private grant. Protocol mock không được mount vào publishing client mạng thật.

## API và Studio

- `GET /api/connections/google-oauth-selections`: metadata runtime, Owner manage permission.
- `GET /api/projects/{project}/google-oauth/selections[/{selection}]`: lịch sử project/workspace, bounded pagination.
- `POST .../selections`: chuẩn bị chọn, raw acknowledgement riêng và idempotency key.
- `POST .../selections/{selection}/verify`: xác minh và chọn bằng snapshot SHA đã duyệt.
- `POST .../selections/{selection}/revoke`: ngừng dùng lựa chọn local.

Các POST cần Owner hiện tại và CSRF trước khi đọc body. Studio có card “Kết nối dùng để xuất bản”, lựa chọn source grant, hai acknowledgement, dấu mock, consent window, chuẩn bị/xác minh/thu hồi và lịch sử. Không có startup fetch, refresh tự động, xác minh ngầm hoặc upload. Response về muộn/khác scope/source/snapshot không được gắn vào project mới; kết quả chưa rõ giữ request key và yêu cầu đọc lịch sử trước khi thao tác tiếp. DOM tests không phải browser/Owner acceptance ở 1366/1920/2560.

## Journal và recovery

`native_google_oauth_selections` là journal additive. Chỉ một lựa chọn active cho một target trong workspace. Reader kiểm tra immutable snapshot/result, nguyên nguồn OAuth và ledger account-read/response binding. Lịch sử vẫn đọc được khi runtime tắt hoặc không mount private keys. Account lookup có ledger riêng, `paid=false`, estimated/actual cost `null`; không giả chi phí bằng zero.

Claim chưa xong khi restart thành `outcome_unknown`, gồm crash window giữa cost intent và attach reference; không tự gửi lại provider request. Backup đếm journal mới và từ chối claim đang chạy; private DPAPI vault nằm ngoài backup public. Fresh-process replay kiểm tra exact toàn bộ 27 bảng journal và lịch sử mà không giải mã token.

Factory được đọc bên trong giao dịch publication. Resolver dùng snapshot WAL chỉ đọc (`mode=ro`, `query_only=ON`), tránh nested `BEGIN IMMEDIATE`. Các thao tác chọn/xác minh/thu hồi vẫn dùng giao dịch ghi durable. Provider response không tự phục hồi claim đã mất hoặc vượt consent/source/Owner fence.

## Bằng chứng và giới hạn

Evidence index: [google-oauth-selection-evidence.json](north-star/google-oauth-selection-evidence.json). Retainer: `scripts/north_star_google_oauth_selections.py`; nguồn và backup dùng namespace fixture riêng, không thay accepted video. Worker test chạy synthetic nonplayable final/QC/rights/human fixtures: xác minh đúng grant, một initialization, ba chunk, processing poll và mock receipt; thu hồi giữa initialization/chunk chặn request tiếp. Không coi đây là media E2E hay Owner acceptance.

Native core/HTTP/worker/registry/recovery tests, toàn bộ Studio suite và retained public backup/replay được index riêng. Log thử nghiệm thất bại được giữ: import fixture sai, dict receipt access, nested writer lock và duplicate intent trong setup. Các lỗi đã sửa và kiểm thử lại; không báo những log này là PASS. Không có real Google OAuth/channel/upload, new paid operation, Owner UAT, main merge hoặc production deployment.

Google mô tả grant/scope riêng trong [YouTube authentication](https://developers.google.com/youtube/v3/guides/authentication) và kết quả kênh của user đã authorize qua `mine=true` trong [channels.list](https://developers.google.com/youtube/v3/docs/channels/list). Các giới hạn journal, Owner/window, exactly-one-channel, restart và không chọn grant ngầm là safeguards của Video Factory.

Remaining: analytics-purpose grant selection; credential/session lifecycle cho Meta/TikTok Native execution; genuine scoped client/provider/channel/rights/platform acceptance; browser/Owner flows; isolated Docker/deployment/soak; full original Mode A/B and acceptance A/B/C. Counts remain 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED. IMPLEMENTATION_COMPLETE, REAL_PROVIDER_ACCEPTANCE_COMPLETE, PRODUCTION_DEPLOYED và VIDEO_FACTORY_NORTH_STAR_READY đều NO.
