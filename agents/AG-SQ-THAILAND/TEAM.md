# TEAM — cách 3 người cùng code mà KHÔNG đụng platform

Áp dụng cho: **Thi (owner)** · **Hương** · **Thái**.

## Nguyên tắc số 1

> Mọi thay đổi của dự án này nằm gọn trong `agents/AG-SQ-THAILAND/`
> (và `apps/agents/AG-SQ-THAILAND/` nếu sau này cần backend riêng — hiện KHÔNG cần).
> **Không sửa bất kỳ file nào khác** của repo: `infra/`, `src/`, `scripts/`, `plugins/`,
> `apps/platform-web/`, `.github/`, `tests/`, `docs/`, agent khác, file .md ở gốc.

Cần platform đổi gì (mở đường tải file, gán ingress, cấp token...) → **mở issue**, gắn
nhãn `agent:AG-SQ-THAILAND`, maintainer (`ntranthi`) xử lý. Xem [PLAN.md](PLAN.md) §4.

## Mô hình cộng tác: FORK + PR (chặn cứng)

Hương và Thái giữ quyền **read** trên `LamsonRetail/lsr-agent-platform` — về mặt kỹ thuật
**không thể push** vào repo gốc, nên không có cách nào "lỡ tay" đụng core.

```bash
# 1. Fork trên GitHub (nút Fork) → về tài khoản cá nhân, rồi:
git clone https://github.com/<username>/lsr-agent-platform.git
cd lsr-agent-platform
git remote add upstream https://github.com/LamsonRetail/lsr-agent-platform.git

# 2. Cài hook chặn sớm (nhắc ngay khi commit chạm core):
bash scripts/install-git-hooks.sh

# 3. Làm việc trên branch của dự án:
git checkout -b agent/thailand-AG-SQ-THAILAND

# 4. Trước khi push, tự kiểm phạm vi:
bash scripts/check-scope.sh --vs-main

# 5. Push lên FORK của mình rồi mở PR về LamsonRetail:main
git push origin agent/thailand-AG-SQ-THAILAND
gh pr create --repo LamsonRetail/lsr-agent-platform --base main
```

Khi PR mở, CI chạy 2 gate của platform:
- **scope-guard** — fail nếu PR chạm file ngoài `agents/<id>/**`, `apps/agents/<id>/**`;
- **agent-gate** — fail nếu có code mà thiếu `USECASE.md`/`TESTCASES.md` (đã có sẵn).

Cập nhật code mới nhất từ repo gốc:
```bash
git fetch upstream && git merge upstream/main
```

## Chia việc để không giẫm chân nhau (1 người / 1 file)

| Người | File phụ trách | Việc |
|---|---|---|
| **Thái** | `knowledge.py` | kho dữ liệu chung: lưu có nguồn, chặn nhạy cảm, tra cứu |
| **Hương** | `minutes.py`, `transcribe.py` | biên bản họp + client Whisper |
| **Thi** | `consumer.py`, `lsr-agent.yaml`, `system_prompt.md` | khung, định tuyến, manifest, prompt |
| Cả nhóm | `USECASE.md`, `TESTCASES.md`, `tests.jsonl` | thêm case trước khi thêm code |

Quy ước:
- Đổi **chữ ký hàm** dùng chung (`answer`, `save`, `build_draft`, `submit/wait`) → báo trong
  nhóm trước, vì người khác đang gọi.
- Thêm tính năng = thêm case vào `TESTCASES.md` + `tests.jsonl` **trước**, code sau
  (đúng quy trình platform use case → test case → code).
- **Không commit secret**: `.env`, `.env.lsr`, token — đã gitignore, CI cũng quét.

## Chạy & test tại chỗ

```bash
cd agents/AG-SQ-THAILAND
cp .env.example .env            # điền LSR_AGENT_TOKEN (hỏi owner/admin)
docker compose up               # DRY_RUN=true mặc định — không gửi tin thật

# test tự động (terminal khác, từ gốc repo):
bash scripts/agent-test.sh AG-SQ-THAILAND
# chat tay:
bash scripts/agent-chat.sh AG-SQ-THAILAND "bạn làm được gì"
```

## Console

`https://app.34-126-154-135.sslip.io/agent/AG-SQ-THAILAND` — chat thử, jobs/DLQ, traces,
chi phí, brain, version. Không cần tài khoản Vercel/Supabase.
