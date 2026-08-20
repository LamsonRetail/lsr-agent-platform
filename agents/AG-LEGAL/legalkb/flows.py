"""Luồng nghiệp vụ S2–S5 + xử lý sau khi Pháp chế quyết định.

Tách khỏi `consumer.py` để consumer chỉ còn việc điều phối (poll job → router → gọi
flow → trả lời). Mọi flow ở đây nhận một `Bundle` nên test được bằng fake.
"""
import json
import os
import time
from dataclasses import dataclass

from legalkb import brain, contracts, news, review as review_mod, signing
from legalkb.gates import GATE, OBSERVE

DRAFT_FOLDER_ENV = "LEGAL_DRAFT_FOLDER"
TEMPLATE_FOLDER_ENV = "LEGAL_TEMPLATE_FOLDER"
# Folder gốc kho văn bản luật; bên dưới tách folder con theo nước (VN/, TH/…).
LAW_ARCHIVE_ENV = "LEGAL_DRIVE_FOLDER"
OK_WORDS = ("ok", "oke", "đúng", "dung", "xác nhận", "xac nhan", "đồng ý", "dong y", "yes")


@dataclass
class Bundle:
    pf: object                 # legalkb.platform.Platform
    store: object
    engine: object
    gates: object
    lark: object = None        # LarkKB — None khi chưa cấu hình app Lark
    model: str = None

    @property
    def drafts(self):
        return contracts.Drafts(self.store)

    @property
    def reviews(self):
        return review_mod.Reviews(self.store)

    @property
    def dossiers(self):
        return signing.Dossiers(self.store)


def _requester_name(bundle, uref):
    r = bundle.store.one("SELECT name FROM legal_roles WHERE open_id=?", (uref,))
    return (r or {}).get("name") or uref or "(không rõ)"


# ============================ S2 — tạo hợp đồng ============================

def s2_create(b, q, sid, uref, chat_id):
    """Hội thoại đa lượt tạo hợp đồng. State ở bảng contract_drafts."""
    d = b.drafts.get(sid)

    if contracts.wants_cancel(q) and d:
        b.drafts.drop(sid)
        return "Đã bỏ yêu cầu tạo hợp đồng. Cần làm lại thì nhắn mình."

    if d and d["status"] == "pending_review":
        return ("Bản thảo của bạn **đang chờ bộ phận Pháp chế kiểm tra**. "
                "Có kết quả mình báo ngay.")

    tmpls = contracts.templates(b.store)
    if not tmpls:
        return ("Kho mẫu hợp đồng chưa được cấu hình nên mình chưa tạo được. "
                "Bạn nhờ bộ phận Pháp chế bổ sung mẫu vào folder mẫu trên Drive.")

    # --- chọn template ---
    if not d or not d.get("template_key"):
        t = contracts.pick_template(b.store, q)
        if not t:
            lines = ["Mình có các mẫu sau — bạn muốn dùng mẫu nào?"]
            lines += [f"- **{x['name']}**" for x in tmpls]
            b.drafts.save(sid, status="collecting", requester=uref, chat_id=chat_id)
            return "\n".join(lines)
        d = b.drafts.save(sid, template_key=t["key"], status="collecting",
                          values={}, requester=uref, chat_id=chat_id)

    t = next((x for x in tmpls if x["key"] == d["template_key"]), None)
    if not t:
        b.drafts.drop(sid)
        return "Mẫu bạn chọn không còn trong kho. Bạn nhắn lại loại hợp đồng cần tạo nhé."

    values = dict(d.get("values") or {})

    # --- đang xác nhận tóm tắt ---
    if d["status"] == "confirming":
        key, val = contracts.parse_edit(q)
        if key:
            values[key] = val
            b.drafts.save(sid, values=values)
            return contracts.summary(t, values)
        if q.strip().lower() in OK_WORDS:
            return _build_and_gate(b, t, values, sid, uref, chat_id, d)
        return ("Mình chưa rõ ý bạn.\n\n" + contracts.summary(t, values))

    # --- đang thu thập field ---
    if d.get("asking"):
        values[d["asking"]] = q.strip()
    key, question = contracts.ask_next(t, values)
    if question:
        b.drafts.save(sid, values=values, asking=key, status="collecting")
        return question
    b.drafts.save(sid, values=values, asking=None, status="confirming")
    return contracts.summary(t, values)


