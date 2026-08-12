# Skills của MAI

**Một skill = một năng lực chung = một file = một owner.** Không sửa file của người khác.

Skill mô tả **"khi được hỏi X thì làm theo trình tự Y"**. Chi tiết hay thay đổi (số, ngưỡng,
ngày, danh sách người) **không** viết vào đây — viết vào `configs/*.json` rồi để skill gọi
`vn_config_get`. Đây là lý do đổi target không cần sửa skill.

| File | Owner | Phase | Config |
|---|---|---|---|
| `vn-internal-knowledge.md` | TP Digital Perf. | 0 | `persona` · `vn_context` · `role_permissions` · `vn_squads` · `vn_p2p_partners` |
| `vn-people-ops.md` | HR / People Ops ⚠ | 0 | `vn_kb_files` |
| `vn-nganh-trangsuc.md` | PM Ngành TS | 0 | `vn_context_ts` |
| `vn-nganh-nuochoa.md` | PM Ngành NH | 0 | `vn_context_nh` |
| `vn-ads-workflow.md` ⭐ | TN Facebook Ads | 1→3 | `vn_ads_rules` · `vn_naming_convention` |
| `vn-creative-content.md` | TN Content Perf. | 1→2 | `vn_brand_voice` |
| `vn-weekly-report.md` | PM / TP KD Online | 1 | `vn_report_sources` · `vn_base_targets` |
| `vn-season-calendar.md` | MKT / CĐS | 1 | `vn_season_calendar` |
| `vn-bst-milestones.md` | MKT / CĐS | 1 | `vn_bst_milestones` |
| `vn-assignments.md` | TN Affiliate / TP TMĐT | 2 | (dùng `vn_squads`) |
| `vn-research.md` | (việc còn trống) | 2 | `vn_research_sources` |

## Viết skill thế nào cho MAI dùng được

Mỗi file giữ đúng 5 phần:

1. **Header** — owner · config phụ thuộc · tool · phase · nghiệm thu.
2. **Khi nào dùng** — để MAI biết chọn skill nào.
3. **Trình tự** — các bước theo thứ tự, gọi tool nào ở bước nào.
4. **Luật bắt buộc** — điều MAI **không được** làm. Viết dứt khoát, không "nên/có thể".
5. **TODO cho owner** — phần chưa điền, để ai đọc cũng biết còn thiếu gì.

Ba luật xuyên suốt mọi skill: **trích nguồn** · **không bịa** · **không gộp số 3 ngành**.
