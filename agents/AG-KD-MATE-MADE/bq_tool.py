"""Truy vấn BigQuery cho LYLY — chạy bằng quyền CÁ NHÂN của owner (ADC).

Khác `src/rating_agent/bq/client.py` của core (dùng service account dùng chung): ở đây
xác thực bằng **Application Default Credentials** — owner chạy ``gcloud auth
application-default login`` một lần, mọi truy vấn chạy **dưới danh tính của owner**.

Hệ quả phải nhớ: log BigQuery ghi **owner** là người chạy MỌI truy vấn, kể cả khi câu hỏi
đến từ người khác. Vì vậy quyền dùng BQ bị giới hạn bằng ``KD_BQ_VIEWERS`` ở
``consumer.py`` — nếu không, LYLY trở thành đường vòng qua hệ thống phân quyền của
BigQuery: ai cũng đọc được thứ chỉ owner được đọc.

**Bốn lớp chặn** (vì SQL do model sinh, không phải người viết):

1. **Chỉ SELECT** — mọi câu có DDL/DML bị từ chối trước khi gửi đi.
2. **Allowlist dataset** — chỉ chạm dataset khai trong ``KD_BQ_DATASETS``.
3. **Dry-run trước** — hỏi BigQuery "câu này quét bao nhiêu bytes" mà không tính tiền.
4. **``maximum_bytes_billed``** — cap cứng; vượt thì BigQuery **từ chối chạy**, không tính
   tiền. Đây là lớp cuối, phòng khi ước lượng ở bước 3 sai.

BigQuery tính tiền theo **bytes quét**, không theo số dòng trả về. Một câu ``SELECT *``
trên bảng lớn có thể tốn thật. Ba lớp đầu là để tiết kiệm, lớp thứ tư là để không bao giờ
mất tiền ngoài dự tính.

Tự kiểm:  python3 bq_tool.py --self-test
Thử SQL:  python3 bq_tool.py --sql "SELECT 1"
"""

from __future__ import annotations

import argparse
import os
import re
import sys

# Cap mặc định 1 GB. Đủ cho báo cáo vận hành thường ngày, chặn được truy vấn quét cả kho.
MAX_BYTES = int(os.environ.get("KD_BQ_MAX_BYTES", str(1024 ** 3)))
# Ngưỡng cảnh báo: dưới cap nhưng đủ lớn để nên nói cho người dùng biết trước.
WARN_BYTES = int(os.environ.get("KD_BQ_WARN_BYTES", str(256 * 1024 ** 2)))
MAX_ROWS = int(os.environ.get("KD_BQ_MAX_ROWS", "200"))
PROJECT = os.environ.get("KD_BQ_PROJECT", "")

# Dataset được phép chạm. RỖNG = KHÔNG dataset nào — fail-closed cố ý: quên khai thì BQ
# không chạy, thay vì mở toang cả warehouse.
DATASETS = {d.strip() for d in os.environ.get("KD_BQ_DATASETS", "").split(",") if d.strip()}

# Chỉ cho SELECT/WITH. Chặn cả câu lệnh ghi lẫn lệnh quản trị.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|truncate|merge|grant|revoke|"
    r"replace|call|export|load)\b", re.IGNORECASE)
_STARTS_OK = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
# Bảng được tham chiếu: `project.dataset.table` hoặc `dataset.table`.
_TABLE_REF = re.compile(r"`?([A-Za-z0-9_\-]+)\.([A-Za-z0-9_]+)(?:\.([A-Za-z0-9_]+))?`?")


class BQError(RuntimeError):
    """Lỗi dùng BigQuery — nội dung an toàn để hiện cho người dùng cuối."""


def human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.1f} TB"


# ----------------------------- lớp chặn 1 & 2 (trước khi gửi đi) -----------------------------

