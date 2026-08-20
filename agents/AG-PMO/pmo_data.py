"""pmo_data — đọc danh mục dự án LSR và dựng câu trả lời có kiểm chứng cho AG-PMO.

Nguồn: Lark Base ``CÁC DỰ ÁN LAMSON RETAIL 2026`` trong wiki space ``LSR - PMO``.
  • ``TỔNG HỢP DỰ ÁN LSR``  (bảng chiều)  — danh tính dự án, mốc ngày, owner
  • ``BÁO CÁO DỰ ÁN``       (bảng sự kiện) — báo cáo tuần: OVERVIEW/RISK/ISSUE/NEXT ACTION

Bốn luật ở file này sinh ra từ **khảo sát dữ liệu thật ngày 20/08/2026**, không phải phòng xa:

1. **Hiện trạng lấy từ BÁO CÁO DỰ ÁN, không lấy từ bảng tổng hợp.** Ở bảng tổng hợp,
   ``Blockers`` và ``NEXT ACTION`` rỗng 61/61 dòng, ``Project Health`` chỉ điền 7/61.
   Đọc mấy field đó = trả lời rỗng cho mọi câu hỏi "dự án đang tắc ở đâu".

2. **Chặn field tài chính mật.** ``Budget``, ``Actual GM (BLG)``, ``Margin Gap``... nằm
   CÙNG bảng với dữ liệu thường. Hàm public mặc định ``include_confidential=False`` và
   lọc theo whitelist — không có đường nào đẩy cả record ra ngoài.

3. **Luôn trả kèm độ cũ.** Báo cáo mới nhất trong Base là 30/07/2026 trong khi hôm nay là
   20/08 — trễ 21 ngày. Nên mọi câu trả lời phải mang theo ``ngay_bao_cao`` và ``tre_ngay``
   để agent nói rõ trước khi nêu nội dung.

4. **Phân biệt "chưa có báo cáo" với "không có rủi ro".** Chỉ 39/61 dự án từng có báo cáo.
   Hai tình huống này trả về ``trang_thai_du_lieu`` khác nhau; gộp chúng là trả lời sai.

Chỉ-đọc. Không có hàm ghi — agent không sửa dữ liệu gốc trên Lark.

Chạy thử độc lập (cần LARK_APP_ID/LARK_APP_SECRET, hoặc --fixture để test offline):
    python3 pmo_data.py --tim "BST Travel Bag"
    python3 pmo_data.py --brief PRJ-2026016
    python3 pmo_data.py --kiem-tra-du-lieu
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# ── Toạ độ dữ liệu (khảo sát 20/08/2026) ────────────────────────────────────────────
APP_TOKEN = os.environ.get("PMO_BASE_TOKEN", "WCd8bTo39arpYKsIDAalwiG8gwh")
TBL_PROJECTS = os.environ.get("PMO_TBL_PROJECTS", "tblXGSGOetbLTx8o")   # TỔNG HỢP DỰ ÁN LSR
TBL_REPORTS = os.environ.get("PMO_TBL_REPORTS", "tblIgOwS5IV2pDXK")     # BÁO CÁO DỰ ÁN
WIKI_SPACE_PMO = os.environ.get("PMO_WIKI_SPACE", "7638442489078157023")

# Ngưỡng cảnh báo dữ liệu cũ. Báo cáo theo tuần nên quá 14 ngày là đã hụt ~2 kỳ.
NGUONG_CU_NGAY = int(os.environ.get("PMO_STALE_DAYS", "14"))

# ── Ranh giới dữ liệu ───────────────────────────────────────────────────────────────
# Field TÀI CHÍNH MẬT — chỉ trả khi include_confidential=True (người trong
# PMO_CONFIDENTIAL_VIEWERS). Danh sách này là DENYLIST cho mọi đường ra công khai.
FIELD_MAT = {
    # bảng TỔNG HỢP DỰ ÁN LSR
    "Financial Target", "Budget", "Budget Used", "Target GM (BLG)", "Actual GM (BLG)",
    "Margin Gap", "Actual Financial Achivement", "% Target Achievement",
    # bảng BÁO CÁO DỰ ÁN
    "CHI PHÍ", "BLG % Kế hoạch", "BLG % Thực tế", "Chênh lệch BLG", "Mức độ BLG", "MTD %",
}

# Field được phép ra ngoài từ bảng chiều (whitelist — an toàn hơn denylist đơn thuần)
FIELD_DUAN_CONG_KHAI = [
    "Project ID", "Project Name", "Brand", "Market", "Project Status", "Project Health",
    "Project Class", "Project Category", "Product Category", "Project Owner",
    "Project Sponsor", "Progress", "Complexity", "Quater (Quý)", "Năm",
    "Kick Off Date", "Sale Start Date", "Launching Date", "End Date", "Days to Launch",
    "DESCRIPTION", "Notes", "Risks", "Project Documents Link", "Project Task List Link",
    "Project Chat Channel", "Project Post-Mortem Link (Đúc kết dự án)", "Related Links",
]

# Field được phép ra ngoài từ bảng báo cáo tuần
FIELD_BAOCAO_CONG_KHAI = [
    "PROJECT ID", "Project Name", "BRAND", "MARKET", "REPORTING DATE", "WEEK", "MONTH",
    "OVERVIEW", "RISK", "ISSUE", "NEXT ACTION", "Cần Support", "INSIGHT",
    "Risk Tag", "Issue Tag", "PIC", "Project Status", "Status", "CLASS", "Launching Date",
]

# Field lookup bị vỡ trong Base (trỏ tới bảng tblFi6vWe1KrJPTD không tồn tại trong Base
# này) → null toàn bộ 61 dòng. KHÔNG dùng, tự tính từ max(REPORTING DATE).
FIELD_LOOKUP_VO = {"Latest Weekly Status", "Last Update Date"}


class PmoDataError(RuntimeError):
    pass


# ── Chuẩn hoá ───────────────────────────────────────────────────────────────────────

def _phang(v):
    """Bitable trả select/user/link dạng list — làm phẳng về scalar hoặc chuỗi gọn.

    Giá trị select trong Base này có khoảng trắng cuối (``"ON GOING "``, ``"On Track "``)
    nên phải trim, nếu không so sánh chuỗi sẽ luôn trượt.
    """
    if v is None:
        return None
    if isinstance(v, str):
        return v.strip() or None
    if isinstance(v, (int, float, bool)):
        return v
    if isinstance(v, dict):
        return (v.get("name") or v.get("text") or v.get("id") or "").strip() or None
    if isinstance(v, list):
        parts = [_phang(x) for x in v]
        parts = [str(p) for p in parts if p not in (None, "")]
        return ", ".join(parts) or None
    return str(v).strip() or None


def _to_ngay(v):
    """REPORTING DATE có thể là ISO string hoặc epoch millis. Trả date hoặc None."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(v / 1000, tz=timezone.utc).date()
        except (ValueError, OSError, OverflowError):
            return None
    s = str(v).strip()
    for cat in (s[:10], s):
        try:
            return datetime.fromisoformat(cat.replace("Z", "+00:00")).date()
        except ValueError:
            continue
    return None


