# Plugin `lsr-telemetry`

Control point khi agent dùng **Claude Agent SDK subscription** (không API key):
plugin cài **hooks** vào Claude Code để tự ghi **tool call + token + output** của
mỗi phiên và gửi về **LSR Collector**. Không cần agent viết code telemetry tay.

## Hooks
- **PostToolUse** → ghi mỗi tool call (tên, ok, có kết quả) vào buffer theo session.
- **Stop** → tổng hợp buffer + parse transcript (token usage, output cuối) → dựng
  `AgentRunTrace` → POST `${LSR_COLLECTOR}/v1/traces` → xoá buffer.

Best-effort, luôn exit 0 — không làm gián đoạn phiên làm việc.

## Cấu hình (env ở môi trường chạy agent)
```
LSR_COLLECTOR=https://collector.lsr.internal
LSR_TELEMETRY_API_KEY=lsr_tel_...
LSR_AGENT_ID=AG-...
# tuỳ chọn: LSR_TRACE_DIR=/var/lib/lsr-trace
```
Thiếu `LSR_COLLECTOR` → plugin no-op êm (tiện dev local).

## Cài
Do `lsr-agent init` gắn sẵn, hoặc thủ công: thêm marketplace/plugin vào Claude Code
rồi bật `lsr-telemetry`. Hooks nằm ở `hooks/hooks.json`, script ở
`scripts/lsr_trace.py` (chỉ cần `python3`, không phụ thuộc gói ngoài).

## Kiểm thử
Logic thuần (parse transcript, dựng trace, suy ok/has_result) có test ở
`tests/test_plugin_trace.py`.
