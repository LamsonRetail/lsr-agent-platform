# Use case — Trợ lý Kế hoạch Hàng hoá (AG-INVENTORY-DAYS)

> ⚠️ BẮT BUỘC điền trước khi code (gate của platform sẽ chặn code nếu thiếu file này).

Tên hiển thị trên Lark: **PLANNING' ASSISTANT** · App: `cli_aaf6d3a61078ded4`

## Bài toán

Phòng Kế hoạch Hàng hoá (KHHH) ngồi giữa 6 phòng ban khác — Kinh doanh, Thu mua,
Sản phẩm, Kho vận, Bán lẻ, Kế toán — và mỗi ngày trả lời lặp đi lặp lại hai loại
câu hỏi:

1. **Câu hỏi quy trình.** "Chốt PR ngày nào?", "Ghép combo báo trước mấy ngày?",
   "Phiếu chuyển kho cần điền gì?". Câu trả lời nằm rải rác trong Wiki, trong đầu
   vài người, hoặc trong lịch sử chat đã trôi. Người mới mất nhiều tuần mới nắm,
   người cũ mất thời gian trả lời lại.
2. **Câu hỏi tồn kho.** "Mã nào sắp hết hàng?", "Mã Aura kem còn tồn bao nhiêu?".
   Số nằm trong Base KHHH, nhưng người hỏi thường không có quyền hoặc không biết
   mở bảng nào.

Hệ quả thực tế đã ghi nhận: thông tin đứt gãy giữa các thành viên, cùng một sự cố
lặp lại ở dự án sau, và câu hỏi tồn kho phải chờ người trực trả lời thủ công.

## Người dùng

- **Thành viên KHHH** — tra quy trình và ngưỡng ra quyết định ngay trong nhóm chat.
- **Các phòng phối hợp** (Thu mua, Kho, Kinh doanh, Bán lẻ) — hỏi "bên KHHH quy
  định thế nào" mà không phải chờ người trực.
- **Người mới của phòng** — thay cho việc đọc hết sổ tay 32 trang trong tuần đầu.

## Luồng chính (happy path)

**A. Hỏi — đáp quy trình vận hành**

1. Ai đó @mention bot trong nhóm Lark, ví dụ *"ghép combo phải báo trước mấy ngày"*.
2. Bot tra `knowledge/CODE_OF_CONDUCT_KHHH.md` (75 mục) bằng tìm kiếm từ khoá có
   trọng số IDF. Câu hỏi đòi con số ("mấy ngày", "bao nhiêu", "ngưỡng") thì ưu tiên
   mục và dòng **thật sự chứa con số**.
3. Trả lời tối đa 3–4 dòng trích nguyên văn, **luôn kèm số mục** để người đọc tự
   tra lại — và tự nhận ra nếu bot trả lệch.

**B. Hỏi — đáp tồn kho**

1. Ai đó hỏi *"mã nào sắp hết hàng"*, *"top 5 mã tồn cao"*, hoặc gõ hẳn mã SKU.
2. Bot nạp tồn kho từ Lark Base `QL KẾ HOẠCH HÀNG HÓA HAPAS`, bảng
   `BÁO CÁO KẾ HOẠCH HÀNG HOÁ` (cache 15 phút).
3. Trả lời kèm số tồn, tốc độ bán/ngày và số ngày tồn quy đổi.

**C. Báo cáo KHHH định kỳ** (`src/khhh_report.py`)

1. Kéo số từ Base, gộp theo BST.
2. Dựng ảnh báo cáo + phần cảnh báo sinh tự động từ ngưỡng NTK.
3. Gửi text + ảnh vào nhóm được chỉ định.

## Nguyên tắc trả lời

- **Tra ra thì trả lời kèm số và nguồn. Không tra ra thì nói thẳng là chưa biết.**
  Không đoán, không bịa số — sai một con số tồn kho có thể dẫn tới một đơn đặt sai.
- **Được @mention → luôn trả lời**, kể cả để nói "mình chưa tra được".
- **Không được gọi tên → chỉ chen vào khi câu đó đúng là câu hỏi VÀ tra ra được
  đáp án chắc chắn.** Còn lại im lặng. Bot ngồi trong nhóm làm việc thật, nói nhiều
  là gây nhiễu.

## Ngoài phạm vi (không làm)

- **Không tư vấn nên đặt bao nhiêu.** Bot đưa số và ngưỡng; quyết định đặt hàng
  thuộc về người.
- **Không ghi, sửa, xoá bất cứ thứ gì trong Base.** Chỉ đọc.
- **Không phụ trách BLG.** Chỉ số này thuộc Kinh doanh / Thu mua — bot có thể đọc
  hiểu nhưng không trả lời thay chủ sở hữu.
- Không trả lời câu hỏi ngoài phạm vi tài liệu (giá vàng, thời tiết, việc phòng khác).

## Dữ liệu cần truy cập

| Nguồn | Quyền | Dùng để |
|---|---|---|
| Tin nhắn nhóm Lark bot được add vào | `im:message.group_msg` (đọc) · `im:message` (gửi) | Nhận câu hỏi, trả lời |
| Base `QL KẾ HOẠCH HÀNG HÓA HAPAS` | `bitable:app:readonly` | Tồn kho, TĐB, hàng đang trên đường |
| `im:resource` | ghi | Upload ảnh báo cáo |
| `knowledge/CODE_OF_CONDUCT_KHHH.md` | build vào image | Kiến thức nền quy trình |

Không cần BigQuery ở giai đoạn này.

## Rủi ro & giới hạn

- **`DRY_RUN=true` mặc định** — chỉ ghi log, không gửi tin thật. Chỉ đổi sang
  `false` sau khi xem log thấy trả lời đúng.
- **Bot đọc tin nhắn của mọi nhóm được add vào** (`CHAT_IDS` để trống). Theo README
  của repo, việc này **phải được thông báo minh bạch** cho thành viên nhóm trước
  khi bật trả lời thật.
- **Tra cứu bằng từ khoá, không phải semantic search.** Câu hỏi mà mọi từ đều tình
  cờ có trong tài liệu vẫn có thể ra mục không liên quan. Vì vậy câu trả lời **luôn
  kèm tên mục + số mục** để người đọc nhận ra ngay khi bot trả lệch. Muốn xử lý
  triệt để phải chuyển sang embedding.
- **Số tồn kho trễ tối đa 15 phút** (chu kỳ cache). Base lỗi thì bot dùng lại số
  cũ thay vì báo "chưa có dữ liệu" — thà số hơi cũ còn hơn không trả lời được,
  nhưng không hợp cho quyết định cần số theo thời gian thực.
- **Đang poll mỗi 3 giây, chưa dùng event.** Khi bật được `im.message.receive_v1`
  thì chuyển sang `src/bot.py` (long connection) — nhanh và nhẹ hơn.
- **Chưa có cảnh báo khi bot chết.** `restart: unless-stopped` xử lý được crash,
  nhưng nếu app_secret bị đổi thì crash-loop im lặng.
