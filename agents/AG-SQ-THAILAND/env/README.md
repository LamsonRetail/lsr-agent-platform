# env/ — nơi đặt khoá truy cập dữ liệu (KHÔNG lên git)

`.gitignore` của repo đã chặn `env/*.json` và `env/*.env`. Chỉ 2 file mẫu
(`*.example`) được commit. Đừng dán nội dung khoá vào chat, Lark hay code.

## BigQuery (project `surya-495408`)

1. Đặt file service-account JSON vào đây, đúng tên:

       env/bq-service-account.json

   Service account cần 2 role trên project: **BigQuery Data Viewer** +
   **BigQuery Job User**. Ploy chỉ ĐỌC — `bq.py` chặn mọi câu SQL không phải SELECT.

2. Khai đường dẫn trong `.env` của agent (cùng thư mục agent):

       GOOGLE_CLOUD_PROJECT=surya-495408
       GOOGLE_APPLICATION_CREDENTIALS=env/bq-service-account.json

   Đường dẫn tương đối được tính từ thư mục agent; dùng đường dẫn tuyệt đối cũng được.

3. Kiểm tra:

       python3 bq.py --datasets          # liệt kê dataset thấy được
       python3 bq.py --tables <dataset>  # liệt kê bảng
       python3 bq.py --sql "SELECT 1"    # chạy thử 1 câu

## Vì sao không dùng connector BigQuery của Claude.ai

Connector đó gắn với tài khoản người dùng trên claude.ai, không dùng được trong
consumer chạy nền. Service account là đường duy nhất để agent tự tra số 24/7.
