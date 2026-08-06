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
1. `vercel` (link project) → set env `LSR_PLATFORM_URL`, `LSR_COLLECTOR`,
   `PLATFORM_ADMIN_TOKEN` trong Project Settings.
2. **Vercel cloud KHÔNG tới được 127.0.0.1 của VM** → Platform API phải có
   **URL công khai** (Caddy+HTTPS+domain, hoặc tunnel như ngrok). Đặt
   `LSR_PLATFORM_URL`/`LSR_COLLECTOR` là URL công khai đó.

## Trang
- `/` — Platform dashboard (agents, token/runs, Activate/Deactivate).
- `/test-learn` — Test & Learn (sinh test auto, Duyệt→active, Giao bài, kết quả,
  import training).
