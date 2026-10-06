# POST INTERNAL PRODUCTION — PHASE 9

Ngày báo cáo: 06/10/2026, giờ Việt Nam.

Content Intelligence đã đi từ nghiên cứu có nguồn tới video qua pipeline Windows Native hiện có. Owner đã duyệt năm brief, lời đọc v2 và storyboard/media/quyền sử dụng của 01/02/04/06/08, rồi báo giọng thay đổi cao độ và bị rè ở nhiều/cả năm bản gốc. Phản hồi này được lưu thật và ràng buộc năm MP4 gốc bằng các quyết định yêu cầu sửa; không suy ra đã xem/nghe trọn cả năm.

Sau bản sửa lần đầu, Owner chỉ rõ tám lỗi đầu câu ở 01/02/04; ba MP4 này được lưu quyết định yêu cầu sửa, còn 06/08 vẫn pending. Reply mới **“Giọng B đạt”** chấp nhận tám mẫu đầu câu B đã gửi, gắn đúng WAV/manifest/hashes; chưa chấp nhận toàn bộ lời đọc hoặc video mới.

Đã dựng đủ năm MP4 theo cách đọc B, giữ nguyên lời v2, hình/cách dựng và research lineage. Trạng thái hiện tại **WARM_B_VIDEOS_AWAIT_FULL_OWNER_REVIEW**: 8/8 mẫu B được Owner chấp nhận, nhưng **0/5 full new audio/final video approvals**. Năm bản mới đạt 11/11 Native QC, actual source/trim/artifact/lineage integrity, byte-exact preview/seek/final guard và fresh-process persistence. Phase 9K chưa PASS; phép đo codec không thay nghiệm thu cảm nhận giọng hoặc độ chính xác toàn bộ từ.

INTERNAL_PRODUCTION_READY = YES

**Release và SHA**

- Branch: codex/vf-post-mvp-roadmap-execution-01.
- Baseline SHA: f61d8de6545653ea46f8ab5f91e6c0c0c167b7af.
- Release marker: annotated tag internal-production-v1, giữ nguyên baseline và lịch sử.
- Final SHA của mã ứng dụng/TTS child đã kiểm thử: ebef5131e50641b93e3f7cf3b424dd151ce26d95, Native 159/159 PASS. Preview evidence helper: 738de15. Main Studio parent vẫn ở 9ce137afa8ac62fdb8ce5b35fbba997013adfef3, render function không đổi; existing dispatch tạo fresh TTS child cho từng job.
- Final SHA của checkpoint năm MP4/WAV B và actual evidence: 7a18ab22c71a92fde3466483252628245099d36f; metadata checkpoint f9a9411261eaeb1873bb1dc53caf0845520ce5a4. Checkpoint sửa lần đầu 235e90664dbddd6a820ad751e32e09d7b8ca84a8 và bản gốc a44bb0d giữ nguyên theo thời điểm.
- HEAD khi chốt báo cáo: 3b333c737dc1e7d2f15bfc10d60edf10f46faaa8, bổ sung kiểm chứng byte Git và sampled visuals. [Git byte integrity](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/git-byte-integrity.json) xác nhận 985 tệp/148.736.826 byte khớp commit evidence, gồm toàn bộ 91 WAV/MP4; không sửa output hay mã sản xuất.
- Commit tiếp theo chỉ cập nhật báo cáo; SHA của chính commit báo cáo được xác định trong Git history và lời bàn giao. Đây là checkpoint, chưa phải human acceptance cuối Phase 9.

Các commit tiến dần: freeze 8f0aacc; domain 2d819c9; engines/profiles 3d1c391; Studio/bridge 3cd4aaf; Windows sources fc986b0; kỹ thuật/10 ca 7c13e2a; brief-duration instructions bf4ec72; năm brief/handoff e4ee6c2; năm script thật 4b2f67f; v2/restart 8ad8346; script review riêng 2980fdf; 25 đồ họa/lineage cee0eab; Owner media receipts 9ce137a; video gốc a44bb0d; opt-in speech context ce21b4a; năm video sửa giọng/Owner negative receipts 4f84418; PCM archive 235e906; actual onset feedback/trials 1fe3590; eight A/B WAVs 63a031a; Owner B receipt/raw sources fdd675b; warm Native policy e087b71; actual boundary correction ebef513; decoded-preview binding 738de15. Checkpoint cũ giữ theo thời điểm.

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
| 9G — Existing pipeline | PASS tích hợp/kỹ thuật; full audio acceptance chờ | Năm MP4 B qua cùng Native pipeline, lineage giữ nguyên |
| 9H — Profiles | PASS | Bốn profiles cấu hình; mix 10 ca 3/2/2/3 |
| 9I — Queue | PASS kỹ thuật | Sáu trạng thái; năm ca IN_PRODUCTION, chưa PRODUCED |
| 9J — Tests | PASS trong phạm vi ghi rõ | 159 Native; 32 Studio historical, UI unchanged; actual provider/audio/video evidence riêng |
| 9K — Acceptance | WARM_B_VIDEOS_AWAIT_FULL_OWNER_REVIEW | Owner accepts eight B onset samples; five actual B MP4/QC/integrity/persistence; 0/5 full new human final |

