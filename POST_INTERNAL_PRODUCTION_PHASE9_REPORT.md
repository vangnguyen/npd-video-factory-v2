# POST INTERNAL PRODUCTION — PHASE 9

Ngày báo cáo: 06/10/2026, giờ Việt Nam.

Phần kỹ thuật Content Intelligence đã triển khai và qua kiểm tra trên Windows Native. Đã có 10 ca nghiên cứu thực tế, 50 ý tưởng có nguồn và điểm xếp hạng minh bạch. Phase 9K chưa nghiệm thu: chưa có lựa chọn/duyệt brief mới của Owner, chưa đưa đủ năm ý tưởng thực tế vào sản xuất và chưa có nghiệm thu các kết quả mới.

INTERNAL_PRODUCTION_READY = YES

**Mốc phát hành và SHA**

- Branch: `codex/vf-post-mvp-roadmap-execution-01`.
- Baseline SHA: `f61d8de6545653ea46f8ab5f91e6c0c0c167b7af`.
- Release marker: annotated tag `internal-production-v1` trỏ đúng baseline. Không viết lại lịch sử hoặc thay bằng chứng Phase 8.
- Final SHA của mã ứng dụng đã kiểm thử và đang chạy: `fc986b00ddab0dd4ab7003da4b4f48c2d57b4db8`.
- SHA chứa mã và bộ bằng chứng kỹ thuật tại lúc lập báo cáo: `7c13e2aa736011712dd621aeee01356e68026b02`. Commit lưu báo cáo này chỉ bổ sung tài liệu đánh giá; SHA của chính commit đó được xem trong Git history. Báo cáo không tự khai một SHA chưa tồn tại hoặc ngụ ý đã có nghiệm thu cuối Phase 9.

Các commit tiến dần: freeze `8f0aacc`; models/persistence `2d819c9`; research/ideas/scoring/profiles `3d1c391`; Studio/production bridge `3cd4aaf`; kiểm tra tương thích nguồn Windows `fc986b0`; bằng chứng kỹ thuật/10 ca `7c13e2a`.

Chi tiết baseline, dependency inventory, schema, 10 quyết định nghiệm thu và SHA của từng video: [release-baseline.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/release-baseline.md), [release-baseline.json](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/release-baseline.json).

**Trạng thái các subphase**

| Phase | Trạng thái | Bằng chứng chính |
|---|---|---|
| 9A — Freeze | PASS | Baseline chính xác, annotated tag, backup nhất quán |
| 9B — Domain | PASS kỹ thuật | Tám canonical models, ID/version/provenance, history integrity |
| 9C — Research | PASS phạm vi URL nguồn | Truy xuất thực tế, trích nguyên văn, nguồn/timestamp/hash được lưu; usefulness chờ người duyệt |
| 9D — Ideas | PASS kỹ thuật và actual provider | 10 lần sinh hợp lệ, mỗi lần năm ứng viên |
| 9E — Scoring | PASS kỹ thuật | Mười thành phần/weights/rationale, HEURISTIC_SCORING; usefulness chờ người duyệt |
| 9F — Studio review | PASS triển khai/kiểm thử | Chọn/sửa/bỏ/tạo lại/duyệt brief; lựa chọn thực tế chưa có |
| 9G — Pipeline bridge | PASS tích hợp kiểm thử | Tái dùng pipeline Native, có MP4 thật trong fixture; sản xuất thực tế còn chờ |
| 9H — Profiles | PASS | Bốn profile và bộ ca 3/2/2/3 nằm trong cấu hình |
| 9I — Queue | PASS kỹ thuật | Sáu trạng thái, chỉ PRODUCED khi final video qua guard nghiệm thu/hash |
| 9J — Tests | PASS phạm vi kỹ thuật | 126 native + 31 Studio; persistence, restart, provenance, failure paths |
| 9K — Practical acceptance | PENDING | 10 ca/50 ý tưởng sẵn sàng, 0/5 handoff thực tế, human acceptance chưa có |

