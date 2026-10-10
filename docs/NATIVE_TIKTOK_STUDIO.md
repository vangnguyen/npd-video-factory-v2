# TikTok trong Native Studio

Studio dùng cùng publication, Owner grant, worker, queue và journal với [runtime TikTok](NATIVE_TIKTOK_RUNTIME.md). Không tạo engine đăng riêng hoặc thay timeline. Gate đăng, queue và quyền Owner vẫn mặc định tắt. Component này chưa chứng nhận browser/Owner UAT, ứng dụng đủ điều kiện, provider thật hoặc toàn bộ Mode A/B.

## Luồng review

1. Đọc cấu hình và cấp consent đọc creator riêng. Chọn video cuối đã duyệt; lưu bản nháp với privacy, tương tác, AI/music/commercial disclosure và review hiện có.
2. Chọn bản nháp đã lưu. Nút **Kiểm tra mô phỏng từ draft TikTok đã chọn** tạo dry-run từ đúng final và toàn bộ metadata snapshot. Form khác không thay metadata của đường này. Dry-run cần duyệt/chạy riêng.
3. Trong **Xuất bản qua API nền tảng**, chọn profile TikTok và đọc video/draft. Chỉ cặp đúng revision/final/metadata/creator configuration/cipher/target mới được chọn. Không gọi account-checks YouTube hoặc override metadata/lịch cho TikTok.
4. Chuẩn bị review qua request có schema TikTok. Owner phải cấp grant đăng riêng, hữu hạn. Mỗi bước cần đọc trạng thái mới và checkbox riêng; kết quả chưa rõ yêu cầu đọc lại, không tự replay.
5. Dùng chung queue hữu hạn khi cấu hình/consent cho phép. Status đã upload hoặc reconcile giữ job gốc khi timeline chuyển phiên bản; bytes mới vẫn cần nguồn hiện tại. Gia hạn dùng snapshot/dispatch version gốc và response gia hạn thực nhận.

Lịch sử/config hỗ trợ cả YouTube và TikTok. Profile change hoặc đọc lại cấu hình bỏ source choices/cursors/consent cũ và loại response đến muộn; đường YouTube/thumbnail/schedule hiện có được giữ. Getter draft nối controller dry-run, không tự duyệt/gửi khi chọn draft.

## Kết quả và dữ liệu thiếu

Private completion có thể không có ID công khai. Public completion thiếu ID tiếp tục chờ moderation. Nhiều ID được giữ tất cả; job ID không phải post ID, không dựng URL. DTO có strict schema/scope, liên kết draft/final/job/observations/receipt, giới hạn kích thước và chặn private fields. Server admission vẫn là authority cho mọi thao tác.

Analytics/refresh Native hiện chỉ có adapter YouTube. Publication TikTok hiển thị chưa cấu hình, không tạo dữ liệu khán giả và không gửi ID TikTok sang route YouTube. Analytics TikTok/Meta vẫn là yêu cầu mở.

## Bằng chứng

[tiktok-studio-evidence.json](north-star/tiktok-studio-evidence.json) ghi fixture, tests và flows. Fixture gồm DTO từ owned HTTP/backend local với protocol/Owner/platform mock và media không phát được. Tests kiểm tra private, moderation, multiple IDs, unknown chunk, gia hạn sau timeline edit, quyền, drift/scope/idempotency, profile change, draft handoff và analytics fence.

`scripts/north_star_tiktok_studio.py` dùng fake DOM, controller Studio thật và cookie/CSRF HTTP tới server riêng: tạo/duyệt/chạy dry-run, tạo publication/duyệt riêng, init/chunk/status. Không dùng browser để đăng. N1 kết thúc processing trong UI rồi hoàn tất bằng poll Python rõ ràng; giữ nguyên bằng chứng. N2 hoàn tất cả hai poll từ UI: 24 request, một init/chunk, 11 nullable costs, zero paid/provider calls. Public backup và cold LocalServer restore giữ đúng publication/job/receipt, không private load/replay. Temporary source fixtures được dọn theo lifecycle chuẩn.

Không suy ra browser rendering, Owner UAT, media thật, legal/account eligibility, provider acceptance hoặc production từ fake DOM/HTTP/mock. Tiếp tục browser/non-developer acceptance khi surface có sẵn, Meta execution/analytics và toàn bộ Master Spec/bundle A/B/C. `PUBLISHING_READY`, `IMPLEMENTATION_COMPLETE`, `REAL_PROVIDER_ACCEPTANCE_COMPLETE`, `PRODUCTION_DEPLOYED`, `VIDEO_FACTORY_NORTH_STAR_READY` vẫn NO; `OWNER_UAT_REQUIRED` YES.
