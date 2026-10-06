# POST INTERNAL PRODUCTION — PHASE 9

Ngày báo cáo: 06/10/2026, giờ Việt Nam.

Phần kỹ thuật Content Intelligence đã triển khai và qua kiểm tra trên Windows Native. Bộ ban đầu có 10 ca nghiên cứu thực tế và 50 ý tưởng có nguồn, điểm xếp hạng minh bạch. Theo quyết định mới `VF-PHASE9K-CONTENT-INTELLIGENCE-ACCEPTANCE-01`, năm brief 01/02/04/06/08 đã được Owner chọn/duyệt và chuyển vào năm dự án Native thật. Đã có năm phản hồi tạo kịch bản thật và năm bản v2 được Codex biên tập để Owner duyệt. Điểm dừng hiện tại là **PHASE9K_SCRIPT_REVIEW_REQUIRED**: chưa duyệt kịch bản/storyboard/media, chưa chạy TTS/render và chưa có video mới. Phase 9K chưa PASS.

INTERNAL_PRODUCTION_READY = YES

**Mốc phát hành và SHA**

- Branch: `codex/vf-post-mvp-roadmap-execution-01`.
- Baseline SHA: `f61d8de6545653ea46f8ab5f91e6c0c0c167b7af`.
- Release marker: annotated tag `internal-production-v1` trỏ đúng baseline. Không viết lại lịch sử hoặc thay bằng chứng Phase 8.
- Final SHA của mã ứng dụng đã kiểm thử và đang chạy: `4b2f67faea5687ab97a4c64c3789216de48c8bf3`.
- HEAD SHA chứa bản v2 và bộ bằng chứng script/restart tại lúc lập báo cáo: `8ad83466bb7e1528a1157dc5c8840f908d0428ce`. Commit lưu bản báo cáo cập nhật này chỉ bổ sung tài liệu; SHA của chính commit đó được xem trong Git history và lời bàn giao. Báo cáo không tự khai SHA của một commit chưa tồn tại hoặc ngụ ý đã có nghiệm thu cuối Phase 9.

Các commit tiến dần: freeze `8f0aacc`; models/persistence `2d819c9`; research/ideas/scoring/profiles `3d1c391`; Studio/production bridge `3cd4aaf`; tương thích nguồn Windows `fc986b0`; kỹ thuật/10 ca `7c13e2a`; script policy theo brief `bf4ec72`; năm brief Owner duyệt và bảo toàn handoff cũ `e4ee6c2`; năm script provider thật `4b2f67f`; năm bản v2/persistence/restart `8ad8346`. Quyết định thực tế của Owner nằm trong evidence; kiểm tra biên tập của Codex không được ghi thành Owner script approval.

Chi tiết baseline, dependency inventory, schema, 10 quyết định nghiệm thu và SHA của từng video: [release-baseline.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/release-baseline.md), [release-baseline.json](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/release-baseline.json).

**Trạng thái các subphase**

| Phase | Trạng thái | Bằng chứng chính |
|---|---|---|
| 9A — Freeze | PASS | Baseline chính xác, annotated tag, backup nhất quán |
| 9B — Domain | PASS kỹ thuật | Tám canonical models, ID/version/provenance, history integrity |
| 9C — Research | PASS phạm vi URL nguồn | Truy xuất thực tế, trích nguyên văn, nguồn/timestamp/hash được lưu; usefulness chờ người duyệt |
| 9D — Ideas | PASS kỹ thuật và actual provider | 10 lần sinh hợp lệ, mỗi lần năm ứng viên |
| 9E — Scoring | PASS kỹ thuật | Mười thành phần/weights/rationale, HEURISTIC_SCORING; usefulness chờ người duyệt |
| 9F — Studio review | PASS triển khai/kiểm thử; brief review thực tế 5/5 | Owner chọn/duyệt năm brief; script/storyboard/media review còn chờ |
| 9G — Pipeline bridge | PASS tích hợp; 5/5 handoff/script thật | Tái dùng Native; 5 phản hồi script thật, 0 MP4 mới ở gate hiện tại |
| 9H — Profiles | PASS | Bốn profile và bộ ca 3/2/2/3 nằm trong cấu hình |
| 9I — Queue | PASS kỹ thuật | Sáu trạng thái, chỉ PRODUCED khi final video qua guard nghiệm thu/hash |
| 9J — Tests | PASS phạm vi kỹ thuật | 129 native + 31 Studio; fresh-process/actual restart, provenance, failure paths |
| 9K — Practical acceptance | PHASE9K_SCRIPT_REVIEW_REQUIRED | 5/5 brief/handoff/script drafts; 0/5 script approvals và 0/5 video mới |

