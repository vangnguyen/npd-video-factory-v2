# Drama M4 — hồi quy PASS, nghiệm thu thao tác Owner còn mở

Ngày 18–19/10/2026. Phạm vi: VF-DRAMA-M4-USABILITY-AND-REAL-EXPORT-CLOSURE-04; không mở thêm tính năng.

| Mục | Trạng thái |
| --- | --- |
| APPLICATION HEAD | `0eb7e679be6a138fff891987bd507ea4c82b8000` |
| STUDIO SERVED SOURCE | `C:/vfdr07` |
| Branch | `codex/vf-drama-m4-closure-07`, đã push; không merge main |
| URL / build | http://127.0.0.1:62684/ · `drama-m4-closure-07` |
| REGRESSION_PASS | YES: các suite nêu dưới |
| TECHNICAL_PASS | PARTIAL: còn qualification tải file qua browser và một nhãn phụ |
| OWNER_UAT_COMPLETE | NO |

Commit báo cáo sau candidate chỉ thay docs/evidence, không thay source đã kiểm thử. About giữ HEAD đã nạp của application. Không kết luận Studio cũ chỉ vì report HEAD khác.

## Baseline và bảo toàn

Điểm đầu thực tế là `C:/vfdr06`: code `2b8ff625`, repository HEAD `dd836b8b` chỉ thêm tài liệu/bằng chứng. Không reset về `baa85747`. Sửa hẹp trong worktree `C:/vfdr07`; source giữ cố định trong từng lượt regression. Chỉ cập nhật Studio khi không có job/audition/preview đang chạy, đã bảo toàn form Owner và hoàn tất backup/restore.

SOURCE_PRESERVED=YES. ACCEPTED_ARTIFACTS_PRESERVED=YES: 15 hash video lịch sử khớp; casting/audio cũ không tự thay. Giữ 25 voice registrations và 10 mẫu nghe thật. File Drama mới được bảo toàn riêng trong [accepted-owner-film.json](../evidence/drama-m4-closure-07/accepted-owner-film.json).

Backup ZIP trước cập nhật Studio đã restore thật vào thư mục mới: 366 entry khớp, SHA256 `d0afb8455277954ec194a9bc1f0e9c678e10b597b18661501649e9e5aab4efdb`. Bản đó có audio/preview, chưa có export tạo sau đó. Ba SQLite snapshot nhất quán sau xuất được giữ bổ sung, `quick_check=ok`; không gọi chúng là một lượt full restore mới. Bundle nguồn đã verify, cần base `dd836b8be1fa8a083aee5a5ad4c67a9aa6fc2e71`. [Receipt và đường recovery](../evidence/drama-m4-closure-07/recovery/receipts.json).

## Browser QA

| Viewport yêu cầu | Kết quả |
| --- | --- |
| 1366×768 | Quan sát và chụp browser thật |
| 1920×1080 | Quan sát và chụp browser thật |
| 2560×1440 | Quan sát và chụp browser thật |

Chrome trên đúng PC đã khởi tạo được sau khi phục hồi đúng thư mục tạm kernel bị thiếu. Không đổi security, quyền hàng loạt hoặc hồ sơ browser người dùng. Mỗi viewport được đặt và chụp riêng, không resize một ảnh thành ba. Metrics và pixel ảnh được giữ riêng; Chrome loại thanh cuộn khỏi bề rộng content. Có 17 ảnh candidate được lưu trong repository; các ảnh chẩn đoán sai tab giữ ngoài tập bằng chứng viewport.

Luồng thật đã đi qua: entry ba lựa chọn → Drama chưa có script/media → lưu kịch bản một tab → xác nhận hai người nói → nghe mẫu → dropdown/voice picker → lưu phân vai sang bước cảnh mà chưa cần audio/media → chọn ảnh từ thư viện → tạo thoại/áp timing → preview/duyệt → render/QC → delivery/history. Mở lại QA giữ revision 13, bước đang làm, casting, line IDs/thứ tự, ghi chú và media. Đây là browser reopen, không gọi là một lượt application restart mới.

Hai lỗi browser đã xác nhận và sửa:

- Header vẫn “Chưa lưu” sau save đã đối chiếu: `native.mjs` cập nhật progress sau khi dirty được xử lý có kiểm chứng; `shot-studio.mjs` cung cấp progress. Không tắt CAS hoặc force dirty=false.
- Panel duyệt preview Drama bị source editor đưa về proposal-card đang ẩn: `native-source-editor.mjs` chỉ khôi phục shared review khi chính source editor đang giữ nó. Panel Drama hiển thị được; project nguồn Mode B vẫn có review.

