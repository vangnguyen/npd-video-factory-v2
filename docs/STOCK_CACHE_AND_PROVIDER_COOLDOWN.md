# Bảo toàn nguồn gốc cache và thời gian chờ provider stock

Đã sửa lỗi cache có thể đổi nhãn dữ liệu mô phỏng thành dữ liệu official khi cấu hình provider thay đổi. Cache v2 ràng buộc provider, chế độ thực thi, credential hash, cấu hình, root và workspace. Cache cũ được giữ nhưng không dùng lại theo giao thức mới; không sửa lịch sử hoặc đổi nhãn dữ liệu cũ. Cùng binding có thể dùng lại qua adapter/tiến trình mới mà không gọi mạng. Body và envelope phải khớp hash; không ghi secret vào cache hoặc provenance.

Lựa chọn “bất kỳ” của Native được chuẩn hóa tại adapter thành giá trị trung lập; DTO, fingerprint và lịch sử giữ nguyên. I/O cache Windows hỗ trợ đường dẫn dài sau khi kiểm containment/link, gồm ghi tạm rồi thay file nguyên tử. Một lần kiểm thử trung gian không dọn được root dài do lỗi Windows; root đó được giữ, không thử xóa lại. Kiểm thử cuối dùng lifecycle có hỗ trợ đường dẫn dài và dọn đúng root mới.

Native lưu cooldown theo provider/config/mode/workspace/root và loại request API/CDN. Kiểm tra và lease trước wire dùng giao dịch ngắn, không giữ khóa DB qua mạng. Phản hồi bị giới hạn được lưu ngay trước khi chốt job; restart hoặc job khác vẫn phải chờ. Lease 45s có chống ghi đè bởi worker cũ; khi chỉ chờ và chưa gửi wire, không tiêu hao retry budget. Mỗi cost intent giữ claim riêng để không tái dùng một thao tác đã hoàn tất. Cache hợp lệ không đi qua wire gate.

`Retry-After` hỗ trợ số giây và HTTP date theo [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after). [Tài liệu Pexels](https://www.pexels.com/api/documentation/) mô tả quota/reset tháng trên phản hồi thành công. Vì vậy API 2xx có Remaining=0 và UNIX Reset hợp lệ tạo bằng chứng chờ tới đúng reset, gồm khoảng chờ 31 ngày trong fixture. Không suy ra quota hoặc sức khỏe khi header thiếu/sai; giới hạn đầu vào deadline là 366 ngày, không cắt deadline tháng còn 24 giờ. API cooldown không chặn CDN khi metadata cache hợp lệ có sẵn.

Backup ghi số bản cooldown và từ chối snapshot khi wire lease còn hiệu lực. Cooldown đang chờ, đã hết wire, không chặn backup. Bản sao khôi phục giữ nguyên hàng dữ liệu và hash bằng chứng. Đây là thử nghiệm SQLite thực trên root mới với HTTP/quota/identity fixture; không chứng nhận đọc tài khoản thật hoặc vận hành production. Cơ chế cooldown bền vững mới thuộc Native; common adapter/cache phục vụ cả SQL API. Quota bền vững và giải nghĩa retry trong toàn bộ SQL worker vẫn còn mở.

WAVE: 5A/8D/8F/15 component

STATUS: IMPLEMENTED_AND_MOCK_TESTED; local file/SQLite/process/restore tested; full waves PARTIAL

HEAD SHA: parent 7fb0806f1eea110559b7bbffa6fd6a535f2e356e; final in recovery/20261007/stock-foundation-program-state.json

CAPABILITIES COMPLETED: bound stock cache, mode/config rotation guards, Native orientation normalization, Windows long-path cache, durable Native cooldown/quota, atomic wire leases, zero-wire wait accounting, backup custody guards

CAPABILITIES PARTIAL: SQL worker-wide quota/retry parity, global quota accounting, cache byte/entry limits/eviction and crash staging retention, observed provider health, complete automated Source B-roll resolution/fallback, genuine provider/legal admission/Owner/full Mode A/B/production acceptance

TESTS: Native73 PASS across8 affected modules; API35 PASS across3 modules;27 new Native cases are included; targeted agent batches overlap and are not added

REAL PROVIDER TESTS: none; no API/OAuth secret, model inference or paid operation; actual local Windows file I/O, SQLite, restart/fresh process, concurrent workers and backup restore tested

MOCK TESTS: all provider replies, quotas, credentials, identities and media fixtures; clock advancement simulates long waits; denied transports prevent unintended network

EVIDENCE: [indexed evidence](north-star/stock-foundation-evidence.json); original contamination/any/cooldown repro, repaired tests, final Native/API logs and portable evidence ZIP

REGRESSIONS: old project/asset/timeline/history and fixture provenance retained; no automatic attachment, publishing or transferred approval; B-roll/resolution/backup suites pass; final source seal rechecks accepted artifacts and live source

EXTERNAL BLOCKERS: real stock credentials/legal admission/Owner/provider/production gates remain; broad cache/fallback and platform requirements still have code gaps

OWNER ACTION REQUIRED: none for safe continuation; real publishing/deployment/provider spending remain disabled; deferred UAT is unchanged

NEXT WAVE: standalone uploaded-audio ASR/transcript SQL path, shared SQL stock quota parity and original complete media resolution/cache/provider/platform requirements

SOURCE_PRESERVED=YES is established by final preservation seal. PHASE10_TECHNICALLY_READY=YES; OWNER_UAT_REQUIRED=YES; PHASE10_READY=NO. Matrix remains5 IMPLEMENTED_REAL/58 PARTIAL/1 NOT_VERIFIED,59 unclosed. IMPLEMENTATION_COMPLETE=NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO; VIDEO_FACTORY_NORTH_STAR_READY=NO.
