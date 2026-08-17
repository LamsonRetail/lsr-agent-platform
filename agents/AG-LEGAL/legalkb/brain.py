"""Gọi Claude (reasoning) + ghép prompt từ ngữ cảnh platform.

Xác thực: **subscription** qua CLI `claude` (docs/AGENT_RUNTIME.md, chuẩn
`runtime.auth: subscription`) — KHÔNG API key, không đọc secret nào ở đây.

Hai việc:
  1. `route()`  — phân intent S1..S5 + mức rủi ro, để consumer chọn luồng và mức gate.
  2. `build_prompt()` / `compress()` — dựng prompt STATELESS mỗi lượt từ ngữ cảnh
     platform trả về, và nén lượt cũ. Không giữ hội thoại trong tiến trình.
"""
import json
import os
import re
import subprocess
import sys

DEFAULT_MODEL = "claude-sonnet-5"
CALL_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "120"))

INTENTS = ("s1_qa", "s2_create_contract", "s3_review_contract",
           "s4_news", "s5_signing", "other")

_ROUTE_PROMPT = """Bạn là bộ phân loại của trợ lý pháp chế nội bộ. Đọc tin nhắn của nhân
viên và trả về DUY NHẤT một JSON, không thêm chữ nào khác:

{"intent": "...", "risk": "low|medium|high", "contract_type": "", "reason": ""}

intent chọn một trong: s1_qa (hỏi đáp quy định/chính sách/pháp luật),
s2_create_contract (muốn tạo/soạn hợp đồng mới từ mẫu),
s3_review_contract (gửi hợp đồng đối tác nhờ rà soát),
s4_news (hỏi về văn bản luật mới/digest), s5_signing (hồ sơ trình ký),
other (không thuộc phạm vi pháp chế).

risk: high nếu việc này có thể gây hậu quả pháp lý ngay (ký kết, cam kết với đối tác,
dữ liệu cá nhân, tranh chấp, hạn mức tiền lớn); medium nếu cần cẩn trọng; low nếu chỉ
tra cứu thông tin thường.

Tin nhắn:
---
{msg}
---"""


def call_claude(prompt, model=None, timeout=None):
    """Một lần gọi model. Trả text; lỗi trả chuỗi rỗng (caller phải degrade rõ ràng)."""
    try:
        r = subprocess.run(
            ["claude", "-p", prompt, "--model", model or DEFAULT_MODEL],
            capture_output=True, text=True, timeout=timeout or CALL_TIMEOUT)
        return (r.stdout or "").strip() or (r.stderr or "").strip()
    except Exception as exc:
        print(f"[claude] lỗi gọi model: {exc}", file=sys.stderr, flush=True)
        return ""


def _first_json(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def route(message, ctx=None, has_attachment=False):
    """Phân intent + mức rủi ro.

    Có tệp đính kèm là dấu hiệu mạnh của S3 (nhờ review hợp đồng) — dùng làm mặc định
    khi model không trả được JSON, thay vì đoán bừa.
    """
    fallback = {"intent": "s3_review_contract" if has_attachment else "s1_qa",
                "risk": "medium" if has_attachment else "low",
                "contract_type": "", "reason": "fallback: router không phân loại được"}
    out = _first_json(call_claude(_ROUTE_PROMPT.replace("{msg}", (message or "")[:4000]),
                                 model=(ctx or {}).get("model"), timeout=60))
    if not out or out.get("intent") not in INTENTS:
        return fallback
    if out.get("risk") not in ("low", "medium", "high"):
        out["risk"] = "medium"
    if has_attachment and out["intent"] == "s1_qa":
        out["intent"] = "s3_review_contract"        # có file mà phân là hỏi đáp → sửa lại
    return out


def build_prompt(ctx, question, extra=""):
    """Ghép prompt cho một lượt TỪ NGỮ CẢNH PLATFORM — không nhồi lịch sử vào code.

    Thứ tự theo `hint` của /v1/self/context: instruction + rolling_summary +
    recent_turns + user_facts + knowledge.
    """
    parts = []
    if ctx.get("instruction_block"):
        parts.append(ctx["instruction_block"])
    if ctx.get("rolling_summary"):
        parts.append("### Bối cảnh hội thoại trước đó\n" + ctx["rolling_summary"])
    turns = ctx.get("recent_turns") or []
    if turns:
        parts.append("### Các lượt gần nhất\n" + "\n".join(
            f"{t.get('role')}: {t.get('text')}" for t in turns))
    if ctx.get("user_facts"):
        parts.append("### Điều đã biết về người này\n" + "\n".join(
            f"- {f}" for f in ctx["user_facts"]))
    if ctx.get("knowledge"):
        know = []
        for k in ctx["knowledge"]:
            src = k.get("source_url") or ""
            know.append(f"- {k.get('title', '')}: {k.get('content', '')}"
                        + (f" (nguồn: {src})" if src else ""))
        parts.append("### Tri thức nội bộ đã duyệt (trích dẫn source_url khi dùng)\n"
                     + "\n".join(know))
    if extra:
        parts.append(extra)
    parts.append("### Câu hỏi lượt này\nuser: " + (question or ""))
    return "\n\n".join(parts)


def kb_question(ctx, question, max_ctx=1200):
    """Câu hỏi gửi NotebookLM, có kèm ngữ cảnh NGẮN từ platform.

    Khác `build_prompt` (dành cho Claude): NotebookLM trả lời dựa trên sources, nhồi
    nhiều ngữ cảnh sẽ làm nó trả lời lệch. Chỉ đưa phần cần để hiểu câu hỏi tiếp nối —
    và ngữ cảnh này lấy từ platform, KHÔNG dựa vào phiên chat của engine (engine mất
    phiên thì vẫn nhớ).
    """
    bits = []
    if ctx.get("rolling_summary"):
        bits.append("Bối cảnh: " + ctx["rolling_summary"])
    for t in (ctx.get("recent_turns") or [])[-2:]:
        bits.append(f"{t.get('role')}: {t.get('text')}")
    if ctx.get("user_facts"):
        bits.append("Về người hỏi: " + "; ".join(ctx["user_facts"][:3]))
    if not bits:
        return question
    head = "\n".join(bits)[:max_ctx]
    return f"[Ngữ cảnh trước đó — chỉ để hiểu câu hỏi, không phải nguồn]\n{head}\n\n{question}"


def compress(dropped_turns, model=None):
    """Nén các lượt bị cắt thành rolling summary.

    Thay cho cách cũ "cắt 2000 ký tự cuối" — cắt ngang câu là mất thông tin thật.
    Model lỗi thì mới rơi về cắt thô, để không bao giờ mất lượt.
    """
    raw = "\n".join(f"{t.get('role')}: {t.get('text')}" for t in dropped_turns or [])
    if not raw:
        return ""
    out = call_claude(
        "Nén đoạn hội thoại pháp chế dưới đây thành bản ghi nhớ ngắn (tối đa 12 dòng), "
        "giữ: người hỏi quan tâm gì, kết luận đã đưa ra, số hiệu/tên tài liệu đã trích, "
        "việc còn dở. Không bình luận thêm.\n\n" + raw[:12000],
        model=model, timeout=90)
    return out or raw[-2000:]
