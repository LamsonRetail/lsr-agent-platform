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
import hmac
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
from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
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

# ĐA APP: mỗi routing_binding có thể gắn một app Lark riêng (vd Sawadee HAPAS cho squad TH).
# Trả lời job PHẢI đi bằng đúng bot đã nhận tin — bot khác không ở trong nhóm đó.
# Secret chỉ nằm trong .env trên VM; compose ghép thành LARK_EXTRA_APPS='{"cli_x":"secret"}'.
_LARK_APPS: dict = {}
for _aid, _sec in (
    (os.environ.get("LARK_NOTIFY_APP_ID", ""), os.environ.get("LARK_NOTIFY_APP_SECRET", "")),
    (os.environ.get("MINH_ANH_LARK_APP_ID", ""), os.environ.get("MINH_ANH_LARK_APP_SECRET", "")),
):
    if _aid and _sec:
        _LARK_APPS.setdefault(_aid, _sec)
try:
    for _aid, _sec in json.loads(os.environ.get("LARK_EXTRA_APPS") or "{}").items():
        if _aid and _sec:
            _LARK_APPS[_aid] = _sec
except Exception:
    pass
LARK_DOMAIN = os.environ.get("LARK_DOMAIN", "https://open.larksuite.com").rstrip("/")

# --- C8: khoá mã hoá token người dùng (at-rest). Chỉ nằm trong .env trên VM. ---
# Không có khoá = broker TẮT HẲN, chứ không lưu token dạng rõ. Thà thiếu tính năng
# còn hơn để token của một con người nằm trần trong Postgres.
LARK_USER_TOKEN_KEY = os.environ.get("LARK_USER_TOKEN_KEY", "")
# Cảnh báo trước khi refresh_token chết (Lark refresh sống ~30 ngày, hết là phải
# xin người authorize lại — AG-LEGAL từng chết âm thầm 1 tháng vì chuyện này).
LARK_USER_REFRESH_WARN_DAYS = int(os.environ.get("LARK_USER_REFRESH_WARN_DAYS", "7"))


def _user_token_cipher():
    """AES-GCM từ LARK_USER_TOKEN_KEY (băm SHA-256 → 32 byte). None nếu chưa cấu hình."""
    if not LARK_USER_TOKEN_KEY:
        return None
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore
    return AESGCM(hashlib.sha256(LARK_USER_TOKEN_KEY.encode()).digest())


def _enc_token(plain: str) -> bytes:
    c = _user_token_cipher()
    if c is None:
        raise HTTPException(status_code=503,
                            detail="thiếu LARK_USER_TOKEN_KEY — broker user token đang tắt")
    nonce = os.urandom(12)
    return nonce + c.encrypt(nonce, (plain or "").encode(), None)


def _dec_token(blob) -> str:
    c = _user_token_cipher()
    if c is None:
        raise HTTPException(status_code=503, detail="thiếu LARK_USER_TOKEN_KEY")
    raw = bytes(blob)
    return c.decrypt(raw[:12], raw[12:], None).decode()

LARK_NOTIFY = os.environ.get("LARK_NOTIFY_ENABLED", "true").lower() != "false"
# Nhóm nhận thông báo khi CHƯA có scope contact:user.id:readonly (không tra được email→open_id)
LARK_NOTIFY_CHAT_ID = os.environ.get("LARK_NOTIFY_CHAT_ID", "")

# --- P10: đăng nhập console qua Lark OAuth + quyền mặc định -----------------
# CONSOLE_BASE_URL: gốc của console web (Lark redirect người dùng về đây sau khi cho phép).
CONSOLE_BASE_URL = os.environ.get("CONSOLE_BASE_URL", "").rstrip("/")
# Kiểm tra org: tenant_key (chặt nhất, lấy sau lần đăng nhập admin đầu) và/hoặc domain email.
LARK_TENANT_KEY = os.environ.get("LARK_TENANT_KEY", "")
ALLOWED_LOGIN_DOMAINS = [d.strip().lower() for d in
                         os.environ.get("ALLOWED_LOGIN_DOMAINS", "hapas.vn").split(",") if d.strip()]
# Mặc định MỌI tài khoản đã đăng nhập có quyền 'user' trên mọi agent (xem được, không sửa).
DEFAULT_LOGIN_ROLE = os.environ.get("DEFAULT_LOGIN_ROLE", "user")

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


# ==================== P8: tài khoản console + RBAC ====================
# Mật khẩu băm bằng PBKDF2 của stdlib (không thêm dependency).
_PW_ITER = 200_000
_ROLE_RANK = {"user": 1, "moderator": 2, "admin": 3}
SESSION_HOURS = int(os.environ.get("WEB_SESSION_HOURS", "12"))
LOGIN_MAX_FAIL = int(os.environ.get("LOGIN_MAX_FAIL", "5"))
LOGIN_LOCK_MINUTES = int(os.environ.get("LOGIN_LOCK_MINUTES", "15"))


def _hash_pw(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PW_ITER)
    return f"pbkdf2${_PW_ITER}${salt}${dk.hex()}"


def _verify_pw(password: str, stored: str) -> bool:
    try:
        algo, iters, salt, want = (stored or "").split("$")
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return secrets.compare_digest(dk.hex(), want)
    except Exception:
        return False


def _bearer(authorization: str) -> str:
    return authorization[7:] if (authorization or "").startswith("Bearer ") else ""


def _session_email(conn, token: str) -> str | None:
    if not token:
        return None
    h = hashlib.sha256(token.encode()).hexdigest()
    row = conn.execute(
        "SELECT s.email FROM web_sessions s JOIN accounts a ON a.email = s.email "
        "WHERE s.token_hash=%s AND s.revoked_at IS NULL AND s.expires_at > now() "
        "  AND a.status='active'", (h,)).fetchone()
    return row["email"] if row else None


def _effective_role(conn, email: str, agent_id: str | None = None) -> str | None:
    """Quyền hiệu lực = CAO HƠN giữa quyền platform và quyền trên chính agent đó.

    P10: không có binding nào → rơi về DEFAULT_LOGIN_ROLE ('user') — mọi người
    đăng nhập đều XEM được mọi agent; sửa/duyệt vẫn phải được cấp quyền tường minh.
    """
    rows = conn.execute(
        "SELECT scope_type, scope_id, role FROM role_bindings WHERE email=%s", (email,)).fetchall()
    best = None
    for r in rows:
        if r["scope_type"] == "platform" or (agent_id and r["scope_type"] == "agent"
                                             and r["scope_id"] == agent_id):
            if best is None or _ROLE_RANK.get(r["role"], 0) > _ROLE_RANK.get(best, 0):
                best = r["role"]
    if best is None and DEFAULT_LOGIN_ROLE in _ROLE_RANK:
        best = DEFAULT_LOGIN_ROLE
    return best


def _pat_email(conn, token: str) -> str | None:
    """Token cá nhân (CLI/Claude Code) → email chủ token. Cập nhật last_used_at."""
    if not token.startswith("lsr_pat_"):
        return None
    h = hashlib.sha256(token.encode()).hexdigest()
    row = conn.execute(
        "UPDATE personal_tokens p SET last_used_at=now() "
        "FROM accounts a WHERE p.token_hash=%s AND a.email=p.email AND a.status='active' "
        "  AND p.revoked_at IS NULL AND p.expires_at > now() RETURNING p.email", (h,)).fetchone()
    if row:
        conn.commit()
        return row["email"]
    return None


def _principal(authorization: str, agent_id: str | None = None) -> dict:
    """Nhận diện người/dịch vụ đang gọi.

    - admin token (service-to-service: gateway, bot, CI) → quyền admin, actor='service'
    - session token console           → quyền theo role_bindings, actor=email
    - token cá nhân `lsr_pat_` (CLI)  → CÙNG quyền như khi đăng nhập console
    """
    tok = _bearer(authorization)
    if not tok:
        return {"kind": "none", "actor": None, "role": None}
    if ADMIN_TOKEN and tok == ADMIN_TOKEN:
        return {"kind": "admin_token", "actor": "service", "role": "admin"}
    try:
        with _db() as conn:
            email = _session_email(conn, tok) or _pat_email(conn, tok)
            if email:
                return {"kind": "pat" if tok.startswith("lsr_pat_") else "session",
                        "actor": email, "role": _effective_role(conn, email, agent_id)}
    except Exception:
        pass
    return {"kind": "unknown", "actor": None, "role": None}