Các trường PHASE, STATUS, HEAD SHA, FILES CHANGED, TESTS, EVIDENCE, NEW CAPABILITIES, REGRESSIONS, BLOCKERS và NEXT ACTION được ghi trong [domain-model.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/domain-model.md), [engines-and-profiles.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/engines-and-profiles.md) và [studio-pipeline-and-verification.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/studio-pipeline-and-verification.md).

**Bổ sung kiến trúc**

Tám model dùng chung gồm ResearchSource, ResearchFinding, TrendSignal, Opportunity, ContentIdea, ContentBrief, IdeaScore và ResearchRun. Mỗi record có stable ID, created_at, updated_at, version và provenance. Giá trị Green Paradise/Saigon Park/Vang Nguyễn/nội dung thị trường nằm trong cấu hình; core model không chứa tên dự án kinh doanh.

Dữ liệu mới nằm ở `C:\NPD-Video-Factory\phase2\intelligence.sqlite3`, schema version 1, tách khỏi database sản xuất đã nghiệm thu. Có version history, quyết định người duyệt và operation receipts. Production schema hiện có được giữ nguyên. Lineage mới dùng `content-intelligence-lineage-v1`; canonical timeline vẫn phiên bản 1.1.

ResearchProvider nhận query/context và trả findings có cấu trúc. Provider đang dùng nhận 1–5 URL HTTPS công khai được nhập hoặc cấu hình. Nó lưu bài nguồn/đoạn văn/receipt, query, thời điểm, metadata và SHA. Findings phân biệt SOURCE_REPORTED, INFERENCE và UNRESOLVED. Trích dẫn đúng nguồn không được gọi là xác minh độc lập tính đúng của nguồn. Không biết ngày đăng thì giữ unknown; ngày lấy không thay ngày công bố.

IdeaProvider tái dùng OpenAI `gpt-6-luna` và credential đã tồn tại để sinh năm ứng viên. Candidate phải tham chiếu đúng source/finding đã lưu. Các góc/hook/talking points/rationale do model tạo được ghi rõ là đề xuất biên tập. Có 13 phản hồi provider thực tế được nhận, 10 kết quả hợp lệ và ba kết quả bị từ chối vì tham chiếu không hợp lệ. Phản hồi lỗi được giữ; chỉ tạo operation mới sau kết quả đã biết, không tự phát lại request có kết quả chưa rõ. Không thêm provider trả phí hoặc credential mới.

Scoring có mười dimensions theo yêu cầu, weights trong cấu hình, component scores, final score, rationale, thời điểm và config hash. Nhãn HEURISTIC_SCORING xuất hiện trong dữ liệu và Studio. Chưa có cơ sở thống kê để dự báo lượt xem/lead; novelty và risk cũng chỉ là proxy biên tập.

