# Use case — Trợ lý PMO, quản lý dự án LamsonRetail (AG-PMO)

Owner: trangdq@hapas.vn — Đặng Quỳnh Trang, PMO (Quản lý dự án công ty)
Squad: PMO · `is_squad_agent: true`

## Bài toán

PMO quản lý các dự án phát sinh của **tất cả brand trong LamsonRetail**, cắt ngang mọi phòng
ban: Kinh doanh, Marketing, Sản phẩm, Supply chain.

Vấn đề của vai trò này không phải thiếu dữ liệu — mà là dữ liệu **nằm rải theo trục phòng ban,
trong khi công việc PMO đi theo trục dự án**. Một dự án chạy qua 4 phòng thì thông tin nằm ở 4
chỗ, mỗi phòng chỉ thấy phần của mình. Hệ quả cụ thể:

1. **Không ai trả lời được "dự án X đang tắc ở đâu"** mà không đi hỏi vòng quanh 4 phòng. PMO
   trở thành người chạy tin thủ công giữa các phòng.
2. **Cam kết trong họp bị mất.** Họp dự án ra quyết định và phân việc, nhưng biên bản viết tay
   chậm và hay sót phần ai-làm-gì-hạn-nào. Tuần sau không ai truy được.
3. **Các phòng ban hỏi lặp lại.** Cùng một câu hỏi về tiến độ/phạm vi/deadline của dự án được
   hỏi đi hỏi lại, PMO trả lời tay từng lần.

Agent này làm trợ lý của PMO, và là **một nơi để mọi phòng ban hỏi thông tin dự án**.

> **Ranh giới cốt lõi: agent tra thông tin để người ta quyết, KHÔNG quyết thay.** Mọi việc đổi
> phạm vi dự án, đổi deadline, phân bổ lại nguồn lực, hay tiêu tiền đều phải người có thẩm
> quyền duyệt. Agent chỉ nêu hiện trạng và chỉ ra rủi ro.

## Người dùng

| Ai | Hỏi gì / cần gì |
|---|---|
| **PMO (owner)** | Tình trạng mọi dự án, việc nào sắp trượt hạn, cam kết nào chưa ai làm, dự án nào thiếu người quyết |
| **Chủ trì cuộc họp dự án** | Người **chốt** biên bản trước khi publish |
| **Kinh doanh** | Dự án nào ảnh hưởng tới hàng/giá/campaign của brand mình, mốc nào cần chuẩn bị |
| **Marketing** | Deadline nội dung/chiến dịch gắn với dự án, phạm vi đã chốt hay chưa |
| **Sản phẩm** | Yêu cầu sản phẩm đã chốt trong họp nào, ai là người quyết |
| **Supply chain** | Mốc hàng về, thay đổi kế hoạch ảnh hưởng tới đặt hàng/tồn kho |

## Luồng chính (happy path)

### Luồng A — Hỏi đáp thông tin dự án

1. Ai đó hỏi trong nhóm Lark hoặc web chat, ví dụ: *"dự án ra mắt dòng túi mới đang ở bước nào?"*
2. Agent gọi `/v1/self/context` → nhận instruction bản đang publish + tóm tắt hội thoại + fact
   người dùng + tri thức liên quan kèm `source_url`.
3. Có căn cứ trong tri thức đã duyệt → trả lời gọn: **hiện trạng + người chủ trì + mốc kế tiếp
   + trích dẫn nguồn + ngày cập nhật dữ liệu**.
4. **Không có căn cứ** → nói thẳng *"Cái này em chưa có trong danh mục dự án, anh/chị hỏi lại
   PMO nhé."* Không suy đoán, không suy từ dự án tương tự.
5. Câu hỏi chạm dữ liệu hạn chế (xem Ranh giới dữ liệu) → chỉ trả lời cho người trong phạm vi.
6. Ghi lượt hội thoại để lượt sau còn ngữ cảnh.

### Luồng B — Ai đó xin quyết định (chặn cứng)

