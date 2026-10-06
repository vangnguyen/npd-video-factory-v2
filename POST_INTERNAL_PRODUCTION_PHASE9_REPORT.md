# POST INTERNAL PRODUCTION — PHASE 9

Ngày báo cáo: 06/10/2026, giờ Việt Nam.

Content Intelligence đã đi từ nghiên cứu có nguồn tới video qua pipeline Windows Native hiện có. Owner đã duyệt năm brief, lời đọc v2 và storyboard/media/quyền sử dụng của 01/02/04/06/08, rồi báo giọng thay đổi cao độ và bị rè ở nhiều/cả năm bản gốc. Phản hồi này được lưu thật và ràng buộc năm MP4 gốc bằng các quyết định yêu cầu sửa; không suy ra đã xem/nghe trọn cả năm.

Sau bản sửa lần đầu, Owner chỉ rõ tám lỗi đầu câu ở 01/02/04; ba MP4 này được lưu quyết định yêu cầu sửa, còn 06/08 vẫn pending. Reply mới **“Giọng B đạt”** chấp nhận tám mẫu đầu câu B đã gửi, gắn đúng WAV/manifest/hashes; chưa chấp nhận toàn bộ lời đọc hoặc video mới.

Đã dựng đủ năm MP4 theo cách đọc B, giữ nguyên lời v2, hình/cách dựng và research lineage. Owner sau đó trả lời **“Duyệt”** cho câu hỏi xem/nghe đúng năm MP4 B đầy đủ 01/02/04/06/08, bao gồm thời lượng thực tế đã báo của 02/04/06. Đã lưu **5/5 Native final approvals** ràng buộc job/revision/snapshot/MP4 hashes và chuyển đúng năm Opportunity sang **PRODUCED**. Trạng thái hiện tại **PHASE9K_ACCEPTED**. Final download trả HTTP 200 với byte/hash đúng, range seek 206 và fresh-process accepted-state persistence PASS. Phase 9K đã PASS trong phạm vi nội bộ Windows Native; không có publishing.

INTERNAL_PRODUCTION_READY = YES

**Release và SHA**

- Branch: codex/vf-post-mvp-roadmap-execution-01.
- Baseline SHA: f61d8de6545653ea46f8ab5f91e6c0c0c167b7af.
- Release marker: annotated tag internal-production-v1, giữ nguyên baseline và lịch sử.
- Final SHA của mã ứng dụng/TTS child đã kiểm thử: ebef5131e50641b93e3f7cf3b424dd151ce26d95, Native 159/159 PASS. Preview evidence helper: 738de15. Native service hiện chạy ứng dụng tại 0b0555f827d4a48c92679d2ed266def063e7f6b1; runtime code không đổi, commit sau bổ sung evidence/helpers. Đã khởi động existing service từ trạng thái port/Python offline thực tế, không dừng/kill tiến trình đang chạy. Renderer và existing dispatch được giữ.
- Final SHA của checkpoint năm MP4/WAV B và actual evidence: 7a18ab22c71a92fde3466483252628245099d36f; metadata checkpoint f9a9411261eaeb1873bb1dc53caf0845520ce5a4. Checkpoint sửa lần đầu 235e90664dbddd6a820ad751e32e09d7b8ca84a8 và bản gốc a44bb0d giữ nguyên theo thời điểm.
- Final SHA evidence nghiệm thu: a26e169635e4fa8eea7f31cf90309472d5723df0, gồm receipts/final reviews/PRODUCED/downloads/persistence và ảnh Studio thật. HEAD ứng dụng khi ghi nghiệm thu: 0b0555f827d4a48c92679d2ed266def063e7f6b1. Commit báo cáo tiếp theo được xác định riêng trong Git history và lời bàn giao. [Git byte integrity](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/git-byte-integrity.json) của checkpoint media xác nhận 985 tệp/148.736.826 byte khớp 7a18ab22, gồm toàn bộ 91 WAV/MP4; final approval không sửa output hay mã sản xuất.
- Receipt cuối lưu nguyên reply “Duyệt”, câu hỏi đầy đủ, review bundle/manifest hashes và ngoại lệ thời lượng; năm review rows 19–23 giữ đúng artifact/snapshot. Lần chốt acceptance gọi thêm provider/TTS/render **0** lần.
- HEAD khi chốt báo cáo: 66c7f9c1736ede3b89fb6b9927633de427fcf950. [Success gate](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/final-acceptance/success-gate.json) ràng buộc đủ mười điều kiện với evidence thật; commit tiếp theo chỉ cập nhật bốn báo cáo.

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
| 9F — Review | PASS; brief/script/media/final 5/5 | Chọn/sửa/bỏ/tạo lại, duyệt trước production và exact final decisions |
| 9G — Existing pipeline | PASS | Năm MP4 B qua cùng Native pipeline, lineage giữ nguyên, final download đã mở sau review |
| 9H — Profiles | PASS | Bốn profiles cấu hình; mix 10 ca 3/2/2/3 |
| 9I — Queue | PASS | Sáu trạng thái; đúng năm ca được Owner duyệt đã PRODUCED |
| 9J — Tests | PASS trong phạm vi ghi rõ | 159 Native; 32 Studio historical, UI unchanged; actual provider/audio/video evidence riêng |
| 9K — Acceptance | PASS — PHASE9K_ACCEPTED | Năm actual B MP4/QC/integrity/persistence; 5/5 full watch/listen decisions, thời lượng ngoại lệ được duyệt |

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
| Live preview/seek/final guard | Trước duyệt: guard từ chối đúng; sau duyệt: 5/5 final HTTP 200 byte/hash đúng, range 206 đúng |
| Project persistence/fresh-process reopen | 5/5 PASS trước và sau final approval; accepted state, reviews, queue và table snapshots khớp trong tiến trình mới |
| Main-service restart sau render | NOT_PERFORMED_POLICY_BLOCKED; không ghi PASS. Actual restart checkpoint trước vẫn có evidence |
| Audio transport/source | 25 trimmed scene PCM units khớp raw sources sample-exact; 8 reviewed targets khác tối đa 1 LSB do encoding lịch sử. MP4/raw correlation 0.99999478–0.99999564, decoded peak 0.7927–0.9001, actual decode bound to exact MP4 SHA; không chứng minh naturalness |
| Visual evidence | Independent sheet-scale inspection của 25 sampled frames PASS; ảnh trích đúng năm MP4 B. Không thay full moving-video/audio watch/listen |
| Human audio/final watch/listen | Năm video gốc rejected; repair01 01/02/04 rejected, 06/08 historically pending; tám B excerpts accepted; năm full B MP4 5/5 OWNER_APPROVED qua reply “Duyệt” |

