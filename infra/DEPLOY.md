# Hạ tầng & Deploy — LSR Agent Platform

Backend platform (LLM Gateway, Collector, Platform API, Scorer/Dashboard) chạy
trên **Google Cloud Compute Engine**.

## VM mục tiêu

| Thuộc tính | Giá trị |
|-----------|---------|
| Project | `ganesha-381907` |
| Zone | `asia-southeast1-b` |
| Instance | `digital-transformation-hosting` |
| Console | https://console.cloud.google.com/compute/instancesDetail/zones/asia-southeast1-b/instances/digital-transformation-hosting?project=ganesha-381907 |

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

> **Chưa kết nối được từ máy này** vì `gcloud` chưa cài và chưa đăng nhập GCP
> (cần OAuth tương tác). Chọn 1 trong 2 đường dưới để hoàn tất.

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

## Điều tôi cần để tự chạy tiếp giúp bạn

- Cài `gcloud` + `gcloud auth login` (đường tương tác — bạn chạy), **hoặc**
- Cung cấp **external IP** sau khi đã thêm deploy key vào metadata (Cách B).

Sau khi SSH thông, bước tiếp là bố trí các service trên VM (xem dưới).

## Bố trí service trên VM (dự kiến)

| Service | Vai trò | Port (nội bộ) |
|---------|---------|---------------|
| LiteLLM Gateway | proxy model, virtual key, budget, kill switch | 4000 |
| Collector API | nhận trace từ Telemetry SDK | 8081 |
| Platform API | đăng ký agent, cấp key, Lark connect | 8080 |
| Scorer/Dashboard | chấm điểm + phục vụ dashboard | 8082 |

Reverse proxy (Caddy/Nginx) + TLS phía trước; tên nội bộ `gateway.lsr.internal`,
`collector.lsr.internal` map vào VM. Chi tiết hoá khi bắt đầu Giai đoạn 1.