Các trường PHASE, STATUS, HEAD SHA, FILES CHANGED, TESTS, EVIDENCE, NEW CAPABILITIES, REGRESSIONS, BLOCKERS và NEXT ACTION được ghi trong [domain-model.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/domain-model.md), [engines-and-profiles.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/engines-and-profiles.md), [studio-pipeline-and-verification.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/studio-pipeline-and-verification.md), và checkpoint mới [phase9k-handoff-matrix.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/phase9k-handoff-matrix.md). Các checkpoint cũ được giữ theo thời điểm, không sửa để giả lập kết quả mới.

**Bổ sung kiến trúc**

Tám model dùng chung gồm ResearchSource, ResearchFinding, TrendSignal, Opportunity, ContentIdea, ContentBrief, IdeaScore và ResearchRun. Mỗi record có stable ID, created_at, updated_at, version và provenance. Giá trị Green Paradise/Saigon Park/Vang Nguyễn/nội dung thị trường nằm trong cấu hình; core model không chứa tên dự án kinh doanh.

Dữ liệu mới nằm ở `C:\NPD-Video-Factory\phase2\intelligence.sqlite3`, schema version 1, tách khỏi database sản xuất đã nghiệm thu. Có version history, quyết định người duyệt và operation receipts. Production schema hiện có được giữ nguyên. Lineage mới dùng `content-intelligence-lineage-v1`; canonical timeline vẫn phiên bản 1.1.

ResearchProvider nhận query/context và trả findings có cấu trúc. Provider đang dùng nhận 1–5 URL HTTPS công khai được nhập hoặc cấu hình. Nó lưu bài nguồn/đoạn văn/receipt, query, thời điểm, metadata và SHA. Findings phân biệt SOURCE_REPORTED, INFERENCE và UNRESOLVED. Trích dẫn đúng nguồn không được gọi là xác minh độc lập tính đúng của nguồn. Không biết ngày đăng thì giữ unknown; ngày lấy không thay ngày công bố.

IdeaProvider tái dùng OpenAI `gpt-6-luna` và credential đã tồn tại để sinh năm ứng viên. Candidate phải tham chiếu đúng source/finding đã lưu. Các góc/hook/talking points/rationale do model tạo được ghi rõ là đề xuất biên tập. Ledger của bộ mười ca ban đầu ghi 13 phản hồi thực tế: 10 kết quả hợp lệ và ba kết quả bị từ chối vì tham chiếu không hợp lệ. Ledger này giữ nguyên phạm vi lịch sử; Owner đã tạo generation mới của ca 01 trong Studio sau đó. Phản hồi lỗi được giữ; chỉ tạo operation mới sau kết quả đã biết, không tự phát lại request có kết quả chưa rõ. Không thêm provider trả phí hoặc credential mới.

Scoring có mười dimensions theo yêu cầu, weights trong cấu hình, component scores, final score, rationale, thời điểm và config hash. Nhãn HEURISTIC_SCORING xuất hiện trong dữ liệu và Studio. Chưa có cơ sở thống kê để dự báo lượt xem/lead; novelty và risk cũng chỉ là proxy biên tập.

