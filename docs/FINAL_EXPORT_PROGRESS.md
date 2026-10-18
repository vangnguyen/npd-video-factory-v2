# Xuất video và bàn giao để đăng thủ công

Chương trình `VF-FINAL-EXPORT-MANUAL-PUBLISHING-FOCUS-01`, bắt đầu 2026-10-18. [Baseline và phục hồi nguồn](FINAL_EXPORT_BASELINE.md).

[Hướng dẫn thao tác cho người dùng](FINAL_EXPORT_USER_GUIDE_VI.md). P0 đã đóng; P1–P5 có chức năng và kiểm thử kỹ thuật đang hoàn thiện chứng nhận; P6 đã nối UI/API, casting, TTS từng câu, canonical timeline, render/QC và delivery bằng mock/local media. P7 chưa có Owner acceptance. Không dùng phần trăm hoàn thành để thay cho các trạng thái này.

## Phần đã triển khai

- **P0 hoàn thành:** source branch riêng, Git bundle đầy đủ đã verify, archive riêng 11 file sửa dở, rehash 15 video nghiệm thu. Không thay checkout đang dùng hoặc video cũ.
- **P1 đang đóng:** QC dùng chung đo đoạn im lặng cuối, mặc định quá 2 giây là fail; thiếu phép đo cũng fail. Frame đen bất kỳ đã phát hiện cũng fail, kể cả chỉ một frame hoặc đoạn cuối được làm tròn duration về 0. Giữ hard gates SAR/rotation và đứng hình cuối ngoài intentional image hold. Policy Native, binding thời lượng thực, tên riêng, phụ đề và source-render hiện có được tái kiểm thử. Chưa có Owner listening/UAT mới.
- **P2–P5 bản đầu trên Windows Native:** mục **Xuất video**, caption theo nền tảng, gói MP4/cover/SRT/copy/QC/rights/manifest/ZIP, lịch sử, download, mở thư mục Windows. Export chỉ sao chép đúng byte MP4 đã qua duyệt cuối và chạy lại FullProductionQC trên file giao thực tế.
- Manifest giữ version của dự án/timeline/script/audio/subtitle, profile, hash preview/final, hash approvals, metadata media, caption version và hash từng file. Không có post ID hoặc trạng thái đã đăng.
- Thay đổi project làm bản xuất cũ mang nhãn phiên bản cũ; vẫn tải được bản lịch sử đã bàn giao sau kiểm tra toàn vẹn. Tạo bản mới không thay tệp cũ.
- Exact request key + fingerprint, lease giữa thread/process, thư mục staging riêng, ghi hash custody trước handoff, đối chiếu lại approval/quyền trước ready. Retry sau mất phản hồi/restart dùng lại cùng export; không tự ghi đè output lỗi hoặc đã đổi.
- Caption có CAS/version history, Master/TikTok/Facebook Reels/Instagram Reels/YouTube Shorts; sửa, copy clipboard và tải TXT. Caption không được gửi đến nền tảng.
- Checklist đăng thủ công chỉ lưu trong phiên browser; không xác minh quyền hay tự đăng.
- Bìa đã hỗ trợ upload kiểm tra magic/MIME/SHA256, dedupe; chọn frame, ảnh project hoặc thumbnail candidate đã lưu; crop theo tỷ lệ, JPG/PNG, chữ tiếng Việt và logo chỉ khi cấu hình hợp lệ. Bìa tải lên mặc định quyền unknown, không tự nâng thành owned.
- Caption đã có chọn bản lịch sử và tái tạo riêng variant từ Master/kịch bản bằng thao tác cục bộ; không giả là đã gọi AI hoặc đăng bài. History có thumbnail và so sánh thông số phiên bản.
- Tạo lại ZIP sinh delivery mới từ các file/hash của bản lịch sử, chạy lại QC, giữ nguyên bản trước kể cả ZIP trước hỏng. Lost response của thao tác này giữ đúng endpoint/key. History có đối chiếu/tiếp tục khi tab browser đã mất receipt; ngừng yêu cầu giữ nguyên file và chặn request-key cũ tự hồi sinh.
- Backup nhận biết export đang chuẩn bị và đếm các journal/cover/caption mới. Đã restore một export vào thư mục mới và kiểm tra lại manifest/video; đã thử child process thật thoát ngay sau handoff rồi đối chiếu lại cùng một export.
- P5 đã thử process thật thoát giữa render (sau Remotion, trước mux/QC): cùng job được resume trong attempt mới, giữ nguyên file partial riêng. Thoát sau render nhưng trước lưu kết quả: resume dùng checkpoint đã verify, không gọi renderer lần hai; bản cuối vẫn phải được duyệt rồi mới tạo một delivery. Các ca này là test fixture, không phải Owner UAT.
- Đã tạo một delivery mới từ bản restore và chạy QC hiện tại gồm gate một frame đen. QC pass; manifest mới, video và ZIP cũ được giữ nguyên. [Biên nhận](../evidence/final-export-manual-publishing/quality-closure/restored-delivery-current-qc.json).
- P2 trên video nguồn và storyboard có giọng đã chuẩn bị: 24/25/30/60 FPS, 3 mức chất lượng allowlist, bật/tắt audio và burn-in. Cài đặt nằm trong canonical metadata, làm mất duyệt/preview cũ; projection không xóa hay sửa clip gốc. SRT riêng vẫn có khi không burn-in. UI chặn gói khi cài đặt chưa áp dụng. Các video chưa chuẩn bị giọng vẫn giữ giới hạn và cần chuẩn bị trước; không giả tạo audio.
- Bộ kiểm tra mới đã render thật narration 24 FPS/high và 25 FPS/small với âm thanh tắt/phụ đề không burn-in nhưng có SRT. Dùng PCM tổng hợp và approval fixture, không phát sinh suy luận TTS, không phải speech hay Owner UAT. Chỉnh shot giữ cài đặt xuất và làm mất duyệt cũ. UI đổi hình học dùng revision/hash mới trả về rồi mới lưu cài đặt, không dùng CAS cũ.
- Native có capability chế độ xuất thủ công; UI ẩn các console tài khoản/OAuth/publication/analytics/winner/learning đang hoãn. Adapter, API contract và dữ liệu lịch sử vẫn giữ nguyên.
- Ba ca render/QC/delivery thật bổ sung đã qua: 1920×1080/30 FPS, 1080×1080/60 FPS và 1080×1350/30 FPS. Ca 4:5 đầu tiên vượt 30s của harness khi chạy cùng hai suite lớn; lượt n2 dùng cùng giới hạn renderer 180s, toàn bộ ba subcase pass trong 99.423s. Không thay timeout production hoặc nới QC.
- Bounded local replay trên dữ liệu restore: 4 thread, 40 exact retry, 200 lần đọc file đã kiểm hash, 0 lỗi, vẫn 2 hàng delivery và chỉ 1 ID được trả về. Thời gian 1.828s; không gọi đây là production soak dài hạn.
- Rehash lại 15 accepted MP4, verify full/incremental Git bundle và CRC backup đều pass. HEAD checkpoint `00631a1388e4ecd27e00e55eb47a604fb0f586b5` khớp upstream; remote main không đổi. [Biên nhận](../evidence/final-export-manual-publishing/baseline/preservation-checkpoint-n2.json) ghi cả WIP test/evidence lúc kiểm.
- P3/P4 đã bỏ giới hạn truy cập âm thầm 100 bản: phân trang theo cursor cho export và caption, có nút xem thêm, kiểm tra workspace/project, giới hạn query và quyền đọc. Test SQLite 105 bản đi qua đủ một lần kể cả trùng timestamp. Đọc caption cũ không hạ latest version để lưu. Đổi project xóa ngay danh sách caption cũ; phản hồi trang cũ đến trễ bị bỏ, bản nháp đang sửa được giữ khi xem thêm.
- P6 Voice Library lưu phiên bản bất biến và journal idempotency theo workspace, CAS, hash, lịch sử, actor và khai báo quyền/consent; không gắn nhân vật vĩnh viễn vào giọng. Quyền mặc định unknown; phiên bản cũ hoặc blocked không qua rights gate. `owner_declared` chỉ là khai báo có tham chiếu, không được gọi là quyền đã được xác minh. Backup/restore giữ cả voice versions và write receipts. UI và API đã nối thư viện, casting và pipeline từng câu; kiểm thử mới dùng mock TTS.
- P6 casting lưu theo project/revision, có nhân vật, lựa chọn version/hash từ thư viện, speaker-tagged lines và narrator mặc định false. Save dùng CAS/idempotency, giữ lịch sử và làm mất approval cũ; cùng voice có thể dùng ở nhiều phim/nhân vật. Draft chưa compile bị chặn trước approval/worker. UI cho phép chọn giọng thủ công, sửa/tách/di chuyển câu, narrator tùy chọn, targeted take và lưu/áp casting của series. Chuyển từ chính sách narrator cũ cần thao tác rõ ràng.
- P6 delivery planner tạo fingerprint từng câu theo workspace/provider config/giọng/text/speed/style/chính sách tên riêng, tách dependency của audio mix và subtitle. Thay giọng một nhân vật chỉ đổi input của câu nhân vật đó; pause/reorder không yêu cầu TTS lại, sửa tên nhân vật chỉ đổi caption input. Narrator off loại đúng các dòng narrator. Cache PCM thực và targeted regeneration đã được kiểm bằng provider tone mock; không suy ra chất lượng lời nói.
- P6 PCM đo WAV PCM16/48k mono, thời lượng thật, activity/clipping/tail; kiểm script/shot/rights/approval trước gọi; riêng từng câu và bản copy private có hash/custody trong SQLite. Đổi giọng hoặc take của một nhân vật chỉ gọi lại câu bị ảnh hưởng; câu còn lại giữ bytes. Có intent trước dispatch, outcome-unknown không tự gọi lại, OS lease/recover, child process thoát thật và backup/restore cache. Đã nối UI/API→compile→worker→canonical timeline/subtitle→preview→render/QC→delivery; chưa có giọng nói thật hoặc Owner voice UAT mới.
- Adapter preset VieNeu local đã có mã chạy child process offline, pin SDK/preset/runtime, seed theo request, chặn voice/language/style/speed không hỗ trợ, yêu cầu EOS và normalize peak bằng gain có ghi nhận. Catalog đọc được 25 preset đã khóa, tất cả mặc định quyền unknown và không chọn giọng sẵn; metadata available không đồng nghĩa runtime/giọng đã được nghiệm thu. Kiểm thử mới chỉ đọc metadata và giả lập transport, không chạy inference mới hoặc khẳng định hai giọng thật.
- Đã lưu [gói kỹ thuật cục bộ và hash](../evidence/final-export-manual-publishing/delivery-package/retained-local-rehearsal.json), cùng [bản backup/restore](../evidence/final-export-manual-publishing/recovery/retained-local-restore.json). Media tổng hợp, approval bằng fixture, không phải 5 case Owner UAT. Lượt rehearsal đầu đặt đường secret vắng mặt bên trong data root nên backup từ chối đúng; n2 sửa riêng config cách ly, không ghi lại video/manifest đã tạo.