Nút bị khóa đã kiểm thật: bỏ giọng Bình trong nháp QA → “Còn thiếu giọng của Bình” → Next khóa → hành động xử lý focus đúng select Bình. Discard khôi phục toàn bộ snapshot revision 13, không thêm save/TTS/job. [Bằng chứng](../evidence/drama-m4-closure-07/browser/missing-voice-validation.json).

Giới hạn còn mở:

- `M4-07-LABEL-01` / minor: quay về casting sau khi đã có audio vẫn có nhãn chung “Chưa tạo lời thoại”. Step 4 và các chốt audio/preview/approval đúng; chưa che finding bằng cách sửa source giữa regression.
- `M4-07-DOWNLOAD-01` / qualification: click MP4/ZIP đã thực hiện nhưng extension không trả download completion. HTTP download/hash/CRC PASS được báo riêng. Copy caption đã kiểm clipboard; Open Output Folder đã gọi UI/API thành công, chưa quan sát Explorer vì native automation bị tắt. Chờ Owner kiểm thao tác bằng browser thường.
- Upload chooser bị giới hạn file-URL của extension; đã dùng Asset Picker từ thư viện hợp lệ. Không nới quyền hoặc ghi upload PASS. Trang `chrome://downloads` bị URL policy chặn; không dùng đường vòng.

[Walkthrough](../evidence/drama-m4-closure-07/browser/walkthrough-result.json) · [Ảnh và hash](../evidence/drama-m4-closure-07/browser/screenshots.json) · [Metrics](../evidence/drama-m4-closure-07/browser/viewport-records.json).

## Voices

Registered=25; có căn cứ nguồn quyền=25; real samples=10 với 10 PCM SHA khác nhau. Không tạo thêm 15 mẫu còn lại, nâng SDK/model hay dùng dịch vụ trả phí. Giữ model/preset Thùy Dung khóa và casting lịch sử.

Owner casting riêng phim nghiệm thu: **An=Thùy Dung; Bình=Thiện Minh; narrator=false**. Chọn giọng không được ghi thành Owner đã nghe duyệt toàn bộ thư viện. [Custody và mẫu thật](../evidence/drama-m4-closure-07/voice-history-custody.json).

## Real Drama — Lá thư trước cơn mưa

Project `1c768012f9624de494a9fadab63c1a31`, revision 8, một bối cảnh, tám câu nguyên bản.

| Chốt | Kết quả |
| --- | --- |
| Script approval | Owner đã duyệt kịch bản và hình quán cà phê |
| Visual assets / rights | Hình minh họa nguyên bản chương trình tạo; giữ provenance/trạng thái quyền hiện có, không tự tạo legal override |
| Real dialogue | Tám câu local thật; Owner đã nghe và duyệt; audio 35.07s |
| Timing | Áp vào canonical timeline 35.32s, thay target 62.8s; không tạo dead air |
| Preview | Owner đã xem/nghe và duyệt để render |
| Final / QC | Owner đã duyệt đúng file cuối; QC PASS |
| Delivery package | MP4/bìa/SRT/caption/ZIP đã tạo và kiểm toàn vẹn |
| Owner decision | Chưa ghi thay nghiệm thu thao tác bàn giao hoặc toàn bộ M4 |

File cuối 35.333s, 1080×1920/9:16, 30 FPS, H.264/AAC 48 kHz. SHA256 `a57f965e530b5100ea13d03464cf38d23300f9245f1e973e30ebf48a36381ef8`. Final reuse đúng preview đã duyệt, hash bằng nhau; không tạo lại TTS/job trùng.

QC: decode toàn bộ, không clipping/black interval, trailing silence 0.58s dưới 2s. 16 cue phụ đề trong safe area; đối chiếu speaker/text/timing với tám câu và xem frame thật của An/Bình. Không tuyên bố word alignment/ASR, Vision semantics hoặc diễn xuất/lip-sync chưa chạy. Hình giữ nguyên như preview đã được duyệt.

Export `nexp_fb80d14cbad44c699c73bef0f02ff9af`: 19 file trong immutable manifest, ZIP 20 entry, CRC và tất cả hash khớp. Có MP4, cover JPG, SRT, title/caption/description/hashtags/CTA, provenance/rights/QC/metadata. Caption v1. Không đăng ra nền tảng. Sau full regression, project vẫn revision 8 và document SHA khớp export binding, không job hoạt động.

[Owner decisions có phạm vi](../evidence/drama-m4-closure-07/owner-scoped-decisions.json) · [Delivery integrity](../evidence/drama-m4-closure-07/owner-delivery-integrity.json) · [Subtitle speaker check](../evidence/drama-m4-closure-07/owner-subtitle-speaker-check.json) · [Custody sau regression](../evidence/drama-m4-closure-07/post-regression-owner-custody.json).

## Đổi giọng thật trong project QA riêng

