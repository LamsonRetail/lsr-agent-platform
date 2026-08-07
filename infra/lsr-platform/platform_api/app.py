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
import pathlib
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

import psycopg
import requests
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse, Response
from psycopg.rows import dict_row
from psycopg.types.json import Json

DATABASE_URL = os.environ["DATABASE_URL"]
COLLECTOR_URL = os.environ.get("COLLECTOR_URL", "http://collector:8081").rstrip("/")
COLLECTOR_INGEST_TOKEN = os.environ.get("COLLECTOR_INGEST_TOKEN", "")
ADMIN_TOKEN = os.environ.get("PLATFORM_ADMIN_TOKEN", "")
# Self-service: token cấp cho thành viên để TỰ đăng ký agent (tạo agent inactive +
# cấp telemetry key). Yếu quyền hơn admin (không active được agent). Rỗng = tắt enroll.
ENROLL_TOKEN = os.environ.get("LSR_ENROLL_TOKEN", "")
# URL collector CÔNG KHAI (để hướng dẫn cấu hình plugin cho agent bên ngoài).
COLLECTOR_PUBLIC_URL = os.environ.get(
    "LSR_COLLECTOR_PUBLIC", "https://collector.34-126-154-135.sslip.io")
# URL bảng điều khiển (web UI) — sinh link dashboard/backend riêng cho từng agent.
APP_PUBLIC_URL = os.environ.get(
    "LSR_APP_PUBLIC", "https://app.34-126-154-135.sslip.io").rstrip("/")
# --- Agent runtime trên VM (docker per-agent, subscription của owner) ---
# Trừu tượng hoá "nơi chạy": platform nói chuyện với 1 Docker daemon qua base_url.
# GĐ này: trỏ tới docker-socket-proxy trên VM chung (quyền hạn chế, KHÔNG mount socket
# thẳng vào API). Tương lai: mỗi agent set `runtime_host` = daemon của VM riêng → KHÔNG
# đổi code, chỉ đổi target.
AGENT_RUNNER_IMAGE = os.environ.get("AGENT_RUNNER_IMAGE", "lsr-agent-runner:latest")
AGENT_NETWORK = os.environ.get("LSR_AGENT_NETWORK", "lsr-platform_default")
AGENT_DOCKER_HOST = os.environ.get("AGENT_DOCKER_HOST", "tcp://docker_proxy:2375")


def _agent_container(agent_id: str) -> str:
    return "lsr-agent-" + re.sub(r"[^a-z0-9_.-]", "-", agent_id.lower())


def _agent_runtime_host(agent_id: str) -> str:
    """Docker daemon để chạy agent: runtime_host riêng nếu có, mặc định proxy VM chung."""
    try:
        with _db() as conn:
            row = conn.execute("SELECT runtime_host FROM agents WHERE agent_id=%s",
                               (agent_id,)).fetchone()
        return (row or {}).get("runtime_host") or AGENT_DOCKER_HOST
    except Exception:
        return AGENT_DOCKER_HOST


def _docker_client(agent_id: str):
    import docker  # type: ignore
    return docker.DockerClient(base_url=_agent_runtime_host(agent_id))


def _agent_links(agent_id: str, backend_url: str = "", dashboard_url: str = "") -> dict:
    """Link dashboard + backend riêng của agent.

    Ưu tiên URL agent tự khai báo khi đăng ký (backend riêng của họ); nếu chưa khai
    báo thì trỏ về trang per-agent do platform host (fallback).
    """
    return {
        "dashboard_url": dashboard_url or f"{APP_PUBLIC_URL}/agent/{agent_id}",
        "backend_url": backend_url or f"{APP_PUBLIC_URL}/agent/{agent_id}#backend",
    }
# Lark notify: bot của platform (fallback creds Minh Anh nếu chưa cấu hình riêng)
LARK_APP_ID = os.environ.get("LARK_NOTIFY_APP_ID") or os.environ.get("MINH_ANH_LARK_APP_ID", "")
LARK_APP_SECRET = os.environ.get("LARK_NOTIFY_APP_SECRET") or os.environ.get("MINH_ANH_LARK_APP_SECRET", "")
LARK_DOMAIN = os.environ.get("LARK_DOMAIN", "https://open.larksuite.com").rstrip("/")
LARK_NOTIFY = os.environ.get("LARK_NOTIFY_ENABLED", "true").lower() != "false"
# Nhóm nhận thông báo khi CHƯA có scope contact:user.id:readonly (không tra được email→open_id)
LARK_NOTIFY_CHAT_ID = os.environ.get("LARK_NOTIFY_CHAT_ID", "")

