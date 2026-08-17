"""Biên bản họp cho AG-KD-MATE-MADE — transcript → nháp → chủ trì chốt → publish.

**Đây là module, không phải process riêng.** ``consumer.py`` là tiến trình duy nhất poll
``/v1/self/jobs``; nếu chạy thêm một process nữa cùng poll thì hai bên giành job của nhau
và tin nhắn sẽ rơi ngẫu nhiên vào process không biết xử lý. Consumer nhận job rồi gọi
``handle_meeting_job()`` ở đây.

Ba ràng buộc ép trong code, không chỉ nhắc trong prompt:

  1. **Không bao giờ tự publish.** Dựng xong là nháp CHƯA CHỐT, phải có người xác nhận.
  2. **Chỉ chủ trì mới chốt được.** Người khác nhắn "chốt" → hỏi lại chủ trì.
  3. **Cam kết thiếu người/hạn thì ghi "chưa rõ"**, không tự gán người, không tự đặt hạn —
     biên bản gán sai người còn tệ hơn biên bản thiếu.

Trạng thái nháp **không giữ trong RAM**: nháp nằm trong lượt hội thoại đã ghi lên platform,
lúc chốt thì đọc lại từ ``ctx["recent_turns"]``. Nhờ vậy restart agent không mất nháp đang
chờ chốt.

Chạy thử không gọi Lark:
    DRY_RUN=true python3 meeting_note.py --transcript mẫu.txt
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import requests

TZ = timezone(timedelta(hours=7))
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"

LARK_DOMAIN = os.environ.get("LARK_DOMAIN", "https://open.larksuite.com").rstrip("/")
LARK_APP_ID = os.environ.get("LARK_APP_ID", "")
LARK_APP_SECRET = os.environ.get("LARK_APP_SECRET", "")
# Folder Drive chứa biên bản đã chốt (rỗng = để ở My Space của app).
NOTE_FOLDER = os.environ.get("KD_NOTE_FOLDER", "")

# Ai được chốt biên bản. Danh sách open_id/email, phân tách dấu phẩy.
# RỖNG = người gửi recording được coi là chủ trì (xem ``is_chair``).
CHAIRS = {c.strip().lower() for c in os.environ.get("KD_MEETING_CHAIRS", "").split(",")
          if c.strip()}

DRAFT_MARKER = "📝 **BIÊN BẢN NHÁP — CHƯA CHỐT**"
UNKNOWN = "_chưa rõ_"

# Dấu hiệu job này là việc biên bản họp.
_MEETING_HINT = re.compile(
    r"biên bản|bien ban|meeting note|ghi chú cuộc họp|tóm tắt (cuộc )?họp|minutes",
    re.IGNORECASE)
_AUDIO_EXT = (".m4a", ".mp3", ".wav", ".mp4", ".mov", ".aac", ".ogg", ".webm", ".flac")

_CONFIRM = re.compile(r"^\s*(chốt|duyệt|confirm|ok chốt|đồng ý)\b", re.IGNORECASE)
_EDIT = re.compile(r"^\s*sửa\b[:\s]*(.+)", re.IGNORECASE | re.DOTALL)

# Câu chứa cam kết. Cố ý rộng — thà bắt dư rồi để người sửa, còn hơn sót một lời hứa với khách.
_COMMIT_VERBS = re.compile(
    r"\bsẽ\b|phụ trách|chịu trách nhiệm|đảm nhận|nhận (làm|phần)|"
    r"gửi (lại|cho|báo giá)|chuẩn bị|hoàn thành|follow[- ]?up|theo dõi|chốt với|"
    r"liên hệ|báo lại|cập nhật|làm xong",
    re.IGNORECASE)

# Hạn chót. Bắt cả ngày cụ thể lẫn cách nói tương đối thường gặp trong họp.
_DEADLINE = re.compile(
    r"(trước|hạn|deadline|xong (trước|trong)|chậm nhất)\s*[:\-]?\s*"
    r"(ngày\s*)?(\d{1,2}[/\-]\d{1,2}([/\-]\d{2,4})?)"
    r"|(cuối (tuần|tháng|ngày))|(trong (tuần|tháng|ngày) (này|tới|sau))"
    r"|(thứ\s*(hai|ba|tư|năm|sáu|bảy)|chủ nhật)"
    r"|(ngày mai|hôm nay|tuần sau|tháng sau)",
    re.IGNORECASE)

# Người thực hiện: "anh/chị/em/bạn <Tên>" hoặc tên viết hoa đầu câu.
_PERSON = re.compile(
    r"\b(anh|chị|em|bạn|c|a)\s+([A-ZĐÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯ][\wÀ-ỹ]*)"
    r"|^([A-ZĐÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯ][\wÀ-ỹ]*)\s+(sẽ|phụ trách|nhận)",
    re.IGNORECASE | re.MULTILINE)

_DECISION = re.compile(r"\bchốt là\b|\bquyết định\b|\bthống nhất\b|\bkết luận\b|"
                       r"\bđồng ý\b|\bduyệt\b", re.IGNORECASE)
_RISK = re.compile(r"\brủi ro\b|\blo (là|ngại)\b|\bvấn đề\b|\bkhó\b|\bchậm\b|\btrễ\b|"
                   r"\bthiếu\b|\bcảnh báo\b", re.IGNORECASE)
_CUSTOMER = re.compile(r"\b(khách|đại lý|đối tác|kh)\s+([A-ZĐÀ-Ỹ][\wÀ-ỹ]*(\s+[A-ZĐÀ-Ỹ][\wÀ-ỹ]*)?)",
                       re.IGNORECASE)


# ----------------------------- nhận diện job -----------------------------

def is_meeting_job(job: dict) -> bool:
    """Job này có phải việc biên bản họp không."""
    payload = job.get("payload") or {}
    if payload.get("file_url") or payload.get("recording_url") or payload.get("minute_token"):
        return True
    name = (payload.get("file_name") or "").lower()
    if name.endswith(_AUDIO_EXT):
        return True
    return bool(_MEETING_HINT.search(payload.get("text") or ""))


def is_chair(user_ref: str, draft_owner: str = "") -> bool:
    """Người này có quyền chốt biên bản không.

    ``KD_MEETING_CHAIRS`` rỗng → người gửi recording được coi là chủ trì. Đây là mặc định
    dùng được ngay mà vẫn giữ nguyên tắc "phải có người xác nhận"; trưởng nhóm KD nên khai
    danh sách thật trước golive.
    """
    who = (user_ref or "").strip().lower()
    if not who:
        return False
    if CHAIRS:
        return who in CHAIRS
    return bool(draft_owner) and who == draft_owner.strip().lower()


# ----------------------------- bóc nội dung -----------------------------

def _sentences(transcript: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+|\n+", transcript or "")
    return [p.strip() for p in parts if len(p.strip()) > 8]


def _person_in(sentence: str) -> str:
    m = _PERSON.search(sentence)
    if not m:
        return UNKNOWN
    return (m.group(2) or m.group(3) or "").strip() or UNKNOWN


def _deadline_in(sentence: str) -> str:
    m = _DEADLINE.search(sentence)
    return m.group(0).strip() if m else UNKNOWN


def extract_commitments(transcript: str) -> list[dict]:
    """Cam kết trong cuộc họp: ai · làm gì · hạn.

    Thiếu người hoặc hạn thì để ``chưa rõ`` — KHÔNG suy đoán. Người đọc biên bản cần thấy
    chỗ nào còn hổng để hỏi lại, chứ không phải một cái tên do máy đoán.
    """
    out = []
    for s in _sentences(transcript):
        if not _COMMIT_VERBS.search(s):
            continue
        out.append({"who": _person_in(s), "what": s[:220], "when": _deadline_in(s)})
    return out


def _match_lines(transcript: str, pattern: re.Pattern, limit: int = 8) -> list[str]:
    return [s[:220] for s in _sentences(transcript) if pattern.search(s)][:limit]


# "đại lý mới", "khách này"… không phải tên khách — lọc ra để danh sách không thành rác.
_NOT_A_NAME = {"mới", "này", "đó", "khác", "cũ", "lớn", "nhỏ", "nào", "kia", "hiện"}


def extract_customers(transcript: str, limit: int = 10) -> list[str]:
    seen: list[str] = []
    for m in _CUSTOMER.finditer(transcript or ""):
        who = (m.group(2) or "").strip()
        if not who or who.split()[0].lower() in _NOT_A_NAME:
            continue
        name = f"{m.group(1)} {who}".strip()
        if name not in seen:
            seen.append(name)
    return seen[:limit]


def build_draft(transcript: str, *, title: str = "", when: str = "") -> str:
    """Dựng biên bản nháp.

    Bản này bóc bằng luật để chạy được ngay và test được. Khi nối model thật, thay phần
    bóc bằng lời gọi model nhưng **giữ nguyên cấu trúc mục và quy tắc "chưa rõ"** — đó là
    hàng rào an toàn, không phải phần sinh văn.
    """
    when = when or datetime.now(TZ).strftime("%d/%m/%Y %H:%M")
    title = title or f"Họp Kinh Doanh Mate Made — {when}"

    commits = extract_commitments(transcript)
    decisions = _match_lines(transcript, _DECISION)
    risks = _match_lines(transcript, _RISK, limit=5)
    customers = extract_customers(transcript)

    lines = [DRAFT_MARKER, f"## {title}", f"_Thời gian: {when}_", ""]

    lines += ["### 1. Tóm tắt", (transcript or "").strip()[:600] or UNKNOWN, ""]

    lines += ["### 2. Quyết định"]
    lines += [f"- {d}" for d in decisions] or [f"- {UNKNOWN}"]
    lines += [""]

    lines += ["### 3. Cam kết (ai · làm gì · hạn)", "",
              "| Ai | Làm gì | Hạn |", "|---|---|---|"]
    if commits:
        lines += [f"| {c['who']} | {c['what']} | {c['when']} |" for c in commits]
    else:
        lines += [f"| {UNKNOWN} | không bóc được cam kết nào từ transcript | {UNKNOWN} |"]
    lines += [""]

    lines += ["### 4. Khách hàng / deal được nhắc"]
    lines += [f"- {c}" for c in customers] or [f"- {UNKNOWN}"]
    lines += [""]

    lines += ["### 5. Next action"]
    lines += [f"- {c['who']}: {c['what'][:120]} (hạn {c['when']})" for c in commits] or \
             [f"- {UNKNOWN}"]
    lines += [""]

    lines += ["### 6. Rủi ro nêu trong họp"]
    lines += [f"- {r}" for r in risks] or ["- không có rủi ro nào được nêu"]
    lines += [""]

    missing = sum(1 for c in commits if UNKNOWN in (c["who"], c["when"]))
    if missing:
        lines += [f"> ⚠️ Có **{missing}** cam kết còn thiếu người hoặc hạn (đánh dấu "
                  f"{UNKNOWN}). Chủ trì bổ sung giúp trước khi chốt.", ""]

    lines += ["---",
              "**Chủ trì trả lời `chốt` để tôi tạo Lark Docs + task.** "
              "Cần sửa thì nhắn `sửa: <nội dung>`. Chưa chốt thì tôi không publish gì cả."]
    return "\n".join(lines)


def parse_commitments(draft: str) -> list[dict]:
    """Đọc cam kết từ BẢNG trong bản nháp — không bóc lại từ text.

    Bóc lại bằng ``extract_commitments()`` trên markdown của nháp sẽ đếm mỗi cam kết 3 lần
    (mục Tóm tắt + bảng Cam kết + Next action) → tạo thừa 3× số task Lark. Bảng là nguồn
    sự thật duy nhất, và nó cũng phản ánh chỉnh sửa của chủ trì.
    """
    out: list[dict] = []
    in_table = False
    for line in draft.split("\n"):
        s = line.strip()
        if s.startswith("|---") or s.startswith("| Ai |"):
            in_table = True
            continue
        if in_table:
            if not s.startswith("|"):
                break
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) >= 3 and cells[1]:
                out.append({"who": cells[0], "what": cells[1], "when": cells[2]})
    # Dòng placeholder khi transcript không có cam kết nào — không tạo task cho nó.
    return [c for c in out if "không bóc được cam kết" not in c["what"]]


def find_pending_draft(ctx: dict) -> str:
    """Nháp đang chờ chốt, đọc ngược từ lượt hội thoại gần nhất. Rỗng = không có."""
    for turn in reversed(ctx.get("recent_turns") or []):
        if turn.get("role") == "assistant" and DRAFT_MARKER in (turn.get("text") or ""):
            return turn["text"]
    return ""


# ----------------------------- publish (chỉ khi đã chốt) -----------------------------

def _tenant_token() -> str:
    if not (LARK_APP_ID and LARK_APP_SECRET):
        raise RuntimeError("cần LARK_APP_ID + LARK_APP_SECRET để publish biên bản")
    r = requests.post(f"{LARK_DOMAIN}/open-apis/auth/v3/tenant_access_token/internal",
                      json={"app_id": LARK_APP_ID, "app_secret": LARK_APP_SECRET},
                      timeout=20)
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"lấy tenant token lỗi: {data.get('msg')}")
    return data["tenant_access_token"]


def publish_doc(title: str, content: str) -> str:
    """Tạo Lark Docs chứa biên bản đã chốt. Trả document_id (rỗng khi DRY_RUN).

    Scope Lark cần: ``docx:document:create``, ``docx:document:write_only``.
    """
    if DRY_RUN:
        print(f"[DRY_RUN] không tạo Lark Docs '{title}' ({len(content)} ký tự)")
        return ""
    h = {"Authorization": f"Bearer {_tenant_token()}", "Content-Type": "application/json"}
    body = {"title": title[:250]}
    if NOTE_FOLDER:
        body["folder_token"] = NOTE_FOLDER
    r = requests.post(f"{LARK_DOMAIN}/open-apis/docx/v1/documents", json=body,
                      headers=h, timeout=30)
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"tạo doc lỗi: {data.get('msg')}")
    doc_id = data["data"]["document"]["document_id"]

    # Mỗi đoạn một block text. Lark giới hạn số block/lần gọi → chia lô 50.
    blocks = [{"block_type": 2,
               "text": {"elements": [{"text_run": {"content": line[:2000]}}], "style": {}}}
              for line in content.split("\n") if line.strip()]
    for i in range(0, len(blocks), 50):
        rb = requests.post(
            f"{LARK_DOMAIN}/open-apis/docx/v1/documents/{doc_id}/blocks/{doc_id}/children",
            json={"children": blocks[i:i + 50], "index": -1}, headers=h, timeout=30)
        if (rb.json() or {}).get("code") != 0:
            raise RuntimeError(f"ghi nội dung doc lỗi: {rb.text[:200]}")
    return doc_id


def create_tasks(commitments: list[dict]) -> int:
    """Tạo task Lark cho từng cam kết. Trả số task đã tạo.

    Scope Lark cần: ``task:task:write``. Cam kết thiếu người thì vẫn tạo task nhưng
    **không gán ai** — để người thật gán, agent không đoán.
    """
    if DRY_RUN:
        print(f"[DRY_RUN] không tạo {len(commitments)} task")
        return 0
    h = {"Authorization": f"Bearer {_tenant_token()}", "Content-Type": "application/json"}
    made = 0
    for c in commitments:
        summary = f"[Họp KD] {c['what'][:100]}"
        desc = f"Người phụ trách: {c['who']}\nHạn: {c['when']}\n\nTrích từ biên bản họp."
        r = requests.post(f"{LARK_DOMAIN}/open-apis/task/v2/tasks",
                          json={"summary": summary, "description": desc},
                          headers=h, timeout=30)
        if (r.json() or {}).get("code") == 0:
            made += 1
        else:
            print(f"[task] tạo lỗi: {r.text[:160]}")
    return made


# ----------------------------- luồng chính -----------------------------

def handle_meeting_job(job: dict, ctx: dict, api, transcribe=None) -> str:
    """Xử lý một job liên quan biên bản họp. Trả nội dung sẽ gửi lại người dùng.

    ``api`` là hàm gọi platform của consumer (tránh trùng code auth).
    ``transcribe`` là ``TranscribeClient`` (None = tự khởi tạo khi cần).
    """
    payload = job.get("payload") or {}
    text = payload.get("text") or ""
    uref = payload.get("sender_open_id") or payload.get("user_ref") or ""

    # --- Nhánh 1: có người bảo chốt ---
    if _CONFIRM.match(text):
        draft = find_pending_draft(ctx)
        if not draft:
            return ("Tôi không thấy bản nháp nào đang chờ chốt trong luồng này. Gửi "
                    "recording cuộc họp để tôi dựng biên bản trước nhé.")
        owner = ((ctx.get("meta") or {}).get("draft_owner")
                 or payload.get("draft_owner") or "")
        if not is_chair(uref, owner):
            return ("Biên bản chỉ được chốt bởi **chủ trì cuộc họp**. Nhờ chủ trì trả lời "
                    "'chốt' ngay dưới bản nháp này giúp tôi — tôi chưa publish gì cả.")

        final = draft.replace(DRAFT_MARKER, "✅ **BIÊN BẢN ĐÃ CHỐT**")
        title = next((l.lstrip("# ").strip() for l in final.split("\n")
                      if l.startswith("## ")), "Biên bản họp Kinh Doanh")
        commits = parse_commitments(draft)

        doc_id = publish_doc(f"Biên bản — {title}", final)
        n_task = create_tasks(commits)

        # Lưu vào kho tri thức để lần sau tra được (vẫn phải qua người duyệt).
        try:
            api("POST", "/v1/self/brain/items", {
                "item_id": f"kd_mt_{job.get('session_id') or job['id']}",
                "kind": "knowledge",
                "title": f"Biên bản họp: {title}",
                "content": final[:4000],
                "domain": "kd-meeting",
                "tags": ["biên bản họp", "Kinh doanh Mate Made"],
                "scope": "shared",
                "source_ref": f"biên bản chốt {datetime.now(TZ).strftime('%d/%m/%Y')}",
            })
        except Exception as exc:
            print(f"[meeting] lưu brain lỗi: {exc}")

        done = [f"đã chốt biên bản **{title}**"]
        done.append(f"Lark Docs: `{doc_id}`" if doc_id else "Lark Docs: _bỏ qua (DRY_RUN)_")
        done.append(f"đã tạo **{n_task}** task từ {len(commits)} cam kết"
                    if n_task else f"task: _bỏ qua (DRY_RUN)_ — {len(commits)} cam kết")
        return "✅ " + " · ".join(done)

    # --- Nhánh 2: chủ trì yêu cầu sửa ---
    m = _EDIT.match(text)
    if m:
        draft = find_pending_draft(ctx)
        if not draft:
            return "Chưa có bản nháp nào để sửa. Gửi recording cuộc họp trước nhé."
        return (draft + f"\n\n> ✏️ **Ghi chú sửa của {uref or 'người dùng'}:** "
                        f"{m.group(1).strip()[:400]}\n> Bản nháp vẫn **CHƯA CHỐT**.")

    # --- Nhánh 3: có recording → dựng nháp ---
    src = payload.get("file_path") or payload.get("file_url") or payload.get("recording_url")
    if not src:
        return ("Gửi giúp tôi file recording (hoặc link Lark Minutes) của cuộc họp, tôi sẽ "
                "dựng biên bản nháp rồi xin chủ trì chốt.")

    if transcribe is None:
        from transcribe import TranscribeClient  # import tại chỗ: chỉ cần khi thật sự dùng
        transcribe = TranscribeClient()
    # Lỗi transcript cố ý KHÔNG bắt ở đây: để job vào DLQ và replay được từ console,
    # thay vì gửi ra nhóm một biên bản rỗng trông như thật.
    job_id = transcribe.submit(src)
    transcript = transcribe.wait(job_id)

    return build_draft(transcript, title=payload.get("meeting_title") or "")


# ----------------------------- chạy tay để thử -----------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Thử dựng biên bản nháp từ transcript có sẵn")
    ap.add_argument("--transcript", required=True, help="file text chứa transcript")
    ap.add_argument("--title", default="")
    args = ap.parse_args()
    with open(args.transcript, encoding="utf-8") as fh:
        print(build_draft(fh.read(), title=args.title))


if __name__ == "__main__":
    sys.exit(main())
