# Tiến độ North Star ngày 12/10/2026

Chương trình vẫn theo toàn bộ Master Spec: 90 mục, được kiểm toán thành 64 nhóm yêu cầu. Hiện có 5 nhóm IMPLEMENTED_REAL, 58 nhóm PARTIAL và 1 nhóm NOT_VERIFIED. Còn 59 nhóm chưa đóng; đây không phải 59 việc nhỏ hay một phép tính phần trăm hoàn thành. IMPLEMENTED_REAL mô tả hành vi chạy được, không tự chứng nhận provider thật, Owner hoặc production.

| Mốc | Trạng thái |
| --- | --- |
| Wave 0 — bảo toàn nguồn | SOURCE_PRESERVED = YES; nhánh riêng trên remote, bundle khôi phục, 15 artifact lịch sử được giữ |
| Wave 1 — kiểm toán | Có baseline, ma trận 64 nhóm và kế hoạch đóng gap theo Master Spec |
| Wave 2 / Phase 10 | PHASE10_TECHNICALLY_READY = YES; OWNER_UAT_REQUIRED = YES; PHASE10_READY = NO |
| Waves 3–14 | Đã triển khai nhiều thành phần và luồng kiểm thử; các tiêu chí đầy đủ vẫn PARTIAL |
| Wave 15 | Hardening/khôi phục cục bộ đã có bằng chứng; Docker/production/soak chưa được nghiệm thu đầy đủ |
| Wave 16 | Chưa có đủ ba bundle A/B/C đáp ứng toàn bộ định nghĩa hoàn tất |

5 nhóm IMPLEMENTED_REAL hiện tại: ranh giới độc lập, chuẩn hóa tín hiệu, vòng đời xu hướng, nghiên cứu/bằng chứng và duyệt của con người.

Các mốc gần nhất gồm timeline nguồn và lời đọc dùng cùng mô hình canonical; chỉnh clip/hiệu ứng/chuyển cảnh; preview/render/QC cục bộ; video công nghệ ngoài bất động sản với giọng đọc thật trên máy và sáu biến thể dùng lại PCM; hồ sơ kênh Owner có phiên bản, lịch sử, lưu trữ/mở lại và khôi phục trong tiến trình mới. Mốc tiếp theo thêm tracking vùng hình ảnh cục bộ/crop canonical và profile ASR tổng quát Việt/Anh/tự phát hiện, có kiểm thử worker và kiểm tra queue trong trình duyệt thật. ASR của mốc mới dùng payload giả lập; không tự nghiệm thu nội dung hay phát âm của Owner.

Phần còn mở tập trung ở luồng UI đầy đủ Mode A/B; ASR/Vision/tracking và generative media thật; quản trị đầy đủ các họ profile, giọng/ngôn ngữ; publishing/analytics trên tài khoản thật; winner/learning có bằng chứng khán giả; Trend Radar đủ nguồn; Agent Hub độc lập ngoài môi trường fixture; Docker/S3/PostgreSQL/Redis/soak/production recovery và nghiệm thu A/B/C.

IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO; VIDEO_FACTORY_NORTH_STAR_READY = NO. Publishing vẫn tắt mặc định. Không merge main, triển khai production, thay artifact đã nghiệm thu hoặc gọi provider trả phí trong mốc quản trị kênh này.

Nguồn chi tiết: [ma trận năng lực](NORTH_STAR_CAPABILITY_MATRIX.md), [kế hoạch đóng gap](NORTH_STAR_GAP_CLOSURE_PLAN.md), [mốc video công nghệ](NATIVE_TECHNOLOGY_ACCEPTANCE.md), [mốc quản trị kênh](NATIVE_CHANNEL_PROFILE_ADMIN.md). SHA nguồn cuối cùng, kiểm thử và bản khôi phục được ghi riêng trong `recovery/20261007/upload-source-hash-program-state.json` của workspace để không tạo tham chiếu vòng với commit chứa tài liệu.

Mốc ASR: [Native language selection](NATIVE_ASR_LANGUAGE_SELECTION.md), [bằng chứng](north-star/asr-language-selection-evidence.json). Kiểm thử 50 Native / 37 API / 747 Studio; browser queue và hình học trường ở 1366/1920/2560 là phạm vi thành phần. Genuine speech/provider và full Mode A/B vẫn còn mở.

Mốc clock nguồn: [decoded source frame clock](NATIVE_DECODED_SOURCE_FRAME_CLOCK.md). Mẫu mới có PTS/time base/log/job/checkpoint thật; legacy giữ seek chưa xác minh. VFR và video bắt đầu giây 4 đã đối chiếu FFprobe và khôi phục trong tiến trình mới. Không nghiệm thu semantics/tracking/ASR/Owner/production từ bằng chứng này.

