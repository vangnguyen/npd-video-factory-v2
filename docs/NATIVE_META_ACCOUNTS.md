# Xác minh Page và Instagram trong Native

Component này đưa custody và account preflight của Meta vào journal, worker, cost ledger, API có xác thực và card **Tài khoản nền tảng** hiện có. Không tạo journal riêng, đổi timeline hoặc cấp quyền đăng. Luồng dispatch Meta vẫn là gap mở của Wave 9.

## Phạm vi cấu hình

`native-meta-account-registry-v1` có `version=1`, workspace và tối đa 50 account bindings. Mỗi binding có account reference, credential alias, đường dẫn token ngoài source/state, cờ đọc mặc định false và profile `native-meta-publishing-profile-v1`. Profile ghi target Facebook hoặc Instagram Reels, Page ID, API version bắt buộc và `login_type=facebook_login`.

Đường Facebook Login của Instagram dùng Page được liên kết với tài khoản Professional, theo [collection chính thức của Meta](https://www.postman.com/meta/instagram/folder/u4g5a2a/instagram-api-with-facebook-login). Cách lấy Page token và liên kết được mô tả trong [request chính thức](https://www.postman.com/meta/instagram/request/lpx8lul/get-access-tokens-of-pages-you-manage). Component hiện nhận Page token đã được operator cấp; chưa tự thực hiện OAuth acquisition/refresh hoặc chọn tài khoản từ danh sách chứa raw tokens.

`v24.0` chỉ là version trong fixtures; không phải khẳng định version đang được Meta chấp nhận cho ứng dụng thật. Operator phải cấu hình version, account, scopes và app đủ điều kiện riêng. Truy cập trực tiếp các trang developers.facebook.com trả HTTP429 trong lần kiểm tra này; collection Meta được dùng để đối chiếu hợp đồng. Nghiệm thu phiên bản/permission/app qua provider thật vẫn chưa thực hiện.

## Custody và đọc

`meta_connection.save_token()` là primitive local có chủ đích. Nó ghi DPAPI domain riêng, ACL riêng, không ghi đè token đã tồn tại. Token bind exact profile/Page/target/API version/credential alias, danh sách permissions được khai báo và expiry có timezone. File và registry phải ở ngoài source và state/backup. Startup chỉ đọc metadata/hash, không decrypt, refresh hoặc gọi provider.

Runtime có cờ độc lập `--meta-account-registry` và `--enable-meta-account-reads`. Bật đọc cần protected registry và Native human authentication. Mock injection chỉ nhận exact Meta factory, workspace/root và MockTransport; cờ đọc false tạo bindings không có quyền đọc. Cấu hình/token hash/client/transport thay đổi khóa request mới. Đọc Meta không bật publishing, queue đăng hay YouTube analytics.

Owner đọc cấu hình, chọn account, xác nhận checkbox rồi gửi request verify hiện có. Snapshot giữ profile, cipher hash và cửa sổ 900 giây. Worker kiểm tra canonical revision/document, cấu hình, token expiry, custody và cửa sổ trước/sau từng request. Read client chỉ nhận fixed GET identity fields trên graph.facebook.com; không nhận client endpoints, token, Page override, publish/create/container requests.

Facebook yêu cầu token identity trả exact Page ID. Instagram cần thêm linked Instagram ID và exact identity lookup của ID đó. Đây là hợp đồng fail-closed được kiểm thử local/mock; khả năng endpoint với app/token thật chưa được chứng nhận. Không dùng lookup một public Page khác làm token identity proof.

## Bằng chứng và dữ liệu thiếu

Mỗi request ghi một cost intent và response hash riêng; thiếu phí thực tế giữ null. Kết quả giữ Page/Instagram IDs, ordered observations, cost references và khai báo permissions. `provider_permissions_verified=false`, `app_eligibility_verified=false`, `publishing_enabled=false` luôn được giữ. Page/account match không chứng minh app review, permissions thực tế, quyền nội dung, project approval hoặc Owner publish grant.

History/idempotent replay/page reads kiểm tra cost foreign keys, scope, request fingerprint và response receipts. Window expiry, đổi project/config/cipher, account/link mismatch, unknown network outcome và restart không tự replay. Thông tin đã xác minh vẫn đọc được khi runtime tắt hoặc token mất; đọc history không decrypt. API giữ Owner/CSRF-before-body; viewer chỉ đọc public history. Studio dùng cùng card, giữ ACK tắt, kiểm tra typed Meta source/proof và loại private fields/permission promotion/foreign/late responses.

## Kiểm chứng và việc tiếp theo

[meta-account-evidence.json](north-star/meta-account-evidence.json) index tests, source và rehearsal. `scripts/north_star_meta_accounts.py` tạo actual isolated cookie/CSRF HTTP, DPAPI và SQLite với explicit protocol/Owner/platform mocks: hai checks, ba requests/costs, project nguyên vẹn. Public backup phục hồi cả hai kết quả và ba observations trong một LocalServer mới, không secret/provider load hoặc replay. Frontend fixture lấy trực tiếp từ rehearsal này; DOM tests không phải browser/Owner UAT.

Tiếp tục Meta publication admission, source delivery, async container/upload/status/finish, shared Owner intent/queue/idempotency/unknown-outcome handling, typed Studio review và platform analytics. OAuth, permissions/app/media/rights/provider thật, browser/non-developer/Owner, full Mode A/B/A/B/C và production vẫn chưa nghiệm thu. Counts 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED chưa đổi; `PUBLISHING_READY`, `IMPLEMENTATION_COMPLETE`, `REAL_PROVIDER_ACCEPTANCE_COMPLETE`, `PRODUCTION_DEPLOYED`, `VIDEO_FACTORY_NORTH_STAR_READY` vẫn NO.