Project `60faab88eb6f4724abd48297d93d2016`; mọi approval/ack mang nhãn TECHNICAL QA FIXTURE, không Owner UAT. Tạo bốn câu với An=Trúc Ly/Bình=Thiện Minh, sau đó chỉ đổi An=Thùy Dung. Hai clip An mới; hai clip Bình giữ đúng binary SHA và reuse=true. Hình, line IDs, text và thứ tự giữ nguyên.

Timeline 9.13→9.14s; phụ đề/mix/preview cập nhật hash. Old preview STALE, video_url=null, approval bị xóa; preview mới vẫn cần duyệt. Audio cũ giữ làm lịch sử nhưng current flags chặn reuse sai. Không sửa phim Owner. [Audio comparison](../evidence/drama-m4-closure-07/targeted-local-real-audio-comparison.json) · [Phụ thuộc](../evidence/drama-m4-closure-07/targeted-dependency-closure.json).

## Regression trên source cố định

| Phạm vi | Kết quả |
| --- | --- |
| FULL STUDIO | 2168 PASS, 0 skip |
| RENDERER / TYPECHECK | 52 PASS / PASS |
| FULL NATIVE | 2313 loaded, 2313 run, 0 failure, 0 error, 0 skip; PASS /4352.938s |
| API SCOPE | 92 PASS: final_export_quality, verified_artifact_delivery, source_asset_delivery |
| POSTGRESQL CASES | Ba ca NOT_RUN; chưa có database test riêng |

Full Native là lượt mới: 254 module, bốn nhóm 561 case rồi 69 case tuần tự. Toàn bộ source Native/Studio/API giữ nguyên; không bỏ ca hoặc cộng replay. Lượt trước `dd836` có 2313 run/1 failure/11 errors vẫn giữ NOT PASS. Quan sát cũ là HTTP fixture timeout/cleanup và STOCK_CACHE_BUSY khi tranh chấp. Fixture client mới chờ tối đa 30s và finally close; không sửa production timeout, QC hay concurrency. Cohort sáu ca PASS chỉ là diagnostic. [Full mới](../evidence/drama-m4-closure-07/full-native-summary.json) · [Full trước](../evidence/drama-m4-closure-07/prior-native-full-not-pass.json) · [Suite khác](../evidence/drama-m4-closure-07/candidate-test-summary.json).

Full API qualification cũ giữ riêng: Linux 4376 collected/4310 pass/26 fail/40 skip; replay media/environment không cộng thành full PASS. Ba ca PostgreSQL không nằm trên Native đang bàn giao, vốn dùng `sqlite3` / `workflow.sqlite3`. Không chứng nhận PostgreSQL/Docker/production ready. [PG qualification](../evidence/drama-m4-closure-07/postgresql-qualification.json).

## Hai mốc bàn giao

STANDARD_EXPORT_OWNER_ACCEPTED=NO: các ca 1–4 giữ riêng; fixture ba giây không thay NPD UAT. DRAMA_FINAL_VIDEO_OWNER_ACCEPTED=YES. DRAMA_EXPORT_OWNER_ACCEPTED=PENDING thao tác bàn giao. OWNER_UAT_COMPLETE=NO.

FINAL_VIDEO_QUALITY_READY=YES cho riêng file Drama đã duyệt/QC. EXPORT_CENTER_READY=PARTIAL qualification tải/mở. DELIVERY_PACKAGE_READY=YES cho export này. EXPORT_HISTORY_READY=YES kỹ thuật/browser trên record mới/cũ. DRAMA_VOICE_CASTING_READY=YES kỹ thuật cho luồng đã thử; OWNER_VOICE_UAT_REQUIRED=YES cho nội dung mới ngoài phạm vi Owner đã nghe duyệt.

Owner còn kiểm Copy caption, Mở thư mục đầu ra, mở/tải MP4 và ZIP ở bước 5; câu hỏi đã gửi. Không có phản hồi không được suy thành duyệt. Nghiệm thu video thường 1–4 và toàn bộ usability M4 vẫn riêng.

PLATFORM_API_PUBLISHING=DEFERRED. ANALYTICS=DEFERRED. FULL_TREND_RADAR=DEFERRED. PRODUCTION_DEPLOYED=NO.

## Policy và dọn dữ liệu

Automatic approval review từ chối trước thực thi các lệnh xóa bản restore thử `C:/vfct/drama-m4-final07-restored-check` và ba scratch đã hoàn tất `C:/vfct/drama-m4-final07-native-n2/0`, `/2`, `/3`, lý do “blocked by policy”. Dù preflight ba scratch có receipt thành công, không active process/reparse point, khoảng 768 MB vẫn giữ nguyên. Không thử lại, dùng đường vòng hoặc xóa source, 15 video, audio/casting cũ và recovery. [Receipt từ chối](../evidence/drama-m4-closure-07/completed-native-scratch-cleanup-denied.json).
