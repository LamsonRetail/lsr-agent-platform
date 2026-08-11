"""Cache store cho DirectLark — token + danh tính (email→open_id).

Có 2 hiện thực:
- ``MemoryStore``: cache trong tiến trình (mặc định, đủ cho 1 agent).
- ``PostgresStore``: cache DÙNG CHUNG qua Postgres (bảng lark_token_cache / lark_identity_cache)
  — để nhiều service/agent chia sẻ 1 token và 1 danh bạ, khớp đúng schema platform_api.
"""

from __future__ import annotations

import time
from typing import Protocol


class CacheStore(Protocol):
    def get_token(self, app_id: str) -> tuple[str, float] | None: ...
    def set_token(self, app_id: str, token: str, expire_at: float) -> None: ...
    def get_identity(self, email: str) -> str | None: ...
    def set_identity(self, email: str, open_id: str) -> None: ...


class MemoryStore:
    def __init__(self) -> None:
        self._tok: dict[str, tuple[str, float]] = {}
        self._ident: dict[str, str] = {}

    def get_token(self, app_id):
        t = self._tok.get(app_id)
        return t if t and time.time() < t[1] else None

    def set_token(self, app_id, token, expire_at):
        self._tok[app_id] = (token, expire_at)

    def get_identity(self, email):
        return self._ident.get((email or "").lower())

    def set_identity(self, email, open_id):
        if email and open_id:
            self._ident[(email or "").lower()] = open_id


class PostgresStore:
    """Chia sẻ cache qua Postgres. ``conn_factory`` trả về psycopg connection.

    Bảng trùng khớp platform_api để mọi thứ đọc chung một nguồn.
    """

    def __init__(self, conn_factory) -> None:
        self._cf = conn_factory
        self._ensure()

    def _ensure(self) -> None:
        try:
            with self._cf() as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS lark_token_cache ("
                             "app_id text PRIMARY KEY, token text, expire_at timestamptz)")
                conn.execute("CREATE TABLE IF NOT EXISTS lark_identity_cache ("
                             "email text PRIMARY KEY, open_id text, updated_at timestamptz DEFAULT now())")
                conn.commit()
        except Exception:
            pass

    def get_token(self, app_id):
        try:
            with self._cf() as conn:
                row = conn.execute("SELECT token, extract(epoch from expire_at) exp "
                                   "FROM lark_token_cache WHERE app_id=%s", (app_id,)).fetchone()
            if row and row[0] and row[1] and time.time() < float(row[1]):
                return (row[0], float(row[1]))
        except Exception:
            pass
        return None

    def set_token(self, app_id, token, expire_at):
        try:
            with self._cf() as conn:
                conn.execute("INSERT INTO lark_token_cache (app_id, token, expire_at) "
                             "VALUES (%s,%s,to_timestamp(%s)) ON CONFLICT (app_id) DO UPDATE "
                             "SET token=EXCLUDED.token, expire_at=EXCLUDED.expire_at",
                             (app_id, token, expire_at))
                conn.commit()
        except Exception:
            pass

    def get_identity(self, email):
        try:
            with self._cf() as conn:
                row = conn.execute("SELECT open_id FROM lark_identity_cache WHERE email=%s",
                                   ((email or "").lower(),)).fetchone()
            return row[0] if row and row[0] else None
        except Exception:
            return None

    def set_identity(self, email, open_id):
        if not (email and open_id):
            return
        try:
            with self._cf() as conn:
                conn.execute("INSERT INTO lark_identity_cache (email, open_id, updated_at) "
                             "VALUES (%s,%s,now()) ON CONFLICT (email) DO UPDATE "
                             "SET open_id=EXCLUDED.open_id, updated_at=now()",
                             ((email or "").lower(), open_id))
                conn.commit()
        except Exception:
            pass
