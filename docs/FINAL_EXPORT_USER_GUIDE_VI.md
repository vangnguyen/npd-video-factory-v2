# Xuất video để đăng thủ công

Áp dụng cho bản **Windows Native** có mục **Xuất video / EXPORT & DELIVERY**. Chức năng đang ở nhánh kiểm thử riêng; chưa cập nhật ứng dụng production. Không cần đọc JSON, tìm ID hoặc mở thư mục evidence để thao tác trong Studio.

1. Mở dự án và lưu các chỉnh sửa. Nếu dự án cần tạo lời đọc, hoàn thành bước chuẩn bị giọng và áp dụng thời lượng đã đo.
2. Vào **Xuất video**. Chọn định dạng: dọc 1080×1920, ngang 1920×1080, vuông 1080×1080 hoặc feed 1080×1350. Video ngắn mặc định dùng khung dọc. Chọn FPS, chất lượng, âm thanh và phụ đề ở các dự án có hỗ trợ.
3. Nếu đã đổi cài đặt, bấm **Áp dụng định dạng · tạo lại preview để duyệt**. Nếu hệ thống yêu cầu xem lại crop, chỉnh crop/reframe trong phần dựng rồi quay lại. Bản đã duyệt trước đó không được đổi định dạng âm thầm.
4. Bấm **Tạo preview**. Xem và nghe từ đầu đến cuối; kiểm tra tên riêng, phần cuối lời thoại, nhạc, phụ đề và khung hình. Duyệt đúng phiên bản hiện tại để tạo video.
5. Chạy tạo/render video bằng nút trong phần **Video của bạn**. Chờ QC hoàn tất. Nếu QC lỗi, sửa nguyên nhân được báo rồi tạo lại preview và duyệt bản sửa.
6. Trong **Duyệt video cuối**, xem và nghe file render, điền người duyệt, xác nhận đã kiểm tra rồi duyệt làm bản cuối. Chỉ bản này mới được tạo gói bàn giao.
7. Trong **Caption & nội dung đăng**, chọn Master Copy hoặc bản TikTok/Facebook Reels/Instagram Reels/YouTube Shorts. Sửa tiêu đề, caption, mô tả, hashtag và CTA; bấm **Lưu nội dung**. Có thể **Copy caption**, tải TXT hoặc chọn bản lịch sử để sửa thành bản mới.
8. Chọn tên file, SRT riêng và ảnh bìa. Bìa có thể lấy khung theo giây từ video, ảnh project, candidate đã có hoặc ảnh tải lên. Chọn JPG/PNG, crop và chữ; logo chỉ xuất hiện khi có cấu hình và nguồn hợp lệ. Việc tạo bìa không tự xác nhận quyền sử dụng ảnh.
9. Tạo gói bàn giao, rồi dùng **Tải video MP4**, **Tải ảnh bìa**, **Tải phụ đề SRT**, **Tải gói ZIP** hoặc **Mở thư mục đầu ra** khi runtime hỗ trợ. Chỉ các file thực sự có mới được đưa vào gói.
10. Dùng checklist trong Studio để rà lại nội dung và quyền. Tự mở nền tảng, chọn tài khoản/quyền riêng tư và tải file lên bằng tay. Studio không gửi caption hoặc video lên mạng xã hội.

## Khi cần sửa hoặc phục hồi

- Đổi script, giọng, âm thanh, phụ đề, crop, asset, timeline hoặc cài đặt xuất sẽ yêu cầu preview và approval mới. Bản lịch sử giữ nhãn **Đã duyệt khi xuất**, không duyệt thay cho dự án hiện tại.
- **Tạo lại gói thành bản mới** giữ nguyên các bản trước. Không tự ghi đè một video đã được duyệt.
- Nếu mất phản hồi hoặc đóng tab, dùng lịch sử và **Đối chiếu / tiếp tục lần xuất**. Không cần tìm request ID. Nếu ngừng một lần xuất, file đã có vẫn được giữ.
- Nếu ổ đĩa thiếu chỗ hoặc không ghi được, kiểm tra dung lượng/quyền ghi rồi tiếp tục yêu cầu cũ. Nếu thư mục biến mất, kết nối lại ổ đĩa hoặc phục hồi backup; không đổi tên tùy tiện các file trong gói.
- Nếu ứng dụng đóng giữa render, job cần được tiếp tục rõ ràng. File partial không phải bản cuối; bản hoàn tất vẫn phải qua QC và duyệt.

Các thao tác trên đã có kiểm thử kỹ thuật. Quan sát UI trên các kích thước màn hình và nghiệm thu năm ca cuối vẫn đang chờ; không coi hướng dẫn này là biên bản Owner UAT.
