# Duyệt QC video đã render trong Studio

Studio có màn hình QC bằng Vision trong khu vực duyệt video dọc và biên tập shot. Chỉ hiện trong phiên có xác thực registry; tính năng giao diện không bật provider. Kết nối vẫn tắt mặc định, không tự gửi, không tự thử lại và không dùng quyền phân tích tài sản gốc.

## Thao tác

1. Chọn dự án và mở Video → Xem bản render để duyệt → QC video đã render · Vision.
2. Chọn video render thành công có bằng chứng QC khung hình gốc. Đọc tối đa tám PNG với mốc giải mã gốc; mỗi tệp được kiểm tra lại phạm vi, SHA256 và binding render trước trả về.
3. Owner đọc cấu hình, chọn profile riêng cho rendered-QC, nhập trần VND và thời hạn60–900 giây, xác nhận gửi các khung hình. Profile giả lập cần xác nhận giả lập riêng.
4. Ghi nhận quyền phân tích chỉ tạo ý định có thời hạn. Bấm Phân tích một lần để gửi đúng snapshot đã duyệt; bấm Hủy yêu cầu để hủy cục bộ. Một kết quả chưa rõ phải được đọc/kiểm tra trước khi tạo yêu cầu mới.
5. Đọc lịch sử để xem phản hồi gốc, khung hình, ứng viên thumbnail và chi phí. Người xem có quyền đọc lịch sử và PNG đúng dự án, kể cả khi khóa/provider đã vắng; quyền đọc không cấp quyền gửi.

Đổi dự án/workspace/phiên bản/quyền hoặc có chỉnh sửa chưa lưu làm mất binding thao tác. Đổi video xóa input và ACK. Trả lời đến muộn không được gán sang lựa chọn mới. Kết quả QC chỉ hỗ trợ người kiểm tra: không sửa timeline, thay hard QC, duyệt final video hay cho phép xuất bản. Token cost chưa phải hóa đơn; số chưa có giữ trạng thái chưa có. Nhãn giả lập và chưa hiệu chuẩn hiện rõ.

Khung hình được bố trí trong lưới cuộn có chiều cao tối đa420px. Đổi biểu mẫu/đọc lại cùng lịch sử giữ nguyên các image node đã tải; không tạo lại toàn bộ ảnh. Mốc thời gian hiển thị tiếng Việt với tối đa hai chữ số thập phân. Shot vẫn là giao diện mặc định, Advanced Timeline và nguồn timeline giữ nguyên.

## HTTP và bằng chứng

PNG dùng `/api/projects/<project>/render-vision/input/<job>/frame/<0..7>`, cookie xác thực/RBAC đọc dự án, `image/png`, `no-store`, `nosniff`. Phạm vi khác, query thừa, tệp bị thay đổi, hard link/path không hợp lệ hoặc binding render thay đổi đều bị chặn. Header no-store được gửi một lần. Lịch sử gốc được đọc riêng, không phụ thuộc việc tái phân tích.

`docs/north-star/render-vision-studio-evidence.json` chỉ mục471 kiểm thử Studio,35 kiểm thử Native HTTP/Phase10/access và diễn tập23 HTTP có xác thực, tám PNG gốc, một response provider nội bộ giả lập, một hủy,11 lịch sử phục hồi bằng tiến trình mới không khóa. Bằng chứng video/timeline/checkpoint/PTS/PNG và nhật ký cũ được giữ nguyên.

Trình duyệt thật đã đọc tám ảnh gốc và chín lịch sử trong app tắt provider, chuyển qua lại chế độ duyệt/biên tập và kiểm tra bố cục DOM1366/1920/2560. Không tràn ngang; kiểm tra DOM không chứng nhận raster đầy đủ ở các độ phân giải này. Có screenshot qua công cụ, không có bản xuất screenshot lâu dài. Post-browser application kiểm tra dữ liệu gốc byte-exact.

Không có nhà cung cấp thật, khóa thật, phí, nhận diện ngữ nghĩa thật, duyệt video cuối, Owner UAT hoặc deployment. Consumer chọn thumbnail từ rendered-QC và gắn vào publication còn là bước tiếp theo. Các trạng thái sẵn sàng North Star và hai Mode tiếp tục chưa hoàn tất.