def _build_and_gate(b, t, values, sid, uref, chat_id, d):
    """Điền docx → upload Drive → mở gate Pháp chế. KHÔNG gửi cho người yêu cầu."""
    folder = os.environ.get(DRAFT_FOLDER_ENV)
    if not (b.lark and folder):
        return ("Mình điền xong nội dung nhưng **chưa xuất được file**: thiếu cấu hình "
                f"`{DRAFT_FOLDER_ENV}` (folder Drive lưu bản thảo). Nhờ admin bổ sung.")
    try:
        raw = b.lark.drive_download(t["file_token"])
        filled = contracts.fill_docx(raw, values)
        stamp = time.strftime("%Y%m%d-%H%M")
        tok = b.lark.drive_upload(folder, f"DRAFT-{t['name']}-{stamp}.docx", filled)
        url = b.lark.drive_file_url(tok)
    except Exception as exc:
        return f"Không xuất được file bản thảo: {exc}. Mình đã ghi nhận sự cố."

    round_no = int(d.get("round") or 1)
    gid = b.gates.open(
        "s2_draft", GATE, risk="medium", session_id=sid, requester_ref=uref,
        round_no=round_no,
        title=f"{t['name']} (vòng {round_no})",
        payload={"chat_id": chat_id, "requester_name": _requester_name(b, uref),
                 "summary": "; ".join(f"{k}={v}" for k, v in list(values.items())[:6]),
                 "file": url, "template": t["name"]})
    b.drafts.save(sid, status="pending_review", gate_id=gid, out_url=url, values=values)
    return (f"Đã soạn xong bản thảo **{t['name']}** (đóng dấu DRAFT) và **chuyển bộ phận "
            f"Pháp chế kiểm tra** trước khi gửi bạn.\n"
            f"Mình sẽ báo lại ngay khi có kết quả — thường trong vài giờ làm việc.")


# ============================ S3 — review hợp đồng đối tác ============================

def s3_review(b, job, q, sid, uref, chat_id):
    payload = job.get("payload") or {}
    file_key, file_name = payload.get("file_key"), payload.get("file_name") or "hợp đồng"
    if not file_key:
        prev = b.reviews.latest(sid)
        if prev and prev["status"] == "issues_sent":
            return ("Bạn gửi lại **file hợp đồng đã sửa** để mình rà vòng tiếp nhé "
                    "(đính kèm vào chat này).")
        return ("Bạn **đính kèm file hợp đồng** (PDF hoặc DOCX) vào chat này, mình rà soát "
                "theo checklist của Pháp chế rồi báo lại các điểm cần sửa.")

    from legalkb import extract
    try:
        data = b.pf.lark_resource(payload.get("message_id") or "", file_key,
                                  app_id=(job.get("reply_to") or {}).get("app_id") or "")
        text = extract.from_bytes(data, file_name)
    except extract.ExtractError as exc:
        return f"Mình chưa đọc được file: {exc}"
    except Exception as exc:
        return (f"Không tải được file từ Lark ({exc}). Bạn thử gửi lại, "
                f"hoặc đưa file vào Drive rồi gửi link.")

    r = b.reviews.open(sid, uref, chat_id, file_name)
    checklist, has_cl = review_mod.get_checklist(b.engine, b.store)
    findings, clean, note = review_mod.analyse(brain, text, checklist, file_name,
                                               model=b.model)
    b.reviews.save(r["id"], findings=findings, status="resolved" if clean else "issues_sent")
    report = review_mod.render_report(findings, clean, note, file_name, has_cl, r["round"])

    if clean:
        gid = b.gates.open(
            "s3_review", GATE, risk="medium", session_id=sid, requester_ref=uref,
            round_no=r["round"], title=f"Xác nhận hợp đồng: {file_name}",
            payload={"chat_id": chat_id, "requester_name": _requester_name(b, uref),
                     "summary": note or "Không còn vấn đề chặn",
                     "file": file_name, "review_id": r["id"]})
        b.reviews.save(r["id"], status="pending_approval", gate_id=gid)
    else:
        high = [f for f in findings if f.get("severity") == "high"]
        b.gates.open("s3_review", OBSERVE, risk="high" if high else "medium",
                     session_id=sid, requester_ref=uref,
                     title=f"Đang rà soát: {file_name}",
                     payload={"chat_id": chat_id, "summary": f"{len(findings)} điểm cần sửa",
                              "file": file_name, "review_id": r["id"]}, notify=bool(high))
    return report


