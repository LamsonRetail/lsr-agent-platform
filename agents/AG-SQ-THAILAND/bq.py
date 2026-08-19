"""BigQuery chỉ-đọc cho Ploy — service account, không cần thư viện ngoài.

Vì sao tự viết: consumer chạy bằng python hệ thống, chủ trương chỉ dùng stdlib
(xem thailand_tools.py). google-cloud-bigquery kéo theo ~10 package; ở đây chỉ
cần 3 việc: ký JWT (nhờ `openssl`), đổi JWT lấy access token, gọi REST jobs.query.

Khoá: env/bq-service-account.json (xem env/README.md). KHÔNG commit khoá.

Luật cứng:
  * chỉ SELECT / WITH — mọi câu khác bị chặn TRƯỚC khi gửi lên Google
  * một câu một lần (chặn `;` nối câu)
  * maximumBytesBilled mặc định 2 GB → câu quét cả kho sẽ lỗi thay vì đốt tiền
  * maxResults mặc định 200 dòng

Dùng: python3 bq.py --datasets | --tables <dataset> | --schema <ds.table> | --sql "SELECT 1"
"""
import base64
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
SCOPE = "https://www.googleapis.com/auth/bigquery.readonly"
TOKEN_TTL = 3600
_token = {"value": "", "exp": 0.0}


class BQError(RuntimeError):
    pass


