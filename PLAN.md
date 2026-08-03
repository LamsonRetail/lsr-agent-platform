# Rating Agent — LamsonRetail

Hệ thống nội bộ đánh giá **Squad** và **Agent** của LamsonRetail dựa trên dữ liệu
làm việc thực tế trên **Lark** (chat, document, task, base) và **BigQuery** (data
warehouse vận hành kinh doanh).

> **Cấu trúc master data (Lark Base) đang chờ confirm** — xem
> [MASTER_DATA.md](MASTER_DATA.md). Các bước code tiếp theo chờ bạn duyệt schema.

## Hai nhánh đánh giá tách biệt

| Đối tượng | Chấm theo | Nguồn chính |
|-----------|-----------|-------------|
| **Squad** (đội người) | **Hiệu quả theo mục tiêu** (OKR/KR achievement, đúng tiến độ) | `squad_objectives`, Lark Task, BigQuery |
| **Agent** (AI/software agent) | **Skill · Mức độ sử dụng · Kết quả trả về** + cổng chặn bằng **test** | `agents`, `agent_test_runs`, `agent_usage` |

Mọi agent trước khi **golive** phải được **đăng ký** vào registry `agents` trên
Lark Base với đầy đủ thông tin, và **pass bộ test** thì mới được kích hoạt. Test
tự động chạy **định kỳ**; agent **fail** sẽ bị **deactivate**.

---

## 1. Kiến trúc tổng thể

```
┌──────────────────────────────────────────────────────────────────────────┐
│                               Rating Agent                                 │
└──────────────────────────────────────────────────────────────────────────┘
        │                          │                            │
┌───────▼────────┐        ┌────────▼─────────┐         ┌────────▼─────────┐
│  Master data    │        │    Thu thập &     │         │   Đánh giá &      │
│  (Lark Base)    │        │    trích tín hiệu │         │   Governance      │
├────────────────┤        ├──────────────────┤         ├──────────────────┤
│ squads          │        │ Lark Chat/Task/Doc│         │ Squad scorer      │
│ squad_objectives│──đọc──►│ BigQuery KPI      │──►      │ Agent scorer      │
│ agents (registry)│       │ Agent test runner │         │ Test gate →       │
│ agent_skills    │        │ Agent usage       │         │   deactivate      │
│ agent_test_cases│        └──────────────────┘         └────────┬─────────┘
│ agent_usage     │                                              │ ghi lại
└────────────────┘◄─────────────────────────────────────────────┘
        ▲                                                         │
        └──────────── squad_evaluations / agent_evaluations ◄─────┘
                                    │
                            ┌───────▼────────┐
                            │  Màn hình (§6)  │  scoreboard, registry, test dashboard
                            └────────────────┘
```

### Thành phần code (dự kiến sau confirm)

| Lớp | Module | Vai trò |
|-----|--------|---------|
| Cấu hình | `src/rating_agent/config.py` | Env + config chấm điểm |
| Lark Base | `src/rating_agent/lark/base.py` | Đọc/ghi master data, registry, test, usage |
| Lark tín hiệu | `src/rating_agent/lark/` | chat/doc/task → tín hiệu squad & usage agent |
| BigQuery | `src/rating_agent/bq/` | KPI kinh doanh cho `squad_objectives.actual` |
| Đánh giá squad | `src/rating_agent/evaluation/squad_scorer.py` | Chấm hiệu quả theo mục tiêu |
| Đánh giá agent | `src/rating_agent/evaluation/agent_scorer.py` | Chấm skill/usage/result + cổng test |
| Test agent | `src/rating_agent/agent_testing/` | Runner chạy test, ghi run, gate deactivate |
| Điều phối | `src/rating_agent/pipeline.py` | Ghép nối thu thập → chấm → ghi kết quả |

---

## 2. Nguồn dữ liệu

### 2.1 Lark Base — system of record
Toàn bộ master data, registry agent, test case/run, usage nằm trên Lark Base.
Truy cập qua **Lark MCP** (`base_record_list`, `base_data_query`,
`base_record_create`) hoặc Open API. Chi tiết bảng: [MASTER_DATA.md](MASTER_DATA.md).

### 2.2 Lark Chat / Task / Doc — tín hiệu vận hành
| Nguồn | API/MCP | Dùng cho |
|-------|---------|----------|
| Chat | `im_chat_list`, `im/v1/messages` | hoạt động squad; usage agent chạy trong chat |
| Task | `task_search`, `task/v2/tasks` | tiến độ mục tiêu squad (`data_source=lark_task`) |
| Doc/Wiki/Drive | `wiki_node_list`, `drive_search` | báo cáo/kết quả squad |

### 2.3 BigQuery — KPI kinh doanh
Cấp `actual` cho các KR có `data_source=bigquery`. Xác thực bằng service account
(`GOOGLE_APPLICATION_CREDENTIALS`) hoặc BigQuery MCP.

Quyền/scope Lark cần: `bitable:app`, `im:message:readonly`, `im:chat:readonly`,
`task:task:readonly`, `docx:document:readonly`, `contact:user.base:readonly`.

---

## 3. Pipeline

1. **Nạp master data** — đọc `squads`, `squad_objectives`, `agents`,
   `agent_test_cases` từ Lark Base.
2. **Thu thập tín hiệu** — Lark chat/task/doc + BigQuery + `agent_usage`.
3. **Chạy test agent** — runner thực thi `agent_test_cases` theo `schedule`, ghi
   `agent_test_runs`.
4. **Chấm điểm** — squad scorer (mục tiêu) + agent scorer (skill/usage/result).
5. **Governance gate** — agent fail test → set `status = deactivated`.
6. **Ghi kết quả** — `squad_evaluations`, `agent_evaluations` về Lark Base + render
   màn hình (§6).

