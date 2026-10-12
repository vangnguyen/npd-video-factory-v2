# SFX tải lên trong Native Studio

Master Spec mục 39–40 yêu cầu track SFX trên cùng timeline canonical. Card audio/phụ đề dùng chung cho Mode A có narration và Mode B có video nguồn nay có vai trò **Hiệu ứng âm thanh (SFX)**. Tải file bằng luồng audio hiện hữu, chọn vai trò SFX, cửa sổ nguồn, vị trí timeline, gain và fade rồi lưu. Có thể thêm track riêng hoặc chọn một track SFX có thể sửa. Chỉ nhạc nền được lặp; tạo caption từ transcript chỉ áp dụng cho lời đọc.

SFX dùng cùng SHA, waveform đo từ nguồn, provenance nhập bất biến, idempotency, CAS và lịch sử hiện hữu. Vai trò track/clip phải khớp quyết định nhập; không được đổi SFX thành lời đọc hoặc nhạc mà giữ nguyên biên nhận cũ. Thao tác trim/split/move/duplicate/disable/lock/mute và undo/redo dùng editor canonical hiện hữu. Lời đọc đã chuẩn bị và nguồn vật lý được giữ. Chọn SFX không cấp quyền xuất bản: quyền sử dụng chưa rõ vẫn bị publishing gate chặn.

SFX được trộn như một lớp riêng; không trở thành tín hiệu điều khiển ducking của lời đọc hay nhạc. Gain/fade được giữ và đầu ra dùng limiter hiện hữu. Sau trim/delay, clock SFX được tính từ toàn bộ luồng mẫu đã chèn khoảng chờ, giữ đúng vị trí khi trộn các nguồn có sample rate khác nhau. Đường xử lý của các track khác được giữ.

## Bằng chứng

[media-sfx-evidence.json](north-star/media-sfx-evidence.json) ghi SHA và đường dẫn bundle/log/restore. Studio: **720 PASS**, gồm hai ca SFX mới. Native: **49 PASS** trong năm module liên quan, gồm bảy ca mới. Static HTTP: ba ca PASS riêng, 63 module; không nằm trong 49 ca Native. API trên Linux: 23 PASS, bảy ca thiếu FFmpeg/FFprobe nên chưa chạy. Các luồng media thật được kiểm tra riêng trên Windows.

Hai bundle `native-media-sfx-mode-a-n2` và `native-media-sfx-mode-b-n2` chạy card thật trong DOM giả qua HTTP có xác thực, upload và SQLite, preview/final/FullQC, backup và khôi phục trong tiến trình riêng. Mỗi bundle có tám request controller: media sáu và SFX hai. Mode A dùng PCM narration tổng hợp đã đo; Mode B dùng video chuyển động/âm thanh tổng hợp và ASR lưu sẵn. Không có ASR/TTS mới hoặc provider/paid call. Không khởi tạo toàn bộ parent editor trong browser và không tự nghiệm thu Owner UAT.

Tone SFX nguồn 3000 Hz được đo độc lập trong PCM, preview và final: cửa sổ 0,9–1,4 s có năng lượng rõ, các khoảng trước/sau là đối chứng. Đây là phép đo fixture về vị trí lớp SFX; không chứng nhận cảm nhận toàn bản mix, chất lượng lời nói hoặc A/B/C đầy đủ. Preview/final giữ cùng PCM, FullQC qua và các bản khôi phục giữ nguồn, history, render cùng undo/redo tạo phiên bản mới.

Bản thử Mode A n1 từng qua QC định dạng nhưng không có SFX đúng mốc trong PCM. Ca hồi quy đo âm thanh tái tạo lỗi trước sửa và qua sau sửa. Bản n1 được giữ để đối chiếu, không được dùng làm bằng chứng SFX hoàn tất; bundle n2 là bằng chứng sau sửa. Artifact lịch sử hoặc đã chấp nhận không bị thay thế.

Visual effects, các giới hạn renderer, chỉnh fade/transition sau nhập, toàn bộ UI/non-developer/browser/Owner, provider thật và các bundle A/B/C còn mở. Fixture mới được teardown sau xuất/xác minh backup; không thử lại lệnh xóa từng bị automatic approval review từ chối. Ma trận vẫn giữ 5 REAL / 58 PARTIAL / 1 NOT_VERIFIED, tức 59 nhóm rộng chưa đóng.
