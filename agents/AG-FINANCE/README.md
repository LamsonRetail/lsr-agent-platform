# AG-FINANCE — Trợ lý Tài chính - Kế toán

Agent của squad Finance-Accounting trên LSR Agent Platform. Hai việc:

1. **Tổng hợp số liệu về một nơi.** Google Sheet + MISA AMIS + Lark Base → chuẩn hoá →
   một Lark Base chung (FIN-HUB) mà ai trong squad cũng mở ra xem được, hoặc hỏi qua chat.
2. **Biên bản họp.** Bot trong nhóm Lark nhận recording, dựng biên bản, xin người chủ trì
   chốt, rồi tạo task.

Chỉ đọc. Không ghi vào MISA, không phê duyệt chi, không lập báo cáo thuế.

## Bắt đầu

```bash
bash agents/AG-FINANCE/scripts/setup-dev.sh    # chạy từ gốc repo
```

Rồi đọc **[ONBOARDING.md](ONBOARDING.md)**.

## Bản đồ thư mục

| Đường dẫn | Nội dung | Ai |
|---|---|---|
| [USECASE.md](USECASE.md) | Nghiệp vụ, phạm vi, dữ liệu cần xin quyền | chủ dự án |
| [TESTCASES.md](TESTCASES.md) | Toàn bộ case, có ID để soi ngược từ test | chủ dự án |
| [CLAUDE.md](CLAUDE.md) | Luật cho Claude Code khi làm trong thư mục này | chủ dự án |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Schema FIN-HUB | Hương |
| `lsr-agent.yaml` | Manifest platform | chủ dự án |
| `system_prompt.md` | Prompt của agent | chủ dự án |
| `consumer.py` | Entrypoint, chỉ điều phối | cả hai |
| `data_hub/` | Nạp và chuẩn hoá dữ liệu, hỏi đáp số liệu | **Hương** |
| `meeting/` | Biên bản họp | **Thái** |
| `shared/` | Phân quyền, Lark, model | cả hai |

## Trạng thái

| Phase | Nội dung | Trạng thái |
|---|---|---|
| 0 | Scaffold, tài liệu, guardrail, phân quyền fail-closed | ✅ xong |
| 1 | Google Sheet → Lark Base + hỏi đáp công nợ, doanh thu | ⬜ chờ service account + scope `bitable:app` |
| 2 | MISA AMIS API + dòng tiền, số dư, lãi lỗ | ⬜ chờ credential MISA |
| 3 | Biên bản họp (text trước, audio sau) | ⬜ chờ xác nhận Whisper server |
| 4 | Đăng ký platform, publish dev → stg → prod | ⬜ chờ enroll token |

Phần đã chạy thật ở Phase 0: cửa phân quyền squad (mặc định từ chối) và ranh giới phạm vi.
Phần chưa làm thì trả lời rõ là chưa làm, không trả lời sai.

## Phạm vi sửa file

Dự án này **chỉ** được thêm/sửa file trong `agents/AG-FINANCE/`. Mọi thứ khác trong repo là
core của platform. Có git hook và CI chặn tự động — xem [CLAUDE.md](CLAUDE.md).

## Chạy

```bash
cd agents/AG-FINANCE
.venv/bin/python -m pytest tests/ -q      # test
LSR_AGENT_TOKEN=... python3 consumer.py   # chạy agent
docker compose up                          # hoặc trong container
```

`DRY_RUN=true` (mặc định) thì không gửi tin thật ra Lark/Telegram.
