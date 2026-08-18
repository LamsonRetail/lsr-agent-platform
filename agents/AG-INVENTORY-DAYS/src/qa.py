"""Hiểu câu hỏi trong nhóm chat và trả lời từ dữ liệu thật.

Hai nguồn trả lời:

1. **Tồn kho** — từ dữ liệu SKU (Excel/BigQuery).
2. **Quy trình vận hành** — từ ``knowledge/CODE_OF_CONDUCT_KHHH.md`` qua
   ``coc.py``. Dùng khi câu hỏi không thuộc nhóm tồn kho.

Tách riêng khỏi phần nhận sự kiện Lark để test được độc lập:
    python qa.py --excel "<file>" "1 mã tồn cao nhất"
    python qa.py --excel "<file>" "chốt PR ngày nào"

Khi Lark đã bật scope + event subscription, listener chỉ cần gọi
``answer(question, skus)`` rồi gửi chuỗi trả về.
"""

from __future__ import annotations

import argparse
import re
import unicodedata

import yaml

from inventory_days import SkuResult, load_excel_skus

try:
    from coc import answer_from_coc, load_sections
except ImportError:  # thiếu file kiến thức nền -> bot vẫn chạy phần tồn kho
    answer_from_coc = None  # type: ignore[assignment]
    load_sections = None  # type: ignore[assignment]


def _strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt để khớp từ khoá kể cả khi người dùng gõ không dấu."""
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn").lower()


def _extract_count(question: str, default: int = 5) -> int:
    """Lấy số lượng mã người dùng muốn xem ('3 mã tồn cao nhất' -> 3)."""
    m = re.search(r"\b(\d+)\s*(mã|ma|sku)", _strip_accents(question))
    if m:
        return max(1, min(int(m.group(1)), 50))
    return default


def _fmt(s: SkuResult, *, decimals: int = 0) -> str:
    days = f"{s.current_days:,.{decimals}f}"
    return (f"{s.sku} — {s.name}: {days} ngày tồn "
            f"(tồn {s.current_qty:,.0f}, bán {s.velocity_per_day:,.1f}/ngày)")


# Các câu trả lời KHÔNG chắc chắn. Khi bot tự nhảy vào (không ai @ nó) thì
# những câu này bị nuốt — im lặng tốt hơn là chen vào để nói "mình không biết".
_UNSURE_PREFIXES = (
    "Mình chưa tra được câu này",
    "Bot chưa được nạp dữ liệu tồn kho",
    "Không tìm thấy mã ",
    "Chưa có dữ liệu",
)


def is_confident(reply: str) -> bool:
    return not reply.startswith(_UNSURE_PREFIXES)


def answer(question: str, skus: list[SkuResult], coc_sections=None,
           *, only_confident: bool = False) -> str | None:
    """Trả lời câu hỏi. Không biết thì nói không biết, không bịa.

    Ưu tiên dữ liệu tồn kho; câu hỏi không thuộc nhóm đó thì tra Code of Conduct.
    ``coc_sections`` truyền vào để không phải đọc lại file mỗi tin nhắn.
    ``only_confident=True`` -> trả None thay vì câu "mình không biết".
    """
    reply = _answer_text(question, skus, coc_sections, strict=only_confident)
    if only_confident and not is_confident(reply):
        return None
    return reply


def _answer_text(question: str, skus: list[SkuResult], coc_sections=None,
                 *, strict: bool = False) -> str:
    q = _strip_accents(question)
    rated = [s for s in skus if s.current_days is not None]
    n = _extract_count(question)

    # 1) Hỏi về 1 mã SKU cụ thể (ưu tiên cao nhất — người dùng gõ hẳn mã ra).
    m = re.search(r"\b([a-z]{2,4}\d{5,}[-a-z0-9]*)\b", q)
    if m:
        code = m.group(1).upper()
        found = [s for s in skus if s.sku.upper() == code]
        if not found:
            found = [s for s in skus if code in s.sku.upper()]
        if not skus:
            return ("Bot chưa được nạp dữ liệu tồn kho nên không tra được mã "
                    f"{code}. (Chạy lại bot kèm `--excel <file>`.)")
        if found:
            s = found[0]
            if s.current_days is None:
                return (f"{s.sku} — {s.name}: còn tồn {s.current_qty:,.0f} nhưng "
                        f"tốc độ bán = 0 nên không quy đổi được ra ngày tồn (vốn chết).")
            return _fmt(s, decimals=1)
        return f"Không tìm thấy mã {code} trong dữ liệu."

    # 2) Vốn chết / không bán được.
    if any(k in q for k in ("von chet", "khong ban duoc", "tdb = 0", "tdb=0", "khong ban")):
        dead = [s for s in skus if s.current_days is None and s.current_qty > 0]
        if not dead:
            return "Không có mã nào còn tồn mà tốc độ bán = 0."
        top = sorted(dead, key=lambda s: s.current_qty, reverse=True)[:n]
        lines = [f"Có {len(dead)} mã còn tồn nhưng không bán được (TĐB=0). "
                 f"{min(n, len(dead))} mã tồn nhiều nhất:"]
        lines += [f"  • {s.sku} — {s.name}: tồn {s.current_qty:,.0f}" for s in top]
        return "\n".join(lines)

    # 3) Tồn thấp / rủi ro hết hàng.
    if any(k in q for k in ("ton thap", "sap het", "het hang", "thieu hang", "rui ro")):
        low = sorted([s for s in rated if s.velocity_per_day > 0], key=lambda s: s.current_days)[:n]
        if not low:
            return "Chưa có dữ liệu để xếp hạng tồn thấp."
        head = "Mã tồn thấp nhất:" if n == 1 else f"Top {n} mã tồn thấp nhất (rủi ro hết hàng):"
        return "\n".join([head] + [f"  • {_fmt(s, decimals=1)}" for s in low])

    # 4) Tồn cao / đọng vốn (mặc định cho các câu hỏi xếp hạng còn lại).
    if any(k in q for k in ("ton cao", "ton nhieu", "ban cham", "dong von", "ton kho cao")):
        high = sorted(rated, key=lambda s: s.current_days, reverse=True)[:n]
        if not high:
            return "Chưa có dữ liệu để xếp hạng tồn cao."
        head = "Mã tồn cao nhất:" if n == 1 else f"Top {n} mã tồn cao nhất:"
        return "\n".join([head] + [f"  • {_fmt(s)}" for s in high])

    # 5) Không phải câu hỏi tồn kho -> tra quy trình trong Code of Conduct KHHH.
    if answer_from_coc is not None:
        from_coc = answer_from_coc(question, coc_sections, strict=strict)
        if from_coc:
            return from_coc

    # Không tra được thì nói thẳng — thà im hơn là đoán bừa một con số.
    return ("Mình chưa tra được câu này. Mình biết 2 thứ:\n"
            "• Quy trình KHHH (Code of Conduct) — vd \"chốt PR ngày nào\", "
            "\"ngưỡng tồn kho cửa hàng\"\n"
            "• Tồn kho theo mã — vd \"top 5 mã tồn cao\", \"mã nào sắp hết hàng\"")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", help="Câu hỏi cần trả lời")
    parser.add_argument("--config", default="../config/thresholds.yaml")
    parser.add_argument("--excel", required=True)
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    cfg = dict(next(c for c in config["sources"].values() if c.get("data_source") == "excel"))
    cfg["_excel_path"] = args.excel

    sections = load_sections() if load_sections is not None else None
    print(answer(args.question, load_excel_skus(cfg), sections))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
