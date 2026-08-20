# Use case — Trợ lý PMO, quản lý dự án LamsonRetail (AG-ASSISTANT-CHAN)

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

Đã khảo sát thực tế trên Lark (20/08/2026) — **nguồn dữ liệu đã tồn tại, không cần dựng mới**.

**Wiki space `LSR - PMO`** — `space_id: 7638442489078157023`
*"Tổng hợp tất cả các thông tin về dự án toàn LSR và việc quản lý dự án"*. Chứa 3 mục:
`CÁC DỰ ÁN LAMSON RETAIL 2026` (Base), `LSR - PMO - Định hướng và kế hoạch` (doc),
`TEMPLATE BÁO CÁO DỰ ÁN` (doc, có mục con).

**Lark Base `CÁC DỰ ÁN LAMSON RETAIL 2026`** — `app_token: WCd8bTo39arpYKsIDAalwiG8gwh`

| Bảng | table_id | Số dòng | Vai trò với agent |
|---|---|---|---|
| `TỔNG HỢP DỰ ÁN LSR` | `tblXGSGOetbLTx8o` | 61 dự án, 44 field | **Bảng chiều** — danh tính dự án: `Project ID`, `Project Name`, `Brand` (HAPAS/MATE MADE/LSR), `Market`, `Project Status`, `Project Owner`, `Project Sponsor`, các mốc ngày, `Project Chat Channel` |
| `BÁO CÁO DỰ ÁN` | `tblIgOwS5IV2pDXK` | 153 báo cáo tuần | **Nguồn sự thật về hiện trạng** — `REPORTING DATE`, `WEEK`, `OVERVIEW`, `RISK`, `ISSUE`, `NEXT ACTION`, `PIC`, `Mức độ BLG` |
| `THÔNG TIN POD CÁC THÀNH VIÊN DỰ ÁN ON GOING` | `tbl95nPxvXbf2eCK` | 17 | Ai thuộc POD dự án nào |
| `PRODUCT PLAN LAM SON 2026 (RnD)` | `tblvn3D3mRJ01Wla` | 54 | Kế hoạch sản phẩm |

> **Quan trọng: hiện trạng dự án nằm ở `BÁO CÁO DỰ ÁN`, KHÔNG nằm ở bảng tổng hợp.** Ở bảng
> tổng hợp, `Blockers` và `NEXT ACTION` **rỗng toàn bộ 61/61 dòng**, `Project Health` chỉ điền
> 7/61. Agent phải lấy **báo cáo tuần mới nhất của từng dự án** làm câu trả lời, không đọc
> `Blockers` ở bảng tổng hợp.

| Domain tri thức | Nguồn | Scope |
|---|---|---|
| `pmo-projects` | `TỔNG HỢP DỰ ÁN LSR` — trừ các field tài chính bên dưới | shared |
| `pmo-status` | `BÁO CÁO DỰ ÁN` — `OVERVIEW`, `RISK`, `ISSUE`, `NEXT ACTION`, `PIC` | shared |
| `pmo-docs` | Wiki `LSR - PMO` + `DỰ ÁN HAPAS` (`7294455484684173343`) + `DOANH THU ĐỘT PHÁ` (`7297080474252394528`) | shared |
| `pmo-meeting` | biên bản agent tự sinh | shared (giới hạn người dự họp + PMO) |
| `pmo-confidential` | `Financial Target`, `Budget`, `Budget Used`, `Target GM (BLG)`, `Actual GM (BLG)`, `Margin Gap`, `Actual Financial Achivement`, `% Target Achievement`, `CHI PHÍ`, `BLG %` | **agent** — chỉ `PMO_CONFIDENTIAL_VIEWERS` |

> ⚠️ **Dữ liệu mật nằm CÙNG bảng với dữ liệu thường.** Base không tách bảng riêng cho tài
> chính — `Budget`, `Actual GM (BLG)`, `Margin Gap` nằm ngay trong `TỔNG HỢP DỰ ÁN LSR`. Nên
> agent **bắt buộc lọc theo field khi sync**, không được đẩy cả record vào tri thức `shared`.
> Đây là lỗi dễ mắc nhất và hậu quả là lộ biên lợi nhuận toàn công ty.

