# POST INTERNAL PRODUCTION — PHASE 9

Ngày báo cáo: 06/10/2026, giờ Việt Nam.

Content Intelligence đã đi từ nghiên cứu có nguồn tới năm MP4 mới qua pipeline Windows Native hiện có. Owner đã duyệt năm brief, năm lời đọc v2 và storyboard/media/quyền sử dụng của 01/02/04/06/08. Năm video dùng giọng Thùy Dung tạo mới tại PC, đủ 11/11 kiểm tra kỹ thuật, toàn vẹn tệp và lineage. Dữ liệu mở lại đúng trong tiến trình mới. Điểm dừng: **PHASE9K_FINAL_HUMAN_WATCH_LISTEN_REVIEW_REQUIRED**, còn 0/5 quyết định xem/nghe cuối. Phase 9K chưa PASS.

INTERNAL_PRODUCTION_READY = YES

**Release và SHA**

- Branch: codex/vf-post-mvp-roadmap-execution-01.
- Baseline SHA: f61d8de6545653ea46f8ab5f91e6c0c0c167b7af.
- Release marker: annotated tag internal-production-v1, giữ nguyên baseline và lịch sử.
- Final SHA của mã ứng dụng đã kiểm thử và đang chạy: 9ce137afa8ac62fdb8ce5b35fbba997013adfef3.
- Final SHA của checkpoint kỹ thuật, năm MP4 và bằng chứng sản xuất: a44bb0dd234e4c620dd394d18e7a9112be62f988.
- Commit tiếp theo chỉ cập nhật báo cáo; SHA của chính commit báo cáo được xác định trong Git history và lời bàn giao. Đây là checkpoint, chưa phải human acceptance cuối Phase 9.

Các commit tiến dần: freeze 8f0aacc; domain 2d819c9; engines/profiles 3d1c391; Studio/bridge 3cd4aaf; Windows sources fc986b0; kỹ thuật/10 ca 7c13e2a; brief-duration instructions bf4ec72; năm brief/handoff e4ee6c2; năm script thật 4b2f67f; v2/restart 8ad8346; script review riêng 2980fdf; 25 đồ họa/lineage cee0eab; Owner media receipts/approval provenance 9ce137a; năm video thực tế a44bb0d. Checkpoint cũ giữ theo thời điểm.

[Release baseline](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/release-baseline.md) và [manifest](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/release-baseline.json) lưu dependency inventory, schema, SHA và nghiệm thu 10 video Phase 8.

**Subphase**

| Phase | Trạng thái | Bằng chứng |
|---|---|---|
| 9A — Freeze | PASS | Exact baseline, annotated tag, consistent backup |
| 9B — Domain | PASS kỹ thuật | Tám canonical models, version/provenance/history |
| 9C — Research | PASS phạm vi URL nguồn | Truy xuất thật, quotes/receipts/timestamps/hashes |
| 9D — Ideas | PASS kỹ thuật và actual provider | Bộ ban đầu 10 lần sinh hợp lệ, mỗi lần năm ứng viên |
| 9E — Scoring | PASS kỹ thuật | Mười components, configured weights, rationale, HEURISTIC_SCORING |
| 9F — Review | PASS triển khai/kiểm thử; brief/script/media 5/5 | Chọn/sửa/bỏ/tạo lại và duyệt trước production; final review chờ |
| 9G — Existing pipeline | PASS tích hợp và production 5/5 | Brief → script v2 → assets → Native TTS/editor → MP4, lineage giữ nguyên |
| 9H — Profiles | PASS | Bốn profiles cấu hình; mix 10 ca 3/2/2/3 |
| 9I — Queue | PASS kỹ thuật | Sáu trạng thái; năm ca IN_PRODUCTION, chưa PRODUCED |
| 9J — Tests | PASS trong phạm vi ghi rõ | 134 Native + 32 Studio; actual video verification riêng |
| 9K — Acceptance | PHASE9K_FINAL_HUMAN_WATCH_LISTEN_REVIEW_REQUIRED | 5/5 new MP4/QC/integrity/persistence; 0/5 human final |

Các trường báo cáo subphase nằm trong [domain-model.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/domain-model.md), [engines-and-profiles.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/engines-and-profiles.md), [studio-pipeline-and-verification.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/studio-pipeline-and-verification.md), [handoff matrix](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/phase9k-handoff-matrix.md), và [real production checkpoint](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/real-production-checkpoint.md).

**Architecture additions**

