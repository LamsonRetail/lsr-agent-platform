# A2A — agent gọi agent

Agent của bạn cần một việc **ngoài phạm vi của mình** (tra dữ liệu ngành khác, hỏi legal,
lấy số liệu sourcing) thì đừng tự nhúng vào. Gọi agent đang giữ việc đó.

Không cần biết agent kia chạy ở đâu, dùng model gì, ai host. Platform đứng giữa: đẩy vào
**cùng một hàng đợi job** với Lark/Telegram/web chat, nên bên nhận không phải viết thêm
code gì mới — nó xử lý job A2A y như một tin nhắn.

## Đường vào (mở sẵn, không cần gateway token)

| Method | Path | Việc |
|---|---|---|
| `GET` | `/v1/self/directory` | Danh bạ: ai đang sống, làm được gì, mình được gọi ai |
| `POST` | `/v1/self/a2a/{target_id}` | Gọi một agent, trả về `req_id` ngay (không chờ) |
| `GET` | `/v1/self/a2a/{req_id}` | Lấy kết quả (poll) |

Base URL: `https://platform.34-126-154-135.sslip.io`
Xác thực: **`Authorization: Bearer $LSR_AGENT_TOKEN`** — token của agent bạn, lấy khi
enroll. Không cần `X-Gateway-Token`, không cần đăng nhập console.

> `POST /v1/a2a/grant` là việc của **admin**, nằm sau lớp guard — agent không gọi được.

## Hai điều kiện bắt buộc

1. **Cả hai agent phải `active`.** Agent bạn còn `registered` thì gọi ra 403; target chưa
   active thì 409 và **không** enqueue. Muốn active thì nộp golive checklist
   ([docs/GOLIVE.md](GOLIVE.md)), admin duyệt.
2. **Phải có grant `caller → target`.** Admin cấp. Chưa cấp thì 403 và ghi audit
   `a2a_denied`. Xem `can_call` trong `/v1/self/directory` để biết mình được gọi ai.

Giới hạn chống vòng lặp: **`A2A_MAX_HOP = 3`**. A gọi B, B gọi C là hop 3 — hết. Khi agent
bạn phục vụ một job A2A mà cần gọi tiếp agent khác, **phải chuyển tiếp hop**:
`X-A2A-Hop: <hop trong payload> + 1`. Không chuyển tiếp là mở đường cho A↔B gọi nhau vô tận.

## Gọi (bên caller)

```python
import json, os, time, urllib.request

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io")
TOKEN = os.environ["LSR_AGENT_TOKEN"]


def api(method, path, body=None, headers=None):
    req = urllib.request.Request(
        PLATFORM + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {TOKEN}", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"{}")


def a2a(target, task, payload=None, hop=1, timeout=120):
    """Gọi agent khác và CHỜ kết quả. Trả (text, loi)."""
    r = api("POST", f"/v1/self/a2a/{target}",
            {"task": task, "payload": payload or {}},
            {"X-A2A-Hop": str(hop)})
    req_id = r["req_id"]

    # Poll có giãn dần: đừng đập 1 lần/giây suốt 2 phút.
    delay, waited = 1.0, 0.0
    while waited < timeout:
        time.sleep(delay)
        waited += delay
        delay = min(delay * 1.5, 8.0)
        res = api("GET", f"/v1/self/a2a/{req_id}")
        st = res.get("job_status")
        if st == "done":
            return (res.get("result") or {}).get("text", ""), None
        if st in ("failed", "dlq"):
            return None, res.get("error") or f"job {st}"
    return None, f"quá {timeout}s chưa có kết quả (req_id={req_id})"
```

Dùng:

```python
text, err = a2a("AG-SOURCING", "Giá NCC túi xách mã TB-2201 hiện bao nhiêu?")
if err:
    # Đừng bịa. Nói thẳng là chưa lấy được và vì sao.
    return f"Em chưa lấy được số từ Sourcing ({err}). Anh/chị hỏi trực tiếp team Sourcing giúp em."
```

## Phục vụ (bên target) — thường KHÔNG phải viết gì thêm

