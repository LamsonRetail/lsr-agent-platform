"""LSR Collector — nhận trace từ Telemetry SDK và lưu vào Postgres.

Endpoint:
  GET  /health              — kiểm tra sống
  POST /v1/traces           — nhận 1 AgentRunTrace (JSON), lưu DB
  GET  /v1/traces           — liệt kê trace gần đây (?agent_id=&limit=)
  GET  /v1/stats            — thống kê token nhanh theo agent

Xác thực ingest: header Authorization: Bearer <COLLECTOR_INGEST_TOKEN>.
"""

from __future__ import annotations

import json
import os
import re

import psycopg
from fastapi import FastAPI, Header, HTTPException
from psycopg.rows import dict_row

DATABASE_URL = os.environ["DATABASE_URL"]
INGEST_TOKEN = os.environ.get("COLLECTOR_INGEST_TOKEN", "")
# --- PII guard: che dữ liệu nhạy cảm TRƯỚC khi lưu (chống lộ vào DB/BigQuery) ---
PII_REDACT = os.environ.get("PII_REDACT", "true").lower() != "false"
_PII_PATTERNS = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,16}\b")),          # thẻ ngân hàng
    ("PHONE", re.compile(r"\b(?:\+?84|0)\d{9,10}\b")),         # SĐT VN
    ("ID", re.compile(r"\b\d{12}\b|\b\d{9}\b")),               # CCCD/CMND
]


def _redact(text: str) -> tuple[str, int]:
    """Trả (text đã che, số lần che). Giữ nguyên nếu tắt PII_REDACT."""

    if not text or not PII_REDACT:
        return text or "", 0
    n = 0
    for label, pat in _PII_PATTERNS:
        text, k = pat.subn(f"[{label}]", text)
        n += k
    return text, n


def _duration_ms(started: str | None, finished: str | None) -> int | None:
    """Tính thời lượng (ms) từ 2 mốc ISO-8601; None nếu không parse được."""

    if not started or not finished:
        return None
    from datetime import datetime
    try:
        s = datetime.fromisoformat(started.replace("Z", "+00:00"))
        f = datetime.fromisoformat(finished.replace("Z", "+00:00"))
        return max(0, int((f - s).total_seconds() * 1000))
    except Exception:
        return None

app = FastAPI(title="LSR Collector", version="0.1.0")


def _db() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


_SCHEMA_READY = False