def _require_role(authorization: str, need: str, agent_id: str | None = None) -> dict:
    """Chặn ở API — KHÔNG dựa vào việc UI có ẩn nút hay không."""
    p = _principal(authorization, agent_id)
    # Phân biệt rõ: CHƯA đăng nhập → 401 (console đưa về trang login);
    # ĐÃ đăng nhập nhưng không đủ quyền trên phạm vi này → 403 (không đá người dùng ra).
    # "pat" = token cá nhân CLI (lsr-login.sh) — cùng danh tính, cùng RBAC như session.
    if p["kind"] not in ("session", "pat", "admin_token"):
        raise HTTPException(status_code=401, detail="cần đăng nhập console")
    if not p["role"]:
        raise HTTPException(
            status_code=403,
            detail=f"bạn không có quyền trên agent {agent_id}" if agent_id
                   else "tài khoản chưa được cấp vai trò nào")
    if _ROLE_RANK.get(p["role"], 0) < _ROLE_RANK.get(need, 99):
        raise HTTPException(
            status_code=403,
            detail=f"cần quyền '{need}'" + (f" trên agent {agent_id}" if agent_id else "")
                   + f" — bạn đang là '{p['role']}'")
    return p


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
            # P2 Model Auth: cách agent lấy quyền gọi model.
            #  own  = subscription RIÊNG (credential_id) → fallback pool nếu kẹt
            #  pool = dùng pool subscription chung
            #  api  = ưu tiên API key (litellm)  (thường chỉ dùng khi mọi sub cooldown)
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS auth_mode text DEFAULT 'pool'",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS credential_id text",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS model_fallback text",
            # P9: no-code — platform tự chạy agent bằng instruction của version.
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS runtime text DEFAULT 'external'",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS usecase_md text",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS testcases jsonb DEFAULT '[]'::jsonb",
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
        # --- Lark dùng chung: cache token + danh tính (mọi agent xài chung 1 nguồn) ---
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lark_token_cache (
                app_id     text PRIMARY KEY,
                token      text,
                expire_at  timestamptz
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lark_identity_cache (
                email      text PRIMARY KEY,   -- lower-case; khớp cả email lẫn enterprise_email
                open_id    text,
                updated_at timestamptz DEFAULT now()
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
        # ===== Brain v2: tri thức/kỹ năng/chính sách + graph liên kết =====
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS brain_items (
                item_id     text PRIMARY KEY,
                kind        text DEFAULT 'knowledge',   -- knowledge|process|definition|lesson|belief|faq
                title       text,
                content     text,
                domain      text,
                tags        text[] DEFAULT '{}',
                scope       text DEFAULT 'shared',       -- shared|agent
                agent_id    text,                        -- nếu scope=agent
                source_agent text,
                source_team text,
                source_url  text,
                source_ref  text,
                status      text DEFAULT 'pending',      -- draft|pending|approved|rejected|deprecated
                reviewed_by text, review_note text, reviewed_at timestamptz,
                version     int DEFAULT 1,
                created_by  text, created_at timestamptz DEFAULT now(),
                updated_by  text, updated_at timestamptz DEFAULT now(),
                confidence  numeric
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_brain_scope ON brain_items(scope, agent_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_brain_domain ON brain_items(domain)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_brain_status ON brain_items(status)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS brain_skills (
                skill_id    text PRIMARY KEY,
                name        text,
                kind        text DEFAULT 'mcp',          -- mcp|builtin|api
                description text,
                domain      text,
                tags        text[] DEFAULT '{}',
                scope       text DEFAULT 'shared',
                agent_id    text,
                owner       text,
                status      text DEFAULT 'proposed',     -- proposed|active|deprecated
                source_url  text,
                created_at  timestamptz DEFAULT now(),
                updated_at  timestamptz DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS brain_links (
                link_id    text PRIMARY KEY,
                from_id    text, from_type text,          -- kb|skill|policy
                to_id      text, to_type   text,
                rel        text,                          -- relates_to|depends_on|derived_from|supersedes|contradicts|refines|uses_skill|governed_by
                note       text,
                status     text DEFAULT 'suggested',      -- suggested|confirmed
                source_url text,
                created_by text,
                created_at timestamptz DEFAULT now()
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_link_from ON brain_links(from_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_link_to ON brain_links(to_id)")
        # policies: mở rộng cho góc nhìn org (title/mô tả/scope/domain/owner/status)
        for ddl in (
            "ALTER TABLE policies ADD COLUMN IF NOT EXISTS title text",
            "ALTER TABLE policies ADD COLUMN IF NOT EXISTS description text",
            "ALTER TABLE policies ADD COLUMN IF NOT EXISTS scope text DEFAULT 'org'",
            "ALTER TABLE policies ADD COLUMN IF NOT EXISTS domain text",
            "ALTER TABLE policies ADD COLUMN IF NOT EXISTS owner text",
            "ALTER TABLE policies ADD COLUMN IF NOT EXISTS source_url text",
            "ALTER TABLE policies ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now()",
        ):
            conn.execute(ddl)
        # Migrate 1 lần: knowledge_items + shared_beliefs -> brain_items (idempotent)
        conn.execute(
            """
            INSERT INTO brain_items(item_id,kind,title,content,domain,source_team,source_ref,
                                    source_url,status,reviewed_by,review_note,reviewed_at,created_at)
            SELECT item_id,'knowledge',title,md_content,domain,source_team,source_ref,
                   source_url,status,reviewed_by,review_note,reviewed_at,created_at
            FROM knowledge_items ON CONFLICT (item_id) DO NOTHING
            """
        )
        conn.execute(
            """
            INSERT INTO brain_items(item_id,kind,title,content,domain,source_url,status,created_by,created_at)
            SELECT belief_id,'belief',title,statement,domain,source_url,'approved',
                   coalesce(updated_by,'admin'),updated_at
            FROM shared_beliefs ON CONFLICT (item_id) DO NOTHING
            """
        )
        # Migrate skills từ manifest (agents.skills) -> brain_skills
        conn.execute(
            """
            INSERT INTO brain_skills(skill_id,name,kind,scope,status)
            SELECT DISTINCT 'sk-'||s, s, 'mcp','shared','active'
            FROM agents, unnest(coalesce(skills,'{}')) s WHERE s <> ''
            ON CONFLICT (skill_id) DO NOTHING
            """
        )
        # ================= P1: Ingress hợp nhất (routing + queue) =================
        # Bảng định tuyến: 1 dòng = 1 binding nguồn→agent. Thêm agent = thêm 1 dòng.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS routing_binding (
                id         bigserial PRIMARY KEY,
                channel    text NOT NULL,          -- lark | web | a2a | cron | webhook
                app_id     text,                   -- Lark app_id (nếu có)
                chat_id    text,                   -- Lark chat_id / khoá kênh
                agent_id   text NOT NULL REFERENCES agents(agent_id),
                active     boolean DEFAULT true,
                created_by text,
                created_at timestamptz DEFAULT now()
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_routing_lookup "
                     "ON routing_binding(channel, app_id, chat_id) WHERE active")
        # Hàng đợi job — 1 sự kiện = 1 job. Consume bằng FOR UPDATE SKIP LOCKED.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id          bigserial PRIMARY KEY,
                agent_id    text,                  -- NULL = chưa route được (unrouted)
                channel     text,
                session_id  text,                  -- gom nhiều lượt cùng hội thoại
                reply_to    jsonb,                 -- nơi trả lời (chat_id/email/req_id...)
                payload     jsonb,
                status      text DEFAULT 'queued', -- queued|running|done|failed|dlq|rejected|unrouted
                priority    int DEFAULT 5,
                attempts    int DEFAULT 0,
                max_attempts int DEFAULT 5,
                run_after   timestamptz DEFAULT now(),
                locked_by   text,
                locked_at   timestamptz,
                last_error  text,
                created_at  timestamptz DEFAULT now(),
                updated_at  timestamptz DEFAULT now()
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_claim "
                     "ON jobs(agent_id, status, run_after)")
        # Sự kiện trong 1 job — dùng cho streaming (SSE) và trace từng bước.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS job_events (
                id       bigserial PRIMARY KEY,
                job_id   bigint NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                seq      int,
                kind     text,                    -- token|message|status|error|done
                data     jsonb,
                created_at timestamptz DEFAULT now()
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id, seq)")
        # Chống trùng sự kiện (Lark retry cùng event_id). Dọn theo TTL định kỳ.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_dedupe (
                event_id text PRIMARY KEY,
                seen_at  timestamptz DEFAULT now()
            )
            """
        )
        # ================= P2: Model Auth — pool credential (ref, KHÔNG lưu secret) =============
        # secret_ref = đường dẫn file trên VM (/opt/lsr-platform/secrets/<ref>). DB chỉ giữ ref.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS model_credentials (
                id            text PRIMARY KEY,
                kind          text NOT NULL,        -- subscription | api_key
                label         text,
                owner_email   text,
                secret_ref    text NOT NULL,        -- path tương đối trong secrets/
                status        text DEFAULT 'active',-- active | cooldown | disabled
                cooldown_until timestamptz,
                priority      int DEFAULT 100,      -- nhỏ = ưu tiên
                note          text,
                created_at    timestamptz DEFAULT now(),
                updated_at    timestamptz DEFAULT now()
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cred_pick "
                     "ON model_credentials(kind, status, priority)")
        # Token `claude setup-token` sống ~1 năm → theo dõi hạn để cảnh báo trước khi chết.
        conn.execute("ALTER TABLE model_credentials ADD COLUMN IF NOT EXISTS expires_at timestamptz")
        # ================= P3: Agent versions (no-code + canary + rollback) =================
        # Mỗi agent có nhiều version; mỗi môi trường (dev/stg/prod) chỉ 1 version "sống".
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_versions (
                agent_id          text NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
                version           int  NOT NULL,
                instruction_block text,
                skills            jsonb DEFAULT '[]'::jsonb,
                model             text,
                model_fallback    text,
                tool_grants       jsonb DEFAULT '{}'::jsonb,
                publication       text DEFAULT 'draft',   -- draft|dev|stg|prod
                note              text,
                created_by        text,
                created_at        timestamptz DEFAULT now(),
                published_at      timestamptz,
                PRIMARY KEY (agent_id, version)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ver_pub "
                     "ON agent_versions(agent_id, publication)")
        # Publication tách bảng: MỘT version có thể sống ở NHIỀU env cùng lúc
        # (vd v2 đang ở cả stg và prod). Mỗi env chỉ trỏ 1 version → PK (agent_id, env).
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_publications (
                agent_id     text NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
                env          text NOT NULL,          -- dev|stg|prod
                version      int  NOT NULL,
                published_by text,
                published_at timestamptz DEFAULT now(),
                PRIMARY KEY (agent_id, env)
            )
            """
        )
        # Gate eval: gắn regression run với version cụ thể (không mượn kết quả version khác).
        conn.execute("ALTER TABLE regression_runs ADD COLUMN IF NOT EXISTS agent_version int")
        # ================= P4: Session memory + RAG =================
        # State hội thoại nằm ở ĐÂY (không ở model) → mỗi call LLM stateless,
        # đổi credential/model/restart runner giữa chừng vẫn giữ nguyên ngữ cảnh.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id      text PRIMARY KEY,
                agent_id        text NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
                channel         text,
                user_ref        text,              -- open_id/email/user id trên kênh
                rolling_summary text DEFAULT '',   -- tóm tắt các lượt cũ (agent nén)
                turns           jsonb DEFAULT '[]'::jsonb,  -- N lượt gần nhất
                pending_summary jsonb DEFAULT '[]'::jsonb,  -- lượt đã cắt, CHỜ agent nén
                n_turns         int DEFAULT 0,     -- tổng số lượt từ đầu hội thoại
                created_at      timestamptz DEFAULT now(),
                updated_at      timestamptz DEFAULT now()
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent_id, updated_at DESC)")
        conn.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS pending_summary jsonb DEFAULT '[]'::jsonb")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_facts (
                id         bigserial PRIMARY KEY,
                agent_id   text NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
                user_ref   text NOT NULL,
                fact       text NOT NULL,
                source     text,                   -- session_id / ghi chú nguồn
                created_at timestamptz DEFAULT now(),
                updated_at timestamptz DEFAULT now()
            )
            """
        )
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_user_fact "
                     "ON user_facts(agent_id, user_ref, md5(fact))")
        # RAG lexical hybrid: full-text + trigram + bỏ dấu (không cần dịch vụ embedding ngoài).
        for ext in ("pg_trgm", "unaccent"):
            try:
                conn.execute(f"CREATE EXTENSION IF NOT EXISTS {ext}")
            except Exception:
                pass
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_brain_fts ON brain_items "
                         "USING GIN (to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(content,'')))")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_brain_trgm ON brain_items "
                         "USING GIN (lower(coalesce(title,'')) gin_trgm_ops)")
        except Exception:
            pass
        # ================= P5: Connector registry + metering =================
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS connectors (
                connector_id text PRIMARY KEY,
                kind         text,               -- lark|data|web|social|core_system|...
                name         text,
                config_ref   text,               -- tham chiếu cấu hình/secret trên VM
                status       text DEFAULT 'active',
                enforce      boolean DEFAULT true,   -- true = phải có grant mới gọi được
                note         text,
                created_at   timestamptz DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS connector_grants (
                agent_id     text NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
                connector_id text NOT NULL REFERENCES connectors(connector_id) ON DELETE CASCADE,
                scope        text DEFAULT 'use',
                granted_by   text,
                granted_at   timestamptz DEFAULT now(),
                PRIMARY KEY (agent_id, connector_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_usage (
                id           bigserial PRIMARY KEY,
                agent_id     text,
                connector_id text,
                tool         text,
                job_id       bigint,
                run_id       text,
                latency_ms   int,
                ok           boolean DEFAULT true,
                error        text,
                tokens_est   int DEFAULT 0,
                created_at   timestamptz DEFAULT now()
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_agent ON tool_usage(agent_id, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_conn ON tool_usage(connector_id, created_at DESC)")
        # Đăng ký 2 connector đang chạy thật + khung cho các connector sắp làm.
        for cid, kind, name, enforce in (
            ("lark", "lark", "Lark Suite (IM/Doc/Base)", True),
            # C8: hành động dưới danh nghĩa một account người dùng (user token).
            # enforce=True và KHÔNG backfill grant — mode rủi ro cao nhất, phải cấp tay.
            ("lark_user", "lark", "Lark — hành động dưới danh nghĩa user (broker)", True),
            ("telegram", "telegram", "Telegram (bot admin + kênh chat agent)", False),
            ("bigquery", "data", "BigQuery AI_DB", True),
            ("web_search", "web", "Web search/crawl (khung)", True),
            ("social", "social", "TikTok/Meta/IG (khung)", True),
            ("core_system", "core_system", "Sapo/Misa/Vietful (khung)", True),
        ):
            conn.execute(
                "INSERT INTO connectors(connector_id, kind, name, enforce) VALUES (%s,%s,%s,%s) "
                "ON CONFLICT (connector_id) DO NOTHING", (cid, kind, name, enforce))
        # Backfill: agent đang dùng Lark trước khi có registry → cấp grant để KHÔNG gãy.
        conn.execute(
            "INSERT INTO connector_grants(agent_id, connector_id, granted_by) "
            "SELECT agent_id, 'lark', 'migration' FROM agents ON CONFLICT DO NOTHING")
        # ================= P6: Directory + A2A =================
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS a2a_grants (
                caller_id  text NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
                target_id  text NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
                scope      text DEFAULT 'call',
                granted_by text,
                granted_at timestamptz DEFAULT now(),
                PRIMARY KEY (caller_id, target_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS a2a_requests (
                req_id     text PRIMARY KEY,
                caller_id  text,
                target_id  text,
                task       text,
                payload    jsonb,
                job_id     bigint,
                status     text DEFAULT 'pending',  -- pending|done|failed|expired
                result     jsonb,
                hop        int DEFAULT 1,
                created_at timestamptz DEFAULT now(),
                updated_at timestamptz DEFAULT now()
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_a2a_caller ON a2a_requests(caller_id, created_at DESC)")
        # ================= P7: HITL + mart KPI + platform agents =================
        # Platform agent (AG-OPS/AG-EVAL) ĐỀ XUẤT, con người DUYỆT. Không agent nào
        # được tự duyệt việc của chính mình (separation of duty).
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_actions (
                id          bigserial PRIMARY KEY,
                proposed_by text NOT NULL,
                action      text NOT NULL,        -- alert|replay_dlq|deactivate_agent|rollback_version|rotate_credential
                params      jsonb DEFAULT '{}'::jsonb,
                risk        text DEFAULT 'high',  -- low = tự chạy + log; high = chờ người duyệt
                reason      text,
                status      text DEFAULT 'pending', -- pending|approved|rejected|expired|auto
                approver    text,
                result      jsonb,
                reminded    boolean DEFAULT false,
                expires_at  timestamptz DEFAULT now() + interval '24 hours',
                created_at  timestamptz DEFAULT now(),
                decided_at  timestamptz
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_actions_status ON pending_actions(status, expires_at)")
        # Admin nhận thông báo/duyệt việc từ platform agent (Lark DM và/hoặc Telegram).
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS platform_admins (
                email            text PRIMARY KEY,
                name             text,
                role             text DEFAULT 'admin',
                lark_open_id     text,
                telegram_chat_id text,
                active           boolean DEFAULT true,
                linked_at        timestamptz,
                created_at       timestamptz DEFAULT now()
            )
            """
        )
        for em, nm, ro in (("thint@hapas.vn", "Nguyễn Trần Thi - BOD", "bod"),
                           ("thienlq@hapas.vn", "Lê Quý Thiện", "admin")):
            conn.execute(
                "INSERT INTO platform_admins(email, name, role) VALUES (%s,%s,%s) "
                "ON CONFLICT (email) DO UPDATE SET name=EXCLUDED.name, role=EXCLUDED.role",
                (em, nm, ro))
        # ============ P8: tài khoản console + phân quyền (platform & theo agent) ============
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                email          text PRIMARY KEY,
                name           text,
                password_hash  text,
                must_change_pw boolean DEFAULT true,
                status         text DEFAULT 'active',   -- active | disabled
                telegram_chat_id text,
                last_login_at  timestamptz,
                created_by     text,
                created_at     timestamptz DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS role_bindings (
                id         bigserial PRIMARY KEY,
                email      text NOT NULL REFERENCES accounts(email) ON DELETE CASCADE,
                scope_type text NOT NULL,          -- platform | agent
                scope_id   text NOT NULL DEFAULT '*',
                role       text NOT NULL,          -- admin | moderator | user
                granted_by text,
                granted_at timestamptz DEFAULT now(),
                UNIQUE (email, scope_type, scope_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS web_sessions (
                token_hash text PRIMARY KEY,
                email      text NOT NULL,
                created_at timestamptz DEFAULT now(),
                expires_at timestamptz NOT NULL,
                ip         text,
                user_agent text,
                revoked_at timestamptz
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sess_email ON web_sessions(email)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS login_attempts (
                id    bigserial PRIMARY KEY,
                email text, ip text, ok boolean, at timestamptz DEFAULT now()
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_login_recent ON login_attempts(email, at DESC)")
        # P10: đăng nhập qua Lark + yêu cầu phân quyền per-agent (admin duyệt).
        conn.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS lark_open_id text")
        conn.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS auth_via text DEFAULT 'password'")
        conn.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS lark_bot_name text")
        # Master data năng lực agent: agent khác đọc qua /v1/self/directory để biết
        # AI làm được GÌ và GỌI THẾ NÀO trước khi A2A.
        conn.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS capabilities jsonb")
        conn.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS usage_guide text")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS role_requests (
                id          bigserial PRIMARY KEY,
                email       text NOT NULL REFERENCES accounts(email) ON DELETE CASCADE,
                scope_type  text NOT NULL DEFAULT 'agent',   -- agent | platform
                scope_id    text NOT NULL,
                role        text NOT NULL,                   -- moderator | admin
                reason      text,
                status      text DEFAULT 'pending',          -- pending | approved | rejected
                decided_by  text,
                decided_at  timestamptz,
                decide_note text,
                created_at  timestamptz DEFAULT now()
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rolereq_status ON role_requests(status, created_at DESC)")
        # P11: token CÁ NHÂN cho CLI/Claude Code (thay enroll token dùng chung) +
        # device-login (như `gh auth login`): CLI không phải dán secret nào.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS personal_tokens (
                token_hash   text PRIMARY KEY,
                email        text NOT NULL REFERENCES accounts(email) ON DELETE CASCADE,
                label        text,
                created_at   timestamptz DEFAULT now(),
                expires_at   timestamptz NOT NULL,
                last_used_at timestamptz,
                revoked_at   timestamptz
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pat_email ON personal_tokens(email)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS device_codes (
                device_code text PRIMARY KEY,
                user_code   text UNIQUE NOT NULL,
                label       text,
                status      text DEFAULT 'pending',   -- pending | approved | denied
                email       text,                     -- người duyệt (chủ token)
                token_once  text,                     -- PAT trả 1 lần cho CLI rồi xoá
                created_at  timestamptz DEFAULT now(),
                expires_at  timestamptz NOT NULL
            )
            """
        )
        # P9: token NGẮN HẠN để nocode_runtime hành động NHÂN DANH agent no-code
        # (khoá gốc của agent chỉ lưu hash nên không lấy lại được).
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_runtime_tokens (
                token_hash text PRIMARY KEY,
                agent_id   text NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
                expires_at timestamptz NOT NULL,
                created_at timestamptz DEFAULT now()
            )
            """
        )
        # Seed 2 admin đầu tiên — mật khẩu tạm in ra LOG của platform_api (không vào git/DB rõ).
        for em, nm in (("thint@hapas.vn", "Nguyễn Trần Thi - BOD"),
                       ("thienlq@hapas.vn", "Lê Quý Thiện")):
            exists = conn.execute("SELECT 1 FROM accounts WHERE email=%s", (em,)).fetchone()
            if not exists:
                tmp = secrets.token_urlsafe(12)
                conn.execute(
                    "INSERT INTO accounts(email, name, password_hash, must_change_pw, created_by) "
                    "VALUES (%s,%s,%s,true,'seed')", (em, nm, _hash_pw(tmp)))
                print(f"[LSR-SEED] tài khoản console {em} — mật khẩu tạm: {tmp} "
                      f"(đổi ngay lần đăng nhập đầu)", flush=True)
            conn.execute(
                "INSERT INTO role_bindings(email, scope_type, scope_id, role, granted_by) "
                "VALUES (%s,'platform','*','admin','seed') ON CONFLICT DO NOTHING", (em,))
        conn.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS is_platform boolean DEFAULT false")
        # Mart: rollup ngày × agent × kênh — nguồn cho KPI/chi phí/chất lượng.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mart_daily (
                day         date NOT NULL,
                agent_id    text NOT NULL,
                channel     text NOT NULL DEFAULT '-',
                version     int,
                runs        int DEFAULT 0,
                tokens_in   bigint DEFAULT 0,
                tokens_out  bigint DEFAULT 0,
                cost_usd    numeric(12,4) DEFAULT 0,
                errors      int DEFAULT 0,
                tool_calls  int DEFAULT 0,
                a2a_out     int DEFAULT 0,      -- lượt agent này GỌI agent khác (caller-pays)
                eval_score  numeric(5,4),
                built_at    timestamptz DEFAULT now(),
                PRIMARY KEY (day, agent_id, channel)
            )
            """
        )
        # ---- C8: User Identity Broker cho Lark -------------------------------
        # Có API Lark chỉ nhận USER token (Approval v4 là ca đầu). Chuẩn platform:
        # agent KHÔNG cầm token của người/account thật — platform giữ, tự refresh,
        # audit từng lời gọi. Token nằm ở đây dạng MÃ HOÁ (bytea), không bao giờ
        # trả ra API, không ghi log.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lark_user_identities (
                subject_email      text PRIMARY KEY,
                open_id            text NOT NULL DEFAULT '',
                name               text,
                app_id             text NOT NULL,
                access_token_enc   bytea NOT NULL,
                refresh_token_enc  bytea NOT NULL,
                scope              text NOT NULL DEFAULT '',
                expires_at         timestamptz NOT NULL,
                refresh_expires_at timestamptz NOT NULL,
                granted_by         text NOT NULL,
                last_used_at       timestamptz,
                created_at         timestamptz DEFAULT now(),
                updated_at         timestamptz DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_user_identity_grants (
                agent_id      text NOT NULL,
                subject_email text NOT NULL REFERENCES lark_user_identities(subject_email)
                              ON DELETE CASCADE,
                path_prefixes text[] NOT NULL,
                methods       text[] NOT NULL DEFAULT '{GET,POST}',
                active        boolean NOT NULL DEFAULT true,
                granted_by    text NOT NULL,
                created_at    timestamptz DEFAULT now(),
                PRIMARY KEY (agent_id, subject_email)
            )
            """
        )
        # Phiên authorize đang chờ người bấm đồng ý trên Lark (biến thể "device":
        # admin lấy link ở CLI, mở ở máy/điện thoại nào cũng được, rồi poll ở đây).
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lark_user_authorize_sessions (
                state        text PRIMARY KEY,
                subject_email text NOT NULL,
                scope        text NOT NULL DEFAULT '',
                app_id       text NOT NULL,
                requested_by text NOT NULL,
                status       text NOT NULL DEFAULT 'pending',
                error        text,
                created_at   timestamptz DEFAULT now(),
                expires_at   timestamptz NOT NULL
            )
            """
        )
        # Migrate 1 lần: agent cũ có prompt_version/prompt_ref → sinh version v1 (P3.8.1)
        conn.execute(
            """
            INSERT INTO agent_versions(agent_id, version, instruction_block, skills,
                                       publication, note, created_by)
            SELECT a.agent_id, 1,
                   coalesce(a.prompt_ref, 'migrate: prompt_version=' || coalesce(a.prompt_version,'?')),
                   to_jsonb(coalesce(a.skills, '{}')), 'draft',
                   'migrate từ prompt_version/prompt_ref', 'migration'
            FROM agents a
            WHERE (a.prompt_version IS NOT NULL OR a.prompt_ref IS NOT NULL)
              AND NOT EXISTS (SELECT 1 FROM agent_versions v WHERE v.agent_id=a.agent_id)
            """
        )
        conn.commit()
    _READY = True


def _reaper_loop() -> None:
    """Nền: thu hồi job 'running' quá hạn khoá + dọn event_dedupe + purge theo retention."""
    ticks = 0
    while True:
        time.sleep(30)
        ticks += 1
        try:
            with _db() as conn:
                _reap_stale(conn)
                conn.execute("DELETE FROM event_dedupe WHERE seen_at < now() - interval '2 days'")
                _expire_actions(conn)          # P7: hết hạn đề xuất + nhắc 1 lần
                if ticks % 120 == 0:          # ~mỗi giờ: dọn dữ liệu quá TTL + dựng mart
                    _run_purge(conn)
                    try:
                        _build_mart(conn, 30)
                    except Exception:
                        pass
                conn.commit()
        except Exception:
            pass


@app.on_event("startup")
def _startup() -> None:
    try:
        _ensure_schema()
    except Exception:
        pass
    try:
        threading.Thread(target=_reaper_loop, daemon=True).start()
    except Exception:
        pass


def _require_admin(authorization: str) -> None:
    """Admin: token dịch vụ HOẶC phiên console của người có vai trò admin (P8)."""
    if ADMIN_TOKEN and authorization == f"Bearer {ADMIN_TOKEN}":
        return
    p = _principal(authorization)
    if p.get("role") == "admin":
        return
    # ĐÃ xác thực (phiên console hoặc token cá nhân CLI) nhưng thiếu quyền → 403,
    # không phải 401 (401 sẽ đá người dùng về trang login dù họ đang đăng nhập).
    if p.get("kind") in ("session", "pat"):
        raise HTTPException(status_code=403, detail="cần quyền admin")
    raise HTTPException(status_code=401, detail="admin token required")


def _actor_of(authorization: str, x_actor: str = "") -> str:
    """Danh tính ghi vào audit: ưu tiên người đăng nhập thật, không tin header."""
    p = _principal(authorization)
    if p.get("kind") in ("session", "pat") and p.get("actor"):
        return p["actor"]
    return x_actor or "service"


# ---------------- Auth API (đăng nhập console) ----------------

@app.post("/v1/auth/login")
def auth_login(body: dict, request: Request) -> dict:
    _ensure_schema()
    email = (body.get("email") or "").strip().lower()
    pw = body.get("password") or ""
    ip = (request.client.host if request.client else "") or ""
    ua = request.headers.get("user-agent", "")[:200]
    if not (email and pw):
        raise HTTPException(status_code=400, detail="cần email và password")
    with _db() as conn:
        # Khoá tạm khi sai nhiều lần (chống dò mật khẩu).
        n_fail = conn.execute(
            "SELECT count(*) c FROM login_attempts WHERE email=%s AND ok=false "
            "AND at > now() - make_interval(mins => %s)", (email, LOGIN_LOCK_MINUTES)).fetchone()["c"]
        if n_fail >= LOGIN_MAX_FAIL:
            conn.execute("INSERT INTO login_attempts(email, ip, ok) VALUES (%s,%s,false)", (email, ip))
            conn.commit()
            raise HTTPException(status_code=429,
                                detail=f"sai quá {LOGIN_MAX_FAIL} lần — thử lại sau {LOGIN_LOCK_MINUTES} phút")
        a = conn.execute("SELECT email, name, password_hash, status, must_change_pw "
                         "FROM accounts WHERE email=%s", (email,)).fetchone()
        ok = bool(a) and a["status"] == "active" and _verify_pw(pw, a["password_hash"])
        conn.execute("INSERT INTO login_attempts(email, ip, ok) VALUES (%s,%s,%s)", (email, ip, ok))
        if not ok:
            _audit(conn, email, "login_failed", "account", email, {"ip": ip})
            conn.commit()
            raise HTTPException(status_code=401, detail="email hoặc mật khẩu không đúng")
        token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO web_sessions(token_hash, email, expires_at, ip, user_agent) "
            "VALUES (%s,%s, now() + make_interval(hours => %s), %s,%s)",
            (hashlib.sha256(token.encode()).hexdigest(), email, SESSION_HOURS, ip, ua))
        conn.execute("UPDATE accounts SET last_login_at=now() WHERE email=%s", (email,))
        role = _effective_role(conn, email)
        _audit(conn, email, "login", "account", email, {"ip": ip})
        conn.commit()
    return {"token": token, "email": email, "name": a["name"], "role": role,
            "must_change_pw": a["must_change_pw"], "expires_hours": SESSION_HOURS}


@app.post("/v1/auth/logout")
def auth_logout(authorization: str = Header(default="")) -> dict:
    tok = _bearer(authorization)
    if tok:
        with _db() as conn:
            conn.execute("UPDATE web_sessions SET revoked_at=now() WHERE token_hash=%s",
                         (hashlib.sha256(tok.encode()).hexdigest(),))
            conn.commit()
    return {"ok": True}


@app.get("/v1/auth/me")
def auth_me(authorization: str = Header(default="")) -> dict:
    """Người đang đăng nhập + vai trò (platform và theo từng agent).

    Dùng được cả bằng phiên console lẫn token cá nhân CLI (`lsr-login.sh --status`).
    """
    tok = _bearer(authorization)
    with _db() as conn:
        email = _session_email(conn, tok) or _pat_email(conn, tok)
        if not email:
            raise HTTPException(status_code=401, detail="chưa đăng nhập")
        a = conn.execute("SELECT email, name, must_change_pw FROM accounts WHERE email=%s",
                         (email,)).fetchone()
        rows = conn.execute("SELECT scope_type, scope_id, role FROM role_bindings WHERE email=%s",
                            (email,)).fetchall()
    plat = next((r["role"] for r in rows if r["scope_type"] == "platform"), None)
    agents = {r["scope_id"]: r["role"] for r in rows if r["scope_type"] == "agent"}
    return {"email": a["email"], "name": a["name"], "must_change_pw": a["must_change_pw"],
            "platform_role": plat, "agent_roles": agents,
            "default_role": DEFAULT_LOGIN_ROLE if DEFAULT_LOGIN_ROLE in _ROLE_RANK else None,
            "can_manage_accounts": plat == "admin",
            "can_create_agent": _ROLE_RANK.get(plat or "", 0) >= 2 or bool(
                [r for r in rows if _ROLE_RANK.get(r["role"], 0) >= 2])}


@app.post("/v1/auth/change-password")
def auth_change_pw(body: dict, authorization: str = Header(default="")) -> dict:
    tok = _bearer(authorization)
    new = body.get("new_password") or ""
    if len(new) < 10:
        raise HTTPException(status_code=400, detail="mật khẩu tối thiểu 10 ký tự")
    with _db() as conn:
        email = _session_email(conn, tok)
        if not email:
            raise HTTPException(status_code=401, detail="chưa đăng nhập")
        a = conn.execute("SELECT password_hash, must_change_pw FROM accounts WHERE email=%s",
                         (email,)).fetchone()
        # Lần đầu (mật khẩu tạm) không cần nhập mật khẩu cũ.
        if not a["must_change_pw"] and not _verify_pw(body.get("old_password") or "", a["password_hash"]):
            raise HTTPException(status_code=403, detail="mật khẩu cũ không đúng")
        conn.execute("UPDATE accounts SET password_hash=%s, must_change_pw=false WHERE email=%s",
                     (_hash_pw(new), email))
        _audit(conn, email, "change_password", "account", email, {})
        conn.commit()
    return {"ok": True}


# ---------------- P10: đăng nhập console qua Lark OAuth ----------------
# Luồng: console → /start lấy URL authorize (state ký HMAC, TTL 10') → Lark hỏi người
# dùng → redirect về console (/api/auth/lark/callback) → console (server-side) POST
# code+state về đây → đổi user_access_token, kiểm tra ORG, tự tạo tài khoản, cấp phiên.
# Session token chỉ đi server-to-server, KHÔNG xuất hiện trên URL trình duyệt.

_OAUTH_STATE_TTL = 600


def _oauth_sign(ts: str) -> str:
    key = (ADMIN_TOKEN or "lsr-oauth").encode()
    return hmac.new(key, f"lark-oauth:{ts}".encode(), hashlib.sha256).hexdigest()[:32]


def _oauth_state_ok(state: str) -> bool:
    try:
        ts, sig = state.split(".", 1)
        return (hmac.compare_digest(sig, _oauth_sign(ts))
                and 0 <= time.time() - int(ts) < _OAUTH_STATE_TTL)
    except Exception:
        return False


@app.get("/v1/auth/lark/start")
def auth_lark_start() -> dict:
    """Trả URL authorize của Lark để console redirect người dùng sang."""
    if not (LARK_APP_ID and LARK_APP_SECRET):
        raise HTTPException(status_code=503, detail="Lark OAuth chưa cấu hình (LARK_NOTIFY_APP_ID/SECRET)")
    if not CONSOLE_BASE_URL:
        raise HTTPException(status_code=503, detail="thiếu CONSOLE_BASE_URL")
    from urllib.parse import quote
    ts = str(int(time.time()))
    state = f"{ts}.{_oauth_sign(ts)}"
    redirect_uri = f"{CONSOLE_BASE_URL}/api/auth/lark/callback"
    url = (f"{LARK_DOMAIN}/open-apis/authen/v1/authorize?app_id={LARK_APP_ID}"
           f"&redirect_uri={quote(redirect_uri, safe='')}&state={state}")
    return {"url": url, "state": state}


@app.post("/v1/auth/lark/callback")
def auth_lark_callback(body: dict, request: Request) -> dict:
    """Đổi code lấy danh tính Lark → kiểm ORG → tạo/tìm tài khoản → cấp phiên console."""
    _ensure_schema()
    code = (body.get("code") or "").strip()
    state = body.get("state") or ""
    if not code:
        raise HTTPException(status_code=400, detail="thiếu code")
    if not _oauth_state_ok(state):
        raise HTTPException(status_code=400, detail="state không hợp lệ hoặc đã hết hạn — đăng nhập lại")
    # 1) code → user_access_token (OAuth v2)
    r = requests.post(f"{LARK_DOMAIN}/open-apis/authen/v2/oauth/token", json={
        "grant_type": "authorization_code", "client_id": LARK_APP_ID,
        "client_secret": LARK_APP_SECRET, "code": code,
        "redirect_uri": f"{CONSOLE_BASE_URL}/api/auth/lark/callback"}, timeout=10)
    d = r.json() if r.content else {}
    at = d.get("access_token")
    if not at:
        raise HTTPException(status_code=401,
                            detail=f"Lark từ chối code: {d.get('error_description') or d.get('msg') or d.get('error')}")
    # 2) danh tính người dùng
    u = requests.get(f"{LARK_DOMAIN}/open-apis/authen/v1/user_info",
                     headers={"Authorization": f"Bearer {at}"}, timeout=10).json()
    info = (u.get("data") or {})
    email = (info.get("enterprise_email") or info.get("email") or "").strip().lower()
    tenant = info.get("tenant_key") or ""
    name = info.get("name") or email
    open_id = info.get("open_id") or ""
    # 3) kiểm tra ĐÚNG ORG: tenant_key (nếu đã cấu hình) + domain email công ty
    if LARK_TENANT_KEY and tenant != LARK_TENANT_KEY:
        raise HTTPException(status_code=403, detail="tài khoản Lark không thuộc tổ chức LamsonRetail")
    if not email:
        raise HTTPException(status_code=403,
                            detail="Lark không trả email — app cần scope email/enterprise_email và tài khoản phải có email công ty")
    domain = email.split("@")[-1]
    if ALLOWED_LOGIN_DOMAINS and domain not in ALLOWED_LOGIN_DOMAINS:
        raise HTTPException(status_code=403, detail=f"email @{domain} không thuộc org được phép")
    ip = (request.client.host if request.client else "") or ""
    provisioned = False
    with _db() as conn:
        a = conn.execute("SELECT email, status FROM accounts WHERE email=%s", (email,)).fetchone()
        if a and a["status"] != "active":
            raise HTTPException(status_code=403, detail="tài khoản đã bị khoá — liên hệ admin")
        if not a:
            # Tự mở tài khoản: danh tính đã được Lark + kiểm org xác nhận. Mật khẩu ngẫu
            # nhiên (không dùng được) — người này đăng nhập bằng Lark, không phát mật khẩu.
            conn.execute(
                "INSERT INTO accounts(email, name, password_hash, must_change_pw, created_by, "
                " auth_via, lark_open_id) VALUES (%s,%s,%s,false,'lark-oauth','lark',%s)",
                (email, name, _hash_pw(secrets.token_urlsafe(24)), open_id))
            provisioned = True
        else:
            conn.execute("UPDATE accounts SET lark_open_id=coalesce(%s, lark_open_id) WHERE email=%s",
                         (open_id or None, email))
        _identity_cache_put(email, open_id)     # agent gửi Lark cho người này khỏi tra lại
        token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO web_sessions(token_hash, email, expires_at, ip, user_agent) "
            "VALUES (%s,%s, now() + make_interval(hours => %s), %s,%s)",
            (hashlib.sha256(token.encode()).hexdigest(), email, SESSION_HOURS,
             ip, request.headers.get("user-agent", "")[:200]))
        conn.execute("UPDATE accounts SET last_login_at=now() WHERE email=%s", (email,))
        has_roles = bool(conn.execute(
            "SELECT 1 FROM role_bindings WHERE email=%s LIMIT 1", (email,)).fetchone())
        _audit(conn, email, "login_lark", "account", email,
               {"ip": ip, "tenant": tenant, "provisioned": provisioned})
        conn.commit()
    return {"token": token, "email": email, "name": name, "provisioned": provisioned,
            "has_roles": has_roles, "default_role": DEFAULT_LOGIN_ROLE,
            "expires_hours": SESSION_HOURS}


# ---------------- P11: device-login + token cá nhân cho CLI/Claude Code ----------------
# Vấn đề cũ: enroll cần LSR_ENROLL_TOKEN — secret dùng chung, ai cũng phải đi xin.
# Nay: CLI gọi /device/start → người dùng mở console duyệt → CLI nhận TOKEN CÁ NHÂN
# mang đúng quyền của người đó. Admin enroll thì agent ACTIVE luôn (tự duyệt).

_PAT_DAYS = int(os.environ.get("PAT_DAYS", "90"))
_DEVICE_TTL_MIN = 15
_USER_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"     # bỏ ký tự dễ nhìn nhầm


def _mint_pat(conn, email: str, label: str) -> str:
    token = "lsr_pat_" + secrets.token_urlsafe(24)
    conn.execute(
        "INSERT INTO personal_tokens(token_hash, email, label, expires_at) "
        "VALUES (%s,%s,%s, now() + make_interval(days => %s))",
        (hashlib.sha256(token.encode()).hexdigest(), email, label[:80], _PAT_DAYS))
    return token


@app.post("/v1/auth/device/start")
def device_start(body: dict) -> dict:
    """CLI mở phiên đăng nhập. KHÔNG cần auth — chưa cấp gì cho tới khi người duyệt."""
    _ensure_schema()
    label = (body.get("label") or "Claude Code CLI")[:80]
    device_code = secrets.token_urlsafe(32)
    with _db() as conn:
        for _ in range(5):      # tránh trùng user_code hiếm gặp
            user_code = ("".join(secrets.choice(_USER_CODE_ALPHABET) for _ in range(4))
                         + "-" + "".join(secrets.choice(_USER_CODE_ALPHABET) for _ in range(4)))
            try:
                conn.execute(
                    "INSERT INTO device_codes(device_code, user_code, label, expires_at) "
                    "VALUES (%s,%s,%s, now() + make_interval(mins => %s))",
                    (device_code, user_code, label, _DEVICE_TTL_MIN))
                conn.commit()
                break
            except Exception:
                conn.rollback()
        else:
            raise HTTPException(status_code=503, detail="không sinh được mã — thử lại")
    return {"device_code": device_code, "user_code": user_code,
            "verify_url": f"{APP_PUBLIC_URL}/device?code={user_code}",
            "expires_in": _DEVICE_TTL_MIN * 60, "interval": 3}


@app.post("/v1/auth/device/poll")
def device_poll(body: dict) -> dict:
    """CLI hỏi kết quả. Token trả về ĐÚNG MỘT LẦN rồi xoá khỏi DB."""
    dc = body.get("device_code") or ""
    with _db() as conn:
        r = conn.execute("SELECT * FROM device_codes WHERE device_code=%s", (dc,)).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="mã thiết bị không tồn tại")
        if r["expires_at"] and r["expires_at"] < datetime.now(timezone.utc):
            return {"status": "expired"}
        if r["status"] == "denied":
            return {"status": "denied"}
        if r["status"] != "approved":
            return {"status": "pending"}
        token = r["token_once"]
        conn.execute("DELETE FROM device_codes WHERE device_code=%s", (dc,))
        conn.commit()
    if not token:
        return {"status": "expired"}
    return {"status": "approved", "token": token, "email": r["email"],
            "expires_days": _PAT_DAYS}


@app.post("/v1/auth/device/approve")
def device_approve(body: dict, authorization: str = Header(default="")) -> dict:
    """Người dùng (đã đăng nhập console) duyệt phiên CLI của chính mình."""
    p = _principal(authorization)
    if p["kind"] not in ("session", "pat"):
        raise HTTPException(status_code=401, detail="cần đăng nhập console")
    code = (body.get("user_code") or "").strip().upper()
    deny = bool(body.get("deny"))
    with _db() as conn:
        r = conn.execute(
            "SELECT device_code, status, expires_at, label FROM device_codes WHERE user_code=%s",
            (code,)).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="mã không đúng — kiểm tra lại")
        if r["expires_at"] and r["expires_at"] < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="mã đã hết hạn — chạy lại lệnh đăng nhập")
        if r["status"] != "pending":
            raise HTTPException(status_code=409, detail=f"mã đã được xử lý ({r['status']})")
        if deny:
            conn.execute("UPDATE device_codes SET status='denied' WHERE user_code=%s", (code,))
            conn.commit()
            return {"ok": True, "status": "denied"}
        token = _mint_pat(conn, p["actor"], r["label"] or "CLI")
        conn.execute("UPDATE device_codes SET status='approved', email=%s, token_once=%s "
                     "WHERE user_code=%s", (p["actor"], token, code))
        _audit(conn, p["actor"], "device_login_approve", "account", p["actor"],
               {"label": r["label"]})
        conn.commit()
    return {"ok": True, "status": "approved", "email": p["actor"], "expires_days": _PAT_DAYS}


@app.get("/v1/auth/tokens")
def pat_list(authorization: str = Header(default="")) -> list[dict]:
    p = _principal(authorization)
    if p["kind"] not in ("session", "pat"):
        raise HTTPException(status_code=401, detail="cần đăng nhập console")
    with _db() as conn:
        rows = conn.execute(
            "SELECT token_hash, label, created_at, expires_at, last_used_at FROM personal_tokens "
            "WHERE email=%s AND revoked_at IS NULL ORDER BY created_at DESC", (p["actor"],)).fetchall()
    return [{"id": r["token_hash"][:12], "label": r["label"], "created_at": r["created_at"],
             "expires_at": r["expires_at"], "last_used_at": r["last_used_at"]} for r in rows]


@app.post("/v1/auth/tokens/{token_id}/revoke")
def pat_revoke(token_id: str, authorization: str = Header(default="")) -> dict:
    p = _principal(authorization)
    if p["kind"] not in ("session", "pat"):
        raise HTTPException(status_code=401, detail="cần đăng nhập console")
    with _db() as conn:
        n = conn.execute(
            "UPDATE personal_tokens SET revoked_at=now() WHERE email=%s AND token_hash LIKE %s "
            "AND revoked_at IS NULL RETURNING token_hash", (p["actor"], token_id + "%")).fetchone()
        if not n:
            raise HTTPException(status_code=404, detail="không thấy token")
        _audit(conn, p["actor"], "pat_revoke", "account", p["actor"], {"id": token_id})
        conn.commit()
    return {"ok": True}


# ---------------- P10: yêu cầu phân quyền per-agent (admin duyệt) ----------------

@app.get("/v1/roles/catalog")
def roles_catalog(authorization: str = Header(default="")) -> dict:
    """Trang 'Xin quyền': mọi agent (tên + bot Lark) + quyền hiện có + yêu cầu của tôi."""
    p = _principal(authorization)
    if p["kind"] not in ("session", "pat"):
        raise HTTPException(status_code=401, detail="cần đăng nhập console")
    email = p["actor"]
    _ensure_schema()
    with _db() as conn:
        agents = conn.execute(
            "SELECT agent_id, name, squad, status, lark_app_id, lark_bot_name FROM agents "
            "WHERE coalesce(is_platform, false) = false ORDER BY agent_id").fetchall()
        binds = {r["scope_id"]: r["role"] for r in conn.execute(
            "SELECT scope_id, role FROM role_bindings WHERE email=%s AND scope_type='agent'",
            (email,)).fetchall()}
        prow = conn.execute(
            "SELECT role FROM role_bindings WHERE email=%s AND scope_type='platform'",
            (email,)).fetchone()
        reqs = conn.execute(
            "SELECT id, scope_type, scope_id, role, reason, status, decided_by, decide_note, "
            "created_at, decided_at FROM role_requests WHERE email=%s "
            "ORDER BY id DESC LIMIT 100", (email,)).fetchall()
    plat = prow["role"] if prow else None
    out = []
    for a in agents:
        mine = binds.get(a["agent_id"])
        eff = mine or plat or DEFAULT_LOGIN_ROLE
        out.append({**dict(a), "my_role": mine, "effective_role": eff})
    return {"email": email, "platform_role": plat, "default_role": DEFAULT_LOGIN_ROLE,
            "agents": out, "requests": [dict(r) for r in reqs]}


@app.post("/v1/roles/request")
def roles_request(body: dict, authorization: str = Header(default="")) -> dict:
    """Người dùng xin quyền moderator|admin trên 1 agent (hoặc platform). Admin sẽ duyệt."""
    p = _principal(authorization)
    if p["kind"] not in ("session", "pat"):
        raise HTTPException(status_code=401, detail="cần đăng nhập console")
    email = p["actor"]
    scope_type = body.get("scope_type") or "agent"
    scope_id = (body.get("scope_id") or "").strip() or ("*" if scope_type == "platform" else "")
    role = body.get("role") or ""
    reason = (body.get("reason") or "").strip()[:500]
    if scope_type not in ("agent", "platform"):
        raise HTTPException(status_code=400, detail="scope_type: agent|platform")
    if role not in ("moderator", "admin"):
        raise HTTPException(status_code=400,
                            detail="chỉ xin moderator|admin — quyền 'user' là mặc định của mọi tài khoản")
    with _db() as conn:
        if scope_type == "agent":
            if not conn.execute("SELECT 1 FROM agents WHERE agent_id=%s", (scope_id,)).fetchone():
                raise HTTPException(status_code=404, detail="agent không tồn tại")
        cur = _effective_role(conn, email, scope_id if scope_type == "agent" else None)
        if _ROLE_RANK.get(cur or "", 0) >= _ROLE_RANK.get(role, 99):
            raise HTTPException(status_code=400, detail=f"bạn đã có quyền '{cur}' — không cần xin '{role}'")
        dup = conn.execute(
            "SELECT id FROM role_requests WHERE email=%s AND scope_type=%s AND scope_id=%s "
            "AND status='pending'", (email, scope_type, scope_id)).fetchone()
        if dup:
            raise HTTPException(status_code=409, detail=f"đã có yêu cầu #{dup['id']} đang chờ duyệt")
        row = conn.execute(
            "INSERT INTO role_requests(email, scope_type, scope_id, role, reason) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (email, scope_type, scope_id, role, reason)).fetchone()
        _audit(conn, email, "role_request", "role_request", str(row["id"]),
               {"scope": f"{scope_type}:{scope_id}", "role": role})
        scope_disp = scope_id if scope_type == "agent" else "PLATFORM"
        _notify_admins(conn,
                       f"🔑 {email} xin quyền {role.upper()} trên {scope_disp}"
                       + (f"\nLý do: {reason}" if reason else "")
                       + "\nDuyệt tại Console → Accounts → Yêu cầu phân quyền.")
        conn.commit()
    return {"ok": True, "id": row["id"], "status": "pending"}


@app.get("/v1/roles/requests")
def roles_requests_list(status: str = "pending",
                        authorization: str = Header(default="")) -> list[dict]:
    _require_role(authorization, "admin")
    _ensure_schema()
    with _db() as conn:
        rows = conn.execute(
            "SELECT q.id, q.email, a.name, q.scope_type, q.scope_id, q.role, q.reason, "
            "q.status, q.decided_by, q.decide_note, q.created_at, q.decided_at "
            "FROM role_requests q LEFT JOIN accounts a ON a.email=q.email "
            "WHERE (%s = 'all' OR q.status = %s) ORDER BY q.id DESC LIMIT 200",
            (status, status)).fetchall()
    return [dict(r) for r in rows]


@app.post("/v1/roles/requests/{req_id}/decide")
def roles_request_decide(req_id: int, body: dict,
                         authorization: str = Header(default="")) -> dict:
    """Admin duyệt/từ chối. Duyệt → ghi role_bindings; báo người xin qua Lark/Telegram."""
    p = _require_role(authorization, "admin")
    approve = bool(body.get("approve"))
    note = (body.get("note") or "").strip()[:300]
    actor = p["actor"] or "admin"
    with _db() as conn:
        q = conn.execute("SELECT * FROM role_requests WHERE id=%s FOR UPDATE", (req_id,)).fetchone()
        if not q:
            raise HTTPException(status_code=404, detail="yêu cầu không tồn tại")
        if q["status"] != "pending":
            raise HTTPException(status_code=409, detail=f"yêu cầu đã ở trạng thái '{q['status']}'")
        # Tách vai: không tự duyệt yêu cầu của chính mình (dù là admin).
        if p["kind"] == "session" and actor == q["email"]:
            raise HTTPException(status_code=403, detail="không tự duyệt yêu cầu của chính mình")
        if approve:
            conn.execute(
                "INSERT INTO role_bindings(email, scope_type, scope_id, role, granted_by) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (email, scope_type, scope_id) "
                "DO UPDATE SET role=EXCLUDED.role, granted_by=EXCLUDED.granted_by, granted_at=now()",
                (q["email"], q["scope_type"], q["scope_id"], q["role"], actor))
        conn.execute(
            "UPDATE role_requests SET status=%s, decided_by=%s, decided_at=now(), decide_note=%s "
            "WHERE id=%s", ("approved" if approve else "rejected", actor, note, req_id))
        _audit(conn, actor, "role_request_decide", "role_request", str(req_id),
               {"approve": approve, "email": q["email"],
                "scope": f"{q['scope_type']}:{q['scope_id']}", "role": q["role"]})
        conn.commit()
    # Báo người xin (best-effort, ngoài transaction — lỗi gửi tin không hỏng quyết định).
    scope_disp = q["scope_id"] if q["scope_type"] == "agent" else "PLATFORM"
    verdict = "✅ ĐƯỢC DUYỆT" if approve else "❌ BỊ TỪ CHỐI"
    _send_lark(q["email"], f"Yêu cầu quyền {q['role'].upper()} trên {scope_disp} của bạn {verdict}"
                           f" (bởi {actor})." + (f"\nGhi chú: {note}" if note else ""))
    try:
        with _db() as conn:
            tg = conn.execute("SELECT telegram_chat_id FROM accounts WHERE email=%s",
                              (q["email"],)).fetchone()
            if tg and tg["telegram_chat_id"]:
                _tg_send(tg["telegram_chat_id"],
                         f"Yêu cầu quyền {q['role']} trên {scope_disp}: {verdict} (bởi {actor})")
    except Exception:
        pass
    return {"ok": True, "id": req_id, "status": "approved" if approve else "rejected"}


# ---------------- Quản lý tài khoản (chỉ admin) ----------------

@app.get("/v1/accounts")
def accounts_list(authorization: str = Header(default="")) -> list[dict]:
    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        rows = conn.execute(
            "SELECT a.email, a.name, a.status, a.must_change_pw, a.last_login_at, a.created_at, "
            "a.telegram_chat_id, a.auth_via, (a.lark_open_id IS NOT NULL) AS lark_linked, "
            "coalesce(json_agg(json_build_object('scope_type', r.scope_type, 'scope_id', r.scope_id, "
            "  'role', r.role) ORDER BY r.scope_type) FILTER (WHERE r.id IS NOT NULL), '[]') AS roles "
            "FROM accounts a LEFT JOIN role_bindings r ON r.email=a.email "
            "GROUP BY a.email ORDER BY a.email").fetchall()
    return [dict(r) for r in rows]


@app.post("/v1/accounts")
def account_create(body: dict, authorization: str = Header(default="")) -> dict:
    """Tạo tài khoản + sinh mật khẩu tạm (hiện MỘT LẦN cho admin chuyển cho người dùng)."""
    _require_admin(authorization)
    _ensure_schema()
    email = (body.get("email") or "").strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="email không hợp lệ")
    actor = _actor_of(authorization)
    tmp = secrets.token_urlsafe(9)
    with _db() as conn:
        if conn.execute("SELECT 1 FROM accounts WHERE email=%s", (email,)).fetchone():
            raise HTTPException(status_code=409, detail="tài khoản đã tồn tại")
        conn.execute(
            "INSERT INTO accounts(email, name, password_hash, must_change_pw, created_by) "
            "VALUES (%s,%s,%s,true,%s)", (email, body.get("name") or email, _hash_pw(tmp), actor))
        role = body.get("role") or "user"
        scope_type = body.get("scope_type") or "platform"
        scope_id = body.get("scope_id") or "*"
        if role in _ROLE_RANK:
            conn.execute(
                "INSERT INTO role_bindings(email, scope_type, scope_id, role, granted_by) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (email, scope_type, scope_id, role, actor))
        _audit(conn, actor, "account_create", "account", email,
               {"role": role, "scope": f"{scope_type}:{scope_id}"})
        conn.commit()
    return {"email": email, "temp_password": tmp,
            "note": "Mật khẩu tạm chỉ hiện MỘT LẦN — người dùng phải đổi khi đăng nhập."}


@app.post("/v1/accounts/{email}/update")
def account_update(email: str, body: dict, authorization: str = Header(default="")) -> dict:
    """Cập nhật thông tin tài khoản: tên, Telegram chat_id (để nhận cảnh báo/duyệt việc)."""
    _require_admin(authorization)
    email = email.lower()
    actor = _actor_of(authorization)
    tg = body.get("telegram_chat_id")
    tg = str(tg).strip() if tg not in (None, "") else None
    with _db() as conn:
        n = conn.execute(
            "UPDATE accounts SET name=coalesce(%s, name), telegram_chat_id=%s "
            "WHERE email=%s RETURNING email", (body.get("name"), tg, email)).fetchone()
        if not n:
            raise HTTPException(status_code=404, detail="tài khoản không tồn tại")
        # Giữ đồng bộ với bảng kênh admin cũ (platform_admins) nếu email có ở đó.
        conn.execute("UPDATE platform_admins SET telegram_chat_id=%s, linked_at=now() "
                     "WHERE lower(email)=%s", (tg, email))
        _audit(conn, actor, "account_update", "account", email,
               {"telegram_linked": bool(tg), "name": bool(body.get("name"))})
        conn.commit()
    return {"ok": True, "email": email, "telegram_linked": bool(tg)}


@app.post("/v1/accounts/{email}/roles")
def account_roles(email: str, body: dict, authorization: str = Header(default="")) -> dict:
    """Gán/thu vai trò theo platform hoặc theo TỪNG agent."""
    _require_admin(authorization)
    email = email.lower()
    scope_type = body.get("scope_type") or "platform"
    scope_id = body.get("scope_id") or "*"
    role = body.get("role")
    revoke = bool(body.get("revoke"))
    if scope_type not in ("platform", "agent"):
        raise HTTPException(status_code=400, detail="scope_type: platform|agent")
    if not revoke and role not in _ROLE_RANK:
        raise HTTPException(status_code=400, detail="role: admin|moderator|user")
    actor = _actor_of(authorization)
    with _db() as conn:
        if not conn.execute("SELECT 1 FROM accounts WHERE email=%s", (email,)).fetchone():
            raise HTTPException(status_code=404, detail="tài khoản không tồn tại")
        if revoke:
            conn.execute("DELETE FROM role_bindings WHERE email=%s AND scope_type=%s AND scope_id=%s",
                         (email, scope_type, scope_id))
        else:
            conn.execute(
                "INSERT INTO role_bindings(email, scope_type, scope_id, role, granted_by) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (email, scope_type, scope_id) "
                "DO UPDATE SET role=EXCLUDED.role, granted_by=EXCLUDED.granted_by, granted_at=now()",
                (email, scope_type, scope_id, role, actor))
        _audit(conn, actor, "role_revoke" if revoke else "role_grant", "account", email,
               {"scope": f"{scope_type}:{scope_id}", "role": role})
        conn.commit()
    return {"ok": True, "email": email, "scope": f"{scope_type}:{scope_id}", "role": None if revoke else role}


@app.post("/v1/accounts/{email}/status")
def account_status(email: str, body: dict, authorization: str = Header(default="")) -> dict:
    """Bật/tắt tài khoản. Tắt → mọi phiên đang mở bị vô hiệu NGAY."""
    _require_admin(authorization)
    email = email.lower()
    st = body.get("status")
    if st not in ("active", "disabled"):
        raise HTTPException(status_code=400, detail="status: active|disabled")
    actor = _actor_of(authorization)
    if st == "disabled" and email == actor:
        raise HTTPException(status_code=400, detail="không tự tắt tài khoản của chính mình")
    with _db() as conn:
        n = conn.execute("UPDATE accounts SET status=%s WHERE email=%s RETURNING email",
                         (st, email)).fetchone()
        if not n:
            raise HTTPException(status_code=404, detail="tài khoản không tồn tại")
        if st == "disabled":
            conn.execute("UPDATE web_sessions SET revoked_at=now() "
                         "WHERE email=%s AND revoked_at IS NULL", (email,))
        _audit(conn, actor, "account_status", "account", email, {"status": st})
        conn.commit()
    return {"email": email, "status": st}


@app.post("/v1/accounts/{email}/reset-password")
def account_reset_pw(email: str, authorization: str = Header(default="")) -> dict:
    _require_admin(authorization)
    email = email.lower()
    tmp = secrets.token_urlsafe(9)
    actor = _actor_of(authorization)
    with _db() as conn:
        n = conn.execute("UPDATE accounts SET password_hash=%s, must_change_pw=true "
                         "WHERE email=%s RETURNING email", (_hash_pw(tmp), email)).fetchone()
        if not n:
            raise HTTPException(status_code=404, detail="tài khoản không tồn tại")
        conn.execute("UPDATE web_sessions SET revoked_at=now() WHERE email=%s AND revoked_at IS NULL",
                     (email,))
        _audit(conn, actor, "account_reset_pw", "account", email, {})
        conn.commit()
    return {"email": email, "temp_password": tmp}


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
    "lsr_lark.py",                      # lib Lark dùng chung (remote, drop-in)
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
            if row:
                return row["agent_id"]
            # Token ngắn hạn do platform cấp cho nocode_runtime (P9)
            row = conn.execute(
                "SELECT agent_id FROM agent_runtime_tokens WHERE token_hash=%s "
                "AND expires_at > now()", (h,)).fetchone()
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
    # P2: runner tự LEASE credential từ broker (LSR_PLATFORM_URL). oauth_token vẫn nhận
    # như FALLBACK (own-mode chưa cấu hình pool) — không log.
    env = {
        "CLAUDE_CODE_OAUTH_TOKEN": oauth,
        "LSR_AGENT_ID": aid,
        "LSR_PLATFORM_URL": "http://platform_api:8090",
        "LSR_COLLECTOR": "http://collector:8081",   # nội bộ docker network (GĐ VM chung)
        "LSR_TELEMETRY_API_KEY": tok,
        "AGENT_REPO": body.get("repo") or "",
        "AGENT_START_CMD": body.get("start_cmd") or "",
    }
    name = _agent_container(aid)
    mem = int(body.get("mem_mb") or 512)
    cpus = float(body.get("cpus") or 0.5)
    # Mount thư mục secrets của VM (chứa credential pool) READ-ONLY để runner đọc theo ref.
    secrets_host = os.environ.get("SECRETS_HOST_DIR", "")
    volumes = ({secrets_host: {"bind": "/secrets", "mode": "ro"}} if secrets_host else None)
    try:
        try:
            client.containers.get(name).remove(force=True)
        except Exception:
            pass
        run_kwargs = dict(
            name=name, detach=True,
            environment=env, network=AGENT_NETWORK,
            restart_policy={"Name": "unless-stopped"},
            mem_limit=f"{mem}m", nano_cpus=int(cpus * 1e9),
            labels={"lsr-agent": aid},
        )
        if volumes:
            run_kwargs["volumes"] = volumes
        c = client.containers.run(AGENT_RUNNER_IMAGE, **run_kwargs)
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
        c.reload()  # đọc lại trạng thái mới sau thao tác (tránh status cache cũ)
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

    _ensure_schema()
    # 3 cách xác thực, ưu tiên DANH TÍNH NGƯỜI DÙNG (không cần secret dùng chung):
    #   1. token cá nhân / phiên console  → owner mặc định = chính người đó;
    #      admin platform thì agent ACTIVE luôn (tự duyệt).
    #   2. enroll token dùng chung        → giữ tương thích cho script cũ (agent 'registered').
    p = _principal(authorization)
    tok = _bearer(authorization)
    if p["kind"] in ("session", "pat", "admin_token"):
        actor, actor_role = p["actor"], p["role"]
    elif ENROLL_TOKEN and tok == ENROLL_TOKEN:
        actor, actor_role = None, None
    else:
        raise HTTPException(
            status_code=401,
            detail="cần đăng nhập: chạy `bash scripts/lsr-login.sh` (mở console duyệt 1 lần) "
                   "— hoặc dùng LSR_ENROLL_TOKEN nếu bạn có sẵn")
    agent_id = (agent.get("agent_id") or "").strip()
    owner = str(agent.get("owner", "")).strip() or (actor or "")
    if not agent_id:
        raise HTTPException(status_code=422, detail="agent_id required")
    if not _EMAIL_RE.match(owner):
        raise HTTPException(status_code=422, detail="owner phải là email thật của người sở hữu")
    # Admin tự duyệt agent mình tạo; người khác vẫn cần admin activate.
    auto_approve = actor_role == "admin"
    status0 = "active" if auto_approve else "registered"
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
                                backend_url, dashboard_url, golive_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    CASE WHEN %s='active' THEN now() END)
            """,
            (agent_id, agent.get("name"), owner, agent.get("squad"),
             agent.get("connect_mode", "bot"), bool(agent.get("is_squad_agent", False)),
             skills, status0, key_hash, agent.get("deployment", "managed"), agent.get("repo_url"),
             agent.get("host_note"), agent.get("backup_owner"),
             agent.get("prompt_version"), agent.get("prompt_ref"),
             agent.get("backend_url"), agent.get("dashboard_url"), status0),
        )
        # Người tạo là moderator của chính agent mình (quản trong console mà không cần xin).
        if actor and "@" in actor:
            conn.execute(
                "INSERT INTO role_bindings(email, scope_type, scope_id, role, granted_by) "
                "VALUES (%s,'agent',%s,'moderator','auto-enroll') ON CONFLICT DO NOTHING",
                (actor, agent_id))
        schema = agent_schema(agent_id)
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        _audit(conn, actor or owner, "enroll", "agent", agent_id,
               {"name": agent.get("name"), "deployment": agent.get("deployment", "managed"),
                "self_service": True, "auto_approved": auto_approve,
                "via": p["kind"] if actor else "enroll_token"})
        _notify_admins(conn,
                       f"🆕 Agent mới: {agent_id} ({agent.get('name') or '?'})\n"
                       f"Owner: {owner} · người tạo: {actor or 'enroll-token'} · "
                       f"deploy: {agent.get('deployment', 'managed')}\n"
                       + ("✅ ĐÃ TỰ ACTIVE (người tạo là admin platform)."
                          if auto_approve else
                          "Token đã cấp TỰ ĐỘNG; test web chat được ngay. "
                          "Cần ACTIVATE để chạy Lark/Telegram + A2A.")
                       + f"\n{APP_PUBLIC_URL}/agent/{agent_id}")
        conn.commit()
    _minh_anh_share(agent_id)
    return {
        "agent_id": agent_id,
        "status": status0,
        "auto_approved": auto_approve,
        "created_by": actor,
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
            "Agent đã ACTIVE — chạy được cả Lark/Telegram + A2A." if auto_approve
            else "Test ngay bằng web chat console; nhờ admin ACTIVATE để chạy Lark/Telegram + A2A.",
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
    # GATE golive (chốt lại 18/08): chưa đủ checklist thì KHÔNG active — nhưng không
    # im lặng: platform NHẮC OWNER đúng những mục còn thiếu. Đủ checklist thì hệ thống
    # tự đẩy sang admin duyệt (xem submit_checklist). force=true chỉ dành cho admin
    # xử lý ngoại lệ và luôn bị ghi audit.
    miss: list = []
    if status == "active":
        with _db() as conn:
            row = conn.execute(
                "SELECT payload FROM agent_golive_checklist WHERE agent_id=%s", (agent_id,)
            ).fetchone()
            miss = missing_checklist((row or {}).get("payload") or {})
            if miss and not body.get("force"):
                _notify_owner_checklist(conn, agent_id, miss)
                conn.commit()
                raise HTTPException(
                    status_code=409,
                    detail={"error": "golive checklist chưa đủ — đã nhắc owner bổ sung",
                            "missing": miss,
                            "hint": "owner nộp tại POST /v1/agents/{id}/golive-checklist; "
                                    "đủ mục là hệ thống tự trình admin duyệt"})
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
               {"status": status, "lark_sync": lark, "vm": vm,
                "checklist_missing": miss})
        conn.commit()
    return {"agent_id": agent_id, "status": status, "lark_sync": lark, "vm": vm,
            "checklist_missing": miss}


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