# --- Cost & Quota ---------------------------------------------------------
# Agent dùng SUBSCRIPTION của owner (không tính tiền theo token) → chi phí ở đây là
# ƯỚC TÍNH quy đổi theo giá API công khai (USD / 1 triệu token), dùng làm thước đo
# mức dùng + đặt hạn mức. Có thể override bằng env MODEL_PRICES_JSON.
_DEFAULT_PRICES = {
    # prefix model : (giá input, giá output) USD / 1M token
    "claude-opus":   (15.0, 75.0),
    "claude-sonnet": (3.0, 15.0),
    "claude-haiku":  (0.80, 4.0),
    "claude-fable":  (3.0, 15.0),
    "claude-3-opus": (15.0, 75.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-5-haiku": (0.80, 4.0),
}
try:
    MODEL_PRICES = {**_DEFAULT_PRICES, **json.loads(os.environ.get("MODEL_PRICES_JSON", "{}"))}
except Exception:
    MODEL_PRICES = dict(_DEFAULT_PRICES)
# Giá mặc định khi không nhận diện được model (lấy mức sonnet).
_FALLBACK_PRICE = (3.0, 15.0)
# Chu kỳ quét cảnh báo hạn mức (giây); 0 = tắt daemon.
ALERT_INTERVAL = int(os.environ.get("QUOTA_ALERT_INTERVAL", "1800"))
# Ngưỡng cảnh báo mặc định (%) nếu quota không đặt riêng.
DEFAULT_ALERT_PCT = int(os.environ.get("QUOTA_DEFAULT_ALERT_PCT", "80"))
# --- A3 Health monitor: agent 'active' im lặng quá ngưỡng giờ → cảnh báo ---
HEALTH_SILENT_HOURS = int(os.environ.get("HEALTH_SILENT_HOURS", "24"))
# --- A4 LLM-judge (tùy chọn): endpoint chấm chủ quan; rỗng = tắt, fallback contains ---
JUDGE_URL = os.environ.get("JUDGE_URL", "").rstrip("/")
JUDGE_TOKEN = os.environ.get("JUDGE_TOKEN", "")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "claude-haiku-4-5-20251001")

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
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS lark_app_id text",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS lark_chat_ids text[]",
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
            CREATE TABLE IF NOT EXISTS lark_admin_actions (
                id         bigserial PRIMARY KEY,
                agent_id   text,
                action     text,        -- remove_bot | add_bot
                chat_id    text,
                ok         boolean,
                detail     text,
                acted_at   timestamptz DEFAULT now()
            )
            """
        )
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
        for ddl in (
            "ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS source_url text",
            "ALTER TABLE shared_beliefs ADD COLUMN IF NOT EXISTS source_url text",
            "ALTER TABLE team_context ADD COLUMN IF NOT EXISTS source_url text",
            "ALTER TABLE knowledge_conflicts ADD COLUMN IF NOT EXISTS source_url text",
        ):
            conn.execute(ddl)
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
                delivered_lark boolean DEFAULT false,
                created_at timestamptz DEFAULT now()
            )
            """
        )
        conn.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS delivered_lark boolean DEFAULT false")
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
        # --- Cost & Quota: hạn mức theo agent + lịch sử cảnh báo (chống spam) ---
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_quotas (
                agent_id            text PRIMARY KEY,
                monthly_usd_limit   numeric,
                monthly_token_limit bigint,
                alert_pct           int DEFAULT 80,
                updated_at          timestamptz DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quota_alerts (
                id          bigserial PRIMARY KEY,
                agent_id    text,
                period      text,          -- 'YYYY-MM'
                level       int,           -- 80 | 100
                usd         numeric,
                tokens      bigint,
                fired_at    timestamptz DEFAULT now(),
                UNIQUE (agent_id, period, level)
            )
            """
        )
        # --- A1: Audit log toàn platform (ai làm gì, khi nào) ---
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id          bigserial PRIMARY KEY,
                actor       text,          -- admin | email reviewer/owner
                action      text,          -- register | set_status | set_quota | ...
                target_type text,          -- agent | knowledge | conflict | belief | ...
                target_id   text,
                detail      jsonb,
                at          timestamptz DEFAULT now()
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_log(target_id)")
        # --- A3: Health alerts (agent active nhưng im lặng) — dedup theo ngày ---
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_health_alerts (
                id        bigserial PRIMARY KEY,
                agent_id  text,
                kind      text,            -- silent | never
                day       text,            -- 'YYYY-MM-DD'
                detail    text,
                fired_at  timestamptz DEFAULT now(),
                UNIQUE (agent_id, kind, day)
            )
            """
        )
        # --- A4: Golden set + regression run ---
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS golden_cases (
                case_id    text PRIMARY KEY,
                skill      text,
                prompt     text,
                expected   text,
                atype      text DEFAULT 'contains',  -- exact|regex|numeric_tolerance|contains|llm_judge
                tol        numeric DEFAULT 0,
                weight     numeric DEFAULT 1,
                rubric     text,                      -- cho llm_judge
                active     boolean DEFAULT true,
                created_by text,
                created_at timestamptz DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS regression_runs (
                run_id      text PRIMARY KEY,
                target_type text,          -- agent | prompt | model
                target_id   text,
                skill       text,
                score       numeric,
                passed      boolean,
                n_total     int,
                n_pass      int,
                threshold   numeric,
                detail      jsonb,
                run_by      text,
                at          timestamptz DEFAULT now()
            )
            """
        )
        # Item 4: con trỏ version prompt (rollback sau = đổi con trỏ; prompt vẫn git-backed).
        conn.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS prompt_version text")
        conn.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS prompt_ref text")
        # Backend riêng của agent (config/chi tiết/dashboard) — đăng ký kèm URL.
        conn.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS backend_url text")
        conn.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS dashboard_url text")
        # Nơi chạy agent runtime: NULL = VM chung (proxy mặc định); set = daemon VM riêng.
        conn.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS runtime_host text")
        # Item 3: bảng policies (admin ghi; collector đọc để chặn runtime).
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS policies (
                policy_id  text PRIMARY KEY,
                agent_id   text,
                phase      text,
                effect     text DEFAULT 'deny',
                rule       jsonb,
                reason     text,
                active     boolean DEFAULT true,
                created_at timestamptz DEFAULT now()
            )
            """
        )
        # Item 5: cấu hình retention (CHƯA bật purge — chỉ khai báo).
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS retention_config (
                scope      text PRIMARY KEY,   -- traces | audit | notifications | ...
                ttl_days   int,
                action     text DEFAULT 'delete',  -- delete | anonymize
                enabled    boolean DEFAULT false,
                updated_at timestamptz DEFAULT now()
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


_BOOTSTRAP_DIR = pathlib.Path(__file__).parent / "bootstrap"
# Đều là TEMPLATE (không chứa token) — an toàn phục vụ công khai. Installer tự hỏi token.
_BOOTSTRAP_ALLOW = {
    "lsr_adopt.py", "lsr_trace.py", "onboard.sh",
    "lsr-telemetry-plugin.zip",         # plugin đóng gói (cài không cần GitHub)
    "lsr-install.command", "lsr-install.bat",  # installer click-and-run (Mac/Windows)
}
_BOOTSTRAP_MTYPE = {
    ".py": "text/x-python", ".sh": "text/x-shellscript",
    ".command": "text/x-shellscript", ".bat": "text/plain", ".zip": "application/zip",
}


@app.get("/bootstrap/{name}")
def bootstrap(name: str):
    """Phục vụ file bootstrap self-service (không cần GitHub/auth) — vì repo private.

    Chỉ allowlist. Dùng: curl PLATFORM/bootstrap/lsr_adopt.py -O
    """

    if name not in _BOOTSTRAP_ALLOW:
        raise HTTPException(status_code=404, detail="not found")
    p = _BOOTSTRAP_DIR / name
    if not p.exists():
        raise HTTPException(status_code=503, detail="chưa publish (deploy lại platform)")
    mtype = _BOOTSTRAP_MTYPE.get(p.suffix, "application/octet-stream")
    if mtype == "application/zip":
        return Response(p.read_bytes(), media_type=mtype,
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})
    return PlainTextResponse(p.read_text(encoding="utf-8"), media_type=mtype)


# ==================== Agent-scoped API (/v1/self*) ====================
# Backend riêng của agent gọi bằng CHÍNH telemetry key của nó (Bearer) — KHÔNG cần
# admin token, KHÔNG cần gateway token. Chỉ thấy dữ liệu của agent đó.

def _agent_from_token(authorization: str) -> str | None:
    tok = authorization[7:] if authorization.startswith("Bearer ") else ""
    if not tok:
        return None
    h = hashlib.sha256(tok.encode()).hexdigest()
    try:
        with _db() as conn:
            row = conn.execute(
                "SELECT agent_id FROM agents WHERE telemetry_key_hash=%s", (h,)).fetchone()
        return row["agent_id"] if row else None
    except Exception:
        return None


def _require_self(authorization: str) -> str:
    aid = _agent_from_token(authorization)
    if not aid:
        raise HTTPException(status_code=401, detail="agent token required (LSR_AGENT_TOKEN)")
    return aid


@app.get("/v1/self")
def self_info(authorization: str = Header(default="")) -> dict:
    aid = _require_self(authorization)
    with _db() as conn:
        a = conn.execute(
            "SELECT agent_id, name, owner, squad, connect_mode, status, deployment, "
            "repo_url, prompt_version, prompt_ref, backend_url, dashboard_url, "
            "registered_at, golive_at FROM agents WHERE agent_id=%s", (aid,)).fetchone()
        st = conn.execute(
            "SELECT count(*) AS runs, coalesce(sum(total_tokens),0) AS total_tokens, "
            "coalesce(sum(tool_calls),0) AS tool_calls, coalesce(sum(pii_flags),0) AS pii_flags "
            "FROM agent_traces WHERE agent_id=%s", (aid,)).fetchone()
    return {"agent": a, "db_schema": agent_schema(aid), "stats": st}


@app.get("/v1/self/conflicts")
def self_conflicts(authorization: str = Header(default=""), status: str = "open") -> list[dict]:
    aid = _require_self(authorization)
    with _db() as conn:
        return conn.execute(
            "SELECT * FROM knowledge_conflicts WHERE agent_id=%s AND status=%s "
            "ORDER BY created_at DESC LIMIT 100", (aid, status)).fetchall()


@app.get("/v1/self/attempts")
def self_attempts(authorization: str = Header(default="")) -> list[dict]:
    aid = _require_self(authorization)
    with _db() as conn:
        return conn.execute(
            "SELECT attempt_id, test_id, taker_type, taker_id, score, passed, at "
            "FROM attempts WHERE taker_id=%s ORDER BY at DESC LIMIT 50", (aid,)).fetchall()


@app.get("/v1/self/traces")
def self_traces(authorization: str = Header(default=""), limit: int = 25) -> list[dict]:
    aid = _require_self(authorization)
    try:
        r = requests.get(f"{COLLECTOR_URL}/v1/traces",
                         params={"agent_id": aid, "limit": min(int(limit), 100)},
                         headers={"Authorization": f"Bearer {COLLECTOR_INGEST_TOKEN}"}, timeout=8)
        return r.json()
    except Exception:
        return []


@app.post("/v1/self/backend")
def self_set_backend(body: dict, authorization: str = Header(default="")) -> dict:
    """Agent tự đặt URL backend/dashboard của mình (dùng bởi script provision Vercel)."""

    aid = _require_self(authorization)
    with _db() as conn:
        conn.execute(
            "UPDATE agents SET backend_url=coalesce(%s, backend_url), "
            "dashboard_url=coalesce(%s, dashboard_url) WHERE agent_id=%s",
            (body.get("backend_url"), body.get("dashboard_url"), aid))
        _audit(conn, aid, "set_backend", "agent", aid,
               {"backend_url": body.get("backend_url")})
        conn.commit()
    return {"agent_id": aid, "backend_url": body.get("backend_url"), "ok": True}


