"""Chạy tests.jsonl OFFLINE qua consumer.answer() — không cần token/platform/mạng.

Dùng để kiểm nhanh trước khi push (bản chạy qua platform thật: scripts/agent-test.sh).
Chấm giống agent-test.sh: mọi từ khoá trong "expect" phải có trong câu trả lời.

  python3 tests/run_offline.py          # model tắt — kiểm luồng luật (mặc định của CI)
  LSR_MODEL_MODE=auto python3 tests/run_offline.py
"""

from __future__ import annotations

import os

# Bộ offline không gọi mạng: BigQuery bị tắt để kết quả tất định (bản kiểm số sống:
# tests/check_bq.py).
os.environ.setdefault("PLOY_OFFLINE", "1")

import json
import os
import sys

_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _DIR)
import consumer  # noqa: E402

consumer.api = lambda m, p, payload=None, timeout=40: {}   # chặn gọi platform

ok = fail = 0
with open(os.path.join(_DIR, "tests.jsonl"), encoding="utf-8") as f:
    for i, line in enumerate((l for l in f if l.strip()), 1):
        case = json.loads(line)
        ans = consumer.answer(case["q"], {}, {})
        miss = [e for e in case.get("expect", []) if e.lower() not in ans.lower()]
        if miss:
            fail += 1
            print(f"✗ case {i}: {case['q'][:60]!r}\n  thiếu: {miss}\n  trả lời: {ans[:160]}")
        else:
            ok += 1
            print(f"✓ case {i}: {case['q'][:60]!r}")

print(f"\n{ok}/{ok + fail} pass")
sys.exit(1 if fail else 0)
