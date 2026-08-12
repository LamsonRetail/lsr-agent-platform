# Configs của MAI

**Một key = một file = một owner.** Không ai sửa file của người khác — cần đổi thì nhắn owner.
Đây là lý do team không bao giờ bị conflict khi cùng làm.

## Quy ước

| Trường | Nghĩa |
|---|---|
| `_status` | `TODO` = owner chưa điền → MAI **nói "chưa có"**, không đoán. `OK` = dùng được. |
| `_owner` | Ai chịu trách nhiệm nội dung file này |
| `_skill` | Skill nào đọc config này |
| `_note` | Bẫy/luật cần nhớ khi điền |
| Giá trị `null` | Chưa điền — MAI không được tự đặt mặc định |

## Bảng config

| Key | Owner | Skill |
|---|---|---|
| `persona` | TP Digital Perf. | vn-internal-knowledge |
| `vn_context` | TP Digital Perf. | vn-internal-knowledge |
| `role_permissions` | TP Digital Perf. | vn-internal-knowledge |
| `vn_squads` | TP Digital Perf. | vn-internal-knowledge · vn-assignments |
| `vn_p2p_partners` | TP Digital Perf. | vn-internal-knowledge |
| `vn_ads_rules` | TN Facebook Ads | vn-ads-workflow |
| `vn_naming_convention` | TN Facebook Ads | vn-ads-workflow |
| `vn_brand_voice` | TN Content Perf. | vn-creative-content |
| `vn_context_ts` | PM Ngành Trang sức | vn-nganh-trangsuc |
| `vn_context_nh` | PM Ngành Nước hoa | vn-nganh-nuochoa |
| `vn_report_sources` | PM / TP KD Online | vn-weekly-report |
| `vn_base_targets` | PM / TP KD Online | vn-weekly-report |
| `vn_season_calendar` | MKT / CĐS | vn-season-calendar |
| `vn_bst_milestones` | MKT / CĐS | vn-bst-milestones |
| `vn_research_sources` | (việc còn trống) | vn-research |
| `vn_kb_files` | HR / People Ops ⚠ | vn-people-ops |

## Sửa config

```bash
# xem MAI đang đọc được gì
python3 ../vn/vietnam_tools.py --call vn_config_get '{"key": "vn_ads_rules"}'
```

Sửa xong nhớ đổi `_status` từ `TODO` → `OK`, rồi commit trên **branch con của mình** và mở PR
vào `feature/vn-agent-mai`.

> **Giai đoạn này config nằm trong git** nên đổi hành vi = commit + PR (vài phút), chưa phải
> "sửa là đổi ngay" như dashboard. Khi platform mở config store per-agent thì chuyển các file
> này lên đó — nội dung giữ nguyên, chỉ đổi chỗ đọc trong `vn_config_get`.
