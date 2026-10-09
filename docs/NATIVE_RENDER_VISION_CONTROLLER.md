# Quyền duyệt hữu hạn và nhật ký Vision cho video đã render

`NativeRenderVision` dùng lại kho dự án Native, xác thực người dùng và sổ chi phí hiện có. Cấu hình mặc định tắt. Đây là bước triển khai Wave 4/6/8; chưa đăng ký với HTTP, worker ứng dụng hay giao diện Studio trong bản thay đổi này.

## Phạm vi được duyệt

`RenderAnalyze` chỉ nhận một job render thành công, revision hiện tại, mã cấu hình riêng `nrvp_…`, SHA256 toàn bộ đầu vào render và xác nhận riêng `acknowledged_rendered_frame_analysis=true`. Hợp đồng phân tích tài sản gốc không tương thích. Owner phải được xác thực trong workspace, còn hiệu lực và không thay đổi bản ghi danh tính. Thời hạn 60–900 giây không được vượt quá thời hạn danh tính.

Đầu vào phải khớp bản render, checkpoint, tài liệu, quyền duyệt render gốc, PNG đã giải mã, PTS, ngân sách và quyền dùng hình ảnh. Kiểm tra lại trước/sau giải mã khóa và trước khi gửi. Tất cả tài sản hình ảnh/video đã đăng ký được xét quyền một cách bảo thủ; chỉ PNG từ video cuối cùng được truyền đi. Audio/music không được gửi. Dữ liệu giả lập bị chặn ở đường nhà cung cấp thật. Quyền không rõ yêu cầu một ngoại lệ Owner đã ghi nhận, còn hiệu lực; ngoại lệ này không xác minh giấy phép hay cấp quyền đăng.

Khi đã có giao dịch cơ sở dữ liệu, đầu đọc render dùng đúng kết nối của kho đó để tránh mở thêm một giao dịch ghi lồng nhau. Kết nối từ kho khác bị từ chối.

## Một lần gửi, giữ lịch sử gốc

Ba bảng bổ sung: `native_render_vision_intents`, `native_render_vision_responses`, `native_render_vision_events`. Khóa chống lặp được lưu dạng SHA256. Yêu cầu giống nhau trả lịch sử gốc; thay đổi nội dung với cùng khóa bị chặn. Hai lần xử lý đồng thời chỉ một lần được lấy quyền gửi.

Trước gửi, sổ chi phí dành mức trần đã duyệt cho đúng project/job/provider/model. Phản hồi hoàn chỉnh được ghi trước kiểm tra quyền sau gửi, kể cả khi quyền đã bị thu hồi hoặc nội dung phản hồi không hợp lệ. Nhật ký giữ SHA256 yêu cầu truyền đi, SHA256 phản hồi, trạng thái HTTP, số token nếu có và chi phí tính từ mức giá cấu hình. Không lưu khóa, header xác thực hay Base64 ảnh. Phí hóa đơn thực tế vẫn `null`; phí tính theo token không được coi là hóa đơn đã xác minh. Nếu phí tính vượt trần, kết quả cần kiểm tra.

Timeout hoặc gián đoạn có kết quả chưa rõ không được tự gửi lại. Phản hồi hoàn chỉnh đến sau phục hồi chuyển sang `review_required`. Hủy là dừng xử lý cục bộ, không tuyên bố đã thu hồi yêu cầu gửi ra ngoài. Kết quả luôn mang `advisory_only=true`; không sửa timeline, thay hard QC, duyệt video cuối cùng, đăng nội dung hay tự chấp nhận Owner UAT.

## Phục hồi và bằng chứng

Đọc lịch sử không cần khóa, profile hiện tại, quyền Owner hiện tại hay ảnh còn trên đĩa; việc sử dụng mới vẫn phải kiểm tra lại dữ liệu vật lý. Bản ghi gốc liên kết job, request, response, cost và các cờ quyền được xác minh khi đọc. Sao lưu ứng dụng tính cả ba bảng và chặn lúc còn thao tác `claimed`. Phục hồi không gia hạn quyền hoặc phát lại yêu cầu.

Kiểm thử và bản diễn tập được lập chỉ mục tại `docs/north-star/render-vision-controller-evidence.json`. Diễn tập dùng video/PNG/PTS thật đã tạo bằng FFmpeg/Remotion trong kho thử riêng, xác thực và khóa DPAPI giả lập, sáu lần HTTP nội bộ giả lập; không có khóa thật, gọi mạng thật hay thanh toán. Bản sao ứng dụng được khôi phục trong tiến trình mới với toàn bộ lịch sử và media giữ nguyên. Khóa giả lập tạm được hủy khi diễn tập kết thúc.

Phần còn thiếu: đăng ký ứng dụng/HTTP, giao diện duyệt riêng và nghiệm thu nhà cung cấp thật. Mode A/B, Phase 10 Owner UAT và North Star chưa được chứng nhận hoàn tất.
