"""Sinh prototype dashboard HTML cho 6 màn hình đánh giá.

Import lazy để chạy được ``python -m rating_agent.reporting.dashboard`` mà không
cảnh báo runpy.
"""

from __future__ import annotations

__all__ = ["build", "render_html"]


def __getattr__(name: str):  # PEP 562 - lazy import
    if name in __all__:
        from . import dashboard

        return getattr(dashboard, name)
    raise AttributeError(name)
