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

import psycopg
from fastapi import FastAPI, Header, HTTPException
from psycopg.rows import dict_row

DATABASE_URL = os.environ["DATABASE_URL"]
INGEST_TOKEN = os.environ.get("COLLECTOR_INGEST_TOKEN", "")

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


@app.post("/v1/traces")
def ingest(trace: dict, authorization: str = Header(default="")) -> dict:
    _check_auth(authorization)
    _ensure_schema()
    llm_calls = trace.get("llm_calls", []) or []
    it = sum(int(c.get("input_tokens", 0)) for c in llm_calls)
    ot = sum(int(c.get("output_tokens", 0)) for c in llm_calls)
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO agent_traces
              (run_id, agent_id, task_id, source, input_tokens, output_tokens,
               total_tokens, tool_calls, final_output, raw)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                trace.get("run_id"),
                trace.get("agent_id"),
                trace.get("task_id"),
                trace.get("source"),
                it,
                ot,
                it + ot,
                len(trace.get("tool_calls", []) or []),
                trace.get("final_output"),
                json.dumps(trace),
            ),
        )
        conn.commit()
    return {"ok": True, "total_tokens": it + ot}


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
                   sum(tool_calls)     AS tool_calls
            FROM agent_traces
            GROUP BY agent_id
            ORDER BY total_tokens DESC NULLS LAST
            """
        ).fetchall()