@app.post("/v1/self/deploy")
def self_deploy(body: dict, authorization: str = Header(default="")) -> dict:
    """Self-service: chạy AGENT runtime trên VM (docker per-agent) bằng subscription owner.

    body: { oauth_token (bắt buộc, từ `claude setup-token`), repo?, start_cmd?, mem_mb?, cpus? }
    Token subscription lưu root-only trên VM, KHÔNG log. Một container / agent, giới hạn tài nguyên.
    """

    aid = _require_self(authorization)
    tok = authorization[7:] if authorization.startswith("Bearer ") else ""
    oauth = (body.get("oauth_token") or "").strip()
    if not oauth:
        raise HTTPException(status_code=422, detail="cần oauth_token (chạy `claude setup-token`)")
    try:
        client = _docker_client(aid)
    except Exception:
        raise HTTPException(status_code=501, detail="runtime chưa bật (thiếu docker SDK/host)")

    # Env truyền thẳng vào container qua daemon (không ghi file host — thân thiện đa-VM).
    env = {
        "CLAUDE_CODE_OAUTH_TOKEN": oauth,
        "LSR_AGENT_ID": aid,
        "LSR_COLLECTOR": "http://collector:8081",   # nội bộ docker network (GĐ VM chung)
        "LSR_TELEMETRY_API_KEY": tok,
        "AGENT_REPO": body.get("repo") or "",
        "AGENT_START_CMD": body.get("start_cmd") or "",
    }
    name = _agent_container(aid)
    mem = int(body.get("mem_mb") or 512)
    cpus = float(body.get("cpus") or 0.5)
    try:
        try:
            client.containers.get(name).remove(force=True)
        except Exception:
            pass
        c = client.containers.run(
            AGENT_RUNNER_IMAGE, name=name, detach=True,
            environment=env, network=AGENT_NETWORK,
            restart_policy={"Name": "unless-stopped"},
            mem_limit=f"{mem}m", nano_cpus=int(cpus * 1e9),
            labels={"lsr-agent": aid},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"không chạy được container: {str(exc)[:200]}")
    with _db() as conn:
        _audit(conn, aid, "deploy_vm", "agent", aid,
               {"container": name, "host": _agent_runtime_host(aid),
                "repo": bool(body.get("repo")), "mem_mb": mem, "cpus": cpus})
        conn.commit()
    return {"agent_id": aid, "container": name, "status": c.status,
            "runtime_host": _agent_runtime_host(aid),
            "note": "agent chạy bằng subscription owner; telemetry + enforce đã bật"}


@app.get("/v1/self/deploy/status")
def self_deploy_status(authorization: str = Header(default="")) -> dict:
    aid = _require_self(authorization)
    try:
        c = _docker_client(aid).containers.get(_agent_container(aid))
        return {"agent_id": aid, "container": c.name, "status": c.status,
                "runtime_host": _agent_runtime_host(aid),
                "started": (c.attrs.get("State") or {}).get("StartedAt")}
    except Exception:
        return {"agent_id": aid, "status": "not_deployed"}


def _agent_vm_action(agent_id: str, action: str) -> str:
    """start/stop container runtime của agent (dùng khi de/activate). Best-effort."""
    try:
        c = _docker_client(agent_id).containers.get(_agent_container(agent_id))
        if action == "stop":
            c.stop(timeout=10)
        elif action == "start":
            c.start()
        return c.status
    except Exception:
        return "n/a"


@app.post("/v1/self/conflicts/{conflict_id}/resolve")
def self_resolve(conflict_id: str, body: dict, authorization: str = Header(default="")) -> dict:
    aid = _require_self(authorization)
    _ensure_schema()
    decision = body.get("decision")
    valid = ("resolved_keep_shared", "resolved_update_shared", "dismissed")
    if decision not in valid:
        raise HTTPException(status_code=422, detail=f"decision phải thuộc {valid}")
    with _db() as conn:
        c = conn.execute("SELECT agent_id FROM knowledge_conflicts WHERE conflict_id=%s",
                         (conflict_id,)).fetchone()
        if not c:
            raise HTTPException(status_code=404, detail="không tìm thấy conflict")
        if c["agent_id"] != aid:
            raise HTTPException(status_code=403, detail="conflict không thuộc agent này")
        conn.execute("UPDATE knowledge_conflicts SET status=%s, resolution=%s, resolved_at=now() "
                     "WHERE conflict_id=%s", (decision, body.get("resolution"), conflict_id))
        _audit(conn, aid, "resolve_conflict", "conflict", conflict_id, {"decision": decision})
        conn.commit()
    return {"conflict_id": conflict_id, "status": decision}


@app.post("/v1/agents/register")
def register(agent: dict, authorization: str = Header(default=""),
             x_actor: str = Header(default="", alias="X-Actor")) -> dict:
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
                                deployment, repo_url, host_note, backup_owner,
                                prompt_version, prompt_ref, backend_url, dashboard_url)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'registered',%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (agent_id) DO UPDATE SET
                name=EXCLUDED.name, owner=EXCLUDED.owner, squad=EXCLUDED.squad,
                connect_mode=EXCLUDED.connect_mode, is_squad_agent=EXCLUDED.is_squad_agent,
                skills=EXCLUDED.skills, telemetry_key_hash=EXCLUDED.telemetry_key_hash,
                deployment=EXCLUDED.deployment, repo_url=EXCLUDED.repo_url,
                host_note=EXCLUDED.host_note, backup_owner=EXCLUDED.backup_owner,
                prompt_version=EXCLUDED.prompt_version, prompt_ref=EXCLUDED.prompt_ref,
                backend_url=EXCLUDED.backend_url, dashboard_url=EXCLUDED.dashboard_url
            """,
            (
                agent_id, agent.get("name"), agent.get("owner"), agent.get("squad"),
                agent.get("connect_mode", "bot"), bool(agent.get("is_squad_agent", False)),
                skills, key_hash,
                agent.get("deployment", "managed"), agent.get("repo_url"),
                agent.get("host_note"), agent.get("backup_owner"),
                agent.get("prompt_version"), agent.get("prompt_ref"),
                agent.get("backend_url"), agent.get("dashboard_url"),
            ),
        )
        # Dataset riêng cho agent trên Supabase chung: mỗi agent 1 schema Postgres.
        schema = agent_schema(agent_id)
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        _audit(conn, x_actor or "admin", "register", "agent", agent_id,
               {"name": agent.get("name"), "owner": agent.get("owner"),
                "deployment": agent.get("deployment", "managed")})
        conn.commit()
    dictionary_shared = _minh_anh_share(agent_id)
    return {
        "agent_id": agent_id,
        "status": "registered",
        "telemetry_key": telemetry_key,  # hiện MỘT LẦN
        "dictionary_shared": dictionary_shared,
        "db_schema": schema,
        "deployment": agent.get("deployment", "managed"),
        **_agent_links(agent_id, agent.get("backend_url"), agent.get("dashboard_url")),
    }


_EMAIL_RE = re.compile(r"^[^@]+@[^@]+\.[^@]+$")


@app.post("/v1/agents/enroll")
def enroll(agent: dict, authorization: str = Header(default="")) -> dict:
    """SELF-SERVICE: thành viên tự đăng ký agent MỚI + nhận telemetry key.

    Khác register (admin): gated bằng LSR_ENROLL_TOKEN; chỉ tạo agent MỚI ở trạng thái
    'registered' (KHÔNG active được — golive vẫn cần admin + đủ checklist). Chống chiếm
    key của agent đã có (409 nếu trùng id).
    """

    if not ENROLL_TOKEN or authorization != f"Bearer {ENROLL_TOKEN}":
        raise HTTPException(status_code=401, detail="enroll token required (LSR_ENROLL_TOKEN)")
    _ensure_schema()
    agent_id = (agent.get("agent_id") or "").strip()
    owner = str(agent.get("owner", "")).strip()
    if not agent_id:
        raise HTTPException(status_code=422, detail="agent_id required")
    if not _EMAIL_RE.match(owner):
        raise HTTPException(status_code=422, detail="owner phải là email thật của người sở hữu")
    skills = agent.get("skills") or []
    if not isinstance(skills, list):
        skills = [str(skills)]
    telemetry_key = "lsr_tel_" + secrets.token_hex(20)
    key_hash = hashlib.sha256(telemetry_key.encode()).hexdigest()
    with _db() as conn:
        if conn.execute("SELECT 1 FROM agents WHERE agent_id=%s", (agent_id,)).fetchone():
            raise HTTPException(status_code=409,
                detail="agent_id đã tồn tại — nhờ admin cấp lại key (không enroll đè)")
        conn.execute(
            """
            INSERT INTO agents (agent_id, name, owner, squad, connect_mode, is_squad_agent,
                                skills, status, telemetry_key_hash, deployment, repo_url,
                                host_note, backup_owner, prompt_version, prompt_ref,
                                backend_url, dashboard_url)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'registered',%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (agent_id, agent.get("name"), owner, agent.get("squad"),
             agent.get("connect_mode", "bot"), bool(agent.get("is_squad_agent", False)),
             skills, key_hash, agent.get("deployment", "managed"), agent.get("repo_url"),
             agent.get("host_note"), agent.get("backup_owner"),
             agent.get("prompt_version"), agent.get("prompt_ref"),
             agent.get("backend_url"), agent.get("dashboard_url")),
        )
        schema = agent_schema(agent_id)
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        _audit(conn, owner, "enroll", "agent", agent_id,
               {"name": agent.get("name"), "deployment": agent.get("deployment", "managed"),
                "self_service": True})
        conn.commit()
    _minh_anh_share(agent_id)
    return {
        "agent_id": agent_id,
        "status": "registered",
        "telemetry_key": telemetry_key,     # hiện MỘT LẦN — dùng cho plugin VÀ backend
        "agent_token": telemetry_key,       # alias: LSR_AGENT_TOKEN cho API /v1/self*
        "db_schema": schema,                # schema Postgres riêng của agent (truy cập qua /v1/self*)
        "collector": COLLECTOR_PUBLIC_URL,
        "platform": f"{APP_PUBLIC_URL}".replace("app.", "platform."),
        **_agent_links(agent_id, agent.get("backend_url"), agent.get("dashboard_url")),
        "next_steps": [
            "Cài plugin: claude plugin marketplace add LamsonRetail/lsr-agent-platform "
            "&& claude plugin install lsr-telemetry@lsr",
            f"Env agent (runtime): LSR_COLLECTOR={COLLECTOR_PUBLIC_URL} "
            f"LSR_AGENT_ID={agent_id} LSR_TELEMETRY_API_KEY=<telemetry_key>",
            "Env backend (Vercel, tài khoản OWNER): LSR_AGENT_TOKEN=<telemetry_key> "
            "— backend gọi /v1/self* để lấy dữ liệu agent (không cần admin/gateway token).",
            "Deploy backend: node scripts/provision-vercel.mjs " + agent_id +
            " (dùng VERCEL_TOKEN của owner) → tự set backend_url.",
            "Hoàn tất golive checklist rồi nhờ admin chuyển sang 'active'.",
        ],
    }


