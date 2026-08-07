# Agent backends (sub-folder trong monorepo)

Backend riêng của **từng agent** nằm ở đây: `apps/agents/<agent-id>/` — chung repo
với platform, deploy cùng một nơi.

## Tạo backend cho một agent
```bash
node scripts/new-agent-backend.mjs AG-ORDER-BOT "Order Lookup Bot"
cd apps/agents/AG-ORDER-BOT && npm install && npm run build
```
Sinh ra 1 Next.js app nhỏ: server-side gọi Platform API theo `AGENT_ID`, hiển thị
config/usage/kết quả làm bài của riêng agent đó.

## Deploy
- **Vercel:** tạo project riêng cho agent, **Root Directory = `apps/agents/<id>`**,
  set env (`AGENT_ID`, `LSR_PLATFORM_URL`, `LSR_COLLECTOR`, `PLATFORM_ADMIN_TOKEN`,
  `LSR_GATEWAY_TOKEN`). Auto-deploy khi push (giống platform-web).
- **Self-host:** thêm service vào `infra/lsr-platform/docker-compose.yml` build từ
  thư mục agent + route Caddy `agent-<id>.34-126-154-135.sslip.io`.

## Nguyên tắc
- Mọi agent-backend đọc/ghi qua **Platform API + collector** (không có DB riêng cục bộ).
- Bộ nhớ/DB của agent nằm trên **Supabase chung**, mỗi agent một **schema (dataset)
  riêng** — xem `infra/DEPLOY.md` mục Supabase.
