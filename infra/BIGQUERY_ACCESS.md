# Cấp quyền BigQuery cho `bq_sink` (đẩy dữ liệu sang `AI_DB`)

Service `bq_sink` đã chạy trên VM nhưng **chưa ghi được** vào BigQuery.

**Nguyên nhân:** service account của VM (`927618081466-compute@developer.gserviceaccount.com`)
có `roles/editor` (đủ quyền IAM) nhưng **scope của instance thiếu BigQuery**:
```
Request had insufficient authentication scopes.
```
Scope là giới hạn ở tầng VM, IAM không ghi đè được → phải xử lý bằng 1 trong 2 cách.

---

## Cách 1 — Thêm scope cho VM (khuyến nghị nếu chấp nhận downtime ngắn)

> ⚠️ **Phải STOP/START VM (~1–2 phút)**. VM này còn chạy **app khác của công ty ở
> port 3000 và 8080** → những app đó cũng gián đoạn. Chọn giờ thấp điểm.

```bash
gcloud compute instances stop digital-transformation-hosting \
  --zone asia-southeast1-b --project ganesha-381907

gcloud compute instances set-service-account digital-transformation-hosting \
  --zone asia-southeast1-b --project ganesha-381907 \
  --service-account 927618081466-compute@developer.gserviceaccount.com \
  --scopes cloud-platform

gcloud compute instances start digital-transformation-hosting \
  --zone asia-southeast1-b --project ganesha-381907
```

Sau khi VM lên (docker `restart: unless-stopped` tự bật lại toàn bộ stack):
```bash
ssh lsr-gcp 'cd /opt/lsr-platform && sudo docker compose ps'
ssh lsr-gcp 'sudo docker logs lsr-platform-bq_sink-1 --tail 20'   # phải thấy "Sink xong: ..."
```

**Ưu:** không sinh file khoá, quản lý bằng IAM. **Nhược:** có downtime; scope
`cloud-platform` là rộng (mọi API Google mà IAM cho phép).

---

## Cách 2 — Service Account key (không cần restart)

Tạo SA riêng chỉ có quyền ghi BigQuery, gắn file key vào container `bq_sink`.

```bash
PROJECT=ganesha-381907
SA=lsr-bq-sink

# 1. Tạo service account riêng
gcloud iam service-accounts create $SA \
  --display-name "LSR BigQuery sink" --project $PROJECT

# 2. Chỉ cấp quyền ghi dữ liệu + chạy job (tối thiểu cần thiết)
for ROLE in roles/bigquery.dataEditor roles/bigquery.jobUser; do
  gcloud projects add-iam-policy-binding $PROJECT \
    --member "serviceAccount:$SA@$PROJECT.iam.gserviceaccount.com" \
    --role $ROLE --condition=None >/dev/null
done

# 3. Tạo key JSON (đây là SECRET — không commit, không gửi qua chat)
gcloud iam service-accounts keys create /tmp/bq-sa.json \
  --iam-account $SA@$PROJECT.iam.gserviceaccount.com --project $PROJECT

# 4. Đưa lên VM (chỉ root/owner đọc được)
ssh lsr-gcp 'mkdir -p /opt/lsr-platform/secrets && chmod 700 /opt/lsr-platform/secrets'
scp /tmp/bq-sa.json lsr-gcp:/opt/lsr-platform/secrets/bq-sa.json
ssh lsr-gcp 'chmod 600 /opt/lsr-platform/secrets/bq-sa.json'
rm -f /tmp/bq-sa.json      # xoá bản local
```

Bật mount trong `infra/lsr-platform/docker-compose.yml` (đang comment sẵn ở service
`bq_sink`) rồi commit — CI sẽ deploy:
```yaml
      GOOGLE_APPLICATION_CREDENTIALS: /secrets/bq-sa.json
    volumes:
      - ./secrets/bq-sa.json:/secrets/bq-sa.json:ro
```
```bash
ssh lsr-gcp 'cd /opt/lsr-platform && sudo docker compose up -d bq_sink'
ssh lsr-gcp 'sudo docker logs lsr-platform-bq_sink-1 --tail 20'
```

**Ưu:** không downtime, quyền tối thiểu (chỉ BigQuery). **Nhược:** sinh file khoá
lâu dài phải bảo quản; nên xoay khoá định kỳ (`gcloud iam service-accounts keys list/delete`).

> `secrets/` đã nằm ngoài rsync của CI (`--exclude='.env'` + thư mục secrets do bạn
> tạo trên VM), nên key **không bị ghi đè hay lọt vào git**.

---

## Kiểm tra sau khi cấp quyền (cách nào cũng vậy)

```bash
# log sink
ssh lsr-gcp 'sudo docker logs lsr-platform-bq_sink-1 --tail 20'

# bảng đã tạo trong AI_DB chưa
bq ls --project_id=ganesha-381907 AI_DB

# dữ liệu đã sang chưa
bq query --use_legacy_sql=false \
  'SELECT COUNT(*) AS rows FROM `ganesha-381907.AI_DB.agent_traces`'
```
Kỳ vọng: log `Sink xong: {'teams':…, 'candidates':…}` hoặc `Sink xong: N traces, M attempts`,
và `AI_DB` xuất hiện 2 bảng `agent_traces`, `attempts` (sink chạy mỗi 15 phút).

---

## So sánh nhanh

| | Cách 1 — scope VM | Cách 2 — SA key |
|---|---|---|
| Downtime | **có** (~1–2 phút, ảnh hưởng cả app 3000/8080) | không |
| Quyền | rộng (`cloud-platform`) | tối thiểu (BigQuery) |
| Quản lý khoá | không có file khoá | có file khoá, cần xoay định kỳ |
| Ai chạy được | cần quyền compute admin | cần quyền tạo SA + key |
