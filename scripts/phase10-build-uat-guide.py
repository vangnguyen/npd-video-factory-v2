"""Build the human campaign guide from actual isolated preparation IDs."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.windows_native.pipeline import REPO

out=REPO/'evidence/post-mvp-roadmap/phase-10'
receipt=json.loads((out/'uat-preparation.json').read_bytes())
lines=['# Phase 10 — nghiệm thu chiến dịch trong Studio', '',
'Studio UAT: [Hàng chờ nội dung](http://127.0.0.1:8030/production). Dữ liệu nằm riêng tại `C:/NPD-Video-Factory/phase10-uat`; các video đã duyệt trong dữ liệu chính được giữ nguyên.', '',
'## 1. Chọn 10 ý tưởng', '',
'Mở từng bộ nghiên cứu bên dưới, xem nguồn/thời điểm, rồi chọn một trong năm ý tưởng. Có thể sửa hook, góc nhìn, CTA và brief. Đây là nghiên cứu đã lưu từ Phase 9, không phải một lượt tìm nguồn mới. Các nguồn chưa rõ ngày hoặc cần đối chiếu được hiển thị riêng. Chưa có lựa chọn hay duyệt Phase 10 của Owner trong các bộ này.', '',
'| Ca | Ý tưởng đứng đầu để tham khảo | Mở nghiên cứu |', '|---|---|---|']
for case in receipt['campaign_cases']:
    title=case['ideas'][0]['title'].replace('|','\\|')
    lines.append(f"| {case['case']:02d} | {title} | [Mở bộ {case['case']:02d}](http://127.0.0.1:8030/intelligence?run={case['run_id']}) |")
lines+=['', '## 2. Lên kế hoạch và chọn ít nhất 5', '',
'Trong Hàng chờ, tìm `Phase10 · thử nghiệm Studio`. Bấm **Xem / lên kế hoạch** để đặt ưu tiên, ngày dự kiến, định dạng, thời lượng, chiến dịch và người thực hiện. Xem phần **Nguồn và thời điểm** và **Điểm ưu tiên và lý do**. Điểm chỉ là gợi ý từ cấu hình, chưa dự báo lượt xem hay khách hàng.', '',
'Chọn ít nhất năm nội dung để tiếp tục. Nếu xuất hiện **Nội dung gần giống**, xem các điểm giống và nhập lý do tiếp tục khi thực sự muốn làm bản mới. Lý do và tên người duyệt được lưu với đúng phiên bản; thay nội dung có thể yêu cầu đối chiếu lại.', '',
'## 3. Duyệt brief, kịch bản và storyboard', '',
'Duyệt brief của năm nội dung đã chọn trong Nghiên cứu & ý tưởng. Quay lại hàng chờ, chọn chúng, điền tên người thực hiện, xác nhận bước muốn chạy và bấm **Tạo kịch bản đã chọn**. Batch chỉ đưa kịch bản vào hàng chờ; từng kịch bản vẫn cần duyệt.', '',
'Mở từng dự án, kiểm tra và lưu lời đọc ở **Script**, rồi **Duyệt riêng kịch bản**. Sau đó có thể chọn các dự án trong hàng chờ và bấm **Lập storyboard đã chọn**. Thêm/chọn media và kiểm tra quyền sử dụng trong **Assets**, rồi xem **Storyboard**. Kịch bản, media và cách dựng phải được duyệt trước khi tạo giọng đọc/video.', '',
'## 4. Thực hiện đủ năm thao tác trên các dự án của chiến dịch', '',
'Người dùng trực tiếp thực hiện các thao tác dưới đây; có thể chia chúng giữa năm dự án. Ghi lại dự án và số shot trước/sau.', '',
'| Thao tác | Cách thực hiện | Cần quan sát |', '|---|---|---|',
'| Thay nguồn | Chọn shot → Thay nguồn media → Lưu shot | Chỉ nguồn cảnh đã chọn đổi; lời đọc không đổi |',
'| Sửa lời đọc | Sửa Lời đọc → Lưu shot | Phụ đề mặc định theo lời mới; phụ đề tự sửa được giữ; lời mới cần duyệt |',
'| Sửa thời lượng | Đổi Thời lượng → Lưu shot | Thời lượng và các mốc sau cập nhật; render báo lỗi nếu lời đọc không vừa |',
'| Đổi thứ tự | Kéo thẻ shot hoặc dùng Trước/Sau | Hình, lời đọc và tuỳ chọn đi cùng ID cảnh |',
'| Tạo lại cảnh | Đề xuất & lịch sử shot → Đề xuất lại nguồn cảnh | Chọn nguồn khác từ thư viện hiện có; không giả lập hình AI mới |', '',
'Có thể thử **AI Edit**: nhập yêu cầu cho shot, xem đề xuất và các cảnh phụ thuộc, rồi chủ động bấm áp dụng. AI không duyệt hoặc render. Sửa lời đọc có thể làm mất cache giọng của cảnh kế tiếp vì ngữ cảnh; thay hình không tạo lại giọng.', '',
'## 5. Preview, khởi động lại và video cuối', '',
'Bấm **Tạo preview** để xem hình và nhịp cảnh. Preview chưa có giọng đọc; thời điểm phụ đề là ước tính. Sửa một shot rồi tạo lại để kiểm tra preview cũ bị đánh dấu hết hiệu lực và cache cảnh không đổi được dùng lại. Có thể hủy preview. Mở lại Studio và xác nhận các chỉnh sửa đã lưu vẫn còn.', '',
'Chọn thương hiệu/mẫu trong Script để dùng NPD hoặc Vang Nguyễn, 9:16 hoặc 16:9, 30/45/60 giây. Giọng Thùy Dung đã nghiệm thu được giữ cố định. Duyệt nội dung/media/cách dựng hiện hành, sau đó chủ động bấm **Tạo giọng đọc & video**. Không đặt thời lượng ngắn hơn lời đọc thực tế: sửa lời hoặc tăng thời lượng nếu renderer báo không vừa.', '',
'Xem/nghe bản render đầy đủ, đánh giá giọng, phụ đề, hình và nhịp dựng, rồi ghi quyết định duyệt video. Trong **Video hoàn chỉnh**, mở **Nguồn gốc và phiên bản** để truy về nghiên cứu, ý tưởng, brief, kịch bản, storyboard, timeline và render.', '',
'## 6. Ghi nghiệm thu', '',
'Sau khi thao tác, trả lời tên người thực hiện, 10 ca/ý tưởng đã chọn, ít nhất 5 dự án đưa vào sản xuất, shot của từng thao tác, và kết quả xem/nghe từng video cuối. Các quyết định trong Studio sẽ được đối chiếu với phiên bản và tệp thực tế. Chỉ nói “duyệt” trước khi làm chiến dịch không đủ để ghi gate Phase 10Y đã đạt.', '',
'Các bản sao dưới đây chỉ để luyện giao diện trước; không thay thế chiến dịch mới ở các bước 1–5:', '',
'| Ca | Bản sao luyện thao tác |', '|---|---|']
for case in receipt['editing_practice_projects']:
    lines.append(f"| {case['case']:02d} | [Mở bản sao {case['case']:02d}]({case['url']}) |")
lines+=['', 'Trạng thái hiện tại: **HUMAN_CAMPAIGN_ACCEPTANCE = PENDING**. Không có đăng bài hay lịch đăng tự động.', '']
(out/'PHASE10_UAT_GUIDE.md').write_text('\n'.join(lines),encoding='utf-8')
print('UAT guide created from 10 actual research sets and 5 practice copies')
