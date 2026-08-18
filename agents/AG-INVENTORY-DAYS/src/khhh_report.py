"""Báo cáo KHHH tự động: đọc Base -> dựng ảnh -> gửi vào nhóm Lark dưới tên bot.

Chạy tay:
    python khhh_report.py --chat-id oc_xxx
    python khhh_report.py --chat-id oc_xxx --dry-run     # chỉ xuất ảnh, không gửi
    python khhh_report.py --out /tmp/bc.png              # chỉ dựng ảnh

Cần trong .env:
    LARK_APP_ID_INVENTORY / LARK_APP_SECRET_INVENTORY
Cần cấp cho app trên Developer Console:
    bitable:app:readonly   — đọc Base
    im:resource            — upload ảnh
    im:message             — gửi tin
Và phải THÊM BOT LÀM CỘNG TÁC VIÊN của Base (quyền đọc), nếu không sẽ 403.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
from collections import defaultdict

import requests
from dotenv import find_dotenv, load_dotenv

logger = logging.getLogger("khhh-report")

BASE_TOKEN = "F7ZxbjBiuah1wtswfbVlmu9ygxh"      # QL KẾ HOẠCH HÀNG HÓA HAPAS
TABLE_ID = "tblDYIZcBY54VCQI"                   # BÁO CÁO KẾ HOẠCH HÀNG HOÁ
NTK_TARGET = 30                                 # HAPAS VN — CoC KHHH mục 3.2

F_NHOM = "Phân loại 2"
F_DT = "Doanh thu đơn tạo-hủy"
F_MTD = "Doanh thu MTD"
F_TON = "Tồn kho"
F_VON = "DT tồn kho (giá vốn)"
F_SL = "Slg bán tại tháng báo cáo"
F_TDB = "TĐB 7 ngày"       # ⚠️ giá trị là TB MỖI NGÀY, không phải tổng 7 ngày
F_DUONG = "Số lượng đang trên đường"
F_NHAP = "Hàng còn nhập trong tháng"
F_SP = "SP"

FIELDS = [F_SP, F_NHOM, F_DT, F_MTD, F_TON, F_VON, F_SL, F_TDB, F_DUONG, F_NHAP]


# --------------------------------------------------------------------------- Lark
class Lark:
    def __init__(self, app_id: str, app_secret: str, domain: str) -> None:
        self._id, self._secret = app_id, app_secret
        self._domain = domain.rstrip("/")
        self._token = None

    @property
    def token(self) -> str:
        if self._token:
            return self._token
        r = requests.post(f"{self._domain}/open-apis/auth/v3/tenant_access_token/internal",
                          json={"app_id": self._id, "app_secret": self._secret}, timeout=30)
        r.raise_for_status()
        p = r.json()
        if p.get("code") != 0:
            raise RuntimeError(f"Lấy token thất bại: {p}")
        self._token = p["tenant_access_token"]
        return self._token

    def _hdr(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def base_records(self) -> tuple[list[dict], list[str]]:
        """Toàn bộ bản ghi của bảng báo cáo (tự phân trang)."""
        out, page = [], None
        while True:
            r = requests.post(
                f"{self._domain}/open-apis/bitable/v1/apps/{BASE_TOKEN}"
                f"/tables/{TABLE_ID}/records/search",
                params={"page_size": 500, **({"page_token": page} if page else {})},
                headers=self._hdr(), json={"field_names": FIELDS}, timeout=60)
            r.raise_for_status()
            p = r.json()
            if p.get("code") != 0:
                raise RuntimeError(
                    f"Đọc Base thất bại: {p}. Kiểm tra scope bitable:app:readonly "
                    f"và bot đã được thêm làm cộng tác viên của Base chưa.")
            d = p["data"]
            out += [it.get("fields", {}) for it in d.get("items", [])]
            if not d.get("has_more"):
                return out, FIELDS
            page = d.get("page_token")

    def upload_image(self, path: str) -> str:
        with open(path, "rb") as fh:
            r = requests.post(f"{self._domain}/open-apis/im/v1/images",
                              headers=self._hdr(),
                              files={"image": fh}, data={"image_type": "message"}, timeout=60)
        r.raise_for_status()
        p = r.json()
        if p.get("code") != 0:
            raise RuntimeError(f"Upload ảnh thất bại: {p} (thiếu scope im:resource?)")
        return p["data"]["image_key"]

    def send_image(self, chat_id: str, image_key: str) -> None:
        self._send(chat_id, "image", {"image_key": image_key})

    def send_text(self, chat_id: str, text: str) -> None:
        self._send(chat_id, "text", {"text": text})

    def _send(self, chat_id: str, msg_type: str, content: dict) -> None:
        r = requests.post(f"{self._domain}/open-apis/im/v1/messages",
                          params={"receive_id_type": "chat_id"}, headers=self._hdr(),
                          json={"receive_id": chat_id, "msg_type": msg_type,
                                "content": json.dumps(content, ensure_ascii=False)}, timeout=30)
        r.raise_for_status()
        p = r.json()
        if p.get("code") != 0:
            raise RuntimeError(f"Gửi tin thất bại: {p}")


# ----------------------------------------------------------------------- tổng hợp
def _n(rec: dict, key: str) -> float:
    v = rec.get(key)
    if isinstance(v, list):
        v = v[0] if v else 0
    if isinstance(v, dict):
        v = v.get("value") or v.get("text") or 0
        if isinstance(v, list):
            v = v[0] if v else 0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _s(rec: dict, key: str) -> str:
    v = rec.get(key)
    if isinstance(v, list):
        v = v[0] if v else ""
    if isinstance(v, dict):
        v = v.get("text") or v.get("value") or ""
    return str(v or "")


def aggregate(records: list[dict]) -> dict:
    g = defaultdict(lambda: defaultdict(float))
    for r in records:
        k = _s(r, F_NHOM) or "(trống)"
        g[k]["sp"] += 1
        for f in (F_DT, F_MTD, F_TON, F_VON, F_SL, F_TDB, F_DUONG, F_NHAP):
            g[k][f] += _n(r, f)

    rows = []
    for k, v in sorted(g.items(), key=lambda x: -x[1][F_DT]):
        ntk = round(v[F_TON] / v[F_TDB]) if v[F_TDB] else 0
        rows.append((k, int(v["sp"]), v[F_DT] / 1e9, v[F_MTD] / 1e9, v[F_TON],
                     ntk, v[F_VON] / 1e9, v[F_DUONG] + v[F_NHAP]))

    T = lambda f: sum(_n(r, f) for r in records)  # noqa: E731
    tdb = T(F_TDB)
    return {
        "rows": rows,
        "n_sku": len(records),
        "dt": T(F_DT), "mtd": T(F_MTD), "ton": T(F_TON), "von": T(F_VON),
        "duong": T(F_DUONG), "nhap": T(F_NHAP), "tdb": tdb,
        "ntk": T(F_TON) / tdb if tdb else 0,
        "ntk_tong": (T(F_TON) + T(F_DUONG) + T(F_NHAP)) / tdb if tdb else 0,
    }


def _vn(x, d=2):
    """1234.5 -> '1.234,50' (kiểu Việt Nam)."""
    return f"{x:,.{d}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def canh_bao(records: list[dict], agg: dict) -> list[str]:
    """Những dòng 'cần xử lý' — chỉ nêu khi thật sự vượt ngưỡng."""
    out = []
    for name, sp, dtv, mtd, ton, ntk, von, ve in agg["rows"]:
        if ntk > 60 and ve > 0:
            out.append(f"{name} — NTK {ntk} ngày, vốn {_vn(von)} tỷ, còn {_vn(ve,0)} sp đang về. "
                       f"Rà lịch hàng về xem giãn được không.")
        elif ntk > 60:
            out.append(f"{name} — NTK {ntk} ngày, vốn {_vn(von)} tỷ. Vượt ngưỡng, cần phương án giải phóng.")
        elif 0 < ntk < 25 and ve > 1000:
            out.append(f"{name} — NTK chỉ {ntk} ngày nhưng {_vn(ve,0)} sp đang về. "
                       f"Check đã tính vào dự phóng chưa.")

    gay = [r for r in records if _n(r, F_TDB) > 0.5 and
           (_n(r, F_TON) / _n(r, F_TDB) if _n(r, F_TDB) else 999) < 20]
    if gay:
        het = [_s(r, F_SP) for r in gay if _n(r, F_TON) == 0][:3]
        msg = f"{len(gay)} mã NTK dưới 20 ngày"
        if het:
            msg += "; đã sạch tồn mà vẫn đang bán: " + ", ".join(het)
        out.append(msg + ".")

    worst = max(records, key=lambda r: _n(r, F_VON), default=None)
    if worst is not None and agg["von"]:
        t = _n(worst, F_TDB)
        if t:
            out.append(f"{_s(worst, F_SP)} — NTK {_n(worst, F_TON)/t:,.0f} ngày, "
                       f"{_vn(_n(worst, F_VON)/1e9)} tỷ = {_n(worst, F_VON)/agg['von']*100:.0f}% "
                       f"tổng vốn tồn.")
    return out[:5]


# --------------------------------------------------------------------------- ảnh
def render(agg: dict, notes: list[str], out_path: str, ky: str) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, Rectangle

    plt.rcParams["font.family"] = "DejaVu Sans"
    INK, INK2, MUTED = "#1A1A1A", "#5A5A5A", "#8A8A8A"
    SURFACE, BAND, RULE, BAR = "#FFFFFF", "#F6F6F4", "#E3E3DF", "#C9CFC4"
    ST = {"good": ("#1F6B3A", "#E3F0E7"), "warn": ("#8A5A00", "#FBF0DA"),
          "crit": ("#9B1C1C", "#FBE6E6"), "low": ("#8A4B00", "#FBEADB"),
          "none": (MUTED, "#F0F0EE")}

    def stt(n):
        if n == 0:
            return "none", "-"
        if n > NTK_TARGET * 2:
            return "crit", str(n)
        if n > NTK_TARGET * 4 // 3:
            return "warn", str(n)
        if n < NTK_TARGET * 5 // 6:
            return "low", str(n)
        return "good", str(n)

    vn = _vn

    rows = agg["rows"]
    W = 15.4
    H = 6.6 + len(rows) * 0.44 + len(notes) * 0.32
    fig = plt.figure(figsize=(W, H), dpi=150, facecolor=SURFACE)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")

    def txt(x, y, s, size=11, c=INK, w="normal", ha="left", style="normal"):
        ax.text(x, y, s, fontsize=size, color=c, fontweight=w, ha=ha, va="center", style=style)

    txt(0.6, H - 0.62, "BÁO CÁO KẾ HOẠCH HÀNG HOÁ — HAPAS VN", 20, INK, "bold")
    txt(0.6, H - 1.02, f"{ky}  ·  {agg['n_sku']} mã  ·  nguồn: Base QL KẾ HOẠCH HÀNG HOÁ", 11, INK2)

    heroes = [("Doanh thu MTD", f"{vn(agg['dt']/1e9)} tỷ", f"dự phóng cả tháng {vn(agg['mtd']/1e9)} tỷ"),
              ("Tồn kho", f"{vn(agg['ton'],0)} sp", f"{vn(agg['von']/1e9)} tỷ giá vốn"),
              ("NTK hiện tại", f"{agg['ntk']:.0f} ngày", f"target {NTK_TARGET} — CoC mục 3.2"),
              ("NTK tổng", f"{agg['ntk_tong']:.0f} ngày",
               f"+{vn(agg['duong'],0)} đang về, +{vn(agg['nhap'],0)} còn nhập")]
    hy, hw = H - 2.55, 3.55
    for i, (lab, val, sub) in enumerate(heroes):
        x = 0.6 + i * hw
        ax.add_patch(FancyBboxPatch((x, hy), hw - 0.22, 1.18,
                     boxstyle="round,pad=0,rounding_size=0.09", fc=BAND, ec="none"))
        txt(x + 0.28, hy + 0.92, lab.upper(), 8.5, MUTED, "bold")
        txt(x + 0.28, hy + 0.58, val, 17, INK, "bold")
        txt(x + 0.28, hy + 0.24, sub, 8.5, INK2)

    top = hy - 0.55
    txt(0.6, top + 0.02, "CHI TIẾT THEO BỘ SƯU TẬP", 12, INK, "bold")
    top -= 0.42
    for name, x, ha in [("BST", 0.60, "left"), ("SP", 4.55, "right"), ("DT tỷ", 5.45, "right"),
                        ("MTD tỷ", 6.55, "right"), ("Tồn", 7.85, "right"), ("NTK", 9.15, "center"),
                        ("Vốn tỷ", 10.6, "right"), ("Về + Nhập", 12.1, "right")]:
        txt(x, top, name, 9.5, MUTED, "bold", ha=ha)
    txt(12.55, top, "TỈ TRỌNG DOANH THU", 9.5, MUTED, "bold")
    ax.plot([0.5, W - 0.5], [top - 0.19] * 2, color=INK, lw=1.1)

    dtmax = max((r[2] for r in rows), default=1) or 1
    y = top - 0.19
    for i, (bst, sp, dtv, mtd, ton, ntk, von, ve) in enumerate(rows):
        y -= 0.44
        if i % 2 == 0:
            ax.add_patch(Rectangle((0.5, y - 0.20), W - 1.0, 0.40, fc=BAND, ec="none"))
        txt(0.60, y, bst[:30], 10.5, INK)
        txt(4.55, y, str(sp), 10.5, INK2, ha="right")
        txt(5.45, y, vn(dtv), 10.5, INK, "bold", ha="right")
        txt(6.55, y, vn(mtd), 10.5, INK2, ha="right")
        txt(7.85, y, vn(ton, 0), 10.5, INK2, ha="right")
        txt(10.6, y, vn(von), 10.5, INK2, ha="right")
        txt(12.1, y, vn(ve, 0), 10.5, INK if ve > 1000 else INK2,
            "bold" if ve > 1000 else "normal", ha="right")
        fg, bg = ST[stt(ntk)[0]]
        ax.add_patch(FancyBboxPatch((8.72, y - 0.145), 0.86, 0.29,
                     boxstyle="round,pad=0,rounding_size=0.07", fc=bg, ec="none"))
        txt(9.15, y, stt(ntk)[1], 10.5, fg, "bold", ha="center")
        if dtv > 0:
            ax.add_patch(FancyBboxPatch((12.55, y - 0.10), max(2.25 * dtv / dtmax, 0.04), 0.20,
                         boxstyle="round,pad=0,rounding_size=0.045", fc=BAR, ec="none"))

    ax.plot([0.5, W - 0.5], [y - 0.22] * 2, color=RULE, lw=1)

    ly = y - 0.64
    for j, (kind, lab) in enumerate([("low", f"dưới {NTK_TARGET*5//6} ngày"),
                                     ("good", f"{NTK_TARGET*5//6}–{NTK_TARGET*4//3}"),
                                     ("warn", f"{NTK_TARGET*4//3+1}–{NTK_TARGET*2}"),
                                     ("crit", f"trên {NTK_TARGET*2}")]):
        x = 0.6 + j * 2.35
        fg, bg = ST[kind]
        ax.add_patch(FancyBboxPatch((x, ly - 0.12), 0.30, 0.24,
                     boxstyle="round,pad=0,rounding_size=0.06", fc=bg, ec=fg, lw=0.9))
        txt(x + 0.42, ly, lab, 9.5, INK2)
    txt(10.0, ly, f"NTK — target HAPAS VN {NTK_TARGET} ngày (CoC mục 3.2)", 9.5, MUTED, style="italic")

    if notes:
        ly -= 0.52
        txt(0.6, ly, "CẦN XỬ LÝ", 11, INK, "bold")
        for i, n in enumerate(notes, 1):
            ly -= 0.32
            txt(0.72, ly, f"{i}.  {n}", 10, INK2)

    ly -= 0.50
    txt(0.6, ly, "Bản do AI tạo tự động — số trích thẳng từ Base, chưa qua người duyệt.",
        8.5, MUTED, style="italic")

    fig.savefig(out_path, facecolor=SURFACE)
    plt.close(fig)
    return out_path


# --------------------------------------------------------------------------- main
def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--chat-id", action="append", help="Nhóm nhận báo cáo (lặp lại được)")
    p.add_argument("--out", default="/tmp/bao_cao_khhh.png")
    p.add_argument("--dry-run", action="store_true", help="Chỉ dựng ảnh, không gửi")
    a = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(find_dotenv(usecwd=True))

    lark = Lark(os.environ.get("LARK_APP_ID_INVENTORY") or os.environ["LARK_APP_ID"],
                os.environ.get("LARK_APP_SECRET_INVENTORY") or os.environ["LARK_APP_SECRET"],
                os.environ.get("LARK_DOMAIN", "https://open.larksuite.com"))

    recs, _ = lark.base_records()
    logger.info("Đọc được %d mã từ Base.", len(recs))
    if not recs:
        logger.error("Base không trả về dòng nào — dừng, không gửi báo cáo rỗng.")
        return 1

    agg = aggregate(recs)
    notes = canh_bao(recs, agg)
    today = dt.date.today()
    ky = f"MTD 01–{today:%d/%m/%Y}"
    render(agg, notes, a.out, ky)
    logger.info("Đã dựng ảnh: %s", a.out)

    if a.dry_run or not a.chat_id:
        logger.info("dry-run / không có --chat-id: không gửi.")
        return 0

    key = lark.upload_image(a.out)
    for cid in a.chat_id:
        lark.send_image(cid, key)
        logger.info("Đã gửi báo cáo vào %s", cid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
