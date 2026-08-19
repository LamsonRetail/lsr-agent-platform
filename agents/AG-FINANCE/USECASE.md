# Use case — Trợ lý Tài chính - Kế toán (AG-FINANCE)

## Bài toán

Squad Finance-Accounting đang có ba chỗ mất thời gian:

1. **Dữ liệu rời rạc.** Số liệu nằm ở ba nơi không nói chuyện với nhau: Google Sheet (mỗi
   người một file), MISA AMIS (sổ kế toán), Lark Base (một số bảng theo dõi thủ công).
   Muốn trả lời một câu hỏi đơn giản như "khách A còn nợ bao nhiêu, quá hạn mấy ngày"
   phải mở 2-3 nguồn rồi đối chiếu tay.
2. **Hỏi đi hỏi lại.** Người ngoài squad (sales, vận hành, ban giám đốc) hỏi cùng một
   nhóm câu hỏi số liệu qua chat. Kế toán trở thành người tra cứu thủ công.
3. **Họp không có biên bản.** Họp xong quyết định nằm trong đầu người dự. Không ai chốt
   ai làm gì, hạn nào. Tuần sau họp lại từ đầu.

## Người dùng

| Nhóm | Kênh | Được làm gì |
|---|---|---|
| Thành viên squad Finance-Accounting | Nhóm Lark của squad | Hỏi mọi số liệu, chạy đồng bộ, chốt biên bản họp |
| Ngoài squad | Chat 1-1 với bot | Bị từ chối trả lời số liệu, được chỉ sang đúng người |

Quyền dựa trên **whitelist email/open_id của squad** (`shared/auth.py`). Đây là dữ liệu
lãi lỗ và công nợ — mặc định là từ chối, không phải mặc định là cho.

## Luồng chính 1 — Tổng hợp dữ liệu về một nơi

1. Theo lịch (hoặc khi có người gọi), agent đọc từ các nguồn: Google Sheet, MISA AMIS API,
   Lark Base.
2. Chuẩn hoá về schema chung (`data_hub/schema.py`): công nợ, doanh thu, chi phí, dòng tiền.
3. Ghi vào **Lark Base "FIN-HUB"** — đây là mặt tiền. Người trong squad mở Lark ra là xem
   được như bảng tính, không cần biết SQL, không cần đăng nhập hệ thống nào khác.
4. Ghi lại một dòng nhật ký đồng bộ: nguồn nào, bao nhiêu dòng, lệch gì, lúc nào.

## Luồng chính 2 — Hỏi đáp số liệu

1. Người trong squad hỏi trong nhóm Lark: *"Công nợ quá hạn trên 30 ngày đang là bao nhiêu?"*
2. Agent kiểm tra người hỏi có trong whitelist squad không. Không có → từ chối.
3. Agent đọc Lark Base FIN-HUB, tính toán, trả lời **kèm thời điểm dữ liệu được đồng bộ lần
   cuối** và **nguồn gốc số liệu**.
4. Nếu dữ liệu cũ hơn ngưỡng cho phép, agent nói rõ là số cũ thay vì trả lời như số mới.

## Luồng chính 3 — Biên bản họp

1. Bot có trong nhóm Lark của cuộc họp.
2. Có người đăng recording (hoặc dán transcript thô).
3. Agent dựng transcript → soạn biên bản: nội dung chính, **quyết định**, **đầu việc kèm
   người chịu trách nhiệm và hạn**.
4. Agent gửi bản nháp vào nhóm, xin người chủ trì xác nhận.
5. Người chủ trì trả lời `chốt` → agent tạo task Lark và lưu biên bản để tra cứu lại.
   Trước khi chốt thì không tạo task nào.

## Ngoài phạm vi (không làm)

- **Không ghi vào MISA.** Agent chỉ đọc. Mọi bút toán do kế toán tự làm trên MISA.
- **Không lập báo cáo tài chính pháp định** (BCTC, thuế). Đây là trợ lý tra cứu và tổng hợp
  nội bộ, không phải công cụ phát hành báo cáo ra ngoài.
- **Không tự ra quyết định chi tiền**, không phê duyệt, không nhắc nợ tự động cho khách hàng
  bên ngoài.
- **Không đoán số.** Thiếu dữ liệu thì nói thiếu. Một con số bịa trong ngữ cảnh tài chính
  tệ hơn hẳn việc trả lời "tôi không biết".
- **Không trả lời số liệu cho người ngoài squad.**

## Dữ liệu cần truy cập

| Nguồn | Cách đọc | Quyền cần xin | Trạng thái |
|---|---|---|---|
| Google Sheet | Service account, read-only | Share sheet cho service account | ⬜ chưa xin |
| MISA AMIS | REST API (cloud) | API key / OAuth client từ quản trị MISA | ⬜ chưa xin |
| Lark Base FIN-HUB | Lark Open API `bitable` | Scope `bitable:app` cho bot | ⬜ chưa xin |
| Tri thức quy định nội bộ | `brain_items` của platform (`/v1/self/context`) | Có sẵn theo agent token | ✅ |
| Transcript họp | Whisper server qua `LSR_TRANSCRIBE_URL` | Server phải bật | ⬜ chưa xác nhận |

## Rủi ro & giới hạn

- **Rò rỉ số liệu nhạy cảm.** Giảm thiểu bằng whitelist squad, mặc định từ chối, và ghi
  audit mọi câu hỏi có trả về số.
- **Số liệu lệch giữa các nguồn.** MISA và Sheet có thể không khớp. Agent **không tự chọn
  bên nào đúng** — báo lệch cho người xử lý.
- **Dữ liệu cũ bị hiểu là mới.** Mọi câu trả lời phải kèm mốc thời gian đồng bộ.
- **Không có quyền ghi MISA** nên FIN-HUB luôn là bản sao trễ, không phải nguồn sự thật
  cho mục đích kế toán.
- **Ghi âm cuộc họp** cần người dự đồng ý. Không bật ghi âm ngầm.
- Tra cứu quy định nội bộ dựa trên full-text search của platform (chưa có vector
  embedding) → câu hỏi diễn đạt khác từ khoá trong tài liệu có thể không tìm ra.
