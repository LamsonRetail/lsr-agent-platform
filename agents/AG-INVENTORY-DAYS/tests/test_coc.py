"""Test tra cứu Code of Conduct KHHH.

Chạy:  cd src && python -m pytest ../tests/test_coc.py -q
Hoặc:  cd src && python ../tests/test_coc.py     (không cần pytest)

Ý nghĩa: khoá lại hành vi "hỏi gì ra mục nào" để lần sau sửa thuật toán tra cứu
hoặc sửa tài liệu mà làm hỏng thì biết ngay.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from coc import answer_from_coc, load_sections, search  # noqa: E402

SECTIONS = load_sections()

# (câu hỏi, chuỗi phải có trong ref của mục trả về)
IN_SCOPE = [
    ("ngày tồn kho mục tiêu của hapas thái lan là bao nhiêu", "3.2"),
    ("ngưỡng tồn kho tại cửa hàng bao nhiêu ngày", "3."),
    ("MAPE là gì", "3.1"),
    ("STR là gì", "3.1"),
    ("chốt PR ngày nào", "4"),
    ("doanh thu khác GMV thế nào", "4"),
    ("cách tính tỷ trọng", "4.5"),
    # v3 tách quy trình combo ra mục riêng 4.10 (v2 nằm chung trong 4.6).
    ("combo Vietful bị lỗi gì", "4."),
    ("ghép combo phải báo trước mấy ngày", "4.10"),
    ("phiếu chuyển kho cần điền gì", "4.9"),
    ("luân chuyển hàng tối thiểu bao nhiêu sản phẩm", "4.9"),
    ("keeper test là gì", "0.3"),
    ("hoàn thành tác vụ nghĩa là gì", "4.7"),
    ("bài học Hazy Kem", "4.8"),
    ("lead time từ Bắc Ninh về kho hoả tốc Hà Nội", "4.4"),
    ("giá trị cốt lõi của công ty", "0.2"),
    ("phép năm bao nhiêu ngày", "0"),
]

# Ngoài phạm vi tài liệu -> PHẢI nói không có, tuyệt đối không bịa.
#
# GIỚI HẠN ĐÃ BIẾT: đây là tra cứu bằng từ khoá, không phải semantic search.
# Câu hỏi mà MỌI từ đều tình cờ có trong tài liệu (vd "thời tiết Hà Nội cuối
# tuần" — "hà nội", "cuối tuần", "thời" đều xuất hiện) vẫn có thể ra một mục
# không liên quan. Vì vậy câu trả lời LUÔN kèm tên mục + số mục để người đọc
# nhận ra ngay là bot trả lệch. Muốn xử lý triệt để thì cần đổi sang embedding.
OUT_OF_SCOPE = [
    "giá cổ phiếu Apple hôm nay",
    "cho tôi công thức làm bánh mì",
    "ai vô địch world cup",
    "giá vàng hôm nay bao nhiêu",
]


def test_in_scope() -> None:
    for question, expected_ref in IN_SCOPE:
        hits = search(question, SECTIONS)
        assert hits, f"không tìm thấy mục nào cho: {question!r}"
        refs = [h[2].ref for h in hits]
        assert any(expected_ref in r for r in refs), \
            f"{question!r} -> {refs}, mong đợi có {expected_ref!r}"


def test_out_of_scope() -> None:
    for question in OUT_OF_SCOPE:
        assert answer_from_coc(question, SECTIONS) is None, \
            f"{question!r} đáng ra phải trả lời 'tài liệu chưa có mục này'"


def test_answer_always_cites_source() -> None:
    for question, _ in IN_SCOPE:
        reply = answer_from_coc(question, SECTIONS)
        assert reply and "— CoC KHHH," in reply, f"thiếu trích nguồn: {question!r}"


# Bot TỰ chen vào (không ai @ nó) — đây là lúc dễ gây phiền nhất trong nhóm
# làm việc thật, nên ngưỡng phải chặt: thà bỏ sót còn hơn trả lời sai.
STRICT_NEN_TRA_LOI = [
    "chốt PR ngày nào",
    "1 năm có bao nhiêu ngày phép",
    "MOQ là gì",
    "ngưỡng tồn kho tại cửa hàng là bao nhiêu ngày",
]
STRICT_NEN_IM_LANG = [
    "trưa nay ăn gì mọi người",                # "trưa" khớp "12h trưa" ở mục 4.1
    "mọi người nhớ nộp báo cáo trước 5h",
    "chị ơi cái file kia gửi em với",
    "hôm nay ai trực kho vậy",
    "mai họp mấy giờ nhỉ",
    "Trước 20.10 KHHH có vào visit với kho Tây Ninh không các bạn",  # hỏi người, không hỏi bot
]


def test_strict_tra_loi_duoc() -> None:
    for q in STRICT_NEN_TRA_LOI:
        assert answer_from_coc(q, SECTIONS, strict=True), f"đáng ra phải trả lời: {q!r}"


def test_strict_im_lang() -> None:
    for q in STRICT_NEN_IM_LANG:
        reply = answer_from_coc(q, SECTIONS, strict=True)
        assert reply is None, f"đáng ra phải im lặng: {q!r} -> {reply!r}"


def test_no_credentials_leaked() -> None:
    """Tài liệu không được chứa tài khoản/mật khẩu hệ thống."""
    body = "\n".join(s.body for s in SECTIONS).lower()
    for banned in ("password:", "mật khẩu:", "matkhau", "pass:"):
        assert banned not in body, f"tài liệu có thể đang chứa credential: {banned!r}"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    print(f"\n{'OK' if not failures else str(failures) + ' test lỗi'} "
          f"— {len(SECTIONS)} mục trong tài liệu.")
    raise SystemExit(1 if failures else 0)