_LARK_TOKEN: dict = {}          # app_id -> {"value": str, "exp": float}


def _lark_token(app_id: str = "") -> str:
    """tenant_access_token THEO APP — cache 2 tầng: L1 in-memory, L2 Postgres.

    app_id rỗng = app mặc định của platform (LARK_NOTIFY/MINH_ANH). App khác
    (vd Sawadee HAPAS) phải có secret trong _LARK_APPS — không có thì trả "",
    caller báo lỗi rõ thay vì âm thầm gửi bằng bot sai (bot đó không ở trong nhóm).
    Cache L2 (bảng lark_token_cache, key app_id) để MỌI service/agent xài chung
    một token mỗi app, không mỗi nơi tự fetch (đồng bộ + tiết kiệm call, sống qua restart).
    """

    import time as _t
    app_id = app_id or LARK_APP_ID
    secret = _LARK_APPS.get(app_id, "")
    if not (app_id and secret):
        return ""
    now = _t.time()
    ent = _LARK_TOKEN.get(app_id)
    if ent and ent["value"] and now < ent["exp"]:
        return ent["value"]
    # L2: token còn hạn do service khác vừa lấy?
    try:
        with _db() as conn:
            row = conn.execute(
                "SELECT token, extract(epoch from expire_at) AS exp "
                "FROM lark_token_cache WHERE app_id=%s", (app_id,)).fetchone()
        if row and row["token"] and row["exp"] and now < float(row["exp"]):
            _LARK_TOKEN[app_id] = {"value": row["token"], "exp": float(row["exp"])}
            return row["token"]
    except Exception:
        pass
    r = requests.post(
        f"{LARK_DOMAIN}/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": secret}, timeout=10)
    d = r.json()
    if d.get("code") != 0:
        return ""
    exp = now + int(d.get("expire", 7200)) - 120
    _LARK_TOKEN[app_id] = {"value": d["tenant_access_token"], "exp": exp}
    try:
        with _db() as conn:
            conn.execute(
                "INSERT INTO lark_token_cache (app_id, token, expire_at) "
                "VALUES (%s,%s,to_timestamp(%s)) ON CONFLICT (app_id) DO UPDATE "
                "SET token=EXCLUDED.token, expire_at=EXCLUDED.expire_at",
                (app_id, d["tenant_access_token"], exp))
            conn.commit()
    except Exception:
        pass
    return d["tenant_access_token"]


def _lark_env_prefix(app_id: str) -> str:
    """Tiền tố env đã khai app_id này (vd 'LYLY' cho LYLY_LARK_APP_ID) — dùng để in
    đúng lệnh `add-lark-app.sh <PREFIX> <app_id> <service>` trong cảnh báo AG-OPS.

    Đọc LARK_APP_PREFIXES (compose ghép sẵn, KHÔNG chứa secret) trước, vì container
    platform_api cố tình không nhận các biến <PREFIX>_LARK_APP_* của app phụ.
    """
    try:
        pref = json.loads(os.environ.get("LARK_APP_PREFIXES") or "{}").get(app_id)
        if pref:
            return str(pref)
    except Exception:
        pass
    for k, v in os.environ.items():
        if k.endswith("_LARK_APP_ID") and (v or "").strip() == app_id:
            return k[: -len("_LARK_APP_ID")]
    return ""


def _lark_gateway_gaps(conn) -> list:
    """Agent 'active' có app Lark riêng nhưng platform KHÔNG dùng được app_secret của app đó.

    Triệu chứng đã gặp 3 lần (Sawadee, AG-HARRY, AG-KD-MATE-MADE): container gateway
    vẫn 'running', binding + grant + status đều xanh trên console, nhưng gateway bỏ qua
    long-connection vì thiếu secret → agent không nhận được một tin nào, và platform
    cũng không gửi trả lời bằng đúng bot được. Không ai thấy vì cảnh báo chỉ nằm
    trong log container. Kiểm 2 mức: (1) có secret không, (2) secret còn dùng được không
    (token bị cache nên gần như không tốn call).
    """
    rows = conn.execute(
        "SELECT DISTINCT coalesce(a.lark_app_id, r.app_id) AS app_id, a.agent_id, a.owner "
        "FROM agents a LEFT JOIN routing_binding r "
        "  ON r.agent_id = a.agent_id AND r.active AND r.channel = 'lark' "
        "WHERE a.status = 'active' AND coalesce(a.lark_app_id, r.app_id) IS NOT NULL "
        "ORDER BY 2").fetchall()
    out = []
    for r in rows:
        app_id = (r["app_id"] or "").strip()
        if not app_id:
            continue
        if app_id not in _LARK_APPS:
            reason = "platform chưa có app_secret của app này"
        elif not _lark_token(app_id):
            reason = "app_secret platform đang giữ bị Lark từ chối (sai hoặc đã thu hồi)"
        else:
            continue
        prefix = _lark_env_prefix(app_id)
        out.append({"agent_id": r["agent_id"], "owner": r["owner"], "app_id": app_id,
                    "reason": reason, "env_prefix": prefix,
                    "service": f"event_gateway_{prefix.lower()}" if prefix else ""})
    return out


def _identity_cache_get(email: str) -> str | None:
    try:
        with _db() as conn:
            row = conn.execute(
                "SELECT open_id FROM lark_identity_cache WHERE email=%s",
                ((email or "").lower(),)).fetchone()
        return row["open_id"] if row and row["open_id"] else None
    except Exception:
        return None


def _identity_cache_put(email: str, open_id: str) -> None:
    if not (email and open_id):
        return
    try:
        with _db() as conn:
            conn.execute(
                "INSERT INTO lark_identity_cache (email, open_id, updated_at) "
                "VALUES (%s,%s,now()) ON CONFLICT (email) DO UPDATE "
                "SET open_id=EXCLUDED.open_id, updated_at=now()",
                ((email or "").lower(), open_id))
            conn.commit()
    except Exception:
        pass


def _lark_open_id(email: str, token: str) -> str:
    """Tra open_id từ email công ty (cần scope contact:user.id:readonly).

    Ưu tiên cache danh tính dùng chung (Postgres) → mọi agent tra 1 lần, dùng lại.
    """

    cached = _identity_cache_get(email)
    if cached:
        return cached
    r = requests.post(
        f"{LARK_DOMAIN}/open-apis/contact/v3/users/batch_get_id?user_id_type=open_id",
        headers={"Authorization": f"Bearer {token}"},
        json={"emails": [email]}, timeout=10)
    try:
        for u in (r.json().get("data") or {}).get("user_list") or []:
            if u.get("user_id"):
                _identity_cache_put(email, u["user_id"])
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
    db_hit = _identity_cache_get(key)   # cache dùng chung (Postgres)
    if db_hit:
        _ENT_EMAIL_CACHE[key] = db_hit
        return db_hit
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
                        _identity_cache_put(em, u.get("open_id", ""))  # write-through DB
            if key in _ENT_EMAIL_CACHE:
                return _ENT_EMAIL_CACHE[key]
            if not d.get("has_more"):
                break
            page = d.get("page_token") or ""
        return ""

    # Duyệt toàn bộ cây phòng ban (fetch_child) — user có thể ở dept con.
    # QUAN TRỌNG: /users?department_id= mặc định nhận OPEN department_id (od-xxx) —
    # dùng department_id thường sẽ bị 400 ở MỌI dept con (bug đã sửa 08-14).
    dept_ids = ["0"]
    page = ""
    for _ in range(30):
        url = (f"{LARK_DOMAIN}/open-apis/contact/v3/departments?parent_department_id=0"
               f"&fetch_child=true&page_size=50" + (f"&page_token={page}" if page else ""))
        try:
            d = (requests.get(url, headers=h, timeout=15).json().get("data") or {})
        except Exception:
            break
        dept_ids += [x.get("open_department_id") or x.get("department_id")
                     for x in (d.get("items") or [])
                     if x.get("open_department_id") or x.get("department_id")]
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


def _lark_send_to(receive_id: str, id_type: str, *, text: str = "",
                  markdown: str = "", app_id: str = "") -> tuple[bool, str]:
    """Gửi 1 tin tới receive_id (open_id|email|chat_id). Trả (ok, detail).

    app_id: gửi bằng bot của app đó (job đến từ app nào trả lời bằng app đó);
    rỗng = app mặc định. App chưa có secret trên VM → lỗi RÕ, không gửi bot sai.
    """

    if app_id and app_id not in _LARK_APPS:
        return False, f"app {app_id} chưa có secret trên VM — thêm vào /opt/lsr-platform/.env"
    token = _lark_token(app_id)
    if not token:
        return False, "no lark token (thiếu LARK_APP_ID/SECRET)"
    if markdown:
        msg_type = "interactive"
        content = json.dumps({
            "config": {"wide_screen_mode": True},
            "elements": [{"tag": "markdown", "content": markdown}],
        }, ensure_ascii=False)
    else:
        msg_type, content = "text", json.dumps({"text": text}, ensure_ascii=False)
    try:
        r = requests.post(
            f"{LARK_DOMAIN}/open-apis/im/v1/messages?receive_id_type={id_type}",
            headers={"Authorization": f"Bearer {token}"},
            json={"receive_id": receive_id, "msg_type": msg_type, "content": content},
            timeout=10)
        d = r.json()
        return d.get("code") == 0, str(d.get("msg"))[:160]
    except Exception as exc:
        return False, str(exc)[:160]


# ==================== Lark broker dùng chung (agent token) ====================
# Mọi agent gọi Lark QUA ĐÂY: không cầm app_secret, không tự resolve open_id, không
# tự cache token. Đồng bộ nhờ cache token + danh tính dùng chung ở Postgres.

# ---------------- C8: User Identity Broker cho Lark ----------------
# Vì sao tồn tại: một số API Lark CHỈ nhận user token (Approval v4 trả thẳng
# "only supports: user" khi gọi bằng tenant token). Agent không được cầm token của
# người/account thật, nên platform đứng giữa: giữ token (mã hoá), tự refresh, kiểm
# quyền theo allowlist path, audit + metering từng lời gọi.
#
# Thiết kế then chốt: MỘT proxy có allowlist path, không phải N endpoint cho từng
# nhóm API. Thêm Approval hôm nay, Task/Docs tháng sau = thêm một dòng grant, không
# phải PR vào core.

_LARK_USER_SESSION_TTL = 900          # phiên authorize chờ người bấm đồng ý
# Scope mặc định theo "domain" nghiệp vụ để người cấp quyền không phải nhớ tên scope.
_LARK_USER_SCOPES = {
    "approval": ["approval:approval:readonly", "approval:instance",
                 "approval:instance:readonly"],
    "task": ["task:task", "task:task:read"],
    "docs": ["docx:document:readonly", "drive:drive:readonly"],
    "im": ["im:message", "im:chat:readonly"],
}


def _lark_user_scope_str(domains: str) -> str:
    """'approval,task' → chuỗi scope Lark + offline_access (bắt buộc để có refresh)."""
    out: list = ["offline_access"]
    for d in [x.strip().lower() for x in (domains or "").split(",") if x.strip()]:
        if d not in _LARK_USER_SCOPES:
            raise HTTPException(status_code=422,
                                detail=f"domain '{d}' chưa hỗ trợ — chọn: {sorted(_LARK_USER_SCOPES)}")
        out += _LARK_USER_SCOPES[d]
    if len(out) == 1:
        raise HTTPException(status_code=422, detail="cần ít nhất 1 domain (vd approval)")
    return " ".join(dict.fromkeys(out))


def _lark_user_redirect_uri() -> str:
    if not CONSOLE_BASE_URL:
        raise HTTPException(status_code=503, detail="thiếu CONSOLE_BASE_URL")
    return f"{CONSOLE_BASE_URL}/api/auth/lark-user/callback"


def _lark_user_store(conn, subject: str, d: dict, *, app_id: str, granted_by: str,
                     scope: str, open_id: str = "", name: str = "") -> None:
    """Ghi/cập nhật identity. access + refresh đều mã hoá; expiry tính từ 'expires_in'."""
    at, rt = d.get("access_token") or "", d.get("refresh_token") or ""
    if not (at and rt):
        raise HTTPException(status_code=502,
                            detail="Lark không trả refresh_token — app thiếu scope offline_access")
    conn.execute(
        "INSERT INTO lark_user_identities (subject_email, open_id, name, app_id, "
        "  access_token_enc, refresh_token_enc, scope, expires_at, refresh_expires_at, "
        "  granted_by, updated_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s, now() + make_interval(secs => %s), "
        "        now() + make_interval(secs => %s), %s, now()) "
        "ON CONFLICT (subject_email) DO UPDATE SET open_id=EXCLUDED.open_id, "
        "  name=coalesce(EXCLUDED.name, lark_user_identities.name), app_id=EXCLUDED.app_id, "
        "  access_token_enc=EXCLUDED.access_token_enc, "
        "  refresh_token_enc=EXCLUDED.refresh_token_enc, scope=EXCLUDED.scope, "
        "  expires_at=EXCLUDED.expires_at, refresh_expires_at=EXCLUDED.refresh_expires_at, "
        "  granted_by=EXCLUDED.granted_by, updated_at=now()",
        (subject, open_id, name or None, app_id, _enc_token(at), _enc_token(rt), scope,
         int(d.get("expires_in") or 7200), int(d.get("refresh_token_expires_in") or 2592000),
         granted_by))


