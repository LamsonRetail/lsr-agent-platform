# Quyền Data Warehouse (BigQuery) cho agent — opt-in, scoped

**Mặc định: agent KHÔNG cần và KHÔNG được cấp quyền BigQuery.** Analytics do platform lo:
service `bq_sink` đẩy `agent_traces` + `attempts` sang `ganesha-381907:AI_DB`. Dashboard/chi
tiết của agent đọc qua API agent-scoped (`/v1/self*`), không đụng BigQuery.

Chỉ cấp DWH khi agent **thực sự cần query dữ liệu phân tích**. Khi đó cấp **scoped tối thiểu**,
không đưa quyền rộng. Chạy bởi **GCP admin** (cần quyền IAM), không phải self-service.

## Cách 1 — Dataset + Service Account riêng cho agent (khuyến nghị)
Mỗi agent một dataset riêng + SA chỉ đọc/ghi dataset đó.
```bash
PROJECT=surya-495408                 # project chứa SA (theo cấu hình hiện tại)
AGENT=ag_salesbot                    # slug agent (chữ thường, gạch dưới)
DATASET=agent_${AGENT}

# 1) tạo dataset riêng cho agent (ở project data-warehouse)
bq --project_id=ganesha-381907 mk --dataset --description "DWH của agent ${AGENT}" ganesha-381907:${DATASET}

# 2) tạo SA riêng cho agent
gcloud iam service-accounts create dwh-${AGENT} --project $PROJECT \
  --display-name "DWH ${AGENT}"

# 3) chỉ cấp quyền trên DATASET đó (không cấp project-wide)
#    (grant ở mức dataset qua bq update ACL, không dùng project IAM rộng)
bq show --format=prettyjson ganesha-381907:${DATASET} > /tmp/ds.json
# thêm entry {"role":"WRITER","userByEmail":"dwh-${AGENT}@${PROJECT}.iam.gserviceaccount.com"} vào access[] rồi:
bq update --source /tmp/ds.json ganesha-381907:${DATASET}

# 4) tạo key JSON (SECRET — đưa cho owner qua kênh an toàn, KHÔNG commit)
gcloud iam service-accounts keys create /tmp/dwh-${AGENT}.json \
  --iam-account dwh-${AGENT}@${PROJECT}.iam.gserviceaccount.com --project $PROJECT
```
Owner đặt key vào backend agent (env `GOOGLE_APPLICATION_CREDENTIALS`) + `BQ_DATASET=${DATASET}`.

## Cách 2 — Endpoint truy vấn trung gian ở platform (không phát key)
Nếu không muốn phát key BigQuery ra ngoài: thêm endpoint `/v1/self/dwh/query` (agent-scoped)
ở platform, chạy query **chỉ trên dataset của agent** rồi trả kết quả. Platform giữ 1 SA,
agent không cầm key. An toàn hơn nhưng cần code thêm ở platform (chưa làm — mở khi có nhu cầu).

## Nguyên tắc
- Quyền tối thiểu, scoped theo dataset — không cấp project-wide/`roles/editor`.
- Key là secret: đưa qua password manager/kênh an toàn, không commit, xoay định kỳ.
- Ghi nhận cấp quyền vào audit (hành động thủ công của admin) để truy vết.
