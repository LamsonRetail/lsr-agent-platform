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
        # Agent external (chạy ở dự án/hạ tầng khác) — thêm cột nếu DB cũ.
        for ddl in (
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS deployment text DEFAULT 'managed'",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS repo_url text",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS host_note text",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS backup_owner text",
        ):
            conn.execute(ddl)
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
        # --- Second brain của team (BẢNG CHUNG, tránh rải rác) ---
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS teams (
                team_id    text PRIMARY KEY,
                kind       text DEFAULT 'squad',   -- squad | chapter | team
                name       text,
                objective  text,
                lead       text,
                lark_chats text[],
                created_at timestamptz DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS team_members (
                id            bigserial PRIMARY KEY,
                team_id       text,
                full_name     text,
                lark_user_id  text,
                role          text,
                expertise     text,
                backup_for    text,
                working_hours text,
                UNIQUE (team_id, full_name)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS team_kpis (
                id          bigserial PRIMARY KEY,
                team_id     text,
                kpi_name    text,
                unit        text,
                formula     text,
                data_source text,
                target      double precision,
                period      text,
                weight      double precision DEFAULT 1,
                UNIQUE (team_id, kpi_name, period)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS team_context (
                id         bigserial PRIMARY KEY,
                team_id    text,
                title      text,
                md_content text,
                tags       text[],
                created_by text,
                created_at timestamptz DEFAULT now()
            )
            """
        )
        # --- LSR Brain: shared brain + consolidate knowledge có governance ---
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shared_beliefs (
                belief_id  text PRIMARY KEY,
                title      text,
                statement  text,          -- niềm tin/nguyên tắc chung của LSR
                domain     text,
                source     text,          -- admin | extracted:<file>
                version    int DEFAULT 1,
                updated_by text,          -- CHỈ admin
                updated_at timestamptz DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_reviewers (
                id       bigserial PRIMARY KEY,
                email    text,
                domain   text,            -- chuyên môn được phê duyệt
                added_by text,
                added_at timestamptz DEFAULT now(),
                UNIQUE (email, domain)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_domains (
                domain     text PRIMARY KEY,
                label      text,
                keywords   text[],          -- tag/keywords để nhận diện chuyên môn
                created_at timestamptz DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_items (
                item_id      text PRIMARY KEY,
                title        text,
                md_content   text,
                domain       text,
                source_team  text,        -- second brain của team nào
                source_ref   text,
                status       text DEFAULT 'pending',  -- pending|approved|rejected
                reviewed_by  text,
                review_note  text,
                reviewed_at  timestamptz,
                created_at   timestamptz DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_conflicts (
                conflict_id  text PRIMARY KEY,
                agent_id     text,
                team_id      text,
                belief_id    text,
                agent_claim  text,        -- nội dung trong agent/team brain
                shared_claim text,        -- nội dung trong shared brain
                status       text DEFAULT 'open',   -- open|resolved_keep_shared|resolved_update_shared|dismissed
                owner_email  text,        -- agent owner phải confirm
                resolution   text,
                created_at   timestamptz DEFAULT now(),
                resolved_at  timestamptz
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id         bigserial PRIMARY KEY,
                to_email   text,
                kind       text,          -- new_knowledge | conflict | belief_suggestion
                ref_id     text,
                message    text,
                read       boolean DEFAULT false,
                created_at timestamptz DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_golive_checklist (
                agent_id     text PRIMARY KEY,
                payload      jsonb,
                submitted_by text,
                submitted_at timestamptz DEFAULT now()
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


def agent_schema(agent_id: str) -> str:
    """Tên schema (dataset) riêng của agent trên Supabase chung."""

    clean = re.sub(r"[^a-zA-Z0-9]+", "_", agent_id).strip("_").lower()
    return f"agent_{clean or 'x'}"


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
                                is_squad_agent, skills, status, telemetry_key_hash,
                                deployment, repo_url, host_note, backup_owner)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'registered',%s,%s,%s,%s,%s)
            ON CONFLICT (agent_id) DO UPDATE SET
                name=EXCLUDED.name, owner=EXCLUDED.owner, squad=EXCLUDED.squad,
                connect_mode=EXCLUDED.connect_mode, is_squad_agent=EXCLUDED.is_squad_agent,
                skills=EXCLUDED.skills, telemetry_key_hash=EXCLUDED.telemetry_key_hash,
                deployment=EXCLUDED.deployment, repo_url=EXCLUDED.repo_url,
                host_note=EXCLUDED.host_note, backup_owner=EXCLUDED.backup_owner
            """,
            (
                agent_id, agent.get("name"), agent.get("owner"), agent.get("squad"),
                agent.get("connect_mode", "bot"), bool(agent.get("is_squad_agent", False)),
                skills, key_hash,
                agent.get("deployment", "managed"), agent.get("repo_url"),
                agent.get("host_note"), agent.get("backup_owner"),
            ),
        )
        # Dataset riêng cho agent trên Supabase chung: mỗi agent 1 schema Postgres.
        schema = agent_schema(agent_id)
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        conn.commit()
    dictionary_shared = _minh_anh_share(agent_id)
    return {
        "agent_id": agent_id,
        "status": "registered",
        "telemetry_key": telemetry_key,  # hiện MỘT LẦN
        "dictionary_shared": dictionary_shared,
        "db_schema": schema,
        "deployment": agent.get("deployment", "managed"),
    }


@app.get("/v1/agents")
def list_agents() -> list[dict]:
    _ensure_schema()
    with _db() as conn:
        return conn.execute(
            "SELECT agent_id, name, owner, squad, connect_mode, is_squad_agent, "
            "skills, status, deployment, repo_url, host_note, registered_at, golive_at "
            "FROM agents ORDER BY registered_at DESC"
        ).fetchall()


@app.get("/v1/agents/{agent_id}")
def get_agent(agent_id: str) -> dict:
    _ensure_schema()
    with _db() as conn:
        row = conn.execute(
            "SELECT agent_id, name, owner, squad, connect_mode, is_squad_agent, "
            "skills, status, deployment, repo_url, host_note, registered_at, golive_at "
            "FROM agents WHERE agent_id=%s",
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
    # GATE: chỉ cho golive khi checklist đủ mục bắt buộc (bỏ qua nếu force=true).
    if status == "active" and not body.get("force"):
        with _db() as conn:
            row = conn.execute(
                "SELECT payload FROM agent_golive_checklist WHERE agent_id=%s", (agent_id,)
            ).fetchone()
        miss = missing_checklist((row or {}).get("payload") or {})
        if miss:
            raise HTTPException(
                status_code=409,
                detail={"error": "golive checklist chưa đủ", "missing": miss,
                        "hint": "POST /v1/agents/{id}/golive-checklist"},
            )
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


# ======================= Second brain của team =======================

@app.post("/v1/teams")
def upsert_team(t: dict, authorization: str = Header(default="")) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    tid = t.get("team_id")
    if not tid:
        raise HTTPException(status_code=422, detail="team_id required")
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO teams (team_id, kind, name, objective, lead, lark_chats)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (team_id) DO UPDATE SET kind=EXCLUDED.kind, name=EXCLUDED.name,
              objective=EXCLUDED.objective, lead=EXCLUDED.lead, lark_chats=EXCLUDED.lark_chats
            """,
            (tid, t.get("kind", "squad"), t.get("name"), t.get("objective"),
             t.get("lead"), t.get("lark_chats") or []),
        )
        conn.commit()
    return {"team_id": tid, "ok": True}


@app.get("/v1/teams")
def list_teams() -> list[dict]:
    _ensure_schema()
    with _db() as conn:
        return conn.execute("SELECT * FROM teams ORDER BY team_id").fetchall()


@app.post("/v1/teams/{team_id}/members")
def add_members(team_id: str, body: dict, authorization: str = Header(default="")) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    members = body.get("members") or []
    with _db() as conn:
        for m in members:
            conn.execute(
                """
                INSERT INTO team_members (team_id, full_name, lark_user_id, role,
                                          expertise, backup_for, working_hours)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (team_id, full_name) DO UPDATE SET
                  lark_user_id=EXCLUDED.lark_user_id, role=EXCLUDED.role,
                  expertise=EXCLUDED.expertise, backup_for=EXCLUDED.backup_for,
                  working_hours=EXCLUDED.working_hours
                """,
                (team_id, m.get("full_name"), m.get("lark_user_id"), m.get("role"),
                 m.get("expertise"), m.get("backup_for"), m.get("working_hours")),
            )
        conn.commit()
    return {"team_id": team_id, "members": len(members)}


@app.post("/v1/teams/{team_id}/kpis")
def add_kpis(team_id: str, body: dict, authorization: str = Header(default="")) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    kpis = body.get("kpis") or []
    with _db() as conn:
        for k in kpis:
            conn.execute(
                """
                INSERT INTO team_kpis (team_id, kpi_name, unit, formula, data_source,
                                       target, period, weight)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (team_id, kpi_name, period) DO UPDATE SET
                  unit=EXCLUDED.unit, formula=EXCLUDED.formula,
                  data_source=EXCLUDED.data_source, target=EXCLUDED.target,
                  weight=EXCLUDED.weight
                """,
                (team_id, k.get("kpi_name"), k.get("unit"), k.get("formula"),
                 k.get("data_source"), k.get("target"), k.get("period"),
                 k.get("weight", 1)),
            )
        conn.commit()
    return {"team_id": team_id, "kpis": len(kpis)}


@app.post("/v1/teams/{team_id}/context")
def add_context(team_id: str, body: dict, authorization: str = Header(default="")) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        conn.execute(
            "INSERT INTO team_context (team_id, title, md_content, tags, created_by) "
            "VALUES (%s,%s,%s,%s,%s)",
            (team_id, body.get("title"), body.get("md_content"),
             body.get("tags") or [], body.get("created_by")),
        )
        conn.commit()
    return {"team_id": team_id, "ok": True}


@app.get("/v1/teams/{team_id}/brain")
def team_brain(team_id: str) -> dict:
    """Second brain của team — agent tra cứu khi cần (không nhồi vào memory)."""

    _ensure_schema()
    with _db() as conn:
        team = conn.execute("SELECT * FROM teams WHERE team_id=%s", (team_id,)).fetchone()
        if not team:
            raise HTTPException(status_code=404, detail="team not found")
        members = conn.execute(
            "SELECT full_name, lark_user_id, role, expertise, backup_for, working_hours "
            "FROM team_members WHERE team_id=%s ORDER BY full_name", (team_id,)).fetchall()
        kpis = conn.execute(
            "SELECT kpi_name, unit, formula, data_source, target, period, weight "
            "FROM team_kpis WHERE team_id=%s ORDER BY kpi_name", (team_id,)).fetchall()
        ctx = conn.execute(
            "SELECT title, md_content, tags, created_at FROM team_context "
            "WHERE team_id=%s ORDER BY created_at DESC LIMIT 50", (team_id,)).fetchall()
    return {"team": team, "members": members, "kpis": kpis, "context": ctx}


# ======================= LSR Brain: shared brain + consolidate =======================

def _notify(conn, to_email: str, kind: str, ref_id: str, message: str) -> None:
    if not to_email:
        return
    conn.execute(
        "INSERT INTO notifications (to_email, kind, ref_id, message) VALUES (%s,%s,%s,%s)",
        (to_email, kind, ref_id, message),
    )


def _reviewers_for(conn, domain: str) -> list[str]:
    rows = conn.execute(
        "SELECT email FROM knowledge_reviewers WHERE domain=%s OR domain='*'", (domain or "",)
    ).fetchall()
    return [r["email"] for r in rows]


# --- Shared beliefs: CHỈ admin được sửa ---

@app.get("/v1/shared-brain")
def shared_brain(domain: str | None = None) -> dict:
    """MỌI agent đều truy xuất được (mặc định). Không cần admin token."""

    _ensure_schema()
    sql = "SELECT belief_id, title, statement, domain, version, updated_at FROM shared_beliefs"
    args: list = []
    if domain:
        sql += " WHERE domain=%s"
        args.append(domain)
    sql += " ORDER BY domain, belief_id"
    with _db() as conn:
        beliefs = conn.execute(sql, args).fetchall()
        knowledge = conn.execute(
            "SELECT item_id, title, md_content, domain, source_team, reviewed_by, reviewed_at "
            "FROM knowledge_items WHERE status='approved' ORDER BY reviewed_at DESC LIMIT 200"
        ).fetchall()
    return {"beliefs": beliefs, "knowledge": knowledge}


@app.post("/v1/shared-beliefs")
def upsert_belief(b: dict, authorization: str = Header(default="")) -> dict:
    """CHỈ admin: tạo/sửa niềm tin chung của LSR (có version)."""

    _require_admin(authorization)
    _ensure_schema()
    bid = b.get("belief_id")
    if not bid or not b.get("statement"):
        raise HTTPException(status_code=422, detail="belief_id và statement là bắt buộc")
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO shared_beliefs (belief_id, title, statement, domain, source, updated_by)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (belief_id) DO UPDATE SET title=EXCLUDED.title,
              statement=EXCLUDED.statement, domain=EXCLUDED.domain,
              version=shared_beliefs.version+1, updated_by=EXCLUDED.updated_by,
              updated_at=now()
            """,
            (bid, b.get("title"), b.get("statement"), b.get("domain"),
             b.get("source", "admin"), b.get("updated_by", "admin")),
        )
        conn.commit()
    return {"belief_id": bid, "ok": True}


@app.post("/v1/shared-beliefs/suggest")
def suggest_beliefs(body: dict, authorization: str = Header(default="")) -> dict:
    """Admin upload nội dung file (pdf/word đã trích text) → gợi ý append shared beliefs.

    Trả về danh sách đề xuất (KHÔNG tự ghi) — admin duyệt rồi mới POST /v1/shared-beliefs.
    """

    _require_admin(authorization)
    _ensure_schema()
    text = body.get("text") or ""
    domain = body.get("domain", "")
    filename = body.get("filename", "upload")
    # Tách câu/đoạn có tính "nguyên tắc" (heuristic; LLM judge ở giai đoạn sau).
    # So khớp KHÔNG phân biệt dấu để hoạt động với cả text có dấu lẫn không dấu.
    import unicodedata

    def _strip(s: str) -> str:
        return "".join(
            c for c in unicodedata.normalize("NFD", s.lower())
            if unicodedata.category(c) != "Mn"
        )

    KEYS = tuple(_strip(k) for k in (
        "luôn", "không được", "phải", "nguyên tắc", "cam kết", "ưu tiên",
        "chúng tôi tin", "giá trị", "tuyệt đối", "không chia sẻ"))
    seen, out = set(), []
    for raw in re.split(r"[\n\.;]+", text):
        s = raw.strip()
        if len(s) < 15 or len(s) > 300:
            continue
        low = _strip(s)
        if any(k in low for k in KEYS) and low not in seen:
            seen.add(low)
            out.append({
                "belief_id": f"b_{abs(hash(low)) % 10**8}",
                "title": s[:60],
                "statement": s,
                "domain": domain,
                "source": f"extracted:{filename}",
            })
        if len(out) >= 30:
            break
    return {"filename": filename, "suggestions": out, "count": len(out)}


# --- Reviewer: admin cấp quyền theo chuyên môn ---

@app.post("/v1/knowledge/reviewers")
def add_reviewer(body: dict, authorization: str = Header(default="")) -> dict:
    """CHỈ admin: cấp quyền cho nhân sự được phê duyệt một nhóm nội dung (domain)."""

    _require_admin(authorization)
    _ensure_schema()
    email, domain = body.get("email"), body.get("domain")
    if not email or not domain:
        raise HTTPException(status_code=422, detail="email và domain là bắt buộc")
    with _db() as conn:
        conn.execute(
            "INSERT INTO knowledge_reviewers (email, domain, added_by) VALUES (%s,%s,%s) "
            "ON CONFLICT (email, domain) DO NOTHING",
            (email, domain, body.get("added_by", "admin")),
        )
        conn.commit()
    return {"email": email, "domain": domain, "ok": True}


@app.post("/v1/knowledge/domains")
def upsert_domain(body: dict, authorization: str = Header(default="")) -> dict:
    """CHỈ admin: định nghĩa chuyên môn + tag/keywords (để chọn & auto-route)."""

    _require_admin(authorization)
    _ensure_schema()
    d = body.get("domain")
    if not d:
        raise HTTPException(status_code=422, detail="domain required")
    kws = body.get("keywords") or []
    if isinstance(kws, str):
        kws = [k.strip() for k in kws.split(",") if k.strip()]
    with _db() as conn:
        conn.execute(
            "INSERT INTO knowledge_domains (domain, label, keywords) VALUES (%s,%s,%s) "
            "ON CONFLICT (domain) DO UPDATE SET label=EXCLUDED.label, keywords=EXCLUDED.keywords",
            (d, body.get("label") or d, kws),
        )
        conn.commit()
    return {"domain": d, "keywords": kws, "ok": True}


@app.get("/v1/knowledge/domains")
def list_domains() -> list[dict]:
    _ensure_schema()
    with _db() as conn:
        return conn.execute(
            "SELECT domain, label, keywords FROM knowledge_domains ORDER BY domain"
        ).fetchall()


@app.post("/v1/knowledge/domains/{domain}/delete")
def delete_domain(domain: str, authorization: str = Header(default="")) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        conn.execute("DELETE FROM knowledge_domains WHERE domain=%s", (domain,))
        conn.commit()
    return {"domain": domain, "deleted": True}


@app.post("/v1/knowledge/reviewers/remove")
def remove_reviewer(body: dict, authorization: str = Header(default="")) -> dict:
    """CHỈ admin: gỡ quyền phê duyệt của một người khỏi một chuyên môn."""

    _require_admin(authorization)
    _ensure_schema()
    email, domain = body.get("email"), body.get("domain")
    if not email or not domain:
        raise HTTPException(status_code=422, detail="email và domain là bắt buộc")
    with _db() as conn:
        cur = conn.execute(
            "DELETE FROM knowledge_reviewers WHERE email=%s AND domain=%s", (email, domain))
        conn.commit()
    return {"email": email, "domain": domain, "removed": cur.rowcount}


@app.post("/v1/shared-beliefs/{belief_id}/delete")
def delete_belief(belief_id: str, authorization: str = Header(default="")) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        conn.execute("DELETE FROM shared_beliefs WHERE belief_id=%s", (belief_id,))
        conn.commit()
    return {"belief_id": belief_id, "deleted": True}


@app.get("/v1/knowledge/reviewers")
def list_reviewers() -> list[dict]:
    _ensure_schema()
    with _db() as conn:
        return conn.execute(
            "SELECT email, domain, added_by, added_at FROM knowledge_reviewers ORDER BY domain, email"
        ).fetchall()


# --- Knowledge candidates: LSR Brain đẩy lên, reviewer duyệt ---

@app.post("/v1/knowledge/items")
def submit_knowledge(body: dict, authorization: str = Header(default="")) -> dict:
    """LSR Brain nộp kiến thức tổng hợp từ second brain các team → chờ review + notify."""

    _require_admin(authorization)
    _ensure_schema()
    items = body.get("items") or [body]
    created, notified = [], 0
    with _db() as conn:
        for it in items:
            iid = it.get("item_id") or ("k_" + secrets.token_hex(6))
            conn.execute(
                """
                INSERT INTO knowledge_items (item_id, title, md_content, domain,
                                             source_team, source_ref)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (item_id) DO NOTHING
                """,
                (iid, it.get("title"), it.get("md_content"), it.get("domain"),
                 it.get("source_team"), it.get("source_ref")),
            )
            created.append(iid)
            for email in _reviewers_for(conn, it.get("domain")):
                _notify(conn, email, "new_knowledge", iid,
                        f"Kiến thức mới cần duyệt: {it.get('title')} (domain {it.get('domain')})")
                notified += 1
        conn.commit()
    return {"created": created, "notified": notified}


@app.get("/v1/knowledge/items")
def list_knowledge(status: str = "pending", domain: str | None = None) -> list[dict]:
    _ensure_schema()
    sql = ("SELECT item_id, title, domain, source_team, status, reviewed_by, reviewed_at "
           "FROM knowledge_items WHERE status=%s")
    args: list = [status]
    if domain:
        sql += " AND domain=%s"
        args.append(domain)
    sql += " ORDER BY created_at DESC LIMIT 200"
    with _db() as conn:
        return conn.execute(sql, args).fetchall()


@app.post("/v1/knowledge/items/{item_id}/review")
def review_knowledge(item_id: str, body: dict) -> dict:
    """Nhân sự phụ trách chuyên môn confirm/reject. Kiểm quyền theo domain.

    Ghi lại AI confirm cái gì (reviewed_by + thời điểm) — bộ nhớ phê duyệt.
    """

    _ensure_schema()
    reviewer = body.get("reviewer_email")
    decision = body.get("decision")  # approved | rejected
    if not reviewer or decision not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="cần reviewer_email và decision approved|rejected")
    with _db() as conn:
        item = conn.execute("SELECT domain, status FROM knowledge_items WHERE item_id=%s",
                            (item_id,)).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="không tìm thấy item")
        allowed = conn.execute(
            "SELECT 1 FROM knowledge_reviewers WHERE email=%s AND (domain=%s OR domain='*')",
            (reviewer, item["domain"] or ""),
        ).fetchone()
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail=f"{reviewer} không có quyền duyệt domain '{item['domain']}'")
        conn.execute(
            "UPDATE knowledge_items SET status=%s, reviewed_by=%s, review_note=%s, "
            "reviewed_at=now() WHERE item_id=%s",
            (decision, reviewer, body.get("note"), item_id),
        )
        conn.commit()
    return {"item_id": item_id, "status": decision, "reviewed_by": reviewer}


