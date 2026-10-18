# VF-DRAMA-CASTING-SAVE-NEXT-STEP-FIX-06

Ngày 18/10/2026. Sửa riêng bước **Nhân vật & giọng → Hình ảnh & cảnh**; không mở tính năng mới. Application/code HEAD **2b8ff625cfcb299642367b8ac2bfa2f07f94c0bd**, source **C:/vfdr06**, nhánh **codex/vf-drama-casting-next-step-06**, build **drama-casting-next-06**, URL **http://127.0.0.1:62684/**. Commit báo cáo sau candidate chỉ đổi tài liệu/bằng chứng. About giữ HEAD đã nạp lúc khởi chạy; bốn module frontend đã đối chiếu đúng hash, Cache-Control=no-store. Không reset về baseline.

## Chẩn đoán đã xác nhận

Source thực tế trước sửa là C:/vfdr05, application HEAD 758466ed97cdd6c204bed3f6d1e7fd06a6db807c, repository HEAD d056c3f57a5d98f13beecefe463e54e491d40bd2. Phần chênh chỉ là báo cáo/evidence; không kết luận UI cũ vì SHA khác.

Server của phim Owner tại thời điểm kiểm tra: revision 8, casting version 4, characters_confirmed=true, 2/2 vai có thoại đã có giọng, An=Thái Sơn/Bình=Minh Đức, không narrator, không job hoạt động, không approval. Owner xác nhận các lựa chọn khớp form và không còn chỉnh sửa chưa lưu. Không đọc được form browser nên **không khẳng định dirty/dirtyPart/dialogueDirty/voiceDirty/pending/working/busy của phiên Owner**. Metadata server không chứng minh Owner chưa chọn hoặc chưa bấm Lưu; không có căn cứ nói Owner mở nhiều tab.

Tái hiện một tab, project riêng, HTTP Native thật và callback reload của UI thật:

- Chọn hai giọng rồi lưu bằng nút lưu riêng đã hoạt động trên baseline. Không suy diễn lỗi 05 quay lại.
- Sửa ghi chú tính cách sau xác nhận → autosave gửi confirm_characters=false → backend hạ characters_confirmed=false dù text/người nói/narrator không đổi. Casting version và lựa chọn vẫn còn, nhưng cờ xác nhận khóa bước tiếp. Ca trước sửa FAIL; sau sửa PASS.
- Khi form còn lựa chọn phân vai chưa lưu, Next cũ dựa vào global dirty và snapshot server; nó không gộp thao tác lưu/xác minh/chuyển bước. Thông báo “Cần lưu / kiểm tra phân vai trước khi tạo audio” cũng hiện khi server đã đủ giọng, gây nhầm điều kiện vào bước cảnh với điều kiện chuẩn bị audio.

Log: [baseline RED](../evidence/drama-casting-save-next-step-06/before-fix-n1.log), [integration sau sửa](../evidence/drama-casting-save-next-step-06/after-fix-n5.log). Chỉ log fixture nguyên bản, metadata/hashes; không token hoặc toàn bộ kịch bản Owner.

## Source và hành vi sửa