def _lark_user_token(conn, subject: str) -> str:
    """user_access_token còn hạn của subject, tự refresh khi gần hết.

    Refresh là TRẠNG THÁI DÙNG CHUNG: hai tiến trình cùng refresh một account sẽ
    vô hiệu hoá token của nhau (platform từng mất phiên NotebookLM đúng vì vậy).
    Nên khoá hàng bằng SELECT ... FOR UPDATE trước khi gọi Lark.
    """
    row = conn.execute(
        "SELECT access_token_enc, refresh_token_enc, app_id, scope, "
        "  extract(epoch from (expires_at - now())) AS ttl, "
        "  extract(epoch from (refresh_expires_at - now())) AS rttl "
        "FROM lark_user_identities WHERE subject_email=%s FOR UPDATE", (subject,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"chưa có identity cho {subject}")
    if float(row["rttl"] or 0) <= 0:
        raise HTTPException(status_code=401,
                            detail=f"refresh token của {subject} đã hết hạn — admin phải authorize lại")
    if float(row["ttl"] or 0) > 120:
        return _dec_token(row["access_token_enc"])
    secret = _LARK_APPS.get(row["app_id"], "")
    if not secret:
        raise HTTPException(status_code=503,
                            detail=f"platform không còn app_secret của {row['app_id']} để refresh")
    r = requests.post(f"{LARK_DOMAIN}/open-apis/authen/v2/oauth/token", json={
        "grant_type": "refresh_token", "client_id": row["app_id"], "client_secret": secret,
        "refresh_token": _dec_token(row["refresh_token_enc"])}, timeout=15)
    d = r.json() if r.content else {}
    if not d.get("access_token"):
        raise HTTPException(status_code=401, detail="refresh thất bại: "
                            f"{d.get('error_description') or d.get('msg') or d.get('error')}")
    _lark_user_store(conn, subject, d, app_id=row["app_id"], granted_by="refresh",
                     scope=d.get("scope") or row["scope"])
    _audit(conn, "platform", "lark_user_refresh", "lark_user", subject, {"app_id": row["app_id"]})
    conn.commit()
    return d["access_token"]


@app.post("/v1/lark/user/authorize/start")
def lark_user_authorize_start(body: dict, authorization: str = Header(default="")) -> dict:
    """(admin) Tạo phiên authorize → trả URL để mở trên máy nào cũng được + state để poll.

    Bắt buộc có người: chỉ chủ account đó đăng nhập và bấm đồng ý mới ra token.
    """
    _require_admin(authorization)
    _ensure_schema()
    if not _user_token_cipher():
        raise HTTPException(status_code=503,
                            detail="thiếu LARK_USER_TOKEN_KEY trên VM — không lưu token dạng rõ")
    subject = (body.get("subject") or "").strip().lower()
    if not subject or "@" not in subject:
        raise HTTPException(status_code=422, detail="cần subject là email account")
    domain = subject.split("@")[-1]
    if ALLOWED_LOGIN_DOMAINS and domain not in ALLOWED_LOGIN_DOMAINS:
        raise HTTPException(status_code=403, detail=f"email @{domain} không thuộc org")
    scope = _lark_user_scope_str(body.get("domains") or "approval")
    app_id = (body.get("app_id") or LARK_APP_ID or "").strip()
    if not (app_id and _LARK_APPS.get(app_id)):
        raise HTTPException(status_code=503, detail=f"platform không có app_secret của app {app_id or '(rỗng)'}")
    from urllib.parse import quote
    ts = str(int(time.time()))
    state = f"u{ts}.{_oauth_sign('user:' + ts + subject)}"
    actor = _actor_of(authorization)
    with _db() as conn:
        conn.execute("DELETE FROM lark_user_authorize_sessions WHERE expires_at < now()")
        conn.execute(
            "INSERT INTO lark_user_authorize_sessions (state, subject_email, scope, app_id, "
            "requested_by, expires_at) VALUES (%s,%s,%s,%s,%s, now() + make_interval(secs => %s))",
            (state, subject, scope, app_id, actor, _LARK_USER_SESSION_TTL))
        _audit(conn, actor, "lark_user_authorize_start", "lark_user", subject,
               {"scope": scope, "app_id": app_id})
        conn.commit()
    url = (f"{LARK_DOMAIN}/open-apis/authen/v1/authorize?app_id={app_id}"
           f"&redirect_uri={quote(_lark_user_redirect_uri(), safe='')}"
           f"&scope={quote(scope, safe='')}&state={state}")
    return {"url": url, "state": state, "subject": subject, "scope": scope,
            "expires_in": _LARK_USER_SESSION_TTL,
            "next": f"Đăng nhập Lark BẰNG CHÍNH account {subject} rồi bấm đồng ý, "
                    f"sau đó poll /v1/lark/user/authorize/poll?state=..."}


@app.post("/v1/lark/user/authorize/callback")
def lark_user_authorize_callback(body: dict) -> dict:
    """Console gọi vào sau khi Lark redirect về: đổi code lấy token và lưu."""
    _ensure_schema()
    code = (body.get("code") or "").strip()
    state = (body.get("state") or "").strip()
    if not (code and state):
        raise HTTPException(status_code=400, detail="thiếu code/state")
    with _db() as conn:
        ses = conn.execute(
            "SELECT * FROM lark_user_authorize_sessions WHERE state=%s AND expires_at > now()",
            (state,)).fetchone()
        if not ses:
            raise HTTPException(status_code=400, detail="phiên authorize không hợp lệ hoặc đã hết hạn")
        secret = _LARK_APPS.get(ses["app_id"], "")
        r = requests.post(f"{LARK_DOMAIN}/open-apis/authen/v2/oauth/token", json={
            "grant_type": "authorization_code", "client_id": ses["app_id"],
            "client_secret": secret, "code": code,
            "redirect_uri": _lark_user_redirect_uri()}, timeout=15)
        d = r.json() if r.content else {}
        if not d.get("access_token"):
            err = d.get("error_description") or d.get("msg") or d.get("error") or "?"
            conn.execute("UPDATE lark_user_authorize_sessions SET status='error', error=%s "
                         "WHERE state=%s", (str(err)[:200], state))
            conn.commit()
            raise HTTPException(status_code=401, detail=f"Lark từ chối code: {err}")
        # Người vừa đồng ý PHẢI đúng account được yêu cầu — nếu không thì token sẽ
        # hành động dưới danh nghĩa người khác, đúng thứ cơ chế này phải ngăn.
        u = requests.get(f"{LARK_DOMAIN}/open-apis/authen/v1/user_info",
                         headers={"Authorization": f"Bearer {d['access_token']}"},
                         timeout=15).json()
        info = u.get("data") or {}
        email = (info.get("enterprise_email") or info.get("email") or "").strip().lower()
        if email != ses["subject_email"]:
            conn.execute("UPDATE lark_user_authorize_sessions SET status='error', error=%s "
                         "WHERE state=%s", (f"đăng nhập bằng {email or '?'}", state))
            _audit(conn, ses["requested_by"], "lark_user_authorize_wrong_account", "lark_user",
                   ses["subject_email"], {"got": email})
            conn.commit()
            raise HTTPException(status_code=403,
                                detail=f"đã đăng nhập bằng {email or '?'} chứ không phải "
                                       f"{ses['subject_email']} — đăng xuất Lark rồi thử lại")
        _lark_user_store(conn, email, d, app_id=ses["app_id"], granted_by=ses["requested_by"],
                         scope=d.get("scope") or ses["scope"], open_id=info.get("open_id") or "",
                         name=info.get("name") or "")
        conn.execute("UPDATE lark_user_authorize_sessions SET status='done' WHERE state=%s", (state,))
        _audit(conn, ses["requested_by"], "lark_user_authorize_done", "lark_user", email,
               {"scope": d.get("scope") or ses["scope"], "app_id": ses["app_id"]})
        conn.commit()
    return {"ok": True, "subject": email}


@app.get("/v1/lark/user/authorize/poll")
def lark_user_authorize_poll(state: str, authorization: str = Header(default="")) -> dict:
    """(admin) Trạng thái phiên authorize — để CLI chờ mà không cần browser tại chỗ."""
    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        r = conn.execute("SELECT subject_email, status, error, expires_at < now() AS expired "
                         "FROM lark_user_authorize_sessions WHERE state=%s", (state,)).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="không thấy phiên")
    return {"subject": r["subject_email"],
            "status": "expired" if (r["expired"] and r["status"] == "pending") else r["status"],
            "error": r["error"]}


@app.post("/v1/lark/user/grants")
def lark_user_grant(body: dict, authorization: str = Header(default="")) -> dict:
    """(admin) Cho agent quyền hành động dưới danh nghĩa subject, GIỚI HẠN theo path."""
    _require_admin(authorization)
    _ensure_schema()
    agent_id = (body.get("agent_id") or "").strip()
    subject = (body.get("subject") or "").strip().lower()
    prefixes = [str(p).strip() for p in (body.get("path_prefixes") or []) if str(p).strip()]
    methods = [str(m).strip().upper() for m in (body.get("methods") or ["GET", "POST"])]
    if not (agent_id and subject and prefixes):
        raise HTTPException(status_code=422, detail="cần agent_id, subject, path_prefixes")
    for p in prefixes:
        if not p.startswith("/open-apis/"):
            raise HTTPException(status_code=422, detail=f"path_prefix phải bắt đầu /open-apis/: {p}")
    actor = _actor_of(authorization)
    with _db() as conn:
        if not conn.execute("SELECT 1 FROM agents WHERE agent_id=%s", (agent_id,)).fetchone():
            raise HTTPException(status_code=404, detail="không thấy agent")
        if not conn.execute("SELECT 1 FROM lark_user_identities WHERE subject_email=%s",
                            (subject,)).fetchone():
            raise HTTPException(status_code=404, detail=f"chưa authorize identity {subject}")
        conn.execute(
            "INSERT INTO agent_user_identity_grants (agent_id, subject_email, path_prefixes, "
            "methods, active, granted_by) VALUES (%s,%s,%s,%s,true,%s) "
            "ON CONFLICT (agent_id, subject_email) DO UPDATE SET path_prefixes=EXCLUDED.path_prefixes, "
            "methods=EXCLUDED.methods, active=true, granted_by=EXCLUDED.granted_by",
            (agent_id, subject, prefixes, methods, actor))
        # Ghi theo SUBJECT (không theo agent): §3.5 đòi dựng lại được "ai làm gì lúc nào"
        # trên một danh tính con người. Mọi sự kiện C8 của account đó — authorize, grant,
        # call, refresh, revoke — phải cùng target_id để truy một lượt là ra hết.
        _audit(conn, actor, "lark_user_grant", "lark_user", subject,
               {"agent_id": agent_id, "path_prefixes": prefixes, "methods": methods})
        conn.commit()
    return {"ok": True, "agent_id": agent_id, "subject": subject, "path_prefixes": prefixes,
            "methods": methods}


@app.get("/v1/lark/user/identities")
def lark_user_identities(authorization: str = Header(default="")) -> list:
    """(admin) Danh sách identity + grant. KHÔNG bao giờ trả token."""
    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        rows = conn.execute(
            "SELECT i.subject_email, i.name, i.open_id, i.app_id, i.scope, i.granted_by, "
            "  i.expires_at, i.refresh_expires_at, i.last_used_at, "
            "  floor(extract(epoch from (i.refresh_expires_at - now()))/86400)::int AS refresh_days_left, "
            "  coalesce(json_agg(json_build_object('agent_id', g.agent_id, 'paths', g.path_prefixes, "
            "    'methods', g.methods, 'active', g.active)) FILTER (WHERE g.agent_id IS NOT NULL), "
            "    '[]') AS grants "
            "FROM lark_user_identities i "
            "LEFT JOIN agent_user_identity_grants g ON g.subject_email = i.subject_email "
            "GROUP BY i.subject_email ORDER BY i.subject_email").fetchall()
    return [dict(r) for r in rows]


@app.post("/v1/lark/user/identities/{subject}/revoke")
def lark_user_revoke(subject: str, authorization: str = Header(default="")) -> dict:
    """(admin) Thu hồi: xoá token + tắt mọi grant. Lời gọi ngay sau đó phải 403/404."""
    _require_admin(authorization)
    _ensure_schema()
    subject = subject.strip().lower()
    actor = _actor_of(authorization)
    with _db() as conn:
        n = conn.execute("UPDATE agent_user_identity_grants SET active=false "
                         "WHERE subject_email=%s", (subject,)).rowcount
        d = conn.execute("DELETE FROM lark_user_identities WHERE subject_email=%s",
                         (subject,)).rowcount
        _audit(conn, actor, "lark_user_revoke", "lark_user", subject,
               {"grants_off": n, "identity_deleted": d})
        conn.commit()
    if not d:
        raise HTTPException(status_code=404, detail=f"không thấy identity {subject}")
    return {"ok": True, "subject": subject, "grants_off": n}


@app.get("/v1/lark/user/status")
def lark_user_status(subject: str, authorization: str = Header(default="")) -> dict:
    """Agent tự kiểm trước khi dùng → degrade rõ ràng thay vì lỗi mù giữa việc."""
    agent_id = _require_self(authorization)
    _ensure_schema()
    subject = (subject or "").strip().lower()
    with _db() as conn:
        g = conn.execute(
            "SELECT path_prefixes, methods, active FROM agent_user_identity_grants "
            "WHERE agent_id=%s AND subject_email=%s", (agent_id, subject)).fetchone()
        i = conn.execute(
            "SELECT scope, expires_at, refresh_expires_at, "
            "  floor(extract(epoch from (refresh_expires_at - now()))/86400)::int AS refresh_days_left "
            "FROM lark_user_identities WHERE subject_email=%s", (subject,)).fetchone()
    if not (g and g["active"] and i):
        return {"connected": False, "subject": subject,
                "reason": "chưa có identity" if not i else
                          ("grant đã tắt" if g else "agent chưa được grant subject này")}
    return {"connected": True, "subject": subject, "scope": i["scope"],
            "expires_at": i["expires_at"], "refresh_expires_at": i["refresh_expires_at"],
            "refresh_days_left": i["refresh_days_left"],
            "path_prefixes": g["path_prefixes"], "methods": g["methods"]}


@app.post("/v1/lark/user/call")
def lark_user_call(body: dict, authorization: str = Header(default="")) -> dict:
    """Proxy gọi Lark bằng user token của subject. Agent KHÔNG bao giờ thấy token.

    Chặn 3 tầng: connector 'lark_user' → grant còn active → path/method trong allowlist.
    """
    _t0 = time.time()
    agent_id = _require_self(authorization)
    _ensure_schema()
    subject = (body.get("subject") or "").strip().lower()
    method = (body.get("method") or "GET").strip().upper()
    path = (body.get("path") or "").strip()
    if not (subject and path.startswith("/open-apis/")):
        raise HTTPException(status_code=422, detail="cần subject và path bắt đầu bằng /open-apis/")
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        raise HTTPException(status_code=422, detail=f"method không hỗ trợ: {method}")
    if ".." in path:
        raise HTTPException(status_code=422, detail="path không hợp lệ")

    with _db() as conn:
        _require_connector(conn, agent_id, "lark_user", "call")
        g = conn.execute(
            "SELECT path_prefixes, methods, active FROM agent_user_identity_grants "
            "WHERE agent_id=%s AND subject_email=%s", (agent_id, subject)).fetchone()
        if not g or not g["active"]:
            _meter(conn, agent_id, "lark_user", "call", ok=False, error="no grant")
            _audit(conn, agent_id, "lark_user_denied", "lark_user", subject,
                   {"path": path, "reason": "chưa có grant hoặc grant đã tắt"})
            conn.commit()
            raise HTTPException(status_code=403,
                                detail=f"agent {agent_id} chưa được cấp quyền hành động dưới "
                                       f"danh nghĩa {subject} (hoặc grant đã bị thu hồi)")
        if not any(path.startswith(p) for p in (g["path_prefixes"] or [])):
            _meter(conn, agent_id, "lark_user", "call", ok=False, error="path off allowlist")
            _audit(conn, agent_id, "lark_user_denied", "lark_user", subject,
                   {"path": path, "reason": "path ngoài allowlist",
                    "allowed": g["path_prefixes"]})
            conn.commit()
            raise HTTPException(status_code=403,
                                detail=f"path {path} ngoài phạm vi được cấp: {g['path_prefixes']}")
        if method not in (g["methods"] or []):
            _meter(conn, agent_id, "lark_user", "call", ok=False, error="method off allowlist")
            _audit(conn, agent_id, "lark_user_denied", "lark_user", subject,
                   {"path": path, "method": method, "allowed": g["methods"]})
            conn.commit()
            raise HTTPException(status_code=403,
                                detail=f"method {method} không được cấp (chỉ {g['methods']})")
        token = _lark_user_token(conn, subject)

    try:
        r = requests.request(method, LARK_DOMAIN + path,
                            headers={"Authorization": f"Bearer {token}",
                                     "Content-Type": "application/json"},
                            params=body.get("query") or None,
                            json=body.get("body") if method != "GET" else None, timeout=30)
        payload = r.json() if r.content else {}
        status, err = r.status_code, "" if r.ok else str(payload)[:200]
    except Exception as exc:
        payload, status, err = {"error": str(exc)}, 502, str(exc)[:200]

    with _db() as conn:
        conn.execute("UPDATE lark_user_identities SET last_used_at=now() WHERE subject_email=%s",
                     (subject,))
        _audit(conn, agent_id, "lark_user_call", "lark_user", subject,
               {"method": method, "path": path, "http": status, "lark_code": payload.get("code")})
        _meter(conn, agent_id, "lark_user", "call", ok=(status < 400),
               latency_ms=int((time.time() - _t0) * 1000), error=err)
        conn.commit()
    return {"http_status": status, "data": payload}


@app.post("/v1/lark/resolve")
def lark_resolve(body: dict, authorization: str = Header(default="")) -> dict:
    """email → open_id (dùng cache danh tính chung)."""

    _require_self(authorization)
    _ensure_schema()
    email = (body.get("email") or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="thiếu email")
    token = _lark_token()
    if not token:
        raise HTTPException(status_code=503, detail="Lark chưa cấu hình (LARK_APP_ID/SECRET)")
    open_id = _lark_open_id(email, token)
    return {"email": email, "open_id": open_id or None,
            "cached": bool(_identity_cache_get(email))}


@app.post("/v1/lark/send")
def lark_send(body: dict, authorization: str = Header(default="")) -> dict:
    """Gửi tin Lark thay cho agent. body: {to, to_type?, text?|markdown?, app_id?}.

    to_type: email (mặc định) | open_id | chat_id. Với email sẽ tự resolve→open_id;
    nếu chưa tra được và có LARK_NOTIFY_CHAT_ID thì rơi về nhóm chung (không mất tin).
    app_id: gửi bằng bot của app đó (rỗng = app mặc định của platform).
    """

    agent_id = _require_self(authorization)
    _ensure_schema()
    to = (body.get("to") or "").strip()
    to_type = (body.get("to_type") or "email").strip()
    text = body.get("text") or ""
    markdown = body.get("markdown") or ""
    send_app = (body.get("app_id") or "").strip()
    if not to or not (text or markdown):
        raise HTTPException(status_code=400, detail="cần 'to' và 'text' hoặc 'markdown'")
    # P5: adapter chuẩn — kiểm quyền connector trước khi ra ngoài + đo usage.
    _t0 = time.time()
    with _db() as conn:
        _require_connector(conn, agent_id, "lark", "send")
        conn.commit()

    if to_type == "email":
        # Resolve email→open_id bằng token của app sẽ gửi (scope contact theo từng app).
        token = _lark_token(send_app) or _lark_token()
        open_id = _lark_open_id(to, token) if token else ""
        if open_id:
            receive_id, id_type = open_id, "open_id"
        elif LARK_NOTIFY_CHAT_ID:
            receive_id, id_type = LARK_NOTIFY_CHAT_ID, "chat_id"
            if text:
                text = f"@{to}: {text}"
            if markdown:
                markdown = f"**@{to}**\n{markdown}"
        else:
            raise HTTPException(status_code=422,
                                detail="chưa resolve được email→open_id và không có nhóm fallback")
    else:
        receive_id, id_type = to, to_type

    ok, detail = _lark_send_to(receive_id, id_type, text=text, markdown=markdown,
                               app_id=send_app)
    with _db() as conn:
        _audit(conn, agent_id, "lark_send", "lark", f"{id_type}:{receive_id[:24]}",
               {"ok": ok, "detail": detail, "via": to_type, "app_id": send_app or None})
        _meter(conn, agent_id, "lark", "send", ok=ok,
               latency_ms=int((time.time() - _t0) * 1000), error="" if ok else detail)
        conn.commit()
    if not ok:
        raise HTTPException(status_code=502, detail=f"Lark từ chối: {detail}")
    return {"ok": True, "receive_id_type": id_type, "detail": detail}


@app.get("/v1/lark/chats")
def lark_chats(authorization: str = Header(default=""), app_id: str = "") -> dict:
    """Liệt kê các nhóm mà BOT đang tham gia (để agent biết chat_id gửi vào).

    app_id: xem nhóm của bot app đó (vd Sawadee HAPAS); rỗng = bot mặc định platform.
    """

    _require_self(authorization)
    if app_id and app_id not in _LARK_APPS:
        raise HTTPException(status_code=503,
                            detail=f"app {app_id} chưa có secret trên VM (.env)")
    token = _lark_token(app_id)
    if not token:
        raise HTTPException(status_code=503, detail="Lark chưa cấu hình")
    try:
        r = requests.get(f"{LARK_DOMAIN}/open-apis/im/v1/chats?page_size=100",
                         headers={"Authorization": f"Bearer {token}"}, timeout=10)
        items = (r.json().get("data") or {}).get("items") or []
        return {"app_id": app_id or LARK_APP_ID,
                "chats": [{"chat_id": c.get("chat_id"), "name": c.get("name")}
                          for c in items]}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:160])


@app.get("/v1/lark/resource/{message_id}/{file_key}")
def lark_resource(message_id: str, file_key: str, type: str = "file", app_id: str = "",
                  authorization: str = Header(default="")):
    """Tải file/media đính kèm 1 tin Lark (vd recording cuộc họp) — stream về agent.

    C1: gateway đẩy file_key trong payload; agent gọi endpoint này để lấy nội dung,
    KHÔNG cần cầm app_secret. type: file (mặc định) | image. app_id = app đã nhận tin
    (lấy từ reply_to.app_id của job) để dùng đúng tenant token.
    """

    agent_id = _require_self(authorization)
    _ensure_schema()
    _t0 = time.time()
    with _db() as conn:
        _require_connector(conn, agent_id, "lark", "resource")
        conn.commit()
    if app_id and app_id not in _LARK_APPS:
        raise HTTPException(status_code=503,
                            detail=f"app {app_id} chưa có secret trên VM (.env)")
    token = _lark_token(app_id)
    if not token:
        raise HTTPException(status_code=503, detail="Lark chưa cấu hình")
    url = (f"{LARK_DOMAIN}/open-apis/im/v1/messages/{message_id}"
           f"/resources/{file_key}?type={type}")
    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"},
                         stream=True, timeout=120)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:160])
    ctype = r.headers.get("content-type", "application/octet-stream")
    if r.status_code != 200 or ctype.startswith("application/json"):
        # Lark trả lỗi dạng JSON (code/msg) — chuyển tiếp cho agent biết vì sao.
        try:
            detail = str(r.json().get("msg"))[:160]
        except Exception:
            detail = f"http {r.status_code}"
        with _db() as conn:
            _meter(conn, agent_id, "lark", "resource", ok=False,
                   latency_ms=int((time.time() - _t0) * 1000), error=detail)
            conn.commit()
        raise HTTPException(status_code=502, detail=f"Lark từ chối: {detail}")
    with _db() as conn:
        _meter(conn, agent_id, "lark", "resource", ok=True,
               latency_ms=int((time.time() - _t0) * 1000))
        _audit(conn, agent_id, "lark_resource", "lark", file_key[:48],
               {"message_id": message_id, "type": type, "app_id": app_id or None})
        conn.commit()
    return StreamingResponse(r.iter_content(chunk_size=64 * 1024), media_type=ctype,
                             headers={"Content-Disposition":
                                      f'attachment; filename="{file_key}"'})


# ==================== P1: Ingress hợp nhất — routing + job queue ====================
# Mọi kênh (Lark, web chat, cron, webhook, A2A) đổ về đây. Thêm agent = thêm 1 dòng
# routing_binding; consumer (managed/tự host) lấy job qua /v1/self/jobs.

GATEWAY_INGEST_TOKEN = os.environ.get("GATEWAY_INGEST_TOKEN", "") or ADMIN_TOKEN
_STALE_LOCK_SECS = int(os.environ.get("JOB_STALE_LOCK_SECS", "120"))


def _require_ingest(authorization: str) -> None:
    """Cho phép gateway nội bộ (hoặc admin) đẩy sự kiện vào queue."""
    tok = authorization[7:] if authorization.startswith("Bearer ") else ""
    if not GATEWAY_INGEST_TOKEN or tok != GATEWAY_INGEST_TOKEN:
        raise HTTPException(status_code=401, detail="ingest token required")


def _agent_status(conn, agent_id: str) -> str | None:
    row = conn.execute("SELECT status FROM agents WHERE agent_id=%s", (agent_id,)).fetchone()
    return row["status"] if row else None


def _route(conn, channel: str, app_id: str | None, chat_id: str | None) -> str | None:
    """Tra routing_binding → agent_id. Ưu tiên khớp cụ thể (chat_id) rồi tới app_id."""
    row = conn.execute(
        """
        SELECT agent_id FROM routing_binding
        WHERE active AND channel=%s
          AND (chat_id=%s OR chat_id IS NULL)
          AND (app_id=%s OR app_id IS NULL)
        ORDER BY (chat_id IS NOT NULL) DESC, (app_id IS NOT NULL) DESC, id ASC
        LIMIT 1
        """,
        (channel, chat_id, app_id),
    ).fetchone()
    return row["agent_id"] if row else None


def _backoff_secs(attempts: int) -> int:
    return min(30 * (2 ** max(0, attempts - 1)), 3600)


def _reap_stale(conn) -> int:
    """Job 'running' quá hạn khoá (consumer chết) → retry backoff hoặc DLQ."""
    rows = conn.execute(
        """
        UPDATE jobs SET
          status = CASE WHEN attempts >= max_attempts THEN 'dlq' ELSE 'queued' END,
          run_after = now() + make_interval(secs => %s),
          locked_by = NULL, locked_at = NULL,
          last_error = coalesce(last_error,'') || ' [reaped stale lock]',
          updated_at = now()
        WHERE status='running' AND locked_at < now() - make_interval(secs => %s)
        RETURNING id
        """,
        (30, _STALE_LOCK_SECS),
    ).fetchall()
    return len(rows)


def _ingest(conn, *, channel: str, payload: dict, event_id: str | None = None,
            app_id: str | None = None, chat_id: str | None = None,
            session_id: str | None = None, reply_to: dict | None = None,
            agent_id: str | None = None) -> dict:
    """dedupe → route → enqueue. Trả {job_id|None, status, dedupe?}."""
    # Nhớ app nguồn vào reply_to → khi trả lời chọn ĐÚNG bot (app khác không ở trong nhóm).
    if app_id:
        reply_to = dict(reply_to or {})
        reply_to.setdefault("app_id", app_id)
    if event_id:
        r = conn.execute(
            "INSERT INTO event_dedupe(event_id) VALUES (%s) ON CONFLICT DO NOTHING RETURNING event_id",
            (event_id,)).fetchone()
        if not r:
            return {"job_id": None, "status": "duplicate", "dedupe": True}
    if not agent_id:
        agent_id = _route(conn, channel, app_id, chat_id)
    status = "queued"
    ag_st = _agent_status(conn, agent_id) if agent_id else None
    if not agent_id:
        status = "unrouted"
    elif ag_st == "deactivated":
        status = "rejected"     # kill-switch: nhận nhưng không cho chạy
    elif channel in ("lark", "telegram") and ag_st != "active":
        status = "rejected"     # kênh THỰC chỉ chạy khi admin đã activate; web test vẫn được
    row = conn.execute(
        """
        INSERT INTO jobs(agent_id, channel, session_id, reply_to, payload, status)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
        """,
        (agent_id, channel, session_id, Json(reply_to or {}), Json(payload or {}), status),
    ).fetchone()
    return {"job_id": row["id"], "agent_id": agent_id, "status": status}


@app.post("/v1/ingest")
def ingest_event(body: dict, authorization: str = Header(default="")) -> dict:
    """Cổng nội bộ cho gateway đẩy sự kiện đã verify. ACK nhanh (chỉ ghi DB)."""
    _require_ingest(authorization)
    _ensure_schema()
    with _db() as conn:
        res = _ingest(
            conn,
            channel=body.get("channel") or "webhook",
            payload=body.get("payload") or {},
            event_id=body.get("event_id"),
            app_id=body.get("app_id"),
            chat_id=body.get("chat_id"),
            session_id=body.get("session_id"),
            reply_to=body.get("reply_to"),
            agent_id=body.get("agent_id"),
        )
        conn.commit()
    return res


# -------- Worker API (agent lấy & báo kết quả job) --------

@app.get("/v1/self/jobs")
def self_jobs(authorization: str = Header(default=""), wait: int = 0, max: int = 1) -> list[dict]:
    """Long-poll lấy job cho agent gọi. wait giây (0=không chờ), max job/lần."""
    agent_id = _require_self(authorization)
    _ensure_schema()
    wait = min(max_wait_cap(wait), 30)
    deadline = time.time() + wait
    while True:
        with _db() as conn:
            if _agent_status(conn, agent_id) == "deactivated":
                raise HTTPException(status_code=403, detail="agent deactivated")
            _reap_stale(conn)
            claimed = []
            for _ in range(max):
                row = conn.execute(
                    """
                    UPDATE jobs SET status='running', locked_by=%s, locked_at=now(),
                                    attempts=attempts+1, updated_at=now()
                    WHERE id = (
                        SELECT id FROM jobs
                        WHERE agent_id=%s AND status='queued' AND run_after<=now()
                        ORDER BY priority ASC, id ASC
                        FOR UPDATE SKIP LOCKED LIMIT 1
                    )
                    RETURNING id, channel, session_id, reply_to, payload, attempts, max_attempts
                    """,
                    (f"{agent_id}:{os.getpid()}", agent_id),
                ).fetchone()
                if not row:
                    break
                claimed.append(dict(row))
            conn.commit()
        if claimed or time.time() >= deadline:
            return claimed
        time.sleep(1.0)


def max_wait_cap(wait: int) -> int:
    try:
        return max(0, int(wait))
    except Exception:
        return 0


@app.post("/v1/self/jobs/{job_id}/event")
def self_job_event(job_id: int, body: dict, authorization: str = Header(default="")) -> dict:
    """Ghi 1 sự kiện tiến trình của job (để SSE stream về client)."""
    agent_id = _require_self(authorization)
    with _db() as conn:
        owner = conn.execute("SELECT agent_id FROM jobs WHERE id=%s", (job_id,)).fetchone()
        if not owner or owner["agent_id"] != agent_id:
            raise HTTPException(status_code=404, detail="job không thuộc agent")
        conn.execute(
            "INSERT INTO job_events(job_id, seq, kind, data) VALUES (%s,%s,%s,%s)",
            (job_id, body.get("seq"), body.get("kind") or "message", Json(body.get("data") or {})))
        conn.commit()
    return {"ok": True}


@app.post("/v1/self/jobs/{job_id}/reply")
def self_job_reply(job_id: int, body: dict, authorization: str = Header(default="")) -> dict:
    """Trả lời một job — platform TỰ chọn kênh theo reply_to.

    Nhờ endpoint này, code agent KHÔNG cần biết tin đến từ Lark, Telegram, web chat
    hay agent khác: cứ gọi reply, platform gửi đúng chỗ. Luôn ghi job_event để
    web chat (SSE) và A2A đọc được.
    """
    agent_id = _require_self(authorization)
    _ensure_schema()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="thiếu text")
    with _db() as conn:
        job = conn.execute("SELECT agent_id, reply_to, channel FROM jobs WHERE id=%s",
                           (job_id,)).fetchone()
        if not job or job["agent_id"] != agent_id:
            raise HTTPException(status_code=404, detail="job không thuộc agent")
        rt = job["reply_to"] or {}
        ch = rt.get("channel") or job["channel"] or "web"
        # Luôn ghi event (nguồn cho SSE web chat + kết quả A2A).
        conn.execute("INSERT INTO job_events(job_id, kind, data) VALUES (%s,'message',%s)",
                     (job_id, Json({"text": text})))
        delivered = {"channel": ch, "sent": False}
        if ch == "lark" and rt.get("chat_id"):
            _require_connector(conn, agent_id, "lark", "reply")
            ok, detail = _lark_send_to(rt["chat_id"], "chat_id", text=text,
                                       app_id=rt.get("app_id") or "")
            _meter(conn, agent_id, "lark", "reply", ok=ok, error="" if ok else detail)
            delivered["sent"] = ok
            if not ok:
                delivered["error"] = detail
        elif ch == "telegram" and rt.get("chat_id"):
            ok = _tg_send(str(rt["chat_id"]), text)
            _meter(conn, agent_id, "telegram", "reply", ok=ok)
            delivered["sent"] = ok
        else:
            delivered["sent"] = True     # web/a2a: đọc qua job_events
        conn.commit()
    return {"ok": True, "job_id": job_id, **delivered}


@app.post("/v1/self/jobs/{job_id}/complete")
def self_job_complete(job_id: int, body: dict, authorization: str = Header(default="")) -> dict:
    """Báo job xong. body.usage {input_tokens, output_tokens, model, duration_ms} nếu có.

    Platform TỰ ghi 1 trace tối thiểu cho mỗi job xong → Runs/Token trên dashboard
    không còn phụ thuộc việc team nhớ cài plugin telemetry (bài học AG-BI).
    Consumer đã dùng plugin thì KHÔNG tự post thêm trace cho job để tránh đếm đôi.
    """
    agent_id = _require_self(authorization)
    usage = body.get("usage") or {}
    with _db() as conn:
        n = conn.execute(
            "UPDATE jobs SET status='done', updated_at=now(), last_error=NULL "
            "WHERE id=%s AND agent_id=%s AND status='running' RETURNING id, channel, session_id",
            (job_id, agent_id)).fetchone()
        if not n:
            raise HTTPException(status_code=409, detail="job không ở trạng thái running của agent")
        conn.execute("INSERT INTO job_events(job_id, kind, data) VALUES (%s,'done',%s)",
                     (job_id, Json(body.get("result") or {})))
        try:
            ti = int(usage.get("input_tokens") or 0)
            to = int(usage.get("output_tokens") or 0)
            conn.execute(
                "INSERT INTO agent_traces (run_id, agent_id, task_id, source, input_tokens, "
                " output_tokens, total_tokens, tool_calls, duration_ms, status, raw) "
                "VALUES (%s,%s,%s,'job_auto',%s,%s,%s,%s,%s,'ok',%s)",
                (f"job-{job_id}", agent_id, n["session_id"], ti, to, ti + to,
                 int(usage.get("tool_calls") or 0),
                 int(usage.get("duration_ms") or 0) or None,
                 Json({"channel": n["channel"], "model": usage.get("model"), "job_id": job_id})))
        except Exception:
            pass    # đếm run là best-effort — không được làm hỏng complete
        conn.commit()
    return {"ok": True}