Studio có vùng [Nghiên cứu & ý tưởng](http://127.0.0.1:8026/intelligence), Opportunity Queue và bước chọn/sửa/bỏ/tạo lại ứng viên, sửa/duyệt brief. Thay ý tưởng, tạo lại hoặc sửa brief làm mất hiệu lực duyệt cũ. Phiên bản cũ được giữ. Handoff explicit chỉ tạo project Native với kịch bản chưa được duyệt, không tự chạy TTS/render.

Research → Idea → approved Brief được đóng băng trong project sản xuất; script/storyboard/job/canonical timeline/render giữ lineage và source hashes. Pipeline Phase 1–8, script review, voice preset, media/editor, preview và final approval được tái sử dụng. Không tạo pipeline video thứ hai hoặc bước xuất bản tự động.

**Kiểm thử và bằng chứng**

| Kiểm tra | Kết quả |
|---|---|
| Native unit/integration/failure suite | 126/126 PASS: 103 bài cũ + 23 bài Content Intelligence |
| Studio suite | 31/31 PASS: 27 bài cũ + 4 bài Content Intelligence |
| Actual research + idea generation | 10 ca, 50 ứng viên hợp lệ; actual provider được phân loại riêng |
| Quote/reference/history/source tamper | PASS; dữ kiện thiếu nguồn và byte bị sửa bị từ chối |
| Persistence/fresh-process restart | PASS; record/version/decision/operation hashes giữ nguyên |
| Khởi động lại server thực tế | PASS; cả production và intelligence table hashes giữ nguyên, health ready |
| Nguồn 10 ca sau restart | PASS; không viết lại nguồn, receipt hoặc bộ brief |
| Research → five ideas → scores → selection → brief → existing pipeline → MP4 | PASS trong fixture cô lập, render FFmpeg thật, 11/11 QC checks PASS |
| Final review/download/queue guard | PASS trong fixture; không tính là nghiệm thu Owner |

Fixture MP4 sử dụng provider/decision kiểm thử có nhãn rõ và audio đã nghiệm thu; không tạo TTS inference mới. Nó chứng minh đường tích hợp/render/provenance, không được tính vào năm sản phẩm thực tế hoặc human acceptance. SHA MP4: `e2315022fe6951f988cda17ae4d1f5b7cde7b6a731f62723ad43b19260b9e909`.

Log kiểm thử, lỗi ban đầu, ba phản hồi provider bị từ chối và các research run thất bại được giữ. Lỗi HTTP 403, giới hạn kích thước trang và lỗi định dạng newline Windows đều có dấu vết. Sửa tương thích chỉ chấp nhận nội dung cũ khi tái dựng đúng hash gốc; nguồn và brief đã gửi duyệt không bị thay đổi.

Bằng chứng: [technical-acceptance-checkpoint.json](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/technical-acceptance-checkpoint.json), [actual-provider-ledger.json](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/actual-provider-ledger.json), [native-tests-final.log](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/native-tests-final.log), [studio-tests.log](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/studio-tests.log), [final-runtime-restart-verification.json](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/final-runtime-restart-verification.json), [render-contract.json](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/render-contract.json).

**Mười ca thực tế và nghiệm thu**

| Ca | Profile | Chủ đề đầu vào | Ý tưởng | Human acceptance |
|---|---|---|---:|---|
| 01 | Green Paradise | Hợp tác IHG và trạng thái vận hành | 5 | PENDING |
| 02 | Green Paradise | Khởi động quá trình chứng nhận và kết quả | 5 | PENDING |
| 03 | Green Paradise | Tin hạ tầng và giới hạn suy luận | 5 | PENDING |
| 04 | Saigon Park | Kiểm tra nguồn/thời điểm bài giới thiệu | 5 | PENDING |
| 05 | Saigon Park | Văn phòng/sa bàn và trạng thái dự án | 5 | PENDING |
| 06 | Vang Nguyễn | Cách kiểm tra nguồn và thời điểm bản tin | 5 | PENDING |
| 07 | Vang Nguyễn | Giá bình quân và giá một căn | 5 | PENDING |
| 08 | Việt Nam | Giao dịch, nguồn cung và tồn kho | 5 | PENDING |
| 09 | Việt Nam | Đọc tin giá nhà và ngân sách | 5 | PENDING |
| 10 | Việt Nam | Đề xuất nhà giá rẻ và trạng thái chính sách | 5 | PENDING |

Đánh giá riêng cả bảy tiêu chí cho từng ca nằm trong [practical-editorial-assessment.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/practical-editorial-assessment.md). Đây là nhận xét Codex, không phải human acceptance. Nhận xét nêu cả điểm hữu ích và giới hạn: năm ca dự án chưa biết ngày đăng; một số hook còn dài/chung; hạng 1 chưa luôn bám chủ đề hơn ứng viên dưới; ca 09 chưa giải đáp đủ ngân sách cụ thể; ca 10 có các đoạn gần trùng nhau. Những giới hạn này không được che bằng điểm xếp hạng.

[Bộ 10 ca và brief đề xuất](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/idea-brief-review-bundle.md) và [manifest](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/idea-brief-review-manifest.json) đã gửi Owner. Đề xuất chọn 01, 02, 04, 06, 08, mỗi ca ứng viên hạng 1; Owner có thể sửa, từ chối hoặc chọn ứng viên khác. Chưa ghi nhận bất kỳ duyệt brief Phase 9 nào. Bundle SHA256 `1ac01b244e396e3d53f76197b1c475e134275fd2c605463981fc3048ba5872e4`; manifest SHA256 `32e0ad2b4052d77ca46e833dd23d8bd462868d8ece8104ad19bca13ffe63a19e`. Git giữ nguyên các byte được dùng để duyệt.

Sản xuất thực tế Phase 9 tại checkpoint: 0/5 handoff, 0 video cuối mới, 0 human acceptance. Nghiệm thu Phase 8 không được dùng để duyệt các chủ đề, kịch bản hoặc video mới này.

**Studio và hình ảnh bằng chứng**

![Studio với nguồn và ý tưởng thực tế](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/content-intelligence-ranked-ideas.png)

Trang thực tế đã được mở lại sau restart và giữ để Owner duyệt. [Ảnh sau restart](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/content-intelligence-final-runtime.png) ghi nhận runtime cuối. Ảnh `ui-fixture-approved-brief.png` và `ui-fixture-native-handoff.png` chỉ chứng minh tương tác trong môi trường kiểm thử cô lập; không đại diện cho quyết định của Owner trên dữ liệu thật.

**Hồi quy và giới hạn**

Không phát hiện hồi quy trong phạm vi Windows Native đã nghiệm thu: 103/27 kiểm tra cũ vẫn PASS; schema và toàn bộ row hashes của dữ liệu sản xuất giữ nguyên; tất cả bằng chứng Phase 8 và byte của 10 MP4 đã duyệt khớp baseline. Phiên bản runtime/dependency/voice preset không đổi. Legacy Docker/RC28 nằm ngoài chứng nhận Native và không được mở lại hoặc khai PASS.

Provider nghiên cứu hiện lấy các URL nguồn cụ thể, chưa tự khám phá thị trường, đo trend velocity hoặc tổng hợp mọi nguồn có liên quan. Nội dung được nguồn công bố chưa phải chân lý được xác minh độc lập. Trang quá lớn, trả 403, cần JavaScript hoặc PDF chưa được provider này hỗ trợ; lỗi được báo rõ.

Chưa có học từ analytics, tự đổi weights, winner detection, autonomous production, scheduling, publishing, agent swarm hoặc distributed orchestration. Media quyền sử dụng, thời lượng lời đọc thực tế, chất lượng hook và phù hợp thương hiệu vẫn cần kiểm tra ở từng sản phẩm mới.

**Blockers và bước tiếp theo**

1. Owner chọn/sửa/bỏ ý tưởng và duyệt ít nhất năm brief mới, gắn đúng phiên bản/nội dung đã xem.
2. Chuyển các brief đó vào pipeline Native, tạo kịch bản/media để Owner duyệt riêng trước TTS/render.
3. Sản xuất các kết quả mới, kiểm tra provenance/QC và ghi nhận human acceptance theo Phase 9K, gồm đánh giá thực tế mười ca.

Các bước này đang chờ quyết định nội dung của con người theo Phase 9F/G/K và nguyên tắc “No automatic production without explicit user action”. Không có blocker về credential mới, provider mới, migration mất dữ liệu hoặc thay kiến trúc lớn.

Khuyến nghị roadmap: hoàn tất nghiệm thu thực tế Phase 9 trước; sau đó cải thiện độ bám query, trùng lặp nguồn/ý tưởng và trình bày timestamp từ phản hồi thật của người dùng. Duy trì workflow internal và các điểm duyệt đã có. Chưa chuyển sang xuất bản tự động hoặc học scoring từ dữ liệu chưa tồn tại.

CONTENT_INTELLIGENCE_READY = NO
