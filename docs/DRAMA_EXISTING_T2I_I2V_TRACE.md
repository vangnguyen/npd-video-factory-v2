# Đối chiếu T2I/I2V đã có — 2026-10-19

Ưu tiên Owner: chỉ tái sử dụng T2I/I2V hiện có, không thêm HeyGen hoặc provider khác. Đã kiểm GitHub, runtime thật và toàn bộ version của project. **Hiện chưa có clip I2V để dựng pilot.** Không tạo request giả, bật fixture hoặc thay bằng ảnh zoom/pan.

## GitHub đã kiểm tra trực tiếp

Remote `https://github.com/vangnguyen/npd-video-factory-v2.git`; `git ls-remote` mới có 160 nhánh. Toàn bộ commit object của các đầu nhánh đều có sẵn và đã đối chiếu `workflows/comfyui` cùng các file provider hiện hữu bằng `git ls-tree`/`git show`, không checkout hoặc reset.

| Ref trên GitHub | HEAD xác minh | Quan hệ với bản local |
|---|---|---|
| main | `fa81c59fbe6b745cba8fed979e30e52a13199afa` | Đã là tổ tiên của local; local ahead 549, behind 0 lúc kiểm tra |
| feat/v2-06-media-intelligence | `44e4de3282ba1484117c0262d14cee89019aeb2a` | Đã có trong lịch sử local |
| codex/vf-north-star-completion-01 | `4162bc32260521277737f7c9ee118b5ba55b3f9b` | Đã có trong lịch sử local |
| codex/vf-drama-m4-closure-07 | `a75c7678d61fc00d54fd5ed07a436aff56724f1a` | Đã có trong lịch sử local |

Có 9 blob JSON workflow độc lập: một manifest, tám graph. **Cả tám graph đều có 0 node thực thi**, T2I và I2V giống nhau giữa main, nhánh media, North Star và local. Không tìm thấy graph executable ở các đường workflow đã commit tại 160 đầu nhánh này. Phạm vi này không suy ra nội dung config triển khai riêng, nhánh đã xóa hoặc file ngoài Git.