## Kiểm thử đã xác nhận

Các tập dưới có overlap; không cộng thành số lượng bài duy nhất.

| Tập | Kết quả | Log trong recovery/20261007 |
|---|---|---|
| API baseline trước sửa | 52 pass / 51.61s | final-export-baseline-API-n1.log |
| Native baseline trước sửa | 32 pass / 196.937s | final-export-baseline-Native-n1.log |
| Shared trailing QC mới | 22 pass / 1.06s, gồm MP4/AAC thật tổng im lặng <30% nhưng tail 3s bị chặn | final-export-tail-n1.log |
| Native quality sau sửa | 32 pass / 147.322s | final-export-quality-Native-n1.log |
| Native delivery | 13 pass / 25.471s, media thật cục bộ, human approval là fixture | final-export-delivery-Native-n2.log |
| HTTP Native có xác thực | 3 pass / 27.082s, download byte thật, role/CSRF/origin/strict fields/folder action | final-export-delivery-http-n2.log |
| UI delivery bằng Node/fake DOM | 15 pass / 110.6928ms | final-export-delivery-Studio-n2.log |
| Full Studio | 2107 pass, 0 fail/skip / 30.597s | final-export-current-full-Studio-n1.log |
| Renderer | 7 file / 48 pass; TypeScript typecheck pass | final-export-renderer-tests-n1.log; final-export-renderer-typecheck-n1.log |
| QC geometry/final freeze | 30 pass / 1.52s, bao gồm bộ trailing trước đó | final-export-aspect-n2.log |
| Cover/recovery/media | 31 pass / 130.477s, có actual images/MP4 và fault injection; tập có overlap với 13/3 trước | final-export-recovery-cover-Native-n2.log |
| Resume và restore | 13 pass / 72.373s | final-export-history-resume-Native-n1.log |
| HTTP + backup regression | 22 pass / 46.315s | final-export-http-backup-Native-n1.log |
| Thoát process thật | 1 pass / 20.475s; owned child exit 86, lease được OS giải phóng, một export được đối chiếu | final-export-process-exit-Native-n1.log |
| UI mở rộng | 20 pass / 150.0543ms | final-export-history-resume-Studio-n2.log |
| Source export settings | 5 pass / 62.517s, có hai ca render thật 24/25 FPS; 21 Node / 234.3394ms; 9 renderer; typecheck pass | final-export-presentation-Native-n2.log; final-export-presentation-Studio-n2.log; final-export-encoder-renderer-n1.log |
| Narrated export + HTTP | 8 pass / 105.517s, có preview/render/QC/SRT thật cục bộ; 27 Node pass / 156.0184ms | final-export-narrated-variants-Native-n4.log; final-export-narrated-settings-Studio-n1.log |
| Full Studio hiện tại | 2119 pass, 0 fail/skip / 34129.3777ms | final-export-current-full-Studio-n2.log |
| Frame đen + quality gates | 32 pass / 2.96s, gồm MP4 thật có 1 frame đen bị chặn; tập chứa lại tail/aspect/freeze | final-export-black-qc-n2.log |
| Canonical + source export regression | 39 pass / 316.667s: shot adapter, source encoder actual media, narrated visual timeline | final-export-canonical-regression-Native-n1.log |
| Render restart thật | 2 pass / 148.148s: owned child exit 87 giữa render và exit 88 sau checkpoint; giữ đúng job và một delivery | final-export-render-recovery-Native-n1.log |
| Tất cả hình học, gồm square 60 FPS | 1 test / 3 subcase pass / 99.423s, có preview, final render, QC và delivery thật | final-export-all-shapes-Native-n2.log |
| Full renderer hiện tại | 7 file / 52 pass / 5.35s; TypeScript typecheck pass | final-export-renderer-full-n2.log; final-export-renderer-typecheck-n2.log |
| UI nhãn phục hồi | 27 pass / 159.3143ms; history phân biệt đã ngừng và thư mục bị mất | final-export-history-label-Studio-n1.log |
| History pagination Native/HTTP | 9 pass / 107.661s, SQLite + signed HTTP, 105 exports/105 caption versions, scope/query/read-role/CAS | final-export-history-pagination-Native-n2.log |
| History pagination UI | 31 pass / 161.3651ms; có late response và unsaved draft | final-export-history-pagination-Studio-n2.log |
| Full Studio sau pagination | 2123 pass, 0 fail/skip / 32767.9766ms | final-export-current-full-Studio-n3.log |
| Voice Library + backup | 26 pass / 18.718s: 9 library + 17 backup, SQLite/restore thật, không có TTS | final-export-voice-library-Native-n1.log |
| Casting + kế hoạch + regression | 57 pass / 57.894s: 9 casting, 9 dependency-plan, 9 library, 17 backup, 13 storyboard QC; các component dùng fixture, không TTS drama | final-export-drama-casting-plan-Native-n3.log |
| Dialogue PCM/cache/recovery | 62 pass / 21.132s: 18 audio + 9 library + 9 casting + 9 plan + 17 backup; WAV thật với tone mock, child exit 89, không giọng thật | final-export-dialogue-audio-recovery-Native-n3.log |
| Local preset adapter | 24 pass / 14.061s: 6 metadata/transport + 18 PCM; transport giả, đọc SDK thật, 0 inference mới | final-export-dialogue-local-adapter-Native-n1.log |
| Compiled dialogue + backup | 29 pass / 11.339s: 10 compiler + 19 backup, không dispatch TTS, không cấp Owner approval | final-export-dialogue-binding-Native-n2.log |
| Dialogue runtime + components | 68 pass / 63.617s, có PCM/cache, duyệt narration-only, áp canonical timeline, audible preview, render/QC, ASS/SRT speaker và manual package; giọng là tone mock | final-export-dialogue-runtime-Native-n2.log |
| Legacy sau dialogue bridge | 40 pass / 111.933s: narration, audible preview, canonical captions, manual delivery và workflow; không đổi accepted profile | final-export-dialogue-legacy-regression-Native-n1.log |
| Compiler bổ sung | 11 pass / 3.331s, gồm shot tắt lời đọc vẫn giữ draft text | final-export-dialogue-binding-Native-n3.log |
| Take theo câu + series | 36 pass / 11.569s: 8 take/series, 19 backup, 9 casting; server cấp nonce, exact retry, giữ câu/giọng khác và lịch sử | final-export-dialogue-reuse-Native-n1.log |
| Native HTTP/UI bridge và stale voice | 36 pass / 67.023s: signed HTTP/RBAC/CSRF, canonical script sync, explicit legacy policy conversion, selected-line/series/runtime, media delivery và module transport | final-export-drama-Studio-Native-n4.log |
| Voice Studio controls | 20 pass / 137.4011ms: literal text, explicit voice/speaker selection, exact retry, foreign receipt, separate drafts, stale preview/render and unsupported provider edit fence | final-export-drama-Studio-n3.log |
| Full Studio sau P6 | 2143 pass, 0 fail/skip / 28965.5272ms | final-export-current-full-Studio-n6.log |
| Native quality/legacy regression sau P6 | 71 pass / 159.212s: narration, preview, captions, delivery, workflow, backup, proper names/quality and narrated export settings | final-export-drama-quality-regression-Native-n2.log |
| Renderer hiện tại sau P6 | 7 file / 52 pass / 10.92s; TypeScript typecheck pass | final-export-renderer-full-n3.log; final-export-renderer-typecheck-n3.log |
| QC cửa sổ lời thoại/người nói + legacy | 64 pass / 160.451s; actual canonical caption move, RMS line timing, preview/render/package, recovery and legacy gates | final-export-dialogue-cue-qc-Native-n3.log |
| QC pin/schema + runtime bổ sung | 15 pass / 42.910s; gồm actionable error và ràng buộc evidence | final-export-dialogue-cue-qc-Native-n4.log |
| API fixture closure: CPU/storage/W1/auth | 58 pass / 87.57s; production guards giữ nguyên, HTTP provider giả lập, đọc local thật | final-export-api-fixture-closure-n5.log |
| API fixture closure: quyền/variant/rebuild/service | 58 pass / 226.74s; các nguồn color/sine tự tạo khai báo quyền rõ ràng, child vẫn unknown | final-export-api-fixture-rights-n2.log |

