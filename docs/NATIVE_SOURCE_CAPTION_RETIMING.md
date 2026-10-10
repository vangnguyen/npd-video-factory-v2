# Giữ phụ đề khi chỉnh video nguồn Mode B

Kiểm chứng ngày 2026-10-11, nguồn trước thay đổi `d8426915cea2fc25b70057182fb509f4bb0ac79b`. SHA sau commit được ghi trong biên bản bảo toàn ngoài repository. Đây là phần bổ sung Wave 3/6; full Mode A/B và Owner UAT chưa hoàn tất.

Lỗi đã tái hiện: đổi tốc độ video qua linked edit thay hai caption SRT đã nhập bằng chữ từ transcript thử. Linked edit nay chỉ dựng lại track transcript được sinh tự động, giữ caption nhập và bố cục người dùng sửa. Hai chế độ dùng cùng timeline canonical, history và các gate review hiện hữu.

## Người dùng chọn mốc phụ đề

Trong Assets → Audio & phụ đề, chọn file SRT/VTT và **Video nguồn**, rồi chọn video đang được dùng. Yêu cầu gắn ID/SHA của cả phụ đề và video. Caption giao với từng cửa sổ video thực sự trong timeline, kể cả trim, split, duplicate, reorder và speed. Không suy ra timestamp từng từ.

Caption bám nguồn được tính lại khi lưu video. Các caption cũ không giữ canvas mở sau khi video ngắn lại. Audio nguồn linked vẫn đi theo video; voice/music hoặc track khác giữ quyết định canonical của chúng. Import record không bị viết lại chỉ vì reflow.

Sửa chữ, thời gian hoặc cấu trúc caption chuyển cả track sang bố cục thủ công. Linked edit và sửa transcript không ghi đè bố cục đó. Xóa hết caption vẫn giữ quyết định xóa, kể cả khi track rỗng. Muốn trở về bám nguồn cần chủ động nhập lại vào track đó. Track khóa chặn reflow làm thay đổi caption; track thủ công khóa vẫn giữ nguyên khi video đổi.

**Timeline hiện tại**, hoặc request Source cũ không có cặp video ID/SHA, giữ bố cục đã nhập. Payload/hash lịch sử vẫn hợp lệ. Client hiện tại có catalog video sẽ yêu cầu chọn video rõ ràng khi dùng mốc nguồn. Không tự nâng request cũ thành một binding video mới.

Duplicate giữ lineage, tạo import ID thuộc project mới và không chuyển approval/replay authority. RBAC/CSRF/CAS, nguồn vật lý, source provenance và publishing-rights gate dùng các kiểm tra hiện hữu. Không có database hay timeline thứ hai.

## Bằng chứng và giới hạn

Chỉ mục: [source-caption-retiming-evidence.json](north-star/source-caption-retiming-evidence.json). Bundle mới nằm tại `C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-source-caption-retiming-n2`.

Controller phụ đề Studio thật chạy trong DOM giả, qua HTTP có đăng nhập. Thao tác video trong bằng chứng dùng Source timeline API; không được ghi nhận là thao tác video qua shot UI. Tổng cộng 17 request kiểm tra nhập, split, duplicate, reorder, sửa caption, speed, nhập lại và mở lại catalog.

Canvas canonical 3,75 giây có ba clip nguồn và năm caption. Preview/final thực sự render ở 1080×1920, 30 fps, H.264/AAC và qua FullQC. Media đo được dài 3,819 giây, A/V delta 0,052 giây trong giới hạn QC hiện hữu. PCM mix và hiệu ứng preview/final khớp. Ba mẫu khung hình được đối chiếu với frame nguồn do FFmpeg giải mã độc lập; mốc canonical gần kết quả render hơn mốc timeline chưa ánh xạ và đối chứng bỏ speed ở clip đầu. Khung hình phụ đề tiếng Việt được kiểm tra bằng mắt; đây không phải Owner UAT.

Backup được khôi phục trong tiến trình riêng; history, catalog và nguồn SRT/video vật lý khớp. Undo/redo tạo version mới, hủy approval và không dispatch job/provider. Dữ liệu dựng thử mới được dọn sau export. Một lần restore đầu đã qua kiểm tra nhưng cleanup lỗi đường dẫn dài; receipt đạt là lần `cold-recovery-n2`. Lệnh dọn thư mục còn sót của lần đầu bị hệ thống duyệt tự động từ chối `blocked by policy`; thư mục đó được giữ, không thử xóa lại.

Video chuyển động và âm tone là tư liệu dựng thử sở hữu cho test; transcript/word/human authorization là fixture. Provider/paid calls bằng 0. Không có ASR/TTS thật mới, nghiệm thu chất lượng lời nói, browser/non-developer UAT, đăng bài hay deployment. Bundle không thay thế Artifact A/B/C hoàn chỉnh và không đổi artifact đã nghiệm thu.

## Chạy lại kiểm chứng

Đặt `PYTHONPATH=apps/api;.` và dùng runtime Python Native hiện hữu:

```text
python -X utf8 scripts/north_star_source_media_tracks.py --source-caption-retiming --evidence-dir <fresh-external-directory>
python -X utf8 scripts/north_star_source_caption_restore.py --bundle <that-directory> --receipt <fresh-external-json>
```

Script yêu cầu thư mục/receipt mới. Restore dùng root tạm ngắn do script tạo để tránh lỗi MAX_PATH và chỉ ghi receipt đạt sau khi cleanup xong. Giữ bundle, backup và manifest hash để phục hồi.

Full advanced video editor Mode A, thao tác UI/drag-and-drop còn thiếu, Meta analytics và mọi yêu cầu chưa đóng trong Master Spec vẫn phải tiếp tục. Trạng thái ma trận giữ 5 REAL / 58 PARTIAL / 1 NOT_VERIFIED, tức 59 nhóm chưa đủ điều kiện đóng. Không có Owner action mới cần cho triển khai an toàn.
