# Reviewed B-roll recovery, internal resolution and local media evidence

Ngày 2026-10-15. Mã nguồn tích hợp: `4f9d2cdf870ce61d6074a2f71472f8958bd44e07`; video được thực thi trước đó tại `b7bbb027b4951382f9861eecaa581163b202293d`. Đây là tiến độ Waves 3/6/8/16, chưa đóng toàn bộ wave hoặc Mode B.

## Hành vi đã triển khai

Studio có thao tác đọc xác minh và dừng đúng yêu cầu chuẩn bị B-roll bị mất phản hồi. Server lưu biên nhận dừng riêng, giữ nguyên kế hoạch, biên nhận gốc và kết quả đến muộn. Thao tác yêu cầu xác nhận của người dùng; chỉ gỡ đúng bản ghi đang giữ sau khi callback đã chứng minh kết quả và quyền sở hữu bản ghi. Không chạy provider, áp dụng timeline, hoàn tiền hoặc xóa dữ liệu dự án trong bước khôi phục.

Phần xử lý asset nội bộ có GET ngữ cảnh, POST chọn rõ asset đã lưu và GET đúng cặp request/job ban đầu. Một giao dịch SQL ghi biên nhận và job; GET không ghi hoặc giao việc. Retry tường minh dùng lại job gốc. Redis handoff dùng LREM/RPUSH nguyên tử cho cùng ID; SQL chỉ cho một lần nhận job và một claim token riêng. Mất ACK có thể phát lại thông điệp; không tuyên bố exactly-once xuyên Redis/SQL. Job đang chạy bị gián đoạn tiếp tục UNKNOWN, không tự nhận lại. Token worker không xuất hiện trong DTO công khai.

Worker kiểm tra bytes, toàn bộ nguồn/asset custody, quyền sử dụng và nguồn timeline trước khi chạy và ngay trong giao dịch hoàn tất. Kết quả cũ không thể ghi thành công khi nguồn thay đổi hoặc job đã bị hủy. Đường legacy chưa đánh dấu được giữ; admission legacy không chiếm item đang thuộc job đã review. Không có migration/schema mới hoặc chỉnh hạ tầng NPD/Agent Hub.

API canonical placement và controller đã có từ các commit trước. Root UI cho placement cùng controller chọn/quan sát internal resolution đang được phát triển riêng; không suy diễn chúng đã có trên UI từ API này.

## Kiểm chứng và phạm vi

| Phạm vi | Kết quả | Giới hạn |
| --- | --- | --- |
| Recovery sau tích hợp | Studio 1.758 PASS, 0 fail/skip, 12.268,1877 ms; SQL/API 32 PASS, 133,85 s | Node DOM/transport/storage fixtures; SQLite/ASGI xác thực fixture; không browser/provider |
| Recovery độc lập N2 trước tích hợp | 4 SQL PASS và 5 Node PASS, findings trống | N1 từng phát hiện lỗ hổng ghép authority; raw repro và bản sửa được giữ |
| Internal resolution tác giả | 31 ca mới PASS, 167,64 s; 20 ca legacy PASS, 170,61 s | Hai tập riêng; các lần thử trước có overlap, không cộng dồn |
| Internal resolution độc lập | 3 ca mới PASS, 23,54 s; static review source9 PASS | Kết quả terminal sai provenance không được nhận/chạy lại; caller không sở hữu không đổi job; token giả bị chặn |
| Main sau tích hợp resolver | 8 PASS, 28 deselected, 25,37 s | Chủ động chọn worker/concurrency/coexistence và recovery auth; không phải full backend rerun |
| Internal contract capture | 10 HTTP records, 1 ca PASS, 6,48 s | Actual main/SQLite/local fixture bytes; GET 0 DML/handoff, receipt nguyên, timeline không đổi |

Helper review N1 của Root đã lỗi trước test vì fixture đồng bộ chặn loopback của Windows asyncio. N2 chỉ đổi thành async fixture, giữ nguyên các phép kiểm tra và mã sản phẩm; raw N1/N2 được giữ. Lần author đầu có 21 ca đạt nhưng teardown lỗi tương tự không được tính thành acceptance; bản cuối 31 ca đạt đầy đủ.

## Video kỹ thuật được giữ nguyên

Trên bản sao SQLite riêng, dùng nguồn benchmark đã lưu, một asset testsrc2 chuyển động tạo bằng FFmpeg và một internal reuse job. Flow thực: reviewed prepare → internal asset reuse legacy → reviewed canonical placement v6→v7/replay → PCM → Remotion review → Full QC. Đây chưa phải flow qua resolver mới hoặc thao tác browser.

Video: `C:/vfct/broll-reviewed-media-n1/render-evidence/review.mp4`, 1.459.441 bytes, SHA256 `f7a559bbb2757e6edd2667441af65bbcdbe0c879d5e21bef9e2289e821e125ae`. Review proxy 540×960, 30 fps; canonical timeline 1080×1920, 6,368 s. File đo được 6,421 s, A/V delta 0,055 s. Không phải final render vertical-short 1080×1920.

