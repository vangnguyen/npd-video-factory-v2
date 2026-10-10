# Chỉnh sửa và hoàn tác timeline audio–phụ đề của Mode A

Ngày kiểm chứng: 2026-10-11. Nguồn gốc: `cfbdf705c225c9f8bcc7106e9a4784e07179566d`, nhánh `codex/vf-north-star-completion-01`. SHA của commit bổ sung được ghi trong bản bảo toàn nguồn và trạng thái chương trình bên ngoài repository.

Thành phần này mở rộng timeline storyboard đã có và dùng lại engine thao tác timeline chung, SQLite/history, lời đọc đã đo, nguồn gốc tư liệu, renderer và QC hiện hữu. Shot vẫn là giao diện chỉnh hình ảnh mặc định. Không tạo một timeline hay cơ sở dữ liệu biên tập thứ hai.

## Hành vi đã triển khai

- GET `/api/projects/{id}/narrated-timeline` đọc snapshot hiện tại, bản chiếu track chưa lưu và tối đa 100 phiên bản từ 200 revision gần nhất. Đọc không tạo job, gọi provider hay tự lưu bản chiếu; lịch sử bị giới hạn được báo rõ.
- POST các đường dẫn `/edit`, `/configure`, `/restore` yêu cầu quyền editor, CSRF, revision, version và SHA của timeline hiện tại. DTO đóng, số hữu hạn, boolean và số nguyên nghiêm ngặt; tối đa 100 thao tác trong một transaction.
- Audio/phụ đề hỗ trợ di chuyển, cắt, chia, đổi thứ tự, nhân bản, xóa, tắt; audio hỗ trợ âm lượng/tốc độ. Track hỗ trợ khóa, tắt và mute audio. Canvas giữ thời lượng lời đọc đã đo, mọi clip kể cả clip tắt phải nằm trong canvas.
- Track lời đọc sinh từ PCM đã chuẩn bị giữ nguyên thời gian: chỉ cho phép gain, disable và trạng thái track. Video được chỉnh bằng shot editor. Không chia hay ép giọng đọc vào một khoảng giả định.
- Điểm cắt của voice tải lên được đối chiếu với word timestamps đã lưu nếu có. Thiếu timestamps không tạo ra bằng chứng căn chỉnh. Thay đổi cấu trúc phụ đề xóa căn chỉnh cũ; lựa chọn xóa hết caption được lưu rõ và không bị dựng lại mặc định.
- Thiết lập canonical gồm normalization, ducking, mẫu phụ đề và từ nổi bật. Track khóa chặn thay đổi thiết lập liên quan; mẫu cần căn chỉnh từng từ bị chặn khi thiếu bằng chứng.
- Khôi phục đúng snapshot và các projection biên tập, tạo revision/version mới, hủy approval và làm preview cũ mất hiệu lực. Chỉ khôi phục trong cùng project và cùng bản chuẩn bị narration; kiểm tra lại bytes/checkpoint/nguồn gốc. Không quay lui uploads, quyền tư liệu, chi phí, journal provider, jobs hay quyền xuất bản.
- Studio có lịch sử undo/redo, waveform đã đo của audio tải lên, zoom, playhead bám mốc và điều khiển track/clip/mix. Form clip và form mix không ghi đè bản nháp của nhau. Phản hồi muộn bị chặn theo workspace/project/revision/role. Mất phản hồi không tự gửi lại mutation; đọc lại chủ động đồng bộ revision dự án.

## Bằng chứng và giới hạn

Chỉ mục: [narrated-timeline-editor-evidence.json](north-star/narrated-timeline-editor-evidence.json). Bundle mới: `C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-narrated-timeline-n2`. Không thay bundle đã nghiệm thu trước đó.

Controller thật chạy qua 9 request HTTP có cookie/CSRF trong DOM giả; cộng 6 request nhập audio/phụ đề từ controller hiện hữu. Preview và final thật qua FFmpeg/QC có cùng SHA `87b643f4cf4571081d0c79907a6f2ffe9f17e0180bad170588522dc495b17dcc`. PCM mix: `50be60869634d70ea26f51a1989e1ef4113b3e881ccf9eb2ca82eeabc8a034bd`. Định dạng 1080×1920, 30fps, 3,3s. PNG đã được kiểm tra trực quan: chữ Việt hiển thị đủ và nằm trong khung phụ đề.

Backup/restore trong tiến trình riêng không cần secret giữ đúng history, checkpoint và tư liệu; undo/redo sau phục hồi giữ đúng SHA snapshot, tạo version mới, hủy approval và không thay jobs. Fixture tạm do chương trình tạo được dọn sau khi xuất bằng chứng/backup; không xóa dữ liệu lịch sử.

PCM, lời nói, người duyệt và word timestamps của phép thử là fixture tổng hợp; hình là fixture minh họa. Không chứng minh chất lượng giọng nói, nhận diện lời thật, provider thật, rights/legal thật, browser, thao tác của người không lập trình hay Owner UAT. Không phát sinh paid/provider call, xuất bản thật, merge main hoặc deploy production.

Mode A/B đầy đủ và các bundle A/B/C vẫn chưa được nghiệm thu. Mapping phụ đề theo video nguồn trong Mode A đã có phần bổ sung được kiểm chứng tại máy: [NATIVE_SOURCE_VIDEO_CAPTIONS.md](NATIVE_SOURCE_VIDEO_CAPTIONS.md). Các thao tác video storyboard tổng quát, provider/media/analytics còn thiếu và các cổng nghiệm thu ban đầu vẫn thuộc kế hoạch North Star. Ma trận vẫn là 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED; không suy ra tỷ lệ hoàn thành từ số nhóm này.

Kiểm tra cuối: Studio 677 PASS; Native related 244 PASS (29 module); thêm 20 PASS cho editor/HTTP sau sửa kiểm tra lời đọc. Các tập Native có giao nhau, không cộng số lượng. Bộ hồi quy bắt đầu trước sửa cuối trong module editor; toàn bộ editor/HTTP và bundle render/restore đã được chạy lại với mã nguồn cuối. Các bộ API/PostgreSQL/Docker/production tổng thể chưa được chứng nhận từ thành phần này.

Khi sửa lời thoại, đọc history vẫn có thể thực hiện mà không lưu track lời đọc cũ; chỉnh audio mới yêu cầu chuẩn bị narration phù hợp. Hoàn tác chỉ được phép nếu bản đích khớp cùng preparation và identity lời đọc, được kiểm tra lại theo bytes/checkpoint.
