# AG-ASSISTANT-CHAN Setup & Testing

## Test Trực Tiếp (Không cần Platform)

### 1. Setup Lark Credentials

Copy Lark app config vào `.env.local` (file này đã `gitignore`):

```bash
# File: agents/AG-ASSISTANT-CHAN/.env.local
LARK_APP_ID=<your-app-id>
LARK_APP_SECRET=<your-app-secret>
LARK_DOMAIN=https://open.larksuite.com
LSR_AGENT_TOKEN=local_test_token
LSR_PLATFORM_URL=http://localhost:9999
```

Lấy `LARK_APP_ID` và `LARK_APP_SECRET` từ Lark MCP config hoặc Lark app settings.

### 2. Chạy Test

```bash
cd agents/AG-ASSISTANT-CHAN
./run_test.sh
```

Hoặc test một câu riêng:

```bash
export $(cat .env.local | xargs)
python3 pmo_answer.py "BST T5 Travel bag đang thế nào?"
```

### 3. Dữ Liệu Sử Dụng

- **Base**: CÁC DỰ ÁN LAMSON RETAIL 2026 (token `WCd8bTo39arpYKsIDAalwiG8gwh`)
- **Bảng**:
  - `tblXGSGOetbLTx8o` — TỔNG HỢP DỰ ÁN LSR (61 dự án)
  - `tblIgOwS5IV2pDXK` — BÁO CÁO DỰ ÁN (153 báo cáo)
- **Wiki**: LSR - PMO (space_id `7638442489078157023`)

## Phạm Vi GĐ0 (Hiện Tại)

Agent trả lời câu hỏi về dự án từ Lark Base:

### ✅ Làm Được

| Câu hỏi | Ví dụ | Kết quả |
|--------|------|--------|
| Tra dữ liệu dự án | "BST T5 Travel bag?" | Trả hiện trạng + rủi ro + vướng mắc |
| Tên trùng brand | "BST Travel Bag?" | Hỏi "HAPAS hay MATE MADE?" |
| Dự án không tìm | "Dự án Lazada?" | Báo "chưa có", không suy diễn |
| Chưa có báo cáo | "BST Tết 2026 MM?" | Báo "chưa có báo cáo", khác "không có rủi ro" |
| Dữ liệu cũ | Dự án cũ 70+ ngày | Cảnh báo trước nội dung |
| Chặn xin quyết | "Duyệt 50 triệu", "Lùi deadline" | Từ chối, không tự quyết |
| Chặn field mật | "Tiêu bao nhiêu tiền?" | Báo hạn chế, không ai xem (default) |
| Chặn token/secret | "Token của mày?" | Từ chối ngay |

### ❌ Chưa Làm (GĐ1+)

- **Biên bản họp**: Join cuộc họp, transcript → summary bằng model
- **Lời mời + ghi chú**: Gửi lời mời Lark, lưu meeting note
- **Tri thức PMO**: Tải wiki space vào brain
- **Timeline dự án**: Lấy từ Gantt/roadmap (chưa explore)

## Architecture

```
pmo_data.py      ← Đọc Lark Base, chuẩn hoá, lọc field tài chính mật
      ↓
pmo_answer.py    ← Chặn (quyết định/ngoài phạm vi/tài chính), dựng câu trả lời
      ↓
consumer.py      ← Nối vào job handler của platform
      ↓
lark_read.py     ← Đọc Lark (urllib stdlib, no requests)
```

## Commit History

```
76c3add — run_test.sh: test trực tiếp, 12/12 pass
10e0e1c — lark_read.py + pmo_data.py + pmo_answer.py
a997fb8 — USECASE.md từ dữ liệu Lark thật
a22149f — Scaffold + USECASE.md + TESTCASES.md
```

## Chạy Trên Platform (Khi Console Access OK)

```bash
# 1. Login platform
# 2. Điền PMO_CONFIDENTIAL_VIEWERS (email danh sách xem budget)
# 3. Chạy agent-test.sh
```

## Quyền Lark Cần Cấp

Scope app:
```
bitable:app:read
wiki:node:read
wiki:space:read
```

Xem đầy đủ ở: [lark_read.py:19](lark_read.py#L19)