@app.post("/v1/self/jobs/{job_id}/fail")
def self_job_fail(job_id: int, body: dict, authorization: str = Header(default="")) -> dict:
    """Báo job lỗi → retry với backoff, quá max_attempts → DLQ."""
    agent_id = _require_self(authorization)
    err = str(body.get("error") or "")[:500]
    with _db() as conn:
        row = conn.execute(
            "SELECT attempts, max_attempts FROM jobs WHERE id=%s AND agent_id=%s AND status='running'",
            (job_id, agent_id)).fetchone()
        if not row:
            raise HTTPException(status_code=409, detail="job không ở trạng thái running của agent")
        to_dlq = row["attempts"] >= row["max_attempts"]
        conn.execute(
            """
            UPDATE jobs SET status=%s, last_error=%s,
                            run_after = now() + make_interval(secs => %s), updated_at=now()
            WHERE id=%s
            """,
            ("dlq" if to_dlq else "queued", err, 0 if to_dlq else _backoff_secs(row["attempts"]), job_id))
        conn.execute("INSERT INTO job_events(job_id, kind, data) VALUES (%s,'error',%s)",
                     (job_id, Json({"error": err, "dlq": to_dlq})))
        conn.commit()
    return {"ok": True, "status": "dlq" if to_dlq else "queued"}


# -------- Admin: routing + jobs/DLQ --------

@app.get("/v1/routing")
def routing_list(authorization: str = Header(default="")) -> list[dict]:
    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, channel, app_id, chat_id, agent_id, active, created_by, created_at "
            "FROM routing_binding ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


@app.post("/v1/routing")
def routing_add(body: dict, authorization: str = Header(default="")) -> dict:
    _ensure_schema()
    agent_id = body.get("agent_id")
    channel = body.get("channel") or "lark"
    if not agent_id:
        raise HTTPException(status_code=400, detail="thiếu agent_id")
    p = _require_role(authorization, "moderator", agent_id)
    with _db() as conn:
        if not conn.execute("SELECT 1 FROM agents WHERE agent_id=%s", (agent_id,)).fetchone():
            raise HTTPException(status_code=404, detail="agent không tồn tại")
        row = conn.execute(
            "INSERT INTO routing_binding(channel, app_id, chat_id, agent_id, created_by) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (channel, body.get("app_id"), body.get("chat_id"), agent_id,
             p["actor"] or "admin")).fetchone()
        _audit(conn, p["actor"] or "admin", "routing_add", "routing",
               str(row["id"]), {"channel": channel, "agent_id": agent_id})
        conn.commit()
    return {"id": row["id"], "ok": True}


@app.post("/v1/routing/{binding_id}/toggle")
def routing_toggle(binding_id: int, authorization: str = Header(default="")) -> dict:
    _require_admin(authorization)
    with _db() as conn:
        row = conn.execute(
            "UPDATE routing_binding SET active = NOT active WHERE id=%s RETURNING active",
            (binding_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="binding không tồn tại")
        conn.commit()
    return {"id": binding_id, "active": row["active"]}


@app.get("/v1/jobs")
def jobs_list(authorization: str = Header(default=""), status: str | None = None,
              agent_id: str | None = None, limit: int = 50) -> list[dict]:
    _require_admin(authorization)
    _ensure_schema()
    q = ("SELECT id, agent_id, channel, session_id, status, attempts, max_attempts, "
         "priority, run_after, last_error, created_at, updated_at FROM jobs")
    where, args = [], []
    if status:
        where.append("status=%s"); args.append(status)
    if agent_id:
        where.append("agent_id=%s"); args.append(agent_id)
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY id DESC LIMIT %s"; args.append(min(limit, 500))
    with _db() as conn:
        rows = conn.execute(q, tuple(args)).fetchall()
    return [dict(r) for r in rows]


@app.get("/v1/jobs/{job_id}/events")
def job_events_list(job_id: int, authorization: str = Header(default="")) -> list[dict]:
    """Sự kiện của 1 job (dùng cho Chat thử trong console + soi lỗi)."""
    _require_admin(authorization)
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, kind, data, created_at FROM job_events WHERE job_id=%s ORDER BY id",
            (job_id,)).fetchall()
    return [dict(r) for r in rows]


@app.post("/v1/jobs/{job_id}/replay")
def job_replay(job_id: int, authorization: str = Header(default="")) -> dict:
    """Đưa job dlq/failed về queued, reset attempts. Dùng cho tab DLQ."""
    _require_admin(authorization)
    with _db() as conn:
        row = conn.execute(
            "UPDATE jobs SET status='queued', attempts=0, run_after=now(), "
            "locked_by=NULL, locked_at=NULL, updated_at=now() "
            "WHERE id=%s AND status IN ('dlq','failed','rejected','unrouted') RETURNING id",
            (job_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=409, detail="job không ở trạng thái replay được")
        _audit(conn, "admin", "job_replay", "job", str(job_id), {})
        conn.commit()
    return {"id": job_id, "ok": True}


# -------- Chat API (UC1): FE riêng chỉ là skin — vẫn đi qua ingress chung --------
# Mọi tin nhắn web → enqueue như kênh Lark, nên tự có telemetry/audit/quota/kill-switch.
# FE KHÔNG bao giờ gọi thẳng agent_runner.

def _chat_auth(authorization: str, token_qs: str | None, agent_id: str) -> None:
    """Cho phép: agent token của CHÍNH agent đó · admin token · phiên console từ moderator trở lên."""
    auth = authorization
    if token_qs and not auth:
        auth = f"Bearer {token_qs}"
    if ADMIN_TOKEN and auth == f"Bearer {ADMIN_TOKEN}":
        return
    if _agent_from_token(auth) == agent_id:
        return
    p = _principal(auth, agent_id)
    if p["kind"] == "session":
        # user chỉ được xem, không được chat thử (theo ma trận quyền P8)
        _require_role(auth, "moderator", agent_id)
        return
    raise HTTPException(status_code=401, detail="cần agent token của agent này hoặc đăng nhập console")


@app.post("/v1/chat/{agent_id}/messages")
def chat_message(agent_id: str, body: dict, authorization: str = Header(default="")) -> dict:
    """Gửi 1 tin nhắn web tới agent → enqueue job channel=web. Trả job_id + session_id."""
    _chat_auth(authorization, None, agent_id)
    _ensure_schema()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="thiếu text")
    session_id = body.get("session_id") or ("web-" + secrets.token_hex(8))
    with _db() as conn:
        if not conn.execute("SELECT 1 FROM agents WHERE agent_id=%s", (agent_id,)).fetchone():
            raise HTTPException(status_code=404, detail="agent không tồn tại")
        res = _ingest(
            conn, channel="web", agent_id=agent_id, session_id=session_id,
            payload={"text": text, "user_ref": body.get("user_ref")},
            reply_to={"channel": "web", "session_id": session_id},
        )
        conn.commit()
    if res["status"] == "rejected":
        raise HTTPException(status_code=403, detail="agent deactivated")
    return {"job_id": res["job_id"], "session_id": session_id, "status": res["status"]}


@app.get("/v1/chat/{agent_id}/stream")
def chat_stream(agent_id: str, session_id: str, authorization: str = Header(default=""),
                token: str | None = None, after: int = 0) -> StreamingResponse:
    """SSE: đẩy job_events của session (token|message|error|done) về client."""
    _chat_auth(authorization, token, agent_id)
    _ensure_schema()

    def gen():
        last = after
        deadline = time.time() + 120
        yield "retry: 3000\n\n"
        while time.time() < deadline:
            with _db() as conn:
                rows = conn.execute(
                    """
                    SELECT e.id, e.kind, e.data FROM job_events e
                    JOIN jobs j ON j.id = e.job_id
                    WHERE j.agent_id=%s AND j.session_id=%s AND e.id > %s
                    ORDER BY e.id ASC LIMIT 100
                    """,
                    (agent_id, session_id, last)).fetchall()
            for r in rows:
                last = r["id"]
                yield f"event: {r['kind']}\ndata: {json.dumps(r['data'], ensure_ascii=False)}\n\n"
                if r["kind"] == "done":
                    return
            time.sleep(1.0)
        yield "event: timeout\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ==================== P2: Model Auth Broker (UC3·4·5) ====================
# Ladder: subscription RIÊNG → pool subscription chung → API key (litellm).
# Trả REF (đường dẫn file trên VM), KHÔNG trả secret → token không bao giờ rời VM/qua log.

LITELLM_URL = os.environ.get("LITELLM_INTERNAL_URL", "http://litellm:4000")
DEFAULT_FALLBACK_MODEL = os.environ.get("LSR_DEFAULT_FALLBACK_MODEL", "claude-sonnet-4-5")
COOLDOWN_SECS = int(os.environ.get("MODEL_COOLDOWN_SECS", str(5 * 3600)))  # cửa sổ 5h

# "Dùng được" = active, hoặc cooldown đã hết hạn (tự hồi phục khi lease).
# "Dùng được" = active (hoặc cooldown đã hết) VÀ chưa quá hạn token.
_USABLE = ("(status='active' OR (status='cooldown' AND cooldown_until < now())) "
           "AND (expires_at IS NULL OR expires_at > now())")


def _pick_credential(conn, kind: str, exclude_id: str | None = None) -> dict | None:
    q = (f"SELECT id, kind, secret_ref, label, owner_email FROM model_credentials "
         f"WHERE kind=%s AND {_USABLE}")
    args: list = [kind]
    if exclude_id:
        q += " AND id <> %s"; args.append(exclude_id)
    q += " ORDER BY priority ASC, id ASC LIMIT 1"
    return conn.execute(q, tuple(args)).fetchone()


def _fallback_model(agent_row: dict) -> str:
    return (agent_row or {}).get("model_fallback") or DEFAULT_FALLBACK_MODEL


@app.post("/v1/self/model-auth/lease")
def model_auth_lease(authorization: str = Header(default=""), body: dict | None = None) -> dict:
    """Cấp quyền gọi model cho agent theo ladder. Trả ref + cấu hình, không trả secret."""
    agent_id = _require_self(authorization)
    _ensure_schema()
    with _db() as conn:
        a = conn.execute(
            "SELECT auth_mode, credential_id, model_fallback FROM agents WHERE agent_id=%s",
            (agent_id,)).fetchone() or {}
        mode = (a.get("auth_mode") or "pool")
        cred = None
        # ① subscription RIÊNG (own)
        if mode == "own" and a.get("credential_id"):
            cred = conn.execute(
                f"SELECT id, kind, secret_ref, label, owner_email FROM model_credentials "
                f"WHERE id=%s AND kind='subscription' AND {_USABLE}",
                (a["credential_id"],)).fetchone()
        # ② pool subscription chung
        if not cred and mode in ("own", "pool"):
            cred = _pick_credential(conn, "subscription")
        # ③ API key (litellm) — chỉ khi không còn subscription (hoặc mode=api)
        if not cred:
            api = _pick_credential(conn, "api_key")
            if api:
                _audit(conn, agent_id, "model_auth_lease", "credential", api["id"],
                       {"mode": "api", "reason": "no_subscription_available"})
                conn.commit()
                return {"mode": "api", "credential_id": api["id"], "kind": "api_key",
                        "secret_ref": api["secret_ref"], "base_url": LITELLM_URL,
                        "model": _fallback_model(a), "env_var": "ANTHROPIC_API_KEY"}
            # ④ cạn hoàn toàn → alert + 503
            _audit(conn, agent_id, "model_auth_exhausted", "agent", agent_id, {})
            try:
                _notify_admins(conn, f"⚠️ *Model Auth CẠN*: agent `{agent_id}` không còn "
                                     f"credential nào (pool + API đều hết).")
            except Exception:
                pass
            conn.commit()
            raise HTTPException(status_code=503, detail="không còn credential khả dụng (pool cạn + không có API)")
        _audit(conn, agent_id, "model_auth_lease", "credential", cred["id"],
               {"mode": "subscription"})
        conn.commit()
    return {"mode": "subscription", "credential_id": cred["id"], "kind": "subscription",
            "secret_ref": cred["secret_ref"], "env_var": "CLAUDE_CODE_OAUTH_TOKEN"}


@app.post("/v1/self/model-auth/report")
def model_auth_report(body: dict, authorization: str = Header(default="")) -> dict:
    """Agent báo trạng thái credential: limit/429 → cooldown; ok → giữ active."""
    agent_id = _require_self(authorization)
    _ensure_schema()
    cid = body.get("credential_id")
    reason = (body.get("reason") or "").lower()
    if not cid:
        raise HTTPException(status_code=400, detail="thiếu credential_id")
    with _db() as conn:
        if reason in ("limit", "429", "rate_limit", "quota"):
            conn.execute(
                "UPDATE model_credentials SET status='cooldown', "
                "cooldown_until = now() + make_interval(secs => %s), updated_at=now() WHERE id=%s",
                (COOLDOWN_SECS, cid))
            _audit(conn, agent_id, "model_auth_cooldown", "credential", cid, {"reason": reason})
        elif reason in ("auth_error", "invalid"):
            conn.execute("UPDATE model_credentials SET status='disabled', updated_at=now() WHERE id=%s", (cid,))
            _audit(conn, agent_id, "model_auth_disabled", "credential", cid, {"reason": reason})
        # reason=ok → không đổi
        conn.commit()
    return {"ok": True}


# -------- Admin: quản lý credential (secret tạo bằng script trên VM) --------

@app.post("/v1/model-auth/credentials")
def cred_upsert(body: dict, authorization: str = Header(default="")) -> dict:
    """Đăng ký/ cập nhật metadata credential. KHÔNG nhận secret — chỉ ref tới file VM."""
    _require_admin(authorization)
    _ensure_schema()
    cid = body.get("id")
    kind = body.get("kind")
    ref = body.get("secret_ref")
    if not (cid and kind in ("subscription", "api_key") and ref):
        raise HTTPException(status_code=400, detail="cần id, kind(subscription|api_key), secret_ref")
    if "token" in body or "secret" in body or "api_key" in body:
        raise HTTPException(status_code=400, detail="KHÔNG gửi secret qua API — chỉ secret_ref (file trên VM)")
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO model_credentials(id, kind, label, owner_email, secret_ref, priority,
                                          note, expires_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,
                    CASE WHEN %s IS NOT NULL THEN now() + make_interval(days => %s) END)
            ON CONFLICT (id) DO UPDATE SET kind=EXCLUDED.kind, label=EXCLUDED.label,
              owner_email=EXCLUDED.owner_email, secret_ref=EXCLUDED.secret_ref,
              priority=EXCLUDED.priority, note=EXCLUDED.note,
              expires_at=coalesce(EXCLUDED.expires_at, model_credentials.expires_at),
              updated_at=now()
            """,
            (cid, kind, body.get("label"), body.get("owner_email"), ref,
             int(body.get("priority", 100)), body.get("note"),
             body.get("expires_days"), body.get("expires_days")))
        _audit(conn, "admin", "cred_upsert", "credential", cid, {"kind": kind})
        conn.commit()
    return {"id": cid, "ok": True}


@app.post("/v1/model-auth/credentials/{cid}/status")
def cred_status(cid: str, body: dict, authorization: str = Header(default="")) -> dict:
    _require_admin(authorization)
    st = body.get("status")
    if st not in ("active", "disabled", "cooldown"):
        raise HTTPException(status_code=400, detail="status: active|disabled|cooldown")
    with _db() as conn:
        n = conn.execute(
            "UPDATE model_credentials SET status=%s, "
            "cooldown_until = CASE WHEN %s='cooldown' THEN now()+make_interval(secs=>%s) ELSE NULL END, "
            "updated_at=now() WHERE id=%s RETURNING id",
            (st, st, COOLDOWN_SECS, cid)).fetchone()
        if not n:
            raise HTTPException(status_code=404, detail="credential không tồn tại")
        _audit(conn, "admin", "cred_status", "credential", cid, {"status": st})
        conn.commit()
    return {"id": cid, "status": st}


@app.get("/v1/model-auth/credentials")
def cred_list(authorization: str = Header(default="")) -> dict:
    """Liệt kê credential (KHÔNG lộ secret) + agent nào đang trỏ own vào cred nào."""
    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        creds = conn.execute(
            "SELECT id, kind, label, owner_email, status, cooldown_until, priority, note, "
            "secret_ref, expires_at, "
            "CASE WHEN expires_at IS NULL THEN NULL "
            "     ELSE floor(extract(epoch from (expires_at - now()))/86400)::int END AS days_left "
            "FROM model_credentials ORDER BY kind, priority, id").fetchall()
        agents = conn.execute(
            "SELECT agent_id, auth_mode, credential_id, model_fallback FROM agents "
            "WHERE auth_mode IS NOT NULL ORDER BY agent_id").fetchall()
        n_sub = conn.execute(f"SELECT count(*) c FROM model_credentials WHERE kind='subscription' AND {_USABLE}").fetchone()["c"]
        n_api = conn.execute(f"SELECT count(*) c FROM model_credentials WHERE kind='api_key' AND {_USABLE}").fetchone()["c"]
    return {"credentials": [dict(c) for c in creds], "agents": [dict(a) for a in agents],
            "pool_subscription_usable": n_sub, "pool_api_usable": n_api}


# ==================== P3: Agent Versions + Builder + eval gate ====================
# Đổi hành vi agent KHÔNG cần deploy code: sửa instruction/model/skills → tạo version
# → publish theo môi trường. Publish PROD phải pass regression trên golden set.

_ENVS = ("draft", "dev", "stg", "prod")


def _version_row(conn, agent_id: str, version: int) -> dict | None:
    return conn.execute(
        "SELECT * FROM agent_versions WHERE agent_id=%s AND version=%s",
        (agent_id, version)).fetchone()


def _resolve_version(conn, agent_id: str, env: str = "prod") -> dict | None:
    """Version đang 'sống' ở một môi trường (mỗi env trỏ tối đa 1 version).

    Đọc từ agent_publications → một version có thể ở nhiều env cùng lúc
    (vd promote stg→prod không làm mất bản ở stg).
    """
    return conn.execute(
        "SELECT v.agent_id, v.version, v.instruction_block, v.skills, v.model, "
        "       v.model_fallback, v.tool_grants, p.env AS publication, p.published_at "
        "FROM agent_publications p JOIN agent_versions v "
        "  ON v.agent_id=p.agent_id AND v.version=p.version "
        "WHERE p.agent_id=%s AND p.env=%s", (agent_id, env)).fetchone()


def _pub_envs(conn, agent_id: str) -> dict:
    """{version: [env,...]} — để hiển thị 1 version đang sống ở những env nào."""
    out: dict = {}
    for r in conn.execute("SELECT env, version FROM agent_publications WHERE agent_id=%s",
                          (agent_id,)).fetchall():
        out.setdefault(r["version"], []).append(r["env"])
    return out


@app.post("/v1/agents/{agent_id}/versions")
def version_create(agent_id: str, body: dict, authorization: str = Header(default=""),
                   x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    """Tạo version mới (luôn ở trạng thái draft). Không bao giờ ghi đè version cũ."""
    p = _require_role(authorization, "moderator", agent_id)   # P8: moderator sửa được agent trong phạm vi
    _ensure_schema()
    instruction = (body.get("instruction_block") or "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="thiếu instruction_block")
    with _db() as conn:
        if not conn.execute("SELECT 1 FROM agents WHERE agent_id=%s", (agent_id,)).fetchone():
            raise HTTPException(status_code=404, detail="agent không tồn tại")
        nxt = (conn.execute("SELECT coalesce(max(version),0)+1 AS v FROM agent_versions "
                            "WHERE agent_id=%s", (agent_id,)).fetchone())["v"]
        conn.execute(
            """
            INSERT INTO agent_versions(agent_id, version, instruction_block, skills, model,
                                       model_fallback, tool_grants, publication, note, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'draft',%s,%s)
            """,
            (agent_id, nxt, instruction, Json(body.get("skills") or []), body.get("model"),
             body.get("model_fallback"), Json(body.get("tool_grants") or {}),
             body.get("note"), p["actor"] or x_actor or "admin"))
        _audit(conn, p["actor"] or x_actor or "admin", "version_create", "agent_version",
               f"{agent_id}:v{nxt}", {"agent_id": agent_id, "version": nxt})
        conn.commit()
    return {"agent_id": agent_id, "version": nxt, "publication": "draft"}


@app.get("/v1/agents/{agent_id}/versions")
def version_list(agent_id: str, authorization: str = Header(default="")) -> list[dict]:
    _require_role(authorization, "user", agent_id)       # xem: mọi vai trò
    _ensure_schema()
    with _db() as conn:
        rows = conn.execute(
            "SELECT agent_id, version, instruction_block, skills, model, model_fallback, "
            "tool_grants, publication, note, created_by, created_at, published_at "
            "FROM agent_versions WHERE agent_id=%s ORDER BY version DESC",
            (agent_id,)).fetchall()
        envs = _pub_envs(conn, agent_id)
    return [{**dict(r), "envs": envs.get(r["version"], [])} for r in rows]


@app.get("/v1/agents/{agent_id}/versions/resolve")
def version_resolve(agent_id: str, env: str = "prod",
                    authorization: str = Header(default="")) -> dict:
    """Version đang chạy ở một môi trường (rỗng nếu chưa publish gì)."""
    _require_role(authorization, "user", agent_id)
    _ensure_schema()
    if env not in _ENVS:
        raise HTTPException(status_code=400, detail=f"env phải thuộc {_ENVS}")
    with _db() as conn:
        row = _resolve_version(conn, agent_id, env)
    return {"agent_id": agent_id, "env": env, "version": (row or {}).get("version"),
            "config": dict(row) if row else None}


def _eval_gate(conn, agent_id: str, version: int) -> dict:
    """Kiểm điều kiện publish PROD: phải có regression PASS gắn ĐÚNG version này."""
    n_cases = conn.execute("SELECT count(*) c FROM golden_cases WHERE active=true").fetchone()["c"]
    if not n_cases:
        return {"ok": False, "reason": "chưa có golden case active — tạo golden case trước "
                                       "(POST /v1/golden-cases) rồi chạy regression cho version này"}
    run = conn.execute(
        "SELECT run_id, score, passed, threshold, n_pass, n_total, detail FROM regression_runs "
        "WHERE target_id=%s AND agent_version=%s ORDER BY at DESC LIMIT 1",
        (agent_id, version)).fetchone()
    if not run:
        return {"ok": False, "reason": f"chưa có regression run cho version v{version} — "
                                       f"chạy POST /v1/regression/run với agent_version={version}"}
    if not run["passed"]:
        failed = [d for d in (run["detail"] or []) if not d.get("ok")]
        return {"ok": False, "reason": f"regression FAIL (score={run['score']} < "
                                       f"threshold={run['threshold']})",
                "run_id": run["run_id"], "failed_cases": failed}
    return {"ok": True, "run_id": run["run_id"], "score": float(run["score"])}


@app.post("/v1/agents/{agent_id}/versions/{version}/publish")
def version_publish(agent_id: str, version: int, body: dict,
                    authorization: str = Header(default=""),
                    x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    """Publish version. dev/stg: moderator. prod: admin — moderator chỉ TẠO YÊU CẦU chờ duyệt."""
    _ensure_schema()
    env = (body.get("env") or "dev").strip()
    if env not in ("dev", "stg", "prod"):
        raise HTTPException(status_code=400, detail="env phải là dev|stg|prod")
    p = _require_role(authorization, "moderator", agent_id)
    force = bool(body.get("force"))
    actor = p["actor"] or x_actor or body.get("published_by") or "admin"
    # P8/P9: moderator publish PROD -> không publish ngay mà tạo việc chờ admin duyệt.
    if env == "prod" and p["role"] != "admin":
        with _db() as conn:
            if not _version_row(conn, agent_id, version):
                raise HTTPException(status_code=404, detail="version không tồn tại")
            row = conn.execute(
                "INSERT INTO pending_actions(proposed_by, action, params, risk, reason) "
                "VALUES (%s,'publish_version',%s,'high',%s) RETURNING id",
                (actor, Json({"agent_id": agent_id, "version": version, "env": "prod"}),
                 body.get("reason") or f"{actor} xin publish {agent_id} v{version} lên prod")).fetchone()
            _audit(conn, actor, "publish_request", "agent_version", f"{agent_id}:v{version}",
                   {"action_id": row["id"]})
            _notify_admins(conn,
                           f"📤 *Xin duyệt publish* #{row['id']}\n"
                           f"• Người đề xuất: `{actor}`\n• Agent: `{agent_id}` v{version} → **prod**\n"
                           f"• Lý do: {body.get('reason') or '(không ghi)'}",
                           action_id=row["id"])
            conn.commit()
        return {"agent_id": agent_id, "version": version, "publication": "pending_approval",
                "action_id": row["id"],
                "note": "Đã gửi admin duyệt — prod chưa đổi."}
    with _db() as conn:
        v = _version_row(conn, agent_id, version)
        if not v:
            raise HTTPException(status_code=404, detail="version không tồn tại")
        gate = {"ok": True, "skipped": True}
        if env == "prod":
            gate = _eval_gate(conn, agent_id, version)
            if not gate["ok"] and not force:
                _audit(conn, actor, "version_publish_blocked", "agent_version",
                       f"{agent_id}:v{version}", {"env": env, "reason": gate.get("reason")})
                conn.commit()
                raise HTTPException(status_code=422, detail={
                    "error": "eval gate chặn publish prod", **gate})
            if not gate["ok"] and force:
                if not (body.get("reason") or "").strip():
                    raise HTTPException(status_code=400,
                                        detail="force=true bắt buộc kèm 'reason' (ghi vào audit)")
        # Mỗi env trỏ đúng 1 version (upsert). Version có thể sống ở nhiều env cùng lúc.
        conn.execute(
            "INSERT INTO agent_publications(agent_id, env, version, published_by) "
            "VALUES (%s,%s,%s,%s) ON CONFLICT (agent_id, env) DO UPDATE "
            "SET version=EXCLUDED.version, published_by=EXCLUDED.published_by, published_at=now()",
            (agent_id, env, version, actor))
        # Cột publication giữ để hiển thị nhanh: env "cao" nhất mà version đang phục vụ.
        conn.execute(
            """
            UPDATE agent_versions v SET publication = coalesce((
                SELECT p.env FROM agent_publications p
                WHERE p.agent_id=v.agent_id AND p.version=v.version
                ORDER BY CASE p.env WHEN 'prod' THEN 1 WHEN 'stg' THEN 2 ELSE 3 END LIMIT 1
            ), 'draft'), published_at = CASE WHEN v.version=%s THEN now() ELSE v.published_at END
            WHERE v.agent_id=%s
            """,
            (version, agent_id))
        # Skill khai trong version → brain_skills (scope agent), idempotent.
        for s in (v["skills"] or []):
            name = s if isinstance(s, str) else (s or {}).get("name")
            if not name:
                continue
            conn.execute(
                "INSERT INTO brain_skills(skill_id, name, kind, scope, agent_id, status) "
                "VALUES (%s,%s,'mcp','agent',%s,'active') ON CONFLICT (skill_id) DO NOTHING",
                (f"sk-{agent_id}-{name}", name, agent_id))
        _audit(conn, actor, "version_publish", "agent_version", f"{agent_id}:v{version}",
               {"env": env, "gate": gate, "forced": force, "reason": body.get("reason")})
        conn.commit()
    return {"agent_id": agent_id, "version": version, "publication": env,
            "gate": gate, "forced": force}


@app.post("/v1/agents/{agent_id}/rollback")
def version_rollback(agent_id: str, body: dict, authorization: str = Header(default=""),
                     x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    """Trỏ môi trường về version ĐÃ TỪNG publish trước đó — không tạo version mới."""
    _ensure_schema()
    env = (body.get("env") or "prod").strip()
    pr = _require_role(authorization, "moderator", agent_id)
    if env == "prod" and pr["role"] != "admin":
        with _db() as conn:
            row = conn.execute(
                "INSERT INTO pending_actions(proposed_by, action, params, risk, reason) "
                "VALUES (%s,'rollback_version',%s,'high',%s) RETURNING id",
                (pr["actor"], Json({"agent_id": agent_id, "env": "prod"}),
                 body.get("reason") or f"{pr['actor']} xin rollback {agent_id}")).fetchone()
            _notify_admins(conn, f"↩️ *Xin duyệt rollback* #{row['id']} — `{agent_id}` (prod) "
                                 f"bởi `{pr['actor']}`", action_id=row["id"])
            conn.commit()
        return {"agent_id": agent_id, "env": env, "status": "pending_approval",
                "action_id": row["id"], "note": "Đã gửi admin duyệt — prod chưa đổi."}
    if env not in ("dev", "stg", "prod"):
        raise HTTPException(status_code=400, detail="env phải là dev|stg|prod")
    with _db() as conn:
        cur = _resolve_version(conn, agent_id, env)
        prev = conn.execute(
            "SELECT version FROM agent_versions WHERE agent_id=%s AND published_at IS NOT NULL "
            "AND version <> %s ORDER BY published_at DESC LIMIT 1",
            (agent_id, (cur or {}).get("version") or -1)).fetchone()
        if not prev:
            raise HTTPException(status_code=409, detail="không có version trước để rollback")
        conn.execute(
            "INSERT INTO agent_publications(agent_id, env, version, published_by) "
            "VALUES (%s,%s,%s,%s) ON CONFLICT (agent_id, env) DO UPDATE "
            "SET version=EXCLUDED.version, published_by=EXCLUDED.published_by, published_at=now()",
            (agent_id, env, prev["version"], x_actor or "admin"))
        conn.execute(
            """
            UPDATE agent_versions v SET publication = coalesce((
                SELECT p.env FROM agent_publications p
                WHERE p.agent_id=v.agent_id AND p.version=v.version
                ORDER BY CASE p.env WHEN 'prod' THEN 1 WHEN 'stg' THEN 2 ELSE 3 END LIMIT 1
            ), 'draft') WHERE v.agent_id=%s
            """,
            (agent_id,))
        _audit(conn, x_actor or "admin", "version_rollback", "agent_version",
               f"{agent_id}:v{prev['version']}",
               {"env": env, "from": (cur or {}).get("version"), "to": prev["version"]})
        conn.commit()
    return {"agent_id": agent_id, "env": env, "from": (cur or {}).get("version"),
            "to": prev["version"]}


@app.get("/v1/self/version")
def self_version(authorization: str = Header(default=""), env: str = "prod") -> dict:
    """Agent tự lấy version đang publish của CHÍNH mình (không rò chéo agent)."""
    agent_id = _require_self(authorization)
    _ensure_schema()
    with _db() as conn:
        if _agent_status(conn, agent_id) == "deactivated":
            raise HTTPException(status_code=403, detail="agent deactivated")
        row = _resolve_version(conn, agent_id, env if env in _ENVS else "prod")
    if not row:
        return {"agent_id": agent_id, "env": env, "version": None,
                "instruction_block": None, "skills": [], "note": "chưa publish version nào"}
    d = dict(row)
    d["agent_id"] = agent_id
    d["env"] = env
    return d


# ==================== P4: Context Compiler + Session Memory + RAG ====================
# Nguyên tắc: STATE Ở PLATFORM, KHÔNG Ở MODEL. Mỗi lượt agent gọi /v1/self/context để
# lấy đủ ngữ cảnh (instruction version + tóm tắt + N lượt cuối + fact người dùng + tri thức),
# nên mỗi call LLM là độc lập — đổi credential/model/restart runner không mất mạch hội thoại.

CTX_LAST_TURNS = int(os.environ.get("CTX_LAST_TURNS", "8"))      # số lượt giữ nguyên văn
CTX_COMPACT_AT = int(os.environ.get("CTX_COMPACT_AT", "12"))     # quá ngưỡng → nén bớt
CTX_RAG_K = int(os.environ.get("CTX_RAG_K", "4"))


def _rag_search(conn, agent_id: str, q: str, k: int = 4) -> list[dict]:
    """Tìm tri thức liên quan: full-text + trigram + bỏ dấu.

    Phạm vi: brain shared (đã duyệt) + brain riêng của chính agent. Trả kèm source_url
    để agent TRÍCH DẪN nguồn thay vì bịa.
    """
    if not (q or "").strip():
        return []
    rows = conn.execute(
        """
        WITH q AS (SELECT unaccent(%s) AS raw)
        SELECT item_id, kind, title, content, domain, source_url, scope,
               ts_rank(to_tsvector('simple', unaccent(coalesce(title,'') || ' ' || coalesce(content,''))),
                       plainto_tsquery('simple', (SELECT raw FROM q))) AS rank,
               similarity(lower(unaccent(coalesce(title,''))), lower((SELECT raw FROM q))) AS sim
        FROM brain_items
        WHERE status = 'approved'
          AND (scope = 'shared' OR agent_id = %s)
          AND (
            to_tsvector('simple', unaccent(coalesce(title,'') || ' ' || coalesce(content,'')))
              @@ plainto_tsquery('simple', (SELECT raw FROM q))
            OR similarity(lower(unaccent(coalesce(title,''))), lower((SELECT raw FROM q))) > 0.2
          )
        ORDER BY (ts_rank(to_tsvector('simple', unaccent(coalesce(title,'') || ' ' || coalesce(content,''))),
                          plainto_tsquery('simple', (SELECT raw FROM q))) * 2
                  + similarity(lower(unaccent(coalesce(title,''))), lower((SELECT raw FROM q)))) DESC
        LIMIT %s
        """,
        (q, agent_id, max(1, min(k, 20)))).fetchall()
    return [{"item_id": r["item_id"], "kind": r["kind"], "title": r["title"],
             "content": (r["content"] or "")[:1200], "domain": r["domain"],
             "source_url": r["source_url"], "scope": r["scope"],
             "score": round(float(r["rank"]) * 2 + float(r["sim"] or 0), 4)} for r in rows]


@app.get("/v1/self/brain/search")
def self_brain_search(q: str, authorization: str = Header(default=""), k: int = 5) -> dict:
    """RAG: tìm tri thức liên quan (shared + của chính agent), kèm nguồn để trích dẫn."""
    agent_id = _require_self(authorization)
    _ensure_schema()
    with _db() as conn:
        hits = _rag_search(conn, agent_id, q, k)
    return {"q": q, "hits": hits, "n": len(hits)}


def _get_session(conn, agent_id: str, session_id: str) -> dict | None:
    return conn.execute(
        "SELECT * FROM sessions WHERE session_id=%s AND agent_id=%s",
        (session_id, agent_id)).fetchone()


@app.get("/v1/self/context")
def self_context(authorization: str = Header(default=""), session_id: str = "",
                 q: str = "", user_ref: str = "", env: str = "prod", k: int = 0) -> dict:
    """Trả TOÀN BỘ ngữ cảnh để agent dựng 1 prompt stateless cho lượt này.

    Gồm: instruction (version đang publish) + rolling_summary + N lượt gần nhất
    + fact đã biết về người dùng + tri thức liên quan (RAG có nguồn).
    """
    agent_id = _require_self(authorization)
    _ensure_schema()
    with _db() as conn:
        if _agent_status(conn, agent_id) == "deactivated":
            raise HTTPException(status_code=403, detail="agent deactivated")
        ver = _resolve_version(conn, agent_id, env if env in _ENVS else "prod")
        sess = _get_session(conn, agent_id, session_id) if session_id else None
        uref = user_ref or (sess or {}).get("user_ref") or ""
        facts = []
        if uref:
            facts = [r["fact"] for r in conn.execute(
                "SELECT fact FROM user_facts WHERE agent_id=%s AND user_ref=%s "
                "ORDER BY updated_at DESC LIMIT 30", (agent_id, uref)).fetchall()]
        turns = (sess or {}).get("turns") or []
        hits = _rag_search(conn, agent_id, q, k or CTX_RAG_K)
    return {
        "agent_id": agent_id,
        "version": (ver or {}).get("version"),
        "instruction_block": (ver or {}).get("instruction_block"),
        "model": (ver or {}).get("model"),
        "session_id": session_id or None,
        "user_ref": uref or None,
        "rolling_summary": (sess or {}).get("rolling_summary") or "",
        "recent_turns": turns[-CTX_LAST_TURNS:],
        # Lượt cũ đã cắt nhưng CHƯA được nén — agent nên nén rồi POST /session/summary.
        "pending_summary": (sess or {}).get("pending_summary") or [],
        "n_turns": (sess or {}).get("n_turns") or 0,
        "user_facts": facts,
        "knowledge": hits,
        "hint": "Ghép prompt: instruction + rolling_summary + recent_turns + user_facts + knowledge. "
                "Trích dẫn source_url khi dùng knowledge. Sau khi trả lời: POST /v1/self/session/turn.",
    }


@app.post("/v1/self/session/turn")
def self_session_turn(body: dict, authorization: str = Header(default="")) -> dict:
    """Ghi 1 lượt vào session. Quá ngưỡng thì cắt bớt lượt cũ (giữ summary + N lượt cuối)."""
    agent_id = _require_self(authorization)
    _ensure_schema()
    sid = (body.get("session_id") or "").strip()
    role = (body.get("role") or "user").strip()
    text = (body.get("text") or "").strip()
    if not sid or not text:
        raise HTTPException(status_code=400, detail="cần session_id và text")
    turn = {"role": role, "text": text[:4000]}
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO sessions(session_id, agent_id, channel, user_ref, turns, n_turns)
            VALUES (%s,%s,%s,%s,%s,1)
            ON CONFLICT (session_id) DO UPDATE SET
              turns = sessions.turns || EXCLUDED.turns,
              n_turns = sessions.n_turns + 1,
              user_ref = coalesce(EXCLUDED.user_ref, sessions.user_ref),
              updated_at = now()
            """,
            (sid, agent_id, body.get("channel"), body.get("user_ref"), Json([turn])))
        row = conn.execute("SELECT turns, agent_id, pending_summary FROM sessions "
                           "WHERE session_id=%s", (sid,)).fetchone()
        if row["agent_id"] != agent_id:
            raise HTTPException(status_code=403, detail="session thuộc agent khác")
        turns = row["turns"] or []
        pending = list(row["pending_summary"] or [])
        if len(turns) > CTX_COMPACT_AT:
            # Cắt lượt cũ khỏi cửa sổ nguyên văn → CHUYỂN VÀO pending_summary (không mất).
            # Platform không gọi model; agent nén rồi POST /session/summary để xoá pending.
            pending += turns[:-CTX_LAST_TURNS]
            conn.execute(
                "UPDATE sessions SET turns=%s, pending_summary=%s, updated_at=now() "
                "WHERE session_id=%s",
                (Json(turns[-CTX_LAST_TURNS:]), Json(pending[-200:]), sid))
        conn.commit()
    # needs_summary giữ TRUE cho tới khi agent gửi summary → agent crash không làm mất lượt cũ.
    return {"ok": True, "session_id": sid, "n_kept": min(len(turns), CTX_LAST_TURNS),
            "needs_summary": bool(pending), "dropped_turns": pending}


