# Phụ đề theo video nguồn trong storyboard Mode A

Ngày kiểm chứng: 2026-10-11. Nguồn gốc: `a8f1225d2d5fe76a60863d0222024f27e36b196b`, nhánh `codex/vf-north-star-completion-01`. SHA bổ sung được ghi trong bản bảo toàn và trạng thái chương trình ngoài repository.

Studio giữ giao diện shot mặc định. Trong Assets → Audio & phụ đề, người dùng chọn SRT/VTT đã tải lên, mốc **Video nguồn** và video đang dùng trong shot. File phụ đề và video đều được gắn ID/SHA vào yêu cầu và provenance. Mốc **Timeline hiện tại** và luồng video nguồn Mode B giữ payload/idempotency lịch sử.

## Hành vi

- Chỉ video thực sự được dùng bởi clip nguồn đang bật mới được chọn. Không suy ra video từ tên file, hình ảnh, audio hay project khác. Thiếu cặp ID/SHA, bytes thay đổi hoặc payload không hợp lệ bị chặn.
- Cue được giao với từng cửa sổ nguồn của timeline canonical; thời gian hiển thị được tính từ source start/end, tốc độ clip, vị trí clip và offset. Cùng video dùng ở nhiều shot hoặc lặp trong một shot tạo caption cho từng khoảng thực sự hiện diện. Không suy ra timestamps từng từ.
- Caption tự động đi theo cửa sổ video khi đổi source start hoặc shot. Việc này không tạo import mới, gọi provider hay đổi audio/history của import. Mọi thay đổi vẫn tạo revision/version mới và hủy approval.
- Sau khi sửa chữ/thời gian/cấu trúc caption thủ công, cả track giữ bố cục đó và Studio hiển thị **vị trí thủ công**. Nguồn gốc video/cue cũ vẫn được giữ; thời gian mới không được trình bày như kết quả căn chỉnh tự động. Muốn ánh xạ lại cần nhập phụ đề chủ động.
- Track khóa chặn thay đổi ánh xạ. Nếu video biến mất làm mất toàn bộ caption tự động, thay đổi shot bị chặn để người dùng xử lý track trước. Tắt track là một quyết định canonical có thể hoàn tác.
- Offset vượt canvas yêu cầu bật lựa chọn trim; khoảng đã cắt/bỏ được báo trong biên nhận. Không tự đổi thời lượng lời đọc đã đo.
- Render, chỉnh tiếp và phục hồi kiểm tra nguồn vật lý/provenance. Video còn được dùng làm nguồn caption phải qua gate quyền tư liệu kể cả khi đã bỏ khỏi các shot. Duplicate/variant tạo import ID riêng, giữ lineage và không mang approval hay quyền replay sang project mới.
- API hiện hữu `/api/projects/{id}/auto-edit/media-tracks/subtitles` dùng RBAC, CSRF và CAS. Catalog có video choices giới hạn 200 và caption labels. Studio chặn dữ liệu sai workspace/project/revision, biên nhận sai video/SHA, form khác đang sửa và phản hồi muộn.

## Bằng chứng

Chỉ mục: [source-caption-mapping-evidence.json](north-star/source-caption-mapping-evidence.json). Bundle mới: `C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-source-video-captions-n1`.

Controller Studio thật thực hiện 6 request qua HTTP có đăng nhập trong DOM giả, gồm chọn video nguồn và sửa caption thủ công. Controller timeline thật thực hiện thêm 9 request, gồm undo/redo. Bước nhập lại để kiểm tra reflow dùng service trực tiếp và được ghi riêng trong bằng chứng; không được tính thành request HTTP/UI.

FFmpeg tạo video thử chuyển động 2s; timeline 3,3s có trim, loop và tái sử dụng nguồn. Caption sau reflow nằm ở `[0,0.5]`, `[0.6,1.5]`, `[1.7,2.6]`, `[2.9,3.3]`. Preview/final thật đều có SHA `56a8ebbf64cc916ad54cc836a096f0b8806701d24e95e84fba70799e5dfc61a6`; Full QC đạt 1080×1920/30fps/H.264/AAC/48kHz, decode, duration và âm thanh. Chữ Việt trong PNG đã được kiểm tra trực quan.

Backup SHA `a50aa0885149ab4d2e40f45b30cb0990fcf8c0a91c2fa5f20e173a297a498b33`; phục hồi trong tiến trình riêng giữ đúng history, checkpoint, video/SRT và render. Undo/redo sau phục hồi tạo version mới, giữ SHA snapshot mục tiêu và hủy approval. Dữ liệu thử tạm được dọn sau khi xuất bằng chứng/backup; dữ liệu lịch sử được giữ.

Kiểm tra: 248 test Native liên quan (31 module), 38 test cuối cho ánh xạ/editor/HTTP và 685 test Studio PASS; 18 test Native và 8 test Studio mới nằm trong các tập đó. Các tập Native có giao nhau. Hồi quy mở rộng bắt đầu trước sửa cuối cho thao tác nhập lại; toàn bộ ánh xạ/editor/HTTP và phục hồi riêng đã kiểm tra lại với mã nguồn cuối.

## Giới hạn nghiệm thu

Video chuyển động, PCM, người duyệt và DOM là fixture. Có bytes/decoder/timeline/HTTP/renderer/backup thật tại máy; không có ASR/TTS/provider hoặc chi phí mới. Không chứng minh speech alignment, chất lượng giọng nói, licensing thực, browser/non-developer/Owner UAT, deployment hay full bundle A/B/C. Final vẫn chờ duyệt của người dùng.

Generic storyboard video operations, toàn bộ Mode A/B và các yêu cầu North Star còn lại tiếp tục thuộc phạm vi chương trình. Ma trận vẫn 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED; 59 nhóm chưa đóng. Không suy ra phần trăm hoàn thành từ số nhóm.
