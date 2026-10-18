# VF-DRAMA-SAVE-SELF-CONFLICT-FIX-05

Bản sửa đã phục vụ tại http://127.0.0.1:62684/. Application source `C:/vfdr05`, nhánh `codex/vf-drama-save-self-conflict-05`, application/code HEAD `758466ed97cdd6c204bed3f6d1e7fd06a6db807c`, build **drama-save-fix-05**. Baseline thực tế là `C:/vfdm4u@2acd7fdd`, kế thừa `baa85747`; không reset về baseline cũ. Commit báo cáo/bằng chứng kế tiếp chỉ đổi docs/evidence, không đổi các file ứng dụng đã kiểm thử hoặc phục vụ. About giữ application HEAD của lúc khởi chạy, không phải dấu hiệu browser đang nhận frontend cũ.

## Nguyên nhân và tái hiện

Dùng project riêng, một controller/tab, server Native HTTP thật, callback `onSaved` và thân `reload()` lấy nguyên từ source baseline. POST lưu đã commit revision 2; callback gọi `reload(true)` khi `dirty=true` và snapshot UI vẫn revision 1. Chính GET revision 2 bị coi là thay đổi từ cửa sổ khác. Hàm thoát trước khi clear pending/dirty, nên nút “Đối chiếu lần lưu trước” tồn tại và “Tiếp tục” bị khóa. Đây là tự xung đột; không có bằng chứng Owner mở nhiều tab.

`single-tab-before-fix-n3.log` và `save-trace-before.jsonl` giữ kết quả RED: server=2, UI=1, dirty=true, pending=true, step=script. Baseline API chưa echo request key nên trường `request_key_matches=false` trong trace cũ biểu thị thiếu field, không chứng minh key bị đổi. Fixture chuẩn bị đầu tiên bị data-root guard từ chối trước khi tạo project; đã sửa bố cục private/test-data riêng trước lần tái hiện hợp lệ. Không dùng lần khởi tạo lỗi đó làm bằng chứng sản phẩm.

## Source đã sửa

- `drama-workflow.mjs`: xác minh receipt trước callback, tách kết quả POST đã commit khỏi GET đối chiếu, chỉ clear dirty khi form hiện tại còn trùng payload đã gửi sau mọi await. Một request in flight cho autosave/manual; pending bất định được giữ nguyên request key/payload. Nháp và pending lưu local theo workspace/project; phản hồi trễ không gán sang phim khác. Chỉnh sửa mới trong lúc chờ vẫn được giữ và tiếp tục là chưa lưu.
- `native.mjs`: callback thật `nativeDramaSaveCallback()` dùng cùng `createNativeProjectReload()` được integration test gọi. Chỉ nhận revision của lần lưu đã xác minh, giữ các form khi render(false). GET mới hơn trả trạng thái cần đối chiếu; reload thường vẫn giữ CAS và dùng thông báo trung tính. Lỗi HTTP có code/status để phân biệt từ chối chắc chắn với mất phản hồi; lỗi đọc danh sách project sau commit không biến lưu thành bất định.
- `drama-script-save.mjs`: ràng buộc project, workspace, request key, base/result revision, SHA-256 của payload chuẩn hóa; GET kiểm cả nội dung, chế độ nhập, ghi chú nhân vật, người kể, series/tập và lựa chọn người nói.
- `production_workflows.py` / `production_workflow_routes.py`: trả receipt có request identity/hash và workspace do server xác định. Replay dùng journal/fingerprint hiện có, không thêm revision hay rewrite journal cũ. Giữ `store.editable()`/CAS, approval invalidation và quyền/CSRF. Không migration phá hủy.
- `server.py`: phục vụ module save mới. About dùng build `drama-save-fix-05`.

Không force reload, tắt CAS, last-write-wins, tự duyệt, gửi TTS/render hoặc thay kịch bản Owner.

## Trạng thái lưu và xử lý xung đột

| Trường hợp | Kết quả |
| --- | --- |
| POST đúng request + GET cùng revision/payload | Đã lưu; clear pending; chỉ clear dirty nếu form còn khớp; mở bước 2 khi đủ điều kiện |
| Form có nội dung mới lúc chờ | Snapshot gửi trước đã lưu; giữ nội dung mới và dirty; không thay form bằng reply cũ |
| POST đã commit nhưng mất response | Giữ request cũ; bấm đối chiếu replay đúng key/payload; không thêm phiên bản |
| Receipt đã nhận nhưng GET lỗi | Giữ receipt đã xác minh; thử GET đối chiếu, không POST mới |
| GET mới hơn kết quả POST | Tách POST thành công khỏi snapshot mới; giữ form và bản server; yêu cầu đối chiếu |
| CAS hai tab thật | 409 được giữ; không overwrite; xem bản server rồi chủ động chọn mốc mới trước khi Lưu |
| Validation/auth từ chối chắc chắn | Giữ form, bỏ attempt bị từ chối; sửa lỗi rồi lưu lại được |
| Chuyển phim/workspace | Không nhận phản hồi trễ vào phim khác; nháp/yêu cầu cũ vẫn thuộc scope cũ |

UI có **Sao chép bản đang nhập**, **Xem bản đã lưu**, ô chỉ đọc chứa bản server và nút **Giữ bản đang nhập · dùng phiên bản này làm mốc lưu**. Nút chọn mốc đọc lại server và kiểm snapshot trước khi đổi base; chưa gửi bản nháp hay cấp approval. Autosave không chạy khi pending/conflict chưa được giải quyết.