Nguồn GitHub cố định: [T2I graph trên main](https://github.com/vangnguyen/npd-video-factory-v2/blob/fa81c59fbe6b745cba8fed979e30e52a13199afa/workflows/comfyui/text-to-image-v1.json), [I2V graph trên main](https://github.com/vangnguyen/npd-video-factory-v2/blob/fa81c59fbe6b745cba8fed979e30e52a13199afa/workflows/comfyui/image-to-video-v1.json), [manifest](https://github.com/vangnguyen/npd-video-factory-v2/blob/fa81c59fbe6b745cba8fed979e30e52a13199afa/workflows/comfyui/manifest.json).

Kết luận: code adapter/queue/import/UI đã có; chưa có workflow/model thực thi đang bị bỏ sót do chưa pull. Git pull không cung cấp checkpoint hoặc tự provision ComfyUI.

## Runtime thực sự đang phục vụ

Studio `http://127.0.0.1:62684/`, PID 24476, source `C:/vfdr07`, application commit `0eb7e679be6a138fff891987bd507ea4c82b8000`, build `drama-m4-closure-07`. HEAD repository lúc kiểm tra là `7187d98a29a6059fb99256c6ce8e6ed0155ca357` trên nhánh `codex/vf-drama-real-visual-08`, chỉ thêm hồ sơ sau application commit.

Đọc byte HTTP `native.mjs`, `drama-workflow.mjs`, `native-generation.mjs` và so SHA256 với source trên PC: cả ba khớp. Không kết luận browser cũ chỉ vì HEAD report khác app-info. Lần đọc tab Flow có sẵn bị timeout khởi tạo CDP; không dùng nó làm bằng chứng có provider/model hoạt động, không gửi yêu cầu tạo video ở đó.

| Capability | Provider/adapter hiện có | Workflow/model thật | State |
|---|---|---|---|
| Native T2I | `comfyui-image`, `GenerationFactory` → `ComfyUIBridgeGenerationProvider` | `npd-text-to-image-v1`/1.0.0, graph `prompt={}`; model identifier chỉ là `owner-provisioned-image-model` | `NOT_CONFIGURED`, 0 node, không execution binding |
| Native I2V | `comfyui-video`, cùng bridge và worker | `npd-image-to-video-v1`/1.0.0, graph `prompt={}`; model identifier chỉ là `owner-provisioned-video-model` | `NOT_CONFIGURED`, 0 node, không execution binding |
| Thử nghiệm trước đây | Native HTTP/worker + synthetic pixels/mock GPU APIs | Fixture contract test, không phải checkpoint thật | `real_provider_tested=false`, không dùng làm phim Owner |
| Ba reference mới | Built-in `image_gen`, đã sinh ảnh thật và nhập thư viện | Không phải job T2I của Native; model/revision tool không công bố | Owner duyệt tham chiếu, chưa qua I2V |

`GET /api/generation/providers`: `owner_enabled=false`, `provider_configuration_sha256=null`, mode contract “official” nhưng status `NOT_CONFIGURED`. Mode “official” không chứng minh đã gọi provider. Launcher `serve_m4_fixed.py` không truyền generation registry/factory, không có human-auth enablement, `start_worker=False` và chỉ start core Runner: generation worker cũng chưa chạy.

Inventory listener tại thời điểm đọc chỉ có Python Studio ở 62684 cùng dịch vụ hệ thống; không có ComfyUI/bridge listener. Runtime models `C:/NPD-Video-Factory/runtime/models` chỉ có `moss-codec` và `vieneu-v3-turbo`, thuộc audio/TTS đang khóa, không phải checkpoint T2I/I2V. GPU GTX 1050 Ti 4 GB, ổ C dưới 1 GB trống. Mức 12/24 GB trong manifest là dự toán placeholder, không phải benchmark của một model đã cài. Không tải model hoặc thay runtime để lấp chỗ trống.

Nguồn source: [generation_registry.py](../services/windows_native/generation_registry.py), [generation_references.py](../services/windows_native/generation_references.py), [generation_worker.py](../services/windows_native/generation_worker.py), [tài liệu Native generation có sẵn](NATIVE_GENERATION_HTTP_STUDIO.md). Fixture rehearsal gốc ghi rõ `synthetic_pixels_and_mock_gpu_apis=true`, ba mock GPU prompt writes, `real_provider_tested=false`.

## Truy vết Lá thư trước cơn mưa

Project `1c768012f9624de494a9fadab63c1a31`, revision 8, canonical timeline version 5, SHA256 `4b096bdef5ed2ea23bfd9ddfdf505fc1f006718ad5bfb32b611d1d74ce319513`. Duration 35,32 giây.

| Cảnh/clip | Timeline đang dùng | Tư liệu thực tế | I2V |
|---|---|---|---|
| CẢNH 1: Quán cà phê trước cơn mưa / `shot_d26adfb26b3c559cbb3be5ea909d7898` | Một visual clip image từ 0 đến 35,32 giây; `motion=none`, không effects | `assets/8a0b0d12496943888a134b2ecc151d8b.jpg`, 1080×1920, SHA `112cf777b130936002690b62f89f5da17f01532bdecdc7dccdc1969d939c5851` | Không job, không clip I2V |

Ảnh ở `C:/vfct/final-export-review-n1/assets/8a0b0d12496943888a134b2ecc151d8b.jpg`; original giữ ở thư mục `originals` với source hash riêng. Cả hai đã kiểm byte. Clip thuộc track `trk_native_video`; voice track và 16 subtitle clip riêng không biến nó thành footage diễn xuất.

Đã đọc revision 1–8: revision 3–4 là metadata-only visual; revision 5–8 dùng ảnh. Không version nào có visual kind video. `native_generation_jobs`, `native_generation_media`, `native_generation_reference_admissions`, `native_generation_events` đều 0 hàng toàn workspace đang chạy, gồm 0 hàng cho project. Vì vậy không có provider job/ticket hoặc output I2V nào để chọn lại.

Project chỉ có hai job thực: narration `ffb25b9779204412ab06f738b353eab6` và render `ecf5e70c44a749f9b0068ba45c9b8d89`, đều succeeded. Render result ghi thư mục `C:/vfct/final-export-review-n1/jobs/ecf5e70c44a749f9b0068ba45c9b8d89`; MP4 đó là render ảnh + audio, không phải output I2V. Bản đã duyệt vẫn ở [gói cũ](DRAMA_M4_REAL_EXPORT_CLOSURE_07.md).

Ba ảnh An/Bình/quán mới nằm trong reference-container project `213be24a515e4cf48c7857cf31f55e71`; chưa được chọn bởi timeline phim gốc và chưa được gửi I2V. Giữ nguyên tạo hình đã được Owner duyệt; không gọi T2I chỉ để tạo lại các reference đã có.

## Đường pilot tái sử dụng, điều kiện còn thiếu

Đã thay kế hoạch đang thực hiện bằng `pilot-existing-pipeline-v2.json`: chỉ dùng `comfyui-image`/`comfyui-video` và workflow ID hiện có. Proposal HeyGen cũ chỉ giữ lịch sử, không còn là hướng thực hiện. Ba shot bám lời thoại/timing cũ, tổng 11,07 giây; cần first-frame đúng góc máy rồi I2V có hành động/phản ứng, không zoom/pan ảnh. Tối đa ba T2I first-frame và ba I2V job, một attempt mỗi shot; chưa submit bất kỳ job nào. Khả năng model thực tế giữ reference nhiều người vẫn NOT_VERIFIED.

Các điều kiện cụ thể cần đủ trước dispatch:

1. Có endpoint ComfyUI/backend và bridge thực sự chạy, dùng đúng model/checkpoint đã được chọn và đủ tài nguyên. Hiện chưa có endpoint/model đó trong cấu hình đang chạy.
2. Cấp hai API graph thực thi, pin graph SHA/model/custom nodes và input/output bindings trong manifest; approval kind của graph phải đúng. `prompt={}` không thực thi được dù bật cờ.
3. Nạp protected registry ngoài state root với workspace đúng, bridge URL/service auth; bật generation qua boundary human auth/RBAC và cờ hiện có, không bỏ bảo vệ. Khởi động riêng generation worker, giữ các integration đã hoãn tắt.
4. Xử lý quyền tham chiếu: ba asset đang `rights_status=unknown`, chưa có active override. `NativeGenerationReferences.source()` sẽ chặn với `NATIVE_GENERATION_REFERENCE_RIGHTS_REVIEW_REQUIRED`. Duyệt tạo hình không tự tạo quyền/override. Chỉ xử lý khi đủ căn cứ và đúng chốt Owner, không tự đổi sang owned/licensed.
5. Nếu cần tải model, đổi runtime/tài nguyên hoặc phát sinh chi phí, trình phương án cụ thể để Owner duyệt trước; chưa được phép làm các việc đó. Không cần thêm provider mới để hoàn thành phần code integration hiện có.

Sau khi có clip thật: tạo bản sản xuất riêng chưa duyệt từ project gốc, giữ audio đủ điều kiện reuse; dùng generation import hiện có để đăng ký clip thật, rồi chọn clip qua shot/canonical media controls. Mỗi shot giữ job/provider/workflow/model/input/clip hash và source dimensions. Cắt theo audio đo, bỏ audio provider, cập nhật subtitle/mix/preview và yêu cầu Owner duyệt pilot. Không tạo approval, không thay bản đã duyệt, không tạo timeline thứ hai. Hiện chưa có clip nên **chưa thực hiện bước nối timeline hoặc render pilot**.

## Trạng thái và bằng chứng

- `EXISTING_T2I_ADAPTER=IMPLEMENTED`, `EXISTING_I2V_ADAPTER=IMPLEMENTED`; runtime thật cả hai `NOT_CONFIGURED`, model thật `NONE_CONFIGURED`.
- `REAL_I2V_JOBS=0`, `REAL_I2V_CLIPS=0`, `PILOT_VIDEO=NOT_CREATED`, `CANONICAL_CLIP_INTEGRATION=NOT_DONE_NO_REAL_CLIP`.
- An = Thùy Dung, Bình = Thiện Minh, narrator OFF. Original revision/timeline/casting/audio/approval không đổi; không gọi TTS/render mới.
- `DRAMA_VISUAL_ACCEPTANCE=NOT_ACCEPTED` cho phim ảnh tĩnh cũ; tạo hình mới đã duyệt riêng. `DRAMA_FILM_READY=NO`.
- Không thêm adapter/provider, không dùng fixture làm pilot, không deploy/merge main hoặc đăng mạng xã hội. Publishing API, Analytics, Full Trend Radar vẫn DEFERRED.

Evidence: [runtime/project trace](../evidence/drama-existing-t2i-i2v/runtime-and-project-trace.json), [GitHub audit summary](../evidence/drama-existing-t2i-i2v/github-audit-summary.json), [kế hoạch hiện hành](../evidence/drama-existing-t2i-i2v/pilot-existing-pipeline-v2.json). Recovery đầy đủ ở `C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261019/drama-existing-t2i-i2v-correction/`; raw project chỉ giữ local, không đưa vào Git. Không sửa source runtime nên không nhận lượt này là full regression mới. Browser read lần này BLOCKED; HTTP/code/hash verification không thay browser walkthrough.
