# SQL narration, Studio và sáu bản con có giọng đọc

Đã tích hợp đề xuất narration từ server, UI nhập lời có xác nhận riêng, đọc receipt và tạo review riêng; polling giữ bản nháp và CAS của người sửa. Nguồn tích hợp chốt trước báo cáo: `3bb7b3fc0a5512f748b136f68cdfd959969c8b00`. Đây là các thành phần của Waves3/6/7/8/16, chưa chứng nhận toàn bộ Mode A/B hoặc các bundle A/B/C.

## Hành vi và kiểm tra

GET đề xuất không copy asset, xếp hàng, tính phí hoặc chạy TTS. Nhập và tạo review là hai thao tác có xác nhận riêng; actor do server xác minh. UI giữ nguyên body/key của lần ghi chưa rõ kết quả và chỉ đối chiếu receipt đúng nguồn. Lời dùng lại không chuyển quyền media, duyệt video hay quyền xuất bản. Main đăng ký route đã kiểm tra auth trước body; runtime narration vẫn mặc định tắt.

Polling dùng single-flight/generation và kiểm tra project, session, timeline, content và package sau await. Khi đang sửa, polling không ghi đè gain/subtitle hoặc đổi expected_version sang bản server mới. Nếu binding server đổi, dừng cập nhật để người sửa tải lại; approval/final chỉ sử dụng review đang gắn đúng các phiên bản. Các repro trước sửa và log thất bại gốc được giữ.

Rebuild storyboard giữ canvas/ratio/FPS đã lưu, dựng clip/cue mới và dùng crop fallback cần chú ý. Nó không nhập lại crop, approval, quyền media, ASR hoặc word clock cũ. Kiểm tra CAS trước và sau builder, kiểm tra family/ready receipt trong SQL; timeline vẫn là nguồn chỉnh sửa duy nhất.

| Bằng chứng | Phạm vi thực sự |
| --- | --- |
| Studio1008 PASS,0 FAIL,0 SKIP | Full bộ Node tại source UI đã ghép; transport/DOM fixture, không phải Owner UAT. |
| SQL API3 PASS | Actual main auth/default-off, proposal/import/review/replay và source video không audio; SQLite/local fixtures. |
| Canvas11 PASS | Canonical CAS/canvas/ratio/source relationship, có một input FFmpeg synthetic; không chạy provider hay render production. |
| Peer polling6 selected PASS | Race gain/subtitle/CAS và unknown writer, có overlap; không cộng vào1008. |
| Browser3 viewport | Main+Studio thật trên clone SQL bất biến, GET đề xuất/receipt, không có mutation của root; host final proof được ghi riêng. |

## Local-real: master có giọng và sáu bản con

Hai semantic chunks được VieNeu CPU thực sự đọc:2HTTP requests,2model inferences, không tải model mới. Sáu bản con dùng lại audio bất biến,0inference ở child. Có15 đầu ra Remotion thực và15FullQC PASS:3review/final của master gồm review trước reflow, và12review/final của sáu child. Các target: YouTube ngang, Shorts, TikTok, Reels,1:1 và4:5; bốn hình học1920×1080,1080×1920,1080×1080,1080×1350.

Lần chạy media thuộc source sản phẩm `5aff8e6`, không giả định đã chạy lại trên HEAD mới. Script, hình nền, source-clock binding và18copy narration là fixture kỹ thuật;7approval là AUTOMATED FIXTURE. Child cần review/approval riêng.30cost rows ghi bookkeeping render/TTS;12child TTS có provider_called=false và chi phí bổ sung0, không phải12 lần inference. Không có paid external call hay publishing.

Master final: `C:/vfns-sql-spoken-six-n4/master/approved-final/final.mp4`. Root độc lập đọc/hash all285actual files, ZIP295entries và FFprobe15media,0inference/render mới. Cold restore dùng SQLite URI ro/immutable, actual scoped viewer routes/media, SQL/object bytes giữ nguyên, không lifespan/DDL/worker/Redis/provider. Đây chưa phải source-footage Auto Edit toàn luồng, ý tưởng/trend toàn luồng hoặc chất lượng giọng được Owner chấp nhận.

Runtime74 cached pins và preset inference path đã chạy; pip check còn thiếu ba dependency của SDK đầy đủ. Không coi preset path đã chứng minh là qualification toàn SDK hoặc production image.

## Toàn vẹn bằng chứng và việc tiếp theo

Index [spoken-studio-deployment-evidence.json](north-star/spoken-studio-deployment-evidence.json) lưu hash từng log/source/helper/archive. Media ZIP42.8MB được tham chiếu riêng để tránh lưu trùng. Các thất bại fixture timezone, namespace noaudio và canvas ratio được ghi đúng source; hai API fixtures sửa namespace/profile để đi qua guard có sẵn, không nới guard. Không tự suy thành full legacy regression PASS từ95PASS/1FAIL trước sửa.

Có va chạm tên helper kiểm tra phụ giữa root/peer: helper gốc được phục hồi đúng SHA riêng, raw log đầu tiên không được tuyên bố khôi phục byte. N2 proof đạt, mã sản phẩm, media, model và accepted artifacts không bị ảnh hưởng. Browser thấy narration controls chưa đồng nhất kiểu dáng; UX vẫn mở.

Audit Mode B mới xác định P1: video word/timing UI còn thiếu; canonical voice/music/sfx chưa được production mix đầy đủ; SQL source_audio_processing chưa nối UI/proxy đầy đủ; genuine uploaded SQL Artifact A chưa có toàn chuỗi render. Word UI và canonical audio đang triển khai trên worktree riêng. Không thay thế chúng bằng tone/fixture acceptance.

SOURCE_PRESERVED=YES; PHASE10_TECHNICALLY_READY=YES; OWNER_UAT_REQUIRED=YES; PHASE10_READY=NO. Matrix5IMPLEMENTED_REAL/58PARTIAL/1NOT_VERIFIED;59 nhóm chưa đóng. IMPLEMENTATION_COMPLETE=NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO; VIDEO_FACTORY_NORTH_STAR_READY=NO. Owner listening/UAT đang deferred; tiếp tục các việc safe, không cần Owner thao tác lúc này.
