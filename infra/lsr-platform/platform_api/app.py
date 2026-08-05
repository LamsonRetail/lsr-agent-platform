"""LSR Platform API — registry agent + cấp telemetry key + hook Minh Anh.

Endpoints:
  GET  /health
  POST /v1/agents/register        [admin]  đăng ký agent, cấp telemetry key,
                                            và kích hoạt Minh Anh share từ điển
                                            meeting-notes cho agent mới.
  GET  /v1/agents                          liệt kê agent (không lộ key)
  GET  /v1/agents/{id}
  POST /v1/agents/{id}/status     [admin]  active | deactivated (kill switch)

Auth admin: header Authorization: Bearer <PLATFORM_ADMIN_TOKEN>.
"""

from __future__ import annotations

import hashlib
import os
import secrets

import psycopg
import requests
from fastapi import FastAPI, Header, HTTPException
from psycopg.rows import dict_row

DATABASE_URL = os.environ["DATABASE_URL"]
COLLECTOR_URL = os.environ.get("COLLECTOR_URL", "http://collector:8081").rstrip("/")
COLLECTOR_INGEST_TOKEN = os.environ.get("COLLECTOR_INGEST_TOKEN", "")
ADMIN_TOKEN = os.environ.get("PLATFORM_ADMIN_TOKEN", "")

app = FastAPI(title="LSR Platform API", version="0.1.0")
_READY = False


def _db() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def _ensure_schema() -> None:
    global _READY
    if _READY:
        return
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agents (
                agent_id           text PRIMARY KEY,
                name               text,
                owner              text,
                squad              text,
                connect_mode       text,
                is_squad_agent     boolean DEFAULT false,
                skills             text[],
                status             text DEFAULT 'registered',
                telemetry_key_hash text,
                registered_at      timestamptz DEFAULT now(),
                golive_at          timestamptz
            )
            """
        )
        conn.commit()
    _READY = True


@app.on_event("startup")
def _startup() -> None:
    try:
        _ensure_schema()
    except Exception:
        pass


def _require_admin(authorization: str) -> None:
    if not ADMIN_TOKEN or authorization != f"Bearer {ADMIN_TOKEN}":
        raise HTTPException(status_code=401, detail="admin token required")


def _dictionary_resource(agent_id: str) -> dict:
    """Mục 'từ điển' meeting-notes Minh Anh share cho agent mới (khớp meeting.minh_anh)."""

    return {
        "resource_id": f"dict-meeting-notes::{agent_id}",
        "agent_id": agent_id,
        "kind": "folder",
        "title": "Meeting Notes Dictionary",
        "uri": "lark://drive/folder/meeting-notes",
        "folder": "meeting-notes",
        "tags": ["meeting-notes", "dictionary", "index"],
        "summary": (
            "Danh mục/thư mục biên bản họp do Minh Anh quản lý. Tra cứu biên bản cũ, "
            "quyết định và task của các cuộc họp tại đây (qua resource index)."
        ),
        "shared_by": "Minh Anh",
    }


def _minh_anh_share(agent_id: str) -> bool:
    """Hook on_agent_registered: Minh Anh share từ điển meeting-notes cho agent mới."""

    try:
        resp = requests.post(
            f"{COLLECTOR_URL}/v1/resources",
            json=_dictionary_resource(agent_id),
            headers={"Authorization": f"Bearer {COLLECTOR_INGEST_TOKEN}"},
            timeout=8,
        )
        return resp.status_code < 300
    except Exception:
        return False


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/v1/agents/register")
def register(agent: dict, authorization: str = Header(default="")) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    agent_id = agent.get("agent_id")
    if not agent_id:
        raise HTTPException(status_code=422, detail="agent_id required")
    skills = agent.get("skills") or []
    if not isinstance(skills, list):
        skills = [str(skills)]
    telemetry_key = "lsr_tel_" + secrets.token_hex(20)
    key_hash = hashlib.sha256(telemetry_key.encode()).hexdigest()
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO agents (agent_id, name, owner, squad, connect_mode,
                                is_squad_agent, skills, status, telemetry_key_hash)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'registered',%s)
            ON CONFLICT (agent_id) DO UPDATE SET
                name=EXCLUDED.name, owner=EXCLUDED.owner, squad=EXCLUDED.squad,
                connect_mode=EXCLUDED.connect_mode, is_squad_agent=EXCLUDED.is_squad_agent,
                skills=EXCLUDED.skills, telemetry_key_hash=EXCLUDED.telemetry_key_hash
            """,
            (
                agent_id, agent.get("name"), agent.get("owner"), agent.get("squad"),
                agent.get("connect_mode", "bot"), bool(agent.get("is_squad_agent", False)),
                skills, key_hash,
            ),
        )
        conn.commit()
    dictionary_shared = _minh_anh_share(agent_id)
    return {
        "agent_id": agent_id,
        "status": "registered",
        "telemetry_key": telemetry_key,  # hiện MỘT LẦN
        "dictionary_shared": dictionary_shared,
    }


@app.get("/v1/agents")
def list_agents() -> list[dict]:
    _ensure_schema()
    with _db() as conn:
        return conn.execute(
            "SELECT agent_id, name, owner, squad, connect_mode, is_squad_agent, "
            "skills, status, registered_at, golive_at FROM agents ORDER BY registered_at DESC"
        ).fetchall()


@app.get("/v1/agents/{agent_id}")
def get_agent(agent_id: str) -> dict:
    _ensure_schema()
    with _db() as conn:
        row = conn.execute(
            "SELECT agent_id, name, owner, squad, connect_mode, is_squad_agent, "
            "skills, status, registered_at, golive_at FROM agents WHERE agent_id=%s",
            (agent_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return row


@app.post("/v1/agents/{agent_id}/status")
def set_status(agent_id: str, body: dict, authorization: str = Header(default="")) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    status = body.get("status")
    if status not in ("registered", "testing", "active", "deactivated"):
        raise HTTPException(status_code=422, detail="invalid status")
    golive = "now()" if status == "active" else "golive_at"
    with _db() as conn:
        cur = conn.execute(
            f"UPDATE agents SET status=%s, golive_at={golive} WHERE agent_id=%s",
            (status, agent_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="not found")
    return {"agent_id": agent_id, "status": status}