ResearchSource, ResearchFinding, TrendSignal, Opportunity, ContentIdea, ContentBrief, IdeaScore và ResearchRun có stable ID, created_at, updated_at, version và provenance. Giá trị kinh doanh nằm trong cấu hình. Intelligence database riêng C:\NPD-Video-Factory\phase2\intelligence.sqlite3, schema 1, lưu history, human decisions và operation receipts. Production schema giữ nguyên; lineage content-intelligence-lineage-v1; canonical timeline 1.1.

ResearchProvider nhận query/context và 1–5 URL HTTPS công khai do người dùng hoặc cấu hình cung cấp. Nó lưu nguồn, trích đoạn, query, receipt, timestamps, provider metadata và SHA. Findings phân biệt SOURCE_REPORTED, INFERENCE, UNRESOLVED. Source-reported chưa phải xác minh độc lập. Retrieval date không thay publication date; unknown giữ nguyên. HTTP/size/parse/grounding failures explicit, không tạo nguồn thay thế.

IdeaProvider tái dùng gpt-6-luna và credential đã tồn tại để sinh năm ứng viên. References phải thuộc source/finding đã lưu; angle/hook/rationale là đề xuất biên tập. Bộ 10 ca ban đầu có 13 phản hồi thực tế: 10 hợp lệ và ba bị từ chối vì references. Ledger này giữ phạm vi lịch sử. Scoring lưu mười dimensions, weights cấu hình, component/final scores, rationale, thời điểm/config hash; HEURISTIC_SCORING không dự báo thống kê lượt xem/lead.

