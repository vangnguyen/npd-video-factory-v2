# POST INTERNAL PRODUCTION — PHASE 9

Ngày báo cáo: 06/10/2026, giờ Việt Nam.

Content Intelligence đã đi từ nghiên cứu có nguồn tới video qua pipeline Windows Native hiện có. Owner đã duyệt năm brief, lời đọc v2 và storyboard/media/quyền sử dụng của 01/02/04/06/08, rồi báo giọng thay đổi cao độ và bị rè ở nhiều/cả năm bản gốc. Phản hồi này được lưu thật và ràng buộc năm MP4 gốc bằng các quyết định yêu cầu sửa; không suy ra đã xem/nghe trọn cả năm.

Đã tạo lại giọng và dựng năm MP4 mới, giữ nguyên lời đọc/hình/cách dựng/research. Mỗi bản mới đạt 11/11 QC, hash/lineage và fresh-process persistence. Trạng thái hiện tại **REPAIRED_VIDEOS_AWAIT_OWNER_LISTENING**: 0/5 chấp nhận chất lượng giọng mới hoặc final watch/listen. Phép đo tín hiệu không chứng minh đã hết rè. Phase 9K chưa PASS.

INTERNAL_PRODUCTION_READY = YES

**Release và SHA**

- Branch: codex/vf-post-mvp-roadmap-execution-01.
- Baseline SHA: f61d8de6545653ea46f8ab5f91e6c0c0c167b7af.
- Release marker: annotated tag internal-production-v1, giữ nguyên baseline và lịch sử.
- Final SHA của mã ứng dụng/TTS child đã kiểm thử: ce21b4ae8f62c65955209abfc87c5beb395b2169. Main Studio parent vẫn ở 9ce137afa8ac62fdb8ce5b35fbba997013adfef3, render function không đổi; existing dispatch tạo fresh TTS child cho từng job.
- Final SHA của checkpoint kỹ thuật và năm bản sửa giọng MP4/WAV: 235e90664dbddd6a820ad751e32e09d7b8ca84a8 (MP4/evidence 4f84418, PCM archive 235e906). Các bản gốc ở a44bb0d giữ nguyên.
- Commit tiếp theo chỉ cập nhật báo cáo; SHA của chính commit báo cáo được xác định trong Git history và lời bàn giao. Đây là checkpoint, chưa phải human acceptance cuối Phase 9.

Các commit tiến dần: freeze 8f0aacc; domain 2d819c9; engines/profiles 3d1c391; Studio/bridge 3cd4aaf; Windows sources fc986b0; kỹ thuật/10 ca 7c13e2a; brief-duration instructions bf4ec72; năm brief/handoff e4ee6c2; năm script thật 4b2f67f; v2/restart 8ad8346; script review riêng 2980fdf; 25 đồ họa/lineage cee0eab; Owner media receipts 9ce137a; video gốc a44bb0d; opt-in speech context ce21b4a; năm video sửa giọng/Owner negative receipts 4f84418; PCM archive 235e906. Checkpoint cũ giữ theo thời điểm.

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
| 9G — Existing pipeline | PASS tích hợp/kỹ thuật; audio acceptance chờ | Năm bản sửa qua cùng Native pipeline, lineage giữ nguyên |
| 9H — Profiles | PASS | Bốn profiles cấu hình; mix 10 ca 3/2/2/3 |
| 9I — Queue | PASS kỹ thuật | Sáu trạng thái; năm ca IN_PRODUCTION, chưa PRODUCED |
| 9J — Tests | PASS trong phạm vi ghi rõ | 139 Native + 32 Studio; actual audio/video verification riêng |
| 9K — Acceptance | REPAIRED_VIDEOS_AWAIT_OWNER_LISTENING | Năm bản gốc yêu cầu sửa; 5/5 MP4 sửa/QC/integrity/persistence; 0/5 new human final |

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

Sau phản hồi lỗi giọng, optional scene-context-v1 được chọn riêng cho năm project mới: đọc liền theo cảnh, seed 604, policy ID/version/hash ràng buộc snapshot. Legacy sentence policy vẫn mặc định. SDK/model/preset/profile và temperature 0.8/top-k/top-p/repetition penalty/frame cap giữ nguyên; metadata lưu thông số thật. Không đổi tốc độ/cao độ/EQ/denoiser. Thay policy tăng revision và bỏ approval, không tự dispatch. Năm quyết định yêu cầu sửa đưa project lên v10, chọn policy lên v11; script review còn current. Production approval dùng lại đúng lời/hình đã duyệt, dẫn actual Owner repair receipt và ghi new_audio_quality_accepted=false/final_video_approved=false. Existing serial worker tạo 27 local inferences mới (5/5/5/5/7), rồi render; không tạo pipeline thứ hai hoặc thêm credential/provider.