# ============================ S4 — hỏi về văn bản luật mới ============================

def s4_answer(b, q):
    rows = b.store.query(
        "SELECT * FROM legal_news_items WHERE status='published' ORDER BY found_at DESC "
        "LIMIT 5")
    if not rows:
        return ("Hiện chưa có bản tin văn bản pháp luật nào được Pháp chế phê duyệt để "
                "công bố. Câu hỏi về quy định cụ thể thì bạn hỏi trực tiếp, mình tra "
                "trong kho tài liệu.")
    lines = ["**Văn bản mới nhất đã được Pháp chế duyệt:**"]
    for r in rows:
        no = f"`{r['doc_no']}` " if r.get("doc_no") else ""
        lines.append(f"- {no}[{r['title']}]({r['url']})")
    lines.append("\nCần chi tiết văn bản nào thì nhắn mình.")
    return "\n".join(lines)


def index_legal_docs(b, keys, log=print):
    """Đưa văn bản đã lưu vào **index bộ nhớ** — để sau này biết truy xuất từ đâu.

    Mỗi mục ghi: nước, số hiệu, tiêu đề, link nguồn gốc, link bản lưu trong Drive. Vào
    brain của platform nên `/v1/self/context` tra được bằng RAG mỗi lượt: hỏi "quy định
    nhãn hàng hoá Thái Lan có gì mới" thì agent thấy ngay mục này và chỉ đúng chỗ lấy.

    Chỉ index **dữ kiện + con trỏ**, không index phần model diễn giải — phần đó còn phải
    qua gate Pháp chế (review §B).
    """
    n = 0
    for key in keys:
        it = b.store.one("SELECT * FROM legal_news_items WHERE key=?", (key,))
        if not it or not it.get("url"):
            continue
        cc = it.get("country") or "VN"
        lines = [f"Nước: {cc}",
                 f"Số hiệu: {it.get('doc_no') or '(không có số hiệu trong tiêu đề)'}",
                 f"Tiêu đề: {it.get('title')}",
                 f"Nguồn gốc: {it['url']}"]
        if it.get("drive_url"):
            lines.append(f"Bản lưu nội bộ (Lark Drive): {it['drive_url']}")
        else:
            lines.append("Bản lưu nội bộ: CHƯA có — chỉ còn link nguồn gốc")
        index_brain(b, f"[Văn bản pháp luật · {cc}] "
                       f"{it.get('doc_no') or ''} {it.get('title')}".strip(),
                    "\n".join(lines), it.get("drive_url") or it["url"])
        n += 1
    if n:
        log(f"[news] đã index {n} văn bản vào bộ nhớ")
    return n


def news_cycle(b, group_chat_id, log=print):
    """Crawl → lưu bản gốc về Drive → index → tóm tắt → **mở gate** cho digest.

    Thứ tự có chủ ý: **lưu + index trước, gate sau**. Bản gốc và con trỏ truy xuất là dữ
    kiện, không cần ai duyệt và cần có ngay để tra khi phát sinh việc. Chỉ phần model
    diễn giải (digest) mới phải chờ Pháp chế (review §B).
    """
    keys = news.crawl(b.store, log=log)
    if not keys:
        log("[news] không có văn bản mới")
        return None
    news.archive(b.store, b.lark, keys, os.environ.get(LAW_ARCHIVE_ENV), log=log)
    index_legal_docs(b, keys, log=log)
    kept = news.summarise(b.store, brain, keys, model=b.model, log=log)
    digest, n = news.render_digest(b.store, kept)
    if not n:
        log("[news] mọi mục đều bị loại (thiếu link nguồn)")
        return None
    gid = b.gates.open(
        "s4_digest", GATE, risk="medium",
        title=f"Digest {n} văn bản mới — chờ duyệt trước khi gửi & nạp KB",
        payload={"summary": f"{n} văn bản", "keys": kept, "digest": digest},
        sla_hours=float(os.environ.get("DIGEST_SLA_HOURS", "8")))
    log(f"[news] mở gate #{gid} cho {n} văn bản")
    return gid


# ============================ S5 — trình ký (shadow) ============================

