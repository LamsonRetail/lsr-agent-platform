"""S4 — tổng hợp nghị định/hướng dẫn luật (PLAN Phase 5).

Luồng: crawl nguồn uy tín → dedupe theo số hiệu văn bản → Claude tóm tắt → **gate Pháp
chế** → chỉ khi được duyệt mới gửi digest + lưu file về Drive + nạp notebook.

Hai luật cứng theo góp ý review §B:
  1. **Mục nào không trích được link nguồn thì LOẠI** khỏi digest (chống bịa nguồn).
  2. **Chưa duyệt = không gửi, không nạp KB.**

Chạy như thread trong consumer, không phải container riêng: NotebookLM chỉ cho một phiên
mỗi tài khoản (xem CLAUDE.md).
"""
import html as html_mod
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

# Nguồn khởi tạo — TRẠNG THÁI ĐÃ KIỂM THẬT ngày 19/08/2026, không phải phỏng đoán.
# (name, url, kind, country, link_pattern, active, note)
#
# Bài học: bản seed trước liệt kê 4 nguồn VN "uy tín" theo suy đoán, kiểm lại thì 3/4
# chết. Nguồn chết mà để active thì crawler báo lỗi mỗi tuần và không ai biết là do seed
# sai. Nên nguồn chưa kiểm được **để inactive kèm `note` nói rõ cần gì để bật**.
DEFAULT_SOURCES = [
    # --- Việt Nam ---
    ("LuatVietnam — văn bản mới", "https://luatvietnam.vn/rss/van-ban-moi.rss",
     "rss", "VN", None, 1, "đã kiểm 19/08: RSS trả 50 item, dùng được"),
    ("Thư viện pháp luật", "https://thuvienphapluat.vn/rss/vanban.rss",
     "rss", "VN", None, 0,
     "19/08: URL trả HTML, 0 item — cần đường RSS đúng hoặc chuyển sang kind=html + link_pattern"),
    ("Cổng TTĐT Chính phủ", "https://chinhphu.vn/rss/van-ban-chi-dao-dieu-hanh.rss",
     "rss", "VN", None, 0, "19/08: HTTP 404 — cần URL feed hiện hành"),
    ("Công báo Chính phủ", "https://congbao.chinhphu.vn/rss",
     "rss", "VN", None, 0, "19/08: 200 nhưng 0 item và 0 link (trang render bằng JS)"),
    # --- Thái Lan --- chưa tìm được nguồn nào lấy được tự động
    ("ราชกิจจานุเบกษา — Royal Gazette", "https://ratchakitcha.soc.go.th/",
     "html", "TH", None, 0,
     "19/08: HTTP 403 kể cả với UA browser (WAF chặn bot) — cần nguồn khác hoặc thoả thuận truy cập"),
    ("Krisdika — Council of State", "https://www.krisdika.go.th/web/guest/law",
     "html", "TH", None, 0, "19/08: HTTP 404 — cần URL trang danh sách văn bản hiện hành"),
    ("Thai Revenue Department", "https://www.rd.go.th/",
     "html", "TH", None, 0,
     "19/08: 200 nhưng là trang JS, chưa có link_pattern — cần URL trang danh sách + mẫu link"),
]

# Số hiệu văn bản VN: 12/2026/NĐ-CP, 05/2026/TT-BTC, 1234/QĐ-TTg…
DOC_NO = re.compile(r"\b(\d{1,4}\s*/\s*(?:\d{4}\s*/\s*)?[A-ZĐ]{2,}(?:\s*-\s*[A-ZĐ]{2,})?)\b")

_SUMMARY_PROMPT = """Tóm tắt văn bản pháp luật dưới đây cho bộ phận pháp chế của một công
ty BÁN LẺ (Lam Son Retail). Trả về DUY NHẤT một JSON:

{"scope": "phạm vi áp dụng, 1 câu", "effective": "hiệu lực từ khi nào (không rõ thì ghi
'chưa rõ')", "impact": "tác động tới hoạt động bán lẻ của LSR, 1-2 câu; không liên quan
thì ghi 'không tác động trực tiếp'"}

Chỉ dựa vào tiêu đề và nội dung đưa vào, KHÔNG suy diễn thêm điều khoản không có.

Số hiệu: {doc_no}
Tiêu đề: {title}
Nội dung: {body}
"""


def seed_sources(store, sources=None):
    """Nạp nguồn. KHÔNG bật lại nguồn admin đã tắt tay: `active` chỉ set lúc tạo mới."""
    n = 0
    for name, url, kind, country, pattern, active, note in (sources or DEFAULT_SOURCES):
        n += bool(store.write(
            "INSERT INTO legal_news_sources (name, url, kind, country, link_pattern, "
            "note, active) VALUES (?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET "
            "name=excluded.name, kind=excluded.kind, country=excluded.country, "
            "link_pattern=excluded.link_pattern, note=excluded.note",
            (name, url, kind, country, pattern, note, active)))
    return n


