# VF-DRAMA-REAL-VISUAL-PRODUCTION-08

Ngày 2026-10-19. Bộ tham chiếu và shot plan đã chuẩn bị; chưa có pilot chuyển động. Owner duyệt ba tham chiếu, **chưa duyệt chi phí**, yêu cầu giữ bản chuẩn bị. Không gửi job video, mua gói, nạp tiền hoặc tải model.

## Phạm vi quyết định

`DRAMA_VISUAL_ACCEPTANCE = NOT_ACCEPTED` áp dụng bản phim ảnh tĩnh cũ. `DRAMA_FILM_READY = NO`. Owner feedback được thêm vào event `owner_drama_visual_feedback`, không sửa/xóa render review, audio approval, caption, export hoặc lịch sử cũ. Duyệt tạo hình mới chỉ áp dụng ba ảnh có hash trong `owner-reference-decision.json`; không phải duyệt pilot, diễn xuất, quyền phát hành hoặc phim.

Giữ project nguồn `1c768012f9624de494a9fadab63c1a31` ở revision 8, An = Thùy Dung, Bình = Thiện Minh, narrator OFF. Kịch bản, ID/người nói/thứ tự tám câu, casting, canonical timeline và job gốc không đổi. Phim hình ảnh sửa mới cần preview/render/approval/version riêng.

## Application và source

- Studio `http://127.0.0.1:62684/`, source `C:/vfdr07`; build đang nạp `drama-m4-closure-07`, application commit `0eb7e679be6a138fff891987bd507ea4c82b8000`.
- Repository HEAD bắt đầu `a75c7678d61fc00d54fd5ed07a436aff56724f1a`: chỉ thêm báo cáo/bằng chứng sau application commit. Nhánh bàn giao mới `codex/vf-drama-real-visual-08` chỉ bổ sung hồ sơ/tham chiếu, không sửa source ứng dụng hoặc restart server.
- Source tree Native `7fcd5f6070a27bf2cd8ab8f1113929a94153217d`, Studio `5345ad3157dc28d83726ddf63e43a8eda7ff4647`, API `2eb30b1819b06f2187ede2c1b35202cdf0e7ee07` giữ nguyên. SHA/nhánh cached trong app-info khác report HEAD không có nghĩa browser nhận frontend cũ.

## Inventory thực tế

| Capability | Implementation/runtime | Trạng thái thực tế và giới hạn |
|---|---|---|
| Ảnh nhân vật/bối cảnh | Built-in `image_gen.imagegen`; model/revision không được tool trả về | REAL: ba ảnh; bối cảnh dùng hai reference nhân vật thật đã sinh. Đây là công cụ của phiên làm việc, chưa phải image provider được cấu hình trong Studio. |
| Native ảnh/biến thể | `generation_registry.py`, `generation_queue.py`, ComfyUI bridge; manifest `v2-06.1`, definitions `1.0.0` | `NOT_CONFIGURED`; 0/8 graph executable được Owner duyệt; model là placeholder owner-provisioned. Không có ảnh sinh từ bridge thật. |
| Native T2V/I2V/reference-assisted | Các adapter/provider-neutral và job/reference/artifact contracts đã có | `NOT_CONFIGURED`, `owner_enabled=false`, chưa có runtime/model/provider credential cho lần chạy thật. Mock tests cũ không được gọi là real video generation. |
| Cloud video được chọn để đề xuất pilot | HeyGen connector `reference_to_video`, model `heygen-video-1`; backend revision không lộ ra | Kết nối đọc profile thành công, plan Free, credit/balance null. Chưa xác minh quyền API trả phí/đơn giá. Không gọi create/upload video; chưa có Studio adapter HeyGen. |
| I2V/T2V cloud | Cùng connector/model, schema hiện hành | Có interface; chưa chạy thật. Không tự thay reference-assisted bằng T2V hoặc avatar. |
| Lip-sync đúng audio An/Bình | Không có Native adapter đã kiểm chứng cho phim này | `NOT_TESTED`; không gọi việc model tự sinh thoại là khớp môi audio đã duyệt. |

Máy có GTX 1050 Ti 4096 MiB VRAM; đầu kiểm tra còn khoảng 3,1 GiB VRAM và 0,77 GiB ổ C. Các manifest video hiện có ghi nhu cầu 24 GB, chưa có model được provision; không suy rộng rằng mọi model khác đều không thể chạy. Không tải model lớn, đổi SDK/runtime hoặc bật ComfyUI. Các cổng local đã đối chiếu 8188/8189/8190/8090 không có listener lúc kiểm tra.