def s5_dossier(b, job, q, sid, uref, chat_id):
    """Shadow mode: hồ sơ vào qua chat. Khi core mở broker Approval (C5) thì chỉ đổi
    phần vào/ra, logic Bước 3/5 dùng lại."""
    payload = job.get("payload") or {}
    file_key = payload.get("file_key")
    if not file_key:
        return ("Luồng **trình ký** đang chạy thử song song với quy trình hiện tại "
                "(chưa nối vào Lark Approval — đang chờ platform mở kết nối).\n"
                "Trong lúc chờ: bạn đính kèm hồ sơ vào chat này, ghi rõ loại hợp đồng và "
                "đang ở **Bước 3** hay **Bước 5**, mình rà soát rồi trả báo cáo.")

    from legalkb import extract
    try:
        data = b.pf.lark_resource(payload.get("message_id") or "", file_key,
                                  app_id=(job.get("reply_to") or {}).get("app_id") or "")
        text = extract.from_bytes(data, payload.get("file_name") or "hồ sơ")
    except Exception as exc:
        return f"Mình chưa đọc được hồ sơ: {exc}"

    code = f"shadow-{sid}-{int(time.time())}"
    ctype = _guess_type(b, q)
    is_step5 = "bước 5" in (q or "").lower() or "buoc 5" in (q or "").lower()
    d = b.dossiers.open(code, contract_type=ctype, requester=uref, chat_id=chat_id)
    policy, _ = review_mod.get_checklist(b.engine, b.store)

    if is_step5:
        res = signing.step5(brain, text, policy, step4_notes=q, model=b.model)
        report = signing.render_step5(res, bounce_count=int(d.get("bounce_count") or 0))
        b.dossiers.save(code, step="step5", step5_report=report,
                        bounce_count=int(d.get("bounce_count") or 0) + (1 if res["blocking"] else 0),
                        status="open" if res["blocking"] else "done")
        kind, risk = "s5_step5", ("high" if res["blocking"] else "low")
    else:
        res = signing.step3(brain, b.store, text, ctype, policy, model=b.model)
        report = signing.render_step3(res, ctype)
        b.dossiers.save(code, step="step3", step3_report=report)
        kind = "s5_step3"
        risk = "high" if (res["missing_docs"] or
                          any(f.get("severity") == "high" for f in res["findings"])) else "low"

    # Observe: báo Pháp chế nhưng KHÔNG chặn hồ sơ. SLA ngắn → quá hạn tự thông.
    b.gates.open(kind, OBSERVE, risk=risk, session_id=sid, requester_ref=uref,
                 title=f"{code} · {ctype or 'chưa rõ loại'}",
                 payload={"chat_id": chat_id, "summary": report[:400]},
                 sla_hours=signing.SLA_MINUTES / 60.0, notify=(risk == "high"))
    return report


def _guess_type(b, q):
    ql = (q or "").lower()
    for r in b.store.query("SELECT contract_type FROM dossier_checklists"):
        ct = r["contract_type"]
        if ct and ct != "*" and ct.lower() in ql:
            return ct
    return None


# ============================ sau khi Pháp chế quyết định ============================

def dispatch_decision(b, gate, action, comment):
    """Thực thi hệ quả của quyết định. Trả text phản hồi thêm cho group (hoặc None).

    Đây là chỗ biến "đã bấm duyệt" thành việc thật: gửi bản thảo cho người yêu cầu, phát
    hành digest, báo kết quả review. Không có bước này thì gate chỉ là cái nhãn.
    """
    kind = gate["kind"]
    if kind == "s2_draft":
        return _after_s2(b, gate, action, comment)
    if kind == "s3_review":
        return _after_s3(b, gate, action, comment)
    if kind == "s4_digest":
        return _after_s4(b, gate, action, comment)
    return None


def index_brain(b, title, content, source_url=None):
    """Ghi một mục vào brain riêng của agent — ĐÂY là bộ nhớ index.

    Vì sao dùng `/v1/self/brain/items` chứ không bảng riêng: brain của platform được
    `/v1/self/context` tra bằng RAG mỗi lượt, nên cái ghi ở đây tự động quay lại trong
    ngữ cảnh câu trả lời sau — đúng nguyên tắc "bộ nhớ ở platform" (CLAUDE.md #1). Bảng
    riêng thì chỉ agent này đọc được và console không thấy.

    `source_url` bắt buộc có khi index file/hợp đồng: không có link đối chứng thì mục đó
    thành nguồn không kiểm được — đúng thứ golden set đang chặn.
    """
    return b.pf.add_brain_item(title[:200], content[:8000], status="approved",
                               source_url=source_url)