Mốc dense video clock: [NATIVE_DENSE_VISUAL_CLOCK.md](NATIVE_DENSE_VISUAL_CLOCK.md). Motion/cảnh mới dùng PTS decoder, v3 còn đọc được; audio/ASR clock và full original acceptance vẫn mở. Native 25 PASS; API 17 PASS / 1 media skip thiếu FFmpeg Linux; hai rehearsal cục bộ và cold restore đạt.

Mốc audio nguồn: [NATIVE_SOURCE_AUDIO_CLOCK.md](NATIVE_SOURCE_AUDIO_CLOCK.md). PCM liên tục và waveform giữ mốc decoder; transcript giả lập giữ bản PCM gốc và ánh xạ sang nguồn. Native 43 / API 20 / Studio 751 / consumer Native 22 PASS (các batch có phần trùng, không cộng thành tổng duy nhất). Rehearsal audio trễ 0,47675 giây và khôi phục trong tiến trình mới đạt. Genuine ASR, audio gián đoạn, đầy đủ audio/AV/QC/Mode A/B/Owner/A-B-C/production vẫn mở.

Mốc audio gián đoạn: [NATIVE_SOURCE_AUDIO_GAPS.md](NATIVE_SOURCE_AUDIO_GAPS.md). Forward gap được đo bằng PTS và FFprobe; WAV phục vụ ASR đệm đúng 9.216 mẫu, giữ PCM gốc và không sửa nguồn. Waveform để trống khoảng thiếu; từ đi qua gap yêu cầu kiểm tra. Native 47 PASS, 7 ca guard chồng lặp sau thay đổi cuối; API 23 / Studio 752 / consumer Native 22 PASS. Hai rehearsal/cold restore đạt với ASR giả lập. Genuine speech/provider, đầy đủ UI/Mode A/B/Owner/A-B-C/production vẫn mở; 59 nhóm chưa đóng.

Mốc UI sửa từ tại audio gap: [NATIVE_ASR_GAP_REVIEW.md](NATIVE_ASR_GAP_REVIEW.md). Bản provider/candidate gốc giữ riêng; sửa chữ/thời gian/bỏ từ được lưu có phiên bản, resume job cũ không cần credential và không tạo transport mới. Native 54 / consumer-static 25 / Studio 758 PASS; static cuối 3 ca chồng lặp PASS. HTTP controller, browser 1366/1920/2560 và hai cold restore đạt trên tone/ASR/danh tính fixture. Owner UAT, genuine speech, đầy đủ Mode A/B/A-B-C/production vẫn mở; 59 nhóm chưa đóng. Xóa root fixture browser bị policy chặn; root và backup được giữ.

Mốc mix/render audio gap: [NATIVE_SOURCE_GAP_RENDER_CLOCK.md](NATIVE_SOURCE_GAP_RENDER_CLOCK.md). Clock nguồn được giữ trước trim/speed; khoảng thiếu giữ silence và âm thanh cuối còn nguyên. Lỗi lệch AAC khoảng 48 ms được sửa bằng mux PCM canonical vào MP4; không đổi ngưỡng QC. Native hồi quy 54 PASS; clock/gap 14 PASS; API 34 PASS / 7 media skip thiếu FFmpeg Linux. Effects preview/final/QC/cold và kiểm tra biên gap đạt trên tone/ASR/approval fixture; không tự nghiệm thu Owner/full Mode A/B. Vẫn còn 59 nhóm chưa đóng. SHA nguồn đã bảo toàn và recovery pair mới ở `recovery/20261007/upload-source-hash-program-state.json`.

Phiên bản preview mới: lightweight v2 / full-effects v3. Studio yêu cầu tạo lại preview cũ cho lượt duyệt mới; render checkpoint cũ chỉ được đọc sau xác minh hash và không cấp quyền render mới. Studio hiện tại 758 PASS; rehearsal n4 đạt đúng profile mới và cold restore.

Kiểm tra profile/legacy cuối: 18 Native PASS; đọc checkpoint cũ không re-encode, duyệt preview cũ không cấp quyền render mới; các batch có phần chồng lặp.

Mốc upload khóa nguồn: [NATIVE_UPLOAD_SOURCE_HASH.md](NATIVE_UPLOAD_SOURCE_HASH.md). UI tính SHA toàn file bằng lát tối đa 1 MiB trước create/resume; file trùng tên/kích thước có nội dung khác không dùng chung ý định. Browser thật upload sáu loại media và phụ đề đổi nội dung; reload journal partial, chặn đuôi file đổi, resume đúng nguồn/dedup và chặn MIME sai. Native cuối 53 PASS / Studio cuối 769 PASS; Node/controller pause và browser pause được tách riêng. Hai cold restore browser giữ đúng dữ liệu, không tạo lại upload; các root được giữ do policy cleanup. Vẫn 59 nhóm chưa đóng, không tự nghiệm thu Mode A/B/Owner/production.