**Tests và verification**

| Kiểm tra | Kết quả |
|---|---|
| Native unit/integration/persistence/provenance/failure suite | 139/139 PASS sau application change cuối; năm tests mới cho grouping/default, policy drift, seed/locked params, revision/persistence/history và approval/no-auto-dispatch |
| Studio suite | 32/32 PASS; UI không đổi sau lần chạy này |
| Actual research/ideas | 10 ca/50 ứng viên hợp lệ ban đầu; provider integrations phân loại riêng |
| Human brief/script/media decisions | 5/5 từng bước, exact versions/hashes/source receipts |
| Actual local TTS | 5/5 fresh repaired jobs, 27 calls, 0 retries; original 43 calls giữ historical; không dùng fixture hoặc Phase 8 audio |
| Actual MP4 ffprobe/QC | 5/5, 11/11 mỗi video: portrait 1080×1920, H264/AAC, 30fps, yuv420p, 48kHz, full decode, finite audible audio, no clipping/black intervals, complete duration/A-V alignment |
| Artifact/source/lineage integrity | 5/5 PASS, exact MP4/voice/snapshot/source hashes và selected assets |
| Live preview/seek/final guard | 5/5 byte-exact MP4, range seek; final endpoint HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED |
| Project persistence/fresh-process reopen | 5/5 PASS; DDL/table hashes của hai database và project/approval/job/MP4 state khớp checkpoint trước |
| Main-service restart sau render | NOT_PERFORMED_POLICY_BLOCKED; không ghi PASS. Actual restart checkpoint trước vẫn có evidence |
| Audio transport/joins | 5/5 decoded MP4 khớp raw waveform, correlation >0.99999 ở offset 1.1s; zero measured join jumps, không hard clipping; không chứng minh hết rè |
| Visual inspection | Codex xem 25 sampled frames mới và playback/source/unchecked-final state trong Studio; không thay Owner watch/listen |
| Human audio/final watch/listen | Năm bản gốc có actual Owner audio-revision decisions; năm bản sửa 0/5, PENDING |

[139 Native tests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/native-tests.log), [32 Studio tests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/studio-tests-storyboard.log), [repaired production verification](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/actual-verification.json), [fresh-process persistence](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/fresh-process-persistence.json), [audio/preview/final guards](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/audio-and-preview-checks.json), [visual scope](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/visual-review.json).

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
| 01 | [Xem/nghe bản sửa](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/case-01/final.mp4) | 34,43s | 30–45s | 5 | PASS | PENDING |
| 02 | [Xem/nghe bản sửa](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/case-02/final.mp4) | 39,97s | 45–60s, ngắn hơn | 5 | PASS | PENDING |
| 04 | [Xem/nghe bản sửa](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/case-04/final.mp4) | 34,30s | 45s, ngắn hơn | 5 | PASS | PENDING |
| 06 | [Xem/nghe bản sửa](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/case-06/final.mp4) | 35,38s | 45s, ngắn hơn | 5 | PASS | PENDING |
| 08 | [Xem/nghe bản sửa](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/case-08/final.mp4) | 46,97s | 45–60s | 7 | PASS | PENDING |

02/04/06 chưa đạt thời lượng mục tiêu. Lời đọc v2 và speed preset được giữ nguyên; technical QC chứng minh video hoàn chỉnh theo measured audio. Owner cần chấp nhận thời lượng thực tế hoặc yêu cầu sửa, không tự đổi narration/speed để che khác biệt.

**Evidence và screenshots**

Idea/brief bundle SHA 1ac01b244e396e3d53f76197b1c475e134275fd2c605463981fc3048ba5872e4; script v2 bundle SHA ba8f2a4572497fe59ece072f767d0d0a54f668304ebb090cfb9338d1bb287d1c; storyboard/media bundle SHA d9fe7af9329c5bc293a155b9f152fdd65730e3f1b6f83bb65149291a81ac7000. Tất cả giữ byte gốc.

[Owner audio feedback và bảo toàn bản gốc](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/owner-feedback.json), [approved repair snapshots](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/production-approval-manifest.json), [bộ năm video sửa giọng](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/review-bundle.md), [exact revised MP4 manifest](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/review-manifest.json), [repair checkpoint](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/checkpoint.md), [final review register](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/phase9k-final-review.md). Original media/source approvals and original video review bundle/manifests remain byte-exact historical evidence.

