"""Giao diện chung cho mọi nguồn dữ liệu.

Thêm nguồn mới = thêm một file trong thư mục này implement `Source`. Không sửa `sync.py`
mỗi lần thêm nguồn.

Hợp đồng mà mọi nguồn phải giữ:
  • Chỉ ĐỌC. Không nguồn nào được ghi ngược về hệ thống gốc.
  • Trả về bản ghi đã đúng schema trong data_hub/schema.py, không phải dict thô.
  • Dòng nguồn hỏng thì báo lỗi kèm số dòng, KHÔNG bỏ qua im lặng và KHÔNG điền mặc định.
  • Không có dữ liệu là trả list rỗng, khác hoàn toàn với việc raise.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class SourceError(RuntimeError):
    """Nguồn không đọc được: mất mạng, hết quyền, đổi cấu trúc. Kèm tên nguồn."""


@dataclass(frozen=True)
class RowError:
    """Một dòng nguồn không hợp lệ. Gom lại để báo một lần thay vì dừng ở dòng đầu tiên."""

    row_ref: str
    reason: str


@dataclass
class FetchResult:
    """Kết quả đọc một bảng từ một nguồn.

    `records` và `errors` cùng có giá trị: đọc được 90 dòng và 10 dòng lỗi là kết quả
    `partial`, không phải thành công cũng không phải thất bại.
    """

    records: list[object]
    errors: list[RowError]

    @property
    def status(self) -> str:
        if self.errors and self.records:
            return "partial"
        return "failed" if self.errors else "ok"


class Source(ABC):
    """Một nguồn dữ liệu tài chính."""

    #: Nhãn ngắn đi vào Provenance.source — "gsheet" | "misa" | "larkbase"
    name: str

    @abstractmethod
    def supported_tables(self) -> list[str]:
        """Các bảng nguồn này cấp được: receivable, payable, revenue, expense, cashflow."""

    @abstractmethod
    def fetch(self, table: str) -> FetchResult:
        """Đọc một bảng. Raise SourceError nếu không tiếp cận được nguồn."""

    @abstractmethod
    def healthcheck(self) -> None:
        """Kiểm tra credential và quyền truy cập. Raise SourceError nếu không dùng được.

        Gọi trước khi chạy đồng bộ để biết sớm, thay vì phát hiện giữa lúc đang ghi dữ liệu.
        """
