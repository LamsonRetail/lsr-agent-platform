"""Điều phối đồng bộ: nguồn → chuẩn hoá → FIN-HUB. Phase 1, Hương.

CHƯA IMPLEMENT.

Luật đã chốt trong docs/DATA_MODEL.md, đừng đổi khi implement:
  • Một nguồn chết KHÔNG làm dừng các nguồn còn lại (B4).
  • Hai nguồn lệch số cùng natural_key: giữ CẢ HAI bản ghi, ghi sync_log status=partial,
    báo squad. KHÔNG tự chọn nguồn nào đáng tin hơn (B5).
  • Idempotent: chạy hai lần trên cùng dữ liệu nguồn không được nhân đôi dòng (B6).
  • Nguồn rỗng: ghi sync_log "0 dòng", KHÔNG xoá dữ liệu cũ trên FIN-HUB (B7).
  • healthcheck() mọi nguồn trước khi ghi dòng đầu tiên.
"""

from __future__ import annotations

from .schema import SyncLog
from .sources.base import Source


def run_sync(sources: list[Source], tables: list[str]) -> list[SyncLog]:
    """Đồng bộ các bảng từ các nguồn vào FIN-HUB. Trả nhật ký từng (nguồn, bảng)."""
    raise NotImplementedError("Phase 1 — xem docstring module")


def find_discrepancies(records: list[object]) -> list[str]:
    """Tìm các natural_key có số khác nhau giữa các nguồn.

    Trả mô tả để đưa vào SyncLog.discrepancies và báo squad. Không sửa dữ liệu.
    """
    raise NotImplementedError("Phase 1 — xem docstring module")
