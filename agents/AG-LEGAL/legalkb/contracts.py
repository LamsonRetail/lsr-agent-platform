"""S2 — tạo hợp đồng từ template (PLAN Phase 3).

Luồng: chọn template → hỏi lần lượt field còn thiếu → xác nhận → điền docx → upload
Drive → **gate Pháp chế** → chỉ khi được duyệt mới gửi link cho người yêu cầu.

State đa lượt nằm ở bảng `contract_drafts`, KHÔNG nhồi vào prompt: người dùng bỏ dở hôm
nay, mai quay lại vẫn tiếp đúng field đang hỏi, kể cả sau khi restart container.

Registry template do legal team quản trên Drive: mỗi hợp đồng gồm
  - `<tên>.docx`        chứa placeholder {{ten_ben_a}}, {{gia_tri}}, …
  - `<tên>.fields.json` mô tả field  [{"key","label","required","hint"}]
Không có file .fields.json thì tự dò placeholder trong docx (mọi field coi là bắt buộc).
"""
import io
import json
import re
import time
import zipfile

DRAFT_MARK = "DRAFT — CHƯA CÓ HIỆU LỰC PHÁP LÝ"
PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
CANCEL_WORDS = ("huỷ", "huy", "thôi", "thoi", "dừng", "dung", "cancel")


# ---------------- đọc/điền docx (không cần python-docx cho phần dò) ----------------