@app.get("/v1/agents")
def list_agents() -> list[dict]:
    _ensure_schema()
    with _db() as conn:
        return conn.execute(
            "SELECT agent_id, name, owner, squad, connect_mode, is_squad_agent, "
            "skills, status, deployment, repo_url, host_note, prompt_version, prompt_ref, "
            "backend_url, dashboard_url, registered_at, golive_at "
            "FROM agents ORDER BY registered_at DESC"
        ).fetchall()


@app.get("/v1/agents/{agent_id}")
def get_agent(agent_id: str) -> dict:
    _ensure_schema()
    with _db() as conn:
        row = conn.execute(
            "SELECT agent_id, name, owner, squad, connect_mode, is_squad_agent, "
            "skills, status, deployment, repo_url, host_note, prompt_version, prompt_ref, "
            "backend_url, dashboard_url, registered_at, golive_at "
            "FROM agents WHERE agent_id=%s",
            (agent_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return row


@app.post("/v1/agents/{agent_id}/status")
def set_status(agent_id: str, body: dict, authorization: str = Header(default=""),
               x_actor: str = Header(default="", alias="X-Actor")) -> dict:
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
        lark = []
        if status in ("active", "deactivated"):
            # Đồng bộ Lark: tắt agent -> gỡ bot khỏi chat; bật lại -> thêm vào lại.
            lark = _sync_lark_status(conn, agent_id, activate=(status == "active"))
        # Đồng bộ runtime VM: tắt agent -> stop container; bật lại -> start (nếu đã deploy).
        vm = _agent_vm_action(agent_id, "start" if status == "active" else "stop") \
            if status in ("active", "deactivated") else None
        _audit(conn, x_actor or "admin", "set_status", "agent", agent_id,
               {"status": status, "forced": bool(body.get("force")), "lark_sync": lark, "vm": vm})
        conn.commit()
    return {"agent_id": agent_id, "status": status, "lark_sync": lark, "vm": vm}


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
            "INSERT INTO team_context (team_id, title, md_content, tags, created_by, source_url) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (team_id, body.get("title"), body.get("md_content"),
             body.get("tags") or [], body.get("created_by"), body.get("source_url")),
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
            "SELECT title, md_content, tags, source_url, created_at FROM team_context "
            "WHERE team_id=%s ORDER BY created_at DESC LIMIT 50", (team_id,)).fetchall()
    return {"team": team, "members": members, "kpis": kpis, "context": ctx}


# ======================= LSR Brain: shared brain + consolidate =======================

_LARK_TOKEN: dict = {"value": "", "exp": 0.0}


def _lark_token() -> str:
    """tenant_access_token (cache tới khi gần hết hạn)."""

    import time as _t
    if _LARK_TOKEN["value"] and _t.time() < _LARK_TOKEN["exp"]:
        return _LARK_TOKEN["value"]
    if not (LARK_APP_ID and LARK_APP_SECRET):
        return ""
    r = requests.post(
        f"{LARK_DOMAIN}/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": LARK_APP_ID, "app_secret": LARK_APP_SECRET}, timeout=10)
    d = r.json()
    if d.get("code") != 0:
        return ""
    _LARK_TOKEN["value"] = d["tenant_access_token"]
    _LARK_TOKEN["exp"] = _t.time() + int(d.get("expire", 7200)) - 120
    return _LARK_TOKEN["value"]


def _lark_open_id(email: str, token: str) -> str:
    """Tra open_id từ email công ty (cần scope contact:user.id:readonly)."""

    r = requests.post(
        f"{LARK_DOMAIN}/open-apis/contact/v3/users/batch_get_id?user_id_type=open_id",
        headers={"Authorization": f"Bearer {token}"},
        json={"emails": [email]}, timeout=10)
    try:
        for u in (r.json().get("data") or {}).get("user_list") or []:
            if u.get("user_id"):
                return u["user_id"]
    except Exception:
        pass
    # Fallback: Lark lưu 2 email (cá nhân `email` vs `enterprise_email`).
    # batch_get_id chỉ khớp email cá nhân → quét danh bạ tìm theo enterprise_email.
    return _lark_open_id_by_enterprise_email(email, token)


_ENT_EMAIL_CACHE: dict = {}


def _lark_open_id_by_enterprise_email(email: str, token: str) -> str:
    key = (email or "").lower()
    if key in _ENT_EMAIL_CACHE:
        return _ENT_EMAIL_CACHE[key]
    h = {"Authorization": f"Bearer {token}"}

    def _scan_dept(dept_id: str) -> str:
        page = ""
        for _ in range(20):
            url = (f"{LARK_DOMAIN}/open-apis/contact/v3/users?department_id={dept_id}"
                   f"&page_size=50" + (f"&page_token={page}" if page else ""))
            try:
                d = (requests.get(url, headers=h, timeout=15).json().get("data") or {})
            except Exception:
                return ""
            for u in d.get("items") or []:
                for f in ("enterprise_email", "email"):
                    em = (u.get(f) or "").lower()
                    if em:
                        _ENT_EMAIL_CACHE[em] = u.get("open_id", "")
            if key in _ENT_EMAIL_CACHE:
                return _ENT_EMAIL_CACHE[key]
            if not d.get("has_more"):
                break
            page = d.get("page_token") or ""
        return ""

    # Duyệt toàn bộ cây phòng ban (fetch_child) — user có thể ở dept con.
    dept_ids = ["0"]
    page = ""
    for _ in range(30):
        url = (f"{LARK_DOMAIN}/open-apis/contact/v3/departments?parent_department_id=0"
               f"&fetch_child=true&page_size=50" + (f"&page_token={page}" if page else ""))
        try:
            d = (requests.get(url, headers=h, timeout=15).json().get("data") or {})
        except Exception:
            break
        dept_ids += [x.get("department_id") for x in (d.get("items") or []) if x.get("department_id")]
        if not d.get("has_more"):
            break
        page = d.get("page_token") or ""

    for did in dict.fromkeys(dept_ids):  # loại trùng, giữ thứ tự
        if _scan_dept(did):
            return _ENT_EMAIL_CACHE[key]
    return ""