**Wiki KHÔNG được sync:** `TEAM KINH DOANH MATE MADE` (`7496094770155061279`) — LYLY ghi rõ
AG-LEGAL đã đồng bộ space này. Đã kiểm tra và xác nhận space này tồn tại, tránh sync trùng.
`PHÁP CHẾ` (`7595876759661186785`) cũng nên coi là địa bàn AG-LEGAL.

Đồng bộ bằng job sync chạy hàng ngày. Mọi tri thức vào hàng chờ `status=pending`, **PMO duyệt**
trên console rồi agent mới dùng được.

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
| **AG-ASSISTANT-CHAN** | **chỉ các nhóm dự án được admin gán** — không phải mọi cuộc họp trong công ty |

Bot **không tự add vào nhóm được**: admin gán kênh vào ở Console → Ingress. Nếu một cuộc họp
dự án diễn ra trong nhóm của MATE MADE thì LYLY làm biên bản, AG-ASSISTANT-CHAN **không** chen vào — thay
vào đó xin biên bản đã chốt của LYLY nộp vào tri thức dự án.

## Rủi ro & giới hạn

| Rủi ro | Mức độ | Giảm thiểu |
|---|---|---|
| **Gom nội dung họp của mọi brand và mọi phòng vào một chỗ, một owner** — mức tập trung dữ liệu cao nhất trong các agent hiện có. Họp giá, họp nhân sự, đàm phán nhà cung cấp đều có thể lọt vào. Nghị định 13/2023 về dữ liệu cá nhân áp dụng. | **Cao — chặn golive kênh thật** | Giai đoạn 1 chỉ nhận **2-3 nhóm dự án** được admin gán, chạy `DRY_RUN=true`. Chỉ xử lý bản ghi mà người tổ chức **đã chủ động bật**, không để bot tự join ghi âm. Cần chính sách chính thức của công ty trước khi mở rộng. |
| **Bịa thông tin dự án** — người ta lên kế hoạch dựa trên deadline bịa, kéo theo cả 4 phòng làm sai | Cao | Bắt buộc tra tri thức trước khi trả lời; không có hit → câu từ chối cố định. Đo bằng tỷ lệ câu trả lời có trích nguồn |
| **Trả thông tin ĐÚNG nhưng của kỳ CŨ** — dự án thay đổi liên tục, đây là lỗi âm thầm, không ai phát hiện ngay. Mức toàn cục hiện **tốt**: báo cáo mới nhất 19/08/2026 (WEEK 3), chỉ trễ 1 ngày. Nhưng **từng dự án lại rất lệch** — ví dụ `PRJ-2026010` (BST Travel Bag, MATE MADE) báo cáo gần nhất cách **71 ngày** | Cao | Mọi câu trả lời bắt buộc nêu **ngày báo cáo của chính dự án đó**, không dùng độ mới toàn cục. Quá 14 ngày (`PMO_STALE_DAYS`) → `trang_thai_du_lieu="cu"`, agent phải nói *"số liệu mới nhất em có là tuần …, đã … ngày chưa cập nhật"* trước khi nêu nội dung |
| **Dữ liệu báo cáo điền không đầy đủ** — khảo sát 153 báo cáo: `OVERVIEW` 65%, `NEXT ACTION` 59%, `RISK` 49%, `ISSUE` 37%, `Cần Support` **1%** (gần như chưa ai dùng). Chỉ **39/61 dự án** từng có báo cáo → **22 dự án chưa bao giờ được báo cáo** | Cao | Agent phải phân biệt rõ *"dự án này chưa có báo cáo nào"* (`trang_thai_du_lieu="chua_co_bao_cao"`) với *"dự án này không có rủi ro"* — hai câu khác nhau hoàn toàn. Không được im lặng bỏ qua field rỗng |
| **6/153 báo cáo thiếu `REPORTING DATE`** → không biết thuộc kỳ nào | Trung bình | Agent bỏ qua các bản ghi này khi tính hiện trạng, và nêu ra khi được hỏi về chất lượng dữ liệu — không âm thầm gộp vào |
| **Đọc thiếu trang khi lấy dữ liệu** — lỗi này đã thực sự xảy ra trong quá trình khảo sát: một lần đọc chỉ ra 143 record và làm ngày mới nhất trông như 30/07 thay vì 19/08, dẫn tới kết luận sai *"báo cáo trễ 21 ngày"* | **Cao** | `lark_read.py` bắt buộc duyệt hết trang, có chặn vòng lặp, và đối chiếu `total` của API. Số liệu thiếu trang nguy hiểm hơn không có số vì nó trông vẫn hợp lý |
| **Tên dự án trùng giữa các brand** — `BST Travel Bag`, `BST TRANG SỨC`, `BST NƯỚC HOA` đều tồn tại ở cả HAPAS và MATE MADE | Trung bình | Bắt buộc hỏi lại brand khi tên trùng, không tự chọn. Ưu tiên dùng `Project ID` (`PRJ-2026xxx`) làm khoá thật |
| **Giá trị select có khoảng trắng cuối** (`"ON GOING "`, `"On Track "`) và có bản ghi tự mâu thuẫn (`BST Travel Bag` MATE MADE: `Project Health = At Risk` nhưng `Project Status = DONE`) | Trung bình | Chuẩn hoá (trim) khi sync; gặp bản ghi mâu thuẫn thì nêu rõ mâu thuẫn cho người hỏi thay vì chọn một bên |
| **Lookup bị vỡ**: `Latest Weekly Status` và `Last Update Date` trỏ tới bảng `tblFi6vWe1KrJPTD` không nằm trong Base này → trả `null` toàn bộ 61 dòng | Trung bình | Agent **không dùng 2 field này**. Tự tính ngày cập nhật từ `max(REPORTING DATE)` trong `BÁO CÁO DỰ ÁN` theo từng `PROJECT ID` |
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

