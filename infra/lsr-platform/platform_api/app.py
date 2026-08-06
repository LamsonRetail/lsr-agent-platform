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
import json
import os
import re
import secrets

import psycopg
import requests
from fastapi import FastAPI, Header, HTTPException
from psycopg.rows import dict_row
from psycopg.types.json import Json

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
        # --- Test & Learn ---
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tests (
                test_id        text PRIMARY KEY,
                title          text,
                description    text,
                questions      jsonb,
                status         text DEFAULT 'draft',
                source         text DEFAULT 'manual',
                created_by     text,
                reviewed_by    text,
                pass_threshold real DEFAULT 0.8,
                created_at     timestamptz DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attempts (
                attempt_id  text PRIMARY KEY,
                test_id     text,
                taker_type  text,
                taker_id    text,
                score       real,
                passed      boolean,
                answers     jsonb,
                detail      jsonb,
                at          timestamptz DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_assignments (
                id          bigserial PRIMARY KEY,
                test_id     text,
                taker_id    text,
                taker_type  text,
                assigned_at timestamptz DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS training_materials (
                material_id text PRIMARY KEY,
                title       text,
                md_content  text,
                tags        text[],
                provided_by text DEFAULT 'HR',
                source_file text,
                created_at  timestamptz DEFAULT now()
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


# ======================= Test & Learn =======================

def _assert_answer(expected: str, actual: str, atype: str, tol: float = 0.0) -> bool:
    a = (actual or "").strip()
    e = (expected or "").strip()
    if atype == "exact":
        return a == e
    if atype == "regex":
        try:
            return re.search(expected or "", actual or "") is not None
        except re.error:
            return False
    if atype == "numeric_tolerance":
        try:
            return abs(float(actual) - float(expected)) <= tol
        except (TypeError, ValueError):
            return False
    # contains + semantic (fallback)
    return e.lower() in a.lower()


def _grade(questions: list[dict], answers: list[dict], threshold: float):
    by_id = {a.get("question_id"): a.get("response", "") for a in answers}
    total_w = sum(float(q.get("weight", 1.0)) for q in questions) or 1.0
    got = 0.0
    detail = []
    for q in questions:
        ok = _assert_answer(
            q.get("expected", ""), by_id.get(q.get("question_id"), ""),
            q.get("assertion_type", "contains"), float(q.get("tolerance", 0.0)),
        )
        if ok:
            got += float(q.get("weight", 1.0))
        detail.append({"question_id": q.get("question_id"), "ok": ok,
                       "skill_id": q.get("skill_id", "")})
    score = round(got / total_w, 4)
    return score, score >= threshold, detail


@app.post("/v1/tests")
def create_test(test: dict, authorization: str = Header(default="")) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    test_id = test.get("test_id")
    if not test_id:
        raise HTTPException(status_code=422, detail="test_id required")
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO tests (test_id, title, description, questions, status,
                               source, created_by, pass_threshold)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (test_id) DO UPDATE SET
              title=EXCLUDED.title, description=EXCLUDED.description,
              questions=EXCLUDED.questions, source=EXCLUDED.source,
              pass_threshold=EXCLUDED.pass_threshold
            """,
            (
                test_id, test.get("title"), test.get("description"),
                Json(test.get("questions") or []),
                test.get("status", "draft"), test.get("source", "manual"),
                test.get("created_by"), float(test.get("pass_threshold", 0.8)),
            ),
        )
        conn.commit()
    return {"test_id": test_id, "status": test.get("status", "draft")}


@app.post("/v1/tests/{test_id}/review")
def review_test(test_id: str, body: dict, authorization: str = Header(default="")) -> dict:
    """Người review DUYỆT → active (bắt buộc có reviewed_by)."""

    _require_admin(authorization)
    _ensure_schema()
    reviewer = body.get("reviewed_by")
    if not reviewer:
        raise HTTPException(status_code=422, detail="reviewed_by required")
    with _db() as conn:
        cur = conn.execute(
            "UPDATE tests SET status='active', reviewed_by=%s WHERE test_id=%s",
            (reviewer, test_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="not found")
    return {"test_id": test_id, "status": "active", "reviewed_by": reviewer}


@app.get("/v1/tests")
def list_tests() -> list[dict]:
    _ensure_schema()
    with _db() as conn:
        return conn.execute(
            "SELECT test_id, title, status, source, reviewed_by, pass_threshold, "
            "jsonb_array_length(coalesce(questions,'[]'::jsonb)) AS num_questions "
            "FROM tests ORDER BY created_at DESC"
        ).fetchall()


@app.get("/v1/tests/{test_id}")
def get_test(test_id: str) -> dict:
    _ensure_schema()
    with _db() as conn:
        row = conn.execute("SELECT * FROM tests WHERE test_id=%s", (test_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return row


@app.post("/v1/tests/generate")
def generate_test(body: dict, authorization: str = Header(default="")) -> dict:
    """Sinh bài test tự động (heuristic) từ tài liệu → DRAFT (auto), chờ review."""

    _require_admin(authorization)
    _ensure_schema()
    md = body.get("material_md") or ""
    if not md and body.get("material_id"):
        with _db() as conn:
            row = conn.execute(
                "SELECT md_content FROM training_materials WHERE material_id=%s",
                (body["material_id"],),
            ).fetchone()
            md = (row or {}).get("md_content") or ""
    skill = body.get("skill", "")
    n = int(body.get("n", 3))
    lines = [l.strip() for l in md.splitlines() if l.strip() and not l.strip().startswith("#")]

    def _sal(s: str) -> str:
        toks = re.findall(r"[0-9A-Za-zÀ-ỹ_]+", s)
        return max(toks, key=len) if toks else ""

    qs = []
    for i, l in enumerate(lines[:n]):
        key = _sal(l)
        if key:
            qs.append({"question_id": f"q{i + 1}", "prompt": "Nội dung: " + l,
                       "expected": key, "assertion_type": "contains",
                       "skill_id": skill, "tags": [skill] if skill else []})
    test_id = body.get("test_id") or ("TL-AUTO-" + secrets.token_hex(3))
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO tests (test_id, title, description, questions, status, source,
                               created_by, pass_threshold)
            VALUES (%s,%s,%s,%s,'draft','auto','llm-generator',%s)
            ON CONFLICT (test_id) DO NOTHING
            """,
            (test_id, body.get("title") or "Bài test tự động", "", Json(qs),
             float(body.get("pass_threshold", 0.8))),
        )
        conn.commit()
    return {"test_id": test_id, "status": "draft", "source": "auto", "num_questions": len(qs)}


@app.post("/v1/tests/{test_id}/assign")
def assign_test(test_id: str, body: dict, authorization: str = Header(default="")) -> dict:
    """Giao bài test cho danh sách agent/người (chỉ khi test đã active)."""

    _require_admin(authorization)
    _ensure_schema()
    assignees = body.get("assignees") or []
    with _db() as conn:
        t = conn.execute("SELECT status FROM tests WHERE test_id=%s", (test_id,)).fetchone()
        if not t:
            raise HTTPException(status_code=404, detail="test not found")
        if t["status"] != "active":
            raise HTTPException(status_code=409, detail="test chưa active, chưa giao được")
        for a in assignees:
            conn.execute(
                "INSERT INTO test_assignments (test_id, taker_id, taker_type) VALUES (%s,%s,%s)",
                (test_id, a.get("taker_id"), a.get("taker_type", "agent")),
            )
        conn.commit()
    return {"test_id": test_id, "assigned": len(assignees)}


@app.get("/v1/tests/{test_id}/assignments")
def list_assignments(test_id: str) -> list[dict]:
    _ensure_schema()
    with _db() as conn:
        return conn.execute(
            "SELECT taker_id, taker_type, assigned_at FROM test_assignments "
            "WHERE test_id=%s ORDER BY assigned_at DESC",
            (test_id,),
        ).fetchall()


@app.post("/v1/attempts")
def submit_attempt(body: dict, authorization: str = Header(default="")) -> dict:
    """Làm bài — dùng chung cho AGENT và NGƯỜI (taker_type)."""

    _ensure_schema()
    test_id = body.get("test_id")
    taker_type = body.get("taker_type", "human")
    taker_id = body.get("taker_id", "")
    answers = body.get("answers") or []
    with _db() as conn:
        test = conn.execute(
            "SELECT questions, status, pass_threshold FROM tests WHERE test_id=%s",
            (test_id,),
        ).fetchone()
        if not test:
            raise HTTPException(status_code=404, detail="test not found")
        if test["status"] != "active":
            raise HTTPException(status_code=409, detail="test chưa active (chưa review xong)")
        questions = test["questions"] or []
        score, passed, detail = _grade(questions, answers, float(test["pass_threshold"]))
        attempt_id = "at_" + secrets.token_hex(8)
        conn.execute(
            """
            INSERT INTO attempts (attempt_id, test_id, taker_type, taker_id,
                                  score, passed, answers, detail)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (attempt_id, test_id, taker_type, taker_id, score, passed,
             Json(answers), Json(detail)),
        )
        conn.commit()

        training: list = []
        if not passed:
            topics = set()
            for q in questions:
                topics.update(q.get("tags") or [])
                if q.get("skill_id"):
                    topics.add(q["skill_id"])
            if topics:
                training = conn.execute(
                    "SELECT material_id, title, tags FROM training_materials "
                    "WHERE tags && %s::text[]",
                    (list(topics),),
                ).fetchall()
            else:
                training = conn.execute(
                    "SELECT material_id, title, tags FROM training_materials LIMIT 10"
                ).fetchall()

    return {
        "attempt_id": attempt_id, "test_id": test_id, "taker_type": taker_type,
        "taker_id": taker_id, "score": score, "passed": passed, "detail": detail,
        "needs_training": (not passed), "training": training,
    }


@app.get("/v1/attempts")
def list_attempts(taker_id: str | None = None, test_id: str | None = None) -> list[dict]:
    _ensure_schema()
    where, args = [], []
    if taker_id:
        where.append("taker_id=%s"); args.append(taker_id)
    if test_id:
        where.append("test_id=%s"); args.append(test_id)
    sql = "SELECT attempt_id, test_id, taker_type, taker_id, score, passed, at FROM attempts"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY at DESC LIMIT 50"
    with _db() as conn:
        return conn.execute(sql, args).fetchall()


@app.post("/v1/training")
def add_training(m: dict, authorization: str = Header(default="")) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    mid = m.get("material_id")
    if not mid:
        raise HTTPException(status_code=422, detail="material_id required")
    tags = m.get("tags") or []
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO training_materials (material_id, title, md_content, tags,
                                            provided_by, source_file)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (material_id) DO UPDATE SET
              title=EXCLUDED.title, md_content=EXCLUDED.md_content, tags=EXCLUDED.tags
            """,
            (mid, m.get("title"), m.get("md_content"), tags,
             m.get("provided_by", "HR"), m.get("source_file")),
        )
        conn.commit()
    return {"material_id": mid, "ok": True}


@app.get("/v1/training")
def list_training() -> list[dict]:
    _ensure_schema()
    with _db() as conn:
        return conn.execute(
            "SELECT material_id, title, tags, provided_by, source_file, created_at "
            "FROM training_materials ORDER BY created_at DESC"
        ).fetchall()