def check_sql(sql: str) -> None:
    """Ném ``BQError`` nếu SQL không an toàn. Chạy TRƯỚC khi gửi lên BigQuery."""
    s = (sql or "").strip()
    if not s:
        raise BQError("SQL rỗng")
    if not _STARTS_OK.match(s):
        raise BQError("chỉ chạy được câu SELECT (hoặc WITH ... SELECT)")
    # Bỏ chuỗi literal trước khi soi từ khoá, kẻo tên sản phẩm chứa chữ 'update' bị chặn oan.
    without_str = re.sub(r"'[^']*'|\"[^\"]*\"", "''", s)
    bad = _FORBIDDEN.search(without_str)
    if bad:
        raise BQError(f"câu lệnh '{bad.group(0).upper()}' không được phép — LYLY chỉ đọc")
    if ";" in without_str.rstrip().rstrip(";"):
        raise BQError("không chạy nhiều câu lệnh trong một lần")

    if not DATASETS:
        raise BQError("chưa khai KD_BQ_DATASETS — không dataset nào được phép truy vấn")
    used = {m.group(2) if m.group(3) else m.group(1)
            for m in _TABLE_REF.finditer(without_str)}
    # Bỏ qua alias/hàm bắt nhầm: chỉ xét cái trùng dạng dataset thật.
    outside = {d for d in used if d and d not in DATASETS} & _referenced_datasets(without_str)
    if outside:
        raise BQError(f"dataset ngoài danh sách cho phép: {', '.join(sorted(outside))}")


def _referenced_datasets(sql: str) -> set[str]:
    """Dataset xuất hiện ngay sau FROM/JOIN — nơi tên bảng thật sự nằm."""
    out = set()
    for m in re.finditer(r"\b(?:from|join)\s+`?([A-Za-z0-9_\-.]+)`?", sql, re.IGNORECASE):
        parts = m.group(1).split(".")
        if len(parts) >= 3:
            out.add(parts[1])
        elif len(parts) == 2:
            out.add(parts[0])
    return out


def add_limit(sql: str, limit: int = MAX_ROWS) -> str:
    """Thêm LIMIT nếu chưa có — giữ câu trả lời ở kích thước người đọc nổi."""
    return sql if re.search(r"\blimit\s+\d+", sql, re.IGNORECASE) else \
        f"{sql.rstrip().rstrip(';')}\nLIMIT {limit}"


# ----------------------------- lớp chặn 3 & 4 (BigQuery) -----------------------------

def _client():
    try:
        from google.cloud import bigquery       # noqa: PLC0415 — chỉ cần khi thật sự dùng
    except ImportError as exc:
        raise BQError("chưa cài thư viện: pip install google-cloud-bigquery") from exc
    try:
        return bigquery, (bigquery.Client(project=PROJECT) if PROJECT
                          else bigquery.Client())
    except Exception as exc:                    # noqa: BLE001
        raise BQError(
            "chưa đăng nhập Google Cloud — chạy: gcloud auth application-default login"
        ) from exc


def estimate(sql: str) -> int:
    """Bytes câu này sẽ quét, hỏi bằng dry-run. KHÔNG tính tiền, không chạy thật."""
    bigquery, client = _client()
    cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    try:
        job = client.query(sql, job_config=cfg)
    except Exception as exc:                    # noqa: BLE001
        raise BQError(f"SQL không hợp lệ: {str(exc)[:200]}") from exc
    return int(job.total_bytes_processed or 0)


def run(sql: str, *, max_bytes: int = MAX_BYTES) -> dict:
    """Chạy truy vấn qua đủ bốn lớp chặn.

    Trả ``{rows, columns, bytes, sql, truncated}``. Người gọi **phải** hiện ``sql`` và
    ``bytes`` cho người dùng — với SQL do model sinh, việc nhìn thấy câu đã chạy là cách
    duy nhất phát hiện số đúng-về-kỹ-thuật nhưng sai-về-ý.
    """
    check_sql(sql)                              # lớp 1 + 2
    sql = add_limit(sql)

    est = estimate(sql)                         # lớp 3
    if est > max_bytes:
        raise BQError(
            f"truy vấn này quét {human_bytes(est)}, vượt hạn mức {human_bytes(max_bytes)} "
            "— chưa chạy, chưa tốn tiền. Thu hẹp khoảng ngày hoặc chọn ít cột hơn.")

    bigquery, client = _client()
    cfg = bigquery.QueryJobConfig(maximum_bytes_billed=max_bytes)   # lớp 4
    try:
        job = client.query(sql, job_config=cfg)
        rows = [dict(r) for r in job.result(max_results=MAX_ROWS)]
    except Exception as exc:                    # noqa: BLE001
        raise BQError(f"chạy truy vấn lỗi: {str(exc)[:200]}") from exc

    return {
        "rows": rows,
        "columns": list(rows[0].keys()) if rows else [],
        "bytes": int(job.total_bytes_processed or 0),
        "sql": sql,
        "truncated": len(rows) >= MAX_ROWS,
    }


