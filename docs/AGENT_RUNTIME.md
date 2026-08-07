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

**Cách owner token lên VM — 2 lựa chọn (cần chốt):**
1. **Qua platform (self-service):** endpoint `POST /v1/self/deploy` (auth = agent token) nhận
   `oauth_token` (owner dán token `claude setup-token`) + tham chiếu code (repo). Platform
   (có quyền VM) tạo service, lưu token vào `/opt/lsr-agents/<id>/.env` (chmod 600, ngoài git).
   → Owner không cần SSH. Token subscription đi qua platform (platform là control point).
2. **Admin provisioning:** owner gửi token cho admin qua kênh an toàn; admin chạy script
   `provision-agent-vm.sh <id>` (SSH sẵn) đặt token + dựng service. Kín hơn nhưng thủ công.

**Bảo mật bắt buộc:**
- Token subscription là secret → `.env` root-only, KHÔNG commit, KHÔNG log; xoay khi owner đổi.
- Cô lập tài nguyên per-agent (VM dùng chung với app khác ở port 3000/8080 — không được đụng).
- De/activate agent → dừng/khởi động service tương ứng (đã có kill-switch collector; thêm
  dừng process).
- Ghi audit khi deploy/dừng agent.

## Việc cần làm (khi chốt)
- [ ] Script/endpoint provisioning (chọn cách 1 hoặc 2).
- [ ] Template service (docker-compose fragment) cho agent + giới hạn tài nguyên.
- [ ] Nối de/activate ⇄ start/stop service.
- [ ] Cập nhật onboard: sau enroll → deploy runtime lên VM; Vercel chỉ cho FE/BE.