![Studio thật với video sửa giọng và final review chưa xác nhận](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/native-studio.png)

![Năm cảnh trích từ MP4 sửa giọng ca 08](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/case-08/contact-sheet.png)

Native screenshot ca 01 thể hiện job sửa giọng 40428232bdb940b8abdabb00e5043c95/34,43s, phát được và dừng ở 13,238614s; ô xem/nghe chưa tick. 25 actual frames mới được trích từ năm MP4 sửa giọng. Static gallery cũ là historical storyboard preview; browser chặn file URLs nên không tuyên bố đã mở HTML gallery. Dùng workspace links và Studio hiện có; Owner Chrome/draft cũ được giữ.

**Regression status và known limitations**

Không phát hiện hồi quy trong phạm vi Windows Native Phase 8 đã nghiệm thu. Dependencies, voice preset, production schema/tag không đổi; 10 Phase 8 MP4/evidence match baseline. Cả 12 projects, 23 jobs, 182 events, 59 versions và 10 final reviews trước task được giữ. Pre-repair backup chứng minh 33 jobs, 287 events, 104 versions và 10 review rows cũ nguyên vẹn; chỉ năm current projects được sửa theo scope. Mười hai project khác, 264 intelligence records, 389 versions, 62 decisions, 35 operations và old IHG history không đổi. Cả 292 frozen Phase 9K files cùng raw WAV gốc của năm jobs giữ hash. Năm Phase 9K gốc có Owner negative audio feedback, không được gọi quality PASS.

Thao tác dừng/khởi động lại main service sau render bị công cụ từ chối trước thực thi với “blocked by policy”. Wrapper PID 18500/listener 30380 và Studio 8026 vẫn hoạt động. Tiến trình kiểm tra mới mở lại đúng database, năm projects/jobs/approvals và actual artifacts; full table hashes khớp pre-checkpoint. [Policy limitation](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/service-restart-policy-limitation.json) tách fresh-process PASS khỏi main-service restart chưa thực hiện. Actual restart/tests của checkpoint trước giữ nguyên; không tạo after-restart giả.

Research nhận URL cụ thể, chưa tự khám phá toàn thị trường hoặc đo trend velocity. Source-reported chưa là xác minh độc lập; publication unknown giữ nguyên; 403/size/JS/PDF báo lỗi rõ. Subtitles theo cụm từ thời lượng audio đo được, chưa word alignment. Phát âm tên quốc tế/số liệu, nhịp dựng và cảm nhận giọng cần Owner nghe; visual review của Codex không thay đủ watch/listen. Legacy Docker/RC28 ngoài chứng nhận Native không được mở lại.

Đọc liền theo cảnh giảm các model contexts ngắn, là hướng sửa có cơ sở từ fragmentation quan sát được, chưa chứng minh nguyên nhân duy nhất của tiếng rè. SDK vẫn chia cảnh dài thành chunks. F0 diagnostics có octave errors và đổi ranh giới đơn vị; ca 08 có range tăng nên không tuyên bố mọi cao độ đều tốt hơn. Không biến correlation/no-clipping thành naturalness PASS. Phụ đề vẫn ước lượng theo cụm, có thể có cue ngắn; cần Owner kiểm tra cùng âm thanh.

Không triển khai analytics learning, self-changing weights, winner detection, autonomous production/scheduling/publishing, agent swarm hoặc distributed orchestration.

**Blockers và next roadmap**

1. Owner nghe/xem đủ năm MP4 sửa giọng mới và xác nhận chất lượng giọng/final approve hoặc nêu lỗi còn lại, gắn đúng artifact/snapshot hashes. Task VF-PHASE9K-CONTENT-INTELLIGENCE-ACCEPTANCE-01 yêu cầu human watch/listen; brief/script/media approvals không thay thế.
2. Final decision cần chấp nhận thời lượng thực tế của 02/04/06 hoặc chỉ rõ bản cần sửa. Bản sửa giữ version/history và quay lại bước review cần thiết.
3. Sau approval thật, ghi Native final review, xác nhận final-download/queue PRODUCED và cập nhật readiness. Hiện queue IN_PRODUCTION; chưa publishing.

Không có blocker credential/provider/migration/major architecture. Main-service restart sau render là giới hạn kiểm chứng được ghi rõ; project persistence PASS qua fresh process có evidence thật. Sau nghiệm thu Phase 9, ưu tiên query relevance, duplicate ideas/source diversity và timestamp presentation từ feedback thực tế, giữ human approval; chưa mở autonomous publishing/analytics learning.

CONTENT_INTELLIGENCE_READY = NO
