# Thumbnail từ video đã render trong Studio

Studio có bảng thumbnail cạnh player dọc trong màn hình duyệt video và biên tập shot. Có thể chọn trực tiếp PNG gốc đã đo trên CPU, không cần cấu hình Vision. Timeline, phiên bản dự án và duyệt final video giữ riêng.

1. Mở dự án → Video → Xem bản render để duyệt → Thumbnail từ video đã render.
2. Chọn render đã thành công, qua hard QC và có bằng chứng khung hình gốc; đọc tối đa tám PNG với mốc decoded PTS đã lưu.
3. Chọn một khung hình, xem ảnh và xác nhận lựa chọn riêng. Khung hình có pixel fact `black_sample=true` không được chọn.
4. Nếu muốn tham chiếu kết quả rendered-Vision đã có, chọn kết quả gốc ở bảng QC và xác nhận kèm kết quả. Kết quả giả lập cần ACK giả lập riêng. Thao tác này không gửi lại provider.
5. Bấm Lưu lựa chọn thumbnail. Đọc thumbnail đã lưu để chọn/xem PNG gốc và bằng chứng trong lịch sử. Lưu ảnh không duyệt video hoặc cho phép xuất bản.

Owner/editor có quyền ghi lựa chọn; reviewer/viewer đọc lịch sử và ảnh đúng phạm vi. Giao diện chỉ hiện khi capability `native_render_thumbnail_review=true`; đây là khả năng giao diện cục bộ, không bật provider hay publishing. App hỗ trợ registry và loopback đã có; xác thực, Origin/CSRF và RBAC được kiểm tra trước đọc body.

POST `/api/projects/<project>/render-thumbnails` nhận phiên bản, render job, input SHA256, frame ID/SHA256, ACK thumbnail raw và request key. GET đường dẫn này phân trang25 mặc định,100 tối đa; GET `/<ast_rthumb_id>` trả bản ghi gốc, GET `/<ast_rthumb_id>/image` trả PNG gốc với `no-store`, `nosniff` và header SHA256. Query thừa, scope sai, PNG/checkpoint/input bị đổi hoặc ACK không đúng kiểu bị chặn. Không tạo thêm bản sao ảnh/video.

Phản hồi trễ khi đổi phạm vi/quyền/phiên bản/guard không gắn vào lựa chọn mới. Trạng thái tải dự án được đồng bộ trước khi người dùng chọn video, giữ được lần đọc ảnh đầu tiên. Đổi video/frame xóa ACK. Khi chưa rõ phản hồi lưu, giữ nguyên request key; khi nhận phản hồi hợp lệ, giải phóng key. Ảnh đã tải giữ nguyên node khi đổi ACK hoặc đọc lại cùng lịch sử. Lưới ảnh cuộn tối đa420px; shot vẫn là mặc định và hai chế độ dùng timeline đã có.

Ảnh giữ `rights_status=unknown`, `license=null`, cần kiểm tra quyền xuất bản riêng. HTTP/UI này chưa gắn thumbnail vào metadata/transport xuất bản; cổng thumbnail hiện có tiếp tục chặn. Kết quả Vision giả lập không thành nhận diện ngữ nghĩa thật, confidence đã hiệu chuẩn, quyền phân tích source, phê duyệt final hoặc Owner UAT.

`docs/north-star/render-thumbnail-studio-evidence.json` chỉ mục493 kiểm thử Studio (22 mới),41 kiểm thử Native HTTP/Phase10/access (6 mới), diễn tập24 request có xác thực, tám PNG gốc và ba PNG đã chọn byte-exact. Sáu lựa chọn (ba cũ, ba mới),11 lịch sử Vision, cost/project/timeline/checkpoint/video/PNG/PTS gốc phục hồi nguyên vẹn bằng ứng dụng ở tiến trình mới, không có khóa provider.

Lần phục hồi đầu của diễn tập cuối gặp Windows từ chối rename staging đã kiểm tra. Giữ nguyên staging/log thất bại, phục hồi cùng ZIP đã xác minh sang đích mới và hoàn tất kiểm tra bằng tiến trình mới; không gọi lại thao tác chọn ảnh. Đây chưa phải chứng nhận phục hồi/soak production.

Trình duyệt Studio thật đọc tám tham chiếu PNG, ba lựa chọn cũ, ảnh đã chọn và trở lại biên tập với ACK preview/final/thumbnail đều chưa bật. Kiểm tra DOM1366/1920/2560 không tràn ngang, ảnh đã chọn tải được và lưới cao420px. Screenshot qua công cụ; chưa có screenshot xuất lâu dài hoặc chứng nhận raster đầy đủ. Sau đóng tab/host, toàn bộ dữ liệu gốc vẫn exact.

Không có media/render/provider mới, khóa thật, phí, xuất bản, Owner UAT hoặc deployment. Kiểm tra nghe mẫu tiếp tục để Owner xem sau. Hai Mode và North Star chưa được chứng nhận hoàn tất. Tiếp theo là quyền thumbnail và binding xuất bản riêng, cùng mọi phần còn thiếu của Master Spec.
