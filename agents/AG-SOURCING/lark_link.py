"""lark_link.py — kiểm tra & xem trạng thái liên kết Lark của agent này.

Chỉ dùng stdlib. Secret đọc từ .env (KHÔNG commit) hoặc biến môi trường:
    LARK_APP_ID, LARK_APP_SECRET, LARK_DOMAIN (mặc định open.larksuite.com)

Dùng:
    python3 lark_link.py                      # verify token + liệt kê nhóm bot đang ở
    python3 lark_link.py --resolve a@b.vn     # email -> open_id
    python3 lark_link.py --send oc_xxx "text" # gửi thử (chặn khi DRY_RUN=true)

Lúc chạy thật, consumer.py KHÔNG cần app_secret: job Lark do platform đẩy về qua
/v1/self/jobs và trả lời qua /v1/self/jobs/{id}/reply (chế độ remote — xem
libs/lsr_lark/README.md). File này chỉ để ops kiểm tra liên kết.
"""
import json, os, sys, urllib.request, urllib.error

DOMAIN = os.environ.get("LARK_DOMAIN", "https://open.larksuite.com").rstrip("/")


def load_env(path=".env"):
    """Nạp .env vào os.environ nếu chưa có (không ghi đè biến môi trường thật)."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), path)) as f:
            for line in f:
                line = line.split("#")[0].strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass


def token():
    app_id, secret = os.environ.get("LARK_APP_ID", ""), os.environ.get("LARK_APP_SECRET", "")
    if not (app_id and secret):
        sys.exit("Thiếu LARK_APP_ID/LARK_APP_SECRET (điền vào .env — xem .env.example)")
    d = call("POST", "/open-apis/auth/v3/tenant_access_token/internal",
             {"app_id": app_id, "app_secret": secret}, auth=None)
    if d.get("code") != 0:
        sys.exit(f"Lark từ chối app credential: {d.get('msg')}")
    return d["tenant_access_token"]


def call(method, path, payload=None, auth=""):
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if auth:
        headers["Authorization"] = f"Bearer {auth}"
    req = urllib.request.Request(DOMAIN + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode() or "{}")


def resolve(email, tok):
    d = call("POST", "/open-apis/contact/v3/users/batch_get_id?user_id_type=open_id",
             {"emails": [email]}, auth=tok)
    for u in ((d.get("data") or {}).get("user_list") or []):
        if u.get("user_id"):
            return u["user_id"]
    return None


def send(to, text, tok, to_type="chat_id"):
    if os.environ.get("DRY_RUN", "true").lower() == "true":
        print(f"[DRY_RUN] sẽ gửi tới {to}: {text}")
        return
    d = call("POST", f"/open-apis/im/v1/messages?receive_id_type={to_type}",
             {"receive_id": to, "msg_type": "text",
              "content": json.dumps({"text": text}, ensure_ascii=False)}, auth=tok)
    print("gửi:", d.get("code"), d.get("msg"))


def main():
    load_env()
    tok = token()
    args = sys.argv[1:]
    if args[:1] == ["--resolve"]:
        print(resolve(args[1], tok) or "(không resolve được)")
        return
    if args[:1] == ["--send"]:
        send(args[1], args[2] if len(args) > 2 else "ping từ agent", tok)
        return

    bot = call("GET", "/open-apis/bot/v3/info", auth=tok).get("bot") or {}
    print(f"✓ app credential hợp lệ — app: {bot.get('app_name')} "
          f"(open_id {bot.get('open_id')}, activate_status {bot.get('activate_status')})")
    chats = call("GET", "/open-apis/im/v1/chats?page_size=50", auth=tok)
    items = (chats.get("data") or {}).get("items") or []
    print(f"Nhóm bot đang tham gia ({len(items)}):")
    for c in items:
        print(f"  {c.get('chat_id')}  {c.get('name')}")
    if not items:
        print("  (chưa có — add bot vào nhóm Lark của dự án rồi chạy lại)")


if __name__ == "__main__":
    main()
