# Phục hồi upload, preview và quyết định duyệt qua API dịch vụ

Khởi tạo upload, ghi job preview và ghi quyết định duyệt nay lưu kết quả lệnh và sự kiện cùng giao dịch dữ liệu lõi. Mất phản hồi sau commit có thể thử lại đúng yêu cầu để nhận biên nhận cũ. Thử lại không tạo thêm phiên upload, job preview hoặc quyết định duyệt. Hook chỉ hoạt động trong yêu cầu dịch vụ đã xác thực; giao diện/người dùng lõi tiếp tục dùng engine cũ.

Upload giữ DTO đã chụp trước commit để SQLite refresh không thay đổi biểu diễn thời gian của biên nhận. Khi ghi outbox thất bại, bản ghi upload rollback và cơ chế sẵn có dọn đúng thư mục staging mới của thao tác đó. Không xóa thư mục hay dữ liệu lịch sử bị chính sách chặn.

Preview ghi cả trường hợp job mới và job hiện có trong giao dịch khóa timeline. Retry job failed/cancelled rollback về trạng thái cũ nếu outbox lỗi. Nếu Redis lỗi sau commit, biên nhận vẫn giữ đúng job queued; cơ chế recover_incomplete sẵn có đưa chính ID đó lại vào hàng đợi. Kiểm tra này dùng Redis giả lập; chưa chứng minh toàn bộ worker/Redis production hoặc sửa mọi trường hợp lặp trong recovery.

Ba quyết định approved, changes_requested, rejected dùng reviewer đã xác thực riêng. Client không thể tự khai tên reviewer. Kể cả replay, yêu cầu vẫn phải qua xác thực người có quyền. Nếu outbox thất bại, quyết định, trạng thái timeline, nhật ký approval và biên nhận rollback cùng nhau. Đây là danh tính CI giả lập, không phải nghiệm thu của Owner.

Sự kiện mới dùng hợp đồng đóng agent-hub-service-outcomes.v2; bốn loại trước vẫn phát v1 với schema và tham chiếu cũ. Discovery và trang đọc có xác thực công bố cả hai phiên bản; từng sự kiện mang phiên bản riêng. Payload chỉ chứa ID/trạng thái và hash, không chứa filename, bình luận riêng, script hay token. Đọc sự kiện dựng lại loại nguồn từ hành động và biên nhận gốc; sửa source_kind rồi tính lại hash bị từ chối. Gửi webhook vẫn tắt.

Kiểm tra: 10 ca intake mới nằm trong batch 34 outcome/facade/schema/migration đạt; 34 hồi quy ingestion/Studio/render/QC/publishing/feature/Bridge đạt. Không cộng các batch cũ vào số ca mới. Ba lỗi lần đầu là thiết lập test: staging chưa tồn tại, kích thước preview ngoài hợp đồng, tên thuộc tính FakeRedis sai; đã sửa và lưu nguyên log thất bại. Không có test provider hoặc video/người thật mới, không chạy Docker, không thay production/live source.

Còn mở: upload part/finalization và analysis transaction; tạo timeline/content/generation/trend và yêu cầu approval; mọi nguồn sự kiện worker, delivery ra ngoài và Native API parity; dữ liệu/provider thật, PostgreSQL/Docker, đầy đủ Mode A/B/A-B-C, Owner và production. 64 nhóm vẫn là 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED, còn 59 chưa đóng. IMPLEMENTATION_COMPLETE=NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO; VIDEO_FACTORY_NORTH_STAR_READY=NO.

## Báo cáo Wave 14/15/16 — thành phần phục hồi intake

WAVE: 14/15/16 component
STATUS: triển khai và kiểm tra SQL/ASGI trên bộ dữ liệu giả lập; full waves PARTIAL
HEAD SHA: parent e8a64aacd1d9fc0248bf88c79294ee4d231785fd; HEAD cuối ở recovery/20261007/service-intake-outcomes-program-state.json
CAPABILITIES COMPLETED: ba root transaction atomic; replay/rollback; human revalidation; preview queue handoff recovery; hợp đồng v1/v2 cùng tồn tại
CAPABILITIES PARTIAL: các lệnh còn lại, worker events/delivery/Native/production và toàn bộ North Star
TESTS: 34 outcome/facade + 34 core PASS; 10 ca mới
REAL PROVIDER TESTS: không; không có nghiệm thu media/Owner thật
MOCK TESTS: SQLite/ASGI/Redis/media/ASR/QC/danh tính CI có ghi nhãn
EVIDENCE: north-star/service-intake-outcomes-evidence.json; service-intake-outcomes-evidence-n1.zip; log thất bại được giữ
REGRESSIONS: hợp đồng v1, upload validation, quyền người duyệt, render/QC và publish gate; 15 artifact cũ và live source được kiểm tra ở seal
EXTERNAL BLOCKERS: OAuth/provider/Owner/production và Docker còn mở riêng
OWNER ACTION REQUIRED: không cần cho triển khai an toàn; nghe/nghiệm thu tiếp tục để sau
NEXT WAVE: các lệnh intake/analysis/content và nguồn worker còn lại; tiếp tục full Master