Câu kiểu *"lùi deadline dự án này sang tháng sau nhé"*, *"bỏ hạng mục này khỏi phạm vi"*,
*"điều người từ dự án A sang B"*, *"duyệt thêm ngân sách cho dự án"* → agent **không bao giờ
phán "được"**, kể cả khi tri thức có sẵn số chứng minh nên làm.

Agent: nói rõ không tự quyết được → tra hiện trạng và rủi ro liên quan để người hỏi trình
người có thẩm quyền → nhắc **đừng thông báo cho các phòng khác trước khi có duyệt**.

### Luồng C — Biên bản họp dự án

1. Ai đó gửi recording / link Lark Minutes vào nhóm dự án đã được admin gán.
2. Agent gửi transcript job lên transcript server, chờ kết quả.
3. Dựng **biên bản nháp**: bối cảnh · nội dung chính · quyết định đã chốt · **cam kết (ai · làm
   gì · hạn)** · vấn đề còn treo · rủi ro nêu trong họp. Ghi rõ dự án nào, phòng nào liên quan.
4. Post nháp vào nhóm và **xin chủ trì xác nhận**. **Không tự publish.**
5. Chủ trì trả lời "chốt" → tạo Lark Docs, nộp biên bản vào hàng chờ tri thức để lần sau tra
   được, và cập nhật cam kết vào danh mục dự án.
6. Chủ trì trả lời "sửa ..." → cập nhật nháp, xin chốt lại.

Cam kết thiếu người phụ trách hoặc thiếu hạn thì ghi **"chưa rõ"**, không bỏ trống và không tự
gán người.

## Ngoài phạm vi (không làm)

- **Không tự quyết** phạm vi dự án, deadline, phân bổ nguồn lực, ngân sách — đẩy về người có
  thẩm quyền. Kể cả khi người hỏi nói gấp.
- **Không tự publish biên bản** khi chưa có chủ trì chốt.
- **Không tự tạo task** ở giai đoạn 1. Cam kết chỉ được liệt kê trong biên bản và danh mục dự
  án. Lý do: tự tạo task khi biên bản còn có thể sai sẽ sinh rác và làm mất tin cậy.
- **Không chủ động nhắc việc sắp trượt hạn** ở giai đoạn 1 — xem Giai đoạn 2. Nhắc sai hạn
  còn tệ hơn không nhắc.
- **Không nhận việc biên bản cho nhóm chưa được admin gán** — xem Ranh giới với LYLY và
  AG-MINH-ANH. Đây là ranh giới cố ý.
- Không đưa thông tin ngoài tri thức đã duyệt. Không làm tròn, không nói "khoảng".
- Không sửa dữ liệu gốc trên Lark Base / Wiki — **chỉ đọc**.
- Không xử lý lương thưởng, đánh giá nhân sự, hay nội dung họp nhân sự — kể cả khi lọt vào
  nhóm dự án. Gặp nội dung này thì dừng, không đưa vào biên bản.

## Dữ liệu cần truy cập

| Nguồn | Domain tri thức | Scope | Trạng thái |
|---|---|---|---|
| **Lark Base — danh mục dự án** (dự án, brand, phòng liên quan, chủ trì, milestone, deadline, trạng thái, việc đang tắc) | `pmo-projects` | shared | ⬜ cần `app_token` — **nguồn sự thật chính** |
| **Lark Wiki / Docs — tài liệu dự án** (kế hoạch, phạm vi đã chốt, SOP) | `pmo-docs` | shared | ⬜ cần `folder_token` / `space_id` |
| **Biên bản họp dự án đã chốt** | `pmo-meeting` | shared | agent tự sinh |
| Dữ liệu hạn chế của dự án (ngân sách, chi phí, điều khoản nhà cung cấp) | `pmo-confidential` | **agent** (chỉ AG-PMO) | ⬜ cần Base/bảng riêng + danh sách người được xem |

Đồng bộ bằng job sync chạy hàng ngày. Mọi tri thức vào hàng chờ `status=pending`, **PMO duyệt**
trên console rồi agent mới dùng được.

> ⚠️ **Trước khi khai `space_id` Wiki phải kiểm tra space đó đã có agent khác sync chưa.** Tiền
> lệ: LYLY ghi rõ trong manifest *"KHÔNG sync wiki space 7496094770155061279 — AG-LEGAL đã đồng
> bộ space đó"*. Hai agent sync cùng space sẽ nhân đôi tri thức và tốn chi phí gấp đôi.

