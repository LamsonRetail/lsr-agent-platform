# Image chạy AGENT trên VM bằng subscription của OWNER (CLAUDE_CODE_OAUTH_TOKEN).
# Plugin telemetry được bake sẵn (control point). Một container / agent.
FROM node:20-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 git ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && ln -sf /usr/bin/python3 /usr/local/bin/python3

# Claude Code CLI (Agent SDK) — agent xác thực bằng token subscription của owner.
RUN npm install -g @anthropic-ai/claude-code || true

# Bake plugin telemetry (CI copy plugins/lsr-telemetry -> ./plugin trước khi build)
COPY plugin /opt/lsr-telemetry
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /agent
ENTRYPOINT ["/entrypoint.sh"]
