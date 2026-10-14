# SQL Video Word Review, canonical audio và cấu hình xử lý nguồn

Đã tích hợp panel sửa từng từ vào Studio, private video nguồn chỉ đọc, canonical PCM dùng chung giữa review/final, và API cấu hình normalization/ducking vào ứng dụng chính. Source parent của tài liệu: `721c52a7e9222c2496779dabcdb460f7720114e3`. Giao diện cấu hình xử lý âm thanh SQL còn đang triển khai riêng; chưa coi full Mode A/B hoặc Artifact A/B/C hoàn tất.

## Transcript, timeline và video nguồn

Word UI dùng transcript đã lưu, giữ thời gian nguồn không làm tròn, lịch sử gốc/sửa và nullable confidence của quyết định người sửa. Lưu dùng atomic transcript/timeline CAS; timeline và preview/approval cũ phải được kiểm tra lại. Không chạy ASR mới, tự ước lượng thời gian, chuyển approval hoặc thay video gốc. Controller chốt workspace/project/source/canonical timeline/principal và literal token sau các await/storage callbacks; UNKNOWN giữ đúng body/key/token SHA, không ghi plaintext token, tự rebase, ghi đè/xóa bản ghi khác hay nhận phiên cũ. Storage tùy biến cần trusted synchronous compare-remove; thiếu primitive thì giữ yêu cầu để đối chiếu.

Studio refresh sau receipt kiểm tra timeline hiện tại và lịch sử cùng project/ID/version/snapshot. Peer phát hiện history cao hơn timeline bị chấp nhận; đã sửa và giữ repro. Browser thật phát hiện demand token_id không có trong public auth/session DTO; bản sửa chỉ bỏ demand trường không công khai, giữ subject/role/expiry và token fences, không thêm token giả vào server. Public DTO sáu trường được actual main test xác minh.

Private GET/HEAD video nguồn xác thực viewer trước dữ liệu, đọc metadata/source snapshot thống nhất, kiểm scope/checksum/size/magic/object custody trước và sau IO, có no-store/range/ETag và bounded cancellation/drain. Rights unknown có thể đọc để review nhưng vẫn chặn publishing. Test header-MP4/typed child không thay cho kiểm decoded quality hoặc cloud/PG acceptance.

## Browser thật và giới hạn bằng chứng

N1 source `8790d37` bị khóa Word Read do contract token_id; lưu ảnh/DOM, 80 HTTP, 0 mutation, không ghi UI PASS. N2 source `2b4dc41` đọc được 23 từ, lịch sử v1 gốc có confidence và v2 sửa không có confidence, tải Blob khớp video 411.042 byte/SHA. Player paused, readyState4, 11,34 giây, 640×360; seek browser 1,359999 giây trong khi input gốc 1,359999999999999 được giữ nguyên.

Ở 1366/1920/2560, cả video và form không tràn ngang; font nút14px/radius7px. Ack=false/saveDisabled=true, không sửa/nhấn lưu hay xác nhận đã nghe. N2 có 83 HTTP=82GET+1HEAD; 80×200, 1×401 kiểm unauth và 2×404 kiểm endpoint/favicon. Source416 file/helper/HEAD, hai seed, SQL87 bảng/toàn bộ rows/SHA và một object giữ nguyên; host/PID/listener đã đóng. Server token chỉ ở RAM; shipped auth.mjs lưu synthetic expiring login token trong sessionStorage, controller UNKNOWN chỉ lưu SHA. Không có token/bootstrap trong archive.

Video dùng hình card synthetic với lời nói public FLEURS đã được ASR CPU thật ở lần chạy trước, cùng editorial v2 tự động phục vụ test. Không coi là genuine uploaded footage Artifact A, listening quality, Owner UAT hoặc full Mode B acceptance. Root independently kiểm historical source Git/EOL, archive36entries, clone bằng seed, video/hash và retained failed N1. Verifier đầu từ chối mixed EOL; N4 dùng exact physical SHA rồi canonical normalization, không viết nguồn. Không đổi nhãn source của media cũ thành HEAD mới.

## Canonical audio và service API

Production audio dựng từ original/voice/music/sfx trên canonical timeline: trim/tempo/gain/fades, measured source clock, normalization trước gain, ducking theo năng lượng audio thật và limiter. Receipt chốt clip graph, source/snapshot/configuration, PCM48kHz stereo/sample/byte/SHA. Final dùng đúng PCM được duyệt; PoisonDSP/TTS fixtures xác nhận không trộn/đọc lại. Raw narration premix được giữ riêng. Missing old canonical proof yêu cầu review mới, không tự nâng acceptance. Same-transaction terminal guards giữ cancellation/source-change và không để QC exception ghi đè terminal trước.

Root phát hiện limiter -3dB cấu hình nhưng graph/receipt -1dB ở nhánh no-legacy-base; đã sửa wrapper, giữ proxy defaults -1dB. Real bounded high-peak PCM kiểm -3/-0,1dB ở cả hai nhánh. Test reference từng thiếu giới hạn làm đầy C:; đã dừng đúng owned processes rồi xóa duy nhất WAV test không hợp lệ2.673.868.800byte. Product PCM768.078byte và product -t/-fs được giữ nguyên; reference sửa -t/-fs/timeout, không đổi guard sản phẩm.

