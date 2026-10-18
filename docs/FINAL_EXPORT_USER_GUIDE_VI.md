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
- Dùng **Xem thêm bản cũ** hoặc **Xem thêm nội dung cũ** để mở các phiên bản ngoài trang đầu. Xem lịch sử không ghi đè bản caption đang sửa.
- Nếu mất phản hồi hoặc đóng tab, dùng lịch sử và **Đối chiếu / tiếp tục lần xuất**. Không cần tìm request ID. Nếu ngừng một lần xuất, file đã có vẫn được giữ.
- Nếu ổ đĩa thiếu chỗ hoặc không ghi được, kiểm tra dung lượng/quyền ghi rồi tiếp tục yêu cầu cũ. Nếu thư mục biến mất, kết nối lại ổ đĩa hoặc phục hồi backup; không đổi tên tùy tiện các file trong gói.
- Nếu ứng dụng đóng giữa render, job cần được tiếp tục rõ ràng. File partial không phải bản cuối; bản hoàn tất vẫn phải qua QC và duyệt.

## Thoại nhiều nhân vật

1. Mở **Nhân vật & giọng thoại**, bấm **Tải thư viện & phân vai**. Cần có kịch bản và shot đã lưu. Phần này dành cho dự án kể chuyện; video nguồn vẫn dùng Auto Edit hiện có.
2. Owner có thể thêm giọng preset local trong **Thư viện giọng dùng chung**. Chọn rõ preset, tên hiển thị và thông tin quyền sử dụng. Mặc định quyền chưa xác định; hệ thống không tự chọn giọng hoặc xác nhận quyền thay Owner. Giọng được lưu theo phiên bản.
3. Bấm **Bắt đầu phân vai**, thêm nhân vật và chọn giọng riêng. Chọn người nói, shot và nội dung từng câu. Có thể chia câu tại khoảng trắng, chuyển thứ tự hoặc xóa câu đang sửa. **Có người kể** mặc định tắt; không cần người kể để render.
4. Bấm **Lưu thoại & phụ đề vào timeline**. Thao tác cập nhật chính timeline đang dựng, giữ tư liệu hình ảnh và xóa approval cũ. Nếu đang dùng cách đọc một giọng cũ, chọn rõ ô chuyển sang phân vai; bản cũ giữ trong lịch sử.
5. Bấm **Kiểm tra phân vai để tạo audio**. Chọn thời lượng **Theo lời đọc** trong Thương hiệu & mẫu nếu được yêu cầu. Giọng chưa khai báo quyền, phiên bản đã đổi, câu chưa có người nói hoặc bộ giọng local chưa sẵn sàng sẽ chặn tạo audio.
6. Trong **Lời đọc & thời lượng đã đo**, duyệt nội dung để tạo audio, chủ động tạo lời đọc, nghe và xem thời lượng, rồi áp dụng. Tạo preview có tiếng và duyệt lại trước khi render. ASS/SRT giữ người nói; không giả nhận căn chỉnh từng từ.
7. Đổi giọng tại nhân vật rồi lưu/kiểm tra lại. Muốn take mới, chọn **Tạo lại riêng câu này**, kiểm tra và duyệt lại. Câu khác được tái sử dụng từ cache đã kiểm hash; không tạo lại tư liệu hình ảnh.
8. **Phân vai dùng lại cho series** lưu nhân vật và lựa chọn giọng để áp dụng vào phim khác. Không mang theo lời thoại, timeline hoặc approval của phim cũ. Mỗi phim có bản phân vai riêng.

Đổi hoặc thu hồi giọng trong thư viện khiến bản hiện tại cần kiểm tra lại. Export cũ vẫn giữ nhãn **Đã duyệt khi xuất**, tải được từ lịch sử và không duyệt thay cho phân vai mới. Nếu mất phản hồi khi lưu, thử lại đúng thao tác đang chờ; không tự gửi lại TTS/render.

Các thao tác trên đã có kiểm thử kỹ thuật. Quan sát UI trên các kích thước màn hình, giọng thật mới và nghiệm thu năm ca cuối vẫn đang chờ; không coi hướng dẫn này là biên bản Owner UAT.