@app.post("/v1/self/session/summary")
def self_session_summary(body: dict, authorization: str = Header(default="")) -> dict:
    """Agent gửi bản nén (rolling summary) sau khi tự tóm tắt các lượt bị cắt."""
    agent_id = _require_self(authorization)
    sid = (body.get("session_id") or "").strip()
    summary = (body.get("summary") or "").strip()
    if not sid or not summary:
        raise HTTPException(status_code=400, detail="cần session_id và summary")
    with _db() as conn:
        # Nhận summary → xoá hàng chờ nén (lượt cũ đã được gói vào summary).
        n = conn.execute(
            "UPDATE sessions SET rolling_summary=%s, pending_summary='[]'::jsonb, updated_at=now() "
            "WHERE session_id=%s AND agent_id=%s RETURNING session_id",
            (summary[:8000], sid, agent_id)).fetchone()
        if not n:
            raise HTTPException(status_code=404, detail="session không thuộc agent")
        conn.commit()
    return {"ok": True, "session_id": sid}


@app.post("/v1/self/facts")
def self_facts_add(body: dict, authorization: str = Header(default="")) -> dict:
    """Lưu fact bền về người dùng (sống qua session khác). Trùng thì bỏ qua."""
    agent_id = _require_self(authorization)
    _ensure_schema()
    uref = (body.get("user_ref") or "").strip()
    fact = (body.get("fact") or "").strip()
    if not uref or not fact:
        raise HTTPException(status_code=400, detail="cần user_ref và fact")
    with _db() as conn:
        conn.execute(
            "INSERT INTO user_facts(agent_id, user_ref, fact, source) VALUES (%s,%s,%s,%s) "
            "ON CONFLICT (agent_id, user_ref, md5(fact)) DO UPDATE SET updated_at=now()",
            (agent_id, uref, fact[:1000], body.get("source")))
        conn.commit()
    return {"ok": True}


@app.get("/v1/self/facts")
def self_facts_list(user_ref: str, authorization: str = Header(default="")) -> list[dict]:
    agent_id = _require_self(authorization)
    with _db() as conn:
        rows = conn.execute(
            "SELECT fact, source, updated_at FROM user_facts WHERE agent_id=%s AND user_ref=%s "
            "ORDER BY updated_at DESC", (agent_id, user_ref)).fetchall()
    return [dict(r) for r in rows]


# ==================== P9: tạo agent no-code từ console ====================

@app.post("/v1/agents/nocode")
def agent_create_nocode(body: dict, authorization: str = Header(default="")) -> dict:
    """Tạo agent KHÔNG CẦN CODE: platform tự chạy bằng instruction của version.

    Bắt buộc có use case + tối thiểu 2 test case — cùng nguyên tắc với đường code.
    """
    p = _require_role(authorization, "moderator")
    _ensure_schema()
    aid = (body.get("agent_id") or "").strip().upper()
    name = (body.get("name") or "").strip()
    usecase = (body.get("usecase_md") or "").strip()
    tests = body.get("testcases") or []
    instruction = (body.get("instruction_block") or "").strip()
    if not re.match(r"^AG-[A-Z0-9-]+$", aid):
        raise HTTPException(status_code=400, detail="agent_id dạng AG-TEN-VIET-HOA")
    if not name:
        raise HTTPException(status_code=400, detail="thiếu tên agent")
    if len(usecase) < 30:
        raise HTTPException(status_code=422,
                            detail="phải mô tả USE CASE trước khi tạo agent (tối thiểu 30 ký tự)")
    valid_tests = [t for t in tests if (t or {}).get("q") and (t or {}).get("expect")]
    if len(valid_tests) < 2:
        raise HTTPException(status_code=422,
                            detail="phải có tối thiểu 2 TEST CASE (câu hỏi + từ khoá kỳ vọng)")
    if not instruction:
        raise HTTPException(status_code=400, detail="thiếu instruction (hành vi agent)")
    actor = p["actor"] or "admin"
    key = "lsr_tel_" + secrets.token_hex(20)
    with _db() as conn:
        if conn.execute("SELECT 1 FROM agents WHERE agent_id=%s", (aid,)).fetchone():
            raise HTTPException(status_code=409, detail="agent_id đã tồn tại")
        conn.execute(
            """
            INSERT INTO agents(agent_id, name, owner, status, telemetry_key_hash, runtime,
                               usecase_md, testcases, deployment, connect_mode, model_fallback)
            VALUES (%s,%s,%s,'registered',%s,'nocode',%s,%s,'managed','bot',%s)
            """,
            (aid, name, body.get("owner") or actor,
             hashlib.sha256(key.encode()).hexdigest(), usecase, Json(valid_tests),
             body.get("model")))
        conn.execute(
            """
            INSERT INTO agent_versions(agent_id, version, instruction_block, skills, model,
                                       model_fallback, publication, note, created_by)
            VALUES (%s,1,%s,%s,%s,%s,'draft','tạo từ wizard no-code',%s)
            """,
            (aid, instruction, Json(body.get("skills") or []), body.get("model"),
             body.get("model_fallback"), actor))
        # Người tạo tự động là moderator của agent này (nếu chưa phải admin platform).
        if p["role"] != "admin" and p["kind"] == "session":
            conn.execute(
                "INSERT INTO role_bindings(email, scope_type, scope_id, role, granted_by) "
                "VALUES (%s,'agent',%s,'moderator','auto-create') ON CONFLICT DO NOTHING",
                (actor, aid))
        # Kênh vào (nếu chọn ở bước 5)
        for ch in (body.get("channels") or []):
            if ch.get("channel") and ch.get("chat_id"):
                conn.execute(
                    "INSERT INTO routing_binding(channel, app_id, chat_id, agent_id, created_by) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (ch["channel"], ch.get("app_id"), ch["chat_id"], aid, actor))
        _audit(conn, actor, "agent_create_nocode", "agent", aid,
               {"name": name, "n_tests": len(valid_tests), "channels": len(body.get("channels") or [])})
        _notify_admins(conn,
                       f"🆕 Agent no-code mới: {aid} ({name})\nNgười tạo: {actor}\n"
                       f"Token đã cấp TỰ ĐỘNG. Chạy thử được ngay trên console; "
                       f"duyệt ACTIVATE để chạy Lark/Telegram + A2A: {APP_PUBLIC_URL}/agent/{aid}")
        conn.commit()
    return {"agent_id": aid, "telemetry_key": key, "version": 1, "runtime": "nocode",
            "console_url": f"{APP_PUBLIC_URL}/agent/{aid}",
            "note": "Agent đã sẵn sàng — bấm Chạy thử. Kênh thực (Lark/Telegram) + A2A "
                    "cần admin ACTIVATE; publish prod cần admin duyệt."}


@app.get("/v1/agents/{agent_id}/spec")
def agent_spec(agent_id: str, authorization: str = Header(default="")) -> dict:
    """Use case + test case của agent (dùng cho console và nút Xuất repo)."""
    _require_role(authorization, "user", agent_id)
    with _db() as conn:
        r = conn.execute("SELECT agent_id, name, owner, runtime, usecase_md, testcases, "
                         "capabilities, usage_guide, lark_bot_name "
                         "FROM agents WHERE agent_id=%s", (agent_id,)).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="agent không tồn tại")
    return dict(r)


@app.post("/v1/agents/{agent_id}/profile")
def agent_profile_update(agent_id: str, body: dict,
                         authorization: str = Header(default="")) -> dict:
    """MASTER DATA của agent: năng lực (capabilities) + hướng dẫn sử dụng (usage_guide).

    Nguồn sự thật cho: trang Xin quyền, /v1/self/directory (agent khác đọc trước khi A2A).
    Moderator của agent (hoặc admin) mới sửa được.
    """
    p = _require_role(authorization, "moderator", agent_id)
    caps = body.get("capabilities")
    guide = body.get("usage_guide")
    bot = body.get("lark_bot_name")
    if caps is not None and not isinstance(caps, list):
        raise HTTPException(status_code=400, detail="capabilities phải là danh sách chuỗi")
    with _db() as conn:
        # %s::jsonb — psycopg gửi Json() dưới type `json`, cột là `jsonb`;
        # COALESCE(json, jsonb) không ghép được nên phải cast tường minh.
        n = conn.execute(
            "UPDATE agents SET capabilities=coalesce(%s::jsonb, capabilities), "
            "usage_guide=coalesce(%s, usage_guide), lark_bot_name=coalesce(%s, lark_bot_name) "
            "WHERE agent_id=%s RETURNING agent_id",
            (Json(caps) if caps is not None else None, guide, bot, agent_id)).fetchone()
        if not n:
            raise HTTPException(status_code=404, detail="agent không tồn tại")
        _audit(conn, p["actor"] or "admin", "agent_profile_update", "agent", agent_id,
               {"capabilities": bool(caps), "usage_guide": bool(guide)})
        conn.commit()
    return {"ok": True, "agent_id": agent_id}


@app.post("/v1/agents/{agent_id}/spec")
def agent_spec_update(agent_id: str, body: dict, authorization: str = Header(default="")) -> dict:
    p = _require_role(authorization, "moderator", agent_id)
    with _db() as conn:
        conn.execute("UPDATE agents SET usecase_md=coalesce(%s, usecase_md), "
                     "testcases=coalesce(%s, testcases) WHERE agent_id=%s",
                     (body.get("usecase_md"), Json(body["testcases"]) if body.get("testcases") else None,
                      agent_id))
        _audit(conn, p["actor"], "agent_spec_update", "agent", agent_id, {})
        conn.commit()
    return {"ok": True}


# ==================== P5: Connector registry + usage metering ====================
# Mỗi connector = 1 adapter chuẩn (auth · schema · rate-limit · error-map · audit · metering).
# Agent chỉ gọi được connector đã được CẤP QUYỀN — thu quyền là chặn ngay, không cần restart.

def _meter(conn, agent_id: str, connector_id: str, tool: str, *, ok: bool = True,
           latency_ms: int | None = None, error: str = "", job_id=None,
           run_id: str = "", tokens_est: int = 0) -> None:
    """Ghi 1 dòng usage — best-effort, không làm hỏng request."""
    try:
        conn.execute(
            "INSERT INTO tool_usage(agent_id, connector_id, tool, job_id, run_id, "
            "latency_ms, ok, error, tokens_est) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (agent_id, connector_id, tool, job_id, run_id or None, latency_ms, ok,
             (error or "")[:300], tokens_est))
    except Exception:
        pass


def _require_connector(conn, agent_id: str, connector_id: str, tool: str = "") -> None:
    """Chặn nếu agent chưa được cấp quyền connector (khi connector bật enforce)."""
    c = conn.execute("SELECT status, enforce FROM connectors WHERE connector_id=%s",
                     (connector_id,)).fetchone()
    if not c:
        return                              # connector chưa đăng ký → không chặn
    if c["status"] != "active":
        _meter(conn, agent_id, connector_id, tool, ok=False, error="connector inactive")
        _audit(conn, agent_id, "connector_denied", "connector", connector_id,
               {"reason": "connector inactive"})
        conn.commit()          # PHẢI commit trước khi raise, nếu không dấu vết bị rollback
        raise HTTPException(status_code=503, detail=f"connector '{connector_id}' đang tắt")
    if not c["enforce"]:
        return
    g = conn.execute("SELECT 1 FROM connector_grants WHERE agent_id=%s AND connector_id=%s",
                     (agent_id, connector_id)).fetchone()
    if not g:
        _meter(conn, agent_id, connector_id, tool, ok=False, error="no grant")
        _audit(conn, agent_id, "connector_denied", "connector", connector_id,
               {"reason": "chưa được cấp quyền", "tool": tool})
        conn.commit()          # ghi nhận lần bị chặn TRƯỚC khi raise (không mất audit)
        raise HTTPException(
            status_code=403,
            detail=f"agent chưa được cấp quyền connector '{connector_id}' — "
                   f"nhờ admin cấp ở Console → Connectors")


@app.get("/v1/connectors")
def connectors_list(authorization: str = Header(default="")) -> dict:
    """Danh sách connector + grant + thống kê usage 7 ngày."""
    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        cons = conn.execute(
            "SELECT connector_id, kind, name, status, enforce, note FROM connectors "
            "ORDER BY kind, connector_id").fetchall()
        grants = conn.execute(
            "SELECT agent_id, connector_id, scope, granted_by, granted_at "
            "FROM connector_grants ORDER BY connector_id, agent_id").fetchall()
        usage = conn.execute(
            "SELECT connector_id, tool, count(*) n, sum(case when ok then 0 else 1 end) n_err, "
            "round(avg(latency_ms)) avg_ms FROM tool_usage "
            "WHERE created_at > now() - interval '7 days' "
            "GROUP BY connector_id, tool ORDER BY n DESC LIMIT 50").fetchall()
    return {"connectors": [dict(c) for c in cons], "grants": [dict(g) for g in grants],
            "usage_7d": [dict(u) for u in usage]}