Private `/v1` playback cần scoped service grant và human viewer đã xác thực thật; không mint human identity từ service. Final `/v1/render` dùng chung business command đã kiểm approval/current-QC với verified service actor; UI route vẫn yêu cầu human editor. Approval và publish vẫn yêu cầu con người riêng. Signed orchestration upload→analysis→timeline→preview→approval→final→dry-run đạt trong fixture flow; ASR/DSP/render/QC/approval/publication đều được gắn nhãn mô phỏng, không coi provider acceptance.

## API cấu hình xử lý âm thanh SQL

GET/PUT `/api/v1/projects/{project_id}/timeline/audio-processing` đã đăng ký main. GET đọc canonical config/receipt/locked audio tracks không mutation; defaults từ shared engine, ba tùy chọn mặc định false, duck_threshold0,02. PUT strict9fields, boolean/số hữu hạn/range/extra/ack, expected timeline ID/version và request key; actor từ verified human principal. Viewer đọc, editor sửa; workspace scope và emergency writes switch được giữ. Chỉ thay metadata.source_audio_processing, dùng existing version/history/invalidation transaction; không DDL/model/provider/render/queue.

Conditional SQL reservation ngăn concurrent same-parent overwrite. Replay chỉ đúng key/actor/body/parent/result/currentreceipt/config; receipt đã superseded trả409. Late flush/cancel rollback giữ versions/events/assets/cost/usage/approval/package/preview/render. Legacy metadata None đọc defaults không ghi. Processing metadata đi vào shared proxy/canonical production graph; tests ở đây là graph planning trên explicit nonplayable contract, không DSP/âm thanh thật. Studio processing form/peer locks/UNKNOWN reconciliation còn đang triển khai.

| Batch có source riêng | Bằng chứng và giới hạn |
| --- | --- |
| Full Studio1093 PASS /0FAIL /0SKIP tại2b4 | Gồm43 Word module và37 shell; Node fixture/actual historical DTO, không browser/provider toàn bộ. Peer5 overlap, không cộng. |
| Source playback70 PASS tại author6a305 | 41new+29existing actual SQLite/ASGI/header-media contracts; root11 overlap. N2 đọc object thật riêng. |
| Canonical audio N1:28core PASS/5adjacent FAIL | Giữ batch33 lịch sử; các failure auth/S5 fixture xử lý riêng, không gọi33PASS. |
| Canonical audio N2:selected9 PASS; root9 PASS | 4new bounded real PCM limiter và5affected; root9 có terminal/custody/PoisonDSP proof, overlap; chưa full32 rerun. S5fixture5PASS riêng. |
| Private service auth12 PASS; peer8cases | Actual signed ASGI/SQLite auth + bounded fake bytes delegate; không decoded media. |
| Service final10 PASS; root4 overlap; integration1 PASS | Signed/SQLite/queue/guard real; model/audio/visual/QC/approval/publication fixtures/dry-run. |
| Processing backend30 PASS; main5 PASS | Actual isolated SQLite/ASGI/CAS/concurrency/rollback/auth; graph-only contracts, không PG/media/DSP/provider. Reviews độc lập static + log/hash,0reviewer rerun. |

Các failure fixture/harness/503/repro/raw-source được giữ, không cộng selected/rerun thành một full run. Adjacent old preview fixture thiếu read_source_snapshot vẫn mở, không nới guard. Word source0byte do C:full được dựng lại về logic từ các bản nguyên vẹn và rerun; không tuyên bố khôi phục byte N5 không có hash. Sourceinventory giữ narrow raw fixture .gitattributes; ASGI capture0CRLF, manifest53CRLF được mô tả đúng, không thay dữ liệu capture.

## Phục hồi và công việc tiếp theo

Index [video-word-canonical-audio-evidence.json](north-star/video-word-canonical-audio-evidence.json) giữ từng source/log/review/archive/hash. Media42,8MB/295entries/285actual files và full base Git bundle được tham chiếu riêng. Ba worktree hoàn tất, clean, bundled đã retire không force; giải phóng2.137.174.016byte thực, giữ branches/artifacts/nguồn/model và production. Không xóa accepted media hay seed. Fresh source recovery seal kiểm protected main/live tree và15 accepted artifact hashes.

SOURCE_PRESERVED=YES; PHASE10_TECHNICALLY_READY=YES; OWNER_UAT_REQUIRED=YES; PHASE10_READY=NO. Matrix5IMPLEMENTED_REAL/58PARTIAL/1NOT_VERIFIED;59 nhóm rộng chưa đóng, không phải59 việc nhỏ hay tỷ lệ tiến độ. IMPLEMENTATION_COMPLETE=NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO; VIDEO_FACTORY_NORTH_STAR_READY=NO. Optional listening/Owner UAT đang deferred; không cần Owner action hiện tại.

Tiếp tục SQL processing UI/config review và preview/final parity, sửa regression fixture còn mở, genuine uploaded full Artifact A, original Mode A/B/C bundles và toàn bộ gaps Waves3–16. DockerCLI vẫn thiếu, Docker stack/soak chưa kiểm; credentials/rights/Owner/deployment acceptance tách riêng, không ngăn safe implementation. Không merge main, publish thật, deploy hay dùng paid budget mới.