[159 Native tests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/native-tests-boundary-final.log), [32 historical Studio tests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/studio-tests-storyboard.log), [actual B production verification](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/actual-verification.json), [fresh-process persistence](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/fresh-process-persistence.json), [PCM/codec/preview/final guards](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/audio-and-preview-checks.json). Earlier 139 Native tests and repair01 verification remain historical evidence, not current human audio acceptance.

Earlier fixture E2E covers research → five ideas → scores → selection → brief → Native render/guards with labelled test providers/decisions. It is not actual provider PASS or human acceptance and contributes zero videos to this gate. The five new production MP4s are distinct fresh actual jobs.

**Practical cases và human acceptance**

| Ca | Profile | Chủ đề | Ý tưởng ban đầu | Owner/current state |
|---|---|---|---:|---|
| 01 | Green Paradise | Thỏa thuận IHG | 5 | Brief/script/media/final APPROVED; PRODUCED; old project preserved |
| 02 | Green Paradise | Khởi động chứng nhận đô thị thông minh | 5 | Brief/script/media/final APPROVED; PRODUCED |
| 03 | Green Paradise | Hạ tầng/giới hạn suy luận | 5 | Unselected/PENDING |
| 04 | Saigon Park | Ba câu hỏi tìm hiểu dự án | 5 | Brief/script/media/final APPROVED; PRODUCED |
| 05 | Saigon Park | Văn phòng/sa bàn/trạng thái | 5 | Unselected/PENDING |
| 06 | Vang Nguyễn | Ngày đăng/kỳ báo cáo/hiện tại | 5 | Brief/script/media/final APPROVED; PRODUCED |
| 07 | Vang Nguyễn | Giá bình quân/giá một căn | 5 | Unselected/PENDING |
| 08 | Việt Nam | Giao dịch/nguồn cung/tồn kho Q2/2026 | 5 | Brief/script/media/final APPROVED; PRODUCED |
| 09 | Việt Nam | Tin giá nhà/ngân sách | 5 | Unselected/PENDING |
| 10 | Việt Nam | Đề xuất nhà giá rẻ/trạng thái chính sách | 5 | Unselected/PENDING |

