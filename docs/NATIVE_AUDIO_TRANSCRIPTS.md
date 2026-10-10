# Bản chép lời từ audio tải lên trong Native Studio

Phần triển khai này nối upload audio ở Wave 3A với ASR và chỉnh transcript ở Wave 3B của `CODEX_MASTER_SPEC_VIDEO_FACTORY_V2.md`. Native Studio tiếp tục dùng Store, worker, hợp đồng Transcript/TranscriptSegment/TranscriptWord và adapter ASR hiện có.

## Nhận diện

Audio có vai trò `audio` được nút **Phân tích** đưa vào luồng nhận diện hiện có. Nhạc và file phụ đề không được gửi đến ASR hoặc bị coi là hình/video. Module chỉnh transcript chỉ đọc dữ liệu đã lưu và lưu bản sửa; khởi tạo, đọc hoặc sửa chữ không tự gọi ASR.

FFprobe đo stream, codec, duration, số kênh và sample rate từ byte nguồn đã xác minh. Audio không có chiều rộng, chiều cao, cảnh hoặc mô tả hình ảnh giả. FFmpeg trích WAV mono 16 kHz; worker dùng adapter AssemblyAI, job/receipt đã lưu, giới hạn, chi phí và quy tắc không tự gửi lại yêu cầu trả phí khi kết quả chưa rõ. Thiếu cấu hình thì nhận diện thất bại rõ ràng, không tạo transcript mẫu.

Bản nhận diện audio lưu transcript chuẩn hóa bên cạnh kết quả provider nguyên bản. ID được gắn với asset, SHA256 nguồn và SHA256 phản hồi ASR; timestamp lấy từ hợp đồng provider, không suy đoán từ văn bản. Trước khi dùng bản chuẩn hóa, hệ thống dựng lại từ kết quả gốc để đối chiếu. Profile Native hiện dùng tiếng Việt đã có; hợp đồng hỗ trợ tiếng Anh nhưng cấu hình chọn ngôn ngữ/tự phát hiện và nghiệm thu provider thật vẫn còn cần hoàn thiện.

## Chỉnh sửa và khôi phục

Trong Assets, mục **Lời nói từ audio nguồn** cho phép đọc, chọn audio, sửa từng đoạn và lưu một phiên bản mới. Có hành động rõ ràng để tạo bản mới từ nhận diện gốc. Bản ASR, các bản sửa trước và byte nguồn được giữ nguyên. Mỗi bản sửa có SHA256, bản cha và người thực hiện; lịch sử hiện giới hạn 50 bản sửa cho mỗi tài liệu dự án, không tự xóa bản cũ.

Sửa chữ giữ ranh giới thời gian của đoạn. Với đoạn đã sửa, timestamp từng từ và confidence cũ bị bỏ vì không còn chứng minh được chữ mới. Khôi phục từ bản gốc có thể lấy lại timestamp từng từ của bản gốc. Văn bản được chuẩn hóa NFC để giữ chữ Việt. Không tự tạo căn từ hoặc độ tin cậy.

Yêu cầu lưu đối chiếu revision dự án, phiên bản transcript, phiên bản timeline nếu có, SHA256 asset và SHA256 analysis. Byte nguồn thực cũng được xác minh trước khi sửa. Thay đổi tăng revision và hủy approval cũ; lưu nội dung không thay đổi là no-op. Script/context của audio sử dụng bản đã chọn mới nhất và phân biệt bản nhận diện với bản sửa của người dùng.

Chỉnh transcript audio chưa tự áp dụng vào timeline. Canonical timeline hiện có được giữ nguyên; áp dụng voice và phụ đề vào track sẽ là bước tiếp theo với hành động duyệt rõ ràng. Không coi bản sửa chữ là bằng chứng rằng timeline đã sử dụng chữ đó.

## API và quyền

`GET /api/projects/{project_id}/audio-transcripts` trả các bản gốc, hiện hành và lịch sử trong đúng workspace. `POST /api/projects/{project_id}/audio-transcripts/{asset_id}` nhận hợp đồng chỉnh sửa nghiêm ngặt, tối đa 128.000 byte. Không nhận query hoặc trường quyền/provider tùy ý. Phản hồi dùng header `Cache-Control: no-store` của server.

Các route dùng đăng nhập, CSRF và RBAC Native hiện có. Viewer/reviewer có thể đọc; chỉ quyền edit mới lưu được. Capability `native_audio_transcript_edit` tải module tương ứng. Controller chặn dự án bẩn, đang chạy, đã archive, sai workspace/source/revision, dữ liệu riêng tư và phản hồi đến sau khi đổi dự án. DOM sử dụng text/textarea, không diễn giải transcript thành HTML.

## Bằng chứng và phần còn lại

`north-star/audio-transcript-evidence.json` ghi log và SHA256 nguồn. Bộ kiểm thử dùng WAV thực được tạo tại máy, upload/decoder/SQLite/HTTP/backup/restore thực, human identity và phản hồi ASR giả lập được ghi rõ. Controller Studio chạy qua HTTP được ký với DOM giả; đây chưa phải kiểm tra trình duyệt hiển thị hay Owner UAT. Các bản gốc và bản sửa còn nguyên sau restart và restore vào thư mục mới.

Còn cần đặt audio vào canonical voice/music tracks, nhập cue SRT/VTT vào caption track, UI tương ứng, căn từ sau sửa, ngôn ngữ/provider thật, kiểm tra trình duyệt ở các kích thước yêu cầu, người dùng không biết lập trình và toàn bộ bundle A. Mode A, Meta analytics, các yêu cầu North Star còn mở và bundle B/C tiếp tục riêng.

Không có ASR/provider thật, cuộc gọi trả phí mới, publishing thật, merge main, production deployment hoặc xóa dữ liệu lịch sử thủ công trong đợt này. Owner UAT vẫn chờ theo yêu cầu của Owner. Mode B và North Star chưa được nghiệm thu hoàn tất.