- [x] ~~`app_token` Lark Base danh mục dự án~~ — **đã có**: `WCd8bTo39arpYKsIDAalwiG8gwh`
- [x] ~~`space_id` Wiki tài liệu dự án~~ — **đã có**: `7638442489078157023` (`LSR - PMO`), đã kiểm tra không trùng space của AG-LEGAL
- [ ] **22/61 dự án chưa bao giờ có báo cáo** — agent sẽ trả *"chưa có báo cáo"* cho các dự án này. Đây là phụ thuộc *nghiệp vụ*, không phải kỹ thuật: agent không thể chính xác hơn dữ liệu nó đọc
- [ ] `chat_id` của 2-3 nhóm dự án cho giai đoạn 1, admin gán ở Console → Ingress
- [ ] Chốt với admin ranh giới nhóm giữa AG-ASSISTANT-CHAN · LYLY · AG-MINH-ANH
- [ ] Danh sách `PMO_CONFIDENTIAL_VIEWERS`
- [ ] Chính sách công ty về ghi âm/xử lý nội dung họp — **chặn việc mở rộng ngoài 2-3 nhóm thử**
- [ ] App Lark cho agent: dùng `platform-shared` hay app riêng. Nếu app riêng thì cần App ID chính xác — lưu ý App ID được cung cấp lúc đầu (`cli_aaf6cb7a0df8dee7`) **khác** app LYLY đang dùng (`cli_aaf6ca84c5389ed4`), cần xác nhận lại
- [ ] URL transcript server ổn định
- [ ] Xác nhận `squad: PMO` được tạo trên platform và AG-ASSISTANT-CHAN là squad agent chính

## Giai đoạn sau (không làm ở giai đoạn 1)

**Giai đoạn 2 — Theo dõi cam kết xuyên dự án.** Gom cam kết từ mọi biên bản đã chốt, đối chiếu
deadline, **chủ động nhắc việc sắp trượt hạn**. Đây là giá trị PMO thật sự mà không agent nào
khác có. Hoãn sang GĐ2 vì cần dữ liệu cam kết tích lũy đủ và độ chính xác biên bản đã được
kiểm chứng ở GĐ1 — nhắc sai hạn còn tệ hơn không nhắc.

**Giai đoạn 3 — Mở rộng nguồn dữ liệu phòng ban.** Phụ thuộc A2A được platform xây, hoặc từng
owner đồng ý mở dữ liệu sang `shared`.
