# QC cân bằng âm thanh Native

Increment này đóng thêm phần kỹ thuật của Wave 6/8/16; các nhóm 32/33/34/39/40/57/60/64 vẫn PARTIAL. Không thay thế nghiệm thu Mode A/B hay Owner UAT.

`services/windows_native/audio_balance.py` đo PCM stereo 48 kHz bằng cửa sổ 50 ms. Hai kênh được giữ khi tính năng lượng, tránh trường hợp tín hiệu ngược pha bị hiểu nhầm là im lặng. Các file tham chiếu và nhạc được tạo trong những lượt xử lý độc lập, dùng đúng file nguồn, gain, fade, normalization và sidechain của timeline. Graph render chính giữ nguyên; thêm đầu ra chẩn đoán vào graph chính đã gây cắt ngắn dữ liệu trong thử nghiệm đầu và được loại bỏ.

Trong lượt đo nhạc ducking, packet 1.024 mẫu và 250 ms buffer ở cuối các đầu vào giữ phần cuối khi FFmpeg kết thúc stream. Đầu ra được trim đúng thời lượng canonical; buffer nằm ngoài phần được đo. Hành vi packet/padding tham khảo [FFmpeg asetnsamples](https://ffmpeg.org/ffmpeg-filters.html#asetnsamples). Đây là kết quả triển khai và kiểm thử local, không phải kết luận về mọi phiên bản FFmpeg.

## Dữ liệu và ràng buộc

Các artifact mới: `audio-reference.f32le`, `audio-music.f32le` khi có nhạc, `audio-final.f32le`, các filter file theo role và `audio-balance.json`. Mode B thêm `audio-stem-manifest.json`, ràng buộc SHA của `timeline-render.json`. Mode A ghi đầu vào đo vào render manifest. Video cuối được decode thực; mọi file nguồn, tham chiếu, filter, manifest, document và video được ràng buộc SHA. File ngắn không được bỏ qua bằng phép so sánh đến stream ngắn nhất. Padding codec được báo riêng và không dùng để rút ngắn vùng đo.

Vai trò tham chiếu:

| Role | Ý nghĩa |
| --- | --- |
| `narrated_voice` | PCM narration đã đặt vào timeline; không xác nhận phát âm hoặc độ dễ hiểu. |
| `canonical_original_audio` | Âm thanh gốc canonical; có thể chứa nhạc hoặc tiếng động, chưa tách giọng nói. |
| `no_reference` | Không có track tham chiếu đang bật; kết quả `not_applicable`, không tuyên bố giọng nói đạt. |

## Policy mặc định

| Kiểm tra | Ngưỡng |
| --- | --- |
| Tham chiếu có hoạt động | RMS từ −40 dBFS, tổng ít nhất 80 ms |
| Tham chiếu so với nhạc | Cách ít nhất 6 dB; phần vi phạm không quá 10% thời gian hoạt động |
| Mix thiếu trong đoạn tham chiếu | Dưới −55 dBFS hoặc thấp hơn tham chiếu 18 dB; phần vi phạm không quá 2% |
| Giới hạn đo | 1.800 giây; đọc từng cửa sổ, không nạp toàn bộ PCM vào RAM |

Policy có version, digest, kiểu số chặt và giới hạn hữu hạn. Các ngưỡng là mặc định kỹ thuật; **chưa được hiệu chỉnh để chứng nhận chất lượng giọng nói hoặc cân bằng cảm nhận**. Metric không có dữ liệu là `null`. Chỉ giữ tối đa tám cửa sổ lỗi nặng nhất.

Lỗi tham chiếu mất hoạt động, nhạc lấn tham chiếu hoặc mix thiếu được ghi `failed_qc`. Worker không công bố final/checkpoint sẵn sàng khi QC thất bại. Các kiểm tra loudness, clipping, silence, frame và subtitle trước đó tiếp tục chạy. Preview narration giữ và kiểm chứng dữ liệu đo trước khi duyệt; render review/download và replay kiểm chứng lại PCM đã lưu, không gọi provider hoặc decode thêm. Checkpoint lịch sử giữ contract cũ và không được tự gán phép đo mới.

## Bằng chứng

- API: 12 PASS, gồm graph render giữ nguyên và PCM đã render không đổi khi xuất chẩn đoán riêng; ducking trên sóng thực.
- Native: 60 PASS, gồm render Source/narration, preview, QC, giữ nguyên source, chống thay artifact và hai lỗi worker thực: nhạc còn nghe được khi tham chiếu bị tắt; nhạc lấn tham chiếu đang hoạt động.
- Rehearsal lưu hai bộ backup Source/narrated; khôi phục trong tiến trình mới không có keys và tái tính PCM đạt. Transcript/giọng tone/human review trong rehearsal là fixture được đánh dấu rõ.
- Bản TTS local 9,42 giây đã có trước được đo trên bản sao. Hash video/source gốc giữ nguyên, không render hoặc inference lại, Owner listening vẫn pending.
- Chi tiết, đường dẫn và hash: [measured-audio-balance-evidence.json](north-star/measured-audio-balance-evidence.json). Các thử nghiệm ban đầu thất bại được giữ và không báo là PASS.

Lệnh tái tạo component evidence trên Windows, dùng thư mục đầu ra mới và mẫu local đã có:

```powershell
$env:PYTHONPATH='C:\vfns01\apps\api;C:\vfns01'
python scripts/north_star_audio_balance_evidence.py --output <fresh-output-directory> --sample-directory <prior-local-sample-directory>
```

## Phần còn thiếu

Chưa có chứng nhận ASR/VAD/ngữ nghĩa hoặc phép đo độc lập đảm bảo giọng nói còn nguyên khi bị nhạc che lấp trong mix. Âm thanh gốc chưa được tách voice/music. Còn kiểm định cảm nhận, hiệu chỉnh ngưỡng theo nguồn/giọng, provider thật, audio UI đầy đủ, quản lý retention/quota cho PCM diagnostic, QC nội dung và toàn bộ A/B/C cùng Owner/browser acceptance. Raw diagnostic hiện phải được giữ để replay; chương trình chưa tự xóa evidence đang được tham chiếu. Không suy ra rights, quyền publish, Owner UAT hoặc production deployment từ PASS này.
