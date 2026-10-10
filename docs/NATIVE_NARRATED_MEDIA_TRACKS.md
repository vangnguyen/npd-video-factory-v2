# Audio và phụ đề trên timeline Mode A

Đây là phần bổ sung cho storyboard có narration đã được đo và áp dụng. Nó tái sử dụng editor audio/phụ đề của Source Mode B và cùng timeline chuẩn. Chưa phải nghiệm thu đầy đủ Mode A, Mode B hoặc bộ Artifact B của North Star.

## Hành vi

- Đọc bảng track tạo projection ổn định từ PCM narration và scene plan đã xác minh. Đọc không sửa dự án, tạo job hoặc gọi provider.
- Lần lưu đầu tiên gắn track voice/caption đã đo vào timeline. Mọi lần lưu có revision, timeline version và SHA; vô hiệu hóa approval/preview cũ, lưu lịch sử và sự kiện.
- Có thể đặt voice/nhạc đã upload, chọn đoạn nguồn, vị trí, gain, fade, loop/crossfade và thay track. Waveform được đo bằng decoder thật. Audio không tạo transcription hoặc TTS từ editor.
- SRT dùng thời gian timeline, có offset và xác nhận trim. Mode A từ chối thời gian video nguồn khi chưa có lựa chọn video/mapping rõ ràng; không đoán nguồn giữa nhiều shot.
- Có thể sửa caption tiếng Việt và chọn template. Sửa chữ/thời gian bỏ alignment cũ. Template cần timestamp từng từ phải có bằng chứng từ nguồn; không suy diễn alignment từ narration.
- Chỉnh visual trong shot giữ các quyết định audio/caption. Subtitle mặc định trong shot tiếp tục được thể hiện trên caption track. Sau khi caption đã được sửa/import riêng, chỉnh subtitle trong shot yêu cầu dùng caption editor, tránh âm thầm bỏ qua lựa chọn.
- Rút ngắn timeline không tự cắt track đã chỉnh. Track khóa từ chối việc tự đổi duration/reference/caption. Nút nhạc legacy vẫn sửa track của nó, giữ các track nhạc đã upload riêng.
- Chuẩn bị narration mới rebind reference/scene plan; không replay upload. Duplicate giữ provenance nhưng không thừa hưởng authority chuẩn bị voice. Sáu variant dùng cùng nguồn, có project reference riêng và phải duyệt riêng.

## Preview, render, QC và phục hồi

Renderer chỉ dùng nhánh mới khi có `native-narrated-media-tracks-v1`. Dự án legacy giữ nhánh hiện có. PCM narration gốc được giữ nguyên; voice đặt trên timeline được xử lý bằng gain RMS/peak hiện có rồi đi qua cùng graph audio chuẩn với các track upload. Ducking đo năng lượng audio, không tuyên bố đã nhận diện lời nói. Nhánh mới căn packet và giữ control input đến cuối đoạn trước khi trim duration để preview và final có PCM nhất quán.

Caption render bằng FFmpeg/libass, sử dụng style có kiểu dữ liệu đóng và text đã escape. Noto Sans/Noto Sans Display được đóng gói từ Google Fonts chính thức, có SHA và OFL 1.1 nguyên bản trong `services/windows_native/fonts`. Font thay đổi làm render/QC thất bại. Syntax tag tham chiếu [tài liệu ASS của Aegisub](https://aegisub.org/docs/latest/ass_tags/).

Checkpoint ràng buộc canonical mix, graph filter, import origins, subtitle/style/font, raw audio diagnostics, frame sampling và Full QC. Replay, review và render đã lưu kiểm tra lại source narration và nguồn upload vật lý. Audio QC ràng buộc đúng stem manifest của nhánh mới; mất marker hoặc khác SHA không được hạ về nhánh legacy.

Evidence retained tại `recovery/20261007/native-narrated-media-tracks-n1` gồm video preview/final, timeline, ASS/JSON, PCM/mix, provenance, render/QC/checkpoint, narration plan, cost, job/events, font/license và backup. Restore vào thư mục độc lập xác minh lại catalog, source và render. File tạm riêng của lượt chạy được dọn sau khi xuất nguồn và backup; không xóa dữ liệu lịch sử.

## Mức xác minh và giới hạn

HTTP loopback, upload, decoder, waveform, SQLite, renderer/libass, QC và backup/restore là local thật. Controller dùng fake DOM; signed human, narration PCM và word timing là fixture. Không có provider, phí mới, ASR/TTS mới, publishing thật, production deployment hoặc Owner UAT trong bằng chứng này. Các test caption động dùng timestamp fixture được ghi rõ, không phải alignment provider thật.

Mỗi nhánh editor dùng tối đa 32 track, 128 audio clip và 2.500 clip tổng; caption import có giới hạn riêng 2.000 nhưng storyboard Full QC hiện chỉ nhận tối đa 128 caption. Không báo hỗ trợ bản dựng dài vượt giới hạn đó. UI chỉnh track nâng cao đầy đủ, source-time SRT theo video được chọn, undo/redo audio/caption Mode A, cấu hình DSP trên UI, alignment/provider/giọng thật, browser/non-developer/Owner acceptance và toàn bộ luồng North Star A/B/C vẫn còn yêu cầu cần đóng.

`PHASE10_TECHNICALLY_READY=YES`, `OWNER_UAT_REQUIRED=YES`, `PHASE10_READY=NO`. `IMPLEMENTATION_COMPLETE`, `REAL_PROVIDER_ACCEPTANCE_COMPLETE`, `PRODUCTION_DEPLOYED` và `VIDEO_FACTORY_NORTH_STAR_READY` tiếp tục là `NO`.

Test và SHA nguồn/bằng chứng được ghi tại [narrated-media-tracks-evidence.json](north-star/narrated-media-tracks-evidence.json). Bảng [North Star capability matrix](NORTH_STAR_CAPABILITY_MATRIX.md) giữ đủ 64 nhóm và 90 mục Master Spec; phần bổ sung này không thu nhỏ tiêu chuẩn nghiệm thu.
