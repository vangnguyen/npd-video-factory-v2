# Ảnh QC từ video sau render

QC mới lưu tối đa 8 ảnh PNG lấy từ đúng video vừa render, cùng thời điểm khung hình được giải mã, mã SHA256 của video, bản thiết kế render, tài liệu dự án, từng PNG và điểm ảnh RGB. Các số đo độ sáng và độ sắc nét sử dụng thuật toán điểm ảnh cục bộ đã có. Độ tin cậy, mô tả cảnh, đối tượng và OCR vẫn để trống khi chưa phân tích bằng Vision.

Luồng Source, storyboard có chính sách chất lượng mới và bản xem trước có lời đọc đều dùng cùng bộ xác minh. PNG được thu nhỏ để vừa trong 960×960 và đo trên lưới xám 64×64; đây là ảnh mẫu, không chứng nhận mọi khung hình của video. Bản xem trước dùng đúng các byte video gốc dưới tên `preview.mp4`, giữ nguyên bằng chứng và không tạo thêm một bản video trùng lặp.

Thời điểm lấy từ PTS nguyên gốc và timebase của bộ giải mã, trước khi thu nhỏ ảnh. Quy trình dùng `copyts`, không dùng bộ lọc đổi FPS hay đặt lại thời điểm. Nhật ký giải mã được giữ cùng checkpoint và đối chiếu khi đọc lại. [Tài liệu FFmpeg](https://ffmpeg.org/ffmpeg.html#Advanced-options) mô tả cách giữ timestamp; [bộ lọc showinfo](https://ffmpeg.org/ffmpeg-filters.html#showinfo) cung cấp PTS của khung hình. Mốc bắt đầu khác 0 được kiểm thử bằng video cục bộ bắt đầu ở giây 4. Quy tắc này chỉ xác minh PTS của **video sau render**; PTS và theo dõi chủ thể liên tục trên video nguồn vẫn là phần việc riêng.

Nếu video, thiết kế, ảnh mẫu hoặc thời điểm gốc thay đổi, QC không được xác nhận thành công. Ảnh và nhật ký nằm trong checkpoint và gói phục hồi; ảnh bị mất hoặc sửa sẽ chặn mở lại đầu ra đã kiểm chứng. Các kiểm tra khung hình đen, video đứng hình, âm thanh, clipping, phụ đề và lỗi giải mã hiện có tiếp tục được áp dụng. Báo cáo và checkpoint cũ được giữ nguyên, không được tự nâng cấp thành bằng chứng mới.

Schema `native-render-frame-qc-v1` ghi `semantic_provider_status=NOT_REQUESTED`, `semantic_inference_performed=false`, `confidence=null`, không cấp quyền xuất bản hay xác nhận Owner UAT. Quy trình không gọi dịch vụ trả phí. Kết quả Vision trên video nguồn không được dùng để khẳng định chất lượng video sau render.

## Kiểm chứng

- 48 kiểm thử liên quan trước thay đổi cuối của bộ đọc; 35 kiểm thử trực tiếp trên phiên bản cuối; 8 kiểm thử API. Bao gồm thời điểm bắt đầu khác 0, sửa ảnh/video/thiết kế, giả thời điểm rồi tính lại hash, liên kết tệp, quyền giả, lỗi đo, checkpoint và bản xem trước.
- Source dùng video và âm thanh tổng hợp cục bộ, ASR và người duyệt kiểm thử; renderer thật thực hiện phụ đề, B-roll, crop thủ công, nhạc, crossfade, xử lý âm thanh và QC. Không tuyên bố nhận diện lời nói thật.
- Storyboard đi qua 192 yêu cầu HTTP có danh tính kiểm thử; bản xem trước và render thật đạt QC, video đứng hình thật vẫn bị từ chối.
- Hai gói phục hồi được kiểm tra trong tiến trình mới, không cần khóa nhà cung cấp. Tất cả ảnh mẫu, PTS, video, dữ liệu dự án và checkpoint giữ nguyên. Bộ đọc cuối xác minh lại cả nhật ký giải mã và điểm ảnh PNG hiện có, không render lại hoặc trích xuất video mới.

Chi tiết hash, đường dẫn phục hồi và giới hạn kiểm chứng nằm trong `docs/north-star/render-frame-qc-evidence.json`. Phân tích Vision thật trên ảnh sau render, UAT, toàn bộ Mode A/B và nghiệm thu North Star vẫn chưa hoàn tất.

Đầu ra sau sao chép được kiểm tra lại trước khi tạo checkpoint hoặc báo bản xem trước sẵn sàng. Ba kiểm thử gây hỏng PNG ngay khi sao chép xác nhận cả ba luồng đều chặn đầu ra.
