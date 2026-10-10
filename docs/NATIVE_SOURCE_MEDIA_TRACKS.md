# Audio và phụ đề tải lên trong Native Source Studio

Ngày: 2026-10-11. Phạm vi: Wave 3G/3I, phần audio Wave 6 và bảo toàn/khôi phục Wave 8F. Commit cha: `fefcbf789786e821d8b8cf10429d406752ecfa3a`. SHA commit mới và đường dẫn phục hồi được ghi trong preservation seal bên ngoài repository.

Phần này nối audio, music và SRT/VTT đã tải lên vào **cùng canonical timeline** của Source Auto Edit. Shot view vẫn là giao diện mặc định. Timeline, lịch sử undo/restore, preview, approval và renderer hiện có được tái sử dụng. Chỉ increment này được kiểm chứng; toàn bộ Wave 3, Mode B và North Star vẫn chưa hoàn tất.

## Cách dùng

Trong Assets, mở **Audio & phụ đề trong bản dựng** sau khi tạo Source timeline từ phân tích video. Danh sách chỉ lấy asset thực trong project hiện tại. Mở bảng và đọc dữ liệu không gọi ASR, TTS hoặc provider.

Chọn audio rồi chọn voice hoặc music, cửa sổ nguồn, vị trí trên timeline, gain và fade. Có thể thêm track hoặc chọn track hiện có; thay nội dung cần chọn rõ ô thay track. Music hỗ trợ lặp đến một thời điểm và crossfade. Những lựa chọn này không kéo dài video hay tạo khoảng trống để đạt một target duration. Waveform được giải mã từ file thực, không dựng biên độ giả.

Nếu audio có transcript đã lưu, có thể chọn phiên bản đã lưu để tạo caption cùng lần đặt voice. Cue và word timing được ánh xạ theo cửa sổ nguồn/vị trí timeline. Cắt voice qua một word có timestamp được từ chối. Khi transcript chưa có word timing, chỉ caption câu được dùng; không tạo alignment giả để bật karaoke. ASR âm thanh vẫn đi qua worker riêng của [NATIVE_AUDIO_TRANSCRIPTS.md](NATIVE_AUDIO_TRANSCRIPTS.md).

Chọn file SRT/VTT để nhập caption. Timebase `timeline` dùng trực tiếp thời gian trong video đang chỉnh; `source` ánh xạ qua các shot nguồn và tốc độ đã lưu. Offset là lựa chọn rõ ràng. Cue ra ngoài timeline mặc định bị từ chối; chỉ lựa chọn trim rõ ràng mới cắt/bỏ phần ngoài phạm vi, với số interval đã cắt/bỏ trong receipt. Chọn caption track cần thay và template. Caption được lưu ở text track, còn SHA/provenance của file phụ đề gốc được giữ riêng.

Editor caption sửa chữ Việt, thời điểm bắt đầu, duration và template theo từng trang 50 cue. Chữ được render bằng DOM text/textarea; không thực thi markup của file. Sửa text bỏ word timing/confidence cũ không còn được chứng minh. Người dùng có thể undo/restore timeline qua lịch sử hiện có. File gốc và transcript gốc không bị ghi đè.

Mỗi thay đổi tạo version timeline và revision project mới, bỏ approval/preview cũ. Preview mới phải được xem và duyệt trước render. Final review vẫn cần thao tác của người dùng. Reviewer/viewer được đọc; editor/owner mới được sửa qua phiên signed human và CSRF. Project/role chuyển, job đang chạy, project lưu trữ hoặc thay đổi chưa lưu ở bảng khác sẽ chặn thao tác.

## Hợp đồng và bảo toàn