Bảy tiêu chí từng ca nằm trong [practical-editorial-assessment.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/practical-editorial-assessment.md); nhận xét Codex không phải human acceptance hoặc đánh giá thống kê hiệu quả ranking. Các giới hạn hook/rank/duplicate/date được giữ. Năm lựa chọn Owner có brief/script/media/final decisions thật; năm ca còn lại chưa được chọn/duyệt, không gắn human PASS. Task VF-PHASE9K-CONTENT-INTELLIGENCE-ACCEPTANCE-01 xác định gate năm handoffs và năm watch/listen decisions; không yêu cầu render cả mười. Các PENDING trong bundle ban đầu là snapshot lịch sử, được giữ nguyên.

| Ca | MP4 B mới | Thực tế | Mục tiêu | Project revision | QC/integrity/persistence | Human final |
|---|---|---:|---|---:|---|---|
| 01 | [Xem/nghe bản B](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/case-01/final.mp4) | 33,715s | 30–45s | 13 | PASS | APPROVED, review 19 |
| 02 | [Xem/nghe bản B](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/case-02/final.mp4) | 39,605s | 45–60s, ngoại lệ được duyệt | 13 | PASS | APPROVED, review 20 |
| 04 | [Xem/nghe bản B](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/case-04/final.mp4) | 34,615s | 45s, ngoại lệ được duyệt | 13 | PASS | APPROVED, review 21 |
| 06 | [Xem/nghe bản B](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/case-06/final.mp4) | 35,475s | 45s, ngoại lệ được duyệt | 12 | PASS | APPROVED, review 22 |
| 08 | [Xem/nghe bản B](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/case-08/final.mp4) | 46,866667s | 45–60s | 12 | PASS | APPROVED, review 23 |

02/04/06 ngắn hơn mục tiêu; câu hỏi cuối đã báo từng thời lượng và Owner “Duyệt” chấp nhận các ngoại lệ này cùng năm video đầy đủ. Lời đọc v2 và speed preset được giữ nguyên; không đổi narration/speed hoặc gọi render để che khác biệt.

Nghiệm thu cuối: [reply và câu hỏi chính xác](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/final-acceptance/owner-final-authorization.json), [năm Native final review rows](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/final-acceptance/native-final-decisions.json), [queue PRODUCED](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/final-acceptance/produced-opportunities.json), [final verification](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/final-acceptance/final-verification.json) và [accepted fresh-process persistence](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/final-acceptance/accepted-fresh-process-persistence.json). Receipt SHA 7f4652e7b0925304821cafaa5da3add24fbb576e49bb8cc5e054c7fbc9d793a6; ghi lúc 06/10/2026 17:00 giờ Việt Nam. Approval này không cấp quyền publishing hoặc chứng nhận ASR word accuracy khách quan. [Verification observations](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/final-acceptance/verification-observations.md) giữ rõ transient offline/setup/helper assertion failures và kiểm chứng sau sửa assertion MIME đúng existing route; không sửa provider/pipeline.

**Evidence và screenshots**

Idea/brief bundle SHA 1ac01b244e396e3d53f76197b1c475e134275fd2c605463981fc3048ba5872e4; script v2 bundle SHA ba8f2a4572497fe59ece072f767d0d0a54f668304ebb090cfb9338d1bb287d1c; storyboard/media bundle SHA d9fe7af9329c5bc293a155b9f152fdd65730e3f1b6f83bb65149291a81ac7000. Tất cả giữ byte gốc.

[Original audio feedback](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/owner-feedback.json), [actual onset rejection receipts](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-02/owner-negative-decisions.json), [Owner B approval và pre-change backups](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/owner-B-approval.json), [new production snapshots](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/production-approval-manifest.json), [năm video B đầy đủ](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/review-bundle.md), [exact new MP4 manifest](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/review-manifest.json), [four boundary failures/recovery](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/boundary-failure-recovery-before.json), [same-job resumes](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/boundary-failure-recovery-resumed.json), [final review register](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/phase9k-final-review.md). Each new case includes portable actual sources/provider receipts and all failed/passing TTS attempts. Original media/source approvals, earlier MP4/WAVs and review bundles remain byte-exact historical evidence.

![Năm cảnh trích từ MP4 B mới ca 08](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/case-08/contact-sheet.png)

![Studio hiển thị final approval sau Owner duyệt](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/final-acceptance/studio-final-approved.jpg)

[Actual Studio queue DOM](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/final-acceptance/studio-produced-queue.json) ghi đúng năm PRODUCED sau acceptance; screenshot/DOM không tự tạo approval.

Năm contact sheets và 25 frame receipts được trích đúng actual B MP4 hashes. Screenshot/playback của repair01 giữ phạm vi lịch sử, không chứng minh video B mới được Owner xem/nghe. Static gallery cũ là historical storyboard preview. Dùng workspace links và Studio hiện có; Owner Chrome/draft cũ được giữ.