def placeholders_in_docx(data):
    """Dò placeholder bằng cách đọc XML trong file docx — không phụ thuộc python-docx.

    Word hay cắt một chuỗi thành nhiều <w:t>, nên phải gộp text của cả document.xml lại
    rồi mới regex; nếu không sẽ bỏ sót đúng những placeholder bị cắt.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except (zipfile.BadZipFile, KeyError):
        return []
    text = re.sub(r"<[^>]+>", "", xml)
    seen, out = set(), []
    for k in PLACEHOLDER.findall(text):
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def fill_docx(data, values, mark=DRAFT_MARK):
    """Thay placeholder trong docx và đóng dấu DRAFT. Trả bytes file mới.

    Dùng python-docx để giữ định dạng. Word cắt placeholder qua nhiều `run` nên phải
    ghép text ở mức paragraph rồi mới thay — thay từng run sẽ trượt.
    """
    from docx import Document

    doc = Document(io.BytesIO(data))

    def sub(s):
        return PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), m.group(0))), s)

    def fix_paragraph(p):
        if "{{" not in p.text:
            return
        new = sub(p.text)
        if new == p.text:
            return
        for r in p.runs[1:]:
            r.text = ""
        if p.runs:
            p.runs[0].text = new
        else:
            p.add_run(new)

    for p in doc.paragraphs:
        fix_paragraph(p)
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    fix_paragraph(p)
    if mark:
        doc.add_paragraph("")
        doc.add_paragraph(f"[{mark}]")
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


# ---------------- registry ----------------

def sync_templates(lark, store, folder_token, log=print):
    """Nạp registry template từ Drive → bảng contract_templates.

    `folder_token` nhận **nhiều folder**, cách nhau bằng dấu phẩy. Lý do: trong Drive pháp
    chế có hai folder tên đều hợp lý cho mẫu hợp đồng ("Hop dong mau" và "Legal - standard
    agreements"), và đoán sai một cái là S2 không thấy mẫu nào mà vẫn báo thành công. Quét
    cả hai thì mẫu bỏ vào đâu cũng nhận được.

    **Không quét đệ quy vào folder con** — có chủ ý: folder bản thảo agent tự xuất
    ("BAN THAO DRAFT") nằm TRONG folder mẫu, quét đệ quy là bản thảo của chính mình thành
    mẫu cho lần sau, sai lệch tích luỹ mà không ai thấy.
    """
    tokens = [t.strip() for t in (folder_token or "").split(",") if t.strip()]
    if not tokens:
        return {"templates": 0, "skipped": "chưa cấu hình LEGAL_TEMPLATE_FOLDER"}
    files, seen = [], set()
    for tok in tokens:
        try:
            for f in lark.drive_files(tok):
                if f.get("type") == "folder" or f.get("token") in seen:
                    continue
                seen.add(f.get("token"))
                files.append(f)
        except Exception as exc:
            log(f"[template] không đọc được folder {tok[:12]}…: {exc}")
    specs = {f["name"]: f for f in files if f["name"].endswith(".fields.json")}
    n = 0
    for f in files:
        name = f.get("name", "")
        if not name.endswith(".docx"):
            continue
        tok, stem = f.get("token"), name[:-5]
        fields = None
        spec = specs.get(stem + ".fields.json")
        if spec:
            try:
                fields = json.loads(lark.drive_download(spec["token"]).decode("utf-8"))
            except Exception as exc:
                log(f"[template] {name}: .fields.json lỗi ({exc}) → dò placeholder")
        if fields is None:
            keys = placeholders_in_docx(lark.drive_download(tok))
            fields = [{"key": k, "label": k.replace("_", " "), "required": True}
                      for k in keys]
        store.write(
            "INSERT INTO contract_templates (key, name, file_token, lark_url, fields, "
            "edit_ts, status, updated_at) VALUES (?,?,?,?,?,?,'active',?) "
            "ON CONFLICT(key) DO UPDATE SET name=excluded.name, fields=excluded.fields, "
            "edit_ts=excluded.edit_ts, status='active', updated_at=excluded.updated_at",
            (f"drive:{tok}", stem, tok, f.get("url") or lark.drive_file_url(tok),
             json.dumps(fields, ensure_ascii=False), f.get("modified_time"), time.time()))
        n += 1
        log(f"[template] {stem}: {len(fields)} field")
    if not n:
        log(f"[template] {len(tokens)} folder, 0 file .docx — legal team chưa bỏ mẫu vào")
    return {"templates": n}


def templates(store):
    rows = store.query("SELECT * FROM contract_templates WHERE status='active' ORDER BY name")
    for r in rows:
        try:
            r["fields"] = json.loads(r.get("fields") or "[]")
        except json.JSONDecodeError:
            r["fields"] = []
    return rows


# Từ chung có trong hầu hết tên mẫu → không mang thông tin phân biệt. Nếu tính cả
# những từ này thì mọi câu chứa "hợp đồng" đều khớp mẫu đầu tiên trong kho.
GENERIC_WORDS = {"hop", "dong", "hd", "mau", "ban", "va", "voi", "cua"}


def pick_template(store, text):
    """Khớp mẫu theo phần ĐẶC TRƯNG của tên (bỏ 'hợp đồng', không phân biệt dấu).

    Chỉ trả về khi có đúng MỘT mẫu khớp trọn phần đặc trưng. Mơ hồ → None để Agent liệt
    kê cho người chọn, thay vì đoán sai loại hợp đồng.
    """
    from legalkb.gates import plain
    want = plain(text)
    hits = []
    for t in templates(store):
        words = [w for w in plain(t["name"]).split()
                 if w not in GENERIC_WORDS and len(w) > 1]
        if words and all(w in want for w in words):
            hits.append(t)
    return hits[0] if len(hits) == 1 else None


# ---------------- state đa lượt ----------------

class Drafts:
    def __init__(self, store):
        self.store = store

    def get(self, session_id):
        d = self.store.one("SELECT * FROM contract_drafts WHERE session_id=?", (session_id,))
        if d:
            try:
                d["values"] = json.loads(d.get("values_json") or "{}")
            except json.JSONDecodeError:
                d["values"] = {}
        return d

    def save(self, session_id, **f):
        cur = self.get(session_id)
        if "values" in f:
            f["values_json"] = json.dumps(f.pop("values"), ensure_ascii=False)
        f["updated_at"] = time.time()
        if cur:
            sets = ", ".join(f"{k}=?" for k in f)
            self.store.write(f"UPDATE contract_drafts SET {sets} WHERE session_id=?",
                             (*f.values(), session_id))
        else:
            cols = ["session_id", *f.keys()]
            self.store.write(
                f"INSERT INTO contract_drafts ({', '.join(cols)}) "
                f"VALUES ({', '.join('?' * len(cols))})", (session_id, *f.values()))
        return self.get(session_id)

    def drop(self, session_id):
        self.store.write("DELETE FROM contract_drafts WHERE session_id=?", (session_id,))


def missing_fields(template, values):
    return [f for f in template["fields"]
            if f.get("required", True) and not str(values.get(f["key"], "")).strip()]


def ask_next(template, values):
    """Câu hỏi cho field còn thiếu tiếp theo, hoặc None nếu đã đủ."""
    miss = missing_fields(template, values)
    if not miss:
        return None, None
    f = miss[0]
    q = f"Cho mình **{f.get('label') or f['key']}**?"
    if f.get("hint"):
        q += f"\n_({f['hint']})_"
    left = len(miss) - 1
    if left:
        q += f"\n\n_Còn {left} thông tin nữa._"
    return f["key"], q


def summary(template, values):
    lines = [f"**{template['name']}** — xác nhận thông tin:"]
    for f in template["fields"]:
        v = values.get(f["key"], "")
        lines.append(f"- {f.get('label') or f['key']}: **{v or '(trống)'}**")
    lines.append("\nĐúng thì trả lời **ok**; muốn sửa thì ghi ví dụ "
                 "`sửa gia_tri: 500 triệu`; bỏ thì ghi **huỷ**.")
    return "\n".join(lines)


EDIT_RE = re.compile(r"^\s*(?:sửa|sua)\s+([a-zA-Z0-9_]+)\s*[:=]\s*(.+)$", re.I | re.S)


def parse_edit(text):
    m = EDIT_RE.match(text or "")
    return (m.group(1), m.group(2).strip()) if m else (None, None)


def wants_cancel(text):
    t = (text or "").strip().lower()
    return any(t == w or t.startswith(w + " ") for w in CANCEL_WORDS)


_FEEDBACK_PROMPT = """Góp ý của bộ phận Pháp chế về bản thảo hợp đồng cần được quy về việc
sửa giá trị của các field. Trả về DUY NHẤT một JSON:

{"updates": {"<field_key>": "<giá trị mới>"}, "unresolved": "phần góp ý KHÔNG quy được về
field nào (chuỗi rỗng nếu không có)"}

Chỉ dùng đúng các field_key có trong danh sách. Không chắc thì để vào unresolved, TUYỆT
ĐỐI không đoán giá trị.

Field hiện có: {fields}
Giá trị hiện tại: {values}
Góp ý của Pháp chế: {comment}
"""


def apply_feedback(brain, template, values, comment, model=None):
    """Quy góp ý của Pháp chế về việc sửa field.

    Trả (values_mới, unresolved). Không quy được thì `unresolved` giữ nguyên văn góp ý —
    để Agent hỏi lại người yêu cầu thay vì tự đoán giá trị hợp đồng.
    """
    import json as _json
    import re as _re
    fields = ", ".join(f"{f['key']} ({f.get('label') or f['key']})"
                       for f in template["fields"])
    raw = brain.call_claude(
        _FEEDBACK_PROMPT.replace("{fields}", fields)
                        .replace("{values}", _json.dumps(values, ensure_ascii=False))
                        .replace("{comment}", comment or ""),
        model=model, timeout=90)
    m = _re.search(r"\{.*\}", raw or "", _re.S)
    if not m:
        return dict(values), (comment or "")
    try:
        out = _json.loads(m.group(0))
    except _json.JSONDecodeError:
        return dict(values), (comment or "")
    valid = {f["key"] for f in template["fields"]}
    new = dict(values)
    for k, v in (out.get("updates") or {}).items():
        if k in valid and str(v).strip():
            new[k] = str(v).strip()
    return new, (out.get("unresolved") or "").strip()