- GET `/api/projects/{project_id}/auto-edit/media-tracks` đọc catalog; query duy nhất được chấp nhận là `caption_page` dương, không lặp.
- POST `/audio` và `/subtitles` yêu cầu revision, expected timeline version, timeline SHA256, native asset ID/SHA256 và request key. Payload là schema đóng; không nhận provider/filter/graph tùy ý.
- POST `/captions` yêu cầu cùng revision/version/timeline SHA, clip IDs và các thay đổi text/time đã chọn. Template là version trong catalog đã phê duyệt.
- SQLite transaction kiểm tra CAS, lock và provenance. Đo waveform chạy ngoài write transaction; transaction thứ hai kiểm tra lại revision, hash và file trước khi lưu. Không giữ write lock suốt thời gian giải mã.
- Request key được lưu dưới dạng hash. Replay cùng request trả receipt cũ; đổi body dưới cùng key bị từ chối. Controller giữ nguyên request/body khi retry một kết quả chưa rõ. Lịch sử import giới hạn 200; audio clip tối đa 128, track tối đa 32. Catalog asset/receipt/caption có giới hạn và đánh dấu cắt ngắn hoặc phân trang rõ ràng.
- `native-source-media-import-v1` giữ source binding, request digest, actor, waveform thực, cue-source hash hoặc immutable transcript version và kết quả. Timeline clip giữ import ID/hash và native source reference. Duplicate tạo ID/hash/lineage trong project mới, không chuyển quyền replay request key.
- Preview và render kiểm tra nguồn normalized **và** original trước khi dùng, kể cả nguồn SRT/VTT không có `asset_id` trực tiếp trong text clip. Source thay đổi làm thao tác/render bị từ chối.
- `source-media-imports.json` trong render checkpoint ràng buộc journal và SHA nguồn import đang dùng. Audio graph, subtitle derivation và QC dùng timeline hiện có. Voice/music không tạo một timeline thứ hai.
- Publishing rights gate tính cả nguồn phụ đề đang dùng. `rights_status=unknown` vẫn chặn mặc định; upload declaration hoặc thành công của render không chứng minh giấy phép. Publishing vẫn tắt mặc định.

Nguồn chính: `source_media_track_models.py`, `source_media_tracks.py`, `source_media_track_origins.py`, `source_media_track_routes.py`, `source_assets.py`, `source_preview.py`, `source_render.py` và `native-source-media-tracks.mjs`.

## Bằng chứng và giới hạn

Kết quả cuối được lưu trong [north-star/source-media-tracks-evidence.json](north-star/source-media-tracks-evidence.json), với hash log/source và phạm vi kiểm thử. Các ca mới gồm 10 unit/worker/provenance Native, 5 signed HTTP/controller Native và 10 Studio; không cộng các lần chạy chồng lặp thành tổng test.

`scripts/north_star_source_media_tracks.py` tạo fixture riêng, tải lên video/audio/music/SRT bằng luồng chunk thực, chạy controller Studio qua sáu yêu cầu HTTP signed, tạo preview đầy đủ hiệu ứng, fixture approval, final render và Full QC. Bundle mới nằm ở `recovery/20261007/native-source-media-tracks-n2`, gồm final/preview, canonical timeline, phụ đề, waveform journal, provenance, audio analysis/balance, render manifests/checkpoint, QC/frame evidence, transcript/scene/highlight/silence fixtures, job/events/cost và nguồn gốc. Preview/final dùng cùng hiệu ứng và PCM mix đã hash. Final download vẫn bị chặn trước final review.

Backup được tạo và khôi phục vào root mới; catalog khớp và nguồn vật lý của project đã khôi phục resolve được. Chỉ temporary fixture mới được dọn sau khi export nguồn và backup. Không xóa dữ liệu lịch sử hay thay accepted artifact.

Đã xem frame preview/final của run n2: dấu tiếng Việt và xuống dòng hiển thị nhất quán trong khung dọc. Đây là kiểm tra ảnh render riêng; chưa chứng minh browser layout, người dùng không phải lập trình viên hay Owner UAT. Audio là tone tạo tại máy, **không phải lời nói thật**; saved ASR, signed human và DOM là fixture. Không có inference ASR/TTS mới, real provider call, paid call hoặc xuất bản.

Run render n1 đã qua renderer/QC nhưng exporter dùng `-ss .35`, bị FFmpeg từ chối ở bước lấy ảnh. Exporter đã sửa thành `0.35`; n2 chạy lại toàn bộ và backup/restore đạt. Log/bundle n1 được giữ, không coi là acceptance hoàn chỉnh. Một assertion fixture track-lock ban đầu so sánh store với projection UI; đã sửa để so sánh đúng trạng thái store trước/sau. Không nới validation hoặc QC.

Còn mở: nối editor này vào narrated Mode A; realignment text đã sửa; language/detection/genuine ASR; metadata BPM/mood/energy/rights và balance cảm nhận; source media/genuine providers; browser ở 1366/1920/2560/non-developer/Owner; Meta analytics; Docker/production; toàn bộ yêu cầu North Star còn lại và ba bundle A/B/C đầy đủ. 64 nhóm vẫn là 5 `IMPLEMENTED_REAL`, 58 `PARTIAL`, 1 `NOT_VERIFIED`: 59 nhóm chưa đóng. `IMPLEMENTATION_COMPLETE`, `REAL_PROVIDER_ACCEPTANCE_COMPLETE`, `PRODUCTION_DEPLOYED` và `VIDEO_FACTORY_NORTH_STAR_READY` vẫn `NO`.
