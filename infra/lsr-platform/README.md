# LSR Platform stack (Giai đoạn 1)

Postgres + **LiteLLM Gateway** (virtual key + budget + kill switch) + **Collector**
(nhận trace từ Telemetry SDK). Triển khai trong `/opt/lsr-platform` trên VM GCP.

## Deploy

```bash
cd /opt/lsr-platform
cp .env.example .env        # điền secrets, dán ANTHROPIC_API_KEY thật
docker compose up -d --build
```

Ports (chỉ localhost VM): LiteLLM `127.0.0.1:4000`, Collector `127.0.0.1:8081`.
Công khai ra ngoài qua Caddy/HTTPS (bước sau).

## Kiểm tra

```bash
curl -s localhost:8081/health
curl -s localhost:4000/health/readiness            # LiteLLM
curl -s localhost:4000/v1/models -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

## Cấp virtual key cho một agent (kill switch = revoke key)

```bash
# Cấp key + budget (vd 5 USD)
curl -s localhost:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"key_alias":"AG-ORDER-BOT","max_budget":5,"models":["*"]}'

# Deactivate: revoke key
curl -s localhost:4000/key/delete \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"keys":["sk-...virtual..."]}'
```

Agent cấu hình: `ANTHROPIC_BASE_URL=https://gateway.lsr.internal`,
`ANTHROPIC_API_KEY=<virtual key>`.
