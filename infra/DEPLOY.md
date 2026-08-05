# Hạ tầng & Deploy — LSR Agent Platform

Backend platform (LLM Gateway, Collector, Platform API, Scorer/Dashboard) chạy
trên **Google Cloud Compute Engine**.

## VM mục tiêu ✅ ĐÃ KẾT NỐI

| Thuộc tính | Giá trị |
|-----------|---------|
| Project | `ganesha-381907` |
| Zone | `asia-southeast1-b` |
| Instance | `digital-transformation-hosting` |
| External IP | `34.126.154.135` |
| Máy | n2-standard-2 · 2 vCPU · 7.8Gi RAM · disk 49G (dùng ~64%) |
| OS | Ubuntu 22.04.5 LTS |
| Runtime sẵn | Docker 29.1.3 · Python 3.10.12 (chưa có node, nginx) |
| SSH user | `ntranthi` (sudo không cần mật khẩu) |
| Console | https://console.cloud.google.com/compute/instancesDetail/zones/asia-southeast1-b/instances/digital-transformation-hosting?project=ganesha-381907 |

> ⚠️ VM **dùng chung** — đang có service chạy ở **port 3000 và 8080** (không được
> đụng). Platform sẽ dùng port khác (xem bảng bố trí service).

### Kết nối nhanh
Đã cấu hình alias trong `~/.ssh/config`:
```bash
ssh lsr-gcp
```
(tương đương `ssh -i ~/.ssh/lsr-deploy ntranthi@34.126.154.135`). Deploy key đã
được thêm vào metadata của VM và xác nhận hoạt động (cả `gcloud compute ssh` lẫn
`ssh` trực tiếp).

## SSH

Đã tạo **deploy key riêng** cho platform (không dùng chung key cá nhân):
```
~/.ssh/lsr-deploy        (private)
~/.ssh/lsr-deploy.pub     (public — thêm vào VM)
```

Public key:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIG858TwCYFoh8+iEFAxX268v9miE7O455rLLDAhtkUDR lsr-agent-platform-deploy@ganesha-381907
```

> ✅ Đã kết nối thành công (xem "Kết nối nhanh" ở trên). Hai cách bên dưới giữ lại
> để tham khảo / máy khác.

### Cách A — gcloud tự quản lý key (khuyến nghị)

```bash
# 1. Cài Google Cloud SDK (macOS)
brew install --cask google-cloud-sdk

# 2. Đăng nhập + chọn project
gcloud auth login
gcloud config set project ganesha-381907

# 3. SSH (gcloud tự đẩy key vào metadata)
gcloud compute ssh digital-transformation-hosting \
  --zone asia-southeast1-b --project ganesha-381907 \
  --ssh-key-file ~/.ssh/lsr-deploy
```

### Cách B — SSH trực tiếp bằng deploy key

1. Thêm public key vào **metadata** của VM (Console → VM → *Edit* → *SSH Keys* →
   *Add item*, dán dòng public key ở trên), hoặc bằng gcloud:
   ```bash
   gcloud compute instances add-metadata digital-transformation-hosting \
     --zone asia-southeast1-b --project ganesha-381907 \
     --metadata-from-file ssh-keys=<(echo "ntranthi:$(cat ~/.ssh/lsr-deploy.pub)")
   ```
   > Username trước dấu `:` (vd `ntranthi`) chính là user sẽ SSH.
2. Lấy **external IP** (Console hoặc `gcloud compute instances describe ...
   --format='get(networkInterfaces[0].accessConfigs[0].natIP)'`).
3. Đảm bảo firewall mở `tcp:22` từ IP của bạn.
4. Kết nối:
   ```bash
   ssh -i ~/.ssh/lsr-deploy ntranthi@<EXTERNAL_IP>
   ```

### SSH config alias (tuỳ chọn)

Thêm vào `~/.ssh/config` (điền IP sau khi có):
```
Host lsr-gcp
    HostName <EXTERNAL_IP>
    User ntranthi
    IdentityFile ~/.ssh/lsr-deploy
    IdentitiesOnly yes
```
Rồi chỉ cần: `ssh lsr-gcp`.

## Bố trí service trên VM (port đã né 3000/8080 đang bận)

| Service | Vai trò | Port (nội bộ) | Trạng thái |
|---------|---------|---------------|-----------|
| Postgres | lưu key/spend (LiteLLM) + trace (collector) | 5432 (nội bộ) | ✅ chạy |
| Collector API | nhận trace + resource index | 127.0.0.1:8081 | ✅ chạy (control point) |
| Platform API | register agent, cấp telemetry key, hook Minh Anh, active/deactivate | 127.0.0.1:8090 | ✅ chạy |
| LiteLLM Gateway | *optional* — chỉ cho agent dùng API key | 127.0.0.1:4000 | ⏸ tắt |
| Scorer/Dashboard | chấm điểm + phục vụ dashboard | 8082 | ⏳ chưa làm |

**Whisper Transcription Server** (ngoài, của Minh Anh): `https://slashingly-unexistent-hue.ngrok-free.dev`
— submit `/transcribe`, poll `/result/{job_id}`; `/health` = large-v3 trên CUDA. Client:
`rating_agent.meeting.TranscribeClient` (env `LSR_TRANSCRIBE_URL`).

Secret thêm: `PLATFORM_ADMIN_TOKEN` (bảo vệ register/status) — sinh ngẫu nhiên trong `.env`.

> **Auth model đã đổi:** agent dùng **subscription (Agent SDK), không API key** →
> **không cần** dán `ANTHROPIC_API_KEY`; LiteLLM gateway **hạ xuống optional** (giữ
> chạy để dành cho agent nào chọn API key, hoặc có thể tắt:
> `sudo docker compose stop litellm`). Control point chính là **Collector** (nhận
> trace từ plugin/SDK). Còn thiếu: Caddy + HTTPS để công khai `collector.lsr.internal`.

Chạy bằng **Docker** (đã có sẵn); reverse proxy (Caddy — tự lo TLS) phía trước,
map tên nội bộ `gateway.lsr.internal` / `collector.lsr.internal`. Cần mở firewall
GCP cho các port public (qua HTTPS 443 của Caddy là đủ, không mở thẳng 4000/808x).

> Vì VM dùng chung, khuyến nghị đặt toàn bộ stack platform trong thư mục riêng
> (vd `/opt/lsr-platform`) + `docker compose` riêng để không ảnh hưởng app hiện có.
