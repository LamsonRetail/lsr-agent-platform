"""pmo_answer — biến dữ liệu dự án thành câu trả lời, và CHẶN trước khi trả lời.

Tách khỏi ``consumer.py`` để test được không cần platform:
    python3 pmo_answer.py "dự án BST Travel Bag đang thế nào"

Thứ tự xử lý CỐ Ý đặt chặn lên trước mọi nhánh khác — không phụ thuộc prompt của model,
vì prompt có thể bị lời lẽ thuyết phục làm lung lay còn luật code thì không:

  1. ``chan_xin_quyet_dinh()``  — ai xin duyệt/quyết → từ chối, kể cả khi nói gấp
  2. ``chan_ngoai_pham_vi()``   — việc của giai đoạn sau (tạo task, gửi ra nhóm khác)
  3. ``chan_du_lieu_mat()``     — hỏi tài chính mà không thuộc PMO_CONFIDENTIAL_VIEWERS
  4. tra dữ liệu → dựng câu trả lời có nêu ngày báo cáo + nguồn

Hàm ``tra_loi()`` trả **dict** chứ không phải chuỗi, để ``consumer.py`` quyết định gọi model
hay trả thẳng. Câu chặn không cần model — vừa nhanh, vừa không thể bị nói lệch.
"""

from __future__ import annotations

import os
import re
import sys

CAU_TU_CHOI_QUYET_DINH = (
    "Dạ cái này Chan không tự quyết được ạ 🙏 — Chan chỉ tra số liệu để anh/chị trình người có "
    "thẩm quyền duyệt thôi. Anh/chị cần Chan lấy hiện trạng và rủi ro của dự án để đưa vào tờ "
    "trình không?\n"
    "À, mình nhớ đừng báo cho các phòng khác trước khi có duyệt chính thức nha."
)

# Người được xem field tài chính mật — khai bằng env, mặc định RỖNG (an toàn trước tiện).
NGUOI_XEM_MAT = {e.strip().lower() for e in
                 os.environ.get("PMO_CONFIDENTIAL_VIEWERS", "").split(",") if e.strip()}

# ── Bộ chặn ─────────────────────────────────────────────────────────────────────────

# Xin quyết định: phải có DẤU HIỆU XIN + ĐỐI TƯỢNG QUYẾT. Cố ý không bắt mọi câu chứa
# "deadline" — "deadline dự án X là ngày nào" là câu hỏi thông tin, không phải xin duyệt.
_DAU_HIEU_XIN = r"(duy[ệe]t|ph[eê] duy[ệe]t|ch[ốo]t|đ[ồo]ng ý|x[áa]c nh[ậa]n|ok nh[ée]|" \
                r"cho\s+(?:em|anh|ch[ị]|t[ôo]i)|l[ùu]i|d[ờo]i|d[ẹe]?i|t[ăa]ng|gi[ảa]m|" \
                r"b[ỏo]|th[êe]m|đi[ềe]u|chuy[ểe]n)"
_DOI_TUONG_QUYET = r"(ng[âa]n s[áa]ch|budget|deadline|h[ạa]n|ph[ạa]m vi|scope|" \
                   r"nh[âa]n s[ựu]|ngu[ồo]n l[ựu]c|ti[ếe]n đ[ộo]|h[ạa]ng m[ụu]c|ti[ềe]n)"

_NGOAI_PHAM_VI = (
    (r"t[ạa]o\s+task|giao vi[ệe]c|assign", "Dạ phần này Chan **chưa tự tạo task** được ạ — hiện tại "
     "Chan chỉ liệt kê cam kết trong biên bản và danh mục dự án, việc tạo task để giai đoạn sau nha."),
    (r"g[ửu]i.*(nh[óo]m|group|ban gi[áa]m đ[ốo]c|bod)", "Chan chỉ trả lời trong nhóm đang trao đổi "
     "thôi ạ, **không tự gửi** sang nhóm khác được — sợ lộ thông tin sai chỗ 😅"),
    (r"(token|secret|api[_ ]?key|m[ậa]t kh[ẩa]u)", "Dạ cái này Chan **không đưa token**/secret ra "
     "ngoài được ạ."),
)

