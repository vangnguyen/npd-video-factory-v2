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

Nguồn chi tiết: [ma trận năng lực](NORTH_STAR_CAPABILITY_MATRIX.md), [kế hoạch đóng gap](NORTH_STAR_GAP_CLOSURE_PLAN.md), [mốc video công nghệ](NATIVE_TECHNOLOGY_ACCEPTANCE.md), [mốc quản trị kênh](NATIVE_CHANNEL_PROFILE_ADMIN.md). SHA nguồn cuối cùng, kiểm thử và bản khôi phục được ghi riêng trong `recovery/20261007/source-audio-clock-program-state.json` của workspace để không tạo tham chiếu vòng với commit chứa tài liệu.

Mốc ASR: [Native language selection](NATIVE_ASR_LANGUAGE_SELECTION.md), [bằng chứng](north-star/asr-language-selection-evidence.json). Kiểm thử 50 Native / 37 API / 747 Studio; browser queue và hình học trường ở 1366/1920/2560 là phạm vi thành phần. Genuine speech/provider và full Mode A/B vẫn còn mở.

Mốc clock nguồn: [decoded source frame clock](NATIVE_DECODED_SOURCE_FRAME_CLOCK.md). Mẫu mới có PTS/time base/log/job/checkpoint thật; legacy giữ seek chưa xác minh. VFR và video bắt đầu giây 4 đã đối chiếu FFprobe và khôi phục trong tiến trình mới. Không nghiệm thu semantics/tracking/ASR/Owner/production từ bằng chứng này.

Mốc dense video clock: [NATIVE_DENSE_VISUAL_CLOCK.md](NATIVE_DENSE_VISUAL_CLOCK.md). Motion/cảnh mới dùng PTS decoder, v3 còn đọc được; audio/ASR clock và full original acceptance vẫn mở. Native 25 PASS; API 17 PASS / 1 media skip thiếu FFmpeg Linux; hai rehearsal cục bộ và cold restore đạt.

Mốc audio nguồn: [NATIVE_SOURCE_AUDIO_CLOCK.md](NATIVE_SOURCE_AUDIO_CLOCK.md). PCM liên tục và waveform giữ mốc decoder; transcript giả lập giữ bản PCM gốc và ánh xạ sang nguồn. Native 43 / API 20 / Studio 751 / consumer Native 22 PASS (các batch có phần trùng, không cộng thành tổng duy nhất). Rehearsal audio trễ 0,47675 giây và khôi phục trong tiến trình mới đạt. Genuine ASR, audio gián đoạn, đầy đủ audio/AV/QC/Mode A/B/Owner/A-B-C/production vẫn mở.
