# Rating Agent — LamsonRetail

Hệ thống agent nội bộ đánh giá nhân viên/agent của LamsonRetail dựa trên dữ liệu
làm việc thực tế trên **Lark** (chat, document, task) và **BigQuery** (data
warehouse vận hành kinh doanh).

Ba trục đánh giá:

- **Collaboration** — mức độ phối hợp với đồng đội.
- **Grow** — sự phát triển, học hỏi, cải thiện theo thời gian.
- **Performance** — hiệu quả công việc, kết quả kinh doanh.

---

## 1. Kiến trúc tổng thể

```
                        ┌────────────────────────────────────────────┐
                        │                Rating Agent                 │
                        └────────────────────────────────────────────┘
                                          │
        ┌─────────────────────────────────┼─────────────────────────────────┐
        │                                 │                                 │
┌───────▼────────┐              ┌─────────▼─────────┐              ┌────────▼────────┐
│  Nguồn dữ liệu  │              │     Pipeline      │              │     Đầu ra       │
├────────────────┤              ├───────────────────┤              ├─────────────────┤
│ Lark Chat       │──collect──►  │ 1. Thu thập        │──►           │ Bản đánh giá     │
│ Lark Document   │              │ 2. Chuẩn hoá       │              │ (per employee)   │
│ Lark Task       │              │ 3. Trích đặc trưng │              │ Xếp hạng (rank)  │
│ BigQuery DWH    │──query───►   │ 4. Tính điểm       │──►           │ Báo cáo/Export   │
└────────────────┘              │ 5. Tổng hợp báo cáo│              └─────────────────┘
                                └───────────────────┘
```

### Thành phần code

| Lớp | Module | Vai trò |
|-----|--------|---------|
| Cấu hình | `src/rating_agent/config.py` | Đọc biến môi trường, load config chấm điểm |
| Kết nối Lark | `src/rating_agent/lark/` | Client OAuth app + wrapper chat/doc/task |
| Kết nối BigQuery | `src/rating_agent/bq/` | Client + query builder + ví dụ query |
| Đánh giá | `src/rating_agent/evaluation/` | Data model, tiêu chí, hàm tính điểm |
| Điều phối | `src/rating_agent/pipeline.py` | Ghép nối thu thập → chấm điểm → báo cáo |

---

## 2. Các nguồn dữ liệu

### 2.1 Lark (Feishu/Lark Open Platform)

Dùng **Custom App** trong Lark Developer Console, xác thực bằng
`app_id` + `app_secret` → lấy `tenant_access_token`.

| Nguồn | API chính | Tín hiệu khai thác |
|-------|-----------|---------------------|
| **Chat** | `im/v1/chats`, `im/v1/messages` | tần suất trả lời, thời gian phản hồi, mức tham gia thảo luận, @mention, hỗ trợ đồng đội |
| **Document** | `docx/v1/documents`, `wiki/v2` | đóng góp tài liệu, đồng tác giả, review/comment |
| **Task** | `task/v2/tasks` | số task hoàn thành, đúng hạn, độ khó, phối hợp task chung |

Quyền (scopes) cần bật cho app: `im:message:readonly`, `im:chat:readonly`,
`docx:document:readonly`, `task:task:readonly`, `contact:user.base:readonly`.

> **Lưu ý riêng tư:** Agent chỉ đọc metadata và tín hiệu tổng hợp phục vụ đánh
> giá công việc. Việc bot tham gia/theo dõi nhóm chat cần được thông báo minh
> bạch tới nhân viên và tuân thủ chính sách nội bộ.

### 2.2 BigQuery Data Warehouse

Chứa dữ liệu vận hành kinh doanh (bán hàng, đơn, KPI theo nhân viên). Xác thực
bằng **Service Account** (JSON key) qua biến `GOOGLE_APPLICATION_CREDENTIALS`.

Ví dụ bảng giả định:
- `dwh.employees` — danh mục nhân viên (map `lark_user_id` ↔ `employee_id`).
- `dwh.sales_fact` — giao dịch bán hàng theo nhân viên/thời gian.
- `dwh.kpi_monthly` — KPI đã tổng hợp theo tháng.

---

## 3. Pipeline: thu thập → tính điểm → báo cáo

