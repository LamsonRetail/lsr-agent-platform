"""Nguồn giả — chạy và test toàn bộ Phase 1 khi chưa có credential nguồn thật.

Đây KHÔNG phải mock trong test. Nó là một `Source` thật, đi qua đúng đường chuẩn hoá của
nguồn thật (`TabularSource.fetch` → `mapping.map_row`), chỉ khác ở chỗ dòng thô lấy từ hằng
số trong file này thay vì gọi API. Nhờ vậy khi cắm nguồn thật vào, phần đã test không đổi.

Dữ liệu cố ý có sẵn các tình huống xấu để test case chạy được mà không cần dựng thêm fixture:
  • INV-003 thiếu ngày đến hạn → B2 (báo thiếu cột, không tự điền)
  • tiền viết "1.234.567đ" và "(2.000.000)" → B3
  • INV-001 có ở cả gsheet và misa, số KHỚP → C8 (chỉ cộng một lần)
  • INV-002 có ở cả hai nguồn, số LỆCH → B5 / C9 (loại khỏi tổng, báo rõ)

Mọi ngày tháng là hằng số, không dùng "hôm nay", để kết quả test không đổi theo thời gian.
"""

from __future__ import annotations

from .base import SourceError, TabularSource

# Mốc thời gian mà bộ dữ liệu giả này được dựng quanh. Test tính tuổi nợ theo mốc này.
FAKE_TODAY = "2026-08-12"

_GSHEET_ROWS: dict[str, list[dict]] = {
    "receivable": [
        {
            "Mã KH": "KH-001", "Tên khách hàng": "Công ty A",
            "Số hoá đơn": "INV-001", "Ngày hoá đơn": "01/07/2026", "Ngày đến hạn": "31/07/2026",
            "Giá trị": "1.234.567đ", "Đã thu": "0",
        },
        {
            "Mã KH": "KH-002", "Tên khách hàng": "Công ty B",
            "Số hoá đơn": "INV-002", "Ngày hoá đơn": "15/05/2026", "Ngày đến hạn": "14/06/2026",
            "Giá trị": "500.000.000", "Đã thu": "100.000.000",
        },
        {
            # Thiếu "Ngày đến hạn" — dòng này phải thành RowError, không được điền mặc định.
            "Mã KH": "KH-003", "Tên khách hàng": "Công ty C",
            "Số hoá đơn": "INV-003", "Ngày hoá đơn": "01/08/2026",
            "Giá trị": "12.000.000", "Đã thu": "0",
        },
        {
            "Mã KH": "KH-004", "Tên khách hàng": "Công ty D",
            "Số hoá đơn": "INV-004", "Ngày hoá đơn": "20/07/2026", "Ngày đến hạn": "20/08/2026",
            "Giá trị": "80.000.000", "Đã thu": "0",
        },
    ],
    "payable": [
        {
            "Mã NCC": "NCC-001", "Tên nhà cung cấp": "Nhà cung cấp X",
            "Số hoá đơn": "PO-001", "Ngày hoá đơn": "01/07/2026", "Ngày đến hạn": "31/07/2026",
            "Giá trị": "300.000.000", "Đã thanh toán": "50.000.000",
        },
    ],
    "revenue": [
        {"Kỳ": "2026-06", "Kênh": "Online", "Mã CH": "", "Doanh thu": "1.500.000.000"},
        {"Kỳ": "2026-06", "Kênh": "Offline", "Mã CH": "CH-01", "Doanh thu": "2.100.000.000"},
        {"Kỳ": "07/2026", "Kênh": "Online", "Mã CH": "", "Doanh thu": "1.800.000.000"},
        {"Kỳ": "07/2026", "Kênh": "Offline", "Mã CH": "CH-01", "Doanh thu": "2.400.000.000"},
        {"Kỳ": "07/2026", "Kênh": "Offline", "Mã CH": "CH-02", "Doanh thu": "900.000.000"},
    ],
    "expense": [
        {"Kỳ": "07/2026", "Mã khoản mục": "6421", "Tên khoản mục": "Chi phí bán hàng",
         "Phòng ban": "Kinh doanh", "Thực tế": "450.000.000", "Ngân sách": "400.000.000"},
        {"Kỳ": "07/2026", "Mã khoản mục": "6422", "Tên khoản mục": "Chi phí quản lý",
         "Phòng ban": "Vận hành", "Thực tế": "(2.000.000)", "Ngân sách": "10.000.000"},
    ],
}

_MISA_ROWS: dict[str, list[dict]] = {
    "receivable": [
        {
            # Khớp gsheet từng đồng → chỉ được cộng MỘT lần vào tổng (C8).
            "ma_kh": "KH-001", "ten_kh": "Công ty A",
            "so_hoa_don": "INV-001", "ngay_hoa_don": "2026-07-01", "ngay_den_han": "2026-07-31",
            "so_tien": "1234567", "da_thu": "0",
        },
        {
            # Lệch gsheet ở "đã thu" → loại khỏi tổng và báo rõ (B5 / C9).
            "ma_kh": "KH-002", "ten_kh": "Công ty B",
            "so_hoa_don": "INV-002", "ngay_hoa_don": "2026-05-15", "ngay_den_han": "2026-06-14",
            "so_tien": "500000000", "da_thu": "150000000",
        },
        {
            "ma_kh": "KH-005", "ten_kh": "Công ty E",
            "so_hoa_don": "INV-005", "ngay_hoa_don": "2026-06-10", "ngay_den_han": "2026-07-10",
            "so_tien": "250000000", "da_thu": "0",
        },
    ],
}


class FakeSource(TabularSource):
    """Nguồn giả mang tên của một nguồn thật.

    `name` cố ý nhận giá trị "gsheet"/"misa" chứ không phải "fake": provenance và natural_key
    phải giống lúc chạy thật, nếu không logic đối chiếu hai nguồn sẽ không được test.
    """

    def __init__(self, name: str, rows: dict[str, list[dict]], *, healthy: bool = True) -> None:
        self.name = name
        self._rows = rows
        self._healthy = healthy

    def supported_tables(self) -> list[str]:
        return sorted(self._rows)

    def read_rows(self, table: str) -> list[dict]:
        if not self._healthy:
            raise SourceError(f"{self.name}: nguồn giả đang được đặt ở trạng thái lỗi")
        return [dict(row) for row in self._rows.get(table, [])]

    def healthcheck(self) -> None:
        if not self._healthy:
            raise SourceError(f"{self.name}: nguồn giả đang được đặt ở trạng thái lỗi")


def fake_gsheet(**kwargs) -> FakeSource:
    return FakeSource("gsheet", _GSHEET_ROWS, **kwargs)


def fake_misa(**kwargs) -> FakeSource:
    return FakeSource("misa", _MISA_ROWS, **kwargs)


def fake_sources() -> list[FakeSource]:
    """Bộ nguồn giả mặc định cho chế độ FIN_FAKE_DATA=1 và cho test."""
    return [fake_gsheet(), fake_misa()]


def empty_source(name: str = "gsheet") -> FakeSource:
    """Nguồn không có dòng nào — dùng cho B7."""
    return FakeSource(name, {"receivable": []})
