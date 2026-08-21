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
    ("Thư viện pháp luật — tìm văn bản",
     "https://thuvienphapluat.vn/page/tim-van-ban.aspx?keyword=&type=3&match=True&area=0",
     "tvpl", "VN", None, 1,
     "đã kiểm 19/08: adapter tvpl đọc được danh sách + TOÀN VĂN không cần đăng nhập. "
     "Đổi `type`/`area` trong URL để lấy loại văn bản khác; thêm dòng nguồn mới trên console"),
    ("LuatVietnam — tra cứu theo tên", "https://luatvietnam.vn/van-ban/tim-kiem.html",
     "lvn", "VN", None, 0,
     "đã kiểm 20/08: tra cứu theo từ khoá chạy ẩn danh, lấy được toàn văn. Agent VẪN dùng "
     "nguồn này để tra cứu tức thời khi có người hỏi — không cần bật. Chỉ bật khi muốn "
     "THEO DÕI một chủ đề hằng tuần: điền TỪ KHOÁ vào link_pattern (vd 'bán lẻ')"),
    ("Cổng TTĐT Chính phủ — Hệ thống văn bản", "https://chinhphu.vn/he-thong-van-ban",
     "chinhphu", "VN", None, 1,
     "đã kiểm 20/08: 50 văn bản/trang, SỐ HIỆU lấy từ cột dữ liệu (không đoán từ tiêu đề) "
     "và tải được PDF KÝ SỐ bản gốc. Nguồn tốt nhất để lưu bản gốc. Chỉ lấy trang 1 "
     "(phân trang là ASP.NET postback)"),
    ("Công báo Chính phủ", "https://congbao.chinhphu.vn/rss",
     "rss", "VN", None, 0, "19/08: 200 nhưng 0 item và 0 link (trang render bằng JS)"),
    # --- Nước khác ---
    # Chốt 21/08: **bỏ Thái Lan khỏi scope seed**, sẽ thêm nguồn trên console agent sau.
    # Lý do bỏ chứ không để inactive: đã đo 9 nguồn (Royal Gazette http+https, Krisdika ×3,
    # Revenue Dept, Nghị viện, Bộ Thương mại, DBD) — WAF 403 hoặc trang render JS, không
    # cái nào đọc được bằng HTTP thuần. Để 3 dòng inactive kèm ghi chú chỉ làm bảng nguồn
    # rối mà không ai định bật.
    #
    # Cơ chế theo NƯỚC vẫn còn nguyên: thêm nguồn nước nào cũng chỉ là thêm một dòng
    # (`country`), và văn bản bỏ tay vào folder con theo nước vẫn được index —
    # `ingest_drive_folder()`.
]

# Số hiệu văn bản VN: 12/2026/NĐ-CP, 05/2026/TT-BTC, 1234/QĐ-TTg, 45/2019/QH14,
# 20519/CHQ-GSQL…
#
# Ba lần nới, mỗi lần vì một lỗi CHẠY THẬT mới thấy:
#   \d{1,6}   công văn hải quan 5 chữ số (20519/CHQ-GSQL) — giới hạn 4 bỏ sót thật.
#   [a-z]*    hậu tố có chữ thường: TTg (Thủ tướng). Không có thì 55/CĐ-TTg bị cắt còn
#             55/CĐ, mà chinhphu.vn cấp đúng 55/CĐ-TTg ⇒ **một văn bản lưu thành hai bản**.
#   \d*       hậu tố có số: QH14 (Quốc hội khoá 14). Không có thì "45/2019/QH14" hỏng
#             luôn cả cụm và trả về None — tức là Bộ luật Lao động không có số hiệu.
_SEG = r"[A-ZĐ]{2,}[a-zà-ỹ]*\d*"
DOC_NO = re.compile(rf"\b(\d{{1,6}}\s*/\s*(?:\d{{4}}\s*/\s*)?{_SEG}(?:\s*-\s*{_SEG})*)")

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


# Nguồn đã kiểm là KHÔNG dùng được và đã có nguồn thay thế. Dọn hẳn cho khỏi rối bảng
# nguồn — nhưng CHỈ khi chưa lấy được văn bản nào từ nó, và KHÔNG chạm vào nguồn do admin
# tự thêm trên console (xoá việc của người khác thì tệ hơn là để lại một dòng rác).
RETIRED_SOURCES = [
    # thay bằng trang "Hệ thống văn bản" — feed RSS này 404 từ 19/08
    "https://chinhphu.vn/rss/van-ban-chi-dao-dieu-hanh.rss",
    # Thái Lan: bỏ khỏi scope 21/08, sẽ thêm trên console sau (xem DEFAULT_SOURCES)
    "https://ratchakitcha.soc.go.th/",
    "https://www.krisdika.go.th/web/guest/law",
    "https://www.rd.go.th/",
]


def seed_sources(store, sources=None):
    """Nạp nguồn. KHÔNG bật lại nguồn admin đã tắt tay: `active` chỉ set lúc tạo mới."""
    for url in RETIRED_SOURCES:
        store.write("DELETE FROM legal_news_sources WHERE url=? AND n_items=0", (url,))
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


