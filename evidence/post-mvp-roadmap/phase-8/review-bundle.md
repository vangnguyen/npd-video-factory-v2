# Bộ duyệt nội dung — 10 video phát hành nội bộ

**Trạng thái: chờ người dùng duyệt nội dung. Chưa tạo giọng đọc hoặc video mới cho bộ này. INTERNAL_PRODUCTION_READY = NO.**

Mở [Studio](http://127.0.0.1:8026/) và chọn từng dự án `Release 01` đến `Release 10`. Đọc lời, xem nguồn từng cảnh, chữ và cách dựng; sửa/lưu nếu cần. Điền tên và xác nhận ở “Duyệt nội dung này”. Sau khi dựng, từng tệp MP4 cần được xem/nghe rồi duyệt ở “Duyệt video cuối”.

Các nguồn dùng quyền đã xác nhận trong MVP/dự án gốc. Ảnh và video đều có nhãn minh họa; khung hình trích và clip tắt tiếng có xuất xứ lưu riêng. Hồ sơ NPD/Vang Nguyễn là cấu hình tham chiếu, chưa có logo chính thức. Media cũ còn thiếu bản sao byte tải lên đầu tiên; bằng chứng hiện có được giữ rõ, không bổ sung giả.

**Điểm cần xem:** bản 04 do trợ lý biên tập tại máy sau lỗi `CONTENT_AMBIGUOUS_RESPONSE`, không phải kết quả provider và không gửi lại yêu cầu lỗi. Bản 07 là transcript thật chưa xác minh: “cái kênh” có thể cần sửa thành “cái tên” sau khi nghe nguồn; transcript gốc giữ nguyên. Các mốc 30 giây giữ tốc độ giọng, nên có thể cần rút lời hoặc chọn mẫu dài hơn nếu thời lượng đo vượt giới hạn. Các bản nháp về cách kiểm tra nội dung là ứng viên cho kiểm tra vận hành; bạn cần xác nhận chúng phù hợp mục đích nghiệm thu nội bộ.

| Bản | Đầu vào | Hồ sơ / mẫu | Trạng thái |
| --- | --- | --- | --- |
| 01 | prompt | Ngọc Phương Đông / Giới thiệu bất động sản · 30 giây | Chờ duyệt nội dung |
| 02 | idea | Vang Nguyễn personal brand / Thương hiệu cá nhân · 30 giây | Chờ duyệt nội dung |
| 03 | script | Ngọc Phương Đông / Giới thiệu bất động sản · 30 giây | Chờ duyệt nội dung |
| 04 | image | Ngọc Phương Đông / Giới thiệu bất động sản · 30 giây | Chờ duyệt nội dung |
| 05 | multiple_images | Ngọc Phương Đông / Giới thiệu bất động sản · 30 giây | Chờ duyệt nội dung |
| 06 | silent_video | Vang Nguyễn personal brand / Tin tức / cập nhật · 30 giây | Chờ duyệt nội dung |
| 07 | speech_video | Ngọc Phương Đông / Giới thiệu bất động sản · 30 giây | Chờ duyệt nội dung |
| 08 | mixed_media | Ngọc Phương Đông / Giới thiệu bất động sản · 30 giây | Chờ duyệt nội dung |
| 09 | document | Vang Nguyễn personal brand / Thương hiệu cá nhân · 30 giây | Chờ duyệt nội dung |
| 10 | multiple_videos | Vang Nguyễn personal brand / Thương hiệu cá nhân · 30 giây | Chờ duyệt nội dung |

## Release 01 · Prompt — đọc đúng ghi chú minh họa

Dự án `3e9cc995db46486aa6ffed0e2cfca4a0` · phiên bản **5** · dấu nội dung `f2c4a47760d63a2619a577c8c63e3d4d8e0b66e096046f7a85448f28c2278718`.

Nguồn lời: actual OpenAI response.

Khi xem video giới thiệu, hãy để ý ghi chú “Phối cảnh minh họa”. Dòng chữ này cho biết hình ảnh phối cảnh có tính chất minh họa; không nên xem hình ảnh đó như xác nhận về hiện trạng thực tế. Hãy đọc ghi chú ngay trong khung hình, rồi đối chiếu với thông tin chính thức nếu cần tìm hiểu thêm. Trong video này, chúng ta chỉ hướng dẫn cách nhận biết ghi chú, không mô tả nội dung bức ảnh. Xem hết phần chú thích và tham khảo kênh thông tin chính thức của dự án để kiểm tra thêm. Đây là bản nháp để con người rà soát trước khi sử dụng.

Nguồn/cảnh để kiểm tra:

- Cảnh 1: **Tìm ghi chú trong video** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.
- Cảnh 2: **Phối cảnh là minh họa** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.
- Cảnh 3: **Đối chiếu thông tin chính thức** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.

Ghi chú cần xác minh:

- Cần hồ sơ đã chọn hoặc tài liệu giọng đọc để xác minh giọng Thùy Dung và CTA tham chiếu; không được cung cấp trong thông tin nhận được.

## Release 02 · Ý tưởng — giữ bản nháp rõ ràng

Dự án `4b8e9972cb9343ee9b40f52a6f8062f3` · phiên bản **5** · dấu nội dung `3386dea862fc3518e1ad384df0331a0846f2eb2fd7fee601953ec9494fe1a68c`.

Nguồn lời: actual OpenAI response.

Một bản nháp nội dung và một video đã được con người kiểm tra không giống nhau. Bản nháp là điểm bắt đầu: lời dẫn, hình ảnh và chữ trên màn hình vẫn cần được xem xét. Trước khi xem là video đã kiểm tra, hãy xác nhận người phụ trách đã rà soát nội dung và cách trình bày. Ảnh được cung cấp chỉ có thông tin kỹ thuật; không thể xác định nội dung từ tên tệp hay kích thước. Vì vậy, hãy kiểm tra ảnh và mọi dữ kiện trước khi sử dụng. Đây là bản nháp để con người xem lại.

Nguồn/cảnh để kiểm tra:

- Cảnh 1: **Bản nháp là điểm bắt đầu** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.
- Cảnh 2: **Cần được xem xét** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.
- Cảnh 3: **Kiểm tra trước khi dùng** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.

Ghi chú cần xác minh:

- Không có transcript hoặc nguồn xác nhận quy trình rà soát cụ thể; cần người phụ trách xác nhận trước khi dùng cụm “đã được con người kiểm tra”.
- Cần kiểm tra trực tiếp nội dung ảnh trước khi sử dụng; thông tin được cung cấp chỉ gồm loại tệp và kích thước.

## Release 03 · Kịch bản có sẵn — đối chiếu bản MVP

Dự án `944bbf21dfa646268b4565c32cd9c877` · phiên bản **5** · dấu nội dung `1077a6b5e8c892614bddc05c515c6135751c0a6528e92cc2057078577ebaa7b7`.

Nguồn lời: existing_user_script.

Với khách hàng quan tâm đến bất động sản cao cấp, Vinhomes Green Paradise Cần Giờ là cái tên đáng để tìm hiểu. Trước khi đưa ra quyết định, hãy xem xét kỹ hồ sơ pháp lý, thông tin quy hoạch, sản phẩm, giá bán và tiến độ từ các tài liệu chính thức. Đối chiếu nguồn tin, đặt câu hỏi với đơn vị phụ trách và cân nhắc mức độ phù hợp với nhu cầu của bạn. Đây là nội dung giới thiệu sơ bộ; hãy kiểm chứng thông tin trước khi giao dịch.

Nguồn/cảnh để kiểm tra:

- Cảnh 1: **Đoạn 01** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.
- Cảnh 2: **Đoạn 02** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.
- Cảnh 3: **Đoạn 03** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.
- Cảnh 4: **Đoạn 04** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.

Ghi chú cần xác minh:

- Nội dung kịch bản do người dùng cung cấp cần được kiểm chứng trước khi duyệt.

## Release 04 · Ảnh — trình bày nguồn minh họa

Dự án `c64fde86cc4a41689f951a0b6fde123d` · phiên bản **5** · dấu nội dung `2db03086893c3e67514887ebce998364c041b80dd09b1fef62718cd7f899d3c0`.

Nguồn lời: explicit local editorial draft after provider failure, not provider output.

Ảnh minh họa giúp truyền tải ý tưởng, nhưng từng thông tin đi kèm vẫn cần nguồn để kiểm tra. Với mỗi bức ảnh, hãy xem chú thích, thời điểm cung cấp và ghi chú về quyền sử dụng; nếu chưa rõ, giữ câu hỏi đó trong bản nháp. Trước khi duyệt video, đối chiếu lời đọc và chữ với nguồn đã có, đồng thời giữ nhãn minh họa trên khung hình. Mời bạn xem kỹ các ghi chú và gửi lại điểm cần làm rõ.

Nguồn/cảnh để kiểm tra:

- Cảnh 1: **Ảnh minh họa và nguồn** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.
- Cảnh 2: **Xem chú thích ảnh** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.
- Cảnh 3: **Kiểm tra trước khi duyệt** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.
- Cảnh 4: **Gửi điểm cần làm rõ** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.

Ghi chú cần xác minh:

- Bản nháp này do trợ lý biên tập tại máy sau khi provider trả CONTENT_AMBIGUOUS_RESPONSE. Không phải kết quả provider. Yêu cầu lỗi được giữ nguyên, không gửi lại. Cần con người kiểm tra nội dung và nguồn ảnh trước khi duyệt.

## Release 05 · Nhiều ảnh — đối chiếu nguồn

Dự án `f803556b506b4d27ad1c1e964524e253` · phiên bản **6** · dấu nội dung `b94d7bf5ad2b8ee07f5140c864a05cbb9583ff8adf2ef33f8377881859b0cac5`.

Nguồn lời: actual OpenAI response.

Trong bản đề xuất này, chúng ta có hai nguồn ảnh minh họa: ảnh của bản MVP và một khung hình trích từ video bạn đã tải lên. Để giữ rõ xuất xứ, hãy ghi riêng cho mỗi ảnh tên nguồn, cách sử dụng và ghi chú do người cung cấp xác nhận; chưa rõ thì đánh dấu cần kiểm tra. Sau đó, đối chiếu từng ảnh với nguồn tương ứng, thay vì suy ra nội dung từ tên tệp hay thông số kỹ thuật. Đây là bản nháp để con người rà soát trước khi sử dụng. Giọng đọc và CTA cần theo hồ sơ đã chọn.

Nguồn/cảnh để kiểm tra:

- Cảnh 1: **Hai nguồn ảnh minh họa** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.
- Cảnh 2: **Ghi chú xuất xứ từng ảnh** — source-frame.jpg; zoom_in, contain; nguồn `c4a2b976fd7d1c4382fad1c26f067203e6b50c46534412cfb4b3487638c35a82`.
- Cảnh 3: **Đối chiếu, rồi rà soát** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.

Ghi chú cần xác minh:

- Cần hồ sơ đã chọn để xác nhận giọng Thùy Dung và CTA tham chiếu; hiện chưa được cung cấp trong dữ liệu nhận được.
- Cần người dùng xác nhận nội dung ghi chú xuất xứ, quyền sử dụng và nguồn gốc của từng ảnh trước khi sử dụng.

## Release 06 · Video không lời — kiểm tra cảnh và chữ

Dự án `84ccb60fc14e40139db3d15cfd95c5a8` · phiên bản **5** · dấu nội dung `c13395db9cf540bee1118ac5842a037890f62a77de105a51300d05f74700e67a`.

Nguồn lời: actual OpenAI response.

Trước khi thêm lời đọc mới, hãy kiểm tra thứ tự ba cảnh từ đầu đến cuối. Đối chiếu từng cảnh với bản dựng, rồi xác nhận chữ hiển thị đúng cảnh, đúng thứ tự và dễ đọc. Đọc thử toàn bộ lời thoại cùng chữ trên màn hình để xem nhịp có phù hợp video 30 giây không. Nếu cần đổi thứ tự hoặc sửa chữ, hãy cập nhật bản dựng rồi kiểm tra lại. Giữ giọng Thùy Dung theo hồ sơ đã chọn và thêm CTA tham chiếu từ hồ sơ đó sau khi đối chiếu. Đây là bản nháp để con người kiểm tra; chưa tự duyệt hay xuất bản.

Nguồn/cảnh để kiểm tra:

- Cảnh 1: **Kiểm tra thứ tự cảnh** — source-silent.mp4; none, contain; nguồn `f73c97089cae8faf62d27852ebd72e0f44d0d4a71612addaf4abfdf5c55be8a8`.
- Cảnh 2: **Đối chiếu chữ từng cảnh** — source-silent.mp4; none, contain; nguồn `f73c97089cae8faf62d27852ebd72e0f44d0d4a71612addaf4abfdf5c55be8a8`.
- Cảnh 3: **Rà soát trước khi duyệt** — source-silent.mp4; none, contain; nguồn `f73c97089cae8faf62d27852ebd72e0f44d0d4a71612addaf4abfdf5c55be8a8`.

Ghi chú cần xác minh:

- Chưa có thông tin hồ sơ cụ thể xác nhận giọng Thùy Dung và CTA tham chiếu; cần đối chiếu hồ sơ đã chọn trước khi thu lời đọc.
- Media chỉ cung cấp thông số kỹ thuật; cần người dùng cung cấp hoặc xác nhận hình ảnh ba cảnh và chữ dự kiến để kiểm tra chính xác thứ tự, nội dung hiển thị.

## Release 07 · Video có lời — duyệt transcript thật

Dự án `744b92230b034f8481acef9af7ec9fef` · phiên bản **6** · dấu nội dung `f29e2868ba8ff76e88e112113137bedb6697751b879603e5cb661531bd7293d4`.

Nguồn lời: immutable_provider_transcript_for_human_review.

Với khách hàng quan tâm đến bất động sản cao cấp, Vinhomes Green Paradise Cần Giờ là cái kênh đáng để tìm hiểu. Trước khi đưa ra quyết định, hãy xem xét kỹ hồ sơ pháp lý, thông tin quy hoạch, sản phẩm, giá bán và tiến độ từ các tài liệu chính thức. Đối chiếu nguồn tin, đặt câu hỏi với đơn vị phụ trách và cân nhắc mức độ phù hợp với nhu cầu của bạn. Đây là nội dung giới thiệu sơ bộ, hãy kiểm chứng thông tin trước khi giao dịch.

Nguồn/cảnh để kiểm tra:

- Cảnh 1: **Đoạn 01** — MVP đã duyệt · lời nói thật 25 giây.mp4; none, contain; nguồn `c0bbcf029554cfd2e7c29e05d595379abb6d894babc78154a16537f7fba1a47a`.
- Cảnh 2: **Đoạn 02** — MVP đã duyệt · lời nói thật 25 giây.mp4; none, contain; nguồn `c0bbcf029554cfd2e7c29e05d595379abb6d894babc78154a16537f7fba1a47a`.
- Cảnh 3: **Đoạn 03** — MVP đã duyệt · lời nói thật 25 giây.mp4; none, contain; nguồn `c0bbcf029554cfd2e7c29e05d595379abb6d894babc78154a16537f7fba1a47a`.
- Cảnh 4: **Đoạn 04** — MVP đã duyệt · lời nói thật 25 giây.mp4; none, contain; nguồn `c0bbcf029554cfd2e7c29e05d595379abb6d894babc78154a16537f7fba1a47a`.

Ghi chú cần xác minh:

- Lời nói do AssemblyAI nhận diện có thể sai. Kiểm tra video nguồn, sửa bản nháp nếu cần và xác minh dữ kiện trước khi duyệt; transcript gốc được giữ nguyên.

## Release 08 · Nguồn hỗn hợp — giữ xuất xứ rõ ràng

Dự án `8bd0c60963024b9b94a826f2c790bb77` · phiên bản **7** · dấu nội dung `96c8f7955719e5c5ca0852ae077eb3c3346208d1674ec1aa87ff5a9b60ff69f6`.

Nguồn lời: actual OpenAI response.

Mỗi ảnh và video cần được giữ cùng với ghi chú về nguồn gốc, để người duyệt có thể đối chiếu. Không suy đoán nội dung từ tên tệp hay thông số kỹ thuật; chỉ mô tả điều đã được nhận diện. Nếu hình là phối cảnh, cần ghi rõ là hình minh họa. Trước khi duyệt, hãy kiểm tra lời đọc, chữ trên từng cảnh, nhãn minh họa và quyền sử dụng. Nếu đổi nguồn hoặc sửa nội dung, cần duyệt lại. Video cuối cần được xem và nghe trước khi nghiệm thu. Đây là bản nháp để con người kiểm tra.

Nguồn/cảnh để kiểm tra:

- Cảnh 1: **Giữ rõ nguồn gốc** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.
- Cảnh 2: **Không suy đoán hình** — source-silent.mp4; none, contain; nguồn `f73c97089cae8faf62d27852ebd72e0f44d0d4a71612addaf4abfdf5c55be8a8`.
- Cảnh 3: **Kiểm tra trước nghiệm thu** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.

Ghi chú cần xác minh:

- Xác nhận nguồn gốc và quyền sử dụng của từng ảnh, video; đối chiếu với ghi chú nguồn.
- Xác nhận nội dung hình ảnh trước khi mô tả hoặc gắn nhãn phối cảnh/hình minh họa.
- Cung cấp cấu hình giọng đọc Thùy Dung và CTA tham chiếu từ hồ sơ thương hiệu đã chọn; hồ sơ hiện có chỉ được mô tả là cấu hình tham chiếu và chưa có logo chính thức.

## Release 09 · Tài liệu — lời đọc theo ghi chú nguồn

Dự án `2bf4aabbd1da43c1997509e918afd89c` · phiên bản **6** · dấu nội dung `dbecb5cbd55ffafd7126abf4789be8c48463233f012b9dc488802fea34024dd3`.

Nguồn lời: actual OpenAI response.

Trước khi duyệt, đội nội dung rà soát bản nháp một cách cẩn trọng. Chúng tôi giữ rõ xuất xứ từng nguồn, rồi kiểm tra chữ, lời đọc, nhãn minh họa và quyền sử dụng. Tư liệu hình ảnh trong bản dựng chỉ dùng để minh họa; không suy đoán nội dung ngoài thông tin đã nhận diện. Nếu nguồn thay đổi hoặc nội dung được chỉnh sửa, bản nháp cần được duyệt lại. Trước khi nghiệm thu, video cuối phải được xem và nghe. Đây là bản đề xuất để con người kiểm tra; cấu hình thương hiệu hiện chỉ mang tính tham chiếu.

Nguồn/cảnh để kiểm tra:

- Cảnh 1: **Rà soát bản nháp** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.
- Cảnh 2: **Kiểm tra nguồn và nội dung** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.
- Cảnh 3: **Xem, nghe, rồi kiểm tra** — MVP — ảnh minh họa.jpg; zoom_in, contain; nguồn `61ebeb0c92702a1bdb504cf22088bde62c4cbf87f125614b9cb32d8a79c0f7ee`.

Ghi chú cần xác minh:

- Giọng Thùy Dung và CTA tham chiếu của hồ sơ đã chọn: cần hồ sơ thương hiệu hoặc mẫu giọng/CTA được xác nhận; tài liệu hiện nêu cấu hình chỉ là tham chiếu, chưa có logo chính thức.

## Release 10 · Nhiều video — kiểm tra từng nguồn

Dự án `63e87c6e073d4ae9acdddbc05c8d2030` · phiên bản **7** · dấu nội dung `9e0379d38f8dac9eca32668f1a7bef686d7d17f13a6789d8fed19cbfd4ff06ff`.

Nguồn lời: actual OpenAI response.

Trước khi duyệt bản nháp, hãy kiểm tra ghi chú nguồn: đối chiếu từng dữ kiện với tài liệu đã được xác nhận, và đánh dấu điều gì còn cần kiểm chứng. Tiếp theo, rà thứ tự ba cảnh để xem chúng có khớp với phần lời đọc mới hay không. Hai video minh họa được xác nhận có quyền sử dụng, nhưng không suy đoán nội dung hình ảnh. Lời nói từ video nguồn không dùng làm lời đọc. Hãy xem lại các ghi chú và thứ tự cảnh; đây là bản nháp cần con người kiểm tra trước khi duyệt.

Nguồn/cảnh để kiểm tra:

- Cảnh 1: **Kiểm tra ghi chú nguồn** — MVP đã duyệt · lời nói thật 25 giây.mp4; none, contain; nguồn `c0bbcf029554cfd2e7c29e05d595379abb6d894babc78154a16537f7fba1a47a`.
- Cảnh 2: **Rà thứ tự cảnh** — MVP đã duyệt · lời nói thật 25 giây.mp4; none, contain; nguồn `c0bbcf029554cfd2e7c29e05d595379abb6d894babc78154a16537f7fba1a47a`.
- Cảnh 3: **Bản nháp chờ kiểm tra** — MVP đã duyệt · lời nói thật 25 giây.mp4; none, contain; nguồn `c0bbcf029554cfd2e7c29e05d595379abb6d894babc78154a16537f7fba1a47a`.

Ghi chú cần xác minh:

- Ghi chú nguồn cho từng dữ kiện cần được đối chiếu với tài liệu gốc đã xác minh; prompt không nêu các dữ kiện hoặc nguồn cụ thể.
- Giọng Thùy Dung và CTA tham chiếu cần được kiểm tra theo hồ sơ đã chọn; hồ sơ không được cung cấp trong nội dung hiện có.