def index_templates(b, log=print):
    """Index NỘI DUNG từng file mẫu hợp đồng, không chỉ tên.

    Mẫu nằm ở Drive (.docx) hoặc Wiki (Lark Doc). Đọc text ra rồi ghi vào brain kèm link,
    để agent trả lời được "mẫu X có điều khoản gì" mà không phải tải lại file mỗi lần.
    """
    n = 0
    for t in contracts.templates(b.store):
        if b.store.get_meta(f"idx:tpl:{t['key']}") == (t.get("edit_ts") or ""):
            continue                      # chưa đổi từ lần index trước
        try:
            raw = b.lark.drive_download(t["file_token"])
            from legalkb import extract
            body = extract.from_bytes(raw, t["name"] + ".docx")
        except Exception as exc:
            log(f"[index] mẫu {t['name']}: {exc}")
            continue
        fields = ", ".join(f.get("key", "") for f in t.get("fields") or [])
        index_brain(b, f"[Mẫu hợp đồng] {t['name']}",
                    f"Các trường cần điền: {fields}\n\n{body}", t.get("lark_url"))
        b.store.set_meta(f"idx:tpl:{t['key']}", t.get("edit_ts") or "")
        n += 1
        log(f"[index] mẫu {t['name']}: đã index {len(body)} ký tự")
    return n


def index_sent_contract(b, kind, name, url, summary, requester=None, reviewer=None):
    """Index một hợp đồng ĐÃ GỬI (bản thảo được duyệt, hoặc HĐ đối tác đã xác nhận).

    Nhờ mục này agent trả được các câu kiểu "đã làm hợp đồng nào với công ty X",
    "lần trước Pháp chế yêu cầu sửa gì" — và người sau tra lại được bằng link.
    """
    when = time.strftime("%d/%m/%Y")
    meta = [f"Ngày: {when}", f"Loại: {kind}"]
    if requester:
        meta.append(f"Người yêu cầu: {requester}")
    if reviewer:
        meta.append(f"Người duyệt: {reviewer}")
    return index_brain(b, f"[Hợp đồng đã gửi] {name} ({when})",
                       "\n".join(meta) + f"\n\n{summary}", url)


def _notify(b, gate, text):
    chat_id = (gate.get("payload") or {}).get("chat_id")
    return b.pf.lark_send(chat_id, markdown=text) if chat_id else False


def _after_s2(b, gate, action, comment):
    sid = gate.get("session_id")
    d = b.drafts.get(sid) if sid else None
    url = (gate.get("payload") or {}).get("file")
    today = time.strftime("%d/%m/%Y")
    if action == "approve":
        _notify(b, gate, f"✅ Bản thảo **{(gate.get('payload') or {}).get('template', '')}** "
                         f"đã **qua Pháp chế kiểm tra** ngày {today}.\n"
                         f"File (dấu DRAFT): {url}\n\n"
                         f"_Bản thảo chưa có hiệu lực pháp lý; việc ký theo quy trình "
                         f"trình ký của công ty._")
        if d:
            b.drafts.save(sid, status="done")
        p = gate.get("payload") or {}
        index_sent_contract(b, p.get("template") or "hợp đồng",
                            p.get("template") or "(không rõ mẫu)", url,
                            p.get("summary") or "", p.get("requester_name"),
                            gate.get("reviewer"))
        return None
    if action == "reject":
        _notify(b, gate, f"❌ Pháp chế **không thông qua** bản thảo.\nLý do: {comment}\n\n"
                         f"Bạn liên hệ bộ phận Pháp chế để được hướng dẫn.")
        if d:
            b.drafts.save(sid, status="cancelled")
        return None

    # changes: quy góp ý về field, sửa rồi mở gate lại
    if not d:
        _notify(b, gate, f"Pháp chế góp ý bản thảo: {comment}")
        return None
    t = next((x for x in contracts.templates(b.store) if x["key"] == d["template_key"]), None)
    if not t:
        return "Mẫu hợp đồng không còn trong kho — không sửa lại được tự động."
    values, unresolved = contracts.apply_feedback(brain, t, d.get("values") or {},
                                                  comment, model=b.model)
    changed = {k: v for k, v in values.items() if (d.get("values") or {}).get(k) != v}
    b.drafts.save(sid, values=values, round=int(d.get("round") or 1) + 1,
                  status="revising")
    if unresolved or not changed:
        _notify(b, gate, f"Pháp chế yêu cầu chỉnh bản thảo: {comment}\n\n"
                         f"Bạn cho mình thông tin cần sửa theo dạng "
                         f"`sửa <tên_field>: <giá trị>` nhé.")
        b.drafts.save(sid, status="confirming")
        return (f"Đã chuyển góp ý cho người yêu cầu. Phần chưa quy được về field: "
                f"_{unresolved or 'không xác định field nào'}_ — Agent **không đoán** giá "
                f"trị hợp đồng.")
    out = _build_and_gate(b, t, values, sid, gate.get("requester_ref"),
                          (gate.get("payload") or {}).get("chat_id"), b.drafts.get(sid))
    _notify(b, gate, f"Pháp chế yêu cầu chỉnh: {comment}\nMình đã sửa và gửi lại Pháp chế "
                     f"kiểm tra.")
    return f"Đã áp góp ý ({', '.join(changed)}) và mở gate mới. {out[:120]}…"


