# LSR Platform Web (Next.js / Vercel)

App web thật thay prototype: server components đọc **dữ liệu live** từ Platform API
+ Collector; các nút (**Duyệt / Giao bài / Import / Activate-Deactivate / Sinh test**)
gọi Platform API **qua route server-side** — admin token KHÔNG lộ ra client.

## Cấu hình (env server-side)
```
LSR_PLATFORM_URL=...      # URL Platform API (reachable từ nơi chạy web)
LSR_COLLECTOR=...         # URL Collector
PLATFORM_ADMIN_TOKEN=...  # token admin (chỉ ở server)
```

## Chạy local (dev) tới API thật trên VM
Platform API/Collector bind 127.0.0.1 trên VM → mở SSH tunnel:
```bash
ssh -L 8090:localhost:8090 -L 8081:localhost:8081 lsr-gcp -N &
cp .env.example .env.local   # điền PLATFORM_ADMIN_TOKEN (lấy từ .env trên VM)
npm install && npm run dev   # http://localhost:3000
```

## Deploy Vercel

> ⚠️ **Lỗi "No python entrypoint found":** repo là monorepo có Python ở gốc; app
> Next.js nằm trong `apps/platform-web`. Trong Vercel **Project Settings → General
> → Root Directory** đặt **`apps/platform-web`**. Vercel sẽ nhận đúng Next.js,
> bỏ qua phần Python. (Hoặc khi import: chọn Root Directory = apps/platform-web.)

**Env (Project Settings → Environment Variables):**
| Biến | Giá trị |
|------|---------|
| `LSR_PLATFORM_URL` | `https://platform.34-126-154-135.sslip.io` (public qua Caddy) |
| `LSR_COLLECTOR` | `https://collector.34-126-154-135.sslip.io` |
| `PLATFORM_ADMIN_TOKEN` | (lấy từ `.env` trên VM) |
| `LSR_GATEWAY_TOKEN` | (lấy từ `.env` trên VM — Caddy yêu cầu header này) |

**Vercel cloud KHÔNG tới được 127.0.0.1 của VM** → dùng URL public qua Caddy ở trên
(đã dựng: HTTPS tự động + gateway token). Xem [../infra/DEPLOY.md](../../infra/DEPLOY.md).

## Trang
- `/` — Platform dashboard (agents, token/runs, Activate/Deactivate).
- `/test-learn` — Test & Learn (sinh test auto, Duyệt→active, Giao bài, kết quả,
  import training).