Studio baseline 66 lỗi do hàm kiểm tra dùng wall clock thay vì clock fixture. Đã sửa riêng injection clock trong harness, không nới kiểm tra phiên production. Full 2092 bài cũ và full 2107 bài có export đều pass.

Full API ban đầu bị chặn collection 5 module trên Windows: thiếu NumPy ở SQL venv, thiếu websockets và Unix `grp`. Không sửa runtime đã khóa hoặc giả module hệ điều hành. Lượt tương thích (loại rõ 5 module trên) đã kết thúc: **4139 pass, 37 fail, 17 error, 63 skip / 6513.19s**, `final-export-compatible-API-n2.log`. Đã phân loại và đối chiếu baseline; nhiều lỗi liên quan getuid/O_NOFOLLOW/POSIX custody, thiếu yaml hoặc symlink privilege, các lỗi còn lại chưa được tự quy thành môi trường. Không gọi đây là full pass. Full Native đã kết thúc và các lỗi đã được chạy lại như ghi bên dưới. Hai lượt rộng được khởi chạy trước phần mở rộng cover/recovery và QC geometry; kết quả không tự chứng nhận những phần được thêm sau lúc khởi chạy. Docker/Linux E2E và toàn bộ Phase 8/9/10 acceptance chưa được tái chứng nhận ở chương trình này.

