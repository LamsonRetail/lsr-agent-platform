"""Regression đa lượt cho luồng biên bản (gate HITL) — chạy offline, không cần token.

Sinh ra từ 4 bug review tìm thấy 12/08 (xem PLOY.md §7). tests.jsonl chỉ chạy được case
1 lượt; các bug này cần NGỮ CẢNH nhiều lượt nên kiểm ở đây.

Chạy:  python3 tests/selfcheck_flows.py   (từ thư mục agent, exit 0 = đạt)
Tên file cố ý KHÔNG bắt đầu bằng test_ để pytest của CI repo không tự collect.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import consumer  # noqa: E402

FAILS = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("✓" if cond else "✗"), name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


class Chat:
    """Hội thoại giả lập: giữ recent_turns như platform, chặn API."""

    def __init__(self):
        self.turns, self.api_calls = [], []
        consumer.api = lambda m, p, payload=None, timeout=40: (self.api_calls.append((m, p)), {})[1]

    def ask(self, q: str) -> str:
        ans = consumer.answer(q, {"recent_turns": self.turns[-12:]}, {})
        self.turns += [{"role": "user", "text": q}, {"role": "assistant", "text": ans}]
        return ans


TRANSCRIPT = ("họp xong rồi, nội dung: Thống nhất đẩy BST T11 thay da lộn. "
              "Giao cho Hạnh chốt danh sách 26 KOC trước ngày 17/08. "
              "Tùng phụ trách brief content du lịch, hạn 20/08.")

# --- Bug #1: phủ định "chưa chốt" không được phép chốt ---
c = Chat()
c.ask(TRANSCRIPT)
r = c.ask("khoan, chưa chốt nhé, sửa mục 2 đã")
check("negation không kích hoạt confirm", "Đã **chốt**" not in r, r[:80])
r = c.ask("tài liệu này ai duyệt?")
check("câu hỏi chứa 'duyệt' không kích hoạt confirm", "Đã **chốt**" not in r, r[:80])
check("chưa có API call nào khi chưa chốt", not c.api_calls, str(c.api_calls))

# --- happy path + Bug #2: chốt xong không chốt lại, không đề xuất trùng ---
r = c.ask("chốt")
check("chốt thật thì chốt", "Đã **chốt**" in r, r[:80])
check("reply kèm biên bản đã chốt", "Trạng thái: đã chốt" in r)
n_calls = len(c.api_calls)
check("chốt tạo đúng 3 call (1 brain + 2 propose)", n_calls == 3, str(c.api_calls))
r = c.ask("chốt")
check("chốt lần 2 bị chặn (idempotent)", "đã chốt trước đó" in r, r[:80])
check("không phát sinh API call trùng", len(c.api_calls) == n_calls)
r = c.ask("tạo task đi")
check("'tạo task' sau khi chốt trả lời đúng trạng thái", "đã chốt" in r and "chưa được" not in r, r[:100])

# --- Bug #4: transcript thô KHÔNG có từ khoá hint vẫn dựng được biên bản ---
raw = ("Hôm nay cả nhóm trao đổi về kế hoạch tháng tới cho thị trường. Sau khi xem số liệu "
       "từng kênh, anh Vinh quyết định chọn phương án B cho chiến dịch cuối năm. "
       "Giao cho Lan chuẩn bị bảng giá mới, hạn 25/08. Mai phụ trách làm việc với đối tác "
       "vận chuyển, deadline 28/08.")
c2 = Chat()
r = c2.ask(raw)
check("transcript thô (không hint) vẫn ra biên bản", "BIÊN BẢN" in r, r[:80])
check("trích được đầu việc từ transcript thô", "Lan" in r and "25/08" in r)

# --- hồi quy: 'chốt' giữa câu khi KHÔNG có nháp → không bị nuốt ---
c3 = Chat()
r = c3.ask("còn mấy ngày tới hạn chốt KOC Tote")
check("'hạn chốt KOC' không có nháp → ra đếm ngược mốc", "17/08" in r, r[:80])

print()
if FAILS:
    print(f"✗ {len(FAILS)} kiểm tra hỏng: {FAILS}")
    sys.exit(1)
print("Tất cả kiểm tra đa lượt ĐẠT ✅")