Các trường báo cáo subphase nằm trong [domain-model.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/domain-model.md), [engines-and-profiles.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/engines-and-profiles.md), [studio-pipeline-and-verification.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/studio-pipeline-and-verification.md), [handoff matrix](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/phase9k-handoff-matrix.md), và [real production checkpoint](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/real-production-checkpoint.md).

**Architecture additions**

ResearchSource, ResearchFinding, TrendSignal, Opportunity, ContentIdea, ContentBrief, IdeaScore và ResearchRun có stable ID, created_at, updated_at, version và provenance. Giá trị kinh doanh nằm trong cấu hình. Intelligence database riêng C:\NPD-Video-Factory\phase2\intelligence.sqlite3, schema 1, lưu history, human decisions và operation receipts. Production schema giữ nguyên; lineage content-intelligence-lineage-v1; canonical timeline 1.1.

ResearchProvider nhận query/context và 1–5 URL HTTPS công khai do người dùng hoặc cấu hình cung cấp. Nó lưu nguồn, trích đoạn, query, receipt, timestamps, provider metadata và SHA. Findings phân biệt SOURCE_REPORTED, INFERENCE, UNRESOLVED. Source-reported chưa phải xác minh độc lập. Retrieval date không thay publication date; unknown giữ nguyên. HTTP/size/parse/grounding failures explicit, không tạo nguồn thay thế.

IdeaProvider tái dùng gpt-6-luna và credential đã tồn tại để sinh năm ứng viên. References phải thuộc source/finding đã lưu; angle/hook/rationale là đề xuất biên tập. Bộ 10 ca ban đầu có 13 phản hồi thực tế: 10 hợp lệ và ba bị từ chối vì references. Ledger này giữ phạm vi lịch sử. Scoring lưu mười dimensions, weights cấu hình, component/final scores, rationale, thời điểm/config hash; HEURISTIC_SCORING không dự báo thống kê lượt xem/lead.