def _rows(bang: dict) -> list[dict]:
    """Đổi payload record-list (fields[] + data[][]) thành list dict theo tên field.

    Nhận cả 2 dạng: {"fields": [...], "data": [[...]]} (record-list dạng ma trận) và
    [{"fields": {...}}] (bitable_records của lark_docs.py).
    """
    if isinstance(bang, list):
        out = []
        for rec in bang:
            f = rec.get("fields", rec) if isinstance(rec, dict) else {}
            out.append({k: _phang(v) for k, v in f.items()})
        return out
    ten = bang.get("fields") or []
    out = []
    for hang in bang.get("data") or []:
        out.append({ten[i]: _phang(hang[i]) for i in range(min(len(ten), len(hang)))})
    return out


def _loc(d: dict, cho_phep: list[str], include_confidential: bool) -> dict:
    """Lọc theo whitelist. Field mật chỉ đi qua khi được phép TƯỜNG MINH."""
    ra = {k: d.get(k) for k in cho_phep if d.get(k) not in (None, "")}
    if include_confidential:
        ra.update({k: d[k] for k in FIELD_MAT if d.get(k) not in (None, "")})
    return ra


# ── Kho dữ liệu ─────────────────────────────────────────────────────────────────────

class PmoStore:
    """Danh mục dự án + báo cáo tuần, đã chuẩn hoá và đánh chỉ mục."""

    def __init__(self, projects_payload, reports_payload, *, hom_nay=None):
        self.hom_nay = hom_nay or datetime.now(timezone.utc).date()
        self.du_an = [r for r in _rows(projects_payload) if r.get("Project Name")]
        self.bao_cao = _rows(reports_payload)

        # Chỉ mục báo cáo theo PROJECT ID, mới nhất trước
        self._bc_theo_id: dict[str, list[dict]] = {}
        for bc in self.bao_cao:
            pid = bc.get("PROJECT ID")
            if not pid:
                continue
            self._bc_theo_id.setdefault(pid, []).append(bc)
        for ds in self._bc_theo_id.values():
            ds.sort(key=lambda b: (_to_ngay(b.get("REPORTING DATE")) or datetime.min.date()),
                    reverse=True)

    # ---- tra cứu ----

    def tim(self, tu_khoa: str) -> list[dict]:
        """Tìm dự án theo Project ID hoặc tên (không phân biệt hoa thường).

        Trả về NHIỀU kết quả khi tên trùng — chủ ý, để agent hỏi lại brand chứ không tự
        chọn. Dữ liệu thật có ``BST Travel Bag``, ``BST TRANG SỨC``, ``BST NƯỚC HOA``
        tồn tại ở cả HAPAS và MATE MADE.
        """
        tk = (tu_khoa or "").strip().lower()
        if not tk:
            return []
        chinh_xac = [d for d in self.du_an if (d.get("Project ID") or "").lower() == tk]
        if chinh_xac:
            return chinh_xac
        return [d for d in self.du_an if tk in (d.get("Project Name") or "").lower()]

    def bao_cao_moi_nhat(self, project_id: str) -> dict | None:
        ds = self._bc_theo_id.get(project_id) or []
        return ds[0] if ds else None

    def brief(self, du_an: dict, *, include_confidential: bool = False) -> dict:
        """Hồ sơ một dự án để agent trả lời. KHÔNG bao giờ chứa field mật nếu không xin.

        ``trang_thai_du_lieu`` là phần quan trọng nhất — agent phải nói nó ra trước khi
        nêu nội dung:
          • ``chua_co_bao_cao`` — dự án chưa từng được báo cáo. KHÁC với "không có rủi ro".
          • ``cu``              — có báo cáo nhưng trễ quá ngưỡng.
          • ``moi``             — báo cáo còn trong ngưỡng.
        """
        pid = du_an.get("Project ID")
        bc = self.bao_cao_moi_nhat(pid) if pid else None
        ngay = _to_ngay(bc.get("REPORTING DATE")) if bc else None
        tre = (self.hom_nay - ngay).days if ngay else None

        if bc is None:
            tt = "chua_co_bao_cao"
        elif tre is not None and tre > NGUONG_CU_NGAY:
            tt = "cu"
        else:
            tt = "moi"

        ra = {
            "du_an": _loc(du_an, FIELD_DUAN_CONG_KHAI, include_confidential),
            "trang_thai_du_lieu": tt,
            "ngay_bao_cao": ngay.isoformat() if ngay else None,
            "tre_ngay": tre,
            "so_bao_cao_da_co": len(self._bc_theo_id.get(pid) or []),
            "bao_cao_moi_nhat": _loc(bc, FIELD_BAOCAO_CONG_KHAI, include_confidential) if bc else None,
        }

        # Nêu rõ mâu thuẫn thay vì chọn một bên. Dữ liệu thật có bản ghi
        # BST Travel Bag (MATE MADE): Project Health = At Risk nhưng Project Status = DONE.
        health = (du_an.get("Project Health") or "").lower()
        status = (du_an.get("Project Status") or "").lower()
        if status == "done" and health in ("at risk", "off track"):
            ra["mau_thuan"] = (
                f"Bản ghi tự mâu thuẫn: Project Status = '{du_an.get('Project Status')}' "
                f"nhưng Project Health = '{du_an.get('Project Health')}'. "
                "Cần người xác nhận lại, agent không tự chọn bên nào."
            )
        return ra

    # ---- kiểm tra chất lượng dữ liệu ----

    def kiem_tra_du_lieu(self) -> dict:
        """Số liệu để agent tự biết mình đang đứng trên nền dữ liệu nào."""
        ngay_bc = [d for d in (_to_ngay(b.get("REPORTING DATE")) for b in self.bao_cao) if d]
        moi_nhat = max(ngay_bc) if ngay_bc else None
        co_bc = {b.get("PROJECT ID") for b in self.bao_cao if b.get("PROJECT ID")}
        id_du_an = {d.get("Project ID") for d in self.du_an if d.get("Project ID")}

        def ty_le(field, nguon):
            if not nguon:
                return 0
            return round(sum(1 for r in nguon if r.get(field) not in (None, "")) * 100 / len(nguon))

        # tên trùng giữa các brand
        theo_ten: dict[str, set] = {}
        for d in self.du_an:
            ten = (d.get("Project Name") or "").strip().lower()
            if ten:
                theo_ten.setdefault(ten, set()).add(d.get("Brand"))
        trung = {t: sorted(b for b in bs if b) for t, bs in theo_ten.items() if len(bs) > 1}

        return {
            "tong_du_an": len(self.du_an),
            "tong_bao_cao": len(self.bao_cao),
            "du_an_co_bao_cao": len(co_bc & id_du_an),
            "du_an_chua_bao_cao": len(id_du_an - co_bc),
            "bao_cao_moi_nhat": moi_nhat.isoformat() if moi_nhat else None,
            "tre_ngay": (self.hom_nay - moi_nhat).days if moi_nhat else None,
            "ty_le_dien_bao_cao": {
                f: ty_le(f, self.bao_cao)
                for f in ("OVERVIEW", "RISK", "ISSUE", "NEXT ACTION", "Cần Support")
            },
            "ten_trung_giua_brand": trung,
        }