1. **Thu thập (collect)** — gọi Lark API + BigQuery, lấy dữ liệu theo kỳ đánh
   giá (ví dụ 1 tháng/quý).
2. **Chuẩn hoá (normalize)** — quy về `employee_id`, đơn vị thời gian thống nhất.
3. **Trích đặc trưng (features)** — tính các chỉ số thô cho từng trục.
4. **Tính điểm (score)** — áp trọng số theo `config/scoring_config.yaml`, chuẩn
   hoá về thang 0–100.
5. **Tổng hợp (report)** — sinh `EmployeeEvaluation` + bảng xếp hạng, export.

---

## 4. Tiêu chí chấm điểm đề xuất

Mỗi trục là trung bình có trọng số của các chỉ số con, chuẩn hoá 0–100.

### Collaboration (phối hợp)
| Chỉ số | Nguồn | Ý nghĩa |
|--------|-------|---------|
| response_rate | Lark chat | tỉ lệ phản hồi tin nhắn được @mention |
| avg_response_time | Lark chat | tốc độ phản hồi (điểm nghịch đảo) |
| cross_team_tasks | Lark task | số task phối hợp liên nhóm |
| doc_coauthor | Lark doc | số tài liệu đồng tác giả/comment hữu ích |

### Grow (phát triển)
| Chỉ số | Nguồn | Ý nghĩa |
|--------|-------|---------|
| skill_trend | BigQuery/Lark | xu hướng cải thiện KPI theo kỳ |
| task_complexity_up | Lark task | độ khó task tăng dần |
| learning_docs | Lark doc | tài liệu học tập/chia sẻ kiến thức tạo ra |
| feedback_adoption | Lark chat/task | mức độ tiếp thu góp ý (định tính, giai đoạn sau) |

### Performance (hiệu quả)
| Chỉ số | Nguồn | Ý nghĩa |
|--------|-------|---------|
| task_completion_rate | Lark task | tỉ lệ hoàn thành task |
| on_time_rate | Lark task | tỉ lệ đúng hạn |
| sales_kpi | BigQuery | đạt/ vượt KPI kinh doanh |
| quality_score | BigQuery | chỉ số chất lượng (đổi trả, hài lòng KH) |

Trọng số mặc định giữa 3 trục: Performance 0.4 / Collaboration 0.3 / Grow 0.3 —
cấu hình được trong `config/scoring_config.yaml`.

---

## 5. Lộ trình theo giai đoạn

### MVP (bản này)
- [x] Scaffold, cấu trúc module, config.
- [x] Khung client Lark (chat/doc/task) + BigQuery.
- [x] Data model + hàm tính điểm chạy được với dữ liệu mẫu.
- [ ] Kết nối thật Lark app + service account (cần credential).

### Giai đoạn 2 — Kết nối thật
- Triển khai token cache cho Lark, phân trang API.
- Query BigQuery thật, map `lark_user_id` ↔ `employee_id`.
- Persist dữ liệu thô (BigQuery/Postgres) để tính xu hướng theo kỳ.

### Giai đoạn 3 — Chất lượng đánh giá
- Chỉ số định tính bằng LLM (tóm tắt đóng góp, phân tích sentiment phối hợp).
- Chuẩn hoá theo phòng ban/vị trí (so sánh công bằng).
- Dashboard báo cáo + xuất PDF/Sheet.

### Giai đoạn 4 — Tự động hoá
- Lịch chạy định kỳ (cron), cảnh báo, vòng phản hồi với quản lý.

---

## 6. Credential cần cấu hình

Xem `.env.example`. Tối thiểu:

| Biến | Mô tả |
|------|-------|
| `LARK_APP_ID` | App ID của Custom App trên Lark |
| `LARK_APP_SECRET` | App Secret |
| `LARK_DOMAIN` | `https://open.larksuite.com` (Lark) hoặc `https://open.feishu.cn` (Feishu) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Đường dẫn file JSON service account |
| `BQ_PROJECT_ID` | Project ID trên Google Cloud |
| `BQ_DATASET` | Dataset chứa dữ liệu vận hành |

> Không commit file `.env` và JSON key vào git (đã liệt kê trong `.gitignore`).
