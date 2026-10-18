# Owner UAT — Drama và chọn giọng

**Chưa nghiệm thu.** Các ô dưới đây dành cho Owner tự kiểm; chương trình không đánh dấu thay Owner.

Mở [Tạo video mới](http://127.0.0.1:62684/?new=1) hoặc [phim mẫu chưa duyệt](http://127.0.0.1:62684/?project=4a492a1795ae4b83b393a20db6f623a7). Nếu tab đã mở từ trước, tải lại trang để nhận bản ứng viên. Kiểm phiên bản trong **Cài đặt → Thông tin ứng dụng**, bản dựng `drama-usability-03`, source `C:\vfdr03`.

1. **Kịch bản:** chọn Phim Drama; đặt tên; kiểm mặc định 9:16; lưu/dán lời thoại. Hành động trong ngoặc không nằm trong nội dung được đọc. Câu thiếu người nói phải cần chọn. Có thể lưu nháp và mở lại.
2. **Nhân vật & giọng:** xác nhận An/Bình hoặc nhân vật của bạn; giữ người kể tắt. Nghe nhiều mẫu; chọn hai giọng và lưu phân vai. Thử dùng cùng giọng cho hai vai: có cảnh báo nhưng vẫn lưu được. Không xem việc chọn giọng là duyệt mọi audio về sau.
3. **Hình ảnh & cảnh:** tải tư liệu có quyền hoặc chọn từ thư viện; gán cho từng cảnh; kiểm crop/thứ tự. Trang trống phải có hướng dẫn và nút tiếp tục phù hợp. Không đòi nhập ID.
4. **Dựng & xem thử:** kiểm tra phân vai; duyệt nội dung để tạo thoại; theo dõi tiến trình từng câu/nhân vật; nghe từng câu; áp thời lượng đo được. Đổi một giọng và xác nhận nhân vật khác/tư liệu vẫn được giữ. Xem và nghe preview rồi duyệt đúng phiên bản.
5. **Xuất video:** tạo video cuối, kiểm QC và xem lại toàn bộ; duyệt tệp cuối; tải MP4, bìa, SRT, caption và ZIP khi có; mở thư mục. Tự đăng thủ công, không có bước đăng API.

- [ ] Nghe rõ và đủ lời thoại, tên riêng phù hợp, không im lặng dài hoặc bị cắt câu.
- [ ] Tỷ lệ đúng, không méo/cắt mất hình, phụ đề và dấu tiếng Việt đúng người nói.
- [ ] Người kể tắt vẫn đi hết luồng; mở lại giữ phân vai và bước đang làm.
- [ ] Mỗi mẫu là đúng giọng của card; chỉ một mẫu phát; lỗi/thử lại rõ ràng.
- [ ] Bàn phím, nhãn, nút bị vô hiệu và hành động tiếp theo dễ hiểu.
- [ ] Video thường và xuất video cũ vẫn dùng được sau khi mở Drama.
- [ ] Tự hoàn thành mà không CLI, ID, JSON hoặc tìm thư mục evidence.
- [ ] Kiểm ở 1366×768, 1920×1080 và 2560×1440.

Mẫu kỹ thuật local thật (tư liệu minh họa QA, approval fixture, **không phải phim Owner đã duyệt**):

- [MP4 7,37 giây](C:/vfct/drama-uat-real-n1/deliveries/6b13c09d9f19411a82d2a47898481325/nexp_126a11f5f80944efaa480a44270bed34/final-video.mp4)
- [Gói bàn giao ZIP](C:/vfct/drama-uat-real-n1/deliveries/6b13c09d9f19411a82d2a47898481325/nexp_126a11f5f80944efaa480a44270bed34/delivery-package.zip)

`OWNER_EXPORT_UAT_COMPLETE=NO`; `OWNER_VOICE_UAT_REQUIRED=YES`. Giữ các cờ này cho đến khi Owner phản hồi kiểm cụ thể. Không có video nào được đăng lên nền tảng ngoài.