# ── Nạp dữ liệu ─────────────────────────────────────────────────────────────────────

def tu_lark() -> PmoStore:
    """Đọc thẳng từ Lark. Cần LARK_APP_ID/LARK_APP_SECRET trong .env local."""
    try:
        from lark_read import LarkRead
    except ImportError as exc:  # pragma: no cover
        raise PmoDataError(f"thiếu lark_read.py: {exc}") from exc
    lark = LarkRead()
    return PmoStore(lark.bitable_records(APP_TOKEN, TBL_PROJECTS),
                    lark.bitable_records(APP_TOKEN, TBL_REPORTS))


def tu_fixture(path: str) -> PmoStore:
    """Nạp từ file JSON đã dump sẵn — để test logic không cần mạng."""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return PmoStore(d["projects"], d["reports"], hom_nay=_to_ngay(d.get("hom_nay")))


# ── CLI ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description="Tra danh mục dự án PMO (chỉ đọc)")
    p.add_argument("--fixture", help="file JSON dump sẵn (test offline)")
    p.add_argument("--tim", help="tìm dự án theo tên hoặc Project ID")
    p.add_argument("--brief", help="hồ sơ dự án theo Project ID")
    p.add_argument("--mat", action="store_true",
                   help="kèm field tài chính mật (chỉ dùng khi người hỏi được phép)")
    p.add_argument("--kiem-tra-du-lieu", action="store_true", dest="kiem_tra")
    a = p.parse_args()

    store = tu_fixture(a.fixture) if a.fixture else tu_lark()

    if a.kiem_tra:
        print(json.dumps(store.kiem_tra_du_lieu(), ensure_ascii=False, indent=2))
        return 0
    if a.tim:
        kq = store.tim(a.tim)
        if not kq:
            print(json.dumps({"tim_thay": 0,
                              "ghi_chu": "Không có dự án nào khớp — KHÔNG được suy từ dự án khác."},
                             ensure_ascii=False, indent=2))
            return 0
        print(json.dumps(
            {"tim_thay": len(kq),
             "can_hoi_lai_brand": len(kq) > 1,
             "ket_qua": [{k: d.get(k) for k in ("Project ID", "Project Name", "Brand",
                                                "Project Status", "Market")} for d in kq]},
            ensure_ascii=False, indent=2))
        return 0
    if a.brief:
        kq = store.tim(a.brief)
        if not kq:
            print(json.dumps({"loi": f"không tìm thấy dự án '{a.brief}'"},
                             ensure_ascii=False, indent=2))
            return 1
        if len(kq) > 1:
            print(json.dumps(
                {"can_hoi_lai_brand": True,
                 "ghi_chu": "Tên trùng ở nhiều brand — hỏi lại người dùng, không tự chọn.",
                 "lua_chon": [{k: d.get(k) for k in ("Project ID", "Project Name", "Brand")}
                              for d in kq]}, ensure_ascii=False, indent=2))
            return 0
        print(json.dumps(store.brief(kq[0], include_confidential=a.mat),
                         ensure_ascii=False, indent=2))
        return 0

    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
