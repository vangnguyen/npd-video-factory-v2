# Native multipart ingestion

Đối chiếu Wave 3A của `CODEX_MASTER_SPEC_VIDEO_FACTORY_V2.md`. Phần này bổ sung upload có thể tiếp tục vào Native Studio đang được dùng, qua Store, thư viện tư liệu và timeline hiện có. Không thay kiến trúc hoặc cấp quyền xuất bản.

## Luồng và dữ liệu

Tại Assets, mục **Upload có thể tiếp tục** nhận video, audio, ảnh, logo PNG, nhạc và phụ đề SRT/VTT. Studio gửi từng chunk tối đa 1 MiB và tính SHA256 từng chunk; bộ nhớ dùng để đọc file không tăng theo kích thước toàn bộ file. Người dùng có thể tạm dừng, đọc lịch sử upload và chọn lại đúng file gốc để tiếp tục. Khi tiếp tục, Studio đối chiếu SHA256 của toàn bộ phần đã nhận trước khi gửi phần còn lại.

SQLite lưu yêu cầu có phiên bản, workspace/project, khóa chống tạo trùng, số byte, vị trí/SHA256 từng chunk, trạng thái, hạn nhận 24 giờ và biên nhận asset. Có giới hạn 20 upload chưa hoàn tất và tổng dung lượng khai báo 1 GiB cho mỗi workspace. Lịch sử trả tối đa 50 mục, có cờ `truncated`; phân trang sâu và chính sách lưu giữ dài hạn còn cần hoàn thiện.

Các trạng thái là `receiving`, `validating`, `needs_attention`, `completed`, `cancelled`. Khi mở lại, upload đang xác minh chuyển sang `needs_attention`; hệ thống không tự thêm asset vào dự án. Upload nhận đủ byte có thể được xác minh lại bằng hành động rõ ràng của người dùng. Phần đã nhận được đưa vào backup và đã thử khôi phục vào thư mục mới để tiếp tục.

Máy chủ kiểm tra MIME khai báo, magic byte, giới hạn và nội dung bằng PIL hoặc FFprobe/FFmpeg. Phần mở rộng do người dùng đặt không quyết định loại file. Máy chủ đo SHA256 toàn bộ nguồn, lưu bản gốc và tư liệu đã chuẩn hóa. Logo PNG giữ RGBA/alpha. Phụ đề giữ chữ Việt và cue/timestamp; parser hiện nhận cue văn bản UTF-8 có thứ tự, tối đa 10 phút, không nhận markup hoặc các mở rộng VTT ngoài hợp đồng này.

File trùng trong cùng dự án, cùng MIME/vai trò và cờ minh họa được đối chiếu bằng nguồn bất biến trước khi tái sử dụng. Thêm asset mới và biên nhận upload là một giao dịch; thay đổi dự án tăng revision và bỏ duyệt cũ. Hoàn tất bằng revision cũ bị chặn và giữ phần đã nhận. Gửi lại chunk hoặc yêu cầu hoàn tất không tạo asset thứ hai.

## HTTP và giao diện

`/api/projects/{project_id}/uploads` hỗ trợ POST tạo yêu cầu và GET lịch sử. `/uploads/{upload_id}` đọc một yêu cầu. Các POST `/chunks`, `/complete`, `/cancel` dùng ranh giới đăng nhập, CSRF và quyền edit hiện có; viewer/reviewer có thể đọc. Chunk dùng `application/octet-stream`, `X-VF-Offset`, `X-VF-SHA256` và Content-Length tối đa 1 MiB; không nhận Transfer-Encoding. Thời gian đọc chunk bị giới hạn 15 giây. Phản hồi không được cache.

Capability `native_multipart_upload=true` mới tải module Studio. Khởi tạo module không gửi upload. Phản hồi sai workspace/project, yêu cầu hoặc manifest đã thay đổi, biên nhận bị thay, dữ liệu riêng tư và phản hồi đến sau khi đổi dự án bị từ chối. Người dùng vẫn phải chọn file và xác nhận quyền sử dụng.

Thư viện hiển thị audio bằng audio player và phụ đề bằng cue văn bản có escape; không tạo thumbnail ảnh cho hai loại này. Bộ lọc `visual` giữ ảnh/video cho nguồn hình của shot. Bộ chọn nguồn shot dùng cùng giới hạn; audio/phụ đề không bị gán nhầm thành ảnh.

## Quyền và dọn dữ liệu

Asset mới giữ `rights_status=unknown`. Khai báo quyền sử dụng khi upload không phải bằng chứng giấy phép và không mở cổng publishing. Approval, rights gate và publishing mặc định tắt vẫn được giữ.

Sau khi biên nhận đã commit thành công, hệ thống chỉ xóa chunk thuộc chính upload đó khi vị trí, kích thước và SHA256 vẫn khớp. Hủy upload cũng chỉ dọn các chunk đã xác minh của upload đó. File không chắc chắn được giữ để kiểm tra. Bản gốc, asset, biên nhận, metadata và video nghiệm thu được giữ. Không có tác vụ xóa dữ liệu lịch sử thủ công trong đợt này.

## Bằng chứng và giới hạn

`north-star/multipart-ingestion-evidence.json` ghi nguồn, log, fixture HTTP và phạm vi kiểm thử. Video/ảnh/audio được tạo thực tại máy và được decoder thực kiểm tra; human identity dùng fixture được ký. Các ca Studio dùng controller và DOM giả với DTO lấy từ HTTP thật tại máy. Đây chưa phải kiểm tra trình duyệt hiển thị, người dùng không biết lập trình hoặc Owner UAT.

Chưa đóng toàn bộ Mode B: áp dụng audio/phụ đề vào các track và công cụ chỉnh sửa tương ứng, ASR từ audio upload, chỉnh logo/mask/alpha, soak với file lớn, nghiệm thu giao diện và toàn bộ bundle A còn cần chứng minh. Mode A, Meta analytics, provider thật, Docker, production, bundle B/C và các yêu cầu North Star còn lại vẫn tiếp tục. Không có provider/paid call, publishing thật, merge main hoặc triển khai production. Bảng kiểm vẫn là 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED; còn 59 nhóm lớn.
