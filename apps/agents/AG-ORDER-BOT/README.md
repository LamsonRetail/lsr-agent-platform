# Agent backend · Order Lookup Bot (`AG-ORDER-BOT`)
Backend riêng của agent, nằm chung monorepo. Deploy:
- **Vercel:** project riêng, Root Directory = `apps/agents/AG-ORDER-BOT`, set env (xem .env.example).
- **Self-host:** thêm service vào infra docker-compose trỏ build tới thư mục này.
Chạy dev: `cp .env.example .env.local && npm install && npm run dev`.
