# Tích hợp & giám sát Agent (VPS ↔ Lark ↔ Rating Agent)

Trả lời: agent host trên VPS, kết nối Lark qua **bot** hoặc **user account** —
làm sao **đăng ký**, **nắm log**, **kiểm soát token**, **thu kết quả công việc**,
và **đo 6 chỉ số hành vi tool** (TSR/CTUR/RIR/OFR/UTR/CTRL-Acc).

---

## 0. Điểm cốt lõi (đọc trước)

> **Lark chỉ nhìn thấy tin nhắn vào/ra của bot.** Nó KHÔNG biết agent gọi LLM
> mấy lần, tốn bao nhiêu token, gọi tool nào, tool trả gì. Muốn có những thứ đó
> phải **đo tại chính process agent trên VPS** (instrument bằng SDK) và/hoặc cho
> agent **gọi LLM qua một gateway**.

Vì vậy có **3 lớp thu thập**, mỗi lớp cho một loại dữ liệu:

```
┌───────────────────────────────────────────────────────────────────────┐
│                              AGENT (VPS)                                │
│   ┌──────────────┐   gọi LLM   ┌───────────────┐                        │
│   │  Logic agent  │───────────►│  LLM Gateway  │ (đếm+chặn token, log)   │  ← Lớp 2/3
│   │  + Telemetry  │            └───────────────┘                        │
│   │     SDK       │─── ghi trace (token, tool call, kết quả, output) ──┐ │  ← Lớp 3
│   └──────┬───────┘                                                     │ │
└──────────│─────────────────────────────────────────────────────────── │─┘
           │ trả lời qua Lark                                            │
     ┌─────▼──────┐   events (tin nhắn, phản hồi)      ┌─────────────────▼────────┐
     │    Lark     │──────────────────────────────────►│   Rating Agent            │  ← Lớp 1
     │ (bot/user)  │   số lần gọi + kết quả cuối        │   Collector + Kho trace   │
     └────────────┘                                    │   → tính chỉ số, dashboard│
                                                        └───────────────────────────┘
```

| Lớp | Nguồn | Cho ta biết |
|-----|-------|-------------|
| **1. Lark** (bot event / API) | số lần gọi, kết quả cuối gửi cho user, phản hồi (reaction) | usage thô, kết quả công việc mặt người dùng |
| **2. LLM Gateway** (proxy) | mọi lời gọi model + token, có thể **chặn** theo hạn mức | token chính xác + **kiểm soát cứng** |
| **3. Telemetry SDK** (trong agent) | trace đầy đủ: token, từng tool call + kết quả, output | **6 chỉ số hành vi tool** + token + log chi tiết |

Lớp 3 là quan trọng nhất và là thứ đã được code trong `src/rating_agent/telemetry/`.

---

## 1. Đăng ký agent (bắt buộc trước golive)

Luồng đăng ký (nối với registry `agents` trên Lark Base — xem MASTER_DATA.md):

1. Tạo record trong bảng `agents`: `agent_id`, tên, version, owner, squad phục vụ,
   skills, `data_sources`, `endpoint_ref` (địa chỉ VPS), cách kết nối Lark (bot/user).
2. Rating Agent cấp cho agent 2 khoá (lưu **hash**, chỉ hiện 1 lần):
   - **`TELEMETRY_API_KEY`** — để SDK gửi trace về collector.
   - **`GATEWAY_VIRTUAL_KEY`** — khoá ảo ở LLM gateway, gắn hạn mức token.
3. Agent chạy full bộ test (pre-golive). Chỉ khi **pass** → `status = active`.
4. Test tự động chạy định kỳ; fail theo chính sách → **auto-deactivate**
   (đã có trong `agent_scorer` + `agent_testing`).

> Agent chưa đăng ký / thiếu khoá → collector từ chối trace → coi như chưa golive.

---

## 2. Hai cách kết nối Lark

| Tiêu chí | **Bot (Custom App)** — khuyến nghị | **User account** |
|----------|-----------------------------------|------------------|
| Danh tính | App bot chính thức | Đóng vai một user thật |
| Xác thực | `app_id/secret` → tenant token (bền) | OAuth user token (ngắn hạn, hay hết hạn) |
| Nhận việc | **Event subscription** (bot nhận message trong nhóm/DM) | Phải poll hoặc long-conn, mong manh |
| Kiểm soát/kiểm toán | Rõ ràng, có scope, log được | Khó kiểm toán, dễ vi phạm chính sách |
| Vào nhóm/doc | Add bot vào nhóm; cấp quyền theo scope | Theo quyền của user đó |
| Rủi ro | Thấp | Cao (tự động hoá tài khoản người thật) |

**Khuyến nghị: dùng bot.** Chỉ dùng user account khi bắt buộc phải hành động
dưới danh nghĩa một người (và cần review chính sách nội bộ + Lark ToS trước).

Với bot: bật **Event Subscription** cho sự kiện `im.message.receive_v1` → mỗi lần
agent được gọi, Rating Agent nhận được 1 event để **đếm invocation** và log
context; kết quả cuối agent gửi lại nhóm cũng đọc được.

---

## 3. Nắm log & kết quả công việc

- **Log chi tiết (nội bộ agent):** SDK ghi `AgentRunTrace` mỗi lượt (token, từng
  tool call + kết quả OK/lỗi, output) → gửi collector → lưu vào kho trace
  (Lark Base bảng `agent_traces` hoặc BigQuery). Đây là log "chuẩn" để phân tích.