def _after_s3(b, gate, action, comment):
    rid = (gate.get("payload") or {}).get("review_id")
    if action == "approve":
        _notify(b, gate, "✅ Hợp đồng đã được **người có thẩm quyền xác nhận**. "
                         "Bạn tiếp tục theo quy trình trình ký của công ty.")
        if rid:
            r = b.reviews.save(rid, status="approved")
            index_sent_contract(
                b, "hợp đồng đối tác (đã rà soát)", r.get("file_name") or "hợp đồng",
                None, f"Đã xác nhận sau {r.get('round')} vòng rà soát. "
                      f"{len(r.get('findings') or [])} điểm đã xử lý.",
                r.get("requester"), gate.get("reviewer"))
    elif action == "reject":
        _notify(b, gate, f"❌ Hợp đồng **chưa được thông qua**.\nLý do: {comment}")
        if rid:
            b.reviews.save(rid, status="rejected")
    else:
        _notify(b, gate, f"Pháp chế yêu cầu làm rõ thêm: {comment}\n"
                         f"Bạn xử lý rồi gửi lại file để mình rà vòng tiếp.")
        if rid:
            b.reviews.save(rid, status="issues_sent")
    return None


def _after_s4(b, gate, action, comment):
    p = gate.get("payload") or {}
    keys, digest = list(p.get("keys") or []), p.get("digest") or ""
    group = b.gates.group
    if action == "reject":
        for k in keys:
            b.store.write("UPDATE legal_news_items SET status='dropped' WHERE key=?", (k,))
        return "Đã bỏ digest này — **không gửi, không nạp KB**."
    if action == "changes":
        drop = {news.doc_no_of(w) for w in (comment or "").split()} - {None}
        keep = [k for k in keys
                if not any((b.store.one("SELECT doc_no FROM legal_news_items WHERE key=?",
                                        (k,)) or {}).get("doc_no") == d for d in drop)]
        if len(keep) == len(keys):
            return ("Chưa rõ cần bỏ mục nào. Ghi kèm **số hiệu văn bản** cần loại, "
                    "ví dụ `#12 sửa: bỏ 15/2026/NĐ-CP`.")
        for k in set(keys) - set(keep):
            b.store.write("UPDATE legal_news_items SET status='dropped' WHERE key=?", (k,))
        digest2, n = news.render_digest(b.store, keep)
        if not n:
            return "Sau khi loại thì không còn mục nào — digest bị bỏ."
        res = news.publish(b.store, b.engine, b.pf, b.lark, keep, digest2, group,
                           drive_folder=os.environ.get("LEGAL_DRIVE_FOLDER"))
        return (f"Đã loại {len(keys) - n} mục và phát hành {n} mục. "
                f"Nạp KB: {res['nlm']} source.")
    res = news.publish(b.store, b.engine, b.pf, b.lark, keys, digest, group,
                       drive_folder=os.environ.get("LEGAL_DRIVE_FOLDER"))
    return (f"Đã phát hành digest ({len(keys)} văn bản). "
            f"Lưu Drive: {'có' if res['drive'] else 'không'} · nạp KB: {res['nlm']} source.")
