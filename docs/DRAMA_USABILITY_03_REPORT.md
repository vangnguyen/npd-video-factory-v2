# Drama: điểm vào, giọng thật và luồng xuất video

Phạm vi: `VF-DRAMA-ENTRY-VOICE-CHOICES-USABILITY-03`. Bản ứng viên chức năng: `24498c9585e68d4f44119e79d222e609b9c21b0a`, nhánh `codex/vf-drama-usability-03`. Studio phục vụ từ `C:\vfdr03`, URL **http://127.0.0.1:62684/?new=1**. Đây là môi trường review Native riêng, giữ dữ liệu review cũ; không phải triển khai production.

Đường mở: **Tạo video → Phim Drama → nhập tên phim → Tạo phim Drama**. Có thể mở [bản nháp nguyên bản đã chuẩn bị](http://127.0.0.1:62684/?project=4a492a1795ae4b83b393a20db6f623a7). Bản nháp này chưa được Owner xác nhận nhân vật, chưa chọn giọng, chưa có tư liệu, job hoặc approval. [Thư viện giọng](http://127.0.0.1:62684/?view=voices) cho phép nghe mẫu trước khi phân vai.

## Kết quả theo mốc

| Mốc | Trạng thái và thay đổi nhìn thấy được | Bằng chứng / giới hạn |
| --- | --- | --- |
| M1 | Đã nối UI thật: ba loại video, profile Drama riêng, năm bước; tạo phim trống trước khi có kịch bản/tư liệu | `production_workflows.py`, `drama-workflow.mjs`; HTTP và DOM contract. Browser thật chưa kiểm được |
| M2 | 25 preset được phát hiện, 25 có căn cứ nguồn được đăng ký nội bộ, 10 mẫu audio thật của 10 preset khác nhau | `m2-real-samples.json`; hash WAV/manifest/voice và phản hồi HTTP khớp. Không suy ra Owner nghe duyệt |
| M3 | Nối kịch bản/nhân vật/tư liệu/thoại/xem thử/duyệt/xuất; nghe từng câu; đổi giọng có tái sử dụng clip của nhân vật khác | Diễn tập local thật ở workspace riêng; 4 clip ban đầu, đổi giọng tạo 2 clip và dùng lại 2 clip; preview/render/QC/cover/SRT/caption/ZIP thật |
| M4 | Đã có kiểm thử Studio, renderer, API liên quan, mẫu kỹ thuật và diễn tập backup/restore; regression Native liên quan đã chốt; lượt rộng ghi riêng | Kiểm browser 1366×768 / 1920×1080 / 2560×1440 và Owner UAT còn mở. Không có ảnh browser để bàn giao |

Phiên bản và đường source nằm trong **Cài đặt → Thông tin ứng dụng**. Menu chính dùng tiếng Việt, Cài đặt mở trang chung; ASR chuyển vào mục nâng cao. Các tính năng social/analytics đã hoãn không nằm trong luồng chính.

## Cấu hình Drama thực tế

- Mặc định dọc 1080×1920, 9:16; người dùng có thể chọn 16:9, 1:1 hoặc 4:5 lúc tạo. Template `purpose=drama`, thời lượng theo audio đo được và khoảng nghỉ; không có logo/CTA/intro BĐS, nhạc mặc định tắt.
- Người kể mặc định tắt. Casting thuộc từng phim, thư viện giọng thuộc workspace. Dùng lại giọng giữa các phim được phép; cùng giọng cho hai vai có cảnh báo không chặn. Nhân vật không thoại không cần voice.
- Parser chỉ gợi ý người nói có nhãn; hành động trong ngoặc/`Hành động:` giữ ở phần hình ảnh. Câu không rõ người nói phải được chọn trước khi xác nhận. Bản nháp ý tưởng được lưu riêng; công cụ AI viết kịch bản Drama chưa cấu hình trong runtime review này.
- Xác nhận nhân vật tạo phân cảnh trên **canonical timeline hiện có**. Cả trình sửa cảnh và phân vai cùng cập nhật nguồn này. Không có timeline dựng phim thứ hai.
- Lưu nháp tự động không cấp approval. Lưu mất phản hồi dùng lại đúng request; nội dung người dùng sửa sau đó được giữ. Khi đổi sang video thường, trả đúng các node/panel cũ về vị trí ban đầu.
- Tư liệu dùng lại upload/Asset Picker/thư viện/crop/thứ tự cảnh đã có. Sau đổi thứ tự cảnh, có thao tác rõ ràng xếp bản nháp thoại theo cảnh và lưu lại. Không giả hoạt động tạo diễn xuất, lip-sync hoặc nhất quán nhân vật.
- TTS từng câu, đo PCM, nghe từng câu từ đúng audio đã kiểm chứng; compile không cấp quyền chạy TTS. Người dùng vẫn duyệt nội dung trước khi tạo thoại, nghe/áp timing, xem và duyệt preview, rồi duyệt tệp render trước khi xuất.

Không tự chuyển các project cũ thành Drama. Chuyển loại project cũ chưa được đưa thành thao tác UI trong bản này; không có chuyển đổi ngầm.

## Giọng đã cài và căn cứ quyền

SDK **3.8.3**, commit `85344322b7258b4e25479b692e8e3396baf9db34`; model **vieneu-v3-turbo**, revision `61b85e3d937fbbacb387714180e8182823512523`; ONNX CPU. Không nâng SDK/model, không thêm dịch vụ trả phí hoặc cloning. Profile Thùy Dung khóa cũ và dependency của nó giữ nguyên.

Danh sách lấy từ `voices_v3_turbo.json` của runtime đã cài, kiểm SHA theo profile khóa. Có 25 payload embedding/reference-code khác nhau; không nhân bản tên hoặc thay pitch/speed để tăng số lượng. Mô tả/vùng giọng lấy từ metadata nguồn, không đoán từ tên. Giao diện chỉ dùng speed 1 và style neutral mà adapter hiện hỗ trợ, không có slider vô tác dụng.

Model card ở revision khóa nêu phạm vi Apache-2.0 bao gồm preset embedding/reference code và cho phép nội dung thương mại dùng audio tạo ra. Bản local model card, LICENSE của SDK và manifest được kiểm hash trước khi nhập thư viện và trước khi inference với trạng thái `source_licensed`. Trạng thái này không đồng nghĩa Owner tự khai báo quyền hay đã nghe duyệt. API create/update thông thường không thể tự cấp trạng thái nhập nội bộ này. [SDK tại commit khóa](https://github.com/pnnbao97/VieNeu-TTS/blob/85344322b7258b4e25479b692e8e3396baf9db34/README.md), [model card tại revision khóa](https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Turbo/blob/61b85e3d937fbbacb387714180e8182823512523/README.md).

| Có mẫu nghe local thật | Metadata nguồn |
| --- | --- |
| Adam bựa | Nam · Bắc · tự nhiên |
| Trúc Ly | Nữ · Bắc · tự nhiên |
| Thiện Minh | Nam · Bắc · kể chuyện |
| Mai Anh | Nữ · Bắc · tin tức |
| Hải Đăng | Nam · Bắc · tự nhiên |
| Thùy Dung | Nữ · Nam · tin tức |
| Thiền Tâm Đức | Nam · Bắc · kể chuyện |
| Ngọc Huyền | Nữ · Bắc · tự nhiên |
| Quang Sơn | Nam · Trung · tự nhiên |
| Ngọc Trân | Nữ · Trung · tự nhiên |

15 preset còn lại đã đăng ký, chưa tạo mẫu thống nhất trước: Minh Đức, Phạm Tuyên, Thái Sơn, Xuân Vĩnh, Thanh Bình, Ngọc Linh, Đoan Trang, Thục Đoan, Minh Triết, Mỹ Duyên, Quỳnh Anh, Đức Trí, Kim Thanh, Adam, Quốc Tuấn. Người dùng có thể bấm tạo mẫu chủ động. Tổng mẫu tạo sẵn là **10**, không phải 25.

Hàng đợi mẫu: một worker, tối đa 10 yêu cầu đang chờ/chạy; không inference khi GET hoặc mở tab. Mẫu có khóa cache theo giọng/phiên bản/text/settings/runtime; tối đa ba lần thử chủ động, không tự thử lại sau crash. Tệp hỏng được kiểm hash; tạo lại không đè tệp cũ. Chỉ một mẫu phát tại một thời điểm.

## Kiểm thử và chứng cứ

- Full Studio ứng viên: **2.160 PASS, 0 FAIL/SKIP**, log `m4-studio-full-n5.log`.
- Renderer: **52/52 PASS**, typecheck PASS; source renderer không đổi từ snapshot kiểm `cb04dfd8` đến ứng viên.
- API liên quan: **141 PASS, 3 SKIP**, log `api-related-n2.log`; ba trường hợp cần PostgreSQL contention thật. Lượt đầu có 29 PASS/115 setup error vì TEMP dùng chung bị WinError 5; giữ log và chạy lại bằng thư mục tạm riêng, không sửa quyền thư mục hệ thống.
- Native liên quan: **182/182 PASS**, nguyên bộ mới, 345,051 giây (`native-related-candidate-n2.log`). Lượt trước 181 PASS/1 FAIL do kỳ vọng capability session cũ thiếu cờ Drama; đã sửa fixture và chạy lại nguyên bộ, không cộng replay. Lượt Native rộng bổ sung ở snapshot `21063783` được ngắt sau khi bộ liên quan của ứng viên hoàn tất; **không tính full PASS**. Chi tiết trong `regression-status.json`. Không cộng các replay thành full regression PASS. Lượt 110 test ban đầu có một lỗi thứ tự báo quyền; đã sửa và kiểm lại, không coi lượt đầu là PASS.
- Diễn tập thật: final MP4 **7,37 giây**, SHA `6584273d0c468e79dfd4231039af1fe536fd6ec2b09ce1500ad618ff024a977c`, 1080×1920; có preview, cover, caption, hashtag, SRT, QC, rights summary, manifest và ZIP. Đây là lời thoại thật qua VieNeu, tư liệu hình do chương trình tự vẽ có nhãn fixture. Các approval trong workspace này đều mang nhãn **AUTOMATED TECHNICAL REHEARSAL - NOT OWNER UAT**.
- Diễn tập thật được cô lập tại `C:\vfct\drama-uat-real-n1`; không cấp approval cho project Owner. [Chứng cứ](../evidence/drama-usability-03/m3-real-drama-rehearsal.json).
- Backup Native phát hiện `localplanning.sqlite3` đã tồn tại nhưng chưa được hỗ trợ; đã bổ sung đúng schema, version/history/integrity/active-operation guard, không bỏ qua database lạ. Backup/restore thực tế giữ 10 mẫu giọng, không inference lại. Archive 18.039.831 byte, SHA `632f623a6fa3331cccc05c21e2cdc9cb16f784fdb754646da4e2916f8cc9413b`; phục hồi riêng tại `C:\vfct\drama-review-restored-n2`. [Chứng cứ](../evidence/drama-usability-03/m4-backup-restore.json).

Mẫu waveform/adapter giả trong unit test chỉ là kiểm thử hợp đồng. Chúng không nằm trong 10 mẫu nghe thật và không dùng để xác nhận chất lượng giọng.

## Phần còn phải xác nhận

Công cụ browser lỗi ngay lúc khởi tạo: `failed to write kernel assets ... path specified ... os error 3`, kể cả sau reset được hỗ trợ. Không quan sát được DOM browser thật, không chụp được screenshot và chưa chạy được ba viewport. HTTP và DOM fixture không thay cho browser walkthrough. [Trạng thái browser](../evidence/drama-usability-03/browser-status.json).

Owner vẫn cần tự nghe/chọn giọng cho vai, xác nhận chất lượng lời thoại và xem video từ đầu đến cuối; kiểm phụ đề, crop, bìa, caption, thao tác xuất và mở thư mục. Chọn voice hoặc QC máy PASS không phải Owner UAT. Không tự ghi nhận nghiệm thu phát âm tên riêng hoặc usability.

Các lỗi/qualification full regression cũ giữ tại [FINAL_EXPORT_REGRESSION_STATUS.md](FINAL_EXPORT_REGRESSION_STATUS.md); kết quả mới không được dùng để che các lượt fail hoặc ba PostgreSQL case chưa chạy.

`SOURCE_PRESERVED=YES`; `ACCEPTED_ARTIFACTS_PRESERVED=YES` (15/15 kiểm hash); `RECOVERY_BUNDLE_VALID=YES` cho backup/restore đã nêu. Các cờ sẵn sàng sản phẩm toàn chương trình chưa chuyển sang YES: `FINAL_VIDEO_QUALITY_READY=NO`, `EXPORT_CENTER_READY=NO`, `DELIVERY_PACKAGE_READY=NO`, `EXPORT_HISTORY_READY=NO`, `DRAMA_VOICE_CASTING_READY=NO`, `OWNER_EXPORT_UAT_COMPLETE=NO`. Điều này tách nghiệm thu sản phẩm khỏi các capability kỹ thuật đã triển khai và kiểm chứng.

`OWNER_VOICE_UAT_REQUIRED=YES`; `OWNER_UAT_COMPLETE=NO`; `TECHNICAL_PASS=PARTIAL` vì browser walkthrough còn mở. `PLATFORM_API_PUBLISHING=DEFERRED`; `ANALYTICS=DEFERRED`; `FULL_TREND_RADAR=DEFERRED`; `PRODUCTION_DEPLOYED=NO`. Không merge main, không upload mạng xã hội, không thử xóa lại các thư mục đã bị policy chặn.

Source code đã push trên nhánh riêng. Delta Git bundle đã verify từ baseline export `4162bc32` đến commit chức năng `24498c95`; checksum baseline và delta, đường recovery đầy đủ ở [source-preservation.json](../evidence/drama-usability-03/source-preservation.json). Commit chứng cứ sau đó không đổi code đã kiểm. HEAD khởi động Studio/bytes HTTP cuối được ghi tại `recovery/20261018/drama-usability-03/final-serving-receipt.json`.