Studio có [Nghiên cứu & ý tưởng](http://127.0.0.1:8026/intelligence), Opportunity Queue, chọn/sửa/bỏ/tạo lại ý tưởng, sửa/duyệt brief và explicit handoff. Sửa candidate/brief làm mất hiệu lực duyệt cũ và giữ history. Handoff tạo project để review script, không tự sản xuất. Research → idea → approved brief → script → storyboard → job/timeline/render giữ lineage/source hashes. Pipeline Phase 1–8, TTS/media/editor/preview/final review được tái sử dụng.

Ca 01 có generation/brief khác do Owner tạo và handoff trước task 9K. Task lấy Rank #1 hiện tại qua retained-research fork có original IDs, nguồn/timestamps/hash gốc; không gọi source/idea provider thêm. Project, approval và 19 record của run cũ cùng toàn bộ history được giữ.

Năm content jobs nhận năm phản hồi script thật, mỗi job một call; request/response/result/model/usage/IDs/hashes giữ nguyên. V2 biên tập từ v1, lưu bằng Native Store, không gọi provider thêm. Reply “Duyệt v2: 01, 02, 04, 06, 08” tạo năm SCRIPT_ONLY events ràng buộc narration và lineage. Sửa narration/lineage làm approval hết hiệu lực; sửa hình không tự sửa script approval.

Reply mới “Duyệt storyboard/media: 01, 02, 04, 06, 08” ràng buộc bộ 25 cảnh đã gửi. Đã nhập đúng 25 PNG, giữ byte gốc và tạo JPEG derivative bằng ingest Native. Asset provenance lưu recipe/font/source/script/Owner receipt hashes. Năm project lên revision 9, giữ lời đọc v2, five scenes/contain/no motion/source-start 0/fade, không nhạc. Approval snapshots và reviewed storyboard v3 giữ nguyên; current storyboard v5 ghi measured timing/job/output, không thay bundle đã duyệt.

Native Store.approve thêm optional review_reference để ghi đúng source human_user_reply_in_codex và authorization hash. Existing calls/UI/schema không đổi; invalid reference bị từ chối, approval không tự dispatch. Helper gọi approval/enqueue hiện có sau reply thật. Runner tuần tự tạo 43 local TTS inferences mới, speed preset 1, 0 retries, network blocked, rồi FFmpeg render. Không thêm provider/credential hoặc pipeline video thứ hai.

**Tests và verification**

| Kiểm tra | Kết quả |
|---|---|
| Native unit/integration/persistence/provenance/failure suite | 134/134 PASS sau application change cuối; hai tests mới cho chat review reference và rejection/no-auto-dispatch |
| Studio suite | 32/32 PASS; UI không đổi sau lần chạy này |
| Actual research/ideas | 10 ca/50 ứng viên hợp lệ ban đầu; provider integrations phân loại riêng |
| Human brief/script/media decisions | 5/5 từng bước, exact versions/hashes/source receipts |
| Actual local TTS | 5/5 fresh jobs, 43 calls, 0 retries; không dùng fixture voice hoặc Phase 8 audio |
| Actual MP4 ffprobe/QC | 5/5, 11/11 mỗi video: portrait 1080×1920, H264/AAC, 30fps, yuv420p, 48kHz, full decode, finite audible audio, no clipping/black intervals, complete duration/A-V alignment |
| Artifact/source/lineage integrity | 5/5 PASS, exact MP4/voice/snapshot/source hashes và selected assets |
| Live preview/seek/final guard | 5/5 byte-exact MP4, range seek; final endpoint HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED |
| Project persistence/fresh-process reopen | 5/5 PASS; DDL/table hashes của hai database và project/approval/job/MP4 state khớp checkpoint trước |
| Main-service restart sau render | NOT_PERFORMED_POLICY_BLOCKED; không ghi PASS. Actual restart checkpoint trước vẫn có evidence |
| Visual inspection | Codex xem 25 sampled actual frames qua năm contact sheets và hai cảnh đầy đủ; không thay Owner watch/listen |
| Human final watch/listen | 0/5; PENDING |

[134 Native tests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/native-tests-production.log), [32 Studio tests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/studio-tests-storyboard.log), [actual production verification](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/actual-production-verification.json), [fresh-process persistence](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/real-video-fresh-process-reopen.json), [preview/final guards](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/actual-video-preview-http-verification.json), [visual scope](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/actual-video-visual-review.json).

Earlier fixture E2E covers research → five ideas → scores → selection → brief → Native render/guards with labelled test providers/decisions. It is not actual provider PASS or human acceptance and contributes zero videos to this gate. The five new production MP4s are distinct fresh actual jobs.

**Practical cases và human acceptance**

| Ca | Profile | Chủ đề | Ý tưởng ban đầu | Owner/current state |
|---|---|---|---:|---|
| 01 | Green Paradise | Thỏa thuận IHG | 5 | Brief/script/media APPROVED; new MP4; final PENDING; old project preserved |
| 02 | Green Paradise | Khởi động chứng nhận đô thị thông minh | 5 | Brief/script/media APPROVED; new MP4; final PENDING |
| 03 | Green Paradise | Hạ tầng/giới hạn suy luận | 5 | Unselected/PENDING |
| 04 | Saigon Park | Ba câu hỏi tìm hiểu dự án | 5 | Brief/script/media APPROVED; new MP4; final PENDING |
| 05 | Saigon Park | Văn phòng/sa bàn/trạng thái | 5 | Unselected/PENDING |
| 06 | Vang Nguyễn | Ngày đăng/kỳ báo cáo/hiện tại | 5 | Brief/script/media APPROVED; new MP4; final PENDING |
| 07 | Vang Nguyễn | Giá bình quân/giá một căn | 5 | Unselected/PENDING |
| 08 | Việt Nam | Giao dịch/nguồn cung/tồn kho Q2/2026 | 5 | Brief/script/media APPROVED; new MP4; final PENDING |
| 09 | Việt Nam | Tin giá nhà/ngân sách | 5 | Unselected/PENDING |
| 10 | Việt Nam | Đề xuất nhà giá rẻ/trạng thái chính sách | 5 | Unselected/PENDING |

Bảy tiêu chí từng ca nằm trong [practical-editorial-assessment.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/practical-editorial-assessment.md); nhận xét Codex không phải human acceptance hoặc đánh giá thống kê hiệu quả ranking. Các giới hạn hook/rank/duplicate/date được giữ. Năm lựa chọn Owner có brief/script/media decisions thật; các ca còn lại chưa được task này duyệt.

| Ca | MP4 mới | Thực tế | Mục tiêu | TTS calls | QC/integrity/persistence | Human final |
|---|---|---:|---|---:|---|---|
| 01 | [Xem/nghe](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/case-01/final.mp4) | 34,17s | 30–45s | 8 | PASS | PENDING |
| 02 | [Xem/nghe](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/case-02/final.mp4) | 40,47s | 45–60s, ngắn hơn | 8 | PASS | PENDING |
| 04 | [Xem/nghe](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/case-04/final.mp4) | 36,04s | 45s, ngắn hơn | 10 | PASS | PENDING |
| 06 | [Xem/nghe](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/case-06/final.mp4) | 36,74s | 45s, ngắn hơn | 7 | PASS | PENDING |
| 08 | [Xem/nghe](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/case-08/final.mp4) | 47,23s | 45–60s | 10 | PASS | PENDING |

02/04/06 chưa đạt thời lượng mục tiêu. Lời đọc v2 và speed preset được giữ nguyên; technical QC chứng minh video hoàn chỉnh theo measured audio. Owner cần chấp nhận thời lượng thực tế hoặc yêu cầu sửa, không tự đổi narration/speed để che khác biệt.

**Evidence và screenshots**

Idea/brief bundle SHA 1ac01b244e396e3d53f76197b1c475e134275fd2c605463981fc3048ba5872e4; script v2 bundle SHA ba8f2a4572497fe59ece072f767d0d0a54f668304ebb090cfb9338d1bb287d1c; storyboard/media bundle SHA d9fe7af9329c5bc293a155b9f152fdd65730e3f1b6f83bb65149291a81ac7000. Tất cả giữ byte gốc.

[Owner media authorization](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/owner-media-authorization.json), [production snapshots](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/production-approval-manifest.json), [bộ năm video cuối](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/final-video-review-bundle.md), [exact MP4 review manifest](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/final-video-review-manifest.json), [final review register](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/phase9k-final-review.md).

![Studio thật với video mới và final review chưa xác nhận](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/actual-videos-native-studio.png)

![Năm cảnh trích từ MP4 ca 08 thực tế](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/case-08/actual-video-contact-sheet.png)

Native screenshot ca 01 thể hiện MP4 mới/34,2s/QC và ô xem/nghe chưa tick. 25 actual frames được trích từ MP4 mới. Static gallery cũ là historical storyboard preview; browser chặn file URLs nên không tuyên bố đã mở HTML gallery. Dùng workspace links và Studio hiện có; Owner Chrome/draft cũ được giữ.

**Regression status và known limitations**

Không phát hiện hồi quy trong phạm vi Windows Native đã nghiệm thu. Dependencies, voice preset, production schema/tag không đổi; 10 Phase 8 MP4/evidence match baseline. Cả 12 projects, 23 jobs, 182 events, 59 versions và 10 final reviews trước task được giữ. Pre-media backup chứng minh mọi row cũ nguyên vẹn, chỉ năm project mới cập nhật theo approval. Cả 264 intelligence records, 389 versions, 62 decisions, 35 operations trước media không đổi; old IHG project/run/history nguyên vẹn. New assets/versions/events/jobs được Owner cho phép; không yêu cầu whole tables khớp release baseline sau bổ sung.

Thao tác dừng/khởi động lại main service sau render bị công cụ từ chối trước thực thi với “blocked by policy”. Wrapper PID 18500/listener 30380 và Studio 8026 vẫn hoạt động. Tiến trình kiểm tra mới mở lại đúng database, năm projects/jobs/approvals và actual artifacts; full table hashes khớp pre-checkpoint. [Policy limitation](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/service-restart-policy-limitation.json) tách fresh-process PASS khỏi main-service restart chưa thực hiện. Actual restart/tests của checkpoint trước giữ nguyên; không tạo after-restart giả.

Research nhận URL cụ thể, chưa tự khám phá toàn thị trường hoặc đo trend velocity. Source-reported chưa là xác minh độc lập; publication unknown giữ nguyên; 403/size/JS/PDF báo lỗi rõ. Subtitles theo cụm từ thời lượng audio đo được, chưa word alignment. Phát âm tên quốc tế/số liệu, nhịp dựng và cảm nhận giọng cần Owner nghe; visual review của Codex không thay đủ watch/listen. Legacy Docker/RC28 ngoài chứng nhận Native không được mở lại.

Không triển khai analytics learning, self-changing weights, winner detection, autonomous production/scheduling/publishing, agent swarm hoặc distributed orchestration.

**Blockers và next roadmap**

1. Owner xem/nghe đủ năm MP4 mới và lưu năm approve/reject decisions gắn đúng artifact/snapshot hashes. Task VF-PHASE9K-CONTENT-INTELLIGENCE-ACCEPTANCE-01 yêu cầu human watch/listen; brief/script/media approvals không thay thế.
2. Final decision cần chấp nhận thời lượng thực tế của 02/04/06 hoặc chỉ rõ bản cần sửa. Bản sửa giữ version/history và quay lại bước review cần thiết.
3. Sau approval thật, ghi Native final review, xác nhận final-download/queue PRODUCED và cập nhật readiness. Hiện queue IN_PRODUCTION; chưa publishing.

Không có blocker credential/provider/migration/major architecture. Main-service restart sau render là giới hạn kiểm chứng được ghi rõ; project persistence PASS qua fresh process có evidence thật. Sau nghiệm thu Phase 9, ưu tiên query relevance, duplicate ideas/source diversity và timestamp presentation từ feedback thực tế, giữ human approval; chưa mở autonomous publishing/analytics learning.

CONTENT_INTELLIGENCE_READY = NO