**Regression status và known limitations**

Không phát hiện hồi quy trong phạm vi Windows Native Phase 8 đã nghiệm thu. Dependencies, voice preset, production schema/tag không đổi; 10 Phase 8 MP4/evidence match baseline. Pre-B backup chứng minh 38 jobs, 335 events, 117 versions, 18 final review rows và 12 other projects nguyên vẹn; chỉ năm current projects được sửa theo scope. Khi chốt final, toàn bộ 43 jobs, 395 events, 122 versions, 17 projects và 18 prior review rows được giữ, thêm năm review rows 19–23. Intelligence giữ 259 current records còn lại và toàn bộ 389 prior versions/62 decisions/35 operations; đúng năm Opportunity chỉ thay status/version/updated_at sang PRODUCED, thêm 5 versions (tổng 394), giữ nguyên 62 decision rows. Old IHG history giữ nguyên. **1.034 frozen historical repository evidence files** giữ hash; original và repair01 raw WAV/MP4/review rows không bị thay. Năm video gốc rejected, ba repair01 onset rejections vẫn tồn tại; năm full B results hiện được Owner duyệt.

Thao tác dừng/khởi động lại main service sau render trước đây bị công cụ từ chối trước thực thi với “blocked by policy”; không retry hoặc ghi PASS cho lần đó. Lúc ghi final mới, inventory thực tế thấy không có listener 8026/Python process. Đã khởi động trusted existing Native service từ trạng thái offline, hidden process, không stop/kill process; preflight trước final xác nhận toàn bộ prior state. [Start-from-offline receipt](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/final-acceptance/native-start-from-offline.json) phân biệt lần start này với denied restart lịch sử. Tiến trình kiểm tra mới sau acceptance mở lại đúng accepted projects/jobs/reviews/queue/artifacts và table snapshots PASS. [Policy limitation](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/service-restart-policy-limitation.json) vẫn giữ nguyên; không tạo after-restart giả.

Research nhận URL cụ thể, chưa tự khám phá toàn thị trường hoặc đo trend velocity. Source-reported chưa là xác minh độc lập; publication unknown giữ nguyên; 403/size/JS/PDF báo lỗi rõ. Subtitles theo cụm từ thời lượng audio đo được, chưa word alignment. Owner đã duyệt cảm nhận đầy đủ năm bản B; visual/codec checks không tự chứng minh subjective quality. Legacy Docker/RC28 ngoài chứng nhận Native không được mở lại.

Warm context có hai authority receipts riêng: “Giọng B đạt” cho tám excerpt và “Duyệt” cho đúng năm full B MP4/duration exceptions. ASR có bất đồng với lời duyệt ở CTA “Để lại câu hỏi”, tên quốc tế như Crowne Plaza/Holiday Inn Express/Garner, ca04 “tách/dữ kiện”, số hoặc viết tắt; actual raw transcripts giữ nguyên. ASR disagreement không chứng minh TTS đọc sai, và không tự rewrite lời hoặc gắn word-accuracy PASS. Human final acceptance không biến raw ASR thành chứng nhận độ chính xác khách quan. Các boundary fallback giữ anchors/cut/raw evidence; F0 diagnostics lịch sử và waveform correlation không thay human acceptance. Phụ đề theo cụm ước lượng, chưa word alignment.

Không triển khai analytics learning, self-changing weights, winner detection, autonomous production/scheduling/publishing, agent swarm hoặc distributed orchestration.

**Blockers và next roadmap**

Không còn blocker của gate Phase 9K trong phạm vi Windows Native nội bộ. Đã có mười ca/50 ứng viên, năm approved brief handoffs, năm script/media reviews, năm actual new MP4, technical/integrity/persistence PASS và năm Owner watch/listen decisions; final downloads/PRODUCED queue/readiness đã xác nhận. Thời lượng ngoại lệ 02/04/06 được Owner duyệt trong câu hỏi cuối. Không có blocker credential/provider/migration/major architecture. Denied main-service restart lịch sử vẫn là giới hạn kiểm chứng được ghi rõ; service start từ offline và accepted fresh-process persistence có evidence riêng.

Roadmap tiếp theo nên cải thiện query relevance, duplicate ideas/source diversity và timestamp presentation bằng feedback thực tế, giữ human approval; chưa mở autonomous publishing/analytics learning. Năm ca chưa chọn vẫn chờ lựa chọn sau, không được tuyên bố human accepted.

CONTENT_INTELLIGENCE_READY = YES