_HOI_TAI_CHINH = r"(ng[âa]n s[áa]ch|budget|chi ph[íi]|gi[áa] v[ốo]n|bi[êe]n l[ợo]i nhu[ậa]n|" \
                 r"margin|gm\b|l[ợo]i nhu[ậa]n|ti[êe]u bao nhi[êe]u|doanh thu th[ựu]c)"


def _co(pat: str, s: str) -> bool:
    return re.search(pat, s, re.IGNORECASE) is not None


def chan_xin_quyet_dinh(cau: str) -> str | None:
    if _co(_DAU_HIEU_XIN, cau) and _co(_DOI_TUONG_QUYET, cau):
        return CAU_TU_CHOI_QUYET_DINH
    return None


def chan_ngoai_pham_vi(cau: str) -> str | None:
    for pat, tra_loi in _NGOAI_PHAM_VI:
        if _co(pat, cau):
            return tra_loi
    return None


def chan_du_lieu_mat(cau: str, email: str | None) -> str | None:
    if not _co(_HOI_TAI_CHINH, cau):
        return None
    if email and email.strip().lower() in NGUOI_XEM_MAT:
        return None
    return ("Dạ phần ngân sách / biên lợi nhuận là dữ liệu hạn chế, Chan chỉ trả lời cho người "
            "trong danh sách được duyệt thôi ạ 🙏 Anh/chị liên hệ PMO nếu cần quyền xem nha.")


# ── Dựng câu trả lời ────────────────────────────────────────────────────────────────

def _mo_ta_do_moi(b: dict) -> str:
    tt = b.get("trang_thai_du_lieu")
    if tt == "chua_co_bao_cao":
        return ("⚠️ Dự án này **chưa có báo cáo tuần nào** ạ — Chan chưa có hiện trạng để trả lời "
                "(khác với 'dự án không có rủi ro' nha). Anh/chị hỏi PIC hoặc chủ trì dự án giúp Chan nhé.")
    ngay, tre = b.get("ngay_bao_cao"), b.get("tre_ngay")
    if tt == "cu":
        return (f"⚠️ Số liệu mới nhất Chan có là báo cáo ngày **{ngay}**, đã **{tre} ngày** chưa "
                f"cập nhật rồi ạ — có thể không còn đúng hiện trạng hôm nay đâu nha.")
    return f"Dạ theo báo cáo ngày **{ngay}** ({tre} ngày trước) thì:"


def _ngay_doc_duoc(v) -> str | None:
    """Base trả datetime dạng epoch millis — người đọc không hiểu ``1782320400000``."""
    from pmo_data import _to_ngay
    d = _to_ngay(v)
    return d.strftime("%d/%m/%Y") if d else None


