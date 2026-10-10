# Quyền sử dụng thumbnail trong Studio

Studio nối primitive ngoại lệ thumbnail vào HTTP có đăng nhập và thẻ **Quyền sử dụng thumbnail**, cạnh ảnh gốc và màn hình duyệt video dọc. Mặc định ngoại lệ tắt. `native_render_thumbnail_rights_review` chỉ công bố giao diện đọc/review; không bật quyền, nhà cung cấp, xuất bản hoặc deployment. Ứng dụng đang dùng không bị đổi cấu hình.

Owner đọc trạng thái cấu hình, chọn một thumbnail đã lưu, đọc bằng chứng chính ảnh đó và nhập lý do, tham chiếu cùng thời hạn 1–30 ngày. Hai xác nhận riêng đều bắt buộc: quyết định ngoại lệ cho ảnh và hiểu rằng giấy phép chưa được xác minh độc lập. Cho phép đưa ảnh vào xét duyệt xuất bản là lựa chọn riêng, mặc định không chọn. Ngày giờ được trình bày theo ngôn ngữ tiếng Việt; thời hạn là thông tin quyết định gốc, không tự khẳng định quyền hiện tại còn hiệu lực.

Chỉ Owner hiện hành được ghi hoặc thu hồi. Cookie, Origin/CSRF và quyền Owner được kiểm tra trước khi đọc request body. Bản ghi đóng băng thumbnail snapshot, ảnh/render/input gốc và fingerprint danh tính; primitive kiểm tra lại trước commit. Editor/reviewer/viewer chỉ đọc bằng chứng/lịch sử trong phạm vi dự án. Không dùng token dịch vụ hoặc quyền biên tập để cấp ngoại lệ.

HTTP:

- `GET /api/connections/render-thumbnail-rights`: trạng thái operator, yêu cầu quyền manage.
- `GET /api/projects/{project}/render-thumbnail-rights`: lịch sử gốc, 25 bản ghi mặc định, tối đa 100; cursor gắn workspace/project.
- `GET /api/projects/{project}/render-thumbnail-rights/{override}`: quyết định gốc.
- `GET /api/projects/{project}/render-thumbnail-rights/input/{thumbnail}`: ảnh/render/rights-input gốc.
- `POST /api/projects/{project}/render-thumbnail-rights`: grant/revoke với request key, SHA256 và hai ACK raw.

Giao diện không tự đọc, cấp, thu hồi, gọi provider hoặc đăng. Đổi dự án, phiên bản, quyền, bản nháp, ảnh đã chọn hoặc form khi phản hồi chưa về làm phản hồi cũ không được áp dụng. Khi ghi quyền, thao tác chọn ảnh bị khóa nhưng ảnh gốc đang được xác nhận vẫn giữ nguyên. Phản hồi chưa rõ kết quả giữ request key để đọc lịch sử/gửi lại an toàn; phản hồi thành công xóa xác nhận. Lịch sử UI giữ tối đa 500 bản ghi. Thu hồi chỉ chọn grant mới nhất trong lịch sử đã đọc; backend kiểm tra lại grant gốc mới nhất. Thu hồi không hồi sinh grant trước đó.

Ảnh vẫn `rights_status=unknown`, `license=null`. Ngoại lệ không duyệt quyền source, timeline, phiên bản, video cuối, provider consent, publishing enablement hoặc Owner UAT. Tại mốc của tài liệu này, metadata/transport thumbnail còn là phần tiếp theo; cổng chặn hiện hành vẫn giữ. Mốc metadata/dry-run bổ sung được ghi riêng trong [NATIVE_PUBLICATION_THUMBNAIL.md](NATIVE_PUBLICATION_THUMBNAIL.md); official transport vẫn chưa cấu hình. Không có quyết định pháp lý thật do agent tự cấp.

Kiểm tra: Native 47 HTTP/render-Vision/thumbnail/Phase10/access PASS, gồm 6 HTTP mới; Studio 515 PASS, gồm 22 trường hợp mới cho luồng quyền. Fixtures identity/legal/provider đều ghi rõ mô phỏng. Luồng controller đã triển khai chạy qua 20 HTTP request có đăng nhập, thêm hai grant và một revoke giả lập vào bốn bản ghi cũ. Bảy quyết định, sáu lựa chọn thumbnail, 11 lịch sử Vision và toàn bộ project/canonical/video/PNG/PTS/cost/journals được đối chiếu chính xác rồi khôi phục qua tiến trình ứng dụng mới không có provider key, ngoại lệ tắt và không tự bật quyền. Không tạo media/render/provider/phí mới trong luồng này.

Trình duyệt IAB thật chỉ đọc bản sao riêng: sáu ảnh đã chọn, bảy quyết định, PNG gốc 540×960 tải được, mọi ACK chưa chọn. Kiểm tra DOM tại 1366/1920/2560 không tràn ngang; chuyển xem dọc/biên tập giữ lịch sử, không có console error. Ảnh chụp 1366 được xem qua công cụ, không xuất thành artifact hay chứng nhận pixel ở ba độ rộng. Không bấm lưu/thu hồi/duyệt final/publish. Tab đã đóng, viewport đã khôi phục; host không còn listener. Handle host mất sau ranh giới lượt công cụ, nên integrity được kiểm tra độc lập từ dữ liệu hiện tại với snapshot gốc của backup, không giả định host shutdown đã chạy.

Bằng chứng mới: `docs/north-star/render-thumbnail-rights-studio-evidence.json`; diễn tập `render-thumbnail-rights-studio-flow-n2`, backup SHA256 `439ad417ea5494ffcdacb5f8c611e52d63e40c343d9aa15bdd7b561cf720ee8b`. Luồng n1 trước cải thiện ngày giờ được giữ làm bằng chứng lịch sử. Chưa có Owner legal override thật, real-provider acceptance, deployment hoặc đủ điều kiện hoàn tất North Star.