# Tên file: `_safe_name()` đổi "/" thành khoảng trắng khi upload (dấu / không đặt được
# trong tên file), nên "326/2026/NĐ-CP" thành "326 2026 NĐ-CP" và DOC_NO không nhận ra.
FILE_NO = re.compile(
    rf"^\s*(\d{{1,6}})\s+(?:(\d{{4}})\s+)?({_SEG}(?:-{_SEG})*)\b")


def doc_no_from_filename(name):
    """Số hiệu đọc lại từ TÊN FILE trong Drive.

    Cần vì bản lưu trong kho mang tên đã bị làm phẳng dấu "/". Không có hàm này thì mọi
    văn bản nạp tay đều `doc_no=NULL` ⇒ dedupe theo số hiệu không chạy ⇒ cùng một văn bản
    lưu hai lần (đã xảy ra thật: Bộ luật Lao động vào kho 2 lần).

    Chốt chống nhận bừa: hoặc phải có **nhóm năm 4 chữ số**, hoặc hậu tố phải **có gạch
    nối**. Không có chốt này thì "2026 BAO CAO nam.pdf" cũng thành số hiệu "2026/BAO".
    """
    no = doc_no_of(name)
    if no:
        return no
    m = FILE_NO.match(name or "")
    if not m:
        return None
    year, suffix = m.group(2), m.group(3)
    if not year and "-" not in suffix:
        return None
    return "/".join([m.group(1)] + ([year] if year else []) + [suffix])


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
            if s["kind"] == "tvpl":
                # thuvienphapluat.vn: trang tìm kiếm có cấu trúc riêng (p.nqTitle[lawid])
                # nên dùng adapter thay vì link_pattern chung.
                from legalkb import tvpl
                items = [{"title": d["title"], "url": d["url"], "desc": ""}
                         for d in tvpl.search(s["url"], log=log)]
            elif s["kind"] == "chinhphu":
                from legalkb import chinhphu
                items = chinhphu.search(s["url"], log=log)
            elif s["kind"] == "lvn":
                # Nguồn "tra cứu theo tên": `link_pattern` giữ TỪ KHOÁ (ví dụ "bán lẻ",
                # "thương mại điện tử") — theo dõi một chủ đề thay vì cả dòng văn bản mới.
                from legalkb import luatvietnam
                kw = (s.get("link_pattern") or "").strip()
                if not kw:
                    raise RuntimeError("nguồn lvn cần TỪ KHOÁ ở link_pattern (vd 'bán lẻ')")
                items = luatvietnam.search(kw, log=log)
            elif s["kind"] == "rss":
                items = parse_rss(fetch(s["url"]))
            elif s["kind"] == "html":
                items = parse_html(fetch(s["url"]), s["url"], s.get("link_pattern"))
            else:
                raise RuntimeError(f"kind '{s['kind']}' chưa hỗ trợ "
                                   f"(rss | html | tvpl | chinhphu | lvn)")
            if not items:
                raise RuntimeError("lấy được trang nhưng 0 văn bản — kiểm URL/link_pattern")
            new = 0
            for it in items:
                # Số hiệu do NGUỒN cấp (chinhphu.vn có cột riêng) đáng tin hơn regex dò
                # trên tiêu đề: trích yếu "Quy định về định danh địa điểm" của Nghị định
                # 326/2026/NĐ-CP không chứa một chữ số nào.
                no = it.get("doc_no") or doc_no_of(it["title"]) or doc_no_of(it.get("desc"))
                key = no or it["url"]
                cur = store.one("SELECT key, file_urls, drive_url FROM legal_news_items "
                                "WHERE key=?", (key,))
                if cur:
                    # Dedupe giữ bản THẤY TRƯỚC, nhưng bản gốc TỐT HƠN có thể tới sau:
                    # RSS chỉ có link trang tin, chinhphu.vn có PDF ký số của cơ quan ban
                    # hành. Chưa lưu về Drive thì còn kịp đổi sang bản tốt hơn.
                    if it.get("files") and not cur["file_urls"] and not cur["drive_url"]:
                        store.write("UPDATE legal_news_items SET file_urls=?, url=?, "
                                    "source_id=? WHERE key=?",
                                    (json.dumps(it["files"]), it["url"], s["id"], key))
                        log(f"[news] {key}: đổi sang bản gốc từ {s['name']}")
                    continue                       # dedupe theo số hiệu, rồi tới URL
                store.write(
                    "INSERT INTO legal_news_items (key, source_id, country, doc_no, title, "
                    "url, file_urls, is_draft, status, found_at) "
                    "VALUES (?,?,?,?,?,?,?,?,'new',?)",
                    (key, s["id"], s.get("country") or "VN", no, it["title"][:500],
                     it["url"], json.dumps(it["files"]) if it.get("files") else None,
                     int(bool(it.get("is_draft"))), time.time()))
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