@app.post("/v1/connectors/grant")
def connector_grant(body: dict, authorization: str = Header(default=""),
                    x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    """Cấp hoặc THU quyền connector cho agent (revoke=true để thu)."""
    _require_admin(authorization)
    _ensure_schema()
    aid, cid = body.get("agent_id"), body.get("connector_id")
    if not (aid and cid):
        raise HTTPException(status_code=400, detail="cần agent_id + connector_id")
    revoke = bool(body.get("revoke"))
    with _db() as conn:
        if revoke:
            conn.execute("DELETE FROM connector_grants WHERE agent_id=%s AND connector_id=%s",
                         (aid, cid))
        else:
            if not conn.execute("SELECT 1 FROM connectors WHERE connector_id=%s", (cid,)).fetchone():
                raise HTTPException(status_code=404, detail="connector không tồn tại")
            conn.execute(
                "INSERT INTO connector_grants(agent_id, connector_id, scope, granted_by) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT (agent_id, connector_id) DO UPDATE "
                "SET scope=EXCLUDED.scope, granted_by=EXCLUDED.granted_by, granted_at=now()",
                (aid, cid, body.get("scope", "use"), x_actor or "admin"))
        _audit(conn, x_actor or "admin", "connector_revoke" if revoke else "connector_grant",
               "connector", cid, {"agent_id": aid})
        conn.commit()
    return {"ok": True, "agent_id": aid, "connector_id": cid, "revoked": revoke}


@app.post("/v1/self/tool-usage")
def self_tool_usage(body: dict, authorization: str = Header(default="")) -> dict:
    """Agent tự báo 1 tool call (cho agent tự host / SDK khác)."""
    agent_id = _require_self(authorization)
    _ensure_schema()
    with _db() as conn:
        _meter(conn, agent_id, body.get("connector_id") or "internal",
               body.get("tool") or "?", ok=bool(body.get("ok", True)),
               latency_ms=body.get("latency_ms"), error=body.get("error") or "",
               job_id=body.get("job_id"), run_id=body.get("run_id") or "",
               tokens_est=int(body.get("tokens_est") or 0))
        conn.commit()
    return {"ok": True}


@app.get("/v1/self/usage")
def self_usage(authorization: str = Header(default=""), days: int = 7) -> dict:
    """Agent xem usage của chính mình theo connector/tool."""
    agent_id = _require_self(authorization)
    with _db() as conn:
        rows = conn.execute(
            "SELECT connector_id, tool, count(*) n, sum(case when ok then 0 else 1 end) n_err, "
            "round(avg(latency_ms)) avg_ms, sum(tokens_est) tokens FROM tool_usage "
            "WHERE agent_id=%s AND created_at > now() - make_interval(days => %s) "
            "GROUP BY connector_id, tool ORDER BY n DESC", (agent_id, min(days, 90))).fetchall()
    return {"agent_id": agent_id, "days": days, "usage": [dict(r) for r in rows]}


@app.get("/v1/runtime/jobs")
def runtime_jobs(authorization: str = Header(default=""), max: int = 5) -> list[dict]:
    """Runtime no-code lấy job của MỌI agent runtime='nocode' (1 service phục vụ N agent)."""
    tok = _bearer(authorization)
    if not (tok and tok in (ADMIN_TOKEN, GATEWAY_INGEST_TOKEN)):
        raise HTTPException(status_code=401, detail="cần runtime/admin token")
    _ensure_schema()
    out = []
    with _db() as conn:
        _reap_stale(conn)
        for _ in range(max):
            row = conn.execute(
                """
                UPDATE jobs SET status='running', locked_by='nocode-runtime', locked_at=now(),
                                attempts=attempts+1, updated_at=now()
                WHERE id = (
                    SELECT j.id FROM jobs j JOIN agents a ON a.agent_id=j.agent_id
                    WHERE j.status='queued' AND j.run_after<=now()
                      AND a.runtime='nocode' AND a.status <> 'deactivated'
                    ORDER BY j.priority ASC, j.id ASC
                    FOR UPDATE OF j SKIP LOCKED LIMIT 1
                )
                RETURNING id, agent_id, channel, session_id, reply_to, payload, attempts
                """).fetchone()
            if not row:
                break
            out.append(dict(row))
        conn.commit()
    return out


@app.get("/v1/agents/{agent_id}/runtime-token")
def runtime_token(agent_id: str, authorization: str = Header(default="")) -> dict:
    """Cấp token ngắn hạn cho runtime hành động nhân danh agent NO-CODE."""
    tok = _bearer(authorization)
    if not (tok and tok in (ADMIN_TOKEN, GATEWAY_INGEST_TOKEN)):
        raise HTTPException(status_code=401, detail="cần runtime/admin token")
    _ensure_schema()
    with _db() as conn:
        a = conn.execute("SELECT runtime, status FROM agents WHERE agent_id=%s",
                         (agent_id,)).fetchone()
        if not a:
            raise HTTPException(status_code=404, detail="agent không tồn tại")
        if a["runtime"] != "nocode":
            raise HTTPException(status_code=403, detail="chỉ cấp cho agent no-code")
        if a["status"] == "deactivated":
            raise HTTPException(status_code=403, detail="agent deactivated")
        t = "lsr_rt_" + secrets.token_hex(24)
        conn.execute("DELETE FROM agent_runtime_tokens WHERE expires_at < now()")
        conn.execute(
            "INSERT INTO agent_runtime_tokens(token_hash, agent_id, expires_at) "
            "VALUES (%s,%s, now() + interval '30 minutes')",
            (hashlib.sha256(t.encode()).hexdigest(), agent_id))
        conn.commit()
    return {"agent_id": agent_id, "token": t, "expires_minutes": 30}


@app.get("/v1/runtime/agent/{agent_id}/config")
def runtime_agent_config(agent_id: str, authorization: str = Header(default=""),
                         env: str = "prod") -> dict:
    """Runtime lấy cấu hình để chạy 1 agent no-code: instruction + model + token của agent."""
    tok = _bearer(authorization)
    if not (tok and tok in (ADMIN_TOKEN, GATEWAY_INGEST_TOKEN)):
        raise HTTPException(status_code=401, detail="cần runtime/admin token")
    with _db() as conn:
        a = conn.execute("SELECT agent_id, name, runtime, model_fallback FROM agents "
                         "WHERE agent_id=%s", (agent_id,)).fetchone()
        if not a:
            raise HTTPException(status_code=404, detail="agent không tồn tại")
        ver = _resolve_version(conn, agent_id, env) or _resolve_version(conn, agent_id, "dev")
    return {"agent_id": agent_id, "name": a["name"],
            "instruction_block": (ver or {}).get("instruction_block"),
            "model": (ver or {}).get("model") or a["model_fallback"],
            "version": (ver or {}).get("version")}


# ==================== P6: Agent Directory + A2A ====================
# Agent nhìn thấy nhau và gọi nhau KHÔNG qua frontend: A2A chỉ là một nguồn sự kiện
# nữa vào cùng job queue (P1) → tự hưởng routing/retry/DLQ/quota/audit/kill-switch.

A2A_MAX_HOP = int(os.environ.get("A2A_MAX_HOP", "3"))


@app.get("/v1/self/directory")
def self_directory(authorization: str = Header(default="")) -> dict:
    """Danh bạ agent: ai đang sống, làm được gì (skills từ version), thuộc domain nào."""
    caller = _require_self(authorization)
    _ensure_schema()
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT a.agent_id, a.name, a.owner, a.status, a.squad,
                   a.capabilities, a.usage_guide, a.lark_bot_name,
                   coalesce(v.skills, to_jsonb(coalesce(a.skills,'{}'))) AS skills,
                   (SELECT 1 FROM a2a_grants g WHERE g.caller_id=%s AND g.target_id=a.agent_id) AS can_call
            FROM agents a
            LEFT JOIN agent_publications p ON p.agent_id=a.agent_id AND p.env='prod'
            LEFT JOIN agent_versions v ON v.agent_id=p.agent_id AND v.version=p.version
            WHERE a.status <> 'deactivated'
            ORDER BY a.agent_id
            """, (caller,)).fetchall()
    return {"caller": caller, "agents": [
        {"agent_id": r["agent_id"], "name": r["name"], "owner": r["owner"],
         "status": r["status"], "squad": r["squad"], "skills": r["skills"],
         "capabilities": r["capabilities"], "usage_guide": r["usage_guide"],
         "lark_bot_name": r["lark_bot_name"],
         "can_call": bool(r["can_call"]), "is_self": r["agent_id"] == caller}
        for r in rows]}


@app.post("/v1/a2a/grant")
def a2a_grant(body: dict, authorization: str = Header(default=""),
              x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    """Admin cấp/thu quyền agent A được gọi agent B."""
    _require_admin(authorization)
    _ensure_schema()
    caller, target = body.get("caller_id"), body.get("target_id")
    if not (caller and target):
        raise HTTPException(status_code=400, detail="cần caller_id + target_id")
    if caller == target:
        raise HTTPException(status_code=400, detail="không cấp quyền tự gọi chính mình")
    revoke = bool(body.get("revoke"))
    with _db() as conn:
        if revoke:
            conn.execute("DELETE FROM a2a_grants WHERE caller_id=%s AND target_id=%s",
                         (caller, target))
        else:
            conn.execute(
                "INSERT INTO a2a_grants(caller_id, target_id, scope, granted_by) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT (caller_id, target_id) DO UPDATE "
                "SET granted_by=EXCLUDED.granted_by, granted_at=now()",
                (caller, target, body.get("scope", "call"), x_actor or "admin"))
        _audit(conn, x_actor or "admin", "a2a_revoke" if revoke else "a2a_grant",
               "a2a", f"{caller}->{target}", {})
        conn.commit()
    return {"ok": True, "caller_id": caller, "target_id": target, "revoked": revoke}


@app.post("/v1/self/a2a/{target_id}")
def a2a_call(target_id: str, body: dict, authorization: str = Header(default=""),
             x_hop: str = Header(default="", alias="X-A2A-Hop")) -> dict:
    """Agent gọi agent khác. Đẩy job channel=a2a vào CÙNG queue; caller poll kết quả."""
    caller = _require_self(authorization)
    _ensure_schema()
    if target_id == caller:
        raise HTTPException(status_code=400, detail="không tự gọi chính mình")
    try:
        hop = int(x_hop or body.get("hop") or 1)
    except Exception:
        hop = 1
    if hop > A2A_MAX_HOP:
        raise HTTPException(status_code=429,
                            detail=f"vượt giới hạn {A2A_MAX_HOP} chặng A2A (chống vòng lặp)")
    task = (body.get("task") or "").strip()
    if not task:
        raise HTTPException(status_code=400, detail="thiếu 'task'")
    with _db() as conn:
        # A2A chỉ giữa các agent ĐÃ được admin activate — cả hai chiều.
        cstatus = _agent_status(conn, caller)
        if cstatus != "active":
            raise HTTPException(status_code=403,
                                detail=f"agent của bạn đang '{cstatus}' — cần admin ACTIVATE mới gọi A2A được")
        tstatus = _agent_status(conn, target_id)
        if not tstatus:
            raise HTTPException(status_code=404, detail="target không tồn tại")
        if tstatus != "active":
            raise HTTPException(status_code=409,
                                detail=f"target đang '{tstatus}' — chưa được admin activate, không enqueue")
        if not conn.execute("SELECT 1 FROM a2a_grants WHERE caller_id=%s AND target_id=%s",
                            (caller, target_id)).fetchone():
            _audit(conn, caller, "a2a_denied", "a2a", f"{caller}->{target_id}", {"task": task[:80]})
            conn.commit()
            raise HTTPException(status_code=403,
                                detail=f"chưa được cấp quyền gọi '{target_id}'")
        req_id = "a2a_" + secrets.token_hex(8)
        res = _ingest(conn, channel="a2a", agent_id=target_id,
                      session_id=req_id,
                      payload={"text": task, "task": task, "payload": body.get("payload") or {},
                               "from_agent": caller, "req_id": req_id, "hop": hop},
                      reply_to={"channel": "a2a", "req_id": req_id, "caller_id": caller})
        conn.execute(
            "INSERT INTO a2a_requests(req_id, caller_id, target_id, task, payload, job_id, hop) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (req_id, caller, target_id, task[:2000], Json(body.get("payload") or {}),
             res.get("job_id"), hop))
        # Audit 2 chiều: bên gọi và bên phục vụ, khớp req_id để đối chiếu.
        _audit(conn, caller, "a2a_call", "a2a", req_id,
               {"target": target_id, "hop": hop, "job_id": res.get("job_id")})
        _audit(conn, target_id, "a2a_serve", "a2a", req_id, {"caller": caller, "hop": hop})
        conn.commit()
    return {"req_id": req_id, "target_id": target_id, "job_id": res.get("job_id"),
            "status": "queued", "hop": hop}


@app.get("/v1/self/a2a/{req_id}")
def a2a_result(req_id: str, authorization: str = Header(default="")) -> dict:
    """Caller lấy kết quả lượt A2A (đọc trạng thái job + kết quả target trả về)."""
    caller = _require_self(authorization)
    with _db() as conn:
        r = conn.execute(
            "SELECT req_id, caller_id, target_id, task, job_id, status, result, hop "
            "FROM a2a_requests WHERE req_id=%s", (req_id,)).fetchone()
        if not r or r["caller_id"] != caller:
            raise HTTPException(status_code=404, detail="không thấy request của agent này")
        job = conn.execute("SELECT status, last_error FROM jobs WHERE id=%s",
                           (r["job_id"],)).fetchone() if r["job_id"] else None
        # Kết quả = event 'message' cuối (nội dung target trả về); nếu không có thì lấy 'done'.
        ev = None
        if r["job_id"]:
            ev = conn.execute(
                "SELECT data FROM job_events WHERE job_id=%s AND kind='message' "
                "ORDER BY id DESC LIMIT 1", (r["job_id"],)).fetchone()
            if not ev:
                ev = conn.execute(
                    "SELECT data FROM job_events WHERE job_id=%s AND kind='done' "
                    "ORDER BY id DESC LIMIT 1", (r["job_id"],)).fetchone()
        status = (job or {}).get("status") or r["status"]
        if status == "done" and r["status"] != "done":
            conn.execute("UPDATE a2a_requests SET status='done', result=%s, updated_at=now() "
                         "WHERE req_id=%s", (Json((ev or {}).get("data") or {}), req_id))
            conn.commit()
    return {"req_id": req_id, "target_id": r["target_id"], "job_status": status,
            "result": (ev or {}).get("data") or r["result"], "hop": r["hop"],
            "error": (job or {}).get("last_error")}


# ==================== P7: HITL + Mart KPI + Platform agents ====================
# Platform agent quan sát & ĐỀ XUẤT; người DUYỆT (rủi ro cao) hoặc hệ thống tự chạy
# (rủi ro thấp, vẫn ghi log). Không ai tự duyệt việc mình đề xuất.

_ACTION_OK = {"alert", "replay_dlq", "deactivate_agent", "activate_agent",
              "rollback_version", "prune_docker",
              "cooldown_credential", "pause_routing", "publish_version"}

# --- Kênh admin: Telegram (dùng được ngay) + Lark DM (khi app mở available-range) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API = "https://api.telegram.org"


def _tg_send(chat_id: str, text: str, buttons: list | None = None) -> bool:
    """Gửi tin Telegram cho 1 admin. buttons = [[{text, callback_data}], ...]"""
    if not (TELEGRAM_TOKEN and chat_id):
        return False
    payload = {"chat_id": chat_id, "text": text[:4000], "parse_mode": "Markdown"}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    try:
        r = requests.post(f"{TELEGRAM_API}/bot{TELEGRAM_TOKEN}/sendMessage",
                          json=payload, timeout=10)
        return bool(r.json().get("ok"))
    except Exception:
        return False


def _notify_admins(conn, text: str, *, action_id: int | None = None,
                   markdown: str = "") -> dict:
    """Gửi cho MỌI admin đang bật: ưu tiên Telegram (có nút duyệt), kèm Lark DM nếu có open_id.

    Trả thống kê để soi kênh nào tới được — không raise (thông báo không được làm hỏng luồng).
    """
    sent = {"telegram": 0, "lark": 0, "none": 0}
    try:
        # Nguồn chính: tài khoản console có vai trò admin (P8). Hợp nhất với bảng
        # platform_admins cũ để không mất kênh đã nối trước đó.
        admins = conn.execute(
            """
            SELECT email, name, lark_open_id, telegram_chat_id FROM (
                SELECT a.email, a.name, NULL::text AS lark_open_id, a.telegram_chat_id
                FROM accounts a JOIN role_bindings r ON r.email = a.email
                WHERE a.status='active' AND r.role='admin' AND r.scope_type='platform'
                UNION
                SELECT p.email, p.name, p.lark_open_id, p.telegram_chat_id
                FROM platform_admins p WHERE p.active
            ) x
            WHERE telegram_chat_id IS NOT NULL OR lark_open_id IS NOT NULL
            """).fetchall()
        if not admins:
            admins = conn.execute(
                "SELECT email, name, lark_open_id, telegram_chat_id FROM platform_admins "
                "WHERE active").fetchall()
    except Exception:
        return sent
    buttons = None
    if action_id:
        buttons = [[{"text": "✅ Duyệt", "callback_data": f"approve:{action_id}"},
                    {"text": "❌ Từ chối", "callback_data": f"reject:{action_id}"}]]
    for a in admins:
        ok_any = False
        if a["telegram_chat_id"] and _tg_send(a["telegram_chat_id"], text, buttons):
            sent["telegram"] += 1; ok_any = True
        if a["lark_open_id"]:
            ok, _ = _lark_send_to(a["lark_open_id"], "open_id",
                                  text=text if not markdown else "", markdown=markdown)
            if ok:
                sent["lark"] += 1; ok_any = True
        if not ok_any:
            sent["none"] += 1
    # Chưa admin nào nối kênh → rơi về nhóm Lark chung để không mất cảnh báo.
    if sent["telegram"] + sent["lark"] == 0 and LARK_NOTIFY_CHAT_ID:
        _lark_send_to(LARK_NOTIFY_CHAT_ID, "chat_id", text=text)
    return sent


@app.get("/v1/admins")
def admins_list(authorization: str = Header(default="")) -> list[dict]:
    """Danh sách admin + kênh đã nối (không lộ chat_id đầy đủ)."""
    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        rows = conn.execute(
            "SELECT email, name, role, active, linked_at, "
            "(lark_open_id IS NOT NULL) AS lark_linked, "
            "(telegram_chat_id IS NOT NULL) AS telegram_linked "
            "FROM platform_admins ORDER BY role, email").fetchall()
    return [dict(r) for r in rows]


@app.post("/v1/admins/link")
def admin_link(body: dict, authorization: str = Header(default="")) -> dict:
    """Nối kênh cho admin. Dùng bởi bot Telegram (ingest token) hoặc admin thủ công."""
    tok = authorization[7:] if authorization.startswith("Bearer ") else ""
    if not (tok and tok in (ADMIN_TOKEN, GATEWAY_INGEST_TOKEN)):
        raise HTTPException(status_code=401, detail="cần admin/ingest token")
    _ensure_schema()
    email = (body.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="thiếu email")
    with _db() as conn:
        row = conn.execute(
            "SELECT email FROM platform_admins WHERE lower(email)=%s "
            "UNION SELECT email FROM accounts WHERE lower(email)=%s", (email, email)).fetchone()
        if not row:
            raise HTTPException(status_code=404,
                                detail="email không có trong danh sách admin/tài khoản console")
        if body.get("telegram_chat_id"):
            conn.execute("UPDATE platform_admins SET telegram_chat_id=%s, linked_at=now() "
                         "WHERE lower(email)=%s", (str(body["telegram_chat_id"]), email))
            # Đồng bộ sang tài khoản console (P8) — một nơi quản lý duy nhất.
            conn.execute("UPDATE accounts SET telegram_chat_id=%s WHERE lower(email)=%s",
                         (str(body["telegram_chat_id"]), email))
        if body.get("lark_open_id"):
            conn.execute("UPDATE platform_admins SET lark_open_id=%s, linked_at=now() "
                         "WHERE lower(email)=%s", (body["lark_open_id"], email))
        _audit(conn, email, "admin_link", "admin", email,
               {"telegram": bool(body.get("telegram_chat_id")),
                "lark": bool(body.get("lark_open_id"))})
        conn.commit()
    return {"ok": True, "email": email}


@app.get("/v1/admins/by-telegram/{chat_id}")
def admin_by_telegram(chat_id: str, authorization: str = Header(default="")) -> dict:
    """Bot Telegram tra admin theo chat_id (để biết ai đang bấm nút duyệt)."""
    tok = authorization[7:] if authorization.startswith("Bearer ") else ""
    if not (tok and tok in (ADMIN_TOKEN, GATEWAY_INGEST_TOKEN)):
        raise HTTPException(status_code=401, detail="cần admin/ingest token")
    with _db() as conn:
        r = conn.execute("SELECT email, name, role FROM platform_admins "
                         "WHERE telegram_chat_id=%s AND active", (str(chat_id),)).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="chat_id chưa nối với admin nào")
    return dict(r)


def _execute_action(conn, action: str, params: dict, actor: str) -> dict:
    """Thực thi 1 action đã được duyệt (hoặc rủi ro thấp). Trả kết quả để ghi lại."""
    if action == "alert":
        sent = _notify_admins(conn, f"🔔 *[{actor}]* {params.get('message', '')}")
        return {"sent": sent, "message": params.get("message", "")[:200]}
    if action == "replay_dlq":
        n = conn.execute(
            "UPDATE jobs SET status='queued', attempts=0, run_after=now(), "
            "locked_by=NULL, locked_at=NULL, updated_at=now() WHERE status='dlq'"
            + (" AND agent_id=%s" if params.get("agent_id") else ""),
            ((params["agent_id"],) if params.get("agent_id") else ())).rowcount
        return {"replayed": n}
    if action == "deactivate_agent":
        aid = params.get("agent_id")
        conn.execute("UPDATE agents SET status='deactivated' WHERE agent_id=%s", (aid,))
        # Kill switch: agent tắt thì cắt luôn quyền hành động dưới danh nghĩa người thật,
        # không để token còn dùng được qua một tiến trình sót lại.
        off = conn.execute("UPDATE agent_user_identity_grants SET active=false "
                           "WHERE agent_id=%s AND active", (aid,)).rowcount
        if off:
            _audit(conn, actor, "lark_user_grants_off", "agent", aid,
                   {"n": off, "reason": "agent bị deactivate"})
        return {"deactivated": aid, "lark_user_grants_off": off}
    if action == "activate_agent":
        # Admin duyệt golive (checklist đã đủ ở bước nộp). Vẫn kiểm lại lần cuối để
        # không bật agent bị xoá checklist sau khi trình duyệt.
        aid = params.get("agent_id")
        row = conn.execute(
            "SELECT payload FROM agent_golive_checklist WHERE agent_id=%s", (aid,)).fetchone()
        miss = missing_checklist((row or {}).get("payload") or {})
        if miss:
            _notify_owner_checklist(conn, aid, miss)
            return {"error": "checklist thiếu lại khi duyệt — đã nhắc owner", "missing": miss}
        n = conn.execute("UPDATE agents SET status='active', golive_at=coalesce(golive_at, now()) "
                         "WHERE agent_id=%s RETURNING agent_id", (aid,)).fetchone()
        if not n:
            return {"error": "agent không tồn tại", "agent_id": aid}
        lark = _sync_lark_status(conn, aid, activate=True)
        vm = _agent_vm_action(aid, "start")
        owner = (conn.execute("SELECT owner FROM agents WHERE agent_id=%s", (aid,)).fetchone()
                 or {}).get("owner")
        if owner:
            _send_lark(owner, f"🎉 Agent {aid} đã được {actor} DUYỆT GOLIVE và đang chạy. "
                              f"Kênh Lark/Telegram + A2A đã mở.")
        return {"activated": aid, "lark_sync": lark, "vm": vm}
    if action == "publish_version":
        aid, ver, env = params.get("agent_id"), params.get("version"), params.get("env", "prod")
        gate = _eval_gate(conn, aid, ver)
        if not gate["ok"]:
            # Eval gate vẫn áp: admin duyệt nhưng golden fail thì KHÔNG publish.
            return {"error": "eval gate chặn", **gate}
        conn.execute(
            "INSERT INTO agent_publications(agent_id, env, version, published_by) "
            "VALUES (%s,%s,%s,%s) ON CONFLICT (agent_id, env) DO UPDATE "
            "SET version=EXCLUDED.version, published_by=EXCLUDED.published_by, published_at=now()",
            (aid, env, ver, actor))
        conn.execute(
            """
            UPDATE agent_versions v SET publication = coalesce((
                SELECT p.env FROM agent_publications p
                WHERE p.agent_id=v.agent_id AND p.version=v.version
                ORDER BY CASE p.env WHEN 'prod' THEN 1 WHEN 'stg' THEN 2 ELSE 3 END LIMIT 1
            ), 'draft'), published_at = CASE WHEN v.version=%s THEN now() ELSE v.published_at END
            WHERE v.agent_id=%s
            """, (ver, aid))
        return {"published": f"{aid} v{ver} → {env}", "gate": gate}
    if action == "rollback_version":
        aid, env = params.get("agent_id"), params.get("env", "prod")
        cur = _resolve_version(conn, aid, env)
        prev = conn.execute(
            "SELECT version FROM agent_versions WHERE agent_id=%s AND published_at IS NOT NULL "
            "AND version <> %s ORDER BY published_at DESC LIMIT 1",
            (aid, (cur or {}).get("version") or -1)).fetchone()
        if not prev:
            return {"error": "không có version trước"}
        conn.execute(
            "INSERT INTO agent_publications(agent_id, env, version, published_by) "
            "VALUES (%s,%s,%s,%s) ON CONFLICT (agent_id, env) DO UPDATE "
            "SET version=EXCLUDED.version, published_at=now()", (aid, env, prev["version"], actor))
        return {"rolled_back_to": prev["version"], "agent_id": aid, "env": env}
    if action == "cooldown_credential":
        cid = params.get("credential_id")
        conn.execute("UPDATE model_credentials SET status='cooldown', "
                     "cooldown_until=now()+make_interval(secs=>%s), updated_at=now() WHERE id=%s",
                     (COOLDOWN_SECS, cid))
        return {"cooldown": cid}
    if action == "prune_docker":
        # Dọn image Docker để cứu đĩa. Hai mức, do người gọi chọn:
        #   scope=dangling → images.prune() = `docker image prune -f` (chỉ image mồ côi)
        #   scope=unused   → thêm dangling:false + until = `prune -a --filter until=...`
        # Đo thật trên VM (19/08): dangling chỉ 0.4GB, còn image có tag nhưng không ai
        # dùng tới 25GB — nên mức 'dangling' KHÔNG cứu nổi đĩa, phải dùng 'unused'.
        # An toàn: Docker không xoá image nào còn container trỏ vào, KỂ CẢ container đã
        # stop — nên agent đang tắt vẫn giữ được image, chỉ mất bản cũ sau khi build lại.
        # 'until' là chốt chặn thêm: không đụng image mới build (mặc định 7 ngày).
        scope = params.get("scope") or "dangling"
        if scope not in ("dangling", "unused"):
            return {"error": "scope phải là 'dangling' hoặc 'unused'"}
        hours = int(params.get("older_than_hours") or 168)
        filters = None if scope == "dangling" else {"dangling": False, "until": f"{hours}h"}
        before = _disk_usage()
        try:
            import docker  # type: ignore
            pr = docker.DockerClient(base_url=AGENT_DOCKER_HOST).images.prune(filters) or {}
        except Exception as exc:
            return {"error": f"không dọn được: {exc}", "disk": before}
        freed_gb = round(int(pr.get("SpaceReclaimed") or 0) / 1e9, 1)
        n = len(pr.get("ImagesDeleted") or [])
        after = _disk_usage()
        res = {"scope": scope, "older_than_hours": hours, "freed_gb": freed_gb,
               "layers_deleted": n, "disk_before": before, "disk_after": after}
        # Chỉ báo admin khi thật sự dọn được — tránh spam "đã dọn 0GB" mỗi giờ khi đĩa
        # cao vì lý do khác (log, volume) chứ không phải image rác.
        if freed_gb > 0:
            _notify_admins(conn, f"🧹 *[{actor}]* Đã dọn image Docker ({scope}, quá "
                                 f"{hours}h): giải phóng *{freed_gb}GB* ({n} lớp image). "
                                 f"Đĩa {before.get('used_pct')}% → {after.get('used_pct')}% "
                                 f"(còn {after.get('free_gb')}GB).")
        return res
    if action == "pause_routing":
        n = conn.execute("UPDATE routing_binding SET active=false WHERE agent_id=%s",
                         (params.get("agent_id"),)).rowcount
        return {"paused_bindings": n}
    return {"error": f"action không hỗ trợ: {action}"}


@app.post("/v1/self/actions/propose")
def action_propose(body: dict, authorization: str = Header(default="")) -> dict:
    """Platform agent đề xuất hành động. risk=low tự chạy + log; risk=high chờ người duyệt."""
    agent_id = _require_self(authorization)
    _ensure_schema()
    action = (body.get("action") or "").strip()
    if action not in _ACTION_OK:
        raise HTTPException(status_code=400, detail=f"action phải thuộc {sorted(_ACTION_OK)}")
    risk = (body.get("risk") or "high").strip()
    params = body.get("params") or {}
    reason = (body.get("reason") or "").strip()
    with _db() as conn:
        plat = conn.execute("SELECT is_platform FROM agents WHERE agent_id=%s",
                            (agent_id,)).fetchone()
        if not (plat or {}).get("is_platform"):
            raise HTTPException(status_code=403,
                                detail="chỉ platform agent (AG-OPS/AG-EVAL) được đề xuất hành động")
        if risk == "low":
            res = _execute_action(conn, action, params, agent_id)
            row = conn.execute(
                "INSERT INTO pending_actions(proposed_by, action, params, risk, reason, "
                "status, result, decided_at) VALUES (%s,%s,%s,'low',%s,'auto',%s, now()) RETURNING id",
                (agent_id, action, Json(params), reason, Json(res))).fetchone()
            _audit(conn, agent_id, "action_auto", "action", str(row["id"]),
                   {"action": action, "result": res})
            conn.commit()
            return {"id": row["id"], "status": "auto", "result": res}
        # Cùng một việc đang chờ duyệt thì đừng đẻ thêm phiếu mỗi giờ — admin thấy
        # 10 phiếu giống nhau sẽ bỏ qua cả 10.
        dup = conn.execute(
            "SELECT id FROM pending_actions WHERE status='pending' AND action=%s "
            "AND params = %s::jsonb AND (expires_at IS NULL OR expires_at > now()) "
            "ORDER BY id LIMIT 1", (action, Json(params))).fetchone()
        if dup:
            return {"id": dup["id"], "status": "pending", "action": action, "duplicate": True}
        row = conn.execute(
            "INSERT INTO pending_actions(proposed_by, action, params, risk, reason, expires_at) "
            "VALUES (%s,%s,%s,'high',%s, now() + make_interval(hours => %s)) RETURNING id",
            (agent_id, action, Json(params), reason, int(body.get("expires_hours", 24)))).fetchone()
        _audit(conn, agent_id, "action_propose", "action", str(row["id"]),
               {"action": action, "params": params, "reason": reason})
        # Gửi thẳng cho ADMIN (Telegram có nút Duyệt/Từ chối; Lark DM nếu đã nối).
        body_txt = (f"⚠️ *Đề xuất cần duyệt #{row['id']}*\n"
                    f"• Đề xuất bởi: `{agent_id}`\n"
                    f"• Hành động: `{action}`\n"
                    f"• Tham số: `{json.dumps(params, ensure_ascii=False)[:200]}`\n"
                    f"• Lý do: {reason or '(không ghi)'}")
        sent = _notify_admins(conn, body_txt, action_id=row["id"],
                              markdown=body_txt.replace("*", "**"))
        conn.commit()
    return {"id": row["id"], "status": "pending", "action": action, "notified": sent}


@app.get("/v1/actions")
def actions_list(authorization: str = Header(default=""), status: str | None = None,
                 limit: int = 50) -> list[dict]:
    _require_admin(authorization)
    _ensure_schema()
    q = ("SELECT id, proposed_by, action, params, risk, reason, status, approver, result, "
         "expires_at, created_at, decided_at FROM pending_actions")
    args: list = []
    if status:
        q += " WHERE status=%s"; args.append(status)
    q += " ORDER BY id DESC LIMIT %s"; args.append(min(limit, 200))
    with _db() as conn:
        rows = conn.execute(q, tuple(args)).fetchall()
    return [dict(r) for r in rows]


@app.post("/v1/actions/{action_id}/decide")
def action_decide(action_id: int, body: dict, authorization: str = Header(default=""),
                  x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    """Người duyệt: approve → thực thi; reject → bỏ. Không được tự duyệt việc mình đề xuất."""
    _require_admin(authorization)
    _ensure_schema()
    decision = (body.get("decision") or "").strip()
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision phải là approve|reject")
    approver = x_actor or body.get("approver") or "admin"
    with _db() as conn:
        a = conn.execute("SELECT * FROM pending_actions WHERE id=%s", (action_id,)).fetchone()
        if not a:
            raise HTTPException(status_code=404, detail="không thấy đề xuất")
        if a["status"] != "pending":
            raise HTTPException(status_code=409, detail=f"đề xuất đã ở trạng thái {a['status']}")
        # Separation of duty: người/agent đề xuất KHÔNG được tự duyệt.
        if approver == a["proposed_by"]:
            _audit(conn, approver, "action_self_approve_blocked", "action", str(action_id), {})
            conn.commit()
            raise HTTPException(status_code=403,
                                detail="không được tự duyệt hành động do chính mình đề xuất")
        if decision == "reject":
            conn.execute("UPDATE pending_actions SET status='rejected', approver=%s, "
                         "decided_at=now() WHERE id=%s", (approver, action_id))
            _audit(conn, approver, "action_reject", "action", str(action_id),
                   {"proposed_by": a["proposed_by"], "action": a["action"]})
            conn.commit()
            return {"id": action_id, "status": "rejected"}
        res = _execute_action(conn, a["action"], a["params"] or {}, approver)
        conn.execute("UPDATE pending_actions SET status='approved', approver=%s, "
                     "result=%s, decided_at=now() WHERE id=%s", (approver, Json(res), action_id))
        _audit(conn, approver, "action_approve", "action", str(action_id),
               {"proposed_by": a["proposed_by"], "action": a["action"], "result": res})
        conn.commit()
    return {"id": action_id, "status": "approved", "result": res}


def _expire_actions(conn) -> int:
    """Hết hạn đề xuất chưa ai duyệt; nhắc 1 lần trước khi hết hạn."""
    due = conn.execute(
        "SELECT id, proposed_by, action FROM pending_actions "
        "WHERE status='pending' AND reminded=false AND expires_at < now() + interval '2 hours'"
    ).fetchall()
    for d in due:
        _notify_admins(conn, f"⏰ Nhắc lần cuối: đề xuất #{d['id']} (`{d['action']}`) sắp hết hạn.",
                       action_id=d["id"])
        conn.execute("UPDATE pending_actions SET reminded=true WHERE id=%s", (d["id"],))
    n = conn.execute(
        "UPDATE pending_actions SET status='expired', decided_at=now() "
        "WHERE status='pending' AND expires_at < now()").rowcount
    return n


# -------- Ops snapshot: platform agent đọc sức khoẻ hệ thống --------

@app.get("/v1/self/ops/snapshot")
def ops_snapshot(authorization: str = Header(default="")) -> dict:
    """Số liệu vận hành cho AG-OPS: DLQ, queue, pool credential, agent im lặng, chi phí."""
    agent_id = _require_self(authorization)
    _ensure_schema()
    with _db() as conn:
        plat = conn.execute("SELECT is_platform FROM agents WHERE agent_id=%s",
                            (agent_id,)).fetchone()
        if not (plat or {}).get("is_platform"):
            raise HTTPException(status_code=403, detail="chỉ platform agent được xem snapshot")
        jobs = conn.execute(
            "SELECT status, count(*) n FROM jobs GROUP BY status").fetchall()
        dlq_by_agent = conn.execute(
            "SELECT agent_id, count(*) n FROM jobs WHERE status='dlq' GROUP BY agent_id "
            "ORDER BY n DESC LIMIT 10").fetchall()
        pool = conn.execute(
            f"SELECT kind, count(*) FILTER (WHERE {_USABLE}) usable, count(*) total "
            "FROM model_credentials GROUP BY kind").fetchall()
        silent = conn.execute(
            "SELECT a.agent_id, max(t.received_at) last_seen FROM agents a "
            "LEFT JOIN agent_traces t ON t.agent_id=a.agent_id "
            "WHERE a.status='active' GROUP BY a.agent_id "
            "HAVING max(t.received_at) IS NULL OR max(t.received_at) < now() - interval '24 hours'"
        ).fetchall()
        errs = conn.execute(
            "SELECT connector_id, count(*) n FROM tool_usage "
            "WHERE ok=false AND created_at > now() - interval '1 day' "
            "GROUP BY connector_id ORDER BY n DESC LIMIT 5").fetchall()
        pending = conn.execute(
            "SELECT count(*) n FROM pending_actions WHERE status='pending'").fetchone()["n"]
        # Binding "bắt tất": không khai app_id lẫn chat_id → hứng MỌI sự kiện của kênh
        # đó khi không có binding cụ thể hơn. Rất dễ đẩy tin sang nhầm agent.
        catchall = [dict(r) for r in conn.execute(
            "SELECT id, channel, agent_id, created_by, created_at FROM routing_binding "
            "WHERE active AND app_id IS NULL AND chat_id IS NULL ORDER BY id").fetchall()]
        lark_gaps = _lark_gateway_gaps(conn)
        # C8: refresh token Lark sống ~30 ngày. Hết mà không ai authorize lại thì agent
        # degrade âm thầm (AG-LEGAL mất 1 tháng mới phát hiện) — báo trước.
        user_ids = [dict(r) for r in conn.execute(
            "SELECT i.subject_email, i.app_id, "
            "  floor(extract(epoch from (i.refresh_expires_at - now()))/86400)::int AS days_left, "
            "  array_remove(array_agg(g.agent_id) FILTER (WHERE g.active), NULL) AS agents "
            "FROM lark_user_identities i "
            "LEFT JOIN agent_user_identity_grants g ON g.subject_email=i.subject_email "
            "WHERE i.refresh_expires_at < now() + make_interval(days => %s) "
            "GROUP BY i.subject_email, i.app_id, i.refresh_expires_at "
            "ORDER BY days_left", (LARK_USER_REFRESH_WARN_DAYS,)).fetchall()]
        expiring = conn.execute(
            "SELECT id, kind, owner_email, "
            "floor(extract(epoch from (expires_at - now()))/86400)::int AS days_left "
            "FROM model_credentials WHERE expires_at IS NOT NULL AND status <> 'disabled' "
            "  AND expires_at < now() + interval '30 days' ORDER BY expires_at").fetchall()
    return {
        "jobs": {r["status"]: r["n"] for r in jobs},
        "dlq_by_agent": [dict(r) for r in dlq_by_agent],
        "credential_pool": [dict(r) for r in pool],
        "silent_agents": [dict(r) for r in silent],
        "connector_errors_24h": [dict(r) for r in errs],
        "credentials_expiring": [dict(r) for r in expiring],
        "pending_actions": pending,
        "disk": _disk_usage(),
        "catchall_routes": catchall,
        "lark_gateway_gaps": lark_gaps,
        "lark_user_identities_expiring": user_ids,
    }


def _disk_usage() -> dict:
    """Dung lượng ổ của VM. Hết đĩa = build/deploy/DB chết đứng — phải cảnh báo sớm.

    (Sự cố 08-14: ổ đầy 100% do image Docker cũ tích tụ, deploy fail giữa chừng.)
    """
    try:
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        if not total:
            return {}
        return {"total_gb": round(total / 1e9, 1), "free_gb": round(free / 1e9, 1),
                "used_pct": round((total - free) / total * 100)}
    except Exception:
        return {}


# -------- Mart: rollup KPI (nguồn cho dashboard + đối soát) --------

def _build_mart(conn, days: int = 30) -> int:
    """Dựng lại mart_daily từ dữ liệu thô. A2A tính chi phí cho agent GỌI (caller-pays)."""
    conn.execute("DELETE FROM mart_daily WHERE day >= current_date - %s", (days,))
    # Nguồn chính: agent_traces (token/chi phí/lỗi) — quy chiếu kênh qua jobs nếu có.
    conn.execute(
        """
        INSERT INTO mart_daily(day, agent_id, channel, runs, tokens_in, tokens_out, errors)
        SELECT date(received_at) AS day, agent_id, '-' AS channel,
               count(*), sum(coalesce(input_tokens,0)), sum(coalesce(output_tokens,0)),
               sum(CASE WHEN status='error' THEN 1 ELSE 0 END)
        FROM agent_traces
        WHERE agent_id IS NOT NULL AND received_at >= current_date - %s
        GROUP BY 1,2
        ON CONFLICT (day, agent_id, channel) DO UPDATE SET
          runs=EXCLUDED.runs, tokens_in=EXCLUDED.tokens_in,
          tokens_out=EXCLUDED.tokens_out, errors=EXCLUDED.errors, built_at=now()
        """, (days,))
    # Job theo kênh (gồm a2a) — caller-pays: lượt a2a tính cho agent GỌI.
    # Dòng theo kênh chỉ mang SỐ LƯỢT YÊU CẦU (không mang token/chi phí) để tránh đếm trùng.
    conn.execute(
        """
        INSERT INTO mart_daily(day, agent_id, channel, runs)
        SELECT date(created_at),
               CASE WHEN channel='a2a' THEN coalesce(payload->>'from_agent', agent_id)
                    ELSE agent_id END,
               channel, count(*)
        FROM jobs
        WHERE agent_id IS NOT NULL AND created_at >= current_date - %s
        GROUP BY 1,2,3
        ON CONFLICT (day, agent_id, channel) DO UPDATE SET runs=EXCLUDED.runs, built_at=now()
        """, (days,))
    # Bảo đảm mỗi (ngày, agent) có ĐÚNG MỘT dòng tổng hợp channel='-' để gắn các
    # chỉ số cấp agent (tool_calls, a2a_out, eval) — nếu gắn vào mọi dòng kênh thì
    # tổng theo agent sẽ ĐẾM TRÙNG.
    conn.execute(
        """
        INSERT INTO mart_daily(day, agent_id, channel)
        SELECT DISTINCT day, agent_id, '-' FROM mart_daily
        WHERE day >= current_date - %s
        ON CONFLICT (day, agent_id, channel) DO NOTHING
        """, (days,))
    # Lượt A2A đi ra (caller-pays) — CHỈ ghi vào dòng tổng hợp.
    conn.execute(
        """
        UPDATE mart_daily m SET a2a_out = s.n FROM (
            SELECT date(created_at) d, caller_id, count(*) n FROM a2a_requests
            WHERE created_at >= current_date - %s GROUP BY 1,2
        ) s WHERE m.day=s.d AND m.agent_id=s.caller_id AND m.channel='-'
        """, (days,))
    # Tool calls — CHỈ ghi vào dòng tổng hợp.
    conn.execute(
        """
        UPDATE mart_daily m SET tool_calls = s.n FROM (
            SELECT date(created_at) d, agent_id, count(*) n FROM tool_usage
            WHERE created_at >= current_date - %s GROUP BY 1,2
        ) s WHERE m.day=s.d AND m.agent_id=s.agent_id AND m.channel='-'
        """, (days,))
    # Điểm eval mới nhất trong ngày — CHỈ ghi vào dòng tổng hợp.
    conn.execute(
        """
        UPDATE mart_daily m SET eval_score = s.score FROM (
            SELECT date(at) d, target_id, max(score) score FROM regression_runs
            WHERE at >= current_date - %s GROUP BY 1,2
        ) s WHERE m.day=s.d AND m.agent_id=s.target_id AND m.channel='-'
        """, (days,))
    # Chi phí ước tính theo giá công khai (token chỉ nằm ở dòng tổng hợp).
    conn.execute(
        "UPDATE mart_daily SET cost_usd = round((tokens_in * %s + tokens_out * %s)::numeric, 4) "
        "WHERE day >= current_date - %s", (3.0 / 1e6, 15.0 / 1e6, days))
    return conn.execute("SELECT count(*) n FROM mart_daily").fetchone()["n"]


@app.post("/v1/mart/rebuild")
def mart_rebuild(authorization: str = Header(default=""), days: int = 30) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        n = _build_mart(conn, min(days, 365))
        _audit(conn, "system", "mart_rebuild", "mart", "daily", {"rows": n, "days": days})
        conn.commit()
    return {"rows": n, "days": days}


@app.get("/v1/mart/kpi")
def mart_kpi(authorization: str = Header(default=""), days: int = 7) -> dict:
    """KPI theo agent (và theo kênh) trong N ngày — nguồn cho dashboard BOD."""
    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        # Chỉ số cấp agent nằm ở dòng tổng hợp (channel='-'); số lượt theo kênh lấy riêng
        # → không đếm trùng khi cộng.
        by_agent = conn.execute(
            """
            SELECT m.agent_id,
                   sum(m.runs) runs, sum(m.tokens_in + m.tokens_out) tokens,
                   sum(m.cost_usd) cost_usd, sum(m.errors) errors,
                   sum(m.tool_calls) tool_calls, sum(m.a2a_out) a2a_out,
                   max(m.eval_score) eval_score,
                   coalesce((SELECT sum(j.runs) FROM mart_daily j
                             WHERE j.agent_id=m.agent_id AND j.channel <> '-'
                               AND j.day >= current_date - %s), 0) AS requests
            FROM mart_daily m
            WHERE m.day >= current_date - %s AND m.channel = '-'
            GROUP BY m.agent_id ORDER BY tokens DESC
            """, (days, days)).fetchall()
        by_day = conn.execute(
            "SELECT day, sum(runs) runs, sum(cost_usd) cost_usd, sum(errors) errors "
            "FROM mart_daily WHERE day >= current_date - %s AND channel='-' "
            "GROUP BY day ORDER BY day", (days,)).fetchall()
        by_channel = conn.execute(
            "SELECT channel, sum(runs) runs FROM mart_daily WHERE day >= current_date - %s "
            "AND channel <> '-' GROUP BY channel ORDER BY runs DESC", (days,)).fetchall()
    return {"days": days, "by_agent": [dict(r) for r in by_agent],
            "by_day": [dict(r) for r in by_day], "by_channel": [dict(r) for r in by_channel]}


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


def _notify_owner_checklist(conn, agent_id: str, miss: list[str]) -> None:
    """Nhắc OWNER những mục checklist còn thiếu (Lark DM, fallback nhóm chung)."""
    row = conn.execute("SELECT owner, name FROM agents WHERE agent_id=%s", (agent_id,)).fetchone()
    owner = (row or {}).get("owner") or ""
    text = (f"📋 Agent {agent_id} ({(row or {}).get('name') or '?'}) chưa golive được: "
            f"còn thiếu {len(miss)} mục checklist.\n"
            f"Thiếu: {', '.join(miss)}\n"
            f"Bổ sung tại Console → Agent → Golive checklist. Đủ mục là hệ thống tự trình "
            f"admin duyệt, anh/chị không cần xin riêng.")
    _audit(conn, "system", "golive_blocked", "agent", agent_id,
           {"missing": miss, "owner_notified": owner})
    if owner:
        _send_lark(owner, text)


def _request_golive_approval(conn, agent_id: str, actor: str) -> int | None:
    """Checklist đã đủ → tạo đề xuất ACTIVATE cho admin duyệt (HITL, tách vai).

    Người nộp checklist (owner) là bên đề xuất; admin là bên duyệt — owner không tự
    bật agent của mình. Trả id đề xuất, hoặc None nếu đã có đề xuất đang chờ.
    """
    st = conn.execute("SELECT status, name, owner FROM agents WHERE agent_id=%s",
                      (agent_id,)).fetchone() or {}
    if st.get("status") == "active":
        return None
    dup = conn.execute(
        "SELECT id FROM pending_actions WHERE status='pending' AND action='activate_agent' "
        "AND params->>'agent_id'=%s", (agent_id,)).fetchone()
    if dup:
        return dup["id"]
    row = conn.execute(
        "INSERT INTO pending_actions(action, params, risk, reason, proposed_by, status) "
        "VALUES ('activate_agent', %s, 'high', %s, %s, 'pending') RETURNING id",
        (Json({"agent_id": agent_id}),
         f"checklist golive ĐỦ — {actor} xin duyệt golive cho {agent_id}", actor)).fetchone()
    _notify_admins(conn,
                   f"✅ Agent {agent_id} ({st.get('name') or '?'}) đã ĐỦ golive checklist.\n"
                   f"Owner: {st.get('owner') or '?'} · người nộp: {actor}\n"
                   f"Duyệt để agent chạy kênh thật: {APP_PUBLIC_URL}/approvals",
                   action_id=row["id"])
    return row["id"]


@app.post("/v1/agents/{agent_id}/golive-checklist")
def submit_checklist(agent_id: str, body: dict, authorization: str = Header(default="")) -> dict:
    """Owner nộp checklist; đủ mục thì TỰ trình admin duyệt golive.

    Owner/moderator của agent nộp được (không cần admin platform) — đúng người làm
    đúng việc; quyền BẬT agent vẫn nằm ở admin.
    """

    p = _require_role(authorization, "moderator", agent_id)
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
        req_id = None if miss else _request_golive_approval(
            conn, agent_id, p["actor"] or "owner")
        conn.commit()
    if miss:
        return {"agent_id": agent_id, "complete": False, "missing": miss,
                "next": "bổ sung các mục còn thiếu rồi nộp lại"}
    return {"agent_id": agent_id, "complete": True, "missing": [],
            "approval_request_id": req_id,
            "next": "đã trình admin duyệt golive — chờ admin bấm Duyệt ở Console → Duyệt việc"}


@app.get("/v1/agents/{agent_id}/golive-checklist")
def get_checklist(agent_id: str, authorization: str = Header(default="")) -> dict:
    """Xem checklist. CẦN quyền trên agent — payload chứa email, KPI, nguồn dữ liệu nội bộ.

    (Trước 18/08 endpoint này không kiểm quyền; khi mở path qua Caddy cho owner nộp từ
    máy dev thì hở ra ngoài internet, nên siết lại.)
    """
    _require_role(authorization, "user", agent_id)
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
                                         passed, n_total, n_pass, threshold, detail, run_by,
                                         agent_version)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (rid, body.get("target_type", "agent"), body.get("target_id"), skill,
             score, passed, len(cases), n_pass, threshold, Json(detail),
             body.get("run_by", "admin"),
             # P3: gắn run với version cụ thể → eval gate không mượn kết quả version khác.
             body.get("agent_version")),
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


# P4: purge THẬT theo retention_config (chỉ scope bật enabled). Chạy nền + gọi tay được.
_PURGE_TARGETS = {
    # scope        -> (bảng, cột thời gian)
    "traces":        ("agent_traces", "received_at"),
    "audit":         ("audit_log", "at"),
    "notifications": ("notifications", "created_at"),
    "sessions":      ("sessions", "updated_at"),
    "user_facts":    ("user_facts", "updated_at"),
    "jobs":          ("jobs", "updated_at"),
}


def _run_purge(conn) -> list[dict]:
    """Xoá dữ liệu quá TTL cho các scope đã bật. Trả danh sách đã dọn."""
    done = []
    rows = conn.execute(
        "SELECT scope, ttl_days FROM retention_config WHERE enabled=true AND ttl_days > 0"
    ).fetchall()
    for r in rows:
        tgt = _PURGE_TARGETS.get(r["scope"])
        if not tgt:
            continue
        table, tcol = tgt
        try:
            n = conn.execute(
                f"DELETE FROM {table} WHERE {tcol} < now() - make_interval(days => %s)",
                (int(r["ttl_days"]),)).rowcount
        except Exception as exc:
            done.append({"scope": r["scope"], "error": str(exc)[:120]})
            continue
        if n:
            _audit(conn, "system", "retention_purge", "retention", r["scope"],
                   {"deleted": n, "ttl_days": r["ttl_days"]})
        done.append({"scope": r["scope"], "deleted": n, "ttl_days": r["ttl_days"]})
    return done


@app.post("/v1/retention/purge")
def retention_purge(authorization: str = Header(default="")) -> dict:
    """Chạy dọn ngay theo cấu hình (admin). Job nền cũng gọi hàm này mỗi giờ."""
    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        res = _run_purge(conn)
        conn.commit()
    return {"purged": res}


# ============================ Shared Brain — đồ thị 3D ============================

@app.get("/v1/brain/graph")
def brain_graph(scope: str = "shared", agent_id: str | None = None) -> dict:
    """Đồ thị brain cho visualize 3D: node kb/belief/skill/policy/domain/team +
    cạnh có LOẠI quan hệ (brain_links) + cạnh cấu trúc (in_domain/from_team).
    scope=shared (mặc định) hoặc scope=agent&agent_id=... cho brain riêng agent."""

    _ensure_schema()
    nodes: dict = {}
    links: list = []

    def _node(nid, ntype, label, **extra):
        if nid not in nodes:
            nodes[nid] = {"id": nid, "type": ntype, "label": (label or nid)[:80], **extra}

    where = "scope=%s" + (" AND agent_id=%s" if scope == "agent" and agent_id else "")
    args = [scope] + ([agent_id] if scope == "agent" and agent_id else [])
    with _db() as conn:
        for it in conn.execute(
            f"SELECT item_id,kind,title,content,domain,source_team,source_url FROM brain_items "
            f"WHERE {where} AND status='approved'", args).fetchall():
            t = "belief" if it["kind"] == "belief" else "knowledge"
            _node(it["item_id"], t, it.get("title"), detail=(it.get("content") or "")[:600],
                  source_url=it.get("source_url"), domain=it.get("domain"), kind=it["kind"],
                  source_team=it.get("source_team"))
            if it.get("domain"):
                _node(f"domain:{it['domain']}", "domain", it["domain"])
                links.append({"source": it["item_id"], "target": f"domain:{it['domain']}", "rel": "in_domain"})
            if it.get("source_team"):
                _node(f"team:{it['source_team']}", "team", it["source_team"])
                links.append({"source": it["item_id"], "target": f"team:{it['source_team']}", "rel": "from_team"})
        for s in conn.execute(
            f"SELECT skill_id,name,domain,source_url FROM brain_skills WHERE {where} AND status='active'",
            args).fetchall():
            _node(s["skill_id"], "skill", s.get("name"), source_url=s.get("source_url"), domain=s.get("domain"))
            if s.get("domain"):
                _node(f"domain:{s['domain']}", "domain", s["domain"])
                links.append({"source": s["skill_id"], "target": f"domain:{s['domain']}", "rel": "in_domain"})
        if scope == "shared":
            for p in conn.execute(
                "SELECT policy_id,title,reason,domain,source_url FROM policies WHERE active=true"
            ).fetchall():
                _node(p["policy_id"], "policy", p.get("title") or p.get("reason") or p["policy_id"],
                      source_url=p.get("source_url"), domain=p.get("domain"))
                if p.get("domain"):
                    _node(f"domain:{p['domain']}", "domain", p["domain"])
                    links.append({"source": p["policy_id"], "target": f"domain:{p['domain']}", "rel": "in_domain"})
        # Cạnh typed (chỉ nối node đã tồn tại)
        for l in conn.execute("SELECT from_id,to_id,rel,status FROM brain_links").fetchall():
            if l["from_id"] in nodes and l["to_id"] in nodes:
                links.append({"source": l["from_id"], "target": l["to_id"],
                              "rel": l["rel"], "status": l["status"]})

    node_list = list(nodes.values())
    counts = {t: sum(1 for n in node_list if n["type"] == t)
              for t in ("domain", "belief", "knowledge", "skill", "policy", "team")}
    return {"nodes": node_list, "links": links, "counts": counts}


# ============================ Brain v2 — items / skills / policies / links ============================
_REL_OK = {"relates_to","depends_on","derived_from","supersedes","contradicts","refines","uses_skill","governed_by"}
_KIND_OK = {"knowledge","process","definition","lesson","belief","faq"}


def _rev_can_domain(conn, email: str, domain: str) -> bool:
    """Reviewer được duyệt domain này? (hoặc domain='*')."""
    if not email:
        return False
    row = conn.execute(
        "SELECT 1 FROM knowledge_reviewers WHERE email=%s AND (domain=%s OR domain='*')",
        (email, domain or "")).fetchone()
    return bool(row)


@app.get("/v1/brain/items")
def brain_items(scope: str = "shared", agent_id: str | None = None, kind: str | None = None,
                domain: str | None = None, status: str | None = None, tag: str | None = None,
                q: str | None = None, limit: int = 200) -> list[dict]:
    _ensure_schema()
    sql = ("SELECT item_id,kind,title,content,domain,tags,scope,agent_id,source_agent,"
           "source_team,source_url,status,reviewed_by,version,created_at,updated_at "
           "FROM brain_items WHERE scope=%s")
    args: list = [scope]
    if scope == "agent" and agent_id:
        sql += " AND agent_id=%s"; args.append(agent_id)
    for col, val in (("kind", kind), ("domain", domain), ("status", status)):
        if val:
            sql += f" AND {col}=%s"; args.append(val)
    if tag:
        sql += " AND %s = ANY(tags)"; args.append(tag)
    if q:
        sql += " AND (title ILIKE %s OR content ILIKE %s)"; args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY updated_at DESC LIMIT %s"; args.append(min(int(limit), 500))
    with _db() as conn:
        return conn.execute(sql, args).fetchall()


@app.post("/v1/brain/items")
def brain_item_upsert(body: dict, authorization: str = Header(default=""),
                      x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    """Tạo/sửa tri thức (admin). Import cũng qua đây. Mặc định status=pending (belief=approved)."""
    _require_admin(authorization)
    _ensure_schema()
    iid = body.get("item_id") or ("k_" + secrets.token_hex(6))
    kind = body.get("kind", "knowledge")
    if kind not in _KIND_OK:
        raise HTTPException(status_code=422, detail=f"kind phải thuộc {_KIND_OK}")
    tags = body.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    status = body.get("status") or ("approved" if kind == "belief" else "pending")
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO brain_items(item_id,kind,title,content,domain,tags,scope,agent_id,
                source_agent,source_team,source_url,source_ref,status,version,created_by,updated_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s)
            ON CONFLICT (item_id) DO UPDATE SET kind=EXCLUDED.kind,title=EXCLUDED.title,
                content=EXCLUDED.content,domain=EXCLUDED.domain,tags=EXCLUDED.tags,
                source_url=EXCLUDED.source_url,status=EXCLUDED.status,
                version=brain_items.version+1,updated_by=EXCLUDED.updated_by,updated_at=now()
            """,
            (iid, kind, body.get("title"), body.get("content"), body.get("domain"), tags,
             body.get("scope", "shared"), body.get("agent_id"), body.get("source_agent"),
             body.get("source_team"), body.get("source_url"), body.get("source_ref"),
             status, x_actor or "admin", x_actor or "admin"),
        )
        _audit(conn, x_actor or "admin", "brain_upsert", "brain_item", iid,
               {"kind": kind, "domain": body.get("domain"), "status": status})
        conn.commit()
    return {"item_id": iid, "status": status, "ok": True}


