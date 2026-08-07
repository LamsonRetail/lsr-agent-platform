# Master Data — Rating Agent LamsonRetail

> **Trạng thái: BẢN ĐỀ XUẤT — cần confirm trước khi triển khai code.**
> Tài liệu này định nghĩa cấu trúc master data đặt trên **Lark Base** (Bitable),
> là "system of record" cho toàn hệ thống đánh giá.

## 0. Giả định cần xác nhận

1. **"Agent" = AI/software agent** (được golive, đăng ký, test tự động, deactivate)
   — KHÁC với nhân viên. Nếu ý bạn là nhân viên/sales agent (con người) thì mô
   hình test/deactivate sẽ đổi, cần báo lại.
2. **Squad = đội người** (nhân viên) làm việc theo mục tiêu; agent là công cụ AI
   phục vụ một hoặc nhiều squad.
3. **Hai nhánh đánh giá tách biệt hoàn toàn:**
   - **Squad** → hiệu quả theo **mục tiêu** (OKR/KR achievement).
   - **Agent** → **skill**, **mức độ sử dụng**, **kết quả trả về**, cộng cổng
     chặn bằng **kết quả test**.
4. **Lark Base** là nơi lưu master data + registry + test case + kết quả; Python
   agent đọc/ghi Base qua Lark MCP (hoặc Open API).

---

## 1. Tổng quan quan hệ (ER)

```
                    ┌─────────────┐
                    │  employees  │
                    └──────┬──────┘
                           │ thuộc
                    ┌──────▼──────┐        ┌────────────────────┐
                    │   squads    │──1:N──►│  squad_objectives   │ (KR để chấm mục tiêu)
                    └──────┬──────┘        └────────────────────┘
                           │ phục vụ                │ nguồn actual
                           │ (N:N)                  ▼
                    ┌──────▼──────┐        ┌────────────────────┐
                    │   agents    │        │  squad_evaluations  │ (kết quả chấm squad)
                    │ (registry)  │        └────────────────────┘
                    └──┬───┬───┬──┘
             skills │   │   │ test │        usage │
        ┌───────────▼┐ ┌▼───────────────┐ ┌──────▼──────────┐
        │agent_skills│ │agent_test_cases│ │  agent_usage    │
        └────────────┘ └───────┬────────┘ └─────────────────┘
                               │ chạy → ghi
                       ┌───────▼────────┐   ┌──────────────────────┐
                       │agent_test_runs │   │  agent_evaluations   │ (kết quả chấm agent)
                       └────────────────┘   └──────────────────────┘
```

---

## 2. Nhóm SQUAD

### 2.1 Bảng `squads`
Danh mục squad và toàn bộ "hiện vật" (chat, task, drive, dashboard, plan).

| Trường | Kiểu Lark Base | Mô tả |
|--------|----------------|-------|
| `squad_id` | Text (unique) | Mã squad, khoá chính |
| `squad_name` | Text | Tên squad |
| `description` | Text | Mô tả |
| `objective_summary` | Text | Mô tả mục tiêu tổng của squad |
| `lead` | Person | Trưởng squad |
| `members` | Person (multi) | Thành viên |
| `group_chats` | Text (multi) | Danh sách `chat_id` nhóm Lark của squad |
| `tasklists` | Text (multi) | Danh sách `tasklist_guid` (Lark Task) |
| `drive_report_links` | URL/Attachment | Link drive/báo cáo, kết quả |
| `dashboard_link` | URL | Link dashboard theo dõi |
| `plan_link` | URL | Link plan/kế hoạch |
| `period` | Text | Kỳ áp dụng (vd `2026-Q3`) |
| `status` | Single select | `active` / `paused` / `archived` |

### 2.2 Bảng `squad_objectives`
Mục tiêu và Key Result — nền tảng chấm **hiệu quả theo mục tiêu**.

| Trường | Kiểu | Mô tả |
|--------|------|-------|
| `objective_id` | Text (unique) | Khoá chính |
| `squad_id` | Link → `squads` | Thuộc squad nào |
| `period` | Text | Kỳ |
| `objective_name` | Text | Tên mục tiêu |
| `key_result` | Text | Mô tả KR |
| `metric_unit` | Text | Đơn vị (đơn hàng, doanh thu, %, ...) |
| `target` | Number | Chỉ tiêu |
| `actual` | Number | Thực đạt (nhập tay hoặc auto từ BigQuery/Task) |
| `weight` | Number | Trọng số KR trong mục tiêu |
| `data_source` | Single select | `manual` / `bigquery` / `lark_task` |
| `source_ref` | Text | Tên query BigQuery / bộ lọc task để lấy `actual` |
| `progress` | Formula | `actual / target` (chuẩn hoá khi chấm) |

---

## 3. Nhóm chung

