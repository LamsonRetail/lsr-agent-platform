# Bài học vận hành — để không lặp lại

## Dữ liệu

- **Số trong kế hoạch có thể đã cũ.** Base target trong kế hoạch Ploy ghi 9,3M/8,0M THB — đó là số **tháng 7**; tháng 8 thật là 13M/2,4M THB. Luôn kiểm kỳ của số trước khi trả lời.
- **Một mốc thường có nhiều phiên bản ngày.** Travel bag có 4 ngày launching giữa 4 nguồn; T10 có 3. Nêu đủ các phiên bản, không tự chọn — trừ khi chủ sở hữu đã chốt (`official: true`).
- **Ngày trong sheet Lark có thể bị render m/d/y.** Cột "Launching Day" từng đọc thành 9/7 thay vì 07/09. Dùng dòng mốc dd/mm/yyyy làm nguồn chuẩn.
- **Không tìm thấy ≠ không tồn tại.** Ngày Travel bag 05/09 từng bị kết luận "không tồn tại" vì chỉ tra wiki tiến độ; nó nằm trong sheet nhúng của CM Weekly Report.
- **Số thực hiện là TỔNG kênh TMĐT**, không tách brand. Số TRƯỚC 19/08 còn gộp MATE MADE TH (đã đóng) — nhớ điểm cắt khi so chuỗi thời gian.
- **Phạm vi có thể thay đổi giữa đường.** MM Thái Lan đóng 19/08 → mọi config/code/memory phải dọn theo, nếu không Ploy trả lời về một mảng không còn tồn tại.

## Nguồn thông tin

- **Chọn nguồn theo chủ đề Ploy phải trả lời, không theo nhóm nào đông tin.** Chỉ quét 8 nhóm "ưu tiên 1" đã làm Ploy trả lời sai "chưa có cập nhật logistics" — thông tin nằm ở nhóm kho vận chuyên môn.
- **Lark tự sinh biên bản họp** dạng `AI notes: <tên họp> on <ngày>` và `Meeting transcript: <tên họp> <ngày>` trong Drive — nguồn biên bản có sẵn, không cần chờ agent gỡ băng.
- Dữ liệu mảng khác do agent khác giữ: doanh số → Jenny · tồn kho MM → LYLY · NCC → Sourcing · BigQuery → Data Support. Hỏi qua A2A, cần grant.

## Kỹ thuật / vận hành

- `pkill -f "python3 -u consumer.py"` KHÔNG khớp (tên tiến trình thật là `.../Python -u consumer.py`) → từng có 6 consumer chạy song song, bản cũ giành job và trả lời sai. Dùng `pkill -f consumer.py`; đã thêm khoá file chống chạy trùng.
- Bot chạy trên máy cá nhân = gập máy là tắt; job trong queue chờ tới khi bật lại (từng trễ 1,5 tiếng). Đích đến: container trên VM.
- Tìm chuỗi con trong tiếng Việt rất dễ sai: `"hi "` khớp `"khi nào"` → mọi câu hỏi "… khi nào" bị hiểu là lời chào. Khớp theo TỪ, không theo chuỗi con.
- RAG trả "mục gần nhất" không có nghĩa là "liên quan": câu hỏi văn hoá từng bị gán mục DEMO của platform. Phải kiểm độ liên quan trước khi dùng.