Studio có [Nghiên cứu & ý tưởng](http://127.0.0.1:8026/intelligence), Opportunity Queue, chọn/sửa/bỏ/tạo lại ý tưởng, sửa/duyệt brief và explicit handoff. Sửa candidate/brief làm mất hiệu lực duyệt cũ và giữ history. Handoff tạo project để review script, không tự sản xuất. Research → idea → approved brief → script → storyboard → job/timeline/render giữ lineage/source hashes. Pipeline Phase 1–8, TTS/media/editor/preview/final review được tái sử dụng.

Ca 01 có generation/brief khác do Owner tạo và handoff trước task 9K. Task lấy Rank #1 hiện tại qua retained-research fork có original IDs, nguồn/timestamps/hash gốc; không gọi source/idea provider thêm. Project, approval và 19 record của run cũ cùng toàn bộ history được giữ.

Năm content jobs nhận năm phản hồi script thật, mỗi job một call; request/response/result/model/usage/IDs/hashes giữ nguyên. V2 biên tập từ v1, lưu bằng Native Store, không gọi provider thêm. Reply “Duyệt v2: 01, 02, 04, 06, 08” tạo năm SCRIPT_ONLY events ràng buộc narration và lineage. Sửa narration/lineage làm approval hết hiệu lực; sửa hình không tự sửa script approval.

Reply mới “Duyệt storyboard/media: 01, 02, 04, 06, 08” ràng buộc bộ 25 cảnh đã gửi. Đã nhập đúng 25 PNG, giữ byte gốc và tạo JPEG derivative bằng ingest Native. Asset provenance lưu recipe/font/source/script/Owner receipt hashes. Năm project lên revision 9, giữ lời đọc v2, five scenes/contain/no motion/source-start 0/fade, không nhạc. Approval snapshots và reviewed storyboard v3 giữ nguyên; current storyboard v5 ghi measured timing/job/output, không thay bundle đã duyệt.

Native Store.approve thêm optional review_reference để ghi đúng source human_user_reply_in_codex và authorization hash. Existing calls/UI/schema không đổi; invalid reference bị từ chối, approval không tự dispatch. Helper gọi approval/enqueue hiện có sau reply thật. Năm video gốc đã tạo 43 local TTS inferences, speed preset 1, 0 retries, network blocked, rồi FFmpeg render; đây là lịch sử, không phải số calls của bản B hiện tại. Không thêm provider/credential hoặc pipeline video thứ hai.

Sau phản hồi lỗi giọng, optional scene-context-v1 được chọn riêng cho năm project mới: đọc liền theo cảnh, seed 604, policy ID/version/hash ràng buộc snapshot. Legacy sentence policy vẫn mặc định. SDK/model/preset/profile và temperature 0.8/top-k/top-p/repetition penalty/frame cap giữ nguyên; metadata lưu thông số thật. Không đổi tốc độ/cao độ/EQ/denoiser. Thay policy tăng revision và bỏ approval, không tự dispatch. Năm quyết định yêu cầu sửa đưa project lên v10, chọn policy lên v11; script review còn current. Production approval dùng lại đúng lời/hình đã duyệt, dẫn actual Owner repair receipt và ghi new_audio_quality_accepted=false/final_video_approved=false. Existing serial worker tạo 27 local inferences mới (5/5/5/5/7), rồi render; không tạo pipeline thứ hai hoặc thêm credential/provider.

Đầu cảnh vẫn có lỗi theo phản hồi cụ thể của Owner. Store lưu thêm ba quyết định reject đúng MP4 v11 của 01/02/04 và đưa project lên v12; 06/08 không nhận quyết định mới. Tám thử nghiệm B dùng câu cuối đã duyệt của cảnh trước làm ngữ cảnh, seed 604 và thông số/model/preset cũ. Reply “Giọng B đạt” ràng buộc tám excerpt; production authority trước đó cho phép sửa/dựng nội bộ bằng đúng lời/hình đã duyệt, chưa approve MP4 đầy đủ.

Policy opt-in warm-scene-context-v1 tạo một context liên tục có giới hạn cho mỗi cảnh, ghi rõ normalization override 4096 và limit 512 ký tự, giữ default profile max_chars 256. TTS coordinator dùng child offline riêng, rồi adapter AssemblyAI đã kết nối để lấy actual native word timestamps. Cắt prefix dựa trên exact canonical opening tokens/abbreviation hoặc khoảng nghỉ đo được có cả target và approved-context anchors; ambiguity thất bại rõ. Raw source WAV, provider payload/receipts, plan, cut và code hashes được lưu portable. Đây không phải forced alignment; first scene không có prefix. Tám raw B sources/cuts được dùng lại, không replay provider của chúng. Renderer/Auto Editor và final review guard cũ nhận một measured unit cho mỗi cảnh; không đổi script/media/lineage, pitch, speed hoặc thêm EQ/denoiser.

Năm project hiện tại: 01/02/04 v13, 06/08 v12. Có 25 resolved scene sources gồm 8 reviewed B và **17 actual new local inferences** cho repair này. Bốn attempt của 01/02/06/08 dừng ở boundary matcher, giữ nguyên source/generation/paid receipts; sửa matcher rồi explicit resume cùng job/snapshot, không replay inference hoặc paid outcomes đã biết. Tất cả chín TTS attempts (4 failed + 5 pass) được archive. Số công việc mới toàn repair: **12 uploads + 12 transcript creates + 27 observations**. Riêng năm passing attempts: 2 fresh + 23 reused local sources, 5 uploads/creates + 12 observations. Source history tổng gồm 20 uploads/creates + 43 observations, trong đó 8 uploads/creates + 16 observations thuộc thử nghiệm B trước; không gọi tất cả là request mới hoặc invoice đã kiểm chứng.

**Tests và verification**

| Kiểm tra | Kết quả |
|---|---|
| Native unit/integration/persistence/provenance/failure suite | 159/159 PASS tại ebef513, gồm guards của warm child/cache/raw timing/source/cut/failure paths; synthetic unit fixtures không được gọi actual provider PASS |
| Studio suite | 32/32 historical PASS; UI không đổi sau lần chạy này, không tuyên bố chạy lại |
| Actual research/ideas | 10 ca/50 ứng viên hợp lệ ban đầu; provider integrations phân loại riêng |
| Human brief/script/media decisions | 5/5 từng bước, exact versions/hashes/source receipts |
| Actual local TTS/timing | 5/5 B jobs; 17 new + 8 reviewed source calls; 4 explicit boundary recoveries giữ failed evidence; 12 new real ASR uploads/creates + 27 observations; không replay known outcomes |
| Actual MP4 ffprobe/QC | 5/5, 11/11 mỗi video: portrait 1080×1920, H264/AAC, 30fps, yuv420p, 48kHz, full decode, finite audible audio, no clipping/black intervals, complete duration/A-V alignment |
| Artifact/source/lineage integrity | 5/5 PASS: canonical plans, exact approved snapshots, raw PCM, actual ASR payload/receipt hashes, reconstructed cut, selected assets và 8 reviewed B sources/cuts |
| Live preview/seek/final guard | 5/5 byte-exact MP4, range seek; final endpoint HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED |
| Project persistence/fresh-process reopen | 5/5 PASS; DDL/table hashes của hai database và project/approval/job/MP4 state khớp checkpoint trước |
| Main-service restart sau render | NOT_PERFORMED_POLICY_BLOCKED; không ghi PASS. Actual restart checkpoint trước vẫn có evidence |
| Audio transport/source | 25 trimmed scene PCM units khớp raw sources sample-exact; 8 reviewed targets khác tối đa 1 LSB do encoding lịch sử. MP4/raw correlation 0.99999478–0.99999564, decoded peak 0.7927–0.9001, actual decode bound to exact MP4 SHA; không chứng minh naturalness |
| Visual evidence | Independent sheet-scale inspection của 25 sampled frames PASS; ảnh trích đúng năm MP4 B. Không thay full moving-video/audio watch/listen |
| Human audio/final watch/listen | Năm video gốc rejected; repair01 01/02/04 rejected, 06/08 pending; tám B excerpts Owner accepted; năm full B MP4 0/5 PENDING |

[159 Native tests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/native-tests-boundary-final.log), [32 historical Studio tests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/studio-tests-storyboard.log), [actual B production verification](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/actual-verification.json), [fresh-process persistence](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/fresh-process-persistence.json), [PCM/codec/preview/final guards](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/audio-and-preview-checks.json). Earlier 139 Native tests and repair01 verification remain historical evidence, not current human audio acceptance.

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

| Ca | MP4 B mới | Thực tế | Mục tiêu | Project revision | QC/integrity/persistence | Human final |
|---|---|---:|---|---:|---|---|
| 01 | [Xem/nghe bản B](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/case-01/final.mp4) | 33,715s | 30–45s | 13 | PASS | PENDING |
| 02 | [Xem/nghe bản B](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/case-02/final.mp4) | 39,605s | 45–60s, ngắn hơn | 13 | PASS | PENDING |
| 04 | [Xem/nghe bản B](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/case-04/final.mp4) | 34,615s | 45s, ngắn hơn | 13 | PASS | PENDING |
| 06 | [Xem/nghe bản B](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/case-06/final.mp4) | 35,475s | 45s, ngắn hơn | 12 | PASS | PENDING |
| 08 | [Xem/nghe bản B](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/case-08/final.mp4) | 46,866667s | 45–60s | 12 | PASS | PENDING |

02/04/06 chưa đạt thời lượng mục tiêu. Lời đọc v2 và speed preset được giữ nguyên; technical QC chứng minh video hoàn chỉnh theo measured audio. Owner cần chấp nhận thời lượng thực tế hoặc yêu cầu sửa, không tự đổi narration/speed để che khác biệt.

**Evidence và screenshots**

Idea/brief bundle SHA 1ac01b244e396e3d53f76197b1c475e134275fd2c605463981fc3048ba5872e4; script v2 bundle SHA ba8f2a4572497fe59ece072f767d0d0a54f668304ebb090cfb9338d1bb287d1c; storyboard/media bundle SHA d9fe7af9329c5bc293a155b9f152fdd65730e3f1b6f83bb65149291a81ac7000. Tất cả giữ byte gốc.

[Original audio feedback](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/owner-feedback.json), [actual onset rejection receipts](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-02/owner-negative-decisions.json), [Owner B approval và pre-change backups](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/owner-B-approval.json), [new production snapshots](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/production-approval-manifest.json), [năm video B đầy đủ](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/review-bundle.md), [exact new MP4 manifest](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/review-manifest.json), [four boundary failures/recovery](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/boundary-failure-recovery-before.json), [same-job resumes](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/boundary-failure-recovery-resumed.json), [final review register](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/phase9k-final-review.md). Each new case includes portable actual sources/provider receipts and all failed/passing TTS attempts. Original media/source approvals, earlier MP4/WAVs and review bundles remain byte-exact historical evidence.

![Năm cảnh trích từ MP4 B mới ca 08](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/case-08/contact-sheet.png)

Năm contact sheets và 25 frame receipts được trích đúng actual B MP4 hashes. Screenshot/playback của repair01 giữ phạm vi lịch sử, không chứng minh video B mới được Owner xem/nghe. Static gallery cũ là historical storyboard preview. Dùng workspace links và Studio hiện có; Owner Chrome/draft cũ được giữ.

**Regression status và known limitations**

Không phát hiện hồi quy trong phạm vi Windows Native Phase 8 đã nghiệm thu. Dependencies, voice preset, production schema/tag không đổi; 10 Phase 8 MP4/evidence match baseline. Pre-B backup chứng minh 38 jobs, 335 events, 117 versions, 18 final review rows và 12 other projects nguyên vẹn; chỉ năm current projects được sửa theo scope. Cả 264 intelligence records, 389 versions, 62 decisions, 35 operations và old IHG history không đổi. **1.034 frozen historical repository evidence files** giữ hash; original và repair01 raw WAV/MP4/review rows không bị thay. Năm video gốc rejected, ba repair01 onset rejections vẫn tồn tại. Full new B audio quality chưa được Owner duyệt.

Thao tác dừng/khởi động lại main service sau render bị công cụ từ chối trước thực thi với “blocked by policy”. Wrapper PID 18500/listener 30380 và Studio 8026 vẫn hoạt động. Tiến trình kiểm tra mới mở lại đúng database, năm projects/jobs/approvals và actual artifacts; full table hashes khớp pre-checkpoint. [Policy limitation](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/service-restart-policy-limitation.json) tách fresh-process PASS khỏi main-service restart chưa thực hiện. Actual restart/tests của checkpoint trước giữ nguyên; không tạo after-restart giả.

Research nhận URL cụ thể, chưa tự khám phá toàn thị trường hoặc đo trend velocity. Source-reported chưa là xác minh độc lập; publication unknown giữ nguyên; 403/size/JS/PDF báo lỗi rõ. Subtitles theo cụm từ thời lượng audio đo được, chưa word alignment. Phát âm tên quốc tế/số liệu, nhịp dựng và cảm nhận giọng cần Owner nghe; visual review của Codex không thay đủ watch/listen. Legacy Docker/RC28 ngoài chứng nhận Native không được mở lại.

Warm context đã được Owner chấp nhận ở tám excerpt. Chưa suy ra toàn bộ năm video đạt naturalness/từ/ngữ điệu. ASR có bất đồng với lời duyệt ở CTA “Để lại câu hỏi”, tên quốc tế như Crowne Plaza/Holiday Inn Express/Garner, ca04 “tách/dữ kiện”, số hoặc viết tắt; actual raw transcripts giữ nguyên. ASR disagreement không chứng minh TTS đọc sai, và không tự rewrite lời hoặc gắn word-accuracy PASS. Các boundary fallback đều giữ anchors/cut/raw evidence, vẫn cần nghe. F0 diagnostics lịch sử và waveform correlation không thay human acceptance. Phụ đề theo cụm ước lượng, chưa word alignment.

Không triển khai analytics learning, self-changing weights, winner detection, autonomous production/scheduling/publishing, agent swarm hoặc distributed orchestration.

**Blockers và next roadmap**

1. Owner nghe/xem đủ năm **MP4 B đầy đủ mới** và xác nhận chất lượng giọng/toàn bộ lời/final approve hoặc nêu lỗi còn lại, gắn đúng artifact/snapshot hashes. Task VF-PHASE9K-CONTENT-INTELLIGENCE-ACCEPTANCE-01 yêu cầu human watch/listen; reply “Giọng B đạt” chỉ chấp nhận tám mẫu đầu câu, không thay final approval.
2. Final decision cần chấp nhận thời lượng thực tế của 02/04/06 hoặc chỉ rõ bản cần sửa. Bản sửa giữ version/history và quay lại bước review cần thiết.
3. Sau approval thật, ghi Native final review, xác nhận final-download/queue PRODUCED và cập nhật readiness. Hiện queue IN_PRODUCTION; chưa publishing.

Không có blocker credential/provider/migration/major architecture. Main-service restart sau render là giới hạn kiểm chứng được ghi rõ; project persistence PASS qua fresh process có evidence thật. Sau nghiệm thu Phase 9, ưu tiên query relevance, duplicate ideas/source diversity và timestamp presentation từ feedback thực tế, giữ human approval; chưa mở autonomous publishing/analytics learning.

CONTENT_INTELLIGENCE_READY = NO
