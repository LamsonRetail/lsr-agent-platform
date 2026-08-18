"""Tra cứu Code of Conduct KHHH để trả lời câu hỏi về quy trình vận hành.

Bot hiện không chạy qua LLM, nên phần kiến thức nền được tra bằng cách chấm điểm
từ khoá trên từng mục của ``knowledge/CODE_OF_CONDUCT_KHHH.md``. Nguyên tắc:
trích THẲNG nội dung trong tài liệu, không diễn giải lại; không tìm thấy thì nói
không có, không bịa.

Dùng độc lập để test:
    python coc.py "ngày tồn kho mục tiêu của hapas thái là bao nhiêu"
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "CODE_OF_CONDUCT_KHHH.md"

# Ngưỡng "có tìm thấy". Dưới ngưỡng -> trả lời không biết, không đoán.
# MIN_COVERAGE chặn dương tính giả: câu hỏi ngoài phạm vi tài liệu thường chỉ
# trúng 1 từ ngẫu nhiên (vd "mưa" khớp "thu mua" sau khi bỏ dấu).
MIN_SCORE = 1.0
MIN_COVERAGE = 0.6
# Phải khớp được ít nhất một từ khoá ĐẶC TRƯNG của câu hỏi, không chỉ toàn từ
# phổ thông: "thời tiết Hà Nội cuối tuần" khớp "hà nội"/"cuối tuần" nhưng
# "thời tiết" thì tài liệu không có -> không được trả lời.
MIN_PEAK_RATIO = 0.6

_SEPARATOR_ROW = re.compile(r"^\|[\s|:-]+\|$")
MAX_CHARS = 1400

# Từ để hỏi / từ nối — không mang thông tin, bỏ khi chấm điểm.
_STOPWORDS = {
    "cai", "cho", "cua", "con", "cung", "duoc", "gi", "gia", "khi", "khong",
    "la", "lam", "nao", "nay", "nhu", "nhung", "nguoi", "o", "phai", "ra",
    "sao", "the", "thi", "tren", "tu", "va", "vao", "voi", "ve", "co", "bao",
    "nhieu", "minh", "team", "toi", "ban", "hoi", "biet", "can", "di", "bi",
    "moi", "hay", "neu", "roi", "day", "kia", "hon", "rat", "qua", "them",
    # Từ để hỏi. "may" (mấy) bắt buộc phải nằm đây: bỏ dấu xong nó trùng "máy"
    # trong "xe máy" -> "1 năm có mấy ngày phép" ra mục Phúc lợi thay vì Nghỉ phép.
    "may", "dau", "vay", "nhi", "the", "a", "o", "voi", "lam", "an", "co",
}


def _strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt. 'đ' KHÔNG tách được bằng NFD nên phải map tay —
    nếu không, 'đơn' -> 'on' và 'đặt' -> 'at', khớp từ khoá sẽ sai hàng loạt."""
    text = text.replace("đ", "d").replace("Đ", "D").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn").lower()


@dataclass
class Section:
    part: str      # "PHẦN 4 — SỔ TAY VẬN HÀNH"
    title: str     # "4.1. Đặt hàng PR & PO"
    ref: str       # "mục 4.1" — dùng để trích nguồn
    body: str

    @property
    def haystack(self) -> str:
        return _strip_accents(f"{self.part}\n{self.title}\n{self.body}")

    @property
    def title_haystack(self) -> str:
        return _strip_accents(f"{self.part} {self.title}")

    @property
    def haystack_accented(self) -> str:
        """Bản GIỮ NGUYÊN DẤU. Bỏ dấu thì 'phạt' = 'phát', 'muốn' = 'muộn' —
        khớp trúng dấu được cộng điểm để phân biệt lại."""
        return f"{self.part}\n{self.title}\n{self.body}".lower()


def _numbered_ref(title: str) -> str | None:
    m = re.match(r"\s*(\d+(?:\.\d+)*)\.?\s", title)
    return f"mục {m.group(1)}" if m else None


def _part_ref(part: str) -> str:
    m = re.match(r"#?\s*PHẦN\s+(\d+)", part)
    return f"Phần {m.group(1)}" if m else "tài liệu"


def load_sections(path: Path | str = DEFAULT_PATH) -> list[Section]:
    """Cắt tài liệu thành các mục theo heading ``##`` / ``###``."""
    text = Path(path).read_text(encoding="utf-8")
    part = "Mở đầu"
    title = "Mở đầu"
    ref = "tài liệu"
    buf: list[str] = []
    out: list[Section] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            out.append(Section(part, title, ref, body))

    for line in text.splitlines():
        if line.startswith("# "):
            flush()
            buf = []
            part = title = line[2:].strip()
            ref = _part_ref(part)
        elif line.startswith("## ") or line.startswith("### "):
            flush()
            buf = []
            title = line.lstrip("#").strip()
            # Heading con không có số (vd 'Nhịp chốt PR' nằm trong 4.1) thì trích
            # nguồn theo mục có số gần nhất phía trên — người đọc tra được.
            ref = _numbered_ref(title) or ref
        else:
            buf.append(line)
    flush()
    return out