def _ensure_schema() -> None:
    """Tạo bảng nếu chưa có (idempotent) — an toàn với thời điểm DB sẵn sàng."""

    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_traces (
                id            bigserial PRIMARY KEY,
                run_id        text,
                agent_id      text,
                task_id       text,
                source        text,
                input_tokens  int,
                output_tokens int,
                total_tokens  int,
                tool_calls    int,
                final_output  text,
                raw           jsonb,
                received_at   timestamptz DEFAULT now()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_traces_agent ON agent_traces(agent_id)"
        )
        # PII guard: đếm số lần che trong mỗi trace (0 = sạch).
        conn.execute("ALTER TABLE agent_traces ADD COLUMN IF NOT EXISTS pii_flags int DEFAULT 0")
        # Item 1 (observability): tích luỹ sẵn cho UI metrics Sóng 4.
        conn.execute("ALTER TABLE agent_traces ADD COLUMN IF NOT EXISTS duration_ms int")
        conn.execute("ALTER TABLE agent_traces ADD COLUMN IF NOT EXISTS status text DEFAULT 'ok'")
        conn.execute("ALTER TABLE agent_traces ADD COLUMN IF NOT EXISTS error text")
        # Item 5 (retention/analytics): index theo thời gian nhận.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_received ON agent_traces(received_at)")
        # Item 3 (enforcement surface): bảng policy do platform_api (admin) ghi,
        # collector ĐỌC để chặn runtime tại /v1/policy/check. Rỗng → allow (no-op).
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS policies (
                policy_id  text PRIMARY KEY,
                agent_id   text,              -- NULL/'*' = áp mọi agent
                phase      text,              -- pre_tool | pre_prompt | *
                effect     text DEFAULT 'deny',   -- deny | allow
                rule       jsonb,             -- {tools:[...], patterns:[...], ...}
                reason     text,
                active     boolean DEFAULT true,
                created_at timestamptz DEFAULT now()
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_policies_agent ON policies(agent_id)")
        # Resource index: file/link được share cho agent (lưu ngoài memory).
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS resource_index (
                id          bigserial PRIMARY KEY,
                resource_id text,
                agent_id    text,
                kind        text,
                title       text,
                uri         text,
                mime        text,
                folder      text,
                tags        text[],
                summary     text,
                shared_by   text,
                shared_at   timestamptz,
                search_blob text,
                raw         jsonb,
                received_at timestamptz DEFAULT now(),
                tsv tsvector GENERATED ALWAYS AS (
                    to_tsvector('simple'::regconfig, coalesce(search_blob,''))
                ) STORED
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_res_tsv ON resource_index USING gin(tsv)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_res_agent ON resource_index(agent_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_res_folder ON resource_index(folder)")
        conn.commit()
    _SCHEMA_READY = True


@app.on_event("startup")
def _startup() -> None:
    try:
        _ensure_schema()
    except Exception:  # DB có thể chưa sẵn sàng — sẽ tạo lazy ở request đầu
        pass


def _check_auth(authorization: str) -> None:
    if INGEST_TOKEN and authorization != f"Bearer {INGEST_TOKEN}":
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _agent_blocked(conn, agent_id: str) -> bool:
    """Agent bị deactivate → từ chối nhận trace.

    Đây là cơ chế 'cắt' cho agent EXTERNAL (platform không kill được process của họ):
    không nhận trace = ngoài governance, và dashboard thấy ngay agent đã dừng báo cáo.
    """

    if not agent_id:
        return False
    try:
        row = conn.execute(
            "SELECT status FROM agents WHERE agent_id=%s", (agent_id,)
        ).fetchone()
    except Exception:
        return False  # bảng agents chưa có (platform_api chưa khởi tạo) → cho qua
    return bool(row and row.get("status") == "deactivated")


@app.post("/v1/traces")
def ingest(trace: dict, authorization: str = Header(default="")) -> dict:
    _check_auth(authorization)
    _ensure_schema()
    with _db() as conn:
        if _agent_blocked(conn, trace.get("agent_id")):
            raise HTTPException(
                status_code=403,
                detail="agent đang deactivated — platform không nhận trace",
            )
    llm_calls = trace.get("llm_calls", []) or []
    it = sum(int(c.get("input_tokens", 0)) for c in llm_calls)
    ot = sum(int(c.get("output_tokens", 0)) for c in llm_calls)
    # PII guard: che final_output + toàn bộ raw (che trên chuỗi JSON, giữ cấu trúc).
    final_out, n1 = _redact(trace.get("final_output") or "")
    raw_json, n2 = _redact(json.dumps(trace, ensure_ascii=False))
    pii_flags = n1 + n2
    # Item 1: suy ra status/duration ngay cả khi client chưa gửi (từ dữ liệu sẵn có).
    tcs = trace.get("tool_calls", []) or []
    status = trace.get("status") or ("error" if trace.get("error")
             or any(c.get("ok") is False for c in tcs) else "ok")
    error = (trace.get("error") or "")[:500]
    duration_ms = trace.get("duration_ms")
    if duration_ms is None:
        duration_ms = _duration_ms(trace.get("started_at"), trace.get("finished_at"))
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO agent_traces
              (run_id, agent_id, task_id, source, input_tokens, output_tokens,
               total_tokens, tool_calls, final_output, raw, pii_flags,
               duration_ms, status, error)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                trace.get("run_id"),
                trace.get("agent_id"),
                trace.get("task_id"),
                trace.get("source"),
                it,
                ot,
                it + ot,
                len(tcs),
                final_out,
                raw_json,
                pii_flags,
                duration_ms,
                status,
                error,
            ),
        )
        conn.commit()
    return {"ok": True, "total_tokens": it + ot, "pii_redacted": pii_flags, "status": status}


@app.get("/v1/traces")
def list_traces(agent_id: str | None = None, limit: int = 20) -> list[dict]:
    _ensure_schema()
    query = (
        "SELECT run_id, agent_id, task_id, total_tokens, tool_calls, received_at "
        "FROM agent_traces"
    )
    args: list = []
    if agent_id:
        query += " WHERE agent_id = %s"
        args.append(agent_id)
    query += " ORDER BY id DESC LIMIT %s"
    args.append(limit)
    with _db() as conn:
        return conn.execute(query, args).fetchall()


@app.get("/v1/stats")
def stats() -> list[dict]:
    _ensure_schema()
    with _db() as conn:
        return conn.execute(
            """
            SELECT agent_id,
                   count(*)            AS runs,
                   sum(total_tokens)   AS total_tokens,
                   sum(tool_calls)     AS tool_calls,
                   coalesce(sum(pii_flags),0) AS pii_flags
            FROM agent_traces
            GROUP BY agent_id
            ORDER BY total_tokens DESC NULLS LAST
            """
        ).fetchall()


# ----------------------- Policy check (enforcement surface) -----------------------

@app.post("/v1/policy/check")
def policy_check(body: dict, authorization: str = Header(default="")) -> dict:
    """Điểm CHẶN runtime DUY NHẤT cho agent (gọi bởi plugin ở PreToolUse/pre-prompt).

    Trả {"decision":"allow"|"deny", "reason": ...}. Rỗng policy → allow (no-op).
    Guardrails Sóng 1 chỉ cần THÊM rule vào bảng policies, KHÔNG sửa agent/plugin.
    """

    _check_auth(authorization)
    _ensure_schema()
    agent_id = body.get("agent_id") or ""
    phase = body.get("phase") or ""
    tool = body.get("tool") or ""
    text = " ".join(str(body.get(k) or "") for k in ("prompt", "arguments"))
    with _db() as conn:
        if _agent_blocked(conn, agent_id):
            return {"decision": "deny", "reason": "agent đang deactivated"}
        rows = conn.execute(
            "SELECT effect, rule, reason FROM policies "
            "WHERE active=true AND (agent_id=%s OR agent_id IS NULL OR agent_id='*') "
            "AND (phase=%s OR phase='*')",
            (agent_id, phase),
        ).fetchall()
    for r in rows:
        rule = r.get("rule") or {}
        hit = False
        tools = rule.get("tools") or []
        if tool and tools and tool in tools:
            hit = True
        for pat in rule.get("patterns") or []:
            try:
                if re.search(pat, text, re.I):
                    hit = True
                    break
            except re.error:
                continue
        if hit and (r.get("effect") or "deny") == "deny":
            return {"decision": "deny", "reason": r.get("reason") or "vi phạm policy"}
    return {"decision": "allow"}


# ----------------------- Resource Index -----------------------

@app.post("/v1/resources")
def index_resource(resource: dict, authorization: str = Header(default="")) -> dict:
    _check_auth(authorization)
    _ensure_schema()
    tags = resource.get("tags") or []
    if not isinstance(tags, list):
        tags = [str(tags)]
    search_blob = " ".join(
        [
            resource.get("title") or "",
            resource.get("summary") or "",
            " ".join(str(t) for t in tags),
            resource.get("uri") or "",
        ]
    )
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO resource_index
              (resource_id, agent_id, kind, title, uri, mime, folder, tags,
               summary, shared_by, shared_at, search_blob, raw)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                resource.get("resource_id"),
                resource.get("agent_id"),
                resource.get("kind", "link"),
                resource.get("title"),
                resource.get("uri"),
                resource.get("mime"),
                resource.get("folder"),
                tags,
                resource.get("summary"),
                resource.get("shared_by"),
                resource.get("shared_at") or None,
                search_blob,
                json.dumps(resource),
            ),
        )
        conn.commit()
    return {"ok": True, "resource_id": resource.get("resource_id")}


@app.get("/v1/resources/search")
def search_resources(
    q: str = "",
    agent_id: str | None = None,
    folder: str | None = None,
    limit: int = 20,
) -> list[dict]:
    _ensure_schema()
    cols = ("resource_id, agent_id, kind, title, uri, mime, folder, tags, "
            "summary, shared_by, shared_at")
    where: list[str] = []
    args: list = []
    if q.strip():
        where.append("tsv @@ websearch_to_tsquery('simple', %s)")
        args.append(q)
    if agent_id:
        where.append("agent_id = %s")
        args.append(agent_id)
    if folder:
        where.append("folder = %s")
        args.append(folder)
    sql = f"SELECT {cols} FROM resource_index"
    if where:
        sql += " WHERE " + " AND ".join(where)
    if q.strip():
        sql += " ORDER BY ts_rank(tsv, websearch_to_tsquery('simple', %s)) DESC"
        args.append(q)
    else:
        sql += " ORDER BY id DESC"
    sql += " LIMIT %s"
    args.append(limit)
    with _db() as conn:
        return conn.execute(sql, args).fetchall()
