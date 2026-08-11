"""lsr_lark — thư viện Lark dùng chung cho mọi agent LSR.

Mục tiêu: tạo agent mới KHÔNG phải viết lại tích hợp Lark, và mọi agent tương tác
Lark một cách ĐỒNG BỘ (chung token + danh bạ open_id, chung định dạng, chung audit).

Hai chế độ — tự chọn qua ``Lark()``:

1. **remote** (khuyến nghị cho agent): agent chỉ cầm ``LSR_AGENT_TOKEN`` và gọi qua
   broker ``platform_api /v1/lark/*``. Không giữ app_secret, không tự cache token,
   không tự resolve open_id — platform lo hết và chia sẻ giữa các agent.

2. **direct**: dành cho dịch vụ lõi giữ ``LARK_APP_ID/SECRET`` (vd platform_api hoặc
   agent long-connection). Gọi thẳng Lark Open Platform, cache token/identity qua store.

Ví dụ (agent):

    from lsr_lark import Lark
    lark = Lark()                       # tự đọc env LSR_PLATFORM_URL + LSR_AGENT_TOKEN
    lark.send("thint@hapas.vn", "Xong báo cáo tuần ✅")
    oid = lark.resolve("ngadt@hapas.vn")
"""

from __future__ import annotations

import os

from .errors import LarkError
from .remote import RemoteLark

__all__ = ["Lark", "RemoteLark", "LarkError", "__version__"]
__version__ = "0.1.0"


def Lark(mode: str | None = None, **kwargs):
    """Factory: trả client phù hợp.

    mode=None → tự suy: có LARK_APP_ID/SECRET → 'direct', ngược lại → 'remote'.
    """

    mode = mode or ("direct" if os.environ.get("LARK_APP_ID") and
                    os.environ.get("LARK_APP_SECRET") else "remote")
    if mode == "direct":
        from .direct import DirectLark  # import trễ: direct cần requests + store
        return DirectLark(**kwargs)
    return RemoteLark(**kwargs)