Studio có vùng [Nghiên cứu & ý tưởng](http://127.0.0.1:8026/intelligence), Opportunity Queue và bước chọn/sửa/bỏ/tạo lại ứng viên, sửa/duyệt brief. Thay ý tưởng, tạo lại hoặc sửa brief làm mất hiệu lực duyệt cũ. Phiên bản cũ được giữ. Handoff explicit chỉ tạo project Native với kịch bản chưa được duyệt, không tự chạy TTS/render.

Research → Idea → approved Brief được đóng băng trong project sản xuất; script/storyboard/job/canonical timeline/render giữ lineage và source hashes. Pipeline Phase 1–8, script review, voice preset, media/editor, preview và final approval được tái sử dụng. Không tạo pipeline video thứ hai hoặc bước xuất bản tự động.

Ca 01 đã có một brief khác được Owner duyệt/handoff trong Studio trước task mới. Generation 1 được review trước đó đã bị thay thế khi Owner tạo lại ứng viên. Task mới lấy Rank #1 của generation hiện tại rồi sao chép nghiên cứu/ứng viên có provenance sang run mới để áp dụng chỉnh sửa; giữ nguyên dự án, brief và lịch sử mà Owner đã handoff. Run mới dùng lại nguồn/receipt/thời điểm gốc và tham chiếu original IDs; không truy xuất nguồn hoặc gọi idea provider thêm. Kiểm thử chứng minh dữ liệu cũ và project đang được khóa không bị thay.

Script generation tái dùng hàm native đã có và giọng đã nghiệm thu. Chỉ với đầu vào Content Intelligence, instructions lấy khoảng thời lượng từ approved brief và yêu cầu hook/CTA/tiếng Việt tự nhiên, bối cảnh thời gian, cảnh chưa duyệt và không đưa ghi chú Owner/TTS/runtime vào lời đọc. Mặc định của các dự án Native cũ được giữ. Năm actual content jobs nhận năm phản hồi `gpt-6-luna` completed, mỗi job một call; request/response/result gốc và model/usage/ID/hash được lưu. Một bản gốc có ghi chú nội bộ lọt vào lời đọc và một số đoạn còn dài; năm bản v2 được biên tập/lưu bằng Native Store, không gọi thêm provider. Bản gốc và sửa đổi có version/hash riêng, approval vẫn trống.

**Kiểm thử và bằng chứng**

| Kiểm tra | Kết quả |
|---|---|
| Native unit/integration/failure suite | 129/129 PASS: 103 bài cũ + 26 bài Content Intelligence; chạy lại sau thay đổi ứng dụng cuối |
| Studio suite | 31/31 PASS: 27 bài cũ + 4 bài Content Intelligence; code Studio không đổi ở task handoff mới |
| Actual research + idea generation | Bộ ban đầu 10 ca/50 ứng viên hợp lệ; actual provider phân loại riêng |
| Owner-approved real handoffs | 5/5 brief v3 → Native project → actual content job; nguồn/điểm/lineage/versions được lưu |
| Actual script provider | 5 completed responses / 5 calls; v1 gốc giữ nguyên, v2 Codex biên tập, 0 calls thêm |
| Quote/reference/history/source tamper | PASS; dữ kiện thiếu nguồn và byte bị sửa bị từ chối |
| Persistence/fresh-process restart | PASS; record/version/decision/operation hashes giữ nguyên |
| Khởi động lại server thực tế sau handoff | PASS; toàn bộ table hashes trước/sau restart giữ nguyên, health ready; 5/5 project v3 mở lại đúng v2 |
| Nguồn 10 ca sau restart | PASS; không viết lại nguồn, receipt hoặc bộ brief |
| Research → five ideas → scores → selection → brief → existing pipeline → MP4 | PASS trong fixture cô lập, render FFmpeg thật, 11/11 QC checks PASS |
| Final review/download/queue guard | PASS trong fixture; không tính là nghiệm thu Owner |

Fixture MP4 sử dụng provider/decision kiểm thử có nhãn rõ và audio đã nghiệm thu; không tạo TTS inference mới. Nó chứng minh đường tích hợp/render/provenance, không được tính vào năm sản phẩm thực tế hoặc human acceptance. SHA MP4: `e2315022fe6951f988cda17ae4d1f5b7cde7b6a731f62723ad43b19260b9e909`.

Log kiểm thử, lỗi ban đầu, ba phản hồi provider bị từ chối và các research run thất bại được giữ. Lỗi HTTP 403, giới hạn kích thước trang và lỗi định dạng newline Windows đều có dấu vết. Sửa tương thích chỉ chấp nhận nội dung cũ khi tái dựng đúng hash gốc; nguồn và brief đã gửi duyệt không bị thay đổi.

Bằng chứng: [technical-acceptance-checkpoint.json](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/technical-acceptance-checkpoint.json), [actual-provider-ledger.json](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/actual-provider-ledger.json), [native-tests-final.log](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/native-tests-final.log), [studio-tests.log](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/studio-tests.log), [final-runtime-restart-verification.json](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/final-runtime-restart-verification.json), [render-contract.json](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/render-contract.json).

Bằng chứng mới: [Owner authorization](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/owner-authorization.json), [five actual script responses](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/actual-script-provider-ledger.json), [129 native tests](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/native-tests-final.log), [restart/source/data preservation](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/script-review-after-restart.json), và [handoff matrix](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/phase9k-handoff-matrix.md). Kiểm tra source integrity/lineage chứng minh đúng tham chiếu và byte, không khẳng định tính đúng độc lập của mọi phát biểu trong bài nguồn.

**Mười ca thực tế và nghiệm thu**

| Ca | Profile | Chủ đề đầu vào | Ý tưởng trong bộ ban đầu | Owner decision hiện tại |
|---|---|---|---:|---|
| 01 | Green Paradise | Hợp tác IHG và trạng thái vận hành | 5 | Brief APPROVE_WITH_EDIT; script v2 PENDING; giữ dự án cũ và fork generation hiện tại |
| 02 | Green Paradise | Khởi động quá trình chứng nhận và kết quả | 5 | Brief APPROVE_WITH_EDIT; script v2 PENDING |
| 03 | Green Paradise | Tin hạ tầng và giới hạn suy luận | 5 | PENDING |
| 04 | Saigon Park | Ba câu hỏi hữu ích khi tìm hiểu dự án | 5 | Brief APPROVE_WITH_EDIT; script v2 PENDING |
| 05 | Saigon Park | Văn phòng/sa bàn và trạng thái dự án | 5 | PENDING |
| 06 | Vang Nguyễn | Ngày đăng/kỳ báo cáo/thời điểm hiện tại | 5 | Brief APPROVE; script v2 PENDING |
| 07 | Vang Nguyễn | Giá bình quân và giá một căn | 5 | PENDING |
| 08 | Việt Nam | Giao dịch, nguồn cung và tồn kho quý II/2026 | 5 | Brief APPROVE; script v2 PENDING |
| 09 | Việt Nam | Đọc tin giá nhà và ngân sách | 5 | PENDING |
| 10 | Việt Nam | Đề xuất nhà giá rẻ và trạng thái chính sách | 5 | PENDING |

Đánh giá riêng cả bảy tiêu chí cho từng ca nằm trong [practical-editorial-assessment.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/practical-editorial-assessment.md). Đây là nhận xét Codex, không phải human acceptance. Nhận xét nêu cả điểm hữu ích và giới hạn: năm ca dự án chưa biết ngày đăng; một số hook còn dài/chung; hạng 1 chưa luôn bám chủ đề hơn ứng viên dưới; ca 09 chưa giải đáp đủ ngân sách cụ thể; ca 10 có các đoạn gần trùng nhau. Những giới hạn này không được che bằng điểm xếp hạng.

[Bộ 10 ca và brief đề xuất](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/idea-brief-review-bundle.md) và [manifest](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/idea-brief-review-manifest.json) đã gửi Owner trước đó và giữ nguyên byte. Owner đã trả quyết định chọn/duyệt 01/02/04/06/08, mỗi ca Rank #1, cùng chỉnh sửa và gate chỉ tạo script. Ca 01 có khác biệt generation được ghi rõ ở phần kiến trúc và handoff matrix. Bundle gốc SHA256 `1ac01b244e396e3d53f76197b1c475e134275fd2c605463981fc3048ba5872e4`; manifest gốc SHA256 `32e0ad2b4052d77ca46e833dd23d8bd462868d8ece8104ad19bca13ffe63a19e`.

Checkpoint mới: **5/5 brief Owner-approved**, **5/5 real handoffs**, **5/5 actual script responses**, **0/5 script approvals**, **0/5 video cuối mới**, **0/5 human watch/listen decisions**. [Bộ năm lời đọc v2](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/script-review-bundle.md) có SHA256 `ba8f2a4572497fe59ece072f767d0d0a54f668304ebb090cfb9338d1bb287d1c`, kèm [manifest ràng buộc version/hash](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/script-review-manifest.json). Nghiệm thu Phase 8 và fixture MP4 không được dùng để duyệt hoặc tính vào sản phẩm mới. Storyboard/media chưa được duyệt; không có `ffprobe.json` hoặc `final.mp4` giả để điền đủ danh sách evidence.

**Studio và hình ảnh bằng chứng**

![Studio với nguồn và ý tưởng thực tế](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/content-intelligence-ranked-ideas.png)

Ảnh trên và [ảnh checkpoint kỹ thuật trước](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/content-intelligence-final-runtime.png) là bằng chứng theo thời điểm. Ảnh `ui-fixture-approved-brief.png` và `ui-fixture-native-handoff.png` chỉ chứng minh tương tác trong môi trường kiểm thử cô lập.

![Studio thật sau handoff và restart, lời đọc v2 chưa duyệt](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/script-review-studio.png)

Studio đã mở lại ca 01 revision 3 sau actual restart, hiển thị lời đọc v2 và chưa có media/video. Các ca khác được đối chiếu qua live API và fresh process. Cửa sổ/draft cũ của Owner được giữ. Bộ năm lời đọc đã lưu trong review bundle để Owner duyệt từng bản.

**Hồi quy và giới hạn**

Không phát hiện hồi quy trong phạm vi Windows Native đã nghiệm thu: 103/27 kiểm tra cũ vẫn PASS; schema và từng row sản xuất có sẵn vẫn khớp backup. Dữ liệu mới được thêm do năm handoff, content jobs và draft versions được Owner cho phép; không đòi whole-table hashes khớp baseline sau khi thêm record. Whole-table hashes trước/sau restart cuối khớp nhau. Cả 12 project trước task, 23 job và 10 render review cũ được giữ; 19 record của run ca 01 cũ và toàn bộ intelligence version/decision/operation history trước task nguyên vẹn. Tất cả bằng chứng Phase 8 và byte của 10 MP4 đã duyệt khớp baseline. Runtime/dependency/voice preset không đổi. Legacy Docker/RC28 nằm ngoài chứng nhận Native và không được mở lại hoặc khai PASS.

Provider nghiên cứu hiện lấy các URL nguồn cụ thể, chưa tự khám phá thị trường, đo trend velocity hoặc tổng hợp mọi nguồn có liên quan. Nội dung được nguồn công bố chưa phải chân lý được xác minh độc lập. Trang quá lớn, trả 403, cần JavaScript hoặc PDF chưa được provider này hỗ trợ; lỗi được báo rõ.

Chưa có học từ analytics, tự đổi weights, winner detection, autonomous production, scheduling, publishing, agent swarm hoặc distributed orchestration. Media quyền sử dụng, thời lượng lời đọc thực tế, chất lượng hook và phù hợp thương hiệu vẫn cần kiểm tra ở từng sản phẩm mới.

Ngày đăng vẫn unknown trong metadata của một số nguồn dự án; retained page có thể chứa ngày hiển thị nhưng chưa được model trích thành canonical timestamp. Không tự sửa source record/hash đã review hoặc lấy ngày retrieval làm publication. Hook/scoring/CTA mới đã được Codex biên tập nhưng chưa có Owner đánh giá kịch bản; số token lời đọc không chứng minh thời lượng thực tế. Chưa gọi TTS để đo vì Owner yêu cầu dừng trước sản xuất.

**Blockers và bước tiếp theo**

1. Owner duyệt/sửa/từ chối đúng năm script **v2** của 01/02/04/06/08; brief approval hiện có không phải script approval.
2. Duyệt riêng storyboard và media/rights trước khi dùng production approval hiện có; chưa tạo TTS/render từ quyết định chỉ duyệt lời đọc.
3. Tạo năm MP4 mới qua pipeline Native, lưu actual ffprobe/QC/hash/persistence, rồi ghi năm quyết định human watch/listen cho đúng final artifact. Hoàn tất đánh giá thực tế theo Phase 9K.

Task `VF-PHASE9K-CONTENT-INTELLIGENCE-ACCEPTANCE-01` yêu cầu nguyên văn: “Generate all five scripts first” rồi “Then STOP at: PHASE9K_SCRIPT_REVIEW_REQUIRED”. Đây là điểm dừng do Owner yêu cầu. [Final review register](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/phase9k-final-review.md) ghi rõ mọi gate còn chờ. Không có blocker về credential mới, provider mới, migration mất dữ liệu hoặc thay kiến trúc lớn.

Khuyến nghị roadmap: hoàn tất nghiệm thu thực tế Phase 9 trước; sau đó cải thiện độ bám query, trùng lặp nguồn/ý tưởng và trình bày timestamp từ phản hồi thật của người dùng. Duy trì workflow internal và các điểm duyệt đã có. Chưa chuyển sang xuất bản tự động hoặc học scoring từ dữ liệu chưa tồn tại.

CONTENT_INTELLIGENCE_READY = NO