def sources(store, only_active=True):
    sql = "SELECT * FROM legal_news_sources"
    if only_active:
        sql += " WHERE active=1"
    return store.query(sql + " ORDER BY id")


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def parse_rss(xml):
    """Parse RSS tối giản bằng regex — đủ cho <item><title><link>.

    Không dùng thư viện ngoài, và cố tình KHÔNG parse HTML tuỳ ý: nguồn nào không có RSS
    thì báo lỗi nguồn đó, hơn là bịa item từ trang HTML đổi layout liên tục.
    """
    items = []
    for block in re.findall(r"<item[\s>].*?</item>", xml, re.S | re.I):
        def tag(name):
            m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", block, re.S | re.I)
            if not m:
                return ""
            v = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", m.group(1), flags=re.S)
            return html_mod.unescape(re.sub(r"<[^>]+>", "", v)).strip()
        title, link = tag("title"), tag("link")
        if title and link:
            items.append({"title": title, "url": link, "desc": tag("description")[:2000]})
    return items


def doc_no_of(text):
    m = DOC_NO.search(text or "")
    return re.sub(r"\s+", "", m.group(1)) if m else None


def parse_html(html, base_url, link_pattern):
    """Lấy danh sách văn bản từ trang HTML theo regex cấu hình riêng của nguồn.

    Cố tình KHÔNG parse HTML tuỳ ý: mỗi cổng pháp luật một layout, đoán chung sẽ ra rác mà
    vẫn "thành công". Có `link_pattern` thì lấy đúng link khớp; không có thì báo lỗi để
    admin biết nguồn này còn thiếu cấu hình, thay vì im lặng trả 0 item.
    """
    if not link_pattern:
        raise RuntimeError("nguồn html thiếu link_pattern — thêm ở console rồi bật lại")
    out, seen = [], set()
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        href, label = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        if not re.search(link_pattern, href):
            continue
        url = urllib.parse.urljoin(base_url, href)
        title = html_mod.unescape(re.sub(r"\s+", " ", label)).strip()
        if not title or url in seen:
            continue
        seen.add(url)
        out.append({"title": title, "url": url, "desc": ""})
    return out


def crawl(store, log=print):
    """Quét mọi nguồn active. Lỗi một nguồn KHÔNG làm chết cả pipeline."""
    found = []
    for s in sources(store):
        try:
            body = fetch(s["url"])
            if s["kind"] == "rss":
                items = parse_rss(body)
            elif s["kind"] == "html":
                items = parse_html(body, s["url"], s.get("link_pattern"))
            else:
                raise RuntimeError(f"kind '{s['kind']}' chưa hỗ trợ (rss | html)")
            if not items:
                raise RuntimeError("lấy được trang nhưng 0 văn bản — kiểm URL/link_pattern")
            new = 0
            for it in items:
                no = doc_no_of(it["title"]) or doc_no_of(it["desc"])
                key = no or it["url"]
                if store.one("SELECT key FROM legal_news_items WHERE key=?", (key,)):
                    continue                       # dedupe theo số hiệu, rồi tới URL
                store.write(
                    "INSERT INTO legal_news_items (key, source_id, country, doc_no, title, "
                    "url, status, found_at) VALUES (?,?,?,?,?,?,'new',?)",
                    (key, s["id"], s.get("country") or "VN", no, it["title"][:500],
                     it["url"], time.time()))
                found.append(key)
                new += 1
            store.write("UPDATE legal_news_sources SET last_run=?, last_error=NULL, "
                        "n_items=n_items+? WHERE id=?", (time.time(), new, s["id"]))
            log(f"[news] {s['name']}: +{new}/{len(items)}")
        except Exception as exc:
            store.write("UPDATE legal_news_sources SET last_run=?, last_error=? WHERE id=?",
                        (time.time(), str(exc)[:300], s["id"]))
            log(f"[news] {s['name']} LỖI: {exc}")
    return found


def summarise(store, brain, keys, model=None, log=print):
    """Tóm tắt các item mới. **Mục không có URL nguồn thì loại** — không bịa nguồn."""
    kept = []
    for key in keys:
        it = store.one("SELECT * FROM legal_news_items WHERE key=?", (key,))
        if not it:
            continue
        if not (it.get("url") or "").startswith("http"):
            store.write("UPDATE legal_news_items SET status='dropped' WHERE key=?", (key,))
            log(f"[news] loại {key}: không có link nguồn hợp lệ")
            continue
        raw = brain.call_claude(
            _SUMMARY_PROMPT.replace("{doc_no}", it.get("doc_no") or "(không rõ)")
                           .replace("{title}", it.get("title") or "")
                           .replace("{body}", (it.get("summary") or "")[:6000]),
            model=model, timeout=120)
        m = re.search(r"\{.*\}", raw or "", re.S)
        data = {}
        if m:
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                data = {}
        text = json.dumps({"scope": data.get("scope", ""),
                           "effective": data.get("effective", "chưa rõ"),
                           "impact": data.get("impact", "chưa đánh giá được")},
                          ensure_ascii=False)
        store.write("UPDATE legal_news_items SET summary=?, status='in_digest' WHERE key=?",
                    (text, key))
        kept.append(key)
    return kept