Đối chiếu đã hoàn tất cho 11 lỗi ngoài nhóm Linux executor/custody: cả 11 tái hiện ở HEAD trước chương trình Export, thêm 5 ca kiểm tra authorization trước body pass. [Phân loại đầy đủ và giới hạn](FINAL_EXPORT_REGRESSION_STATUS.md). Checkout baseline tạm đã kiểm tra sạch và dọn bằng Git, thu hồi 703169497 byte; không đụng checkout nguồn chính hay accepted videos. 26 fail và 17 setup error thuộc nhóm môi trường/POSIX vẫn chưa được chứng nhận trên Linux. Full regression chưa đạt.

11 lỗi fixture API cũ đã được đóng bằng hai cohort 58/58 phía trên tại commit `6150047a`; không đổi source production hoặc nới quyền/auth/storage. Full Native mới đã được discover đủ 2285 case và chia disjoint thành 4 tiến trình (572/571/571/571), với source tree được pin trước/sau. Kết quả của lượt đang chạy chưa được tính là pass. [Hồ sơ fixture](../evidence/final-export-manual-publishing/baseline/api-fixture-closure.json).

Full Native đã kết thúc: 2156 bài / 7802.239s, 3 fail và 14 error. Đã chạy lại trên nguồn hiện tại và đóng các 17 ca lỗi bằng cohort **38 pass / 302.792s** (`final-export-native-regression-closure-n1.log`), kèm backup/static regression. Không gọi đây là một full run mới. Hai lỗi 404 do map route cũ trong process dài đọc UI mới; fixture capability được cập nhật ba field Export mới. Legacy restore đã hỗ trợ thiếu đúng optional ASR path bằng sentinel tuyệt đối không tồn tại; không mặc định bí mật/đường bắt buộc và không bật provider. Checksum hai archive cũ giữ nguyên. [Chi tiết](FINAL_EXPORT_REGRESSION_STATUS.md).