Đã đọc [HeyGen model documentation](https://developers.heygen.com/docs/models/heygen-video): scene generation hỗ trợ tham chiếu; route yêu cầu paid API keys. Account Free với số dư null chưa đủ căn cứ xác nhận được phép chạy. Giới hạn/thông số proposal đối chiếu thêm [API reference](https://developers.heygen.com/reference/create-heygen-video): chọn 3 job, mỗi job 5 giây, 768p, portrait. Không dùng giá khởi điểm quảng cáo làm báo giá Ref2V cho tài khoản này. Đơn giá thực tế và nguồn thanh toán vẫn NOT_VERIFIED.

## Tham chiếu và Studio

Ba ảnh sinh thật, nhân vật hư cấu trưởng thành; không dùng ảnh người thật làm reference:

| Input | Kích thước nguồn | SHA256 |
|---|---|---|
| An, mặt và toàn thân/trang phục | 1536×1024 | `06668966fc4e81c9d300d50d659e710a842beeb27e28449ff7e7eee536c3d7db` |
| Bình, mặt và toàn thân/trang phục | 1536×1024 | `68f36e17be2b731d95b6c91917456bb1b383ff016db88f960a47c752886c8ef0` |
| Quán cà phê, hai nhân vật/đạo cụ/bố trí | 941×1672 | `0598de0fefee4e9f3ae687785adf0c30cd2910814e83882b810d26cfd4d39bea` |

Owner duyệt cả ba tham chiếu bằng phản hồi trực tiếp. Giữ raw PNG và fingerprint; Native intake tạo bản thư viện JPEG và giữ original PNG với hash riêng. Dùng Asset Library có sẵn, không thêm hệ quản lý nhân vật hay state dựng phim thứ hai.

Bản nháp chứa tư liệu `213be24a515e4cf48c7857cf31f55e71`, revision 5; chưa có kịch bản dựng, casting mới, scene binding, canonical timeline, approval hoặc job. Đây là chỗ lưu input hình ảnh, không phải một phim đã sản xuất. [Mở thư viện](http://127.0.0.1:62684/?view=assets). Chọn bản “Lá thư trước cơn mưa · Tư liệu tạo hình v2 · Chưa duyệt” để xem nguồn dự án. Không sửa project phim gốc.

Các asset giữ `source_type=ai_generated`, provider/image tool, source reference, generation provenance, `rights_status=unknown`, `rights_confirmed=false`, `production_eligible=false`. Duyệt tạo hình không được nâng thành quyền phát hành. Nhãn file “CHƯA DUYỆT” giữ thời điểm nhập trước phản hồi; event và manifest mới ghi rõ Owner đã duyệt tham chiếu. UI library hiện vẫn dùng nhãn nguồn chung “Tải lên”; chưa có hiển thị review state tạo hình chuyên biệt. Không trình bày các nhãn này là chức năng đã hoàn thiện.

Browser Chrome Work thật mở ba thumbnail và ảnh bối cảnh trong Asset Picker thành công; không chọn checkbox hoặc xác nhận gán ảnh vào scene. [Screenshot thật](../evidence/drama-real-visual-08/studio-reference-library-real-browser.jpg). Đây là kiểm tra thư viện ở viewport hiện tại, không phải full walkthrough M4 ba viewport hoặc nghiệm thu Owner về khả năng sử dụng.

## Shot plan và pilot hữu hạn

Kế hoạch 9 shot từ đúng kịch bản đang lưu; [bảng dựng dự kiến](../evidence/drama-real-visual-08/SHOT_PLAN_V1.md). File đầy đủ `shot-plan-v1.json` ở recovery giữ exact dialogue/line IDs, per-line audio URLs/hash, hành động, biểu cảm đầu/cuối, phản ứng người nghe, góc máy, props, timing và continuity. Đây là đề xuất nhập vào canonical timeline khi có clip và duyệt, không phải timeline thứ hai tự điều khiển dựng.

Pilot P01–P03: ba clip nguồn 5 giây, dựng 11,07 giây (bao gồm khoảng nghỉ có sẵn 0,03 giây). P01 An nhấc phong bì, Bình quay lại và bớt lo; P02 An đưa phong bì, lắng nghe Bình kể về bức thư; P03 Bình phản ứng ngập ngừng với câu hỏi của An. Giữ An trái/Bình phải, trục 180°, cùng quán/ánh sáng/trang phục; một phong bì, hai ly, một ô gấp. Cắt thẳng có chủ ý. Camera khóa, nhân vật hành động thật; không dùng ảnh zoom/pan/fade/loop thay shot.

Chưa qualified lip-sync nên mỗi shot tập trung mặt người nghe phản ứng; người nói ngoài khuôn miệng/quay lưng. Không thêm lời dẫn hoặc thoại mới. Nếu đầu ra tự có tiếng, bỏ toàn bộ track provider, dùng đúng audio An/Bình. Nếu muốn quay rõ người đang nói trực diện, phải kiểm chứng lip-sync riêng trước.

Nguồn proposal 768p portrait theo docs là 768×1344; target cuối vẫn 1080×1920. Cần kiểm actual dimensions rồi pad đúng tỷ lệ trước scale, không kéo giãn; phải công bố source resolution/upscale. Chưa có clip để kiểm hoặc chứng nhận các bước này.

Tối đa ba request, một attempt/shot; không retry tự động, không tạo phần còn lại trước Owner duyệt pilot. Trần 3 USD đã được hỏi nhưng **Owner chưa duyệt**. Vì vậy `dispatch_allowed=false`. Ngoài ngân sách còn cần xác minh paid API entitlement/đơn giá. Không mua gói/nạp tiền và không chuyển sang provider khác để vượt quyết định này.

## Audio, bảo toàn, kiểm tra

Tám audio endpoint thật đã đọc, đo PCM và hash riêng; không gọi TTS. WAV đã duyệt 35,07 giây, SHA256 `6e6a31855cdfd7da30d844cbf31c3710fd1a5de26899d63ebe934d786a01215c`; timeline gốc 35,32 giây. Audio sẽ được reuse khi input đủ điều kiện, không stretch, không bù dead air cho clip.

Đã kiểm 15 video lịch sử giữ nguyên hash, MP4 cũ `a57f965e530b5100ea13d03464cf38d23300f9245f1e973e30ebf48a36381ef8`, ZIP cũ CRC PASS, recovery source/state files giữ nguyên. Đọc lại project gốc bằng HTTP sau thao tác thêm references/events: không đổi document/revision/casting/timeline/audio/jobs/approval. Không xóa đường dẫn từng bị policy chặn.

Không sửa source runtime nên không chạy lại full regression hàng giờ để gọi là kết quả mới. Qualification candidate 0eb7 trước đó giữ nguyên: Studio 2168 PASS; renderer 52 PASS/typecheck PASS; full Native 2313 PASS; API liên quan 92 PASS. Full API cũ có lỗi và 3 PostgreSQL NOT_RUN vẫn giữ riêng, xem [báo cáo M4 gốc](DRAMA_M4_REAL_EXPORT_CLOSURE_07.md). Không chứng nhận production/SQL/Docker hay diễn xuất từ những test này.

## Trạng thái bàn giao

| Trường | Trạng thái |
|---|---|
| ACTUAL_IMAGE_PROVIDER | OpenAI built-in image_gen; 3 real outputs, model/revision không được trả về |
| ACTUAL_VIDEO_PROVIDER | NONE executed; candidate HeyGen Video `heygen-video-1` |
| REAL_GENERATION_AVAILABLE | IMAGE=YES; NATIVE_VIDEO=NOT_CONFIGURED; CLOUD_VIDEO_ENTITLEMENT=NOT_VERIFIED |
| EXTERNAL_BLOCKER / BUDGET_REQUIRED | Owner chưa duyệt chi phí; paid API entitlement/đơn giá chưa xác minh |
| CHARACTER_REFERENCES / ENVIRONMENT_REFERENCE | An/Bình/quán v1: Owner APPROVED_REFERENCES_ONLY |
| SHOT_PLAN | 9 shot/35,32 giây; pilot 3 shot/11,07 giây; proposal, chưa nhập canonical timeline |
| REAL_MOVING_SHOTS / STATIC_SHOTS_AND_REASON | 0 generated / 0 ảnh dùng làm shot diễn xuất mới; ảnh chỉ làm input |
| PILOT_VIDEO | NOT_CREATED |
| VISUAL_LIMITATIONS | Chưa đánh giá được motion/acting/identity continuity; lip-sync chưa test; source upscale dự kiến |
| OWNER_VISUAL_DECISION | OLD_FILM=NOT_ACCEPTED; NEW_REFERENCES=APPROVED; NEW_PILOT/NEW_FILM=NOT_REVIEWED |
| EXISTING_AUDIO_REUSED | 8 clip/WAV bảo toàn và xác minh; chưa có bản dựng mới để mux |
| LIP_SYNC | NOT_TESTED |
| FULL_FILM_STATUS | PREPARATION_ONLY, chưa được phép gọi video có phí |
| DRAMA_FILM_READY | NO |
| PRODUCTION_DEPLOYED | NO |

Publishing API, Analytics và Full Trend Radar tiếp tục DEFERRED. Không merge main, deploy hoặc đăng mạng xã hội. Bước tiếp theo chỉ bắt đầu khi Owner thay đổi quyết định chi phí và có quyền API/đơn giá hợp lệ; không hỏi lại để ép duyệt trong lần bàn giao này.

Recovery: `C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261019/drama-real-visual-08/`. Bộ này giữ reference PNG, provenance, script baseline riêng tư, shot prompts, audio hashes, quyết định Owner và trạng thái mới; raw private screenplay/account billing/session không đưa vào Git.
