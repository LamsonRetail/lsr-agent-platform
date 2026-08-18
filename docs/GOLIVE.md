# Golive agent — quy trình 2 chặng

> Áp dụng cho MỌI agent. Agent không tự lên sóng: **owner nộp đủ checklist → hệ thống
> tự trình admin → admin duyệt → agent chạy kênh thật**. Đây là control point của
> platform, không phải giấy tờ hình thức: mỗi mục tương ứng một thứ có thể gãy trong
> vận hành thật.

## Luồng

```
1. Owner điền agents/<ID>/golive.json          (28 mục, xem bảng dưới)
2. bash scripts/submit-golive.sh <ID>
      │
      ├─ còn thiếu → platform trả danh sách thiếu + nhắn Lark cho owner → sửa, nộp lại
      └─ đủ 28 mục → TỰ tạo đề xuất duyệt golive (risk=high) + notify admin
3. Admin bấm Duyệt ở Console → Duyệt việc
4. Platform bật agent: mở kênh Lark/Telegram + A2A, sync bot vào nhóm, start container,
   rồi nhắn Lark cho owner "đã golive".
```

Ghi chú quan trọng:
- **Owner tự nộp được**, không cần xin admin platform — bạn là moderator của agent mình.
- Nộp đủ checklist **không tự bật agent** (owner không tự golive việc của mình — tách vai).
- Nộp lại nhiều lần **không tạo đề xuất trùng**, admin không bị spam.
- Nếu checklist bị xoá sau khi trình duyệt, lúc admin bấm Duyệt hệ thống **chặn lại** và
  nhắc owner — không lách được.
- Trước khi golive, agent vẫn **test được qua web chat console** bình thường
  (`/agent/<ID>`). Chỉ kênh thật (Lark/Telegram) + A2A là phải chờ duyệt.

## Bắt đầu

```bash
bash scripts/lsr-login.sh                                  # 1 lần: đăng nhập Lark, duyệt CLI
cp templates/golive.example.json agents/<AGENT-ID>/golive.json
# điền thật vào file, rồi:
bash scripts/submit-golive.sh <AGENT-ID>
```

## 28 mục — điền gì, vì sao cần

### A. Định danh & sở hữu
| Mục | Điền gì | Vì sao cần |
|---|---|---|
| `owner_email` | email người chịu trách nhiệm | agent chạy bằng **subscription của owner**; mọi cảnh báo gửi về đây |
| `backup_owner` | email người thay khi owner nghỉ | owner nghỉ phép mà agent hỏng thì ai xử lý |
| `team_id` | mã squad (vd `SQ-FA`) | gắn agent vào second brain của team |

### B. Con người & phối hợp
| Mục | Điền gì | Vì sao cần |
|---|---|---|
| `team_members` | danh sách `{full_name, role, lark_user_id?, expertise?}` | biết ai dùng, ai review |
| `approver` | ai duyệt **kết quả** agent làm ra | agent đề xuất, người quyết |
| `collaboration_rules` | luật khi nào agent lên tiếng / nhường người | tránh agent trả lời tràn lan trong nhóm |
| `work_channels` | nhóm Lark + chat_id, kênh khác | khớp với routing ingress đã khai |

### C. Mục tiêu & KPI
| Mục | Điền gì | Vì sao cần |
|---|---|---|
| `kpis` | KPI của **team** `{kpi_name, unit, target, period, data_source, formula}` | đo agent có giúp việc thật không |
| `agent_kpi` | KPI của **chính agent** (vd % câu có trích nguồn) | chuẩn để đánh giá/rollback |
| `alert_thresholds` | ngưỡng báo động (DLQ, im lặng, tỷ lệ lỗi) | AG-OPS dùng để cảnh báo |

### D. Phạm vi & dữ liệu
| Mục | Điền gì | Vì sao cần |
|---|---|---|
| `data_sources_allowed` | nguồn được đọc (Base/Doc/BigQuery cụ thể) | ranh giới dữ liệu, tránh đọc bừa |
| `data_forbidden` | thứ **không** được trả lời (nhân sự, tài chính chi tiết, dữ liệu cá nhân) | tuân thủ + chống rò rỉ |
| `skills` | skill/MCP agent dùng | đối chiếu với chi phí & rủi ro tool |
| `writes` | agent được GHI gì (task, brain, sheet…) | đọc thì nhẹ, ghi thì phải rõ |

### E. Kết nối & xác thực
| Mục | Điền gì | Vì sao cần |
|---|---|---|
| `auth_mode` | `subscription của owner` | KHÔNG dùng API key chung |
| `lark_connect` | app_id, nhóm đã add bot, đã publish event + Long Connection | thiếu bước nào là Lark không đẩy tin |
| `telemetry_verified` | đã thấy run/token trên Console ngày nào | không đo được = không quản được (bài học AG-BI, Jenny) |
| `deployment` | chạy ở đâu (docker máy nào / VPS nào) | biết chỗ khởi động lại khi sự cố |

### F. Chất lượng & an toàn
| Mục | Điền gì | Vì sao cần |
|---|---|---|
| `tests_passed` | kết quả `scripts/agent-test.sh <ID>` + ngày | có bằng chứng chạy đúng |
| `escalation_rules` | khi không chắc / lỗi lặp thì làm gì | agent biết dừng, không đoán |
| `risks` | rủi ro đã biết + cách giảm | nói trước hơn giải thích sau |
| `reviewer_first_week` | ai đọc lại câu trả lời tuần đầu | tuần đầu là lúc sai nhiều nhất |

### G. Vận hành dài hạn
| Mục | Điền gì | Vì sao cần |
|---|---|---|
| `schedule` | job định kỳ (hoặc `["không có"]`) | biết agent tự làm gì khi không ai gọi |
| `retrain_process` | tri thức/prompt sai thì sửa thế nào | agent phải sửa được, không phải đập đi |
| `feedback_channel` | người dùng phản hồi ở đâu | kênh nghe cái sai |
| `review_cadence` | bao lâu owner xem lại (vd `weekly`) | không ai xem = agent trôi |
| `team_notified` | đã thông báo minh bạch cho nhóm ngày nào | agent ghi log hội thoại — người trong nhóm phải được biết |
| `scope_confirmed` | owner xác nhận agent đúng phạm vi USECASE.md | chốt lại lằn ranh trước khi lên sóng |

## Kiểm tra trạng thái

```bash
curl -s https://platform.34-126-154-135.sslip.io/v1/agents/<ID>/golive-checklist | python3 -m json.tool
```

Sau khi admin duyệt, xem agent chạy thật ở Console → Agent → `<ID>`: số run, token, lỗi.
