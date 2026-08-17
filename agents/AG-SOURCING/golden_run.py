"""Chạy golden set của AG-SOURCING → tạo regression run để mở eval gate publish PROD.

Vì sao cần: /v1/self/context mà consumer.py gọi mặc định env=prod (app.py:3448), nên
instruction chỉ có tác dụng khi version được publish PROD. Publish PROD đi qua _eval_gate
(app.py:3212): phải có >=1 golden case active + 1 regression run PASS gắn ĐÚNG version đó.

3 bước, 2 loại token:
  1) --upload   POST /v1/golden-cases     — CẦN ADMIN TOKEN
  2) --ask      POST /v1/chat/{id}/messages + SSE stream — chỉ cần AGENT TOKEN
  3) --run      POST /v1/regression/run   — CẦN ADMIN TOKEN

Dùng:
  # 1. nạp case (admin)
  LSR_ADMIN_TOKEN=... python3 golden_run.py --upload
  # 2. hỏi agent 4 câu, lưu câu trả lời ra answers.json (agent token, KHÔNG ghi gì lên platform)
  LSR_AGENT_TOKEN=... python3 golden_run.py --ask --env dev
  # 3. đọc answers.json, chấm, ghi regression run cho version N (admin)
  LSR_ADMIN_TOKEN=... python3 golden_run.py --run --version 3

⚠️ Bước 2 lấy câu trả lời từ consumer.py ĐANG CHẠY. Consumer đọc instruction theo
LSR_ENV (mặc định prod). Muốn kiểm version draft trước khi publish prod thì chạy consumer
với LSR_ENV=dev và publish version đó lên dev trước — nếu không, bạn đang chấm instruction
CŨ rồi gắn kết quả cho version MỚI, tức là eval gate xanh mà không kiểm gì cả.
"""
import argparse, json, os, re, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM = os.environ.get("LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io").rstrip("/")
AGENT_ID = os.environ.get("LSR_AGENT_ID", "AG-SOURCING")
SKILL = AGENT_ID          # namespace golden case theo agent — xem ghi chú CẢNH BÁO ở dưới
CASES_FILE = os.path.join(HERE, "golden-cases.json")
ANSWERS_FILE = os.path.join(HERE, "answers.json")     # gitignored, chỉ để xem lại bằng mắt


