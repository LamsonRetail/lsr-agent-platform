# TEAM — cách 3 người cùng code mà KHÔNG đụng platform

Áp dụng cho: **Thi (owner)** · **Hương** · **Thái**.

## Nguyên tắc số 1

> Mọi thay đổi của dự án này nằm gọn trong `agents/AG-SQ-THAILAND/`
> (và `apps/agents/AG-SQ-THAILAND/` nếu sau này cần backend riêng — hiện KHÔNG cần).
> **Không sửa bất kỳ file nào khác** của repo: `infra/`, `src/`, `scripts/`, `plugins/`,
> `apps/platform-web/`, `.github/`, `tests/`, `docs/`, agent khác, file .md ở gốc.

Cần platform đổi gì (mở đường tải file, gán ingress, cấp token...) → **mở issue**, gắn
nhãn `agent:AG-SQ-THAILAND`, maintainer (`ntranthi`) xử lý. Xem [PLAN.md](PLAN.md) §4.

## Mô hình cộng tác: BRANCH CHUNG trên repo gốc

Thành viên team có quyền **write** trên `LamsonRetail/lsr-agent-platform` → clone thẳng,
cùng push lên **branch của dự án** `agent/thailand-AG-SQ-THAILAND`. **Không commit thẳng
main** — xong việc thì mở PR.

```bash
# 1. Clone repo gốc:
git clone https://github.com/LamsonRetail/lsr-agent-platform.git
cd lsr-agent-platform

# 2. BẮT BUỘC ngay sau clone — cài hook chặn commit chạm core:
bash scripts/install-git-hooks.sh

# 3. Làm việc trên branch của dự án (cả team dùng chung):
git checkout agent/thailand-AG-SQ-THAILAND
git pull

# 4. Trước khi push, tự kiểm phạm vi:
bash scripts/check-scope.sh --vs-main

# 5. Push lên branch dự án (KHÔNG push main):
git push origin agent/thailand-AG-SQ-THAILAND

# 6. Khi muốn merge vào bản stable → mở PR:
gh pr create --base main
```

Khi PR mở, CI chạy 2 gate của platform:
- **scope-guard** — fail nếu PR chạm file ngoài `agents/<id>/**`, `apps/agents/<id>/**`;
- **agent-gate** — fail nếu có code mà thiếu `USECASE.md`/`TESTCASES.md` (đã có sẵn).

> ⚠️ Repo private + org Free ⇒ **không có branch protection**: quyền write về kỹ thuật
> push được cả vào `main` và file core. Vì vậy kỷ luật bắt buộc: (1) cài pre-commit hook
> ở bước 2 — commit chạm core bị chặn ngay tại máy; (2) mọi thay đổi vào `main` đi qua
> PR để CI scope-guard kiểm. Push nhầm main/core = revert + nhắc nhở.

Cập nhật bản mới nhất từ main vào branch dự án:
```bash
git fetch origin && git merge origin/main
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