def _send_lark(to_email: str, text: str) -> bool:
    """Gửi tin nhắn Lark cho một email. Best-effort — lỗi không làm hỏng request."""

    if not LARK_NOTIFY:
        return False
    try:
        token = _lark_token()
        if not token:
            return False
        open_id = _lark_open_id(to_email, token)
        if open_id:
            receive_id, id_type, body = open_id, "open_id", text
        elif LARK_NOTIFY_CHAT_ID:
            # Chưa tra được email→open_id (thiếu scope contact:user.id:readonly)
            # → gửi vào nhóm chung, ghi rõ người nhận để không mất thông báo.
            receive_id, id_type, body = LARK_NOTIFY_CHAT_ID, "chat_id", f"@{to_email}: {text}"
        else:
            return False
        r = requests.post(
            f"{LARK_DOMAIN}/open-apis/im/v1/messages?receive_id_type={id_type}",
            headers={"Authorization": f"Bearer {token}"},
            json={"receive_id": receive_id, "msg_type": "text",
                  "content": json.dumps({"text": body}, ensure_ascii=False)},
            timeout=10)
        return r.json().get("code") == 0
    except Exception:
        return False


def _lark_chat_member(chat_id: str, app_id: str, add: bool) -> tuple[bool, str]:
    """Thêm/gỡ BOT khỏi một chat. Chỉ đổi thành viên — KHÔNG xoá tin nhắn/dữ liệu."""

    token = _lark_token()
    if not token:
        return False, "no lark token"
    url = f"{LARK_DOMAIN}/open-apis/im/v1/chats/{chat_id}/members?member_id_type=app_id"
    try:
        if add:
            r = requests.post(url, headers={"Authorization": f"Bearer {token}"},
                              json={"id_list": [app_id]}, timeout=10)
        else:
            r = requests.delete(url, headers={"Authorization": f"Bearer {token}"},
                                json={"id_list": [app_id]}, timeout=10)
        d = r.json()
        return d.get("code") == 0, str(d.get("msg"))[:120]
    except Exception as exc:
        return False, str(exc)[:120]


def _sync_lark_status(conn, agent_id: str, activate: bool) -> list[dict]:
    """Đồng bộ trạng thái agent sang Lark: gỡ bot khi tắt, thêm lại khi bật."""

    row = conn.execute(
        "SELECT lark_app_id, lark_chat_ids FROM agents WHERE agent_id=%s", (agent_id,)
    ).fetchone() or {}
    app_id = row.get("lark_app_id")
    chats = row.get("lark_chat_ids") or []
    results = []
    if not app_id or not chats:
        return results
    for cid in chats:
        ok, detail = _lark_chat_member(cid, app_id, add=activate)
        action = "add_bot" if activate else "remove_bot"
        conn.execute(
            "INSERT INTO lark_admin_actions (agent_id, action, chat_id, ok, detail) "
            "VALUES (%s,%s,%s,%s,%s)", (agent_id, action, cid, ok, detail))
        results.append({"chat_id": cid, "action": action, "ok": ok, "detail": detail})
    return results


def _audit(conn, actor: str, action: str, target_type: str, target_id: str,
           detail: dict | None = None) -> None:
    """Ghi audit log — best-effort, không làm hỏng request nếu lỗi."""

    try:
        conn.execute(
            "INSERT INTO audit_log (actor, action, target_type, target_id, detail) "
            "VALUES (%s,%s,%s,%s,%s)",
            (actor or "unknown", action, target_type, target_id,
             Json(detail or {})),
        )
    except Exception:
        pass


def _notify(conn, to_email: str, kind: str, ref_id: str, message: str) -> None:
    """Ghi hàng đợi + GỬI LARK cho người nhận (reviewer/agent owner)."""

    if not to_email:
        return
    delivered = _send_lark(to_email, message)
    conn.execute(
        "INSERT INTO notifications (to_email, kind, ref_id, message, delivered_lark) "
        "VALUES (%s,%s,%s,%s,%s)",
        (to_email, kind, ref_id, message, delivered),
    )


def _route_domain(conn, title: str, content: str, given: str | None) -> str:
    """Gán chuyên môn cho tri thức: ưu tiên domain đã có; nếu trống thì khớp keywords.

    Nhờ vậy notify đến ĐÚNG người phụ trách kể cả khi LSR Brain chưa gán domain.
    """

    if given:
        return given
    blob = f"{title or ''} {content or ''}".lower()
    if not blob.strip():
        return ""
    rows = conn.execute("SELECT domain, keywords FROM knowledge_domains").fetchall()
    best, best_hits = "", 0
    for r in rows:
        hits = sum(1 for k in (r.get("keywords") or []) if k and k.lower() in blob)
        if hits > best_hits:
            best, best_hits = r["domain"], hits
    return best


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
    sql = ("SELECT belief_id, title, statement, domain, source, source_url, version, "
           "updated_at FROM shared_beliefs")
    args: list = []
    if domain:
        sql += " WHERE domain=%s"
        args.append(domain)
    sql += " ORDER BY domain, belief_id"
    with _db() as conn:
        beliefs = conn.execute(sql, args).fetchall()
        knowledge = conn.execute(
            "SELECT item_id, title, md_content, domain, source_team, source_ref, source_url, "
            "reviewed_by, reviewed_at FROM knowledge_items WHERE status='approved' "
            "ORDER BY reviewed_at DESC LIMIT 200"
        ).fetchall()
    return {"beliefs": beliefs, "knowledge": knowledge}