Job A2A vào **cùng** hàng đợi với mọi kênh khác, nên consumer sẵn có đã xử lý được:

`GET /v1/self/jobs` trả về **một list job**, không phải object bọc ngoài — lấy sai là
`TypeError: list indices must be integers`.

```python
jobs = api("GET", "/v1/self/jobs?wait=25&max=1")     # -> list[dict]
for j in jobs:
    text = j["payload"]["text"]              # = task bên gọi gửi
    answer = tra_loi(text)
    api("POST", f"/v1/self/jobs/{j['id']}/reply", {"text": answer})
    api("POST", f"/v1/self/jobs/{j['id']}/complete", {})
```

`/reply` tự chọn kênh theo `reply_to` — Lark thì gửi Lark, A2A thì ghi `job_events` cho
bên gọi đọc. **Code agent không cần biết tin đến từ đâu.**

Muốn xử lý riêng cho A2A thì đọc thêm:

```python
if j["channel"] == "a2a":
    caller = j["payload"]["from_agent"]      # agent nào gọi
    hop = j["payload"]["hop"]                # để chuyển tiếp nếu gọi tiếp agent khác
```

## Bảng lỗi

| HTTP | Nghĩa | Làm gì |
|---|---|---|
| 401 | thiếu/sai `LSR_AGENT_TOKEN` | kiểm env, `bash scripts/lsr-login.sh` nếu là token cá nhân |
| 403 `agent của bạn đang 'registered'` | **agent BẠN** chưa active | nộp golive checklist |
| 403 `chưa được cấp quyền gọi` | thiếu grant | xin admin cấp `caller → target` |
| 404 `target không tồn tại` | sai `agent_id` | đối chiếu `/v1/self/directory` |
| 409 `target đang 'registered'` | **agent KIA** chưa active | chờ họ golive, đừng retry vô nghĩa |
| 429 `vượt giới hạn 3 chặng` | chuỗi gọi quá sâu | rút ngắn, hoặc gọi trực tiếp agent cần |
| 429 (Caddy) | quá rate-limit | giãn poll; A2A có zone riêng 600 req/phút/IP |

## Bốn lỗi hay gặp

**Poll 1 lần/giây rồi thắc mắc sao bị 429.** Giãn dần (1s → 1.5s → … → 8s) như code trên.
A2A có zone riêng 600 req/phút **tính theo IP** — nhiều agent sau cùng một IP công ty là
dùng chung hạn mức đó.

**Không chuyển tiếp hop.** Khi phục vụ job A2A mà gọi tiếp agent khác, phải gửi
`X-A2A-Hop: hop + 1`. Bỏ qua là giới hạn chống vòng lặp mất tác dụng.

**Coi lỗi A2A là "không có dữ liệu".** Target chết mà agent bạn trả lời như thể đã tra và
không thấy gì thì đó là **bịa**. Nói rõ chưa gọi được và vì sao.

**Test bằng consumer giả mà lease job của kênh thật.** Đã có sự cố thật: một consumer test
lease job Lark của nhóm Sourcing và trả lời một nội dung bịa vào nhóm. Luật từ đó:
consumer test **chỉ** được chạm job `channel='a2a'` khớp đúng `req_id` của chính nó; job
kênh thật lease nhầm thì `POST /v1/self/jobs/{id}/fail` để trả về hàng đợi, **tuyệt đối
không** reply.

## Xin grant

Không có self-service. Nhắn admin:

> Xin cấp A2A: `AG-CUA-EM` → `AG-SOURCING`. Lý do: cần tra giá NCC để trả lời câu hỏi
> giá bán. Tần suất ước tính: ~20 lượt/ngày.

Admin chạy:

```bash
curl -sS -X POST "$P/v1/a2a/grant" -H "X-Gateway-Token: $G" -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' -d '{"caller_id":"AG-CUA-EM","target_id":"AG-SOURCING"}'
```

Mọi lượt gọi đều vào audit **hai chiều** (`a2a_call` bên gọi, `a2a_serve` bên phục vụ,
khớp `req_id`) — dựng lại được ai gọi ai, lúc nào.
