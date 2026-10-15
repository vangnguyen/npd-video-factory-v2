# Studio xử lý âm thanh và đồng bộ timeline SQL

Đã ghép cấu hình normalization/ducking vào Studio trên canonical timeline, source `6b39993c2003802ceffcfbc46475cda16268c748`. Người sửa có thể đọc và lưu chín trường với xác nhận riêng; saved processing metadata đi vào shared proxy/canonical production graph. Chưa chứng nhận Mode A/B hoặc một nhóm North Star hoàn tất.

Panel dùng app shell hiện có. GET cho viewer; PUT cần verified human editor, writes enabled, exact project/workspace/source, timeline ID/version và request key. Ba tùy chọn mặc định false, threshold0,02. Không tự chạy DSP/render/provider hoặc tự phê duyệt khi đổi cấu hình. Audio track đã khóa và bản sửa khác đang chờ đều chặn ghi. Lưu hợp lệ làm stale preview/review/approval cũ; source media không đổi.

Controller giữ body/key và token SHA của yêu cầu chưa biết kết quả. Phiên/role/expiry/literal token, source hoặc draft thay đổi sau bất kỳ await nào đều ngăn nhận kết quả. Reconcile chỉ nhận receipt hiện tại đúng actor/parent/result/body, hoặc cho phép thử lại đúng yêu cầu ở cùng parent; không đoán theo số version. Studio đọc processing→history→processing và chỉ cài DTO nguyên vẹn khớp toàn bộ, không gọi loadProject để tái chốt CAS.

Hai lỗi được phát hiện bằng bằng chứng thật hoặc repro riêng. Capture ASGI N1 trả updated_at có Z sau PUT nhưng SQLite GET thiếu Z; TimelineRead hiện chuẩn hóa UTC tại DTO, giữ microseconds, không sửa database/history/source clock. Test actual main roundtrip trước sửa FAIL; N2 giữ nguyên raw response với năm TimelineRead bằng nhau. Không sửa timestamp trong fixture để làm test qua.

Kiểm tra độc lập phát hiện history có cùng head ID/snapshot nhưng khác actor hoặc mutation receipt vẫn được nhận và xóa UNKNOWN. Bản sửa kiểm chính xác head actor, type source-audio-processing, hai cờ false và full receipt trước nhận. Generic Word history không đổi. Giữ source ZIP/repro trước sửa,13 ca FAIL trước sửa và toàn bộ log cũ. Independent58 ca sau sửa kiểm cả failed save/reconcile giữ UNKNOWN nguyên byte, chỉ xóa đúng intent khi history trở lại hợp lệ, mỗi flow chỉ một PUT mock.

| Batch có source riêng | Kết quả / giới hạn |
| --- | --- |
| Full Studio tại working bytes được commit6b399 | 1181 PASS/0FAIL/0SKIP,6551,169ms. Root shell68 và module20 nằm trong batch; không cộng thành suite lớn hơn. Node transports/races mô phỏng trên raw actual ASGI DTO. |
| Independent history review | 58 PASS:28 direct reject,28 controller UNKNOWN/reconcile,2 valid controls; không actual HTTP/SQL/browser. Findings=[]; original P2 được đóng. |
| Processing API sau UTC tại d6e166 | 30 PASS/76,44s actual isolated SQLite/ASGI; metadata CAS/receipts/guards, không DSP. |
| Main route + legacy auto-edit tại UTC fix | 9 PASS/24,18s; six main cases và three legacy cases. Earlier main5 là subset/history, không cộng. |
| Canonical audio full32 tại4196b31 | 32 PASS/96,77s; bounded local FFmpeg PCM, graph/reuse/terminal fixtures. Không provider/Remotion/Owner acceptance. Subsequent UTC/UI không đổi production audio modules; không gắn lại source của run cũ. |
| Actual capture N2 tại d6e166 | 11 ASGI requests,1logical metadata CAS2→3,1exact replay,1stale409; five whole TimelineDTO rawequal. SQL48SELECT/3UPDATE/1INSERT, không gọi một physical UPDATE. Schema, all non-timeline rows và original history không đổi. |

Browser host tại6b399 chạy28HTTP=27GET+1HEAD,27×200/1×401; source419files, seed/clone87tables và object nguyên,0mutation, PID/port đóng bình thường. Phiên CUA trả apps=[]/browsers=[]; documented createBrowserTab trả Browser is not available: chrome. Không bootstrap, screenshot hay processing endpoint GET. Vì vậy processing form/defaults/1366–1920–2560 là NOT_VERIFIED; Word browser N2 lịch sử không được dùng thay. API behavior và Node form assertions giữ nhãn riêng.

Rà soát tiếp theo xác nhận lỗi SQL shot editing bằng TimelineService.mutate/schema thật, repository chỉ RAM: trim5s giữ audio11,34s; speed2 giữ audio/caption clock cũ; split giữa từ1,64s được nhận; xóa source cuối còn audio/caption. Native linked-source implementation đã có; SQL command và UI canonical handoff đang được triển khai riêng. Chưa coi RAM repro là SQL/backend exploit hoặc fix đã hoàn thành.

Evidence index: `north-star/processing-studio-evidence.json`; recovery root giữ source ZIP, incremental bundle, raw capture/logs và browser integrity proof. Không sao chép lại accepted video hay model vào metadata archive. Không xóa dữ liệu trong đợt này. Phase10 technically ready=YES/Owner UAT required=YES/Phase10 ready=NO. SOURCE_PRESERVED=YES; IMPLEMENTATION_COMPLETE/REAL_PROVIDER_ACCEPTANCE_COMPLETE/PRODUCTION_DEPLOYED/VIDEO_FACTORY_NORTH_STAR_READY=NO. 59/64 nhóm còn chưa đóng.
