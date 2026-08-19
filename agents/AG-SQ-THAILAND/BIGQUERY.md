# BigQuery cho Ploy — cách cấp quyền

Khoá đặt trong thư mục `env/` của agent. `.gitignore` gốc của repo đã chặn sẵn mọi
thư mục tên `env/` → khoá KHÔNG bao giờ lên git (đã kiểm bằng `git check-ignore`).
Chính vì cả thư mục bị chặn nên tài liệu này nằm ngoài, ở đây. Đừng dán nội dung khoá
vào chat, Lark hay code.

## BigQuery (project `surya-495408`)

1. Đặt file service-account JSON vào đây, đúng tên:

       env/bq-service-account.json

   Service account cần 2 role trên project: **BigQuery Data Viewer** +
   **BigQuery Job User**. Ploy chỉ ĐỌC — `bq.py` chặn mọi câu SQL không phải SELECT.

2. Khai đường dẫn trong `.env` của agent (mẫu có trong `.env.example`):

       GOOGLE_CLOUD_PROJECT=surya-495408
       GOOGLE_APPLICATION_CREDENTIALS=env/bq-service-account.json

   Đường dẫn tương đối được tính từ thư mục agent; dùng đường dẫn tuyệt đối cũng được.

3. Kiểm tra:

       python3 bq.py --datasets          # liệt kê dataset thấy được
       python3 bq.py --tables <dataset>  # liệt kê bảng
       python3 bq.py --schema 01_hptl_report.hptl_pnl_dashboard
       python3 bq.py --sql "SELECT 1"    # chạy thử 1 câu
       python3 tests/check_bq.py         # bộ kiểm đầy đủ

## Vì sao không dùng connector BigQuery của Claude.ai

Connector đó gắn với tài khoản người dùng trên claude.ai, không dùng được trong
consumer chạy nền. Service account là đường duy nhất để agent tự tra số 24/7.

## Dữ liệu Thái Lan nằm ở đâu (dò ngày 19/08/2026)

| Nguồn | Dùng cho |
|---|---|
| `01_hptl_report.hptl_pnl_dashboard` | GMV/DT thuần/đơn/hoàn theo ngày·kênh·kho, brand `HPTH` — **nguồn chính của Ploy** |
| `01_hptl_report.hptl_inventory` · `hptl_inventory_control_sku` | tồn kho TH |
| `00_serving_sales.vw_business_daily` | bản dùng chung toàn tập đoàn (Ploy không cần) |
| `10_lsr.fact_target_detail` | target — **chưa có HPTH**, chỉ MMVN/HPVN |

Hai chỗ DB không trả lời được, đã ghi trong `configs/th_bq.json`:
1. **LNĐG**: `ads_cost_branding` và `operation_cost` của HPTH đang NULL 100% → không tính
   được lãi từ DB; số LNĐG vẫn là số người nhập trong `th_numbers_snapshot`.
2. **Target TH**: không có trong DB → lấy từ `th_base_targets`.

DB quy hết về **VND**. Muốn Ploy trả lời bằng THB thì điền `ty_gia_thb_vnd` trong
`configs/th_bq.json`; chưa điền thì Ploy trả lời bằng VND và nói rõ là chưa quy đổi.

## Thêm một câu hỏi mới cho Ploy

Thêm một mục vào `cac_truy_van` của `configs/th_bq.json` (SQL phải là SELECT), thêm từ khoá
nhận câu hỏi trong `th_bq_sales()` của `thailand_tools.py`, rồi chạy `tests/check_bq.py`.
Ploy **không** tự viết SQL từ câu chat — một tin nhắn cài chỉ thị trong nhóm là đủ để lấy
dữ liệu ngoài phạm vi hoặc bắt DB quét cả kho.