def _terms(question: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", _strip_accents(question))
    return [w for w in words if len(w) >= 2 and w not in _STOPWORDS]


def _count(term: str, hay: str) -> int:
    """Đếm theo ranh giới từ — tránh 'ma' khớp trong 'mai', 'ton' trong 'tong'."""
    return len(re.findall(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", hay))


def _defines(term: str, hay: str) -> bool:
    """Mục có DÒNG ĐỊNH NGHĨA cho từ này (đầu ô bảng, hoặc theo sau là = / — / :).

    Nhờ đó "MAPE là gì" ra mục *Chỉ số phải thuộc lòng* / *Từ điển viết tắt*,
    chứ không ra một mục tình cờ nhắc tới MAPE nhiều lần.
    """
    pat = rf"(?:^|\|\s*|\n)\**{re.escape(term)}\**\s*(?:\||=|—|–|-|:|\bla\b)"
    return re.search(pat, hay, re.MULTILINE) is not None


def search(question: str, sections: list[Section] | None = None,
           *, min_score: float = MIN_SCORE,
           min_coverage: float = MIN_COVERAGE,
           limit: int = 3) -> list[tuple[float, float, Section]]:
    """Các mục khớp nhất, điểm cao trước. Rỗng nếu tài liệu không có."""
    sections = sections if sections is not None else load_sections()
    terms = _terms(question)
    if not terms:
        return []

    hays = [s.haystack for s in sections]
    # IDF: từ xuất hiện ở khắp tài liệu ("hàng", "mua") gần như không phân biệt
    # được mục nào; từ hiếm ("voucher", "MAPE") mới là từ khoá thật của câu hỏi.
    idf = {t: math.log(len(sections) / (1 + sum(1 for h in hays if _count(t, h)))) + 1.0
           for t in terms}

    total_weight = sum(idf.values())

    # Kiểm tra phạm vi ở mức CÂU HỎI: từ khoá đặc trưng nhất của câu hỏi có tồn
    # tại trong tài liệu không. "thời tiết Hà Nội cuối tuần" khớp "hà nội" và
    # "cuối tuần" nhưng "tiết" không có ở đâu -> câu hỏi ngoài phạm vi, dừng luôn.
    present = [t for t in terms if any(_count(t, h) for h in hays)]
    if not present or max(idf[t] for t in present) < max(idf.values()) * MIN_PEAK_RATIO:
        return []

    # Từ có dấu trong câu hỏi (người gõ không dấu thì phần này rỗng, không sao).
    accented = [w for w in re.findall(r"[^\W\d_]+", question.lower())
                if _strip_accents(w) in idf and w != _strip_accents(w)]

    scored: list[tuple[float, float, Section]] = []    # (score, coverage, section)
    for s, hay in zip(sections, hays):
        title_hay = s.title_haystack
        score = 0.0
        matched_weight = 0.0
        for t in terms:
            w = idf[t]
            hits = _count(t, hay)
            if hits:
                matched_weight += w
                score += w * (1.0 + min(hits - 1, 4) * 0.25)  # nhắc lại nhiều -> đúng chủ đề
            if _count(t, title_hay):
                score += w * 2.0                              # trúng tiêu đề: ưu tiên mạnh
            if _defines(t, hay):
                score += w * 1.5                              # mục ĐỊNH NGHĨA từ đó

        # Thưởng cho mục khớp ĐÚNG DẤU: "phạt" thật, không phải "phát triển".
        if accented:
            acc_hay = s.haystack_accented
            for w_acc in accented:
                if _count(w_acc, acc_hay):
                    score += idf[_strip_accents(w_acc)] * 1.2

        # Chuẩn hoá theo độ dài: mục dài đương nhiên chứa nhiều từ hơn, không có
        # nghĩa là đúng chủ đề hơn.
        score /= 1.0 + math.log(1.0 + len(hay) / 1200.0)

        # Coverage tính theo TRỌNG SỐ, không theo số lượng từ: câu hỏi ngoài
        # phạm vi ("đội tuyển Việt Nam") chỉ khớp mấy từ phổ thông (viet, nam)
        # còn từ khoá thật (doi, tuyen) thì không có ở đâu -> coverage thấp.
        coverage = matched_weight / total_weight if total_weight else 0.0
        if score > 0:
            scored.append((score, coverage, s))

    scored = [x for x in scored if x[0] >= min_score and x[1] >= min_coverage]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:limit]


def domain_terms(sections: list[Section]) -> set[str]:
    """Từ vựng 'thuộc chuyên môn' — lấy từ TIÊU ĐỀ các mục và cột viết tắt.

    Dùng làm cổng chặn khi bot TỰ chen vào (không ai @ nó): câu hỏi phải chứa ít
    nhất một từ trong đây thì mới được xét. Không có cổng này thì "trưa nay ăn
    gì" khớp "12h trưa" trong mục chốt PR và bot trả lời tầm bậy giữa nhóm.
    """
    vocab: set[str] = set()
    for s in sections:
        vocab.update(_terms(s.title))
        for line in s.body.splitlines():
            line = line.strip()
            if line.startswith("|"):                    # ô đầu của dòng bảng
                first = line.strip("|").split("|")[0]
                if len(first.strip()) <= 30:            # nhãn, không phải câu văn
                    vocab.update(_terms(first))
    return {t for t in vocab if len(t) >= 2}


def _plain(line: str) -> str:
    """Markdown -> chữ thường đọc được trong chat Lark (Lark không render bảng)."""
    line = line.strip()
    if _SEPARATOR_ROW.match(line):
        return ""
    if line.startswith("|"):                       # 1 dòng bảng -> "cột 1: cột 2 · cột 3"
        cells = [c.strip() for c in line.strip("|").split("|")]
        cells = [c for c in cells if c]
        if not cells:
            return ""
        line = cells[0] + (": " + " · ".join(cells[1:]) if len(cells) > 1 else "")
    line = re.sub(r"^[>\-\*\s]*\[[ x]\]\s*", "", line)   # checkbox
    line = re.sub(r"^>\s*", "", line)                    # blockquote
    line = re.sub(r"^#+\s*", "", line)                   # heading
    line = re.sub(r"^[-*•]\s+", "", line)                # bullet
    line = line.replace("<br>", " ").replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", line).strip()


def _relevant_lines(section: Section, terms: list[str], idf: dict[str, float],
                    k: int = 4) -> list[str]:
    """Vài dòng liên quan nhất trong mục, giữ nguyên thứ tự gốc.

    Trả cả mục thì đúng nhưng không ai đọc. Người hỏi "1 năm mấy ngày phép"
    cần đúng dòng nói về phép năm, không cần cả bảng đơn từ.
    """
    scored = []
    for i, raw in enumerate(section.body.splitlines()):
        line = _plain(raw)
        if len(line) < 8:
            continue
        hay = _strip_accents(line)
        score = sum(idf.get(t, 1.0) for t in terms if _count(t, hay))
        scored.append((score, i, line))

    if not scored:
        return []
    # Chỉ giữ dòng THỰC SỰ khớp từ khoá — bỏ dòng dẫn nhập và dòng tiêu đề bảng
    # ("Viết tắt | Nghĩa"), vốn luôn nằm đầu mục nhưng không trả lời gì cả.
    hits = [x for x in scored if x[0] > 0]
    if not hits:
        return [line for _, _, line in scored[:2]]
    hits.sort(key=lambda x: -x[0])
    # Chỉ giữ dòng khớp mạnh gần bằng dòng tốt nhất. Hỏi "1 năm mấy ngày phép"
    # thì dòng "Phép năm: 12 ngày…" ăn đứt mấy dòng bảng chỉ tình cờ có chữ "ngày".
    floor = hits[0][0] * 0.4
    hits = [x for x in hits[:k] if x[0] >= floor]
    return [line for _, _, line in sorted(hits, key=lambda x: x[1])]


def answer_from_coc(question: str, sections: list[Section] | None = None,
                    *, strict: bool = False) -> str | None:
    """Câu trả lời ngắn để gửi vào nhóm, hoặc None nếu tài liệu không có.

    Chỉ trích vài dòng liên quan nhất + số mục để tự tra tiếp — không đổ cả mục.
    ``strict=True`` dùng khi bot tự chen vào: siết ngưỡng và bắt buộc câu hỏi
    phải có từ chuyên môn, thà bỏ sót còn hơn trả lời sai giữa nhóm.
    """
    sections = sections if sections is not None else load_sections()

    if strict:
        if not set(_terms(question)) & domain_terms(sections):
            return None
        hits = search(question, sections, min_coverage=0.8, min_score=2.0)
    else:
        hits = search(question, sections)
    if not hits:
        return None

    terms = _terms(question)
    hays = [s.haystack for s in sections]
    idf = {t: math.log(len(sections) / (1 + sum(1 for h in hays if _count(t, h)))) + 1.0
           for t in terms}

    _, _, s = hits[0]
    lines = _relevant_lines(s, terms, idf)

    out = [_plain(s.title)]
    out += [f"• {ln}" for ln in lines]
    out.append(f"— CoC KHHH, {s.ref}")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--knowledge", default=str(DEFAULT_PATH))
    args = parser.parse_args()

    reply = answer_from_coc(args.question, load_sections(args.knowledge))
    if reply is None:
        print("Tài liệu chưa có mục này.", file=sys.stderr)
        return 1
    print(reply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
