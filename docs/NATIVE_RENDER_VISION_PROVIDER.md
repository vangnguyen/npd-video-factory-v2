# Cấu hình Vision dành riêng cho QC

Profile `native-render-vision-profile-v1` và registry `native-render-vision-registry-v1` dành riêng cho đánh giá chất lượng video sau render. Profile dùng mã `nrvp_`, không nhận profile phân tích tài sản nguồn. Chúng tái sử dụng bộ giữ khóa được bảo vệ và bộ phân tích Vision có cấu trúc hiện có; không dùng lại sự đồng ý gửi ảnh của tài sản nguồn.

Profile và quyền bật của ứng dụng đều mặc định tắt. Khởi tạo, đọc registry và xem trạng thái không giải mã khóa. Cấu hình và các byte registry được chụp bằng hash, kiểm tra lại khi dùng; thay đổi file trong lúc đọc cũng bị từ chối. Giá ước tính và đơn giá cần có giá trị hợp lệ để cấu hình đường gửi thật.

Factory chỉ nhận bộ đọc ảnh của đúng workspace và render còn khớp tài liệu dự án hiện tại. Đường gửi thật bắt buộc có callback kiểm tra quyền duyệt hiện tại và callback ghi nhận kết quả, mức sử dụng và chi phí. Callback phải đồng bộ; giá trị trả về giả hoặc callback bất đồng bộ không được dùng làm kiểm tra quyền. Cấu hình, đầu vào và quyền duyệt được kiểm tra trước và sau giải mã khóa, rồi trước khi gửi.

Callback không phải bằng chứng Owner đã duyệt. Controller có sự đồng ý có thời hạn, ngân sách, xác thực Owner, nhật ký bền vững và giao diện duyệt vẫn cần được triển khai. Factory không tự đăng ký vào ứng dụng đang chạy và không tự gửi ảnh. `CONFIGURED` chỉ mô tả cấu hình kỹ thuật; `provider_authorized=false`, `automatic_dispatch=false` và quyền xuất bản vẫn tắt.

## Kiểm chứng

6 kiểm thử mới và 46 kiểm thử liên quan đạt. Chúng kiểm tra mặc định tắt, không đọc khóa khi khởi động, sai loại profile/đầu vào, giá không hợp lệ, trùng dữ liệu JSON, thay đổi registry, thiếu controller hoặc nhật ký, thu hồi quyền, dữ liệu cũ, và giao thức mô phỏng với ảnh PNG thật.

Bài chạy lưu bằng chứng dùng dữ liệu Source gốc và đã phục hồi. Mỗi bộ dữ liệu đi qua một yêu cầu HTTP trong tiến trình bằng `MockTransport`, giữ đúng 8 ảnh, PTS và hash; quan sát kết quả và mức sử dụng được ghi lại. Khóa giả được tạo trong thư mục tạm, được bảo vệ bằng cơ chế hiện có và xóa sau kiểm thử. Nhật ký ứng dụng gốc giữ nguyên. Không đọc khóa thật, không gọi nhà cung cấp ngoài hoặc phát sinh phí.

Chi tiết nằm trong `docs/north-star/render-vision-provider-evidence.json`. Gửi Vision thật, controller Owner, nhật ký vận hành, UI và nghiệm thu North Star vẫn chưa hoàn tất.
