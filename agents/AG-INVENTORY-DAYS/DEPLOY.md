# Deploy bot ANN_KHHH lên VM (chạy 24/7)

Bot đang chạy bằng `run_bot.bat` trên máy cá nhân — tắt máy là bot chết. Dưới đây
là cách đưa lên VM dùng chung của công ty (đã có Docker, xem `infra/DEPLOY.md`).

| | |
|---|---|
| VM | `digital-transformation-hosting` · `34.126.154.135` |
| Zone / Project | `asia-southeast1-b` · `ganesha-381907` |
| SSH | `ssh lsr-gcp` (alias có sẵn) hoặc `ssh -i ~/.ssh/lsr-deploy ntranthi@34.126.154.135` |
| Cổng | Bot **không mở port nào** — chỉ gọi ra ngoài tới Lark. Không đụng port 3000/8080 đang có service khác. |
| Tài nguyên | ~80 MB RAM, CPU gần như 0 (poll 3s, 1 request nhỏ) |

## Deploy lần đầu

```bash
ssh lsr-gcp

git clone https://github.com/LamsonRetail/lsr-agent-platform.git   # hoặc git pull nếu đã có
cd lsr-agent-platform/agents/AG-INVENTORY-DAYS

# Secret — KHÔNG commit file này.
cat > .env <<'EOF'
LARK_APP_ID_INVENTORY=cli_aaf6d3a61078ded4
LARK_APP_SECRET_INVENTORY=<dán secret>
# CHAT_IDS để trống = phục vụ mọi nhóm bot được add vào.
CHAT_IDS=
DRY_RUN=true
EOF
chmod 600 .env

docker compose up -d --build
docker compose logs -f
```

Log phải có 3 dòng:

```
Đã nạp Code of Conduct KHHH: 75 mục.
Trả lời khi được @PLANNING' ASSISTANT, hoặc khi có câu hỏi mà tra ra được đáp án chắc chắn.
Bắt đầu poll mỗi 3.0s (DRY_RUN=True) — N nhóm: <tên các nhóm>
```

`DRY_RUN=true` nghĩa là bot **chỉ in ra log** câu sẽ trả lời, không gửi vào nhóm.
Gõ vài câu vào nhóm, xem log thấy trả lời đúng thì mới bật thật:

```bash
sed -i 's/DRY_RUN=true/DRY_RUN=false/' .env
docker compose up -d          # tự tạo lại container với env mới
```

## Vận hành

```bash
docker compose logs -f --tail 50     # xem log
docker compose restart               # restart
docker compose down                  # tắt bot
docker compose up -d --build         # cập nhật sau khi git pull
docker stats ann-khhh                # xem RAM/CPU
```

`restart: unless-stopped` → VM reboot bot tự lên lại. Chỉ khi chạy `docker compose
down` thì nó mới nằm im.

## Đổi cấu hình

Sửa `.env` rồi `docker compose up -d`:

| Biến | Ý nghĩa |
|---|---|
| `CHAT_IDS` | Nhóm bot phục vụ, cách nhau bởi dấu phẩy. **Bỏ trống = mọi nhóm bot được add vào** |
| `DRY_RUN` | `true` = chỉ log, không gửi. Luôn dùng `true` khi thử nghiệm |
| `EXCEL_PATH` | Trỏ tới file tồn kho *(phải mount volume vào container)*. Bỏ trống = chỉ trả lời câu hỏi quy trình |
| `ANSWER_ALL` | `true` = trả lời mọi tin, không cần @mention. Chỉ dùng ở nhóm test |
| `POLL_INTERVAL` | Giây giữa 2 lần kiểm tra tin mới. Mặc định 3 |

## Cập nhật Code of Conduct

Tài liệu được **build vào image**, nên sửa xong phải build lại:

```bash
git pull && docker compose up -d --build
```

## Điều còn thiếu

- **Tồn kho**: hiện đọc file Excel. Muốn dùng trên VM phải mount volume, hoặc tốt
  hơn là chuyển sang đọc BigQuery (`skills: bigquery` đã khai trong
  `lsr-agent.yaml` nhưng chưa nối).
- **Poll, chưa dùng event.** Đang gọi API mỗi 3s. Khi bật được event
  `im.message.receive_v1` trên Developer Console thì chuyển sang `src/bot.py`
  (long connection) — phản hồi tức thì và nhẹ hơn.
- **Chưa có alert khi bot chết.** Container `restart: unless-stopped` xử lý được
  crash, nhưng nếu app_secret bị đổi thì bot sẽ crash-loop im lặng. Nên thêm
  healthcheck báo về `collector.lsr.internal`.