Lượt `final-export-narrated-settings-regression-n2.log` có 38 test chạy qua nhưng gọi nhầm thêm module không tồn tại `test_shot_timeline`, nên toàn lượt không pass. Đã sửa lời gọi bằng module thật `test_shot_adapter` ở cohort canonical 39 pass phía trên; không che lỗi gọi test bằng cách đổi mã production.

## Phần còn phải hoàn thành trước khi đánh dấu ready

| Ưu tiên | Trạng thái | Còn thiếu |
|---|---|---|
| P1 | PARTIAL | Bộ quality/cache-invalidation tổng hợp, các ca đích thật và kiểm tra tên/giọng bằng người |
| P2 | PARTIAL | Source và storyboard có prepared narration đã có FPS/quality/burn-in/audio gắn preview/render; còn video watermark khi cấu hình và UI acceptance 1366/1920/2560 |
| P3 | PARTIAL | Các chức năng cover/copy đã có và được kiểm thử cục bộ; còn UI acceptance thực tế, quyền nội dung và bundle UAT đích |
| P4 | PARTIAL | History/thumbnail/compare/recreate đã có; còn UI acceptance thực tế và các ca đích |
| P5 | PARTIAL | Render restart giữa/sau checkpoint, handoff/collision/tamper/disk error/backup-restore và bounded concurrency đã có bằng chứng; còn tổng regression và vận hành/UAT |
| P6 | PARTIAL | Library/casting/planner/cache/adapter, targeted take, series và UI/API→compiled approval→worker→canonical playback/subtitle→final QC→delivery đã có bằng chứng mock/local media; còn UI visual review và real voice/Owner acceptance |
| P7 | PENDING_OWNER_UAT | 5 case Owner UAT; không tự ghi nhận nghiệm thu |

