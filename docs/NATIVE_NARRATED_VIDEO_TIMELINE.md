# Chỉnh clip video trên timeline Mode A

Master Spec mục 39–40 vẫn là yêu cầu đầy đủ. Đây là một bước đóng gap của Native Studio, không phải nghiệm thu toàn bộ Mode A/B hay Artifact B.

Shot vẫn là giao diện mặc định. Timeline nâng cao đọc cùng `TimelineSnapshot`, version, SHA và history để trim, split, move, delete, duplicate, disable, reorder và đổi tốc độ clip tư liệu. Ảnh dùng thời gian hiển thị; không tạo thời gian nguồn giả. Track có thể khóa hoặc tắt. Zoom, playhead, waveform đã đo và snapping dùng controller hiện hữu. Có thể chọn clip trên graph hoặc kéo clip trong cùng track; vị trí vượt thời lượng lời đọc bị chặn.

Thông tin lời đọc, tiêu đề và shot được giữ trong metadata canonical có fingerprint. Cửa sổ clip hình là dữ liệu canonical riêng trong cùng snapshot; renderer đọc chính các cửa sổ đó. Chỉnh title trong shot không dựng lại các clip đã split hoặc đổi tốc độ. Thay asset, mốc nguồn hoặc thời lượng của một shot chỉ thay nhóm clip của shot ấy. Shot hiển thị thêm các cửa sổ clip đã chỉnh để người dùng phân biệt chúng với khoảng lời đọc.

Chỉnh clip hình giữ canvas lời đọc đã đo và các track audio. Không ép, kéo dài hoặc tái tổng hợp TTS để lấp thời lượng. Các thuộc tính dành cho hình không được dùng để vượt bảo vệ giọng đọc. Có thể lưu quyết định tạo khoảng trống hoặc tắt clip để tiếp tục biên tập; preview/render chặn khoảng thiếu hình với `NARRATED_VIDEO_VISUAL_GAPS_REVIEW_REQUIRED`.

Phụ đề đã nhập với video ID/SHA và mốc nguồn bám theo các cửa sổ clip thực tế. Bố cục caption do người dùng sửa giữ nguyên. Nếu reflow làm đổi track đã khóa, toàn bộ thao tác bị từ chối nguyên tử. Import history, nguồn vật lý, rights và approval không bị quay ngược khi undo/redo. Mọi thay đổi lưu thành phiên bản mới, cần preview và duyệt lại.

## Render và lưu bằng chứng

Khi người dùng chủ động chỉnh track hình bằng timeline nâng cao, metadata `native-narrated-video-timeline-v1` được thêm vào snapshot. Các project chưa dùng chức năng này giữ đường render cũ. Đường mới dùng renderer Remotion cục bộ hiện hữu với media riêng cho job. Viewport trong contract v2.3 đặt clip vào vùng hình của brand; overlay title giữ các khoảng lời đọc canonical. Subtitle ASS, font tiếng Việt, audio mix và FullQC dùng đường hiện hữu.

Định dạng ảnh/video được nhận dạng từ bytes đã đăng ký và kiểm tra SHA; không phụ thuộc trường MIME bị thiếu trong các record cũ. Snapshot, cửa sổ nguồn, crop, transform, speed, source SHA, header PNG, audio mix, video và renderer receipt được kiểm tra lại trước khi xác nhận bundle. Overlay được xuất vào checkpoint/backup cùng artifact. Source có thể khôi phục sang root mới và vẫn kiểm tra được physical origins cùng history.

## Bằng chứng và giới hạn

Chỉ mục: [narrated-video-timeline-evidence.json](north-star/narrated-video-timeline-evidence.json). Các bundle chỉ dùng video chuyển động tự tạo và PCM âm thanh mẫu; transcript/TTS/provider inference mới bằng 0. Controller Studio thật chạy trong DOM giả qua HTTP có đăng nhập, gồm kéo graph, split, speed, duplicate, reorder, delete, undo/redo và mở lại. Đây không phải browser UAT.

Preview/final chạy thực tế ở 1080×1920, 30 fps, H.264/AAC với FullQC. Mốc nguồn và speed được đối chiếu bằng FFmpeg giải mã độc lập. Backup được khôi phục trong tiến trình mới; thay cửa sổ nguồn dù tính lại digest, hoặc đổi overlay, đều bị chặn. Duplication và sáu profile variant được kiểm tra bảo toàn quyết định hình, không chuyển approval và không tạo inference/job mới.

Còn phải kiểm tra usability trong browser ở các kích thước yêu cầu, full non-developer Mode A/B và các bundle A/B/C đầy đủ. Bảng [crop/bố trí hình dùng chung](NATIVE_VISUAL_PROPERTIES.md) hiện cung cấp input crop, vị trí, scale, xoay và độ hiện, minh họa và lưu vào cùng timeline. Các giới hạn track/clip/shot của renderer hiện hữu vẫn áp dụng. Chưa có provider acceptance, nội dung tiếng nói tự nhiên được Owner chấp nhận, publishing thật hay production deployment. Owner đã chọn xem/nghe sau; không tự chấp nhận UAT.

Dữ liệu fixture mới được xuất và xác minh backup trước teardown thông thường. Không xóa hay thay artifact lịch sử/đã chấp nhận; không thử lại các lệnh xóa đã bị automatic approval review từ chối.
