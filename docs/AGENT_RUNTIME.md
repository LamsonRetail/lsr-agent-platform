# Nơi agent chạy — mô hình runtime

## Chuẩn (chốt)
- **Agent runtime = tiến trình Claude Agent SDK, chạy trên GCP VM của platform.**
  Xác thực bằng **subscription của OWNER**: owner chạy `claude setup-token` → token đặt vào
  biến `CLAUDE_CODE_OAUTH_TOKEN` cho tiến trình agent (KHÔNG dùng API key, KHÔNG auth chung).
- **Vercel = chỉ front-end + backend** (dashboard/config/chi tiết của agent). Backend đọc dữ
  liệu qua API agent-scoped `/v1/self*` bằng `LSR_AGENT_TOKEN`.
- **Telemetry + enforcement**: plugin `lsr-telemetry` bật trong runtime trên VM → mọi tool
  call/token về collector; hook `PreToolUse`/`UserPromptSubmit` gọi Policy API.

```
Owner subscription (setup-token)
        │  CLAUDE_CODE_OAUTH_TOKEN
        ▼
GCP VM  ├─ /opt/lsr-agents/<id>/  ── tiến trình agent (SDK) + plugin telemetry
        │        │ trace/policy
        │        ▼
        └─ collector / platform_api (control point)  ◄── Vercel FE/BE gọi /v1/self*
```

## Hiện trạng
- VM đang chạy **platform core** (collector, platform_api, postgres, caddy, web, bq_sink, lsr_brain).
- **Chưa** có cơ chế host **agent runtime** per-owner trên VM. Đây là phần cần bổ sung.

## Đề xuất provisioning agent-on-VM
Mỗi agent = 1 **service cô lập** trên VM: thư mục `/opt/lsr-agents/<id>/` + `.env` (root-only)
chứa `CLAUDE_CODE_OAUTH_TOKEN` (của owner), `LSR_AGENT_ID`, `LSR_COLLECTOR`,
`LSR_TELEMETRY_API_KEY`, và code/lệnh chạy agent. Chạy bằng docker-compose service riêng
(hoặc systemd), `restart: unless-stopped`, có giới hạn tài nguyên (CPU/RAM) để không ảnh
hưởng app khác trên VM dùng chung.

## Đã chốt (thiết kế ít-đổi-khi-scale)
- **Self-service qua platform:** `POST /v1/self/deploy` (auth = agent token) nhận `oauth_token`
  (owner dán từ `claude setup-token`) + repo/start_cmd tuỳ chọn → platform chạy **1 container/agent**.
- **Docker per-agent** với giới hạn CPU/RAM, `restart: unless-stopped`, network nội bộ.
- **Trừu tượng hoá nơi chạy = `DockerClient(base_url=host)`:**
  - **GĐ này (1 VM chung):** host = **docker-socket-proxy** (`tcp://docker_proxy:2375`) — platform_api
    KHÔNG mount socket thẳng; proxy chỉ mở quyền CONTAINER/IMAGE/NETWORK + POST. Giảm blast radius.
  - **Tương lai (agent/VM riêng):** đặt cột `agents.runtime_host` = daemon của VM đó
    (`tcp://vm-x:2376` TLS). **KHÔNG đổi code** — cùng `_docker_client(agent_id)`.
- **De/activate ⇄ stop/start** container tương ứng (nối trong `set_status`).
- Token subscription truyền thẳng vào container qua daemon (không ghi file host → thân thiện đa-VM);
  KHÔNG log. Xoay khi owner đổi.

## Đường nâng cấp lên nhiều VM (khi cần) — chỉ config, không sửa code
1. Dựng VM agent mới, chạy Docker + **docker-socket-proxy** (hoặc daemon TLS) trên đó.
2. Set `agents.runtime_host` cho các agent muốn chuyển → lần deploy sau chạy trên VM mới.
3. (tuỳ chọn) Cân bằng tải: gán runtime_host theo squad/nhóm.

## Bảo mật
- Socket Docker chỉ vào **proxy** (quyền hạn chế), không vào API web-facing.
- VM chung với app khác (port 3000/8080) — giới hạn tài nguyên per-agent, không đụng.
- Ghi audit khi deploy/dừng agent (`deploy_vm`, `set_status.vm`).

## Việc còn lại
- [ ] Cập nhật onboard: sau enroll → gọi `/v1/self/deploy` (owner dán setup-token).
- [ ] (tương lai) UI đặt `runtime_host` per-agent khi tách VM.
