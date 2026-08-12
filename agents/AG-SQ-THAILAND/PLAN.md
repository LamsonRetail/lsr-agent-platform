# PLAN — Trợ lý Squad Thái Lan (AG-SQ-THAILAND)

Dự án con nằm **trong** LSR Agent Platform, tuân thủ chuẩn platform. Mọi thứ của dự án
này nằm gọn trong `agents/AG-SQ-THAILAND/` — **không đụng core**.

- Use case: [USECASE.md](USECASE.md) · Test case: [TESTCASES.md](TESTCASES.md)
- Cách 3 người cùng code mà không đụng platform: [TEAM.md](TEAM.md)

---

## 1. Mục tiêu

| # | Mục tiêu | Đo bằng |
|---|---|---|
| M1 | Dữ liệu chung của squad về **một nơi**, tra được, có nguồn | ≥ 20 mục tri thức đã duyệt sau 4 tuần; ≥ 80% câu trả lời có `source_url` |
| M2 | **Ai cũng** tương tác được, qua kênh sẵn có | ≥ 80% thành viên squad có ít nhất 1 lượt hỏi/tuần |
| M3 | Họp xong **có biên bản** trong ngày | ≥ 90% cuộc họp có biên bản được chủ trì chốt trong 24h |

## 2. Kiến trúc (bám đúng platform, không dựng thêm hạ tầng)

```
Nhóm Lark squad TL ─┐
Telegram           ─┼─► event_gateway ─► hàng đợi platform ─► AG-SQ-THAILAND (container riêng)
Web chat console   ─┘                                            │
                                                                 ├─ /v1/self/context   (instruction + tóm tắt + tri thức)
                                                                 ├─ /v1/self/brain/*   (kho dữ liệu chung, có source_url)
                                                                 ├─ Whisper server     (transcript recording)
                                                                 ├─ /v1/self/actions/propose (đề xuất task — không tự tạo)
                                                                 └─ /v1/self/jobs/{id}/reply (platform gửi đúng kênh)
```

**Không cần** Vercel, Supabase, DB riêng hay web riêng — console của agent có sẵn tại
`https://app.34-126-154-135.sslip.io/agent/AG-SQ-THAILAND`.

### File & chủ sở hữu (3 người code song song, không giẫm chân)

| File | Việc | Chủ |
|---|---|---|
| `consumer.py` | khung poll job + định tuyến | owner (Thi) |
| `knowledge.py` | kho dữ liệu chung: lưu có nguồn, chặn nhạy cảm, tra cứu | **Thái** |
| `minutes.py` | biên bản: dựng nháp, gate confirm, trích đầu việc | **Hương** |
| `transcribe.py` | client Whisper (submit/poll) | **Hương** |
| `USECASE.md` / `TESTCASES.md` / `tests.jsonl` | use case & test | owner + cả nhóm |

## 3. Lộ trình

### Phase 0 — Khung & chuẩn ✅ (bản commit này)
- [x] Scaffold bằng `scripts/new-agent.sh` (đúng quy trình use case → test case → code)
- [x] `USECASE.md` + `TESTCASES.md` + `tests.jsonl` + bộ test có nhãn `tests/agent_tests.yaml`
- [x] `lsr-agent.yaml` đạt chuẩn CI: owner email thật · `auth: subscription` · `telemetry.enabled: true` · không khoá LLM
- [x] Code 3 luồng chạy bằng luật (chạy & test được ngay, chưa cần model)
- [x] Docker riêng, chỉ stdlib

### Phase 1 — Lên sóng nội bộ (tuần 1)
- [ ] Owner `claude setup-token` → đăng ký agent: `python3 scripts/lsr_adopt.py --enroll-token <admin cấp> --id AG-SQ-THAILAND --name "Trợ lý Squad Thái Lan" --owner thint@hapas.vn --squad SQ-THAILAND`
- [ ] Chạy `docker compose up` với `DRY_RUN=true` → test qua web chat console
- [ ] `bash scripts/agent-test.sh AG-SQ-THAILAND` xanh 9/9
- [ ] Admin gán ingress: channel `lark` + `chat_id` nhóm squad Thái Lan
- [ ] **Thông báo minh bạch** cho squad về việc bot đọc nhóm (yêu cầu tuân thủ của platform)

### Phase 2 — Thay luật bằng model (tuần 2)
- [ ] `answer()` gọi Claude Agent SDK với `build_prompt(ctx, q)` (auth = subscription owner)
- [ ] `minutes.build_draft()` gọi model bằng `minutes.prompt_for()` rồi parse về `Minutes`
- [ ] Giữ nguyên mọi gate: có nguồn mới lưu · chưa confirm không tạo task · chặn nhạy cảm
- [ ] Bật `DRY_RUN=false` sau khi duyệt

### Phase 3 — Nạp kho & vận hành (tuần 3–4)
- [ ] Import tài liệu nền của squad (quy trình, NCC, bảng giá) — mỗi mục **bắt buộc** `source_url`
- [ ] Chỉ định reviewer chuyên môn cho tag `squad-thailand` trên console
- [ ] Theo dõi cost/quota + health alert trên console; đặt hạn mức token
- [ ] Đánh giá squad/agent theo scorer của platform

## 4. Cần core làm (KHÔNG tự sửa — nhờ maintainer)

| # | Việc | Vì sao chặn | Ai làm |
|---|---|---|---|
| C1 | `event_gateway` chưa đẩy `file_key`/URL tải file recording (`infra/lsr-platform/event_gateway/gateway.py:66-80` chỉ có text/message_type) | Luồng 3 chưa tải được recording từ Lark → hiện phải dán transcript tay | maintainer |
| C2 | Gán ingress Lark cho `AG-SQ-THAILAND` + add bot vào nhóm squad | Không có event thì agent không nhận việc | admin |
| C3 | Cấp `enroll-token` để đăng ký agent | Không có token thì không chạy được | admin |
| C4 | Xác nhận endpoint `/v1/self/actions/propose` nhận `kind: create_task` | Đề xuất đầu việc sau khi chốt biên bản | maintainer |

> Cách xử lý: mở issue trên repo, gắn nhãn `agent:AG-SQ-THAILAND`. Hương/Thái **không**
> tự sửa `infra/`, `src/`, `scripts/`, `.github/` — CI scope-guard sẽ chặn PR.

## 5. Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| Biên bản model dựng sai → quyết định sai | Gate confirm của chủ trì; không tạo task trước confirm |
| Tri thức không kiểm chứng vào kho | Bắt buộc `source_url`; trạng thái `pending_review`; reviewer chuyên môn |
| Lộ thông tin nhạy cảm qua kênh chung | Chặn từ khoá ở `knowledge.py` + PII redact ở collector |
| Whisper server (ngrok) chết | Job vào DLQ, replay từ console; fallback dán transcript tay |
| Chi phí token tăng | Hạn mức + cảnh báo cost trên console (platform có sẵn) |
