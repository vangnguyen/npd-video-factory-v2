# QC bằng Vision qua ứng dụng Native

Bộ điều khiển rendered-QC được đăng ký riêng với `LocalServer`, bộ kiểm tra quyền và bước phục hồi của worker. Mặc định tắt; worker không tự tạo hoặc xử lý yêu cầu phân tích. Giao diện Studio riêng chưa có trong bản thay đổi này.

## Cấu hình

Các tham số riêng: `--render-vision-registry`, `--render-vision-directory`, `--enable-render-vision`. Registry công khai và thư mục khóa DPAPI phải nằm ngoài dữ liệu ứng dụng/mã nguồn theo quy tắc bảo vệ hiện có. Phải có xác thực người dùng khi cấu hình provider. Profile phải thuộc đúng workspace, có giá hợp lệ, khóa được bảo vệ và quyền bật của operator. Trạng thái cấu hình không giải mã khóa lúc khởi động, không cấp quyền gửi và không gia hạn quyền duyệt.

Tiêm factory khi kiểm thử chỉ nhận đúng `NativeRenderVisionFactory` với `MockTransport`, đúng root/workspace/thư mục khóa và trạng thái operator. Factory phân tích tài sản gốc hoặc factory có khả năng gửi mạng thật không được tiêm qua đường kiểm thử.

## Luồng thao tác

1. Owner đọc `/api/connections/render-vision`.
2. Người có quyền đọc dự án xem `/api/projects/<id>/render-vision/input/<render-job-id>` để lấy bằng chứng render gốc và SHA256 đầu vào. Thông tin này không cấp quyền phân tích.
3. Owner gửi `RenderAnalyze` tới `/api/projects/<id>/render-vision`, xác nhận riêng việc gửi khung hình video đã render, mức trần và thời hạn.
4. Owner gọi `/<nrvi-id>/process` với SHA256 snapshot gốc. Mỗi yêu cầu chỉ được gửi một lần; hủy dùng `/<nrvi-id>/cancel`.
5. Đọc danh sách có phân trang hoặc `/<nrvi-id>` để xem lịch sử gốc và chi phí. Các trạng thái kết quả chưa rõ/cần kiểm tra không được tự thử lại.

Quyền Owner, cookie, CSRF và Origin được kiểm tra trước đọc body. Các vai editor/reviewer/viewer có thể đọc dữ liệu thuộc workspace nhưng không tạo/gửi/hủy yêu cầu; trạng thái kết nối chỉ cho Owner. Query thừa/lặp, body thừa, khóa bí mật từ client, profile của tài sản gốc, input/configuration/snapshot thay đổi đều bị chặn. Phản hồi đặt `Cache-Control: no-store`.

Khởi động worker chỉ phục hồi claim bị gián đoạn; không giải mã khóa, gọi provider hay gia hạn consent. Khởi động lại không cấu hình provider vẫn đăng ký bộ đọc lịch sử khi bảng gốc tồn tại. Bằng chứng, nhật ký và media được khôi phục bằng bản sao ứng dụng; mọi kiểm tra sử dụng mới vẫn yêu cầu dữ liệu gốc còn đúng.

## Bằng chứng và giới hạn

`docs/north-star/render-vision-http-evidence.json` chỉ mục các kiểm thử HTTP qua socket loopback thật, kiểm thử hồi quy quyền/Phase 10/Vision nguồn cũ và diễn tập có chữ ký. Diễn tập dùng danh tính/khóa giả lập, PNG/PTS/video/checkpoint thật đã có trong kho thử, HTTP provider nội bộ giả lập và bản sao ứng dụng được phục hồi bằng tiến trình mới.

Không có khóa thật, thanh toán, gửi nhà cung cấp thật, UI/browser mới, thay hard QC, duyệt final video, Owner UAT hoặc triển khai production. Các cờ readiness toàn chương trình tiếp tục giữ `NO`. Bước tiếp theo là màn hình duyệt rendered-QC, rồi các consumer thumbnail/OAuth và các phần North Star còn lại.
