"""BQ sink — đẩy dữ liệu platform (Postgres trên VM) sang BigQuery dataset AI_DB.

Postgres trên VM = DB giao dịch (registry, trace, test & learn, schema-per-agent).
BigQuery AI_DB = kho phân tích, nằm cạnh các dataset vận hành 0_lsr_*.

Chạy định kỳ (mặc định mỗi 15 phút). Idempotent: dùng insertId theo khoá tự nhiên
để BigQuery loại trùng (best-effort dedup ~1 phút), và chỉ đẩy bản ghi mới hơn watermark.

Xác thực (theo thứ tự):
  1. GOOGLE_APPLICATION_CREDENTIALS (service account JSON), hoặc
  2. metadata server của VM (cần scope bigquery trên instance).
"""

from __future__ import annotations

import json
import logging
import os
import time

import psycopg
import requests
from psycopg.rows import dict_row

PROJECT = os.environ.get("BQ_PROJECT", "ganesha-381907")
DATASET = os.environ.get("BQ_DATASET", "AI_DB")
DATABASE_URL = os.environ["DATABASE_URL"]
INTERVAL = int(os.environ.get("SINK_INTERVAL_SECONDS", "900"))
SA_FILE = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bq-sink")

_BQ = "https://bigquery.googleapis.com/bigquery/v2"


# ----------------------- Auth -----------------------

def _token_from_metadata() -> str:
    r = requests.get(
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
        headers={"Metadata-Flavor": "Google"}, timeout=5,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _token_from_sa() -> str:
    """JWT-bearer flow bằng service account JSON (không cần thư viện google-auth)."""

    import base64
    import datetime

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    info = json.load(open(SA_FILE, encoding="utf-8"))
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claim = {
        "iss": info["client_email"],
        "scope": "https://www.googleapis.com/auth/bigquery",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now, "exp": now + 3600,
    }
    b64 = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=")
    signing_input = b64(header) + b"." + b64(claim)
    key = serialization.load_pem_private_key(info["private_key"].encode(), password=None)
    sig = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    assertion = signing_input + b"." + base64.urlsafe_b64encode(sig).rstrip(b"=")
    r = requests.post(
        "https://oauth2.googleapis.com/token",
        data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def get_token() -> str:
    if SA_FILE and os.path.exists(SA_FILE):
        return _token_from_sa()
    return _token_from_metadata()


# ----------------------- BigQuery -----------------------

def ensure_table(token: str, table: str, fields: list[dict]) -> None:
    """Tạo bảng nếu chưa có (idempotent)."""

    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{_BQ}/projects/{PROJECT}/datasets/{DATASET}/tables"
    body = {
        "tableReference": {"projectId": PROJECT, "datasetId": DATASET, "tableId": table},
        "schema": {"fields": fields},
    }
    r = requests.post(url, headers=h, json=body, timeout=20)
    if r.status_code in (200, 201):
        log.info("Đã tạo bảng %s", table)
    elif r.status_code == 409:
        pass  # đã tồn tại
    else:
        log.warning("ensure_table %s -> %s %s", table, r.status_code, r.text[:200])


def insert_rows(token: str, table: str, rows: list[dict], id_key: str) -> int:
    if not rows:
        return 0
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{_BQ}/projects/{PROJECT}/datasets/{DATASET}/tables/{table}/insertAll"
    payload = {
        "kind": "bigquery#tableDataInsertAllRequest",
        "skipInvalidRows": False,
        "rows": [{"insertId": str(r.get(id_key)), "json": r} for r in rows],
    }
    resp = requests.post(url, headers=h, json=payload, timeout=30)
    if resp.status_code != 200:
        log.error("insertAll %s -> %s %s", table, resp.status_code, resp.text[:300])
        return 0
    errs = resp.json().get("insertErrors")
    if errs:
        log.warning("insertAll %s có lỗi dòng: %s", table, json.dumps(errs)[:300])
    return len(rows)


# ----------------------- Sync -----------------------

TABLES = {
    "agent_traces": {
        "fields": [
            {"name": "run_id", "type": "STRING"}, {"name": "agent_id", "type": "STRING"},
            {"name": "task_id", "type": "STRING"}, {"name": "source", "type": "STRING"},
            {"name": "input_tokens", "type": "INTEGER"}, {"name": "output_tokens", "type": "INTEGER"},
            {"name": "total_tokens", "type": "INTEGER"}, {"name": "tool_calls", "type": "INTEGER"},
            {"name": "received_at", "type": "TIMESTAMP"},
        ],
        "sql": ("SELECT id, run_id, agent_id, task_id, source, input_tokens, output_tokens, "
                "total_tokens, tool_calls, received_at FROM agent_traces WHERE id > %s ORDER BY id LIMIT 1000"),
    },
    "attempts": {
        "fields": [
            {"name": "attempt_id", "type": "STRING"}, {"name": "test_id", "type": "STRING"},
            {"name": "taker_type", "type": "STRING"}, {"name": "taker_id", "type": "STRING"},
            {"name": "score", "type": "FLOAT"}, {"name": "passed", "type": "BOOLEAN"},
            {"name": "at", "type": "TIMESTAMP"},
        ],
        "sql": ("SELECT attempt_id, test_id, taker_type, taker_id, score, passed, at "
                "FROM attempts WHERE at > COALESCE(%s::timestamptz, '-infinity') ORDER BY at LIMIT 1000"),
    },
}

_STATE = "/tmp/bq_sink_state.json"


def load_state() -> dict:
    try:
        return json.load(open(_STATE, encoding="utf-8"))
    except Exception:
        return {}


def save_state(s: dict) -> None:
    try:
        json.dump(s, open(_STATE, "w", encoding="utf-8"))
    except Exception:
        pass


def sync_once() -> None:
    token = get_token()
    state = load_state()
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        # traces: watermark theo id
        ensure_table(token, "agent_traces", TABLES["agent_traces"]["fields"])
        last_id = int(state.get("agent_traces_id", 0))
        rows = conn.execute(TABLES["agent_traces"]["sql"], (last_id,)).fetchall()
        payload = []
        for r in rows:
            last_id = max(last_id, r.pop("id"))
            r["received_at"] = r["received_at"].isoformat() if r.get("received_at") else None
            payload.append(r)
        n1 = insert_rows(token, "agent_traces", payload, "run_id")
        state["agent_traces_id"] = last_id

        # attempts: watermark theo thời gian
        ensure_table(token, "attempts", TABLES["attempts"]["fields"])
        last_at = state.get("attempts_at")
        rows = conn.execute(TABLES["attempts"]["sql"], (last_at,)).fetchall()
        payload = []
        for r in rows:
            if r.get("at"):
                state["attempts_at"] = r["at"].isoformat()
                r["at"] = r["at"].isoformat()
            payload.append(r)
        n2 = insert_rows(token, "attempts", payload, "attempt_id")

    save_state(state)
    log.info("Sink xong: %s traces, %s attempts -> %s.%s", n1, n2, PROJECT, DATASET)


def main() -> None:
    log.info("BQ sink khởi động: %s.%s mỗi %ss", PROJECT, DATASET, INTERVAL)
    while True:
        try:
            sync_once()
        except Exception as exc:
            log.exception("sync lỗi: %s", exc)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