- `drama-workflow.mjs`: nút **Lưu phân vai & tiếp tục**, lý do cạnh nút và dẫn tới vai thiếu; hành động **Xác nhận người nói** ngay ở bước 2 khi thực sự thiếu xác nhận. Xác nhận vẫn do người dùng bấm. Giữ kiểm tra/tạo audio ở bước Dựng & xem thử.
- `native-drama.mjs`: can_continue_to_scenes riêng với can_prepare_dialogue_audio. Xét xác nhận, vai có thoại thiếu giọng, narrator policy, dirty riêng, quyền, active jobs, pending/busy; không đòi media/audio/approval/preview. Dropdown và voice card cùng cập nhật một casting draft. Vai không thoại không cần voice; trùng voice chỉ cảnh báo. Chọn lại đúng voice giữ vị trí binding, không tạo revision mới chỉ vì thứ tự mảng.
- Save lưu đúng request/CAS, đối chiếu receipt và GET cùng project/workspace/revision/payload. Chỉ clear dirty sau bằng chứng khớp. Đã lưu không đổi → GET kiểm tra rồi chuyển bước, không POST. POST mất phản hồi → giữ request cũ; đã có receipt nhưng GET lỗi → thử GET, không POST mới. Khóa yêu cầu song song, không gửi lại thao tác compile/take từ nút chuyển bước.
- Nháp/pending được giữ local theo workspace/project; mở lại đối chiếu đúng request. Phản hồi muộn không nhận vào phim khác. Xung đột thật giữ form, có **Sao chép phân vai đang chọn**, **Xem phân vai đã lưu**, và hành động chọn mốc sau khi đối chiếu. Không tắt CAS hoặc tự last-write-wins.
- `native.mjs`: callback Native thật dùng chung production reload bridge, receipt kiểm riêng cho casting. Cờ sửa kịch bản/ghi chú và phân vai độc lập; không xóa chỉnh sửa khác để mở nút.
- `production_workflows.py`: metadata-only notes/series/tập giữ xác nhận nếu raw text, parsed speaker assignments, input mode và narrator policy đều khớp. Không rebuild casting/timeline/audio cho ghi chú. Nội dung/người nói thực sự thay đổi vẫn cần xác nhận. Xác nhận lại tương thích giữ line/character/scene IDs và casting version.
- `drama_casting.py` / `drama-script-save.mjs`: receipt có workspace/request identity/hash, write revision, casting version/config, provider_calls=0 và human_approval_granted=false. Giữ journal/fingerprint/CAS/CSRF/permission hiện có; không migration phá hủy hoặc rewrite journal lịch sử.
- About build đổi qua `production_workflow_routes.py`.

Không TTS, render, approval hoặc khai báo quyền tự động. Không sửa nội dung hay chọn giọng thay Owner.

## Kiểm thử candidate cố định

| Phạm vi | Kết quả |
| --- | --- |
| Full Studio | **2168 PASS**, 0 fail/skip, 33.25s helper |
| Native liên quan | **80 PASS**, 0 fail/skip, 102.297s helper; unittest 98.473s |
| API liên quan | **92 PASS**, 0 fail/skip: final export quality, verified delivery, source asset delivery |
| Full renderer | **52 PASS**, 7 file |
| Renderer typecheck | **PASS** |
| Browser thật | **BLOCKED**; không screenshot / browser PASS |

80 Native parent tests có một parent chạy **15 ca casting HTTP/Studio callback** và một parent chạy **9 ca lưu kịch bản HTTP/callback**. Không cộng 24 ca con thành 104 Native tests. Metadata voice fixture là synthetic và có nhãn, không audio/provider inference. Full Studio là toàn bộ *.test.mjs; integration *.integration.mjs chạy qua Native parent. Source/HEAD sạch và giữ nguyên suốt năm suite; [receipt](../evidence/drama-casting-save-next-step-06/candidate-test-summary-n1.json).

15 ca casting bao gồm: dropdown và voice picker thật; lưu→bước 3; ghi chú không mất xác nhận/casting/timeline; lặp Next/chọn lại voice không tăng version; thiếu Bình có tên và focus; non-speaking role, narrator tắt, shared voice; POST mất response; GET sau POST mất response; không tạo write cạnh tranh; hai tab CAS thật và explicit rebase; reopen pending và giữ lựa chọn/bước; response phim A sau chuyển B; validation giữ form/sửa lại; script đổi cần xác nhận rõ; GET mới hơn own POST giữ snapshot riêng. Chưa có media/audio vẫn sang cảnh. Các lần chạy thử chưa đạt n2/n4 được giữ local trong recovery, không gọi là PASS; n2 phát hiện lỗi restore draft trước khi catalog được tải, n4 phát hiện race trong barrier kiểm thử và đã sửa chờ POST commit thật.

Trên runtime 62684 sau cập nhật: project **CASTING TO SCENES CONTRACT FIXTURE**, hai binding Thái Sơn/Minh Đức có sẵn, revision 3/casting version 2, confirmed=true, dirty=false/dirtyPart=null/pending=false/working=false; chuyển scenes, không media/audio/job/approval. Chuyển lại lần nữa không tăng revision. Line/character IDs nguyên, không inference/mẫu nghe mới. Fixture 5598b4ff20b04a699f25b79919c1a68c đã archive, không sửa phim Owner. [Trace](../evidence/drama-casting-save-next-step-06/live-casting-check-n1.jsonl). Đây là HTTP và controller với minimal DOM contract, **không phải browser walkthrough hoặc Owner UAT**.

### Qualification vẫn mở