def _original_for(it, kind):
    """Bản gốc để lưu về Drive, theo từng loại nguồn → `(bytes, đuôi file)`.

    Thứ tự ưu tiên là có chủ ý: **file ký số của cơ quan ban hành > toàn văn trích được >
    HTML cả trang**. Bản PDF ký số là bản trích dẫn được; bản gõ lại của trang trung gian
    thì không, và HTML cả trang thì 90% là menu với quảng cáo.
    """
    # `file_urls` là tín hiệu mạnh nhất: đã có link file gốc của cơ quan ban hành thì
    # dùng nó, bất kể item vào DB qua nguồn nào (bản gốc có thể do nguồn KHÁC cấp — xem
    # bước "đổi sang bản gốc" trong crawl()).
    files = json.loads(it.get("file_urls") or "[]")
    if files or kind == "chinhphu":
        from legalkb import chinhphu
        raw, ext, _ = chinhphu.download_original(it["url"], files)
        return raw, ext
    # Chọn theo HOST của link, không chỉ theo `kind` của nguồn: link luatvietnam đến từ
    # RSS cũng phải dùng bộ trích của luatvietnam. Không thì lưu nguyên HTML 2MB toàn
    # menu/quảng cáo và gọi đó là "văn bản gốc".
    host = urllib.parse.urlsplit(it.get("url") or "").netloc.lower()
    for match, module in (("thuvienphapluat.vn", "legalkb.tvpl"),
                          ("luatvietnam.vn", "legalkb.luatvietnam")):
        if match in host:
            text = __import__(module, fromlist=["fetch_text"]).fetch_text(it["url"])
            if not text:
                raise RuntimeError("không trích được toàn văn (đổi layout?)")
            return text.encode("utf-8"), ".txt"
    raw, ext = fetch_bytes(it["url"]), _ext_of(it["url"])
    if ext == ".html":
        raise RuntimeError(f"nguồn {host} chưa có bộ trích toàn văn — chỉ index link, "
                           "không lưu HTML cả trang làm 'bản gốc'")
    return raw, ext


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
            src = store.one("SELECT kind FROM legal_news_sources WHERE id=?",
                            (it.get("source_id"),)) or {}
            raw, ext = _original_for(it, src.get("kind"))
            prefix = "DU THAO " if it.get("is_draft") else ""
            name = (f"{prefix}{_safe_name(it.get('doc_no') or '')} "
                    f"{_safe_name(it['title'])}").strip()
            tok = lark.drive_upload(folders[cc], f"{name}{ext}", raw)
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


def ingest_drive_folder(store, lark, root_folder, log=print):
    """Nhận văn bản do NGƯỜI bỏ tay vào kho Drive → đăng ký + trả về key để index.

    Vì sao cần: có nước không crawl tự động được. Thái Lan là ví dụ thật — đã đo 9 nguồn
    (Royal Gazette, Krisdika, Revenue Dept, Bộ Thương mại, DBD, Nghị viện…), **không cái
    nào** đọc được bằng HTTP thuần: hoặc WAF trả 403, hoặc trang render bằng JS nên HTML
    tĩnh chỉ có menu.

    Nên đường vào thứ hai: người (squad Thái, hoặc pháp chế) tải văn bản về rồi bỏ vào
    folder con theo nước trong kho Drive. Agent quét thấy file mới thì đăng ký và index —
    **kết quả cuối giống hệt crawl tự động**: hỏi tới là biết truy xuất từ đâu.

    Cố ý KHÔNG đọc nội dung file ở đây: file người bỏ vào là pdf/docx/scan, trích text là
    việc của bước index sau. Ở đây chỉ ghi *có văn bản này, nằm ở đây*.
    """
    if not (lark and root_folder):
        return []
    out = []
    try:
        entries = lark.drive_files(root_folder)
    except Exception as exc:
        log(f"[drive] không đọc được kho văn bản: {exc}")
        return []
    for folder in [e for e in entries if e.get("type") == "folder"]:
        cc = (folder.get("name") or "").strip().upper()[:8] or "VN"
        try:
            files = lark.drive_files(folder["token"])
        except Exception as exc:
            log(f"[drive] không đọc được folder {cc}: {exc}")
            continue
        for f in files:
            if f.get("type") == "folder":
                continue
            name = f.get("name") or ""
            key = f"drive:{f.get('token')}"
            if store.one("SELECT key FROM legal_news_items WHERE key=?", (key,)):
                continue
            no = doc_no_from_filename(name)
            # Số hiệu đã có trong kho từ nguồn khác → không tạo bản ghi thứ hai.
            if no and store.one("SELECT key FROM legal_news_items WHERE doc_no=?", (no,)):
                continue
            url = lark.drive_file_url(f["token"]) if hasattr(lark, "drive_file_url") else None
            store.write(
                "INSERT INTO legal_news_items (key, country, doc_no, title, url, drive_url, "
                "status, found_at) VALUES (?,?,?,?,?,?,'archived',?)",
                (key, cc, no, name[:500], url, url, time.time()))
            out.append(key)
            log(f"[drive] nhận {cc}/{name[:60]}")
    return out


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
