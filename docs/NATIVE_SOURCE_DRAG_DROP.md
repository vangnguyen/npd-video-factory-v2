# Kéo/thả clip nguồn trong Native Studio

Master Spec mục 39–40 và Wave 3I vẫn yêu cầu toàn bộ timeline editor. Giao diện shot giữ mặc định; trong timeline nâng cao, kéo clip đang có trong cùng track để đổi vị trí. Zoom và bám mốc 0,25 s được dùng khi tính vị trí, kể cả khi timeline đã cuộn ngang. Các nút nhập vị trí hiện hữu vẫn dùng được.

Shot nguồn dùng thao tác linked edit hiện hữu: sắp lại các shot liền nhau, đồng bộ cửa sổ âm thanh nguồn và reflow phụ đề đã chọn theo nguồn. Không tạo khoảng trống chỉ vì vị trí thả. Các clip âm thanh, phụ đề và B-roll độc lập dùng vị trí tuyệt đối trong canvas hiện tại. Cần kiểm tra lại B-roll, tạo preview và duyệt phiên bản mới sau khi đổi thứ tự. Track âm thanh nguồn đã bị chỉnh lệch riêng hoặc track liên quan bị khóa có thể làm linked edit bị từ chối; dữ liệu không bị ghi đè ngầm.

Controller chỉ di chuyển clip đã bắt đầu kéo trong chính timeline này; không đọc payload từ bên ngoài. Viewer, track khóa, project archive, draft chưa lưu, job đang chạy và context project/workspace/revision/version/SHA không khớp đều chặn ghi. Thay đổi zoom hoặc bám mốc trong lúc kéo hủy thao tác. Vị trí không hữu hạn hoặc vượt canvas bị từ chối. Kết quả lưu không xác định không được lặp lại từ cùng binding.

## Bằng chứng thành phần

[source-drag-drop-evidence.json](north-star/source-drag-drop-evidence.json) ghi SHA và đường dẫn log/bundle. Studio: **718 PASS**, gồm 10 ca kéo/thả mới. Native liên quan: **18 PASS** trong bốn module; ba ca static chạy riêng đã nằm trong lượt này, không cộng hai lần. HTTP kiểm tra toàn bộ cây import của bốn entrypoint và tải được **63 module**.

Bundle `native-source-drag-drop-n1` chạy upload, SQLite, request HTTP có xác thực, preview/final FFmpeg/Remotion, FullQC và backup/restore thực trên máy. Có 24 request controller: media 6, widget hình 7 và kéo/thả/caption 11. Sau split, kéo shot đầu đổi thứ tự cửa sổ nguồn từ 0–1,5 / 1,5–3 thành 1,5–3 / 0–1,5; âm thanh nguồn đi cùng shot. SRT theo nguồn được reflow; lời đọc nhập riêng được kéo đến 0,25 s. Undo/redo và mở lại giữ đúng snapshot, tạo phiên bản mới và không chuyển approval cũ.

Timeline 3 s; output đo 3,051 s, 1080×1920, 30 fps, A/V lệch 0,051 s trong giới hạn QC. Không clipping, black/freeze frame hoặc silence đo được. Preview/final dùng cùng PCM. Hai ROI giải mã bằng FFmpeg và biến đổi affine PIL độc lập xác nhận cửa sổ nguồn đã đổi cùng crop/transform/opacity; đây là đối chiếu fixture, không phải QC ngữ nghĩa hoặc khớp toàn khung hình tuyệt đối. Frame phụ đề đã được xem trực quan.

Controller và caption importer được chạy trong DOM giả; **chưa khởi tạo toàn bộ Source editor trong browser**. Video chuyển động/âm thanh tổng hợp và transcript lưu sẵn là fixture; không có ASR/TTS mới, provider/paid call, đăng bài hoặc deployment. Không tự nghiệm thu Owner UAT. Usability ở 1366/1920/2560, visual effects, giới hạn renderer và toàn bộ Mode A/B/A/B/C còn mở. Increment tiếp theo bổ sung [SFX tải lên](NATIVE_MEDIA_SFX.md) với bằng chứng riêng.

Fixture mới được teardown sau khi xuất và xác minh backup. Artifact lịch sử hoặc đã chấp nhận không bị xóa/thay thế; không thử lại lệnh xóa từng bị automatic approval review từ chối. Ma trận vẫn giữ 5 REAL / 58 PARTIAL / 1 NOT_VERIFIED, tức 59 nhóm rộng chưa đóng.