QC thực `passed`: không black/freeze/decode error/clipping/silence; `publishing_blocked=true`. Signalstats chỉ đo luma, không semantic Vision. PCM 48 kHz/stereo giữ nguyên 1.222.880 bytes, SHA256 `164a8a1c02c41f576459aac10cb3a733a746761301d9946ae273d860e3aaa0a0`. Hai frame đã decode và xem; bố cục/timecode theo asset chuyển động. Kiểm tra raw RGB ban đầu vượt ngưỡng MAE 8/255, đạt 16,7073 tại 1 s; bản ghi N2 chỉ xác nhận nhận dạng hình theo không gian. **Color fidelity NOT_VERIFIED**; cần kiểm tra conversion/tag màu trước nghiệm thu chất lượng màu. Không chuyển thất bại này thành kết quả RGB PASS.

87 bảng giữ nguyên schema; không xóa hàng cũ. Chỉ hai bảng có hàng cũ đổi: `timelines` tăng current version và `production_packages` đổi liên kết timeline/subtitle/audio/review tương ứng. Upload, transcript, analysis và mọi phiên bản timeline cũ được giữ. Database gốc và source gốc ngoài bản sao giữ nguyên bytes. Có thêm các hàng asset/plan/job/evidence/version/render riêng cho lần thử này.

FixtureQueue cũ không phân biệt queue key: một ID media-resolution đã hoàn tất còn trong FIFO bị wrapper của worker từ chối trước processor/SQL; sau đó đúng render job đã chạy thành công. Raw log được giữ. Không dùng lần thử này làm bằng chứng Redis isolation hoặc queue production.

Archive `broll-reviewed-media-evidence-n1.zip`: 62 file, 18.134.722 bytes, SHA256 `659e69863f2f181bdfed086e28606dc740a5694bafd2bdb4ec2f32c536d31be9`. CRC và toàn bộ bytes/SHA từng file đã kiểm tra. Gồm video/PCM/manifest/SRT/QC/API capture/database trước-sau/source/motion/pins và raw helper; video failed-QC cũ vẫn thiếu file vật lý, không bị thay thế bằng video mới.

## Khoảng trống và nghiệm thu tiếp theo

| Hạng mục | Trạng thái / mức độ | Phụ thuộc / wave | Acceptance tiếp theo |
| --- | --- | --- | --- |
| Recovery yêu cầu chưa tới server, credential gốc đã đổi và không có witness | PARTIAL / P1; vẫn khóa và giữ bản ghi | Witness ký server riêng, Waves 3/8 | Cùng actor/exact roles, key rotation/restart/registry cũ bị prune; seal đúng namespace; POST gốc đến muộn bị chặn; v1 không bị nới lỏng |
| Placement và internal resolution trên UI | PARTIAL / P1 | Root UI/controller đang làm song song, Wave 3 | Chọn/đọc/xác nhận rõ; GET current→history→current; callback guard sau mọi await; cold/foreign-pending; browser 1366/1920/2560 |
| Màu render | NOT_VERIFIED / P1 | Đo tags/conversion ở renderer, Waves 6/16 | Giải thích/chỉnh conversion và kiểm tra màu bằng nguồn được gắn tag, giữ raw frame/video cũ |
| Full Artifact A và Mode A/B | PARTIAL / P0 | Genuine source, ASR/semantic Vision, UI và các wave khác | Bộ A/B/C đủ file và evidence; Owner UAT riêng; không suy diễn từ fixture |
| Production | NOT_VERIFIED | PostgreSQL/Redis/S3/Docker/soak/restore, Waves 8/15 | Stack disposable kiểm chứng; production deployment cần Owner riêng |

Witness là khoảng trống implementation nội bộ, không phải thiếu API key bên ngoài. Các provider chưa cấu hình không chặn những việc an toàn còn lại. Tổng ma trận vẫn 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED; 59/64 nhóm lớn chưa đóng.

## Source preservation và trạng thái

Recovery được chia ba commit `43862447`, `b28a82a1`, `7515451b`; resolver `4f9d2cdf`. Tất cả đã đẩy lên `codex/vf-north-star-completion-01`, có Git bundle riêng; không merge main. Các index: [recovery](north-star/broll-preparation-recovery-evidence.json), [resolver](north-star/broll-internal-resolution-evidence.json), [local media](north-star/broll-local-media-evidence.json).

SOURCE_PRESERVED=YES. PHASE10_TECHNICALLY_READY=YES, OWNER_UAT_REQUIRED=YES, PHASE10_READY=NO. IMPLEMENTATION_COMPLETE=NO, REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO, PRODUCTION_DEPLOYED=NO, VIDEO_FACTORY_NORTH_STAR_READY=NO. Không có yêu cầu approval, final render, real publish, model ASR/TTS mới hoặc chi phí/provider bên ngoài trong lần video này.

Thao tác xóa cache renderer tái tạo được đã bị cơ chế phê duyệt tự động chặn; công cụ không cung cấp lý do chi tiết. Cache vẫn còn, không tính 24.110.132 bytes đó là dung lượng đã giải phóng. Không thử đường xóa khác.
