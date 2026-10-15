# Khôi phục B-roll bằng chứng thực đã ký

Ngày 2026-10-15; product `297427e15985ce98a6d9b4bc6047156f82d0ce30`. Tiến độ Waves 3/8, chỉ backend. Phần này nối issuer/verifier đã review vào cùng giao dịch/project lock của cơ chế settlement hiện có.

API mới dưới `/api/v1/projects/{project_id}/broll-plan-review/witnessed-recovery` gồm POST `inspect`, POST `abandon` có xác nhận/CAS và GET `settlements/{id}`. `VerifiedWitness`/scope có seal riêng được tạo trên server; không có cờ trust từ client. Nguồn, authority hiện tại, key và thời hạn được xác minh lại sau SQL await trước quyết định settlement. Không có đường ghi song song ngoài lock.

Observation CAS ràng buộc đúng SHA của envelope. Hai chứng thực hợp lệ cho cùng body vẫn không thể tráo observation. Replay giữ nguyên envelope ban đầu đã được nhận; lịch sử sau khi key bị thu hồi không bị gắn lại nhãn bằng chứng thực mới. Audit lưu literal claims/envelope, identity, request/observation digest và private original snapshot; chuỗi sai phải failclosed, không tự sửa hoặc gửi lại.

Witness chỉ xác nhận authorization/request gốc, `execution_status=NOT_ASSERTED`; không phải chứng cứ request đã/chưa chạy. Biên nhận, kế hoạch và kết quả đến muộn gốc được giữ. Original prepare đến sau seal bị chặn. API/DTO recovery v1 không đổi; trường hợp legacy absent request đổi credential mà không có witness vẫn giữ failclosed.

Khóa riêng vẫn **NOT_CONFIGURED** trong cấu hình thực, issuer tắt mặc định. Mọi lần thử dùng khóa ephemeral fixture. Chưa nối controller pending v2 hoặc Root UI; wrapper Studio hiện chỉ cho v1 routes/raw format. Không suy diễn backend mới đã dùng được qua UI cũ.

| Kiểm chứng | Kết quả | Phạm vi |
| --- | --- | --- |
| Final focused tác giả | 24 PASS, 81,54 s | 16 wrapper + 5 actual main + 3 legacy; không phải full backend |
| Kiểm tra độc lập | 4 PASS, 14,88 s, findings trống | Proof-bound CAS, original proof trên replay/history, key/write drift sau SQL, scope giả bị chặn; 0 network |
| Current primary main | 15 PASS, 70,46 s | Signed recovery + initial witness + recovery v1 auth/mount coexistence |
| Actual shipped main capture | 14 requests, 12 recorded + 2 helper GET | Absent → issue → renew/prune → plain409 → signed inspect/seal → reads/replay → late original409; 1 settlement, 0 plan/provider |

Capture `broll-witnessed-recovery-actual-main-n3.json`: 441.896 bytes, SHA256 `8c837257587f3c6cc39ad54a0d697b4cb7e04672a602e72d92da9ea823462445`. Các helper N1/N2 lỗi được giữ; không sửa raw hoặc mã sản phẩm để làm lại nhãn kết quả. Run 45 PASS trước đó dùng source cũ, không được thay cho final24. Initial issuer47/independent2 và Studio1.843 tại source9b9 được ghi riêng, không cộng thành tổng test mới hoặc nhận là full rerun trên backend này.

Nguồn6 và dependency9 được kiểm tra đúng ZIP/pins trước/sau independent review. Primary chỉ thêm hai dòng mount/import vào main đang có và hook hẹp vào recovery; các router nội bộ, controller/UI và callback guard trước đó giữ nguyên. Commit nhánh làm việc và Git bundle riêng đã lưu, không merge main, không migration/deploy/publish/paid call.

## Khoảng trống tiếp theo

- Pending v2/controller và Root UI opt-in: P1, Waves 3/8. Phải giữ literal intent v1 + envelope, chứng thực trước prepare, lưu durable trước execution POST, exact raw guard sau mọi await; không auto-sign, fallback, đổi key hoặc downgrade pending.
- Internal-resolution Root UI và settlement của job terminal được làm riêng. Không coi witnessed prepare settlement là settlement của asset-resolution job.
- Browser, nguồn thật/ASR/Vision, provider/key thực, full A/B/C, production và Owner UAT vẫn chưa nghiệm thu. Cổng browser và thao tác dọn cache đã bị policy từ chối, không thử đường vòng.

WAVE: 3/8

STATUS: Witnessed preparation recovery backend integrated/preserved; full waves remain open.

HEAD SHA: `297427e15985ce98a6d9b4bc6047156f82d0ce30`; docs riêng sau đó.

CAPABILITIES COMPLETED: typed signed authorization trong original project lock, proof-bound CAS, original proof/audit replay/history và late original rejection.

CAPABILITIES PARTIAL: pending/controller/UI v2, internal resolution UI/terminal release, full Mode A/B và các khoảng trống Master Spec; 59 nhóm lớn chưa đóng.

TESTS: final24/independent4/current primary15 PASS, các tập riêng có overlap; không full Studio rerun vì backend-only.

REAL PROVIDER TESTS: none; default signing NOT_CONFIGURED, ephemeral keys only.

MOCK TESTS: fixture human auth/source metadata; actual owned SQLite/ASGI, không browser/media/provider/production acceptance.

EVIDENCE: [index](north-star/broll-witnessed-recovery-evidence.json), source ZIP/bundles, raw captures/logs, independent review và import pins.

REGRESSIONS: legacy v1/no-witness remains failclosed; older mounts/source preserved; accepted artifacts chưa bị thay thế.

EXTERNAL BLOCKERS: key thực/provider/browser/Owner acceptance tách riêng, không chặn implementation an toàn tiếp theo.

OWNER ACTION REQUIRED: none for current safe work; listening/UAT deferred.

NEXT WAVE: pending v2/controller; internal-resolution UI và terminal settlement; các gap Master Spec còn lại.

SOURCE_PRESERVED=YES; PHASE10_TECHNICALLY_READY=YES; OWNER_UAT_REQUIRED=YES; PHASE10_READY=NO; IMPLEMENTATION_COMPLETE=NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO; VIDEO_FACTORY_NORTH_STAR_READY=NO.
