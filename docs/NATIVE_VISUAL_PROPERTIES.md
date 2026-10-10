# Chỉnh crop và bố trí hình trong Native Studio

Master Spec mục 39–40 vẫn là yêu cầu đầy đủ. Shot giữ vai trò giao diện mặc định; bảng này bổ sung chỉnh clip hình trên cùng timeline canonical cho cả Mode A có narration và Mode B dùng video nguồn.

Chọn clip video hoặc ảnh rồi mở **Crop & bố trí hình**. Có thể sửa crop trái/trên/rộng/cao, dịch ngang/dọc, scale, xoay và độ hiện. Phần trăm dịch tính theo kích thước phần tử hình sau crop, đúng đơn vị renderer hiện hữu. Sơ đồ chỉ minh họa bố trí, không phải khung hình đã giải mã hay kết quả Vision. Sau khi lưu cần tạo preview, xem/nghe và duyệt phiên bản mới.

Chỉ thuộc tính thực sự đổi được gửi. Đổi scale/xoay/độ hiện giữ đường crop tự động; lưu một crop khác thay đường crop riêng của clip đã chọn. Nguồn vật lý, cửa sổ nguồn, tốc độ, canvas và các track audio/phụ đề được giữ. Undo/redo khôi phục đúng snapshot nhưng tạo phiên bản mới và không chuyển approval cũ.

Draft của bảng này không ghi đè draft trim, mix hoặc đường reframe. Viewer, track khóa, project archive, job đang chạy, lời đọc đã đổi và context project/workspace/version/SHA không khớp đều chặn ghi. Input trống, không hữu hạn hoặc ngoài giới hạn bị từ chối. Khi kết quả lưu không xác định, không lặp mutation từ cùng binding; mở lại dữ liệu trước khi tiếp tục.

Server Native phục vụ rõ ràng module bảng mới, module timeline narration và CSS tương ứng. Kiểm tra HTTP duyệt đệ quy các import tĩnh/động của bốn entrypoint Studio; 62 module tải được với MIME JavaScript và không mở rộng quyền đọc file ngoài allowlist.

## Bằng chứng

[visual-properties-evidence.json](north-star/visual-properties-evidence.json) ghi SHA và đường dẫn bundle, log và receipt khôi phục. Studio: 708 PASS, gồm 14 ca mới. Native liên quan: 25 PASS trong bốn module, gồm ba ca HTTP mới; lượt này chứa các ca static đã chạy riêng, không cộng hai lần.

Hai bundle mới dùng video chuyển động/âm thanh tổng hợp, HTTP đăng nhập bằng identity fixture, SQLite, FFmpeg, Remotion, preview/final và FullQC thực trên máy. Mode A chạy controller timeline narration thật trong DOM giả; Mode B chạy widget chung thật cùng helper request Source, chưa khởi tạo toàn bộ DOM Source editor. Có 33 request controller có xác thực: Mode A 6 + 14, Mode B 6 + 7.

Mode A: 3,3 s, 1080×1920, 30 fps; Mode B: timeline 3 s, output đo 3,051 s, A/V lệch 0,051 s trong giới hạn QC. Không clipping, black/freeze frame; preview/final dùng cùng PCM. Mỗi bundle được khôi phục trong tiến trình riêng không dùng provider key, giữ history, nguồn vật lý, render và undo/redo, đồng thời vô hiệu approval mới.

Hai ROI cho mỗi bundle được đối chiếu bằng FFmpeg giải mã và phép biến đổi affine PIL độc lập. Bố trí canonical khớp tốt hơn các đối chứng bỏ crop, bỏ transform hoặc bỏ opacity. Đây là phép đo fixture theo ngưỡng so sánh; không phải khớp toàn khung hình tuyệt đối, QC ngữ nghĩa hay nghiệm thu chất lượng nội dung. Frame cuối đã được kiểm tra trực quan, chữ Việt và vùng brand giữ được.

Không có inference ASR/TTS mới, provider/paid call, publishing hoặc deployment. Owner UAT, usability browser ở 1366/1920/2560, toàn bộ giao diện Source, Mode A/B và các bundle A/B/C đầy đủ còn mở. Authoring effects/SFX và giới hạn renderer tiếp tục cần đóng; shot transition cơ bản hiện hữu được giữ. Increment tiếp theo bổ sung [kéo/thả Source timeline](NATIVE_SOURCE_DRAG_DROP.md) với bằng chứng riêng; các số kiểm thử và bundle trên vẫn mô tả đúng checkpoint visual-properties trước đó.

Dữ liệu fixture mới được xuất và xác minh backup trước teardown thông thường. Không xóa/thay artifact lịch sử hoặc đã chấp nhận; không thử lại các lệnh xóa đã bị automatic approval review từ chối. Ma trận giữ 5 REAL / 58 PARTIAL / 1 NOT_VERIFIED, tức 59 nhóm rộng chưa đóng.
