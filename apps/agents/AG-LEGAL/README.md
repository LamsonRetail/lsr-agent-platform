# Agent backend · AG-LEGAL (`AG-LEGAL`)
Backend riêng của agent, nằm chung monorepo. Deploy:
- **Vercel:** project riêng, Root Directory = `apps/agents/AG-LEGAL`, set env (xem .env.example).
- **Self-host:** thêm service vào infra docker-compose trỏ build tới thư mục này.
Chạy dev: `cp .env.example .env.local && npm install && npm run dev`.