## Ranh giới dữ liệu (ai thấy được gì)

| Nhóm dữ liệu | Ai tra được |
|---|---|
| Tiến độ, mốc, chủ trì, phạm vi đã chốt (`pmo-projects`) | mọi phòng ban liên quan dự án |
| Tài liệu dự án, kế hoạch (`pmo-docs`) | mọi phòng ban liên quan dự án |
| Biên bản họp dự án đã chốt (`pmo-meeting`) | **chỉ người dự cuộc họp đó + PMO** — không mở cho cả công ty |
| Ngân sách, chi phí, điều khoản nhà cung cấp (`pmo-confidential`) | **chỉ người trong `PMO_CONFIDENTIAL_VIEWERS`** — `scope=agent` |

Biên bản họp **không** mở cho toàn công ty là quyết định có chủ ý: nội dung họp dự án thường có
đánh giá về hiệu suất phòng ban khác và đàm phán chưa chốt.

## Ranh giới với các agent khác (BẮT BUỘC chốt với admin trước golive)

Platform đã có hai agent làm biên bản họp. Ba agent **không được cùng vào một nhóm** — nếu
cùng nhóm sẽ ra nhiều biên bản khác nhau cho cùng cuộc họp và không ai biết bản nào là chính.

| Agent | Địa bàn |
|---|---|
| **AG-KD-MATE-MADE (LYLY)** | nhóm của team MATE MADE |
| **AG-MINH-ANH** | agent demo/tham chiếu của platform |
| **AG-PMO** | **chỉ các nhóm dự án được admin gán** — không phải mọi cuộc họp trong công ty |

Bot **không tự add vào nhóm được**: admin gán kênh vào ở Console → Ingress. Nếu một cuộc họp
dự án diễn ra trong nhóm của MATE MADE thì LYLY làm biên bản, AG-PMO **không** chen vào — thay
vào đó xin biên bản đã chốt của LYLY nộp vào tri thức dự án.

## Rủi ro & giới hạn