def _safe_name(s, cap=90):
    s = re.sub(r"[\\/:*?\"<>|\r\n\t]+", " ", s or "").strip()
    return re.sub(r"\s+", " ", s)[:cap] or "van-ban"


def archive(store, lark, keys, root_folder, log=print):
    """Tải VĂN BẢN GỐC về Lark Drive, mỗi nước một folder con.

    Đây là phần trả lời câu "khi có vấn đề phát sinh thì biết truy xuất từ đâu": bản gốc
    nằm trong Drive của công ty, không phụ thuộc nguồn ngoài còn sống hay không (cổng
    pháp luật đổi URL/xoá bài là chuyện thường).

    Lưu bản gốc KHÔNG cần ai duyệt — nó là tài liệu nhà nước, không phải nội dung AI sinh
    ra. Phần tóm tắt của model thì vẫn phải qua gate Pháp chế (review §B).
    """
    if not (lark and root_folder):
        log("[news] chưa cấu hình Drive folder → bỏ qua bước lưu bản gốc")
        return 0
    folders, n = {}, 0
    for key in keys:
        it = store.one("SELECT * FROM legal_news_items WHERE key=?", (key,))
        if not it or it.get("drive_url"):
            continue
        cc = it.get("country") or "VN"
        if cc not in folders:
            try:
                folders[cc] = lark.ensure_folder(root_folder, cc)
            except Exception as exc:
                log(f"[news] không tạo được folder {cc}: {exc}")
                continue
        try:
            raw = fetch_bytes(it["url"])
            name = f"{_safe_name(it.get('doc_no') or '')} {_safe_name(it['title'])}".strip()
            tok = lark.drive_upload(folders[cc], f"{name}{_ext_of(it['url'])}", raw)
            url = lark.drive_file_url(tok) if tok else None
            store.write("UPDATE legal_news_items SET drive_url=?, status='archived' "
                        "WHERE key=?", (url, key))
            n += 1
            log(f"[news] lưu {cc}/{name[:50]} → Drive")
        except Exception as exc:
            log(f"[news] lưu {key} lỗi: {exc}")
    return n


def _ext_of(url):
    m = re.search(r"\.(pdf|docx?|xlsx?)(?:\?|$)", (url or "").lower())
    return "." + m.group(1) if m else ".html"


def fetch_bytes(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def render_digest(store, keys):
    """Digest markdown. Mọi mục đều có link — mục thiếu link đã bị loại ở summarise()."""
    rows = [store.one("SELECT * FROM legal_news_items WHERE key=?", (k,)) for k in keys]
    rows = [r for r in rows if r]
    if not rows:
        return "", 0
    lines = [f"**Văn bản pháp luật mới** — {len(rows)} văn bản"]
    for r in rows:
        try:
            s = json.loads(r.get("summary") or "{}")
        except json.JSONDecodeError:
            s = {}
        no = f"`{r['doc_no']}` " if r.get("doc_no") else ""
        lines.append(f"\n**{no}[{r['title']}]({r['url']})**")
        if s.get("scope"):
            lines.append(f"- Phạm vi: {s['scope']}")
        lines.append(f"- Hiệu lực: {s.get('effective') or 'chưa rõ'}")
        lines.append(f"- Tác động LSR: {s.get('impact') or 'chưa đánh giá được'}")
    return "\n".join(lines), len(rows)


def publish(store, engine, pf, lark, keys, digest_md, group_chat_id,
            drive_folder=None, notebook_ingest=True, log=print):
    """CHỈ gọi sau khi Pháp chế duyệt gate. Gửi digest + lưu Drive + nạp notebook."""
    result = {"sent": False, "drive": None, "nlm": 0}
    if group_chat_id:
        result["sent"] = pf.lark_send(group_chat_id, markdown=digest_md)
    stamp = time.strftime("%Y%m%d-%H%M")
    if drive_folder and lark:
        try:
            tok = lark.drive_upload(drive_folder, f"digest-van-ban-luat-{stamp}.md",
                                    digest_md.encode("utf-8"))
            result["drive"] = lark.drive_file_url(tok) if tok else None
        except Exception as exc:
            log(f"[news] lưu Drive lỗi: {exc}")
    if notebook_ingest:
        for k in keys:
            it = store.one("SELECT * FROM legal_news_items WHERE key=?", (k,))
            if not it:
                continue
            try:
                engine.add_text_source(
                    f"[Legal Update] {it.get('doc_no') or ''} {it['title']}"[:200],
                    f"{it['title']}\nNguồn: {it['url']}\n\n{it.get('summary') or ''}")
                result["nlm"] += 1
            except Exception as exc:
                log(f"[news] nạp notebook lỗi ({k}): {exc}")
    for k in keys:
        store.write("UPDATE legal_news_items SET status='published' WHERE key=?", (k,))
    return result