Full Native M4 tại 2acd7fdd: **2306 loaded/2306 run, 0 failure, 2 error, 0 skip — NOT PASS**. Hai lỗi cùng fixture TikTok cold-history: HTTP timeout và cleanup WinError32 do SQLite còn mở. Không sửa trong task này, không cộng replay/cohort liên quan thành full pass. Full API qualification cũ giữ riêng. Ba ca PostgreSQL **NOT_RUN**, chưa có database kiểm thử riêng; đường Native bàn giao dùng SQLite, không gọi ba ca PG này. Không claim PostgreSQL/Docker/production ready.

Browser bootstrap lỗi `failed to write kernel assets: The system cannot find the path specified. (os error 3)`. Giữ log; không xóa/reset browser profile, đổi quyền, vượt cơ chế bảo vệ hoặc dùng ảnh dựng. Không có browser screenshot tại 1366/1920/2560.

## Bảo toàn và cập nhật local đã được phép

Owner xác nhận **“Khớp và không còn chỉnh sửa chưa lưu; có thể cập nhật Studio”**. Sau khi các suite kết thúc mới kiểm zero active jobs/auditions, dừng đúng process local cũ, backup+restore riêng, chuyển từ C:/vfdr05 sang C:/vfdr06 tại cùng port. Chỉ Core Runner; các worker publishing/OAuth/analytics/vision/trends còn hoãn không khởi động. Không production.

Cả **7 project cũ** giữ document hash, revision, approval hash, casting/voice metadata qua cập nhật và sau live fixture. Phim Owner vẫn revision 8/casting version 4, An=Thái Sơn/Bình=Minh Đức. **15 video lịch sử nguyên hash; 25 preset; 10 mẫu thật có 10 hash khác nhau**. Không đổi SDK/model/Thùy Dung, casting/audio cũ, recovery hoặc thư mục từng bị policy chặn. [Custody và frontend hash](../evidence/drama-casting-save-next-step-06/serving-and-preservation-n1.json), [sample audit](../evidence/drama-casting-save-next-step-06/post-update-voices-history-n1.json).

Recovery local: `C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261018/drama-casting-save-next-step-06/owner-state-before-studio-update-n1.zip` — 18,805,833 bytes; SHA-256 **230e65bfe2e4206a30c57c5f62a6b75792ee1e45ae91febf78b97641886f377b**. Restore mới tại `C:/vfct/drama-casting06-pre-update-restore`; database logical check giống nguồn. ZIP chứa dữ liệu riêng, chỉ giữ local.

Nhánh đã push. `source-casting-next-06.bundle` trong cùng recovery, SHA-256 **4f2c7367072d7301eaae432e6f07d4c2977cbf9385350a6355559d2755ee36cd**, đã git bundle verify, cần commit d056c3f57a5d98f13beecefe463e54e491d40bd2 và chuỗi bundle trước. Docs/evidence commit sau source được bảo toàn riêng. Không merge main.

## Owner kiểm tra trong tab đang dùng

Mở lại http://127.0.0.1:62684/?project=410d8fb90ed747e6a099a1e72e3f05b5 sau xác nhận nháp đã bảo toàn. Trong Cài đặt → Thông tin ứng dụng đối chiếu **drama-casting-next-06**. Ở **Nhân vật & giọng**, kiểm tra An=Thái Sơn/Bình=Minh Đức rồi bấm **Lưu phân vai & tiếp tục**. Casting đã lưu đúng sẽ sang **Hình ảnh & cảnh** mà không tạo lại revision hoặc đòi TTS/media. Nếu thực sự còn thiếu, lý do và hành động sửa hiện cạnh nút. Không cần nhập ID/JSON hoặc tạo phim khác.

`CASTING_NEXT_STEP_TECHNICAL_PASS=YES` (phạm vi trên); `BROWSER_QA=BLOCKED`; `OWNER_CASTING_NEXT_STEP_UAT=NOT_RECORDED`; `OWNER_UAT_COMPLETE=NO`. Xác nhận khớp form/cập nhật không phải nghiệm thu giọng, audio/video hoặc ca xuất Standard/Drama.

`PLATFORM_API_PUBLISHING=DEFERRED`; `ANALYTICS=DEFERRED`; `FULL_TREND_RADAR=DEFERRED`; `PRODUCTION_DEPLOYED=NO`.
