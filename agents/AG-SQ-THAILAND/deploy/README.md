# Đưa Ploy (AG-SQ-THAILAND) lên VM

Hiện Ploy chạy trên **máy của Vinh** → gập máy là bot tắt. File
`deploy-ag-sq-thailand.yml` đưa Ploy lên VM chạy 24/7, theo đúng khuôn
`agents/AG-INVENTORY-DAYS/deploy/` đã chạy thật từ 19/08.

Workflow **không tự cài được**: CI scope-guard chỉ cho squad sửa `agents/<id>/**`,
không cho sửa `.github/workflows/`. Nên file nằm ở đây, admin/maintainer copy vào.

## Việc của admin (3 bước, ~5 phút)

1. Copy file vào workflow:
   ```
   cp agents/AG-SQ-THAILAND/deploy/deploy-ag-sq-thailand.yml \
      .github/workflows/deploy-ag-sq-thailand.yml
   ```
2. Thêm secret ở **Settings > Secrets and variables > Actions**:

   | Secret | Nội dung | Ghi chú |
   |---|---|---|
   | `LSR_AGENT_TOKEN_THAILAND` | agent token của AG-SQ-THAILAND | **bắt buộc** |
   | `GCP_SA_JSON_THAILAND` | JSON service account BigQuery (project `surya-495408`) | thiếu thì Ploy vẫn chạy, chỉ mất số sống |

   `LSR_DEPLOY_KEY` · `LSR_DEPLOY_HOST` · `LSR_DEPLOY_USER` đã có sẵn (agent
   AG-INVENTORY-DAYS đang dùng) — không cần thêm.
3. Chạy workflow (`workflow_dispatch`). Lần đầu `DRY_RUN=true` → Ploy lên nhưng
   **không** trả lời Lark, để đối chiếu an toàn.

## Bật trả lời thật — thứ tự bắt buộc

Cùng một agent token mà có 2 consumer thì hai bên **giành job trên cùng hàng đợi**,
bản cũ trả lời trước và người dùng thấy câu sai. Đã xảy ra thật 19/08 (6 consumer
song song). Nên:

1. Tắt consumer trên máy Vinh: `pkill -f consumer.py`
2. Đặt biến repo `AG_SQ_THAILAND_DRY_RUN=false`
3. Chạy lại workflow, xem bước *Verify Ploy đã chạy* báo `✓`.

## Việc còn treo: model trên VM

Ploy gọi model qua **Claude Code CLI** bằng subscription của owner
(`lsr-agent.yaml: auth: subscription`). Container trên VM không có CLI đó →
workflow đặt `LSR_MODEL_MODE=off`, Ploy trả lời **thuần luật**: mốc BST, mùa vụ,
base target, số BigQuery, logistics, tổ chức vẫn đủ; mất phần suy luận tự do
(khung first-principles) và phần dựng biên bản bằng model.

Ba đường xử lý, cần admin chọn:
- **A.** Cài Claude Code CLI + `claude setup-token` trên VM, mount `~/.claude` vào
  container. Giữ đúng chuẩn "agent không cầm API key".
- **B.** Platform cấp một endpoint model dùng chung, agent gọi qua platform token.
  Sạch nhất về lâu dài, nhưng là việc của core.
- **C.** Giữ Ploy trên máy Vinh cho phần model, VM chỉ chạy bản luật làm dự phòng.

Trước khi có A/B: **giữ Ploy trên máy Vinh** (đã có launchd ở `ops/`), coi bản VM
là dự phòng chạy `DRY_RUN=true`.