def format_answer(result: dict) -> str:
    """Dựng câu trả lời — luôn kèm SQL đã chạy và lượng dữ liệu quét."""
    rows, cols = result["rows"], result["columns"]
    if not rows:
        body = "_Truy vấn chạy xong nhưng không có dòng nào khớp._"
    else:
        head = " | ".join(cols)
        sep = "|".join(["---"] * len(cols))
        body = "\n".join([f"| {head} |", f"|{sep}|"] + [
            "| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in rows[:20]])
        if len(rows) > 20:
            body += f"\n_(hiện 20/{len(rows)} dòng)_"
    warn = ("\n> ⚠️ Kết quả bị cắt ở "
            f"{MAX_ROWS} dòng — thu hẹp câu hỏi để thấy đủ." if result["truncated"] else "")
    return (f"{body}{warn}\n\n"
            f"**Câu truy vấn đã chạy** (kiểm giúp em xem có đúng ý không ạ):\n"
            f"```sql\n{result['sql']}\n```\n"
            f"_Quét {human_bytes(result['bytes'])}._")


def enabled() -> bool:
    """BQ có bật không — thiếu cấu hình thì coi như tắt, không phải lỗi."""
    return bool(DATASETS)


# ----------------------------- tự kiểm -----------------------------

def _self_test() -> int:
    ok = True
    print("cấu hình:")
    print(f"  KD_BQ_DATASETS : {', '.join(sorted(DATASETS)) or '(rỗng → BQ TẮT)'}")
    print(f"  KD_BQ_PROJECT  : {PROJECT or '(mặc định của ADC)'}")
    print(f"  cap bytes      : {human_bytes(MAX_BYTES)} (cảnh báo từ {human_bytes(WARN_BYTES)})")
    print()

    print("lớp chặn 1+2 (không cần mạng):")
    for sql, mong_doi in (
        ("SELECT 1", "chặn — chưa khai dataset" if not DATASETS else "cho qua"),
        ("DROP TABLE x", "chặn"),
        ("SELECT * FROM ganesha.AI_DB.orders; DELETE FROM x", "chặn"),
        ("UPDATE t SET a=1", "chặn"),
        ("SELECT name FROM `p.secret_ds.t`", "chặn (dataset ngoài danh sách)"),
    ):
        try:
            check_sql(sql)
            got = "cho qua"
        except BQError as e:
            got = f"chặn ({e})"
        dau = "✓" if got.startswith(mong_doi.split()[0]) else "✗"
        if dau == "✗":
            ok = False
        print(f"  {dau} {sql[:46]!r:50} → {got}")

    print()
    if not DATASETS:
        print("→ BQ đang TẮT (chưa khai KD_BQ_DATASETS). Đây là mặc định an toàn.")
        return 0 if ok else 1

    print("lớp 3+4 (cần đăng nhập Google Cloud):")
    try:
        n = estimate("SELECT 1")
        print(f"  ✓ dry-run chạy được — 'SELECT 1' quét {human_bytes(n)}")
    except BQError as e:
        print(f"  ✗ {e}")
        ok = False
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Công cụ BigQuery của LYLY")
    ap.add_argument("--self-test", action="store_true", dest="self_test",
                    help="kiểm cấu hình và các lớp chặn")
    ap.add_argument("--sql", help="chạy thử một câu SQL")
    ap.add_argument("--estimate", action="store_true",
                    help="chỉ ước lượng bytes, không chạy")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()
    if not args.sql:
        ap.print_help()
        return 1
    try:
        if args.estimate:
            check_sql(args.sql)
            print(f"quét khoảng {human_bytes(estimate(add_limit(args.sql)))}")
        else:
            print(format_answer(run(args.sql)))
    except BQError as e:
        print(f"✗ {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