@app.post("/v1/brain/items/{item_id}/review")
def brain_item_review(item_id: str, body: dict, authorization: str = Header(default="")) -> dict:
    """Reviewer (theo domain) hoặc admin duyệt/loại tri thức."""
    _ensure_schema()
    decision = body.get("decision")
    if decision not in ("approved", "rejected", "deprecated"):
        raise HTTPException(status_code=422, detail="decision: approved|rejected|deprecated")
    reviewer = body.get("reviewer_email") or ""
    is_admin = (ADMIN_TOKEN and authorization == f"Bearer {ADMIN_TOKEN}") or \
               (body.get("admin_token") and body["admin_token"] == ADMIN_TOKEN)
    with _db() as conn:
        it = conn.execute("SELECT domain FROM brain_items WHERE item_id=%s", (item_id,)).fetchone()
        if not it:
            raise HTTPException(status_code=404, detail="không tìm thấy")
        if not is_admin and not _rev_can_domain(conn, reviewer, it["domain"]):
            raise HTTPException(status_code=403, detail=f"{reviewer} không có quyền duyệt domain '{it['domain']}'")
        conn.execute("UPDATE brain_items SET status=%s,reviewed_by=%s,review_note=%s,reviewed_at=now(),"
                     "updated_at=now() WHERE item_id=%s",
                     (decision, reviewer or "admin", body.get("note"), item_id))
        _audit(conn, reviewer or "admin", "brain_review", "brain_item", item_id, {"decision": decision})
        conn.commit()
    return {"item_id": item_id, "status": decision}


@app.post("/v1/brain/items/{item_id}/delete")
def brain_item_delete(item_id: str, authorization: str = Header(default=""),
                      x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        conn.execute("DELETE FROM brain_items WHERE item_id=%s", (item_id,))
        conn.execute("DELETE FROM brain_links WHERE from_id=%s OR to_id=%s", (item_id, item_id))
        _audit(conn, x_actor or "admin", "brain_delete", "brain_item", item_id, {})
        conn.commit()
    return {"item_id": item_id, "deleted": True}


@app.get("/v1/brain/skills")
def brain_skills(scope: str = "shared", agent_id: str | None = None, domain: str | None = None,
                 status: str | None = None) -> list[dict]:
    _ensure_schema()
    sql = ("SELECT skill_id,name,kind,description,domain,tags,scope,agent_id,owner,status,"
           "source_url,updated_at FROM brain_skills WHERE scope=%s")
    args: list = [scope]
    if scope == "agent" and agent_id:
        sql += " AND agent_id=%s"; args.append(agent_id)
    for col, val in (("domain", domain), ("status", status)):
        if val:
            sql += f" AND {col}=%s"; args.append(val)
    sql += " ORDER BY updated_at DESC"
    with _db() as conn:
        return conn.execute(sql, args).fetchall()


@app.post("/v1/brain/skills")
def brain_skill_upsert(body: dict, authorization: str = Header(default=""),
                       x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    sid = body.get("skill_id") or ("sk-" + (body.get("name") or secrets.token_hex(4)))
    tags = body.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO brain_skills(skill_id,name,kind,description,domain,tags,scope,agent_id,
                                     owner,status,source_url,updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
            ON CONFLICT (skill_id) DO UPDATE SET name=EXCLUDED.name,kind=EXCLUDED.kind,
              description=EXCLUDED.description,domain=EXCLUDED.domain,tags=EXCLUDED.tags,
              status=EXCLUDED.status,source_url=EXCLUDED.source_url,updated_at=now()
            """,
            (sid, body.get("name"), body.get("kind", "mcp"), body.get("description"),
             body.get("domain"), tags, body.get("scope", "shared"), body.get("agent_id"),
             body.get("owner"), body.get("status", "proposed"), body.get("source_url")),
        )
        _audit(conn, x_actor or "admin", "skill_upsert", "skill", sid, {"status": body.get("status")})
        conn.commit()
    return {"skill_id": sid, "ok": True}


@app.get("/v1/brain/policies")
def brain_policies() -> list[dict]:
    _ensure_schema()
    with _db() as conn:
        return conn.execute(
            "SELECT policy_id,title,description,scope,agent_id,phase,effect,domain,owner,"
            "active,reason,created_at,updated_at FROM policies ORDER BY created_at DESC").fetchall()


@app.get("/v1/brain/links")
def brain_links(status: str | None = None) -> list[dict]:
    _ensure_schema()
    sql = "SELECT link_id,from_id,from_type,to_id,to_type,rel,note,status,source_url,created_by,created_at FROM brain_links"
    args: list = []
    if status:
        sql += " WHERE status=%s"; args.append(status)
    sql += " ORDER BY created_at DESC LIMIT 500"
    with _db() as conn:
        return conn.execute(sql, args).fetchall()


@app.post("/v1/brain/links")
def brain_link_create(body: dict, authorization: str = Header(default=""),
                      x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    if body.get("rel") not in _REL_OK:
        raise HTTPException(status_code=422, detail=f"rel phải thuộc {_REL_OK}")
    lid = body.get("link_id") or ("l_" + secrets.token_hex(6))
    with _db() as conn:
        conn.execute(
            "INSERT INTO brain_links(link_id,from_id,from_type,to_id,to_type,rel,note,status,"
            "source_url,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (link_id) DO NOTHING",
            (lid, body.get("from_id"), body.get("from_type", "kb"), body.get("to_id"),
             body.get("to_type", "kb"), body.get("rel"), body.get("note"),
             body.get("status", "confirmed"), body.get("source_url"), x_actor or "admin"))
        _audit(conn, x_actor or "admin", "link_create", "brain_link", lid,
               {"rel": body.get("rel"), "from": body.get("from_id"), "to": body.get("to_id")})
        conn.commit()
    return {"link_id": lid, "ok": True}


@app.post("/v1/brain/links/{link_id}/confirm")
def brain_link_confirm(link_id: str, body: dict, authorization: str = Header(default=""),
                       x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    decision = body.get("decision", "confirmed")  # confirmed | rejected
    with _db() as conn:
        if decision == "rejected":
            conn.execute("DELETE FROM brain_links WHERE link_id=%s", (link_id,))
        else:
            conn.execute("UPDATE brain_links SET status='confirmed' WHERE link_id=%s", (link_id,))
        _audit(conn, x_actor or "admin", "link_confirm", "brain_link", link_id, {"decision": decision})
        conn.commit()
    return {"link_id": link_id, "status": decision}


@app.post("/v1/brain/links/{link_id}/delete")
def brain_link_delete(link_id: str, authorization: str = Header(default=""),
                      x_actor: str = Header(default="", alias="X-Actor")) -> dict:
    _require_admin(authorization)
    _ensure_schema()
    with _db() as conn:
        conn.execute("DELETE FROM brain_links WHERE link_id=%s", (link_id,))
        _audit(conn, x_actor or "admin", "link_delete", "brain_link", link_id, {})
        conn.commit()
    return {"link_id": link_id, "deleted": True}


# ============================ Brain per-agent (agent-scoped, /v1/self/brain/*) ============================
# Mọi agent quản lý brain RIÊNG bằng token của mình — giống console platform nhưng scope=agent.

@app.get("/v1/self/brain/items")
def self_brain_items(authorization: str = Header(default=""), status: str | None = None,
                     domain: str | None = None, q: str | None = None) -> list[dict]:
    aid = _require_self(authorization)
    sql = ("SELECT item_id,kind,title,content,domain,tags,source_agent,source_team,source_url,"
           "status,version,created_at,updated_at FROM brain_items WHERE scope='agent' AND agent_id=%s")
    args: list = [aid]
    if status: sql += " AND status=%s"; args.append(status)
    if domain: sql += " AND domain=%s"; args.append(domain)
    if q: sql += " AND (title ILIKE %s OR content ILIKE %s)"; args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY updated_at DESC LIMIT 300"
    with _db() as conn:
        return conn.execute(sql, args).fetchall()


@app.post("/v1/self/brain/items")
def self_brain_upsert(body: dict, authorization: str = Header(default="")) -> dict:
    aid = _require_self(authorization)
    _ensure_schema()
    iid = body.get("item_id") or ("ak_" + secrets.token_hex(6))
    kind = body.get("kind", "knowledge")
    if kind not in _KIND_OK:
        raise HTTPException(status_code=422, detail=f"kind phải thuộc {_KIND_OK}")
    tags = body.get("tags") or []
    if isinstance(tags, str): tags = [t.strip() for t in tags.split(",") if t.strip()]
    with _db() as conn:
        # chỉ cho sửa item thuộc chính agent này
        ex = conn.execute("SELECT agent_id FROM brain_items WHERE item_id=%s", (iid,)).fetchone()
        if ex and ex["agent_id"] != aid:
            raise HTTPException(status_code=403, detail="item không thuộc agent này")
        conn.execute(
            """
            INSERT INTO brain_items(item_id,kind,title,content,domain,tags,scope,agent_id,
                source_agent,source_url,source_ref,status,version,created_by,updated_by)
            VALUES (%s,%s,%s,%s,%s,%s,'agent',%s,%s,%s,%s,%s,1,%s,%s)
            ON CONFLICT (item_id) DO UPDATE SET kind=EXCLUDED.kind,title=EXCLUDED.title,
                content=EXCLUDED.content,domain=EXCLUDED.domain,tags=EXCLUDED.tags,
                source_url=EXCLUDED.source_url,status=EXCLUDED.status,
                version=brain_items.version+1,updated_by=EXCLUDED.updated_by,updated_at=now()
            """,
            (iid, kind, body.get("title"), body.get("content"), body.get("domain"), tags, aid,
             aid, body.get("source_url"), body.get("source_ref"),
             body.get("status", "approved"), aid, aid))  # owner tự quản → mặc định approved trong agent
        _audit(conn, aid, "self_brain_upsert", "brain_item", iid, {"kind": kind})
        conn.commit()
    return {"item_id": iid, "ok": True, "scope": "agent", "agent_id": aid}


@app.post("/v1/self/brain/items/{item_id}/delete")
def self_brain_delete(item_id: str, authorization: str = Header(default="")) -> dict:
    aid = _require_self(authorization)
    with _db() as conn:
        r = conn.execute("SELECT agent_id FROM brain_items WHERE item_id=%s", (item_id,)).fetchone()
        if not r or r["agent_id"] != aid:
            raise HTTPException(status_code=403, detail="không thuộc agent này")
        conn.execute("DELETE FROM brain_items WHERE item_id=%s", (item_id,))
        conn.execute("DELETE FROM brain_links WHERE from_id=%s OR to_id=%s", (item_id, item_id))
        _audit(conn, aid, "self_brain_delete", "brain_item", item_id, {})
        conn.commit()
    return {"item_id": item_id, "deleted": True}


@app.get("/v1/self/brain/links")
def self_brain_links(authorization: str = Header(default="")) -> list[dict]:
    aid = _require_self(authorization)
    with _db() as conn:
        ids = [r["item_id"] for r in conn.execute(
            "SELECT item_id FROM brain_items WHERE scope='agent' AND agent_id=%s", (aid,)).fetchall()]
        if not ids:
            return []
        return conn.execute(
            "SELECT link_id,from_id,to_id,rel,status,created_by,created_at FROM brain_links "
            "WHERE from_id = ANY(%s) OR to_id = ANY(%s) ORDER BY created_at DESC", (ids, ids)).fetchall()


@app.post("/v1/self/brain/links")
def self_brain_link(body: dict, authorization: str = Header(default="")) -> dict:
    aid = _require_self(authorization)
    if body.get("rel") not in _REL_OK:
        raise HTTPException(status_code=422, detail=f"rel phải thuộc {_REL_OK}")
    lid = "l_" + secrets.token_hex(6)
    with _db() as conn:
        # from_id phải thuộc agent này
        r = conn.execute("SELECT agent_id FROM brain_items WHERE item_id=%s", (body.get("from_id"),)).fetchone()
        if not r or r["agent_id"] != aid:
            raise HTTPException(status_code=403, detail="from_id không thuộc agent này")
        conn.execute("INSERT INTO brain_links(link_id,from_id,from_type,to_id,to_type,rel,status,created_by) "
                     "VALUES (%s,%s,%s,%s,%s,%s,'confirmed',%s)",
                     (lid, body.get("from_id"), "kb", body.get("to_id"), body.get("to_type", "kb"),
                      body.get("rel"), aid))
        _audit(conn, aid, "self_link_create", "brain_link", lid, {"rel": body.get("rel")})
        conn.commit()
    return {"link_id": lid, "ok": True}


@app.get("/v1/self/brain/graph")
def self_brain_graph(authorization: str = Header(default="")) -> dict:
    aid = _require_self(authorization)
    return brain_graph(scope="agent", agent_id=aid)