- **Kết quả công việc (mặt người dùng):** lấy từ Lark event (tin nhắn agent trả)
  + `final_output` trong trace. Chất lượng kết quả chấm qua:
  `success_rate`, `user_rating` (reaction 👍/👎 trên Lark), và 6 chỉ số hành vi.
- **Log hệ thống VPS:** stdout/stderr đẩy về cùng collector hoặc một log store —
  tuỳ chọn, không bắt buộc cho chấm điểm.

---

## 4. Kiểm soát token

Hai mức, nên làm cả hai:

1. **Đo (observability):** SDK ghi token mỗi `LLMCall`; `compute_token_stats()`
   tổng hợp theo agent/kỳ → hiển thị trên Agent Detail, cảnh báo khi vượt xu hướng.
2. **Chặn (enforcement):**
   - **Tại chỗ (soft — vì dùng subscription, không API key):** `TokenBudget(
     limit_tokens=...)` trong SDK/plugin → vượt hạn mức thì dừng lượt chạy. Đã code sẵn.
   - **Gateway (hard, OPTIONAL):** chỉ áp dụng cho agent nào chọn dùng **API key**
     qua LiteLLM gateway (virtual key + budget). Với **subscription OAuth thì không
     áp được** — Anthropic không cho cắt token theo key ở tầng đó.

> **Cập nhật auth model:** agent dùng **Claude Agent SDK đăng nhập subscription
> riêng, KHÔNG API key** → không proxy được model call. Vì vậy **cả token lẫn dữ
> liệu tool** đều lấy từ **Telemetry SDK / Claude Code plugin bắt buộc**; kill switch
> là **cắt Lark + dừng process + thu hồi đăng ký** (xem PLAN §5). LiteLLM gateway
> hạ xuống *optional*.

---

## 5. Đo 6 chỉ số hành vi tool

Sáu chỉ số này **không đo được từ Lark** — cần **trace** (lớp 3) chạy trên một
**bộ đánh giá có nhãn**. Mỗi task gắn nhãn `needs_tool` (cần tool hay không),
tách thành 2 tập:

- **Required set** (cần tool): TSR, CTUR, RIR, OFR.
- **Control set** (không cần tool): UTR, CTRL-Acc.

| Chỉ số | Ý nghĩa | Cách đo (đã code: `telemetry/metrics.py`) | Tốt |
|--------|---------|-------------------------------------------|-----|
| **TSR** | Bỏ qua tool đáng lẽ phải dùng | #Required không gọi tool / #Required | ↓ |
| **CTUR** | Dùng tool "sạch" (đúng tool, không lỗi) | #Required dùng tool sạch / #Required | ↑ |
| **RIR** | Có kết quả tool nhưng output phớt lờ | #(có kết quả & bị bỏ qua) / #(có kết quả) | ↓ |
| **OFR** | Output bịa ngoài kết quả tool | #Required bịa / #Required | ↓ |
| **UTR** | Không cần tool vẫn gọi | #Control có gọi tool / #Control | ↓ |
| **CTRL-Acc** | Trả lời đúng khi không cần tool | #Control đúng / #Control | ↑ |

**Nguồn dữ liệu cho từng đánh giá:**
- `needs_tool`, `expected_tool`: nhãn trong bộ test (mở rộng bảng `agent_test_cases`).
- Gọi tool nào, OK/lỗi, có kết quả: SDK ghi tự động (`ToolCall`).
- `result_used` (RIR), `fabricated` (OFR), `answer_correct` (CTRL-Acc): cần **judge**
  ngữ nghĩa. Giai đoạn đầu: heuristic/nhãn tay; giai đoạn 2: **LLM judge** (khớp
  assertion `semantic`). Các trường này nằm sẵn trên `AgentRunTrace`/`TaskLabel`.

**Quy trình:** test runner (`agent_testing`) chạy bộ test có nhãn → agent (qua SDK)
trả về trace → judge điền `result_used/fabricated/answer_correct` → 
`compute_behavior_metrics(traces, labels)` ra 6 chỉ số → lưu `agent_behavior_metrics`
→ hiển thị trên Agent Detail + đưa vào `agent_scorer` (thành phần result/skill).

---

## 6. Bảng master data cần bổ sung (đề xuất)

Thêm vào Lark Base (chi tiết hoá sau khi confirm):

| Bảng | Nội dung |
|------|----------|
| `agent_traces` | mỗi lượt chạy: agent_id, task_id, tokens, số tool call, output, judge flags |
| `agent_task_labels` | nhãn bộ đánh giá: task_id, needs_tool, expected_tool, answer_correct |
| `agent_behavior_metrics` | theo agent+kỳ: TSR/CTUR/RIR/OFR/UTR/CTRL-Acc + token tổng |

`agent_test_cases` mở rộng thêm cột `needs_tool`, `expected_tool`.

---

## 7. Cần confirm

1. **Kết nối Lark:** dùng **bot** (khuyến nghị) hay có tình huống bắt buộc user account?
2. **Token:** chỉ **đo**, hay cần **chặn cứng** qua gateway? Dùng gateway nào
   (LiteLLM tự host trên VPS là gọn nhất)?
3. **Judge cho RIR/OFR/CTRL-Acc:** chấp nhận **LLM judge** (giai đoạn 2) hay muốn
   nhãn tay giai đoạn đầu?
4. Agent dùng nhà cung cấp LLM nào (để SDK đọc đúng trường token usage)?