| Rủi ro | Mức độ | Giảm thiểu |
|---|---|---|
| **Gom nội dung họp của mọi brand và mọi phòng vào một chỗ, một owner** — mức tập trung dữ liệu cao nhất trong các agent hiện có. Họp giá, họp nhân sự, đàm phán nhà cung cấp đều có thể lọt vào. Nghị định 13/2023 về dữ liệu cá nhân áp dụng. | **Cao — chặn golive kênh thật** | Giai đoạn 1 chỉ nhận **2-3 nhóm dự án** được admin gán, chạy `DRY_RUN=true`. Chỉ xử lý bản ghi mà người tổ chức **đã chủ động bật**, không để bot tự join ghi âm. Cần chính sách chính thức của công ty trước khi mở rộng. |
| **Bịa thông tin dự án** — người ta lên kế hoạch dựa trên deadline bịa, kéo theo cả 4 phòng làm sai | Cao | Bắt buộc tra tri thức trước khi trả lời; không có hit → câu từ chối cố định. Đo bằng tỷ lệ câu trả lời có trích nguồn |
| **Trả thông tin ĐÚNG nhưng của kỳ CŨ** — dự án thay đổi liên tục, đây là lỗi âm thầm, không ai phát hiện ngay | Cao | Mọi câu trả lời bắt buộc nêu **ngày cập nhật dữ liệu**. Sync hàng ngày. Trạng thái cũ hơn 7 ngày phải cảnh báo rõ trong câu trả lời |
| **Tự quyết phạm vi / deadline / nguồn lực** | Cao | Chặn bằng luật trong `consumer.py` **trước** mọi nhánh khác — không phụ thuộc prompt. Có test case |
| **Lộ nội dung họp sang phòng không liên quan** — PMO thấy hết nên agent cũng thấy hết, dễ trả lời cho người không nên biết | Cao | `pmo-meeting` giới hạn người dự họp + PMO; `pmo-confidential` để `scope=agent`; chặn **trước** khi tra tri thức nên nội dung mật không vào ngữ cảnh |
| **A2A chưa được xây** (`docs/ARCHITECTURE.md` mục 7 ghi trạng thái "Chưa") → không hỏi được LYLY, AG-SOURCING, AG-LEGAL về dữ liệu phòng họ | **Trung bình — giới hạn thiết kế** | Giai đoạn 1 **không phụ thuộc A2A**: PMO tự sync từ Lark Base/Wiki của mình. Dữ liệu phòng ban khác đưa vào qua danh mục dự án do PMO cập nhật, không qua agent khác |
| **Không đọc được dữ liệu `scope=agent` của brand khác** (ví dụ `kd-confidential` của LYLY) | Trung bình | Đây là **giới hạn theo thiết kế của platform, không phải lỗi**. Muốn vượt phải từng owner đồng ý chuyển sang `shared` — quyết định của họ. Agent phải nói rõ "phần này thuộc dữ liệu hạn chế của brand X" thay vì im lặng trả thiếu |
| **Sót cam kết trong biên bản** — mất đúng thứ PMO cần nhất | Trung bình | Cam kết là mục bắt buộc; thiếu người/hạn ghi "chưa rõ", không bỏ trống, không tự gán người |
| **Biên bản sai được publish** | Trung bình | Không bao giờ tự publish — bắt buộc chủ trì chốt |
| **Trùng biên bản với LYLY / AG-MINH-ANH** | Trung bình | Ranh giới nhóm ở mục trên, chốt với admin trước golive |
| Transcript sai / server transcript chết | Thấp | URL cấu hình được; lỗi → job vào DLQ, replay từ console |
| **Owner là điểm tập trung rủi ro**: PMO vừa là owner, vừa duyệt tri thức, vừa là người dùng chính. Một mục sai được duyệt nhầm thì không có lớp thứ hai bắt lại | Trung bình | Khi việc đã quen, tách người duyệt theo phòng ban (chủ trì dự án duyệt tri thức dự án của mình) |

## Phụ thuộc bên ngoài (chặn golive, không chặn code)

- [ ] `app_token` Lark Base danh mục dự án — **quan trọng nhất**, chưa có thì không có nguồn sự thật
- [ ] `space_id` / `folder_token` Wiki-Docs tài liệu dự án, **kèm xác nhận space đó chưa có agent khác sync**
- [ ] `chat_id` của 2-3 nhóm dự án cho giai đoạn 1, admin gán ở Console → Ingress
- [ ] Chốt với admin ranh giới nhóm giữa AG-PMO · LYLY · AG-MINH-ANH
- [ ] Danh sách `PMO_CONFIDENTIAL_VIEWERS`
- [ ] Chính sách công ty về ghi âm/xử lý nội dung họp — **chặn việc mở rộng ngoài 2-3 nhóm thử**
- [ ] App Lark cho agent: dùng `platform-shared` hay app riêng. Nếu app riêng thì cần App ID chính xác — lưu ý App ID được cung cấp lúc đầu (`cli_aaf6cb7a0df8dee7`) **khác** app LYLY đang dùng (`cli_aaf6ca84c5389ed4`), cần xác nhận lại
- [ ] URL transcript server ổn định
- [ ] Xác nhận `squad: PMO` được tạo trên platform và AG-PMO là squad agent chính

## Giai đoạn sau (không làm ở giai đoạn 1)

**Giai đoạn 2 — Theo dõi cam kết xuyên dự án.** Gom cam kết từ mọi biên bản đã chốt, đối chiếu
deadline, **chủ động nhắc việc sắp trượt hạn**. Đây là giá trị PMO thật sự mà không agent nào
khác có. Hoãn sang GĐ2 vì cần dữ liệu cam kết tích lũy đủ và độ chính xác biên bản đã được
kiểm chứng ở GĐ1 — nhắc sai hạn còn tệ hơn không nhắc.

**Giai đoạn 3 — Mở rộng nguồn dữ liệu phòng ban.** Phụ thuộc A2A được platform xây, hoặc từng
owner đồng ý mở dữ liệu sang `shared`.