Các preset 4 hình học có hard validation; gói phải khớp video đã duyệt. Đổi format từ Export Center áp dụng lại cấu hình dự án và cần preview/duyệt mới; video nguồn còn hỗ trợ FPS/quality/burn/audio. Không transcode âm thầm một MP4 đã duyệt thành file khác. Thư mục đầu ra do Native quản lý; chưa có chọn thư mục tùy ý. Không ghi những tùy chọn chưa hỗ trợ thành đã hoàn thành.

Quan sát browser từng bị URL policy từ chối; Node/fake DOM và HTTP không thay cho quan sát UI hoặc Owner UAT. Không dùng browser/CDP khác để vượt chặn. Dọn cache từng bị policy từ chối cũng chưa thực hiện; dữ liệu và artifacts vẫn giữ nguyên.

## Trạng thái công bố

`FINAL_VIDEO_QUALITY_READY = NO`  
`EXPORT_CENTER_READY = NO`  
`DELIVERY_PACKAGE_READY = NO`  
`EXPORT_HISTORY_READY = NO`  
`DRAMA_VOICE_CASTING_READY = NO`  
`OWNER_EXPORT_UAT_COMPLETE = NO`  
`OWNER_VOICE_UAT_REQUIRED = YES`  
`PLATFORM_API_PUBLISHING = DEFERRED`  
`ANALYTICS = DEFERRED`  
`FULL_TREND_RADAR = DEFERRED`  
`PRODUCTION_DEPLOYED = NO`