def _load_env():
    """Đọc .env của agent (không ghi đè biến môi trường đã có sẵn)."""
    path = os.path.join(AGENT_DIR, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _creds():
    _load_env()
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    key_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not project or not key_path:
        raise BQError("Thiếu GOOGLE_CLOUD_PROJECT hoặc GOOGLE_APPLICATION_CREDENTIALS "
                      "trong .env — xem env/README.md")
    if not os.path.isabs(key_path):
        key_path = os.path.join(AGENT_DIR, key_path)
    if not os.path.exists(key_path):
        raise BQError(f"Không thấy file khoá: {key_path} — đặt JSON vào env/ theo env/README.md")
    with open(key_path, encoding="utf-8") as f:
        sa = json.load(f)
    for k in ("client_email", "private_key"):
        if not sa.get(k):
            raise BQError(f"File khoá thiếu trường {k} — có phải service account JSON không?")
    return project, sa


def _b64(raw: bytes) -> bytes:
    return base64.urlsafe_b64encode(raw).rstrip(b"=")


def _sign_rs256(payload: bytes, private_key_pem: str) -> bytes:
    """Ký RS256 bằng openssl. Khoá đi qua stdin (không ghi ra đĩa); dữ liệu cần ký
    qua file tạm vì openssl không nhận cả hai trên cùng một stdin — dữ liệu này
    là phần header/claims của JWT, không bí mật."""
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf.write(payload)
        data_path = tf.name
    try:
        p = subprocess.run(["openssl", "dgst", "-sha256", "-sign", "/dev/stdin", data_path],
                           input=private_key_pem.encode(), capture_output=True)
        if p.returncode != 0:
            raise BQError("openssl ký JWT lỗi: " + p.stderr.decode()[:300])
        return p.stdout
    finally:
        os.unlink(data_path)


def access_token(force: bool = False) -> str:
    if not force and _token["value"] and time.time() < _token["exp"] - 120:
        return _token["value"]
    _, sa = _creds()
    now = int(time.time())
    header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = _b64(json.dumps({
        "iss": sa["client_email"], "scope": SCOPE,
        "aud": sa.get("token_uri", "https://oauth2.googleapis.com/token"),
        "iat": now, "exp": now + TOKEN_TTL,
    }).encode())
    signing_input = header + b"." + claims
    assertion = signing_input + b"." + _b64(_sign_rs256(signing_input, sa["private_key"]))
    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion.decode(),
    }).encode()
    req = urllib.request.Request(sa.get("token_uri", "https://oauth2.googleapis.com/token"),
                                data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise BQError("Google từ chối cấp token: " + e.read().decode()[:300])
    _token["value"] = data["access_token"]
    _token["exp"] = time.time() + int(data.get("expires_in", TOKEN_TTL))
    return _token["value"]


def _call(path: str, body=None, params=None):
    project, _ = _creds()
    url = f"https://bigquery.googleapis.com/bigquery/v2/projects/{project}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, data=json.dumps(body).encode() if body is not None else None,
        method="POST" if body is not None else "GET",
        headers={"Authorization": "Bearer " + access_token(),
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:600]
        try:
            detail = json.loads(detail)["error"]["message"]
        except Exception:
            pass
        raise BQError(f"BigQuery {e.code}: {detail}")


_FORBID = re.compile(r"\b(insert|update|delete|merge|drop|create|alter|truncate|grant|revoke|"
                     r"call|export|load|begin|commit)\b", re.I)


def check_sql(sql: str) -> str:
    """Chỉ cho SELECT/WITH, một câu. Trả về SQL đã làm sạch, hoặc raise."""
    clean = re.sub(r"--[^\n]*", " ", sql)
    clean = re.sub(r"/\*.*?\*/", " ", clean, flags=re.S).strip().rstrip(";").strip()
    if not clean:
        raise BQError("Câu SQL rỗng")
    if ";" in clean:
        raise BQError("Chỉ chạy MỘT câu SELECT mỗi lần")
    if not re.match(r"^\(*\s*(select|with)\b", clean, re.I):
        raise BQError("Chỉ cho phép SELECT/WITH — Ploy không được ghi vào BigQuery")
    if _FORBID.search(clean):
        raise BQError("Câu lệnh có từ khoá ghi/đổi dữ liệu — bị chặn")
    return clean


def query(sql: str, max_rows: int = None, timeout_ms: int = 60000) -> dict:
    """Chạy SELECT. Trả {'cot': [...], 'dong': [[...]], 'so_dong': n, 'bytes': n}."""
    _load_env()
    clean = check_sql(sql)
    max_rows = int(max_rows or os.environ.get("BQ_MAX_ROWS", 200))
    res = _call("queries", {
        "query": clean, "useLegacySql": False, "maxResults": max_rows,
        "timeoutMs": timeout_ms,
        "maximumBytesBilled": os.environ.get("BQ_MAX_BYTES_BILLED", "2000000000"),
    })
    if not res.get("jobComplete"):
        raise BQError("Truy vấn chưa xong trong thời gian cho phép — thu hẹp câu hỏi lại")
    cols = [f["name"] for f in res.get("schema", {}).get("fields", [])]
    rows = [[c.get("v") for c in r.get("f", [])] for r in res.get("rows", [])]
    return {"cot": cols, "dong": rows, "so_dong": int(res.get("totalRows", len(rows))),
            "bytes": int(res.get("totalBytesProcessed", 0))}


def datasets() -> list:
    out, tok = [], None
    while True:
        res = _call("datasets", params={"maxResults": 200, **({"pageToken": tok} if tok else {})})
        out += [d["datasetReference"]["datasetId"] for d in res.get("datasets", [])]
        tok = res.get("nextPageToken")
        if not tok:
            return sorted(out)


def tables(dataset: str) -> list:
    out, tok = [], None
    while True:
        res = _call(f"datasets/{dataset}/tables",
                    params={"maxResults": 500, **({"pageToken": tok} if tok else {})})
        out += [t["tableReference"]["tableId"] for t in res.get("tables", [])]
        tok = res.get("nextPageToken")
        if not tok:
            return sorted(out)


def schema(dataset: str, table: str) -> list:
    res = _call(f"datasets/{dataset}/tables/{table}")
    return [(f["name"], f.get("type", ""), f.get("description", ""))
            for f in res.get("schema", {}).get("fields", [])]


def as_markdown(res: dict, limit: int = 20) -> str:
    if not res["dong"]:
        return "_không có dòng nào_"
    head = "| " + " | ".join(res["cot"]) + " |"
    sep = "|" + "|".join(["---"] * len(res["cot"])) + "|"
    body = ["| " + " | ".join("" if v is None else str(v) for v in r) + " |"
            for r in res["dong"][:limit]]
    more = f"\n_… {res['so_dong'] - limit} dòng nữa_" if res["so_dong"] > limit else ""
    return "\n".join([head, sep] + body) + more


if __name__ == "__main__":
    import sys
    a = sys.argv[1:]
    try:
        if not a or a[0] == "--datasets":
            print("\n".join(datasets()) or "(không thấy dataset nào)")
        elif a[0] == "--tables":
            print("\n".join(tables(a[1])) or "(dataset rỗng)")
        elif a[0] == "--schema":
            ds, _, tb = a[1].partition(".")
            for n, t, d in schema(ds, tb):
                print(f"{n}\t{t}\t{d}")
        elif a[0] == "--sql":
            r = query(a[1])
            print(as_markdown(r))
            print(f"\n{r['so_dong']} dòng · {r['bytes'] / 1e6:.1f} MB quét")
        else:
            print(__doc__)
    except BQError as e:
        print("LỖI:", e)
        sys.exit(1)
