# Đầu vào Vision gắn với video sau render

`NativeRenderEvidenceFrameExtractor` đọc ảnh PNG đã có từ một job render thành công. Bộ đọc kiểm tra workspace, dự án, job, checkpoint, kết quả QC, tài liệu gốc, video, bản thiết kế và thời điểm giải mã. Đầu vào dành cho nhà cung cấp dùng mã `render:<job_id>` và đường dẫn bằng chứng `render-frame://<project>/<job>/<frame>.png`. Nó không nhận ảnh của video nguồn để thay thế ảnh đầu ra.

Mỗi ảnh gửi qua giao thức kiểm thử giữ nguyên byte PNG, SHA256 và thời điểm tương đối của video sau render. Thông tin kích thước gửi cho bộ phân tích là kích thước PNG thực tế. Bộ đọc không tự tạo mô tả cảnh hay bản transcript. Thay đổi ảnh, checkpoint, dữ liệu dự án hiện tại hoặc thuộc tính bộ đọc sẽ làm đầu vào đã chụp bị từ chối.

Có thể đọc lại bằng chứng của một render cũ; trường `matches_current_project_document` cho biết nó còn khớp tài liệu hiện tại hay không. Dù khớp hay không, bộ đọc không cấp quyền gửi ảnh, chi tiền, xuất bản hoặc chấp nhận UAT. Sự đồng ý trước đây dành cho phân tích tài sản nguồn không được dùng lại. Factory hiện có dành cho tài sản nguồn từ chối bộ đọc này trước khi tạo provider hoặc giải mã khóa.

## Bằng chứng và giới hạn

40 kiểm thử liên quan đạt, gồm 5 trường hợp mới và các kiểm thử hồi quy của bộ đọc tài sản nguồn, registry và khóa được bảo vệ. Các trường hợp mới kiểm tra ảnh thật sau render, sai workspace/job/ngữ cảnh, ảnh bị sửa, dữ liệu thay đổi, gửi đúng PNG qua giao thức mô phỏng và việc factory nguồn từ chối đầu vào render.

Hai bài chạy lưu bằng chứng đọc đúng 8 ảnh của Source và storyboard từ dữ liệu gốc lẫn dữ liệu đã phục hồi. Mỗi bài chạy thực hiện một yêu cầu HTTP trong tiến trình bằng `MockTransport`, không kết nối tới dịch vụ ngoài. Các kết quả mô phỏng được lưu riêng và đánh dấu rõ; toàn bộ nhật ký dữ liệu gốc giữ nguyên. Không trích xuất video hay render lại; ảnh PNG hiện có được giải mã và kiểm tra thật bằng Pillow.

Đây là bộ đọc đầu vào có kiểm thử, chưa phải đường gửi Vision thật đã hoàn tất. Cần nối tiếp profile dành riêng cho QC, sự đồng ý Owner có thời hạn và mức phí, controller, nhật ký yêu cầu/kết quả/chi phí, quyền xem và giao diện duyệt. Khóa nhà cung cấp, kiểm thử Vision thật và UAT vẫn chưa có. Các phép đo QC hiện tại tiếp tục quyết định lỗi kỹ thuật; một kết quả Vision không thay thế chúng.

Chi tiết nằm trong `docs/north-star/render-vision-input-evidence.json`.
