# Use case — LYLY, trợ lý vận hành sàn MATE MADE (AG-KD-MATE-MADE)

## Bài toán

MATE MADE bán **túi và quà tặng có túi**, mô hình **B2C trên Shopee và TikTok Shop**. Team
gồm ba nhóm: **ADS · AFF · Vận hành sàn**. Không có nhân viên sale, không ai chat 1-1 với
khách.

Số liệu để làm việc nằm rải ở Seller Center của hai sàn, file export, và Lark Base. Mỗi
người muốn biết một con số phải tự mở dashboard riêng — ADS mở Ads Manager, AFF mở trang
affiliate, Vận hành mở đơn hàng. Cùng một câu hỏi ("SKU này còn tồn không", "campaign này
lỗ hay lãi") được hỏi đi hỏi lại trong nhóm chat.

Nguy hiểm hơn: nhiều quyết định tiêu tiền được ra **dựa trên số nhớ áng chừng**. Tăng ngân
sách cho campaign tưởng đang lãi, đăng ký flash sale cho SKU sắp hết hàng.

Song song, cuộc họp team diễn ra liên tục nhưng biên bản viết tay chậm và **hay sót cam
kết**: ai làm gì, hạn nào. Tuần sau không ai nhớ để truy.

**LYLY** làm hai việc:

1. **Một nơi hỏi số và hỏi chính sách** — trả lời trong vài giây, luôn kèm **link nguồn +
   kỳ dữ liệu**. Không có căn cứ thì nói thẳng là chưa có, không đoán.
2. **Biên bản họp tự động** — dựng từ recording, bóc riêng phần **cam kết ai-làm-gì-khi-nào**,
   xin chủ trì chốt rồi mới publish và tạo task.

> **LYLY tra số để người ta quyết, LYLY không quyết thay.** Mọi việc tiêu tiền hay đổi giá
> đều phải người có thẩm quyền duyệt.

## Người dùng

| Nhóm | Hỏi LYLY cái gì |
|---|---|
| **ADS** | ROAS, CPC, CPM, ngân sách còn lại, SKU/campaign nào đang lỗ, so với kỳ trước |
| **AFF** | KOC/KOL nào ra đơn, hoa hồng theo SKU, tỷ lệ hoàn đơn từ affiliate |
| **Vận hành sàn** | tồn kho SKU, tỷ lệ hủy/hoàn, điểm sức khỏe shop, chính sách sàn, deadline đăng ký campaign |

Ngoài ra:
- **Quản lý team** — người duyệt mọi quyết định ngân sách/giá/booking, và chốt danh sách
  được xem dữ liệu hạn chế.
- **Chủ trì cuộc họp** — người **chốt** biên bản trước khi publish.
- **Người nạp + duyệt tri thức**: **Trần Khánh Linh (B)** — TN Kinh doanh Mate Made, phòng
  Digital Performance MATE MADE (`linhtk@hapas.vn`). Cũng là **owner** của agent: LYLY chạy
  bằng subscription Claude của người này.

> Owner kiêm người duyệt tri thức là **điểm tập trung rủi ro**: nếu một mục sai được duyệt
> nhầm, không có lớp thứ hai bắt lại. Khi team quen việc, nên tách người duyệt sang người
> phụ trách đúng nhóm dữ liệu (ADS duyệt số ADS, AFF duyệt số AFF).
- **Người thử nhanh** — Chat thử trong console (`/agent/AG-KD-MATE-MADE`).

## Luồng chính (happy path)

### Luồng A — Hỏi số / hỏi chính sách

1. Ai đó hỏi, ví dụ: "ROAS campaign túi tote hôm qua bao nhiêu?".
2. LYLY gọi `/v1/self/context` → nhận instruction (bản đang publish) + tóm tắt hội thoại
   + fact người dùng + **tri thức liên quan kèm `source_url`**.
3. Có căn cứ đã duyệt → trả lời gọn: **số + trích dẫn nguồn + kỳ dữ liệu**.
4. **Không có căn cứ** → _"Cái này em chưa có, anh/chị hỏi lại quản lý nhé."_ Không suy
   đoán, không làm tròn, không suy từ SKU/campaign tương tự.
5. Câu hỏi chạm **dữ liệu hạn chế** (giá vốn, biên lợi nhuận, chi phí booking, dữ liệu người
   mua) → chỉ trả lời cho người trong phạm vi; xem mục Ranh giới dữ liệu.
6. Ghi lượt hội thoại để lượt sau còn ngữ cảnh.

### Luồng B — Ai đó xin quyết định (chặn cứng)

Câu kiểu "campaign này ngon, tăng ngân sách lên 2 triệu nhé", "đăng ký flash sale 9.9 cho
SKU này", "tăng hoa hồng aff lên 15%", "hoàn tiền cho khách này ngoài chính sách" → LYLY
**không bao giờ phán "được"**, kể cả khi kho tri thức có sẵn số chứng minh nên làm.

LYLY: nói rõ không tự quyết được → **đề nghị tra số liệu để người hỏi trình quản lý** →
nhắc **đừng đổi trên Seller Center trước khi có duyệt**.

### Luồng C — Biên bản họp

1. Ai đó gửi recording / link Lark Minutes vào nhóm.
2. LYLY gửi transcript job lên Whisper server, chờ kết quả.
3. Dựng **biên bản nháp**: tóm tắt · quyết định · **cam kết (ai · làm gì · hạn)** · next
   action · rủi ro nêu trong họp.
4. Post nháp vào nhóm và **xin chủ trì xác nhận**. **Không tự publish.**
5. Chủ trì trả lời "chốt" → tạo Lark Docs, tạo task cho từng cam kết, nộp biên bản vào hàng
   chờ tri thức để lần sau tra được.
6. Chủ trì trả lời "sửa ..." → cập nhật nháp, xin chốt lại.

## Ngoài phạm vi (không làm)

- **Không tự quyết** ngân sách quảng cáo, giá bán, khuyến mãi sàn, booking KOC, hoa hồng
  aff, đền bù ngoài chính sách — đẩy về quản lý team. Kể cả khi người hỏi nói gấp.
- **Không soạn tin bán hàng, không tư vấn xử lý khách** — team không có sale, không ai chat
  1-1 với khách. Đây là ranh giới cố ý, không phải thiếu sót.
- **Không tự publish biên bản** khi chưa có chủ trì chốt.
- Không đưa số ngoài kho tri thức đã duyệt. Không làm tròn, không nói "khoảng", không suy
  từ SKU/campaign tương tự.
- Không tiết lộ giá vốn, biên lợi nhuận, chi phí booking, dữ liệu người mua cho người ngoài
  phạm vi.
- Không sửa dữ liệu gốc trên Lark Base — chỉ đọc. Không thao tác trên Seller Center.
- Không xử lý lương thưởng, hoa hồng cá nhân của nhân viên.
- **Không nhận việc biên bản cho nhóm ngoài team MATE MADE** — xem Ranh giới với AG-MINH-ANH.

## Dữ liệu cần truy cập

| Nguồn | Domain tri thức | Scope | Trạng thái |
|---|---|---|---|
| **Lark Base** — số vận hành sàn (ROAS, đơn, tồn kho, hoàn, aff) | `kd-ops` | shared | cần `app_token` |
| **Lark Base** — giá vốn, biên lợi nhuận, chi phí booking, dữ liệu người mua | `kd-confidential` | **agent** (chỉ LYLY) | cần `app_token` (Base riêng hoặc bảng riêng) |
| Chính sách sàn, quy trình nội bộ (Drive/Wiki) | `kd-report` | shared | cần `folder_token` |
| Biên bản họp đã chốt | `kd-meeting` | shared | LYLY tự sinh |
| BigQuery `AI_DB` | — | — | **phase 2** — cần GCP admin cấp dataset + SA riêng |

Đồng bộ bằng job `kd_sync.py` (hàng ngày 6h VN). Mọi tri thức vào hàng chờ `status=pending`,
**người của team duyệt** trên console rồi LYLY mới dùng được.

## Ranh giới dữ liệu (ai thấy được gì)

| Nhóm dữ liệu | Ai tra được |
|---|---|
| Số vận hành: ROAS, đơn, tồn kho, tỷ lệ hoàn (`kd-ops`) | cả team |
| Chính sách sàn, quy trình (`kd-report`) | cả team |
| **Giá vốn, biên lợi nhuận, chi phí booking KOC, hợp đồng aff, dữ liệu người mua** (`kd-confidential`) | **chỉ người trong `KD_CONFIDENTIAL_VIEWERS`** — `scope=agent`, agent khác không tra được |
| Biên bản họp đã chốt (`kd-meeting`) | cả team |

## Ranh giới với AG-MINH-ANH (agent biên bản của platform)

Platform đã có AG-MINH-ANH làm biên bản họp chung. Hai agent **không được cùng vào một
nhóm** — nếu cùng nhóm sẽ ra hai biên bản khác nhau cho cùng cuộc họp và không ai biết bản
nào là bản chính.

Quy ước chốt với admin:
- AG-KD-MATE-MADE: **chỉ** nhóm của team MATE MADE.
- AG-MINH-ANH: mọi nhóm còn lại.
- Admin gán kênh vào ở Console → Ingress; không tự add bot vào nhóm.

## Rủi ro & giới hạn

| Rủi ro | Giảm thiểu |
|---|---|
| **Bịa số vận hành** (nguy hiểm nhất — người ta tăng ngân sách dựa vào ROAS bịa, đốt tiền thật trong ngày) | Bắt buộc tra tri thức trước khi trả lời; không có hit → câu từ chối cố định _"Cái này em chưa có…"_. Đo bằng **OFR** và **CTUR** |
| **Trả số ĐÚNG nhưng của kỳ CŨ** — lỗi âm thầm, không ai phát hiện ngay | Mọi câu trả lời bắt buộc nêu **kỳ dữ liệu** + ngày sync; sync hàng ngày 6h VN |
| **Tự quyết ngân sách / giá / khuyến mãi / booking** | Chặn bằng luật trong `consumer.py` (`ASK_APPROVAL`) **trước** mọi nhánh khác — không phụ thuộc prompt. Có 5 test case |
| **Lộ giá vốn / biên lợi nhuận / chi phí booking** | `scope=agent` cho `kd-confidential`; chặn **trước** khi tra tri thức nên nội dung mật không vào ngữ cảnh. Có 4 test case |
| **Lộ dữ liệu người mua (SĐT, địa chỉ)** | Cùng cơ chế trên; PII còn được redact ở collector |
| **Sót cam kết trong biên bản** | Cam kết là mục bắt buộc; thiếu người/hạn ghi "chưa rõ", không bỏ trống |
| **Biên bản sai được publish** | Không bao giờ tự publish — bắt buộc chủ trì chốt |
| Transcript sai / server transcript chết | `LSR_TRANSCRIBE_URL` cấu hình được; lỗi → job vào DLQ, replay từ console |
| **Riêng tư khi ghi âm họp** | Thông báo minh bạch cho team trước khi tắt `DRY_RUN` |
| Trùng biên bản với AG-MINH-ANH | Ranh giới nhóm ở trên, chốt với admin trước golive |

## Phụ thuộc bên ngoài (chặn golive, không chặn code)

- [ ] `app_token` Lark Base chứa số vận hành sàn + Base/bảng chứa dữ liệu hạn chế.
- [ ] `folder_token` folder chính sách sàn / quy trình (nếu có).
- [ ] App Lark riêng của agent được cấp scope đọc bitable/drive/docx + `im:message`.
- [ ] `chat_id` nhóm Lark của team, admin gán ở Console → Ingress.
- [ ] Danh sách người được xem `kd-confidential` (`KD_CONFIDENTIAL_VIEWERS`).
- [ ] URL transcript server ổn định (hiện là ngrok free, không SLA).
- [ ] Chốt với admin ranh giới nhóm với AG-MINH-ANH.
- [ ] (phase 2) GCP admin cấp dataset + SA riêng cho BigQuery `AI_DB`.