@app.post("/v1/shared-beliefs")
def upsert_belief(b: dict, authorization: str = Header(default=""),
                  x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    """CHỈ admin: tạo/sửa niềm tin chung của LSR (có version)."""

    _require_admin(authorization)
    _ensure_schema()
    bid = b.get("belief_id")
    if not bid or not b.get("statement"):
        raise HTTPException(status_code=422, detail="belief_id và statement là bắt buộc")
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO shared_beliefs (belief_id, title, statement, domain, source,
                                        source_url, updated_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (belief_id) DO UPDATE SET title=EXCLUDED.title,
              statement=EXCLUDED.statement, domain=EXCLUDED.domain,
              source_url=EXCLUDED.source_url,
              version=shared_beliefs.version+1, updated_by=EXCLUDED.updated_by,
              updated_at=now()
            """,
            (bid, b.get("title"), b.get("statement"), b.get("domain"),
             b.get("source", "admin"), b.get("source_url"), b.get("updated_by", "admin")),
        )
        _audit(conn, x_actor or b.get("updated_by", "admin"), "upsert_belief", "belief", bid,
               {"title": b.get("title"), "domain": b.get("domain")})
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
    source_url = body.get("source_url", "")  # link Lark file gốc để đối chứng
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
                "source_url": source_url,
            })
        if len(out) >= 30:
            break
    return {"filename": filename, "suggestions": out, "count": len(out)}


# --- Reviewer: admin cấp quyền theo chuyên môn ---

@app.post("/v1/knowledge/reviewers")
def add_reviewer(body: dict, authorization: str = Header(default=""),
                 x_actor: str = Header(default="", alias="X-Actor")) -> dict:
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
        _audit(conn, x_actor or body.get("added_by", "admin"), "add_reviewer", "reviewer", email,
               {"domain": domain})
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
            it["domain"] = _route_domain(conn, it.get("title"), it.get("md_content"),
                                         it.get("domain"))
            conn.execute(
                """
                INSERT INTO knowledge_items (item_id, title, md_content, domain,
                                             source_team, source_ref, source_url)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (item_id) DO NOTHING
                """,
                (iid, it.get("title"), it.get("md_content"), it.get("domain"),
                 it.get("source_team"), it.get("source_ref"), it.get("source_url")),
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
    sql = ("SELECT item_id, title, domain, source_team, source_ref, source_url, "
           "status, reviewed_by, reviewed_at FROM knowledge_items WHERE status=%s")
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
        _audit(conn, reviewer, "review_knowledge", "knowledge", item_id,
               {"decision": decision, "domain": item["domain"]})
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
        _audit(conn, body.get("owner_email") or "owner", "resolve_conflict", "conflict",
               conflict_id, {"decision": decision, "agent_id": c.get("agent_id")})
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
    sql = "SELECT id, kind, ref_id, message, read, delivered_lark, created_at FROM notifications WHERE to_email=%s"
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


# ============================ Cost & Quota ============================
# Chi phí ước tính (agent chạy bằng subscription của owner → không có hoá đơn theo
# token; con số USD ở đây quy đổi theo giá API công khai để đo mức dùng + đặt hạn mức).

def _price_for(model: str) -> tuple[float, float]:
    m = (model or "").lower()
    # khớp prefix dài nhất trước (vd 'claude-3-5-sonnet' trước 'claude-sonnet')
    for key in sorted(MODEL_PRICES, key=len, reverse=True):
        if key in m:
            return MODEL_PRICES[key]
    return _FALLBACK_PRICE


def _cost_of_calls(calls) -> tuple[float, dict]:
    """Trả (tổng USD ước tính, breakdown theo model{tokens,usd})."""

    total = 0.0
    by_model: dict = {}
    for c in calls or []:
        it = int(c.get("input_tokens", 0) or 0)
        ot = int(c.get("output_tokens", 0) or 0)
        pin, pout = _price_for(c.get("model", ""))
        usd = it / 1e6 * pin + ot / 1e6 * pout
        total += usd
        mk = c.get("model") or "unknown"
        b = by_model.setdefault(mk, {"tokens": 0, "usd": 0.0})
        b["tokens"] += it + ot
        b["usd"] += usd
    return total, by_model


def _month_bounds(period: str | None) -> tuple[datetime, datetime, str]:
    """(start, end, 'YYYY-MM') cho tháng — mặc định tháng hiện tại (UTC+7)."""

    tz = timezone(timedelta(hours=7))
    now = datetime.now(tz)
    if period:
        y, m = int(period[:4]), int(period[5:7])
    else:
        y, m = now.year, now.month
    start = datetime(y, m, 1, tzinfo=tz)
    end = datetime(y + (m // 12), (m % 12) + 1, 1, tzinfo=tz)
    return start, end, f"{y:04d}-{m:02d}"


def _cost_rows(conn, start: datetime, end: datetime) -> list[dict]:
    """Đọc trace trong khoảng, tính tokens + USD ước tính theo agent/ngày."""

    rows = conn.execute(
        """
        SELECT agent_id,
               (received_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS day,
               total_tokens,
               coalesce(raw->'llm_calls','[]'::jsonb) AS calls
        FROM agent_traces
        WHERE received_at >= %s AND received_at < %s
        """,
        (start, end),
    ).fetchall()
    return rows


def _aggregate_cost(rows: list[dict]):
    """Gộp theo agent + theo ngày. Trả (per_agent, per_day)."""

    per_agent: dict = {}
    per_day: dict = {}
    for r in rows:
        aid = r["agent_id"] or "unknown"
        usd, by_model = _cost_of_calls(r["calls"])
        toks = int(r["total_tokens"] or 0)
        a = per_agent.setdefault(aid, {"agent_id": aid, "runs": 0, "tokens": 0,
                                       "usd": 0.0, "models": {}})
        a["runs"] += 1
        a["tokens"] += toks
        a["usd"] += usd
        for mk, b in by_model.items():
            mm = a["models"].setdefault(mk, {"tokens": 0, "usd": 0.0})
            mm["tokens"] += b["tokens"]
            mm["usd"] += b["usd"]
        dk = str(r["day"])
        d = per_day.setdefault(dk, {"day": dk, "tokens": 0, "usd": 0.0})
        d["tokens"] += toks
        d["usd"] += usd
    return per_agent, per_day


def _quota_map(conn) -> dict:
    return {q["agent_id"]: q for q in conn.execute(
        "SELECT agent_id, monthly_usd_limit, monthly_token_limit, alert_pct "
        "FROM agent_quotas").fetchall()}


def _pct(usage: dict, q: dict | None) -> float | None:
    """% hạn mức dùng — lấy max giữa % theo USD và % theo token."""

    if not q:
        return None
    pcts = []
    if q.get("monthly_usd_limit"):
        pcts.append(usage["usd"] / float(q["monthly_usd_limit"]) * 100)
    if q.get("monthly_token_limit"):
        pcts.append(usage["tokens"] / float(q["monthly_token_limit"]) * 100)
    return round(max(pcts), 1) if pcts else None


@app.get("/v1/cost/summary")
def cost_summary(period: str | None = None) -> dict:
    """Tổng hợp chi phí ước tính + mức dùng theo agent cho một tháng."""

    _ensure_schema()
    start, end, pkey = _month_bounds(period)
    with _db() as conn:
        rows = _cost_rows(conn, start, end)
        per_agent, per_day = _aggregate_cost(rows)
        quotas = _quota_map(conn)
        names = {a["agent_id"]: a for a in conn.execute(
            "SELECT agent_id, name, owner, status FROM agents").fetchall()}
    agents = []
    for aid, u in per_agent.items():
        q = quotas.get(aid)
        meta = names.get(aid, {})
        agents.append({
            **u,
            "usd": round(u["usd"], 4),
            "name": meta.get("name"), "owner": meta.get("owner"),
            "status": meta.get("status"),
            "quota_usd": float(q["monthly_usd_limit"]) if q and q.get("monthly_usd_limit") else None,
            "quota_tokens": int(q["monthly_token_limit"]) if q and q.get("monthly_token_limit") else None,
            "alert_pct": q.get("alert_pct") if q else None,
            "pct": _pct(u, q),
        })
    agents.sort(key=lambda x: x["usd"], reverse=True)
    return {
        "period": pkey,
        "total_usd": round(sum(a["usd"] for a in agents), 4),
        "total_tokens": sum(a["tokens"] for a in agents),
        "total_runs": sum(a["runs"] for a in agents),
        "agents": agents,
    }


@app.get("/v1/cost/timeseries")
def cost_timeseries(period: str | None = None) -> dict:
    """Chuỗi ngày (tokens + USD ước tính) trong tháng — cho biểu đồ."""

    _ensure_schema()
    start, end, pkey = _month_bounds(period)
    with _db() as conn:
        rows = _cost_rows(conn, start, end)
    _, per_day = _aggregate_cost(rows)
    series = [{"day": k, "tokens": v["tokens"], "usd": round(v["usd"], 4)}
              for k, v in sorted(per_day.items())]
    return {"period": pkey, "series": series}


@app.get("/v1/quotas")
def list_quotas() -> list[dict]:
    _ensure_schema()
    with _db() as conn:
        return conn.execute(
            "SELECT agent_id, monthly_usd_limit, monthly_token_limit, alert_pct, "
            "updated_at FROM agent_quotas ORDER BY agent_id").fetchall()


@app.post("/v1/quotas")
def set_quota(body: dict, authorization: str = Header(default=""),
              x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    """Đặt/sửa hạn mức tháng cho agent (USD ước tính và/hoặc token)."""

    _require_admin(authorization)
    _ensure_schema()
    aid = body.get("agent_id")
    if not aid:
        raise HTTPException(status_code=422, detail="agent_id required")

    def _num(v):
        return None if v in (None, "", "null") else v

    with _db() as conn:
        conn.execute(
            """
            INSERT INTO agent_quotas (agent_id, monthly_usd_limit, monthly_token_limit,
                                      alert_pct, updated_at)
            VALUES (%s,%s,%s,%s, now())
            ON CONFLICT (agent_id) DO UPDATE SET
              monthly_usd_limit=EXCLUDED.monthly_usd_limit,
              monthly_token_limit=EXCLUDED.monthly_token_limit,
              alert_pct=EXCLUDED.alert_pct, updated_at=now()
            """,
            (aid, _num(body.get("monthly_usd_limit")), _num(body.get("monthly_token_limit")),
             int(body.get("alert_pct") or DEFAULT_ALERT_PCT)),
        )
        _audit(conn, x_actor or "admin", "set_quota", "agent", aid,
               {"usd": body.get("monthly_usd_limit"), "tokens": body.get("monthly_token_limit"),
                "alert_pct": body.get("alert_pct")})
        conn.commit()
    return {"agent_id": aid, "ok": True}


def _check_quota_alerts(conn) -> list[dict]:
    """So mức dùng tháng hiện tại với hạn mức; gửi Lark khi vượt ngưỡng (1 lần/mức).

    Mức cảnh báo: ngưỡng `alert_pct` của agent (mặc định 80%) và 100%.
    Ghi vào quota_alerts (UNIQUE agent+period+level) → không spam lặp lại.
    """

    start, end, pkey = _month_bounds(None)
    rows = _cost_rows(conn, start, end)
    per_agent, _ = _aggregate_cost(rows)
    quotas = _quota_map(conn)
    owners = {a["agent_id"]: a for a in conn.execute(
        "SELECT agent_id, name, owner FROM agents").fetchall()}
    fired = []
    for aid, q in quotas.items():
        u = per_agent.get(aid, {"usd": 0.0, "tokens": 0})
        pct = _pct(u, q)
        if pct is None:
            continue
        thresh = int(q.get("alert_pct") or DEFAULT_ALERT_PCT)
        for level in sorted({thresh, 100}):
            if pct < level:
                continue
            # đã cảnh báo mức này trong tháng chưa?
            dup = conn.execute(
                "SELECT 1 FROM quota_alerts WHERE agent_id=%s AND period=%s AND level=%s",
                (aid, pkey, level)).fetchone()
            if dup:
                continue
            meta = owners.get(aid, {})
            name = meta.get("name") or aid
            msg = (f"⚠️ Hạn mức agent [{name}] tháng {pkey}: đã dùng ~{pct:.0f}% "
                   f"(≈${u['usd']:.2f}, {u['tokens']:,} token). "
                   f"Ngưỡng {level}%. Kiểm tra usage/điều chỉnh hạn mức.")
            conn.execute(
                "INSERT INTO quota_alerts (agent_id, period, level, usd, tokens) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (aid, pkey, level, round(u["usd"], 4), u["tokens"]))
            _notify(conn, meta.get("owner"), "quota", aid, msg)
            fired.append({"agent_id": aid, "level": level, "pct": pct,
                          "usd": round(u["usd"], 2), "notified": meta.get("owner")})
    conn.commit()
    return fired


@app.post("/v1/cost/check-alerts")
def check_alerts(authorization: str = Header(default="")) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        return {"fired": _check_quota_alerts(conn)}


def _alert_loop() -> None:
    """Daemon: định kỳ quét cảnh báo hạn mức (best-effort)."""

    while True:
        time.sleep(max(60, ALERT_INTERVAL))
        try:
            _ensure_schema()
            with _db() as conn:
                _check_quota_alerts(conn)
                _check_health_alerts(conn)
        except Exception:
            pass


@app.on_event("startup")
def _start_alert_daemon() -> None:
    if ALERT_INTERVAL > 0:
        threading.Thread(target=_alert_loop, daemon=True).start()


# ============================ A1: Audit log ============================

@app.get("/v1/audit")
def list_audit(action: str | None = None, target_id: str | None = None,
               actor: str | None = None, limit: int = 100) -> list[dict]:
    """Nhật ký thao tác toàn platform (ai làm gì, khi nào) — cho quản trị/tuân thủ."""

    _ensure_schema()
    sql = "SELECT actor, action, target_type, target_id, detail, at FROM audit_log"
    where, args = [], []
    if action:
        where.append("action=%s"); args.append(action)
    if target_id:
        where.append("target_id=%s"); args.append(target_id)
    if actor:
        where.append("actor=%s"); args.append(actor)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY at DESC LIMIT %s"
    args.append(min(int(limit), 500))
    with _db() as conn:
        return conn.execute(sql, args).fetchall()


# ============================ A3: Health monitor ============================

def _health_rows(conn) -> list[dict]:
    """Mỗi agent: status + lần trace gần nhất + số giờ im lặng + cờ health."""

    last = {r["agent_id"]: r for r in conn.execute(
        "SELECT agent_id, max(received_at) AS last_trace, count(*) AS runs "
        "FROM agent_traces GROUP BY agent_id").fetchall()}
    agents = conn.execute(
        "SELECT agent_id, name, owner, status FROM agents ORDER BY agent_id").fetchall()
    out = []
    now = datetime.now(timezone.utc)
    for a in agents:
        lt = last.get(a["agent_id"], {})
        last_trace = lt.get("last_trace")
        hours = None
        if last_trace:
            hours = round((now - last_trace).total_seconds() / 3600, 1)
        health = "ok"
        if a["status"] == "active":
            if last_trace is None:
                health = "never"
            elif hours is not None and hours >= HEALTH_SILENT_HOURS:
                health = "silent"
        out.append({**a, "last_trace": last_trace.isoformat() if last_trace else None,
                    "runs": lt.get("runs", 0), "silent_hours": hours, "health": health})
    return out


@app.get("/v1/health/agents")
def health_agents() -> dict:
    _ensure_schema()
    with _db() as conn:
        rows = _health_rows(conn)
    return {"threshold_hours": HEALTH_SILENT_HOURS, "agents": rows,
            "n_problem": sum(1 for r in rows if r["health"] != "ok")}


def _check_health_alerts(conn) -> list[dict]:
    """Agent active mà im lặng/never → cảnh báo Lark (1 lần/agent/ngày)."""

    _, _, _ = _month_bounds(None)
    day = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")
    fired = []
    for r in _health_rows(conn):
        if r["health"] not in ("silent", "never"):
            continue
        dup = conn.execute(
            "SELECT 1 FROM agent_health_alerts WHERE agent_id=%s AND kind=%s AND day=%s",
            (r["agent_id"], r["health"], day)).fetchone()
        if dup:
            continue
        name = r["name"] or r["agent_id"]
        if r["health"] == "never":
            detail = "chưa từng gửi trace nào dù đang active"
        else:
            detail = f"im lặng ~{r['silent_hours']}h (ngưỡng {HEALTH_SILENT_HOURS}h)"
        conn.execute(
            "INSERT INTO agent_health_alerts (agent_id, kind, day, detail) "
            "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (r["agent_id"], r["health"], day, detail))
        _notify(conn, r["owner"], "health", r["agent_id"],
                f"🩺 Agent [{name}] có vấn đề sức khoẻ: {detail}. Kiểm tra agent còn chạy không.")
        fired.append({"agent_id": r["agent_id"], "kind": r["health"], "detail": detail})
    conn.commit()
    return fired


@app.post("/v1/health/check-alerts")
def health_check_alerts(authorization: str = Header(default="")) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        return {"fired": _check_health_alerts(conn)}


# ============================ A4: Golden set + regression ============================

def _judge_llm(prompt: str, expected: str, rubric: str, response: str) -> tuple[bool, str]:
    """Chấm chủ quan qua LLM (tùy chọn). Trả (pass, note). Tắt/nghẽn → fallback contains."""

    if not JUDGE_URL:
        return ((expected or "").lower() in (response or "").lower(),
                "fallback contains (JUDGE_URL chưa cấu hình)")
    try:
        sys = ("Bạn là giám khảo chấm câu trả lời. Chỉ trả JSON "
               '{"pass": true/false, "reason": "..."} — không thêm gì khác.')
        user = (f"Yêu cầu: {prompt}\nĐáp án mong đợi/tiêu chí: {expected}\n"
                f"Rubric: {rubric or '(không)'}\nCâu trả lời của agent: {response}\n"
                "Câu trả lời có ĐẠT không?")
        r = requests.post(
            f"{JUDGE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {JUDGE_TOKEN}", "Content-Type": "application/json"},
            json={"model": JUDGE_MODEL, "temperature": 0,
                  "messages": [{"role": "system", "content": sys},
                               {"role": "user", "content": user}]},
            timeout=30)
        txt = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", txt, re.S)
        j = json.loads(m.group(0)) if m else {}
        return bool(j.get("pass")), str(j.get("reason", ""))[:300]
    except Exception as exc:
        return ((expected or "").lower() in (response or "").lower(),
                f"fallback contains (judge lỗi: {str(exc)[:80]})")


@app.post("/v1/golden-cases")
def add_golden_case(body: dict, authorization: str = Header(default=""),
                    x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    """Thêm/sửa ca golden (bộ chuẩn để test hồi quy)."""

    _require_admin(authorization)
    _ensure_schema()
    cid = body.get("case_id") or ("g_" + secrets.token_hex(6))
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO golden_cases (case_id, skill, prompt, expected, atype, tol,
                                      weight, rubric, active, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (case_id) DO UPDATE SET skill=EXCLUDED.skill, prompt=EXCLUDED.prompt,
              expected=EXCLUDED.expected, atype=EXCLUDED.atype, tol=EXCLUDED.tol,
              weight=EXCLUDED.weight, rubric=EXCLUDED.rubric, active=EXCLUDED.active
            """,
            (cid, body.get("skill"), body.get("prompt"), body.get("expected"),
             body.get("atype", "contains"), float(body.get("tol", 0) or 0),
             float(body.get("weight", 1) or 1), body.get("rubric"),
             bool(body.get("active", True)), body.get("created_by", "admin")),
        )
        _audit(conn, x_actor or body.get("created_by", "admin"), "golden_case", "golden", cid,
               {"skill": body.get("skill"), "atype": body.get("atype")})
        conn.commit()
    return {"case_id": cid, "ok": True}


@app.get("/v1/golden-cases")
def list_golden_cases(skill: str | None = None) -> list[dict]:
    _ensure_schema()
    sql = "SELECT case_id, skill, prompt, expected, atype, tol, weight, rubric, active FROM golden_cases"
    args: list = []
    if skill:
        sql += " WHERE skill=%s"; args.append(skill)
    sql += " ORDER BY created_at DESC"
    with _db() as conn:
        return conn.execute(sql, args).fetchall()


@app.post("/v1/regression/run")
def run_regression(body: dict, authorization: str = Header(default=""),
                   x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    """Chạy hồi quy trên golden set.

    body: { target_id, target_type, skill?, threshold?, answers: [{case_id, response}] }
    Chấm deterministic (exact/regex/numeric/contains) + llm_judge (nếu cấu hình).
    """

    _require_admin(authorization)
    _ensure_schema()
    answers = {a.get("case_id"): a.get("response", "") for a in (body.get("answers") or [])}
    skill = body.get("skill")
    threshold = float(body.get("threshold", 0.8) or 0.8)
    with _db() as conn:
        sql = "SELECT * FROM golden_cases WHERE active=true"
        args: list = []
        if skill:
            sql += " AND skill=%s"; args.append(skill)
        cases = conn.execute(sql, args).fetchall()
        if not cases:
            raise HTTPException(status_code=422, detail="không có golden case active")
        total_w = sum(float(c["weight"] or 1) for c in cases) or 1.0
        got, detail = 0.0, []
        for c in cases:
            resp = answers.get(c["case_id"], "")
            if c["atype"] == "llm_judge":
                ok, note = _judge_llm(c["prompt"], c["expected"], c["rubric"], resp)
            else:
                ok = _assert_answer(c["expected"], resp, c["atype"], float(c["tol"] or 0))
                note = ""
            w = float(c["weight"] or 1)
            if ok:
                got += w
            detail.append({"case_id": c["case_id"], "skill": c["skill"], "ok": ok,
                           "atype": c["atype"], "note": note})
        score = round(got / total_w, 4)
        passed = score >= threshold
        n_pass = sum(1 for d in detail if d["ok"])
        rid = "r_" + secrets.token_hex(6)
        conn.execute(
            """
            INSERT INTO regression_runs (run_id, target_type, target_id, skill, score,
                                         passed, n_total, n_pass, threshold, detail, run_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (rid, body.get("target_type", "agent"), body.get("target_id"), skill,
             score, passed, len(cases), n_pass, threshold, Json(detail),
             body.get("run_by", "admin")),
        )
        _audit(conn, x_actor or body.get("run_by", "admin"), "regression_run", "regression", rid,
               {"target_id": body.get("target_id"), "score": score, "passed": passed})
        conn.commit()
    return {"run_id": rid, "score": score, "passed": passed,
            "n_total": len(cases), "n_pass": n_pass, "threshold": threshold, "detail": detail}


@app.get("/v1/regression/runs")
def list_regression_runs(target_id: str | None = None, limit: int = 50) -> list[dict]:
    _ensure_schema()
    sql = ("SELECT run_id, target_type, target_id, skill, score, passed, n_total, "
           "n_pass, threshold, run_by, at FROM regression_runs")
    args: list = []
    if target_id:
        sql += " WHERE target_id=%s"; args.append(target_id)
    sql += " ORDER BY at DESC LIMIT %s"
    args.append(min(int(limit), 200))
    with _db() as conn:
        return conn.execute(sql, args).fetchall()


# ============================ A5: Extract PDF/Word + dọn agent ============================

@app.post("/v1/extract")
async def extract_document(file: UploadFile = File(...),
                           authorization: str = Header(default="")) -> dict:
    """Trích text từ PDF/DOCX/TXT server-side (cho import shared beliefs)."""

    _require_admin(authorization)
    data = await file.read()
    name = (file.filename or "").lower()
    text = ""
    try:
        if name.endswith(".pdf"):
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        elif name.endswith(".docx"):
            import io
            import docx
            d = docx.Document(io.BytesIO(data))
            text = "\n".join(p.text for p in d.paragraphs)
        else:  # txt/md
            text = data.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"không trích được text: {str(exc)[:120]}")
    return {"filename": file.filename, "chars": len(text), "text": text[:200_000]}


@app.post("/v1/agents/{agent_id}/delete")
def delete_agent(agent_id: str, body: dict | None = None,
                 authorization: str = Header(default=""),
                 x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    """Gỡ agent khỏi REGISTRY (chỉ metadata). KHÔNG xoá trace/schema/dữ liệu.

    Dùng để dọn agent demo/test. Trace lịch sử vẫn còn để truy vết.
    """

    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        row = conn.execute("SELECT name, status FROM agents WHERE agent_id=%s",
                           (agent_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        conn.execute("DELETE FROM agents WHERE agent_id=%s", (agent_id,))
        conn.execute("DELETE FROM agent_quotas WHERE agent_id=%s", (agent_id,))
        _audit(conn, x_actor or "admin", "delete_agent", "agent", agent_id,
               {"name": row.get("name"), "note": "registry only; traces kept"})
        conn.commit()
    return {"agent_id": agent_id, "deleted_from_registry": True,
            "data_kept": "traces + schema giữ nguyên"}


# ============================ Item 3: Policies (control-plane write) ============================
# Admin GHI rule; COLLECTOR đọc & enforce runtime tại /v1/policy/check. Rỗng → allow.

@app.post("/v1/policies")
def upsert_policy(body: dict, authorization: str = Header(default=""),
                  x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    """Thêm/sửa policy chặn runtime. rule ví dụ: {\"tools\":[\"delete_file\"]} hoặc
    {\"patterns\":[\"(?i)bỏ qua chỉ dẫn\"]}. phase: pre_tool|pre_prompt|*."""

    _require_admin(authorization)
    _ensure_schema()
    pid = body.get("policy_id") or ("pol_" + secrets.token_hex(5))
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO policies (policy_id, agent_id, phase, effect, rule, reason, active)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (policy_id) DO UPDATE SET agent_id=EXCLUDED.agent_id,
              phase=EXCLUDED.phase, effect=EXCLUDED.effect, rule=EXCLUDED.rule,
              reason=EXCLUDED.reason, active=EXCLUDED.active
            """,
            (pid, body.get("agent_id"), body.get("phase", "*"),
             body.get("effect", "deny"), Json(body.get("rule") or {}),
             body.get("reason"), bool(body.get("active", True))),
        )
        _audit(conn, x_actor or "admin", "upsert_policy", "policy", pid,
               {"phase": body.get("phase"), "effect": body.get("effect")})
        conn.commit()
    return {"policy_id": pid, "ok": True}


@app.get("/v1/policies")
def list_policies() -> list[dict]:
    _ensure_schema()
    with _db() as conn:
        return conn.execute(
            "SELECT policy_id, agent_id, phase, effect, rule, reason, active, created_at "
            "FROM policies ORDER BY created_at DESC").fetchall()


@app.post("/v1/policies/{policy_id}/delete")
def delete_policy(policy_id: str, authorization: str = Header(default=""),
                  x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        conn.execute("DELETE FROM policies WHERE policy_id=%s", (policy_id,))
        _audit(conn, x_actor or "admin", "delete_policy", "policy", policy_id, {})
        conn.commit()
    return {"policy_id": policy_id, "deleted": True}


# ============================ Item 5: Retention config (chưa purge) ============================

@app.get("/v1/retention")
def list_retention() -> list[dict]:
    _ensure_schema()
    with _db() as conn:
        return conn.execute(
            "SELECT scope, ttl_days, action, enabled, updated_at FROM retention_config "
            "ORDER BY scope").fetchall()


@app.post("/v1/retention")
def set_retention(body: dict, authorization: str = Header(default=""),
                  x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    """Khai báo TTL cho một loại dữ liệu (traces|audit|notifications). CHƯA chạy purge —
    job dọn sẽ đọc bảng này khi bật (enabled=true) ở bước sau."""

    _require_admin(authorization)
    _ensure_schema()
    scope = body.get("scope")
    if not scope:
        raise HTTPException(status_code=422, detail="scope required")
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO retention_config (scope, ttl_days, action, enabled, updated_at)
            VALUES (%s,%s,%s,%s, now())
            ON CONFLICT (scope) DO UPDATE SET ttl_days=EXCLUDED.ttl_days,
              action=EXCLUDED.action, enabled=EXCLUDED.enabled, updated_at=now()
            """,
            (scope, body.get("ttl_days"), body.get("action", "delete"),
             bool(body.get("enabled", False))),
        )
        _audit(conn, x_actor or "admin", "set_retention", "retention", scope,
               {"ttl_days": body.get("ttl_days"), "enabled": body.get("enabled")})
        conn.commit()
    return {"scope": scope, "ok": True}