---

## 4. Tiêu chí chấm điểm

### 4.1 Squad — hiệu quả theo mục tiêu
| Chỉ số | Nguồn | Ý nghĩa |
|--------|-------|---------|
| objective_achievement | `squad_objectives` | TB có trọng số `progress = actual/target` các KR |
| on_time_rate | Lark Task | tỉ lệ mốc/việc đúng hạn |
| (tuỳ chọn) collaboration | Lark Chat | phối hợp nội bộ squad |

`total_squad = 0.7 * objective_achievement + 0.3 * on_time_rate` (cấu hình được).

### 4.2 Agent — skill / usage / kết quả
| Chỉ số | Nguồn | Ý nghĩa |
|--------|-------|---------|
| skill_score | `agent_test_runs` theo `skill_id` | tỉ lệ pass test theo từng skill |
| usage_score | `agent_usage` | chuẩn hoá `invocations`, `unique_users` |
| result_score | `agent_usage` | `success_rate`, `user_rating`, `latency` (nghịch) |
| test_pass_rate | `agent_test_runs` | % test pass trong kỳ |

`total_agent = 0.4*skill + 0.3*result + 0.3*usage` (cấu hình được).

**Cổng chặn (governance):** nếu test định kỳ gần nhất = `fail` (hoặc fail N lần
liên tiếp — chờ bạn chốt N), `status_recommendation = deactivate` và tự set
`agents.status = deactivated`, bất kể điểm số.

Ngưỡng xếp loại A/B/C/D áp riêng cho từng nhánh (config).

---

## 5. Governance & vòng đời agent

```
draft ──đăng ký đủ thông tin──► registered ──chạy full test──► testing
                                                                  │
                              pass ───────────────────────────────┤
                                                                  ▼
   deactivated ◄──test định kỳ FAIL / fail N lần── active ◄──golive
        │                                            ▲
        └────────sửa + test lại pass────────────────┘
```

- **Đăng ký bắt buộc trước golive:** `agent_id, name, version, owner,
  served_squads, skills, data_sources, endpoint_ref` phải đầy đủ.
- **Pre-golive test:** chạy toàn bộ `agent_test_cases enabled` → phải pass.
- **Test định kỳ:** theo `schedule` (daily/weekly) → ghi `agent_test_runs`.
- **Auto-deactivate:** vi phạm chính sách test → `status=deactivated` +
  `deactivate_reason`, thông báo owner.

---

## 6. Màn hình đánh giá (ưu tiên làm rõ trước)

| # | Màn hình | Nội dung chính | Nguồn |
|---|----------|----------------|-------|
| 1 | **Squad Scoreboard** | Xếp hạng squad theo `total_squad`, đèn tiến độ mục tiêu | `squad_evaluations` |
| 2 | **Squad Detail** | KR & progress, link chat/task/drive/dashboard/plan, thành viên | `squads`, `squad_objectives` |
| 3 | **Agent Registry** | Danh sách agent + `status` + `health` + lần test gần nhất | `agents` |
| 4 | **Agent Detail** | Skill, xu hướng usage, lịch sử test, kết quả | `agents`, `agent_usage`, `agent_test_runs` |
| 5 | **Agent Test Dashboard** | Lịch test, pass/fail, agent đang bị deactivate + lý do | `agent_test_runs` |
| 6 | **Agent Leaderboard** | Xếp hạng agent theo skill/usage/result | `agent_evaluations` |

Định dạng render đề xuất: HTML dashboard tĩnh (self-contained) hoặc Lark
Dashboard/Base view.

> **Prototype đã có:** cả 6 màn hình được dựng trong `src/rating_agent/reporting/`
> (dữ liệu điểm từ scorer thật + dữ liệu mẫu). Sinh bằng
> `python -m rating_agent.reporting.dashboard` → `output/dashboard.html`.

---

## 7. Lộ trình

### Giai đoạn 0 — Chốt thiết kế (đang ở đây)
- [ ] Confirm cấu trúc master data ([MASTER_DATA.md](MASTER_DATA.md)).
- [ ] Confirm tiêu chí (§4) và danh sách màn hình (§6).

### MVP — sau confirm
- Tạo/nạp Lark Base theo schema; connector đọc/ghi Base.
- Squad scorer + Agent scorer chạy với dữ liệu thật.
- Test runner + auto-deactivate; render màn hình 1,3,5.

### Giai đoạn 2 — Tự động hoá
- Lịch chạy định kỳ (cron) cho test + chấm điểm; cảnh báo owner.
- Đầy đủ 6 màn hình; export báo cáo.

### Giai đoạn 3 — Nâng cao
- Chấm định tính bằng LLM (assertion `semantic`), chuẩn hoá theo nhóm, phân tích
  xu hướng nhiều kỳ.

---

## 8. Credential cần cấu hình

Xem [.env.example](.env.example). Tối thiểu:

| Biến | Mô tả |
|------|-------|
| `LARK_APP_ID` / `LARK_APP_SECRET` | Custom App Lark (bật quyền `bitable:app` cho Base) |
| `LARK_DOMAIN` | `https://open.larksuite.com` (Lark) hoặc `https://open.feishu.cn` (Feishu) |
| `LARK_BASE_APP_TOKEN` | Token app Lark Base chứa master data |
| `GOOGLE_APPLICATION_CREDENTIALS` | JSON service account BigQuery |
| `BQ_PROJECT_ID` / `BQ_DATASET` | Project & dataset DWH |

> Không commit `.env` và JSON key (đã có trong `.gitignore`).
