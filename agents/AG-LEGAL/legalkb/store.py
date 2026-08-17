"""SQLite lưu ánh xạ tài liệu Lark ↔ source NotebookLM (bảng legal_sources).

State nội bộ của engine KB — hội thoại/facts vẫn ở platform theo nguyên tắc chung.
File DB đặt trong volume của container (mặc định ./data/legalkb.db).
"""
import os
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS legal_sources (
  key            TEXT PRIMARY KEY,   -- wiki:<node_token> | drive:<file_token>
  kind           TEXT NOT NULL,      -- wiki | drive
  obj_type       TEXT,               -- docx | file | pdf ...
  title          TEXT,
  lark_url       TEXT,
  edit_ts        TEXT,               -- obj_edit_time / modified_time từ Lark
  content_hash   TEXT,
  nlm_source_id  TEXT,
  notebook_id    TEXT,
  status         TEXT NOT NULL DEFAULT 'synced',  -- synced | removed | error
  error          TEXT,
  updated_at     REAL
);
CREATE INDEX IF NOT EXISTS idx_legal_sources_nlm ON legal_sources(nlm_source_id);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);

-- Khung "Pháp chế in the loop" (PLAN §4). MỘT bảng cho cả S1..S5 thay vì 5 bảng rời.
CREATE TABLE IF NOT EXISTS legal_gates (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  kind           TEXT NOT NULL,   -- s1_answer|s2_draft|s3_review|s4_digest|s5_step3|s5_step5
  level          TEXT NOT NULL,   -- observe | gate
  risk           TEXT,            -- low | medium | high
  session_id     TEXT,
  channel        TEXT,
  requester_ref  TEXT,            -- open_id người yêu cầu
  title          TEXT,
  payload        TEXT,            -- JSON: nội dung để người duyệt đọc
  status         TEXT NOT NULL DEFAULT 'open',
                 -- open|joined|approved|changes_requested|rejected|expired|auto_passed
  reviewer       TEXT,            -- email người quyết định
  comment        TEXT,
  round          INTEGER NOT NULL DEFAULT 1,
  sla_deadline   REAL,
  reminded       INTEGER NOT NULL DEFAULT 0,
  created_at     REAL,
  decided_at     REAL
);
CREATE INDEX IF NOT EXISTS idx_gates_status ON legal_gates(status, sla_deadline);
CREATE INDEX IF NOT EXISTS idx_gates_session ON legal_gates(session_id);

-- Ai được duyệt/được thông báo. Seed bằng seed_roles.py, không hard-code trong code.
CREATE TABLE IF NOT EXISTS legal_roles (
  email          TEXT NOT NULL,
  role           TEXT NOT NULL,   -- legal_reviewer | approver | digest_owner
  contract_type  TEXT,            -- NULL = mọi loại
  open_id        TEXT,            -- resolve qua /v1/lark/resolve, cache lại
  name           TEXT,
  active         INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (email, role, contract_type)
);

-- Trạng thái takeover của từng hội thoại (N3).
CREATE TABLE IF NOT EXISTS session_modes (
  session_id     TEXT PRIMARY KEY,
  mode           TEXT NOT NULL DEFAULT 'auto',   -- auto | joined | paused
  taken_by       TEXT,
  chat_id        TEXT,
  since          REAL
);
"""


class SourceStore:
    """Dùng chung giữa luồng chat và luồng sync → connection cho phép đa luồng,
    mọi truy cập bọc trong lock (SQLite chỉ cho 1 writer)."""

    def __init__(self, path=None):
        path = path or os.environ.get("LEGALKB_DB", "data/legalkb.db")
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self.db.executescript(SCHEMA)

    def get(self, key):
        with self._lock:
            r = self.db.execute("SELECT * FROM legal_sources WHERE key=?",
                                (key,)).fetchone()
        return dict(r) if r else None

    def all_active(self):
        with self._lock:
            rows = self.db.execute(
                "SELECT * FROM legal_sources WHERE status != 'removed'").fetchall()
        return [dict(r) for r in rows]

    def upsert(self, key, **fields):
        fields["updated_at"] = time.time()
        cur = self.get(key)
        with self._lock:
            if cur:
                sets = ", ".join(f"{k}=?" for k in fields)
                self.db.execute(f"UPDATE legal_sources SET {sets} WHERE key=?",
                                (*fields.values(), key))
            else:
                fields.setdefault("status", "synced")
                cols = ["key", *fields.keys()]
                self.db.execute(
                    f"INSERT INTO legal_sources ({', '.join(cols)}) "
                    f"VALUES ({', '.join('?' * len(cols))})",
                    (key, *fields.values()))
            self.db.commit()

    def mark_removed(self, key):
        with self._lock:
            self.db.execute(
                "UPDATE legal_sources SET status='removed', updated_at=? WHERE key=?",
                (time.time(), key))
            self.db.commit()

    def by_nlm_source(self, nlm_source_id):
        with self._lock:
            r = self.db.execute(
                "SELECT * FROM legal_sources WHERE nlm_source_id=? AND status='synced'",
                (nlm_source_id,)).fetchone()
        return dict(r) if r else None

    # ---- meta ----
    def set_meta(self, k, v):
        with self._lock:
            self.db.execute(
                "INSERT INTO meta (k, v) VALUES (?, ?) "
                "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))
            self.db.commit()

    def get_meta(self, k, default=None):
        with self._lock:
            r = self.db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r["v"] if r else default

    # ---- truy vấn chung cho gates/roles/session_modes ----

    def query(self, sql, params=()):
        with self._lock:
            rows = self.db.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def write(self, sql, params=()):
        """INSERT/UPDATE/DELETE — trả lastrowid (hữu ích khi mở gate mới)."""
        with self._lock:
            cur = self.db.execute(sql, params)
            self.db.commit()
            return cur.lastrowid