def _phan_tram(v) -> str | None:
    """``Progress`` là phân số 0–1 (style percentage) — hiện ``1`` là sai, phải là ``100%``."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f"{f * 100:.0f}%" if 0 <= f <= 1 else f"{f:.0f}"


def _muc(nhan: str, gt) -> str | None:
    return f"- **{nhan}**: {gt}" if gt not in (None, "") else None


def dung_tra_loi(brief: dict) -> str:
    """Câu trả lời cho một dự án — luôn mở đầu bằng độ mới của dữ liệu."""
    da = brief.get("du_an") or {}
    bc = brief.get("bao_cao_moi_nhat") or {}
    dong = [f"**{da.get('Project Name')}** ({da.get('Project ID')} · {da.get('Brand')})",
            "", _mo_ta_do_moi(brief), ""]

    if brief.get("mau_thuan"):
        dong += [f"❗ {brief['mau_thuan']}", ""]

    for nhan, gt in (("Trạng thái", da.get("Project Status")),
                     ("Sức khoẻ dự án", da.get("Project Health")),
                     ("Tiến độ", _phan_tram(da.get("Progress"))),
                     ("Chủ trì", da.get("Project Owner")),
                     ("Ngày mở bán", _ngay_doc_duoc(da.get("Sale Start Date"))),
                     ("Ngày launching", _ngay_doc_duoc(da.get("Launching Date"))),
                     ("PIC báo cáo", bc.get("PIC"))):
        m = _muc(nhan, gt)
        if m:
            dong.append(m)

    if brief.get("trang_thai_du_lieu") != "chua_co_bao_cao":
        for nhan, key in (("Tình hình", "OVERVIEW"), ("Rủi ro", "RISK"),
                          ("Vướng mắc", "ISSUE"), ("Việc kế tiếp", "NEXT ACTION")):
            gt = bc.get(key)
            dong.append(f"\n**{nhan}**\n{gt}" if gt else
                        f"\n**{nhan}**: _báo cáo kỳ này để trống_")

    link = da.get("Project Documents Link") or da.get("Related Links")
    if link:
        dong += ["", f"Nguồn: {link}"]
    return "\n".join(d for d in dong if d is not None)


def dung_hoi_lai_brand(lua_chon: list[dict]) -> str:
    ds = "\n".join(f"- {d.get('Project ID')} · **{d.get('Brand')}** · "
                   f"trạng thái {d.get('Project Status')}" for d in lua_chon)
    return ("Dạ có nhiều dự án cùng tên này, anh/chị cho Chan biết là dự án nào ạ:\n" + ds)


# ── Điểm vào ────────────────────────────────────────────────────────────────────────

def tra_loi(cau: str, *, email: str | None = None, store=None) -> dict:
    """Trả ``{"text": ..., "can_model": bool}``.

    ``can_model=False`` nghĩa là câu trả lời đã đủ và tất định — consumer trả thẳng, không
    gọi model. Câu chặn và câu tra dữ liệu đều thuộc loại này: gọi model ở đây chỉ thêm
    rủi ro model diễn giải lệch đi.
    """
    cau = (cau or "").strip()
    if not cau:
        return {"text": "Dạ Chan nghe đây, anh/chị hỏi về dự án nào ạ? 😊", "can_model": False}

    for chan in (chan_xin_quyet_dinh(cau), chan_ngoai_pham_vi(cau),
                 chan_du_lieu_mat(cau, email)):
        if chan:
            return {"text": chan, "can_model": False}

    if store is None:
        from pmo_data import tu_lark
        store = tu_lark()

    # Rút tên dự án: bỏ các từ hỏi thường gặp để lấy phần lõi
    tu_khoa = re.sub(r"(d[ựu]\s*[áa]n|t[ìi]nh h[ìi]nh|hi[ệe]n tr[ạa]ng|đang|th[ếe] n[àa]o|"
                     r"ra sao|b[âa]y gi[ờo]|sao r[ồo]i|c[ủa]a|\?|t[ắa]c [ởo] đ[âa]u)", " ",
                    cau, flags=re.IGNORECASE).strip()
    kq = store.tim(tu_khoa) or store.tim(cau)

    if not kq:
        return {"text": ("Dạ dự án này Chan **chưa có** trong danh mục ạ 🤔 Có thể do sai tên, "
                         "hoặc dự án chưa được thêm vào danh mục — anh/chị hỏi lại **PMO** kiểm tra "
                         "giúp nha. Chan không đoán bừa từ dự án khác đâu ạ."), "can_model": False}
    if len(kq) > 1:
        return {"text": dung_hoi_lai_brand(kq), "can_model": False}

    cho_xem_mat = bool(email and email.strip().lower() in NGUOI_XEM_MAT)
    brief = store.brief(kq[0], include_confidential=cho_xem_mat)
    return {"text": dung_tra_loi(brief), "can_model": False, "brief": brief}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    r = tra_loi(" ".join(sys.argv[1:]), email=os.environ.get("PMO_TEST_EMAIL"))
    print(r["text"])
