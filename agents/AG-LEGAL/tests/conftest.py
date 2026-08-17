"""Unit test KHÔNG được gọi model thật.

`brain.route()`/`compress()` chạy CLI `claude` qua subprocess — trong test điều đó vừa
chậm vừa không tất định (cùng câu hỏi có thể phân loại khác nhau). Fixture autouse dưới
đây chặn ở đúng một điểm: `brain.call_claude`. Test nào muốn thử nhánh lỗi thì tự
monkeypatch lại (monkeypatch sau thắng).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from legalkb import brain

STUB_ROUTE = ('{"intent": "s1_qa", "risk": "low", "contract_type": "", '
              '"reason": "stub trong test"}')


@pytest.fixture(autouse=True)
def no_real_model_calls(monkeypatch):
    monkeypatch.setattr(brain, "call_claude",
                        lambda prompt, model=None, timeout=None: STUB_ROUTE)
