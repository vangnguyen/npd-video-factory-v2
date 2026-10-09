# Lựa chọn thumbnail từ render gốc

`NativeRenderThumbnails` lưu lựa chọn ảnh người dùng đã xem vào bảng riêng. Ảnh tham chiếu PNG gốc thuộc checkpoint của video render đã qua hard QC, có SHA256, pixel facts và decoded PTS. Không chép thêm ảnh/video, chạy render, sửa timeline hoặc đổi phiên bản/phê duyệt dự án.

`Create` yêu cầu phiên bản hiện tại, render job, SHA256 input, frame ID/SHA256 và ACK thumbnail riêng. Có thể chọn trực tiếp khung hình CPU mà không có Vision provider. Nếu kèm kết quả rendered-Vision đã có, phải chỉ đúng intent/snapshot/result và xác nhận giả lập nếu cần; lưu response/cost tham chiếu gốc, không gọi lại provider hay dùng quyền phân tích tài sản. Khung hình đen bị loại theo pixel facts đã lưu. Kết quả giả lập không trở thành nhận diện ngữ nghĩa hoặc độ tin cậy đã hiệu chuẩn.

Request key bảo đảm một lựa chọn khi gọi đồng thời/nhận lại phản hồi. Đổi nội dung request với cùng key bị chặn. Lịch sử giữ nguyên sau khi dự án thay đổi; lựa chọn mới cần phiên bản/input hiện tại. Đọc lịch sử không phụ thuộc PNG còn có; lấy ảnh để sử dụng luôn kiểm tra lại tệp, checkpoint và binding render. Phạm vi workspace/project/job/SQLite connection, link/path và dữ liệu bị thay đổi được kiểm tra. Danh sách có phân trang giới hạn25 mặc định,100 tối đa.

Ảnh ghi `source_type=rendered_frame`, `rights_status=unknown`, `license=null`, cần kiểm tra quyền xuất bản; không tự nhận sở hữu, cấp license, duyệt final video hoặc quyền xuất bản. Thumbnail ID có định dạng `ast_rthumb_<32hex>` tương thích trường metadata hiện có, nhưng binding tới publishing chưa được triển khai trong mốc này. HTTP và UI là bước tiếp theo. Cổng thumbnail cũ của publishing vẫn chặn lựa chọn không cấu hình; không có đăng thật.

Bản sao ứng dụng đếm và giữ nguyên bảng lựa chọn cùng mọi bản ghi Vision/cost/project/checkpoint/video/PNG/PTS. `docs/north-star/render-thumbnail-evidence.json` chỉ mục28 kiểm thử Native thumbnail/backup (11 mới), ba lựa chọn trên media thật đã có, 11 lịch sử Vision cũ và phục hồi bằng tiến trình mới không khóa. Không có provider/khóa thật, phí, media mới, Owner UAT, deployment hoặc trạng thái North Star được nâng lên.
