# Deployment profiles độc lập: kiến trúc và giới hạn kiểm chứng

Đã ghép11file của `dd6b274243a45c20e186d307e355698ca39ffaa3` vào primary `3bb7b3fc0a5512f748b136f68cdfd959969c8b00`. Compiler sinh deterministic Compose JSON cho dev,ci,production-cpu,production-gpu; CPU không phụ thuộc GPU. Các profile dùng namespace/database/Redis server/S3 bucket/networks/volumes riêng và loopback ports; không sửa stack NPD/Agent Hub hiện hữu.

## Hành vi đã có

Build context dùng source root rõ ràng; secret directory nằm ngoài repo, grants theo service. Runtime đọc bounded mounted files, từ chối links/hardlinks/example/oversize/control characters/Redis injection; DB secret được URL-escape. Settings được dựng từ environment allowlist, bỏ ambient provider/cloud/proxy secrets. Publishing, paid provider, bridge execution, SQL narration và human writes production mặc định tắt; human approval mặc định bật.

Approved ComfyUI workflow manifest chỉ đọc; bridge NOT_CONFIGURED nếu chưa có GPU/provider, core CPU tiếp tục độc lập. Optional S3 init là kiến trúc/SDK fixture, chưa phải Minio đã chạy. Dockerfile Python, runtime wrappers và official Compose schema có source/hash/license/provenance. Schema pin `914ec15d1fa498969c0df5c1d672306db3256089`, SHA `d61cc3df8c6e6a727043e84f3405c69ffd63d341f629db8480f1d2ee5405b10c`, Apache2. Alembic offline đọc một head0032_ns_sql_variants, không DDL.

## Review và sửa lỗi

Peer tìm được model admission cho phép sửa foreign host bind, Studio data network, secret grant, API entrypoint và remote/executing bridge; repro chỉ dựng argv, không chạy Docker hoặc truy cập secret. Bản sửa kiểm tra exact compiler projection toàn service/config, chỉ cho các lựa chọn operator rõ ràng. Một race config/empty-env trong lúc đọc được sửa bằng immutable deepcopy và kiểm tra identity/content của cả hai file, có final pair fence sau IO cuối trước argv. Guard là point-in-time, không cấp deployment approval hoặc lease cho quá trình deploy.

| Batch | Phạm vi |
| --- | --- |
| N1 author31PASS; runtime16PASS sau sửa | Lịch sử source riêng; không tuyên bố đã full rerun35. |
| N2 profile46PASS | Old19+new27; runtime16 không chạy lại. |
| N3 selected12PASS/40deselected | Pair/file/CLI guards; overlap N2, không cộng thành52. |
| Peer pair6PASS | Repro ban đầu bị chặn, positive plan vẫn hợp lệ; source/archive/legacy before-after đúng hash. |
| Primary Settings4PASS | Actual app.config có flag mới, ambient publish/paid/provider/narration bị loại,0socket connection; parent env giữ nguyên. |

N4 chỉ bỏ hai byte blank EOF trong new test; AST/strip-EOF giữ nguyên, diff check PASS. Legacy9Compose/Docker/env và hai helper S6 cũ giữ hash; .dockerignore thêm loại khỏi build context, không xóa dữ liệu.

## Chưa kiểm chứng

DockerCLI không có trên máy. Chưa build image, khởi chạy daemon/container, disposable PG/Redis/S3 stack, GPU, network/ACL, heartbeat, actual backup/restore stack hoặc soak. Không cài Docker, không deploy và không chạm production. Image/package/Minio FILE behavior phải được kiểm tra trên disposable infrastructure riêng trước acceptance. Wave15 chưa hoàn thành; deployment profiles PARTIAL, Docker NOT_VERIFIED.

Index [spoken-studio-deployment-evidence.json](north-star/spoken-studio-deployment-evidence.json) giữ original findings/failures, N1–N4 source archives, independent review và primary Settings proof. Tiếp tục audio/word UI và các safe implementation khác trong khi blocker Docker/provider được giữ riêng. Owner chỉ cần duyệt khi đến production deployment/infrastructure hoặc real publishing; chưa cần action cho việc này.