def api(method, path, payload=None, token=None, timeout=60):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(PLATFORM + path, data=data, method=method, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = r.read().decode()
            return json.loads(b) if b else {}
    except urllib.error.HTTPError as e:
        sys.exit(f"✗ {method} {path} → {e.code}: {e.read().decode()[:300]}")


def load_cases(only_active=True):
    cases = json.load(open(CASES_FILE, encoding="utf-8"))
    if only_active:
        cases = [c for c in cases if c.get("active", True)]
    return cases


def cmd_upload(args):
    token = os.environ.get("LSR_ADMIN_TOKEN") or sys.exit("thiếu LSR_ADMIN_TOKEN (POST /v1/golden-cases đòi admin)")
    cases = load_cases(only_active=False)
    for c in cases:
        body = {k: v for k, v in c.items() if not k.startswith("_")}
        body.setdefault("skill", SKILL)
        r = api("POST", "/v1/golden-cases", body, token)
        print(f"  {'✓' if r.get('ok') else '✗'} {body['case_id']}  active={body.get('active', True)}")
    print(f"\nĐã nạp {len(cases)} case (skill={SKILL}).")
    print("⚠️ golden_cases là bảng DÙNG CHUNG toàn platform, không có cột agent_id.")
    print("   Luôn truyền skill khi chạy regression, nếu không sẽ chấm lẫn case của agent khác.")


def ask(question, agent_token, timeout=90):
    """Gửi 1 câu qua Chat API rồi đọc SSE tới 'done'. Trả text agent đáp."""
    r = api("POST", f"/v1/chat/{AGENT_ID}/messages", {"text": question}, agent_token)
    sid = r.get("session_id") or sys.exit(f"không lấy được session_id: {r}")
    req = urllib.request.Request(
        f"{PLATFORM}/v1/chat/{AGENT_ID}/stream?session_id={sid}&token={agent_token}")
    texts, kind, deadline = [], "", time.time() + timeout
    with urllib.request.urlopen(req, timeout=timeout + 5) as s:
        while time.time() < deadline:
            line = s.readline().decode().rstrip("\n")
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: "):
                d = json.loads(line[6:] or "{}")
                if kind == "message":
                    texts.append(d.get("text", ""))
                elif kind == "done":
                    break
                elif kind in ("error", "timeout"):
                    return f"(lỗi stream: {d})"
    return " ".join(texts).strip()


def cmd_ask(args):
    token = os.environ.get("LSR_AGENT_TOKEN") or sys.exit("thiếu LSR_AGENT_TOKEN")
    cases = load_cases()
    out = []
    print(f"Hỏi {len(cases)} case active qua Chat API (consumer.py phải đang chạy)…\n")
    for c in cases:
        a = ask(c["prompt"], token)
        ok = re.search(c["expected"], a or "", re.S) is not None if c["atype"] == "regex" \
            else (c["expected"] or "").lower() in (a or "").lower()
        out.append({"case_id": c["case_id"], "response": a})
        print(f"{'✓' if ok else '✗'} {c['case_id']}\n   Q: {c['prompt']}\n   A: {(a or '(rỗng)')[:220]}\n")
    json.dump(out, open(ANSWERS_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    n_ok = sum(1 for c, o in zip(cases, out)
               if re.search(c["expected"], o["response"] or "", re.S))
    print(f"→ {n_ok}/{len(cases)} pass (chấm thử tại local, chưa ghi lên platform)")
    print(f"→ đã lưu {ANSWERS_FILE}. ĐỌC LẠI BẰNG MẮT trước khi --run:")
    print("   regex chỉ chứng minh agent CÓ NÓI câu đúng, không chứng minh nó không bịa thêm.")


def cmd_run(args):
    token = os.environ.get("LSR_ADMIN_TOKEN") or sys.exit("thiếu LSR_ADMIN_TOKEN (POST /v1/regression/run đòi admin)")
    if not args.version:
        sys.exit("thiếu --version N: eval gate chỉ nhận run gắn ĐÚNG version sắp publish (app.py:3220)")
    if not os.path.exists(ANSWERS_FILE):
        sys.exit(f"chưa có {ANSWERS_FILE} — chạy --ask trước")
    answers = json.load(open(ANSWERS_FILE, encoding="utf-8"))
    r = api("POST", "/v1/regression/run", {
        "target_type": "agent", "target_id": AGENT_ID, "skill": SKILL,
        "threshold": args.threshold, "agent_version": args.version, "answers": answers,
    }, token)
    print(json.dumps(r, ensure_ascii=False, indent=2)[:1500])
    print(f"\nscore={r.get('score')} threshold={r.get('threshold')} "
          f"→ {'PASS' if r.get('passed') else 'FAIL'} ({r.get('n_pass')}/{r.get('n_total')})")
    if r.get("passed"):
        print(f"Giờ publish được: POST /v1/agents/{AGENT_ID}/versions/{args.version}/publish "
              '{"env":"prod"}  (admin)')
    else:
        print("Đừng force publish. Sửa instruction rồi tạo version mới, chạy lại từ --ask.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Golden set + regression cho AG-SOURCING")
    p.add_argument("--upload", action="store_true", help="nạp golden-cases.json lên platform (admin)")
    p.add_argument("--ask", action="store_true", help="hỏi agent các case active, lưu answers.json (agent token)")
    p.add_argument("--run", action="store_true", help="chấm answers.json thành regression run (admin)")
    p.add_argument("--version", type=int, help="version agent đang muốn publish")
    p.add_argument("--threshold", type=float, default=0.8, help="mặc định 0.8 — với 4 case đồng weight thì phải pass cả 4 (3/4=0.75 < 0.8)")
    p.add_argument("--env", default="prod", help="chỉ để nhắc: consumer phải chạy cùng LSR_ENV này")
    a = p.parse_args()
    if a.upload:
        cmd_upload(a)
    elif a.ask:
        cmd_ask(a)
    elif a.run:
        cmd_run(a)
    else:
        p.print_help()