# --- Conflict: shared brain vs agent/team brain ---

@app.post("/v1/knowledge/conflicts")
def raise_conflict(body: dict, authorization: str = Header(default="")) -> dict:
    """LSR Brain phát hiện sai lệch → tạo request cho AGENT OWNER confirm."""

    _require_admin(authorization)
    _ensure_schema()
    cid = body.get("conflict_id") or ("c_" + secrets.token_hex(6))
    owner = body.get("owner_email")
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO knowledge_conflicts (conflict_id, agent_id, team_id, belief_id,
                                             agent_claim, shared_claim, owner_email)
            VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (conflict_id) DO NOTHING
            """,
            (cid, body.get("agent_id"), body.get("team_id"), body.get("belief_id"),
             body.get("agent_claim"), body.get("shared_claim"), owner),
        )
        _notify(conn, owner, "conflict", cid,
                f"Sai lệch giữa shared brain và brain của {body.get('agent_id')} — cần xác nhận")
        conn.commit()
    return {"conflict_id": cid, "status": "open", "notified": bool(owner)}


@app.get("/v1/knowledge/conflicts")
def list_conflicts(status: str = "open", agent_id: str | None = None,
                   owner_email: str | None = None) -> list[dict]:
    """Lọc theo agent_id/owner — conflict hiển thị ở BACKEND CỦA TỪNG AGENT."""

    _ensure_schema()
    sql = "SELECT * FROM knowledge_conflicts WHERE status=%s"
    args: list = [status]
    if agent_id:
        sql += " AND agent_id=%s"; args.append(agent_id)
    if owner_email:
        sql += " AND owner_email=%s"; args.append(owner_email)
    sql += " ORDER BY created_at DESC LIMIT 100"
    with _db() as conn:
        return conn.execute(sql, args).fetchall()


@app.post("/v1/knowledge/conflicts/{conflict_id}/resolve")
def resolve_conflict(conflict_id: str, body: dict) -> dict:
    """Agent owner xác nhận: giữ shared, cập nhật shared, hoặc bỏ qua."""

    _ensure_schema()
    decision = body.get("decision")
    valid = ("resolved_keep_shared", "resolved_update_shared", "dismissed")
    if decision not in valid:
        raise HTTPException(status_code=422, detail=f"decision phải thuộc {valid}")
    with _db() as conn:
        c = conn.execute("SELECT * FROM knowledge_conflicts WHERE conflict_id=%s",
                         (conflict_id,)).fetchone()
        if not c:
            raise HTTPException(status_code=404, detail="không tìm thấy conflict")
        if body.get("owner_email") and c["owner_email"] and body["owner_email"] != c["owner_email"]:
            raise HTTPException(status_code=403, detail="chỉ agent owner được xác nhận")
        conn.execute(
            "UPDATE knowledge_conflicts SET status=%s, resolution=%s, resolved_at=now() "
            "WHERE conflict_id=%s",
            (decision, body.get("resolution"), conflict_id),
        )
        # Nếu chọn cập nhật shared → tạo knowledge item chờ reviewer duyệt (không tự ghi belief).
        if decision == "resolved_update_shared":
            iid = "k_" + secrets.token_hex(6)
            conn.execute(
                "INSERT INTO knowledge_items (item_id, title, md_content, domain, "
                "source_team, source_ref) VALUES (%s,%s,%s,%s,%s,%s)",
                (iid, f"Cập nhật từ conflict {conflict_id}", c["agent_claim"],
                 body.get("domain"), c["team_id"], conflict_id),
            )
            for email in _reviewers_for(conn, body.get("domain")):
                _notify(conn, email, "new_knowledge", iid,
                        f"Đề xuất cập nhật shared brain từ conflict {conflict_id}")
        conn.commit()
    return {"conflict_id": conflict_id, "status": decision}


@app.get("/v1/notifications")
def list_notifications(to_email: str, unread_only: bool = True) -> list[dict]:
    _ensure_schema()
    sql = "SELECT id, kind, ref_id, message, read, created_at FROM notifications WHERE to_email=%s"
    args: list = [to_email]
    if unread_only:
        sql += " AND read=false"
    sql += " ORDER BY created_at DESC LIMIT 100"
    with _db() as conn:
        return conn.execute(sql, args).fetchall()


# ======================= Checklist golive =======================

# Mục BẮT BUỘC (xem GOLIVE_CHECKLIST.md) — thiếu thì không cho golive.
REQUIRED_CHECKLIST = [
    # A. Định danh & sở hữu
    "owner_email", "backup_owner", "team_id",
    # B. Con người & phối hợp
    "team_members", "approver", "collaboration_rules", "work_channels",
    # C. Mục tiêu & KPI
    "kpis", "agent_kpi", "alert_thresholds",
    # D. Phạm vi & dữ liệu
    "data_sources_allowed", "data_forbidden", "skills", "writes",
    # E. Kết nối & xác thực
    "auth_mode", "lark_connect", "telemetry_verified", "deployment",
    # F. Chất lượng & an toàn
    "tests_passed", "escalation_rules", "risks", "reviewer_first_week",
    # G. Vận hành sau golive
    "schedule", "retrain_process", "feedback_channel", "review_cadence",
    # H. Tuân thủ
    "team_notified", "scope_confirmed",
]


def missing_checklist(payload: dict) -> list[str]:
    miss = []
    for k in REQUIRED_CHECKLIST:
        v = payload.get(k)
        if v is None or (isinstance(v, (str, list, dict)) and len(v) == 0):
            miss.append(k)
    return miss


@app.post("/v1/agents/{agent_id}/golive-checklist")
def submit_checklist(agent_id: str, body: dict, authorization: str = Header(default="")) -> dict:
    """Owner nộp checklist; dữ liệu team/KPI chảy thẳng vào second brain."""

    _require_admin(authorization)
    _ensure_schema()
    payload = body.get("payload") or body
    miss = missing_checklist(payload)
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO agent_golive_checklist (agent_id, payload, submitted_by)
            VALUES (%s,%s,%s)
            ON CONFLICT (agent_id) DO UPDATE SET payload=EXCLUDED.payload,
              submitted_by=EXCLUDED.submitted_by, submitted_at=now()
            """,
            (agent_id, Json(payload), body.get("submitted_by") or payload.get("owner_email")),
        )
        # Nạp vào second brain (bảng chung) nếu có team_id.
        tid = payload.get("team_id")
        if tid:
            conn.execute(
                "INSERT INTO teams (team_id, name) VALUES (%s,%s) ON CONFLICT (team_id) DO NOTHING",
                (tid, payload.get("team_name") or tid),
            )
            for m in payload.get("team_members") or []:
                if isinstance(m, dict) and m.get("full_name"):
                    conn.execute(
                        """
                        INSERT INTO team_members (team_id, full_name, lark_user_id, role, expertise)
                        VALUES (%s,%s,%s,%s,%s)
                        ON CONFLICT (team_id, full_name) DO UPDATE SET
                          lark_user_id=EXCLUDED.lark_user_id, role=EXCLUDED.role,
                          expertise=EXCLUDED.expertise
                        """,
                        (tid, m.get("full_name"), m.get("lark_user_id"), m.get("role"),
                         m.get("expertise")),
                    )
            for k in payload.get("kpis") or []:
                if isinstance(k, dict) and k.get("kpi_name"):
                    conn.execute(
                        """
                        INSERT INTO team_kpis (team_id, kpi_name, unit, formula, data_source,
                                               target, period, weight)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (team_id, kpi_name, period) DO UPDATE SET
                          unit=EXCLUDED.unit, formula=EXCLUDED.formula,
                          data_source=EXCLUDED.data_source, target=EXCLUDED.target
                        """,
                        (tid, k.get("kpi_name"), k.get("unit"), k.get("formula"),
                         k.get("data_source"), k.get("target"), k.get("period"),
                         k.get("weight", 1)),
                    )
        conn.commit()
    return {"agent_id": agent_id, "complete": not miss, "missing": miss}


@app.get("/v1/agents/{agent_id}/golive-checklist")
def get_checklist(agent_id: str) -> dict:
    _ensure_schema()
    with _db() as conn:
        row = conn.execute(
            "SELECT payload, submitted_by, submitted_at FROM agent_golive_checklist "
            "WHERE agent_id=%s", (agent_id,)).fetchone()
    if not row:
        return {"agent_id": agent_id, "submitted": False,
                "missing": REQUIRED_CHECKLIST, "required": REQUIRED_CHECKLIST}
    miss = missing_checklist(row["payload"] or {})
    return {"agent_id": agent_id, "submitted": True, "complete": not miss,
            "missing": miss, "payload": row["payload"],
            "submitted_by": row["submitted_by"], "submitted_at": row["submitted_at"]}


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