Owner action hiện không cần cho các phần cài đặt an toàn đang chạy. Listening và UAT vẫn để Owner xem sau theo chỉ đạo trước. Không merge main, không deploy production, không gọi API đăng bài, không mở rộng analytics/winner/learning/trend.

## Điểm review cục bộ

Bản Studio kiểm thử riêng đang chạy tại **http://127.0.0.1:62684/native.html** trên máy này, mã nguồn `a01dbd6eff8d744ad262949dc0f5ce839fdc96ba`. Dữ liệu là bản restore riêng của rehearsal tổng hợp; không phải dự án production hoặc ca NPD/giọng thật đã nghiệm thu. Đã kiểm HTTP source bytes, capability và tải MP4 từ export history với đúng SHA256. Không quan sát bằng browser và không ghi nhận Owner UAT. Phiên n1/port 61248 đã ngừng trước khi thay code QC; dữ liệu của nó được giữ nguyên.

Chỉ core worker được khởi động. Publication/OAuth/analytics/provider-sync, scheduler/bridge/trend/generative workers không chạy trong phiên review này; credentials trả phí vắng mặt. Dữ liệu ở `C:/vfct/final-export-review-n1`, PID thực `20824`. Năm ca UAT đích còn phải chuẩn bị/duyệt; [kế hoạch Owner UAT](../evidence/final-export-manual-publishing/owner-uat/README.md).

Nguồn implementation đã push và có incremental bundle n6 tại `C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/final-export-focus-progress-n6.bundle`: 225343 byte, SHA256 `49f6a4ce90284013c04a0e4666e7c0192bce6863f38730643135a2a2ea49e0e8`, pin code `a01dbd6e`, cần full baseline bundle và commit `4162bc32260521277737f7c9ee118b5ba55b3f9b`. Fixture/report sau checkpoint được ghi riêng; không ngụ ý nằm trong bundle n6. Cả 15 accepted MP4 được rehash, không đổi; source live `C:/NPD-Video-Factory/source` vẫn sạch tại `2ced7bc81f9402368fb22c9e7aca242e740531af`.