### 3.1 Bảng `employees`
| Trường | Kiểu | Mô tả |
|--------|------|-------|
| `employee_id` | Text (unique) | Khoá chính |
| `full_name` | Text | Họ tên |
| `lark_user_id` | Text | Map sang Lark (chat/task/doc) |
| `department` | Text | Phòng ban |
| `squad_id` | Link → `squads` | Squad chính |
| `role` | Text | Vai trò |
| `status` | Single select | `active` / `inactive` |

---

## 4. Nhóm AGENT (registry + governance)

> **Quy tắc golive:** một agent chỉ được `status = active` khi (a) đã điền đủ
> trường bắt buộc trong `agents`, và (b) lần test gần nhất trong `agent_test_runs`
> = `pass`. Nếu test định kỳ fail → tự động chuyển `status = deactivated`.

### 4.1 Bảng `agents` (registry — bắt buộc trước golive)
| Trường | Kiểu | Mô tả |
|--------|------|-------|
| `agent_id` | Text (unique) | Khoá chính |
| `agent_name` | Text | Tên agent |
| `version` | Text | Phiên bản |
| `description` | Text | Mô tả chức năng |
| `owner` | Person | Người/đội phụ trách |
| `served_squads` | Link → `squads` (multi) | Agent phục vụ squad nào |
| `skills` | Link → `agent_skills` (multi) | Các skill agent tuyên bố |
| `data_sources` | Multi select | `lark_chat` / `lark_doc` / `lark_task` / `bigquery` / ... |
| `endpoint_ref` | Text | Endpoint/config để gọi khi test |
| `status` | Single select | `draft` / `registered` / `testing` / `active` / `deactivated` |
| `registered_at` | Date | Ngày đăng ký |
| `golive_at` | Date | Ngày golive |
| `last_test_status` | Lookup/Single select | `pass` / `fail` (từ run mới nhất) |
| `last_test_at` | Date | Lần test gần nhất |
| `health` | Formula | Đèn trạng thái (xanh/vàng/đỏ) |
| `deactivate_reason` | Text | Lý do khi bị deactivate |

### 4.2 Bảng `agent_skills`
Từ điển skill để **đánh giá agent theo skill**.

| Trường | Kiểu | Mô tả |
|--------|------|-------|
| `skill_id` | Text (unique) | Khoá chính |
| `skill_name` | Text | Tên skill (vd: tra cứu đơn, tóm tắt chat, phân tích KPI) |
| `category` | Single select | Nhóm skill |
| `description` | Text | Mô tả |

### 4.3 Bảng `agent_test_cases` (bài test)
| Trường | Kiểu | Mô tả |
|--------|------|-------|
| `test_id` | Text (unique) | Khoá chính |
| `agent_id` | Link → `agents` | Test cho agent nào |
| `skill_id` | Link → `agent_skills` | Test kiểm skill nào |
| `test_name` | Text | Tên bài test |
| `input_payload` | Text | Đầu vào gửi cho agent |
| `expected` | Text | Kết quả kỳ vọng |
| `assertion_type` | Single select | `exact` / `contains` / `semantic` / `regex` / `numeric_tolerance` |
| `weight` | Number | Trọng số bài test |
| `schedule` | Single select | `on_demand` / `daily` / `weekly` (test định kỳ) |
| `enabled` | Checkbox | Bật/tắt |

### 4.4 Bảng `agent_test_runs` (kết quả mỗi lần chạy)
| Trường | Kiểu | Mô tả |
|--------|------|-------|
| `run_id` | Text (unique) | Khoá chính |
| `agent_id` | Link → `agents` | |
| `test_id` | Link → `agent_test_cases` | |
| `run_at` | DateTime | Thời điểm chạy |
| `trigger` | Single select | `manual` / `scheduled` / `pre_golive` |
| `status` | Single select | `pass` / `fail` |
| `score` | Number | Điểm bài test |
| `actual_output` | Text | Đầu ra thực tế |
| `latency_ms` | Number | Độ trễ |
| `error` | Text | Lỗi (nếu có) |

### 4.5 Bảng `agent_usage` (mức độ sử dụng + kết quả trả về theo kỳ)
| Trường | Kiểu | Mô tả |
|--------|------|-------|
| `record_id` | Text (unique) | Khoá chính |
| `agent_id` | Link → `agents` | |
| `period` | Text | Kỳ (YYYY-MM hoặc tuần) |
| `invocations` | Number | Số lần gọi (mức độ sử dụng) |
| `unique_users` | Number | Số người dùng |
| `success_rate` | Number | Tỉ lệ trả về thành công/đúng |
| `avg_latency_ms` | Number | Độ trễ trung bình |
| `user_rating` | Number | Điểm phản hồi người dùng (1-5) |
| `cost` | Number | Chi phí vận hành (tuỳ chọn) |

---

