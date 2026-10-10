# Native TikTok: upload, async status và biên nhận

Backend này tiếp nối [admission riêng](NATIVE_TIKTOK_DISTRIBUTION_ADMISSION.md), dùng chung publication, Owner grant, intent, cost, queue và recovery hiện có. Nó không chứng nhận đăng thật, ứng dụng TikTok đủ điều kiện, media thật, Owner UAT hoặc toàn bộ Wave 9/Mode A/B.

`NativeTikTokPublishingFactory.execution_supported=true` cho backend này. Ba gate và Owner enablement vẫn mặc định false. [Runtime riêng](NATIVE_TIKTOK_RUNTIME.md) đã nối protected companion registry vào CLI/server startup và các route Owner/CSRF/queue hiện có; luồng đăng TikTok trong Studio còn mở. Creator UI hiện có và quyền đọc creator không tự cấp quyền đăng. Không có cấu hình/secret thật, bài đăng thật hoặc deployment trong bằng chứng này.

## Thực thi qua journal hiện có

1. Publication giữ nguyên draft đã duyệt, dry-run, final, QC, rights, tài khoản, metadata, lựa chọn creator và ciphertext fingerprint ban đầu.
2. Owner cấp grant đăng riêng, hữu hạn. Trước init, worker đọc lại tài khoản và creator bằng protocol chính thức; kiểm tra lựa chọn, disclosure và giới hạn thời lượng hiện tại. Hai response nối với cost receipt và preflight có hash. Một intent init duy nhất được claim trước request.
3. Init thành công giữ `publish_id` thực nhận trong public job. Upload URI được mã hóa DPAPI ngoài source/data root và public backup, với prefix/entropy riêng cho TikTok. Session giữ đúng scope, target, credential/configuration, byte count và hạn một giờ; OAuth token không nằm trong session.
4. Worker gửi tuần tự đúng bytes của final đã duyệt. Mỗi chunk có range/body hash, intent và cost receipt; PUT không chứa Bearer. Init không rõ kết quả chuyển sang review, không tự tạo job mới. Chunk không rõ kết quả chỉ reconcile bằng job ID ban đầu; không tự gửi lại bytes.
5. Reconcile giữ tiến độ thiếu dưới dạng null. Chỉ tiến độ hợp lệ của các chunk đã thử mới được nhận; tiến độ giữa chunk cần review. Throttle/lỗi server tạo backoff có response hash. Phiên upload hết hạn không cấp quyền gửi thêm bytes.
6. Status của job đã upload dùng snapshot gốc cùng grant Owner hiện tại. Sửa timeline hoặc thiếu file local không biến job cũ thành video mới. Init và mọi chunk mới vẫn yêu cầu canonical project/final hiện tại. Queue dùng cùng admission, có số bước/deadline hữu hạn, mặc định tắt.

Quy tắc chunk dùng số chunk làm tròn xuống, gộp phần dư vào chunk cuối và nhận 206/201 theo vị trí chunk. [TikTok Media Transfer Guide](https://developers.tiktok.com/docs/en/content-posting-api-media-transfer-guide).

## Kết quả có điều kiện

`publish_id` theo dõi job, không phải ID bài đăng. Observation giữ status, uploaded bytes có thể null, danh sách ID công khai thực nhận, response/cost hash, thời điểm request và thời điểm quan sát. Với bài public, completion chưa có ID công khai tiếp tục chờ moderation; với bài private, completion có thể không có ID công khai. [TikTok Get Post Status](https://developers.tiktok.com/docs/en/content-posting-api-reference-get-video-status).

Receipt giữ toàn bộ ID thật. `remote_post_id` chỉ có khi đúng một ID; nhiều ID không bị chọn tùy tiện. Không dựng URL và không lấy job ID làm post ID. Response đã nhận khi grant hết hạn/bị thu hồi vẫn là lịch sử, không cho phép request tiếp theo. Mock luôn cho `published=false`; `mock_publication_complete=true` chỉ khi bằng chứng mock hoàn tất.

Public job/preflight/observation/receipt có strict schema, hash và liên kết original draft, final/review metadata, grant, init intent, cost, session và registration event. Đổi job ID rồi tính lại hash riêng không thay được response đã đăng ký. Keyless history không load credential hoặc upload URI.

## Bằng chứng và recovery

Chỉ mục: [tiktok-publishing-evidence.json](north-star/tiktok-publishing-evidence.json). Fixture dùng media không phát được và protocol/Owner/platform mock; DPAPI, SQLite, byte reads, backup và restore chạy thật ở local. Chi phí chưa biết giữ null; không gọi provider thật hoặc thao tác trả phí.

Retainer dùng directory mới có ownership marker, không thay fixture/bundle cũ:

```powershell
$env:PYTHONPATH='C:\vfns01\apps\api;C:\vfns01'
& 'C:\NPD-Video-Factory\runtime\venv\Scripts\python.exe' -X utf8 `
  scripts\north_star_native_tiktok_publishing.py `
  --fixture-root C:\vf-native-fixture-tiktok-publishing-state-03 `
  --restore-root C:\vf-native-fixture-tiktok-publishing-restore-03 `
  --output 'C:\Users\PC\Documents\ChatGPT\Video Factory\recovery\20261007\tiktok-publishing-flow-n3'
```

`--replay` đọc restore trong process mới, factory/queue tắt, không decrypt/replay. Lần n1 gặp lỗi retainer sau khi queue hoàn tất: đọc dispatch DTO như publication DTO. `--resume-finish` lưu đúng job gốc, không gọi thêm provider; raw capture trong bộ nhớ bị mất được ghi rõ. Fixture n2 độc lập xác minh runner đã sửa và giữ wire digest. Cả hai bundle đều được giữ.

Ba bảng TikTok chỉ tạo khi bind factory: `native_official_tiktok_preflights`, `native_official_tiktok_jobs`, `native_official_tiktok_observations`. Constructor cold không thêm chúng vào backup admission cũ. Hồ sơ mốc 270 đọc lại đúng 27 bảng và cùng hash media; execution/queue có 33 bảng.

## Công việc còn lại

Nối reviewed draft/dry-run, profile, approval, queue và status vào Studio; kiểm tra UI/browser và genuine HTTP/provider acceptance; hoàn thiện adapter/analytics còn thiếu; xác minh ứng dụng/credentials/rights/Owner enablement khi được phép. Startup và signed HTTP component có bằng chứng riêng trong [runtime](NATIVE_TIKTOK_RUNTIME.md). Eligibility/audit chưa xác minh; checkbox local không thay [TikTok Content Sharing Guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines/). Tiếp tục toàn bộ Master Spec và bundle A/B/C. `PUBLISHING_READY`, `IMPLEMENTATION_COMPLETE`, `REAL_PROVIDER_ACCEPTANCE_COMPLETE`, `PRODUCTION_DEPLOYED`, `VIDEO_FACTORY_NORTH_STAR_READY` vẫn NO.
