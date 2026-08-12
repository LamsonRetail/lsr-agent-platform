# Trợ lý Cung Ứng — Workflow

Squad agent theo đúng chuẩn platform (đăng ký registry, telemetry bắt buộc, Lark bot,
resource index). Xem [CREATE_AGENT.md](../../CREATE_AGENT.md).

## A. Tra cứu tri thức Cung Ứng

```
1. Thành viên team hỏi (Lark nhóm / Chat thử console)
2. GET /v1/self/context?...  → tri thức liên quan trong "cung-ung-knowledge"
3a. Có hit    → trả lời + trích dẫn nguồn (source_url / tên tài liệu)
3b. Không hit → "chưa có thông tin đã được duyệt" (không bịa)
```
Nguồn dữ liệu cụ thể (nhà cung cấp, đơn mua hàng, hợp đồng, tồn kho, SLA nhà cung
cấp...) — **đang chờ team Cung Ứng confirm danh sách + nơi lưu (Lark Base/Drive/Wiki)**;
tới khi đó, kho `cung-ung-knowledge` được nạp dần qua các phiên họp đã chốt (luồng B)
và tài liệu team tự thêm qua resource-index.

## B. Biên bản họp

```
1. Lấy transcript            (Whisper server: POST /transcribe -> poll /result)
2. Trích key_points + decisions
3. Soạn biên bản (draft) + đề xuất task
4. Gửi người chủ trì XIN CONFIRM   (Lark IM)      ── status: awaiting_confirm
        │ chủ trì confirm
        ▼
5. Tạo task (Lark Task) + lưu biên bản vào cung-ung-knowledge (resource index)
                                                  ── status: confirmed
```
Không tạo task khi **chưa** có confirm của chủ trì — giống nguyên tắc của agent mẫu
Minh Anh (`agents/minh-anh/WORKFLOW.md`).

## Skills (MCP) dùng
`lark-minutes` (transcript) · `lark-docx` (soạn biên bản) · `lark-task` (tạo task)
· `lark-im` (xin confirm) · `resource-index` (lưu/tra tri thức Cung Ứng).

## Trạng thái hiện tại
- [x] Scaffold agent theo chuẩn platform (`lsr-agent.yaml`, `system_prompt.md`, bộ test).
- [ ] Danh sách nguồn dữ liệu Cung Ứng thật cho `resources.managed_folder` — chờ team confirm.
- [ ] Add bot vào nhóm Lark team Cung Ứng (hiện `chat_ids: []`).
- [ ] Đăng ký squad `SQ-CUNGUNG` trên Lark Base (admin thực hiện).
- [ ] Bật `DRY_RUN=false` sau khi pass bộ test + có token thật.