## 5. Bảng kết quả đánh giá (đầu ra của agent chấm điểm)

### 5.1 `squad_evaluations`
| Trường | Kiểu | Mô tả |
|--------|------|-------|
| `squad_id` | Link → `squads` | |
| `period` | Text | Kỳ |
| `objective_score` | Number | Điểm đạt mục tiêu (0-100) |
| `on_time_score` | Number | Điểm đúng tiến độ |
| `total_score` | Number | Điểm tổng |
| `grade` | Single select | A/B/C/D |

### 5.2 `agent_evaluations`
| Trường | Kiểu | Mô tả |
|--------|------|-------|
| `agent_id` | Link → `agents` | |
| `period` | Text | Kỳ |
| `skill_score` | Number | Theo tỉ lệ pass test theo skill (0-100) |
| `usage_score` | Number | Theo mức độ sử dụng |
| `result_score` | Number | Theo success_rate/rating/latency |
| `test_pass_rate` | Number | % test pass trong kỳ |
| `total_score` | Number | Điểm tổng |
| `grade` | Single select | A/B/C/D |
| `status_recommendation` | Single select | `keep_active` / `watch` / `deactivate` |

---

## 6. Nguồn dữ liệu → trường nào

| Nguồn | Cấp dữ liệu cho |
|-------|-----------------|
| **Lark Base** | Toàn bộ master data, registry, test case/run, usage (system of record) |
| **Lark Chat** (`im_chat_list`, messages) | tín hiệu hoạt động squad; usage agent nếu agent chạy trong chat |
| **Lark Task** (`task_search`) | `squad_objectives.actual` (data_source=lark_task); tiến độ squad |
| **Lark Doc/Wiki/Drive** | báo cáo/kết quả squad (`drive_report_links`) |
| **BigQuery** | `squad_objectives.actual` (data_source=bigquery) — KPI kinh doanh thật |

---

## 7. Tiêu chí chấm điểm (tóm tắt — chi tiết ở PLAN.md §4)

**Squad (hiệu quả theo mục tiêu):**
`objective_score` = trung bình có trọng số `progress` của các KR; cộng
`on_time_score`. Không trộn với đánh giá agent.

**Agent (skill / usage / kết quả):**
- `skill_score` = tỉ lệ pass test theo từng skill (trọng số theo skill).
- `usage_score` = chuẩn hoá `invocations`, `unique_users`.
- `result_score` = từ `success_rate`, `user_rating`, `latency` (nghịch).
- **Cổng chặn:** nếu test định kỳ gần nhất = `fail` (hoặc fail N lần liên tiếp)
  → `status_recommendation = deactivate` và tự set `agents.status = deactivated`,
  bất kể điểm.

---

## 8. Cần bạn confirm

1. Định nghĩa "agent" = AI/software agent (đúng/sai?).
2. Danh sách **squad thực tế** của LamsonRetail (tên, mục tiêu, nhóm chat, tasklist,
   link drive/dashboard/plan) — để nạp vào `squads` + `squad_objectives`.
3. Bộ **skill** chuẩn cho agent (điền `agent_skills`).
4. Chính sách deactivate: fail **1 lần** hay **N lần liên tiếp** thì deactivate?
5. Đồng ý đặt master data trên **Lark Base** (tôi thấy đã có Lark MCP + BigQuery MCP
   kết nối) hay muốn nơi khác?

Sau khi bạn confirm, tôi sẽ: (a) chốt schema, (b) sinh code data model + connector
đọc/ghi Lark Base, (c) tách scorer thành 2 nhánh squad/agent, (d) module test agent.

---

## 9. Bảng bổ sung (phạm vi mới — PLAN §10c)

| Bảng | Nội dung chính |
|------|----------------|
| `agents` (mở rộng) | + `deployment` (`managed`\|`external`), `backup_owner`, `lark_chat_ids` (để khôi phục khi activate lại) |
| `teams` | team_id, loại (squad/chapter/team), tên, mục tiêu, lead, kênh Lark |
| `team_members` | team_id, họ tên, `lark_user_id`, vai trò, chuyên môn, backup, giờ làm việc |
| `team_kpis` | team_id, tên KPI, đơn vị, **công thức**, nguồn dữ liệu, target, kỳ, trọng số |
| `team_context` | second brain: ghi chú/quy ước/quyết định (markdown + tags) |
| `agent_golive_checklist` | câu trả lời checklist golive theo agent (xem GOLIVE_CHECKLIST.md) |
| `lark_admin_actions` | audit thao tác admin Lark: agent, hành động, chat_id trước/sau, người thực hiện, thời điểm |

> Nguyên tắc: **bảng chung của platform** — không để thông tin team rải rác theo từng agent.
> Mọi thao tác Lark admin chỉ đổi trạng thái/quyền, **không xoá dữ liệu**.
