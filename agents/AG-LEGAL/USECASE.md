# Use case — Legal Agent (AG-LEGAL)

> ⚠️ BẮT BUỘC điền trước khi code (gate của platform sẽ chặn code nếu thiếu file này).

## Bài toán

Nhân viên LSR thường xuyên cần tra cứu quy định/chính sách nội bộ và pháp luật liên
quan, soạn hợp đồng theo mẫu, và nhờ pháp chế review hợp đồng đối tác. Bộ phận Pháp
chế tốn nhiều thời gian trả lời câu hỏi lặp lại, điền hợp đồng mẫu, và review sơ bộ;
nhân viên thì chờ lâu hoặc tự làm sai. Văn bản pháp luật mới (nghị định, thông tư,
hướng dẫn) cũng cần được theo dõi thủ công.

AG-LEGAL giải quyết 5 việc (S1–S5):

- **S1 — Hỏi đáp pháp chế**: trả lời câu hỏi về quy định/chính sách công ty **có
  trích dẫn** từ kho tài liệu chính thức (Lark Wiki pháp chế + Drive văn bản luật),
  qua engine NotebookLM — không bịa, ngoài tài liệu thì nói rõ và hướng về legal team.
- **S2 — Tạo hợp đồng**: điền template có sẵn (Drive) qua hội thoại thu thập thông
  tin, xuất bản DRAFT.
- **S3 — Review hợp đồng đối tác**: nhận file, đối chiếu checklist pháp chế, trả
  danh sách rủi ro; khi hết vấn đề → chuyển người có thẩm quyền xác nhận.
- **S4 — Tổng hợp văn bản luật**: crawl nguồn uy tín định kỳ, tóm tắt, lưu về Drive
  folder văn bản luật + digest cho legal team — **chỉ gửi/nạp KB sau khi Pháp chế duyệt**.
- **S5 — Hỗ trợ quy trình trình ký** (trên Lark Approval): Bước 3 rà soát đủ đầu mục hồ sơ
  + review nội dung trước khi người rà soát chính vào việc; Bước 5 cross-check sau khi
  Pháp chế và Tài chính/Nhân sự đã rà soát. Agent **không phải chốt duyệt** và **không
  được chặn hồ sơ** (quá SLA thì tự thông + ghi chú).

## Pháp chế in the loop (áp cho cả S1–S5)

Không output nào tới người dùng cuối hoặc vào KB chính thức mà Pháp chế không biết:

| Mức | Dùng ở | Hành vi |
|---|---|---|
| Observe | S1, S5 Bước 3/5 | báo về group Pháp chế/Admin, **không chặn** |
| Gate | S2 draft, S4 digest, S3 bước cuối | **chặn** tới khi có người quyết định |
| Takeover | khi Pháp chế `#id tham gia` | Agent im, người xử lý trực tiếp |

Thông báo + phê duyệt qua **một group Lark** (`oc_2c44821d37e5e12a2c1651251cfd4efb`);
người duyệt quyết định bằng lệnh nhắn (`#12 duyệt` / `sửa:` / `huỷ:` …).
Người duyệt hiện tại: **Nguyễn Trần Thi** (BOD) và **Nguyễn Thị Anh** (Legal).

## Người dùng

- **Nhân viên LSR** (mọi phòng ban): hỏi đáp S1, tạo hợp đồng S2, nộp hợp đồng S3.
  Qua **Lark chat** và **web console**. (Telegram: bỏ khỏi scope 17/08/2026.)
- **Legal team**: quản lý tài liệu trên Wiki/Drive, chỉnh instruction qua console,
  nhận digest S4, là người có thẩm quyền duyệt ở S3.
- **Admin platform**: duyệt publish instruction, nhận cảnh báo sync/engine lỗi.

## Luồng chính (happy path)

### S1 — Hỏi đáp
1. Người dùng hỏi: "Chính sách đổi trả hàng của công ty cho khách sỉ là gì?"
2. Agent lấy context platform (memory + instruction) → hỏi NotebookLM (KB đã sync
   từ Wiki pháp chế + Drive văn bản luật) → nhận answer + citations.
3. Trả về theo format: **Trả lời** (căn cứ tài liệu) → **⚠️ Rủi ro pháp lý** →
   **✅ Đề xuất hành động** → **📎 Nguồn** (tên tài liệu + link Lark).

### S2 — Tạo hợp đồng (Phase 3)
1. "Tạo hợp đồng nguyên tắc mua bán với nhà cung cấp X."
2. Agent liệt kê template phù hợp → hỏi lần lượt các trường còn thiếu (lưu state,
   tiếp tục được giữa các phiên) → xác nhận tóm tắt.
