"""Test logic consolidate của LSR Brain."""

from __future__ import annotations

from rating_agent.brain import (
    consolidate_team,
    detect_conflict,
    is_reusable,
    is_sensitive,
)


def test_loại_bỏ_dữ_liệu_nhạy_cảm():
    assert is_sensitive("Bảng lương tháng 8 của team")
    assert is_sensitive("Đánh giá cá nhân của Bình")
    assert not is_sensitive("Quy trình xử lý đơn hàng")


def test_nhận_diện_tri_thức_dùng_chung():
    assert is_reusable("Quy trình đổi trả gồm 3 bước")
    assert is_reusable("Công thức tính KPI doanh thu")
    assert not is_reusable("Hôm nay ăn trưa lúc 12h")


def test_consolidate_tạo_ứng_viên_và_bỏ_nhạy_cảm():
    ctx = [
        {"title": "Quy trình đổi trả", "md_content": "Quy trình đổi trả gồm 3 bước...",
         "tags": ["ops"]},
        {"title": "Bảng lương", "md_content": "Bảng lương tháng 8...", "tags": ["hr"]},
        {"title": "Ăn trưa", "md_content": "Team ăn trưa lúc 12h", "tags": []},
    ]
    res = consolidate_team("SQ-OPS", ctx, beliefs=[])
    assert [c.title for c in res.candidates] == ["Quy trình đổi trả"]
    assert res.candidates[0].source_team == "SQ-OPS"
    assert res.skipped_sensitive == 1


def test_detect_conflict_cùng_chủ_đề_ngược_nhau():
    belief = "Luôn xác nhận đơn hàng với khách trước khi giao"
    assert detect_conflict("Không cần xác nhận đơn hàng với khách trước khi giao", belief)
    # khác chủ đề -> không phải conflict
    assert not detect_conflict("Không dùng màu đỏ trong thiết kế banner", belief)
    # cùng chiều -> không conflict
    assert not detect_conflict("Luôn xác nhận đơn hàng với khách trước khi giao hàng", belief)


def test_consolidate_phát_hiện_conflict_kèm_owner():
    beliefs = [{"belief_id": "b1",
                "statement": "Luôn xác nhận đơn hàng với khách trước khi giao"}]
    ctx = [{"title": "Quy ước giao hàng",
            "md_content": "Quy trình: không cần xác nhận đơn hàng với khách trước khi giao",
            "tags": ["ops"]}]
    res = consolidate_team("SQ-OPS", ctx, beliefs, agent_id="AG-OPS",
                           owner_email="ops@lamsonretail.vn")
    assert len(res.conflicts) == 1
    c = res.conflicts[0]
    assert c.belief_id == "b1" and c.owner_email == "ops@lamsonretail.vn"
    assert c.as_payload()["team_id"] == "SQ-OPS"
