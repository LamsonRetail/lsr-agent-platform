"""Nạp tri thức từ Lark Doc của team Sourcing vào brain RIÊNG của AG-SOURCING.

    python3 brain_seed.py --dry-run     # in ra sẽ nạp gì, không gọi API
    LSR_AGENT_TOKEN=... python3 brain_seed.py            # nạp
    LSR_AGENT_TOKEN=... python3 brain_seed.py --list      # xem brain hiện có
    LSR_AGENT_TOKEN=... python3 brain_seed.py --check     # thử RAG vài câu hỏi thật

Chỉ cần token AGENT, KHÔNG cần admin: `POST /v1/self/brain/items` dùng `_require_self`
(platform_api/app.py:6347) và ép `scope='agent'`, `agent_id=<agent của token>`; item của agent
khác thì trả 403. Nên script này về mặt cấu trúc KHÔNG thể ghi sang brain agent khác.

`item_id` cố định trong brain-seed.json → chạy lại là UPSERT (version+1), không tạo bản trùng.

Nội dung lấy nguyên văn từ doc, chỉ rút gọn câu. KHÔNG tự thêm số liệu/giá/tên NCC —
xem `_nguyen_tac` trong brain-seed.json.
"""
import argparse, json, os, pathlib, sys, urllib.error, urllib.parse, urllib.request

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io").rstrip("/")
HERE = pathlib.Path(__file__).parent
SEED = HERE / "brain-seed.json"

# Câu hỏi thật dùng để kiểm RAG có trả về đúng đoạn — câu đầu chính là golden case #1.
CHECKS = ["Quy trình duyệt báo giá NCC hiện tại ra sao?",
          "Ai duyệt onboard NCC mới?",
          "Đánh giá xưởng chấm theo tiêu chí gì?",
          "Mở ngành hàng mới thì làm thế nào?",
          "Hợp đồng khung có điều khoản gì về đổi giá?"]


def api(method, path, payload=None, token=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(PLATFORM + path, data=data, method=method, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=40) as r:
        b = r.read().decode()
        return json.loads(b) if b else {}


def load_items():
    doc = json.loads(SEED.read_text(encoding="utf-8"))
    out = []
    for it in doc["items"]:
        # bỏ các key tài liệu (_ đứng đầu) — chúng chỉ để người đọc file, không gửi lên API
        out.append({k: v for k, v in it.items() if not k.startswith("_")})
    return out


def need_token():
    t = os.environ.get("LSR_AGENT_TOKEN")
    if not t:
        sys.exit("thiếu LSR_AGENT_TOKEN (xem .env)")
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    if a.list:
        items = api("GET", "/v1/self/brain/items", token=need_token())
        print(f"{len(items)} item trong brain AG-SOURCING:")
        for i in items:
            print(f"  {i['item_id']:28} v{i['version']:<3} {i['status']:9} {i['kind']:10} {i['title']}")
        return

    if a.check:
        token = need_token()
        for q in CHECKS:
            r = api("GET", "/v1/self/brain/search?" + urllib.parse.urlencode({"q": q, "k": 4}),
                    token=token)
            print(f"\nQ: {q}")
            if not r["hits"]:
                print("  (KHÔNG có hit — câu này agent sẽ phải trả lời 'chưa có dữ liệu')")
            for h in r["hits"]:
                print(f"  [{h['scope']:6}] {h['score']:>7} {h['title']}")
                print(f"           nguồn: {h['source_url'] or '(không có)'}")
        return

    items = load_items()
    if a.dry_run:
        print(f"sẽ nạp {len(items)} item (dry-run, không gọi API):\n")
        for i in items:
            print(f"- {i['item_id']} [{i['kind']}/{i['domain']}] {i['title']}")
            print(f"  nguồn : {i['source_url']}")
            print(f"  ref   : {i.get('source_ref')}")
            print(f"  {len(i['content'])} ký tự nội dung\n")
        return

    token = need_token()
    ok = 0
    for i in items:
        try:
            r = api("POST", "/v1/self/brain/items", i, token=token)
            print(f"✓ {r['item_id']:28} scope={r['scope']} agent={r['agent_id']}  {i['title']}")
            ok += 1
        except urllib.error.HTTPError as e:
            print(f"✗ {i['item_id']}: HTTP {e.code} {e.read().decode()[:200]}")
    print(f"\n{ok}/{len(items)} item đã nạp. Kiểm lại: python3 brain_seed.py --check")


if __name__ == "__main__":
    main()