## Kiểm thử trên candidate cố định

| Phạm vi | Kết quả |
| --- | --- |
| Full Studio | **2.165 PASS**, 0 fail/skip |
| Native liên quan | **76 PASS**; trong đó 1 parent chạy 9 ca HTTP/Studio callback |
| API liên quan | **92 PASS**: final export quality, verified delivery, source asset delivery |
| Renderer | **52 PASS** |
| Typecheck | **PASS** |
| Browser thật | **BLOCKED**, không có screenshot hoặc browser PASS |

9 ca HTTP/callback: lưu một tab → bước 2; autosave + Lưu; mất response sau commit; sửa mới trong GET đối chiếu; hai tab CAS thật và explicit rebase; GET mới hơn POST; phim A trả lời sau khi sang B; validation/network; reopen/restart phục hồi pending + nội dung mới, chuyển bước rồi mở lại. Thêm contract tests cho hash/workspace/revision/payload, GET trễ sau đổi workspace, lỗi đọc danh sách phụ và reload thường còn CAS. DOM fixture chỉ kiểm contract/controller, không thay browser walkthrough. Startup browser vẫn lỗi `failed to write kernel assets: The system cannot find the path specified. (os error 3)`; không reset profile, đổi quyền hoặc thử vô hạn.

Trên API đang phục vụ 62684, một project thử riêng lưu lên revision 2, dirty=false, pending=false, bước voices; không approval/job. Project thử `f12e3bfc39d84b389ea969b6b2d4c8e9` có nhãn KHÔNG UAT và được archive, giữ lịch sử; không sửa project Owner.

### Qualification cũ được giữ riêng

Full Native M4 tại `2acd7fdd`: **2.306 loaded / 2.306 run / 0 failures / 2 errors / 0 skip — NOT PASS**, không còn RUNNING. Cùng một ca `test_cold_server_reads_original_history_without_configuration_or_private_load` gặp HTTP timeout rồi cleanup WinError32 do workflow.sqlite3 còn được dùng. Không sửa/đóng lỗi này trong task 05, không cộng replay hoặc 76 test liên quan thành full PASS. Full API qualification cũ giữ nguyên; 3 ca PostgreSQL vẫn NOT_RUN, chưa có DB kiểm thử riêng. Không có xác nhận PostgreSQL/Docker/production ready.

## Bảo toàn Owner và source

Owner đã trả lời “Đã sao chép đầy đủ; có thể cập nhật Studio”. Chỉ sau đó mới kiểm zero active jobs/auditions, backup và restore kiểm đủ **6 project**, rồi chuyển server từ C:/vfdm4u sang C:/vfdr05. GET/source hashes xác nhận frontend thực sự đang được phục vụ, Cache-Control=no-store. Cả 6 document/revision/approval được giữ nguyên tại thời điểm chuyển; không đọc toàn bộ bản nháp browser riêng tư hoặc log token/kịch bản riêng. Trước sửa đã kiểm các receipt lưu server để phân biệt commit với trạng thái UI; không khẳng định bản đang gõ khớp server khi không đọc được tab.

Recovery `owner-state-before-studio-update-n1.zip`: 18.768.968 byte, SHA-256 `c76501d187911015b2ea2f8bb32a782efb6cc09048ba686a95dd3f303fcb00a2`; restore riêng `C:/vfct/drama-save05-pre-update-restore`. Recovery chứa dữ liệu riêng chỉ giữ local, không đưa ZIP vào Git. Source bundle và hash trong `source-preservation.json`, nhánh đã push; không merge main.

Kiểm lại **15 video lịch sử nguyên hash; 25 preset, 10 mẫu thật/10 hash khác nhau; casting cũ giữ nguyên**. Không thêm mẫu, đổi model/SDK/Thùy Dung, xóa thư mục bị policy chặn hoặc thay video/audio được duyệt.

## Owner kiểm tra trong tab của mình

Tải lại tab Studio sau khi đã sao chép, mở **Cài đặt → Thông tin ứng dụng** để đối chiếu build `drama-save-fix-05`. So sánh kịch bản đang hiển thị với bản đã sao chép. Nếu đã đúng, không cần dán/lưu lại; bấm Tiếp tục. Nếu có chỉnh sửa chưa lên server, giữ bản sao và đối chiếu trước khi dán/lưu. Sau lưu đúng: Đã lưu và bước Nhân vật & giọng mở được. Nếu có xung đột thật, dùng các nút sao chép/xem/chọn mốc ngay trong panel; không phải tải lại để giải quyết.

`SAVE_FIX_TECHNICAL_PASS=YES` (scope kiểm thử trên); `BROWSER_QA=BLOCKED`; `OWNER_SAVE_UAT=NOT_RECORDED`; `OWNER_UAT_COMPLETE=NO`. Xác nhận sao chép/cập nhật không phải nghiệm thu video hoặc giọng. M4/Standard/Drama Export Owner acceptance chưa tự đóng.

`PLATFORM_API_PUBLISHING=DEFERRED`; `ANALYTICS=DEFERRED`; `FULL_TREND_RADAR=DEFERRED`; `PRODUCTION_DEPLOYED=NO`.