3. Điền docx (đóng dấu **DRAFT**) → upload Drive → **chuyển Pháp chế kiểm tra**.
4. Pháp chế duyệt → agent gửi link cho người yêu cầu. Yêu cầu sửa → agent quy góp ý về
   field và làm lại; góp ý không quy được về field thì **hỏi lại người**, không đoán.

### S3 — Review hợp đồng (Phase 4)
1. Người dùng gửi file hợp đồng đối tác kèm ghi chú loại hợp đồng.
2. Agent đối chiếu checklist pháp chế (trên Wiki) + chính sách → trả báo cáo rủi ro
   (mức độ, điều khoản, đề xuất sửa).
3. Người dùng nộp lại bản đã xử lý → hết vấn đề → agent mở gate cho người có thẩm quyền
   (duyệt bằng lệnh trong group) → báo kết quả cho người nộp.
   Model lỗi → báo "chưa rà soát được", **không bao giờ kết luận hợp đồng sạch**.

### S4 — Tổng hợp văn bản luật (Phase 5)
1. Hằng ngày (6h), thread crawl danh sách nguồn RSS uy tín, dedupe theo số hiệu văn bản.
2. Văn bản mới → tóm tắt phạm vi/hiệu lực/tác động tới LSR. **Mục không trích được link
   nguồn thì bị loại.**
3. Digest ở trạng thái chờ → **Pháp chế duyệt trong group** → mới gửi group + lưu file về
   Drive folder văn bản luật + nạp notebook "Legal Updates". Chưa duyệt = không gửi, không nạp KB.

### S5 — Hỗ trợ trình ký (Phase 6, đang chạy shadow)
1. **Bước 3**: hồ sơ vào → Agent đối chiếu danh mục đầu mục theo loại hợp đồng + rà soát
   nội dung → báo cáo đính kèm hồ sơ, DM người khởi tạo nếu thiếu giấy tờ.
2. **Bước 4**: Pháp chế rồi Tài chính/Nhân sự rà soát (người làm, Agent không tham gia).
3. **Bước 5**: Agent cross-check bản cuối. Mức chặn → đề nghị quay lại Bước 4; mức thấp →
   cảnh báo tham khảo, Admin vẫn trình ký.
4. Quá SLA 30 phút hoặc Agent lỗi → hồ sơ **vẫn đi tiếp** kèm ghi chú "chưa rà soát kịp".
   Agent không bao giờ là lý do hồ sơ bị treo.

## Ngoài phạm vi (không làm)

- Không đưa ra **tư vấn pháp lý chính thức** — mọi output là tham khảo nội bộ, quyết
  định cuối thuộc legal team/người có thẩm quyền.
- Không tự ý ký/phát hành hợp đồng; mọi bản S2 là DRAFT, mọi kết luận S3 phải qua
  người có thẩm quyền.
- Không trả lời dựa trên kiến thức nền của model khi KB không có căn cứ.
- Không xử lý tranh chấp/tố tụng cụ thể — chuyển legal team.

## Dữ liệu cần truy cập

| Nguồn | Chi tiết | Quyền |
|---|---|---|
| Lark Wiki pháp chế | space_id `7595876759661186785` | Bot cần được thêm vào space (Read) — **đang chờ admin** |
| Drive folder văn bản luật | `MIx2fFd8rlzWJBd9bQGlcLQegCd` | Bot đọc được ✅ |
| Drive folder template hợp đồng | (chưa chỉ định — env `LEGAL_TEMPLATE_FOLDER`) | Chờ legal team |
| Drive folder lưu bản thảo DRAFT | (chưa chỉ định — env `LEGAL_DRAFT_FOLDER`) | Chờ chỉ định |
| NotebookLM | 2 notebook: "LSR Legal KB" + "LSR Legal Updates"; tài khoản Google cá nhân, auth storage_state.json | Chờ chủ tài khoản login |
| Nguồn luật public | thuvienphapluat.vn, luatvietnam.vn, chinhphu.vn… (danh sách trong console) | Public |

## Rủi ro & giới hạn

- `notebooklm-py` là API **không chính thức** — có thể gãy khi Google thay đổi;
  engine được bọc interface để swap sang Gemini File Search API.
- Trả lời chỉ đúng bằng KB tại thời điểm sync gần nhất (footer ghi thời điểm sync).
- Giới hạn NotebookLM: ~300 sources/notebook; theo dõi và cảnh báo khi gần chạm.
- Hợp đồng do agent tạo/review **không có giá trị thay thế thẩm định của pháp chế**.
