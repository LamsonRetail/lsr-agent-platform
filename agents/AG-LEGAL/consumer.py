"""AG-LEGAL consumer — trợ lý pháp chế trên LSR Agent Platform.

Chạy: LSR_AGENT_TOKEN=... python3 consumer.py

Ba nguyên tắc bám chuẩn platform (PLAN §2), đừng phá:

1. **Bộ nhớ ở platform, không ở prompt/tiến trình.** Mỗi lượt gọi `/v1/self/context`
   để lấy instruction đang publish + rolling_summary + lượt gần nhất + fact người dùng
   + tri thức RAG, rồi dựng prompt stateless. Restart container vẫn nhớ.
2. **Mọi tương tác Lark qua platform.** Gửi/nhận đều qua `legalkb/platform.py`
   (broker `/v1/lark/*`, `/v1/self/jobs/*`). Agent KHÔNG cầm app_secret, KHÔNG tự gọi
   `im/v1/messages`. Ngoại lệ duy nhất: đọc Wiki/Drive để nạp KB (`legalkb/lark_kb.py`,
   chờ core mở broker — yêu cầu C1).
3. **Hành vi từ instruction_block có version**, không hard-code. Persona của NotebookLM
   cũng nạp từ instruction_block đó, không phải hằng số trong file này.

Pháp chế in the loop (PLAN §4): mọi câu trả lời S1 được báo về group Pháp chế/Admin;
người duyệt quyết định bằng **lệnh nhắn trong group** (`#12 duyệt` …).
"""
import json
import os
import queue
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from legalkb import brain, gates as gates_mod
from legalkb.engine import NotebookLMEngine
from legalkb.gates import GATE, OBSERVE, Gates
from legalkb.lark_kb import LarkKB
from legalkb.platform import Platform
from legalkb.store import SourceStore
from legalkb.sync import sync_once

DEFAULT_SPACE = "7595876759661186785"           # Wiki pháp chế LSR
DEFAULT_FOLDER = "MIx2fFd8rlzWJBd9bQGlcLQegCd"  # Drive: văn bản luật
# Group Pháp chế/Admin: nhận thông báo + gửi lệnh phê duyệt (chốt 17/08/2026).
DEFAULT_GROUP = "oc_2c44821d37e5e12a2c1651251cfd4efb"

DISCLAIMER = "_Tham khảo nội bộ — quyết định cuối thuộc bộ phận Pháp chế._"
WATCHED_NOTE = ("_Nội dung trao đổi được bộ phận Pháp chế giám sát để bảo đảm chất "
                "lượng tư vấn._")
DEGRADE_MSG = ("Hiện không truy cập được kho tài liệu pháp chế, đã ghi nhận sự cố. "
               "Vui lòng thử lại sau hoặc liên hệ trực tiếp bộ phận Pháp chế.\n\n"
               + DISCLAIMER)
# Nghĩa vụ thông báo giám sát — nói ở lượt ĐẦU của mỗi hội thoại, đầy đủ một lần,
# thay vì để người dùng tự suy ra từ dòng footer nhỏ.
GREETING = ("Mình là **Legal Agent** — trợ lý pháp chế nội bộ của LSR.\n"
            "Trước khi bắt đầu: nội dung trao đổi này **được bộ phận Pháp chế giám sát** "
            "để bảo đảm chất lượng tư vấn, và Pháp chế có thể tham gia trực tiếp khi cần.\n\n"
            "---\n")
# S2–S5 chưa mở: nói thật, không giả vờ làm được.
NOT_READY = {
    "s2_create_contract": "soạn hợp đồng từ mẫu",
    "s3_review_contract": "rà soát hợp đồng đối tác",
    "s4_news": "tổng hợp văn bản luật mới",
    "s5_signing": "hỗ trợ hồ sơ trình ký",
}

GROUP_CHAT_ID = os.environ.get("LEGAL_GROUP_CHAT_ID", DEFAULT_GROUP)


# ============================ khởi tạo ============================

def build():
    pf = Platform()
    if not pf.token:
        sys.exit("thiếu LSR_AGENT_TOKEN — đăng ký agent trước (xem SETUP.md / PLAN §2.2)")
    store = SourceStore(os.environ.get("LEGALKB_DB"))
    engine = NotebookLMEngine(notebook_id=os.environ["NLM_NOTEBOOK_KB_ID"],
                              auth_path=os.environ.get("NLM_AUTH_PATH"), store=store)
    g = Gates(store, pf, GROUP_CHAT_ID,
              sla_hours=float(os.environ.get("GATE_SLA_HOURS", "4")))
    return pf, store, engine, g


def apply_instruction(pf, engine, store):
    """Nạp instruction_block (bản đang publish) làm persona cho NotebookLM.

    Trước đây persona là một hằng số ngay trong file này → legal team muốn đổi hành vi
    phải sửa code. Nay lấy từ platform; đổi version thì nạp lại, không deploy lại.
    Không có instruction → CẢNH BÁO to, vì đó cũng là điều kiện golive thật.
    """
    ctx = pf.context(session_id="")
    block, ver = ctx.get("instruction_block"), ctx.get("version")
    if not block:
        print("⚠️  instruction_block đang NULL — agent chưa có policy nào. "
              "Publish INSTRUCTION.md qua console trước khi mở kênh thật.",
              file=sys.stderr, flush=True)
        return None
    if store.get_meta("instruction_version") == str(ver):
        return ver
    try:
        engine.configure_chat(block)
        store.set_meta("instruction_version", str(ver))
        print(f"đã nạp instruction v{ver} vào NotebookLM", flush=True)
    except Exception as exc:
        print(f"configure_chat lỗi (chạy tiếp với persona cũ): {exc}",
              file=sys.stderr, flush=True)
    return ver


def check_group(pf):
    """Xác nhận bot đã ở trong group nhận thông báo — sai group thì im lặng là tệ nhất."""
    if not GROUP_CHAT_ID:
        print("⚠️  chưa cấu hình LEGAL_GROUP_CHAT_ID — Pháp chế sẽ KHÔNG nhận thông báo",
              file=sys.stderr, flush=True)
        return False
    ids = {c.get("chat_id") for c in pf.lark_chats()}
    if ids and GROUP_CHAT_ID not in ids:
        print(f"⚠️  bot chưa ở trong group {GROUP_CHAT_ID} — admin cần add bot vào group "
              f"(thông báo & phê duyệt sẽ không tới)", file=sys.stderr, flush=True)
        return False
    return True


# ============================ S1: hỏi đáp ============================

def format_reply(ans, kb_updated_at=None, watched=True):
    if not ans.ok:
        return DEGRADE_MSG
    parts = [ans.text.strip()]
    cited = [c for c in ans.citations if c.url]
    if cited:
        parts.append("📎 **Nguồn:**\n" + "\n".join(
            f"- [{c.title}]({c.url})" for c in cited))
    footer = DISCLAIMER
    if kb_updated_at:
        footer += f"\n_KB cập nhật lúc {kb_updated_at}._"
    if watched:
        footer += "\n" + WATCHED_NOTE
    parts.append(footer)
    return "\n\n".join(parts)


def answer_s1(question, ctx, session_id, engine, store):
    """Một lượt S1. Ngữ cảnh lấy từ platform, KHÔNG dựa vào phiên chat của engine."""
    conv_key = f"conv:{session_id}"
    ans = engine.ask(brain.kb_question(ctx, question),
                     conversation_id=store.get_meta(conv_key) or None)
    if ans.ok and ans.conversation_id:
        store.set_meta(conv_key, ans.conversation_id)   # tối ưu phụ, không phải bộ nhớ
    if not ans.ok:
        print(f"engine error: {ans.error}", file=sys.stderr, flush=True)
    return ans


def record_turns(pf, session_id, question, reply, uref, channel, model=None):
    """Ghi lượt về platform + nén lượt cũ bằng model (không cắt ngang câu)."""
    pf.add_turn(session_id, "user", question, user_ref=uref, channel=channel)
    r = pf.add_turn(session_id, "assistant", reply) or {}
    if r.get("needs_summary"):
        summary = brain.compress(r.get("dropped_turns") or [], model=model)
        if summary:
            pf.set_summary(session_id, summary)


# ============================ lệnh trong group ============================

def handle_group(job, pf, store, g):
    """Tin trong group Pháp chế/Admin: chỉ xử lý LỆNH, còn lại im lặng.

    Im lặng là chủ ý: group này người ta còn trao đổi việc khác, agent nhảy vào trả lời
    mọi câu sẽ thành nhiễu.
    """
    payload = job.get("payload") or {}
    text = payload.get("text", "")
    sender = payload.get("sender_open_id") or ""
    cmd = gates_mod.parse_command(text)
    if not cmd:
        return None                                   # không phải lệnh → không trả lời

    who = g.reviewer_by_open_id(sender)
    if not who:
        return ("Bạn chưa có quyền quyết định trên AG-LEGAL. "
                "Người được cấp quyền hiện tại do admin cấu hình trong `legal_roles`.")
    gate_id, action, arg = cmd

    if action == "list":
        rows = g.open_list()
        if not rows:
            return "Không có việc nào đang chờ."
        return "**Đang chờ xử lý:**\n" + "\n".join(
            f"- `#{r['id']}` {gates_mod.KIND_LABEL.get(r['kind'], r['kind'])}"
            f" · {r['status']}" for r in rows)

    gate = g.get(gate_id)
    if not gate:
        return f"Không thấy việc `#{gate_id}`. Gõ `#ds` để xem danh sách."

    if action == "join":
        # Cách "thêm người vào thẳng chat" chưa làm được: broker platform chỉ có
        # send/resolve/chats/resource; `_lark_chat_member` của core dùng
        # member_id_type=app_id nên chỉ thêm/gỡ BOT, không thêm người, và không expose
        # cho agent. Đã mở yêu cầu core C6. Vì vậy đường duy nhất hiện nay là RELAY —
        # và relay chạy cho cả chat nhóm lẫn DM 1-1, nên không ai bị kẹt.
        if not gate.get("session_id"):
            return f"`#{gate_id}` không gắn với hội thoại nào nên không tham gia được."
        g.set_mode(gate["session_id"], "joined", taken_by=who["email"],
                   chat_id=(gate.get("payload") or {}).get("chat_id"))
        g.decide(gate_id, "join", who["email"])
        notify_requester(pf, gate,
                         f"👤 **{who.get('name') or who['email']}** (Pháp chế) đã tham gia "
                         f"hỗ trợ trực tiếp cuộc trao đổi này.")
        return (f"Đã ghi nhận: **{who.get('name') or who['email']}** tham gia hội thoại "
                f"của `#{gate_id}`. Agent tạm ngừng tự trả lời. "
                f"Chuyển lời cho người hỏi: `#{gate_id} nhắn: <nội dung>` · "
                f"Xong: `#{gate_id} trả lại`")

    if action == "release":
        if gate.get("session_id"):
            g.set_mode(gate["session_id"], "auto")
        return f"Đã trả hội thoại của `#{gate_id}` lại cho Agent."

    if action == "relay":
        if not arg:
            return f"Thiếu nội dung. Cú pháp: `#{gate_id} nhắn: <nội dung>`"
        ok = notify_requester(pf, gate,
                              f"👤 **Pháp chế ({who.get('name') or who['email']}):** {arg}")
        return "Đã chuyển lời." if ok else "Không chuyển được lời (thiếu chat_id của hội thoại)."

    # approve / changes / reject
    if gate["level"] != GATE:
        return (f"`#{gate_id}` chỉ là thông báo theo dõi, không cần duyệt. "
                f"Muốn vào hỗ trợ: `#{gate_id} tham gia`")
    if action in ("changes", "reject") and not arg:
        kw = "sửa" if action == "changes" else "huỷ"
        return f"Cần nêu lý do: `#{gate_id} {kw}: <nội dung>`"
    out = g.decide(gate_id, action, who["email"], comment=arg)
    if out and out.get("_error"):
        return f"`#{gate_id}`: {out['_error']}."
    label = {"approve": "DUYỆT", "changes": "YÊU CẦU SỬA", "reject": "HUỶ"}[action]
    print(f"gate#{gate_id} → {out['status']} bởi {who['email']}", flush=True)
    return (f"Đã ghi nhận **{label}** cho `#{gate_id}` bởi "
            f"{who.get('name') or who['email']}."
            + (f"\nGóp ý: {arg}" if arg else ""))


def notify_requester(pf, gate, text):
    """Gửi tin cho người đã yêu cầu — qua broker platform, theo chat_id của hội thoại."""
    chat_id = (gate.get("payload") or {}).get("chat_id")
    if not chat_id:
        return False
    return pf.lark_send(chat_id, markdown=text)


# ============================ luồng chính ============================

def handle(job, pf, store, engine, g):
    """Trả về text để reply, hoặc None nếu cố ý không trả lời."""
    payload = job.get("payload") or {}
    q = payload.get("text", "")
    sid = job.get("session_id") or f"job-{job['id']}"
    uref = payload.get("sender_open_id") or payload.get("user_ref") or ""
    chat_id = payload.get("chat_id") or (job.get("reply_to") or {}).get("chat_id")

    if chat_id and chat_id == GROUP_CHAT_ID:
        return handle_group(job, pf, store, g)

    # Đang có người Pháp chế tham gia → Agent im, nhưng vẫn ghi lượt để không mất lịch sử.
    if g.mode(sid) == "joined":
        pf.add_turn(sid, "user", q, user_ref=uref, channel=job.get("channel"))
        print(f"↷ job#{job['id']}: session {sid} đang do người xử lý — agent im", flush=True)
        return None

    ctx = pf.context(sid, user_ref=uref, q=q)
    # n_turns của platform = số lượt đã ghi. Lấy context TRƯỚC khi ghi lượt này nên
    # 0 nghĩa là đây là lượt đầu của hội thoại → chào + nói rõ việc giám sát.
    first_turn = int(ctx.get("n_turns") or 0) == 0
    has_file = bool(payload.get("file_key"))
    r = brain.route(q, ctx, has_attachment=has_file)
    intent, risk = r["intent"], r["risk"]
    pf.event(job["id"], "route", r)

    if intent == "other":
        reply = ("Câu này ngoài phạm vi pháp chế nội bộ mình hỗ trợ. Nếu là việc pháp lý "
                 "cá nhân, bạn liên hệ luật sư ngoài; việc của công ty thì hỏi bộ phận "
                 "Pháp chế.\n\n" + DISCLAIMER)
    elif intent in NOT_READY:
        reply = (f"Việc **{NOT_READY[intent]}** đang được xây, mình chưa nhận được. "
                 f"Mình đã báo bộ phận Pháp chế để có người xử lý cho bạn.\n\n" + DISCLAIMER)
    else:
        ans = answer_s1(q, ctx, sid, engine, store)
        # Lượt đầu đã nói rõ việc giám sát ở câu chào → không nhắc lại ở footer cùng tin.
        reply = format_reply(ans, kb_updated_at=store.get_meta("last_sync_at"),
                             watched=not first_turn)
        risk = "high" if (ans.ok and not any(c.url for c in ans.citations)) else risk

    if first_turn:
        reply = GREETING + reply
    record_turns(pf, sid, q, reply, uref, job.get("channel"), model=ctx.get("model"))

    # N1 Observe: báo Pháp chế MỌI lượt, gom theo hội thoại, không chặn người dùng.
    open_observe(g, sid, chat_id, uref, q, reply, risk, intent, job.get("channel"))
    return reply


def open_observe(g, sid, chat_id, uref, q, reply, risk, intent, channel):
    """Một hội thoại một gate observe; lượt sau chỉ nhắc khi rủi ro tăng lên high."""
    cur = g.store.one(
        "SELECT * FROM legal_gates WHERE session_id=? AND kind='s1_answer' "
        "ORDER BY id DESC LIMIT 1", (sid,))
    if cur and cur["status"] in gates_mod.OPEN_STATUSES:
        if risk == "high" and (cur["risk"] or "low") != "high":
            g.store.write("UPDATE legal_gates SET risk='high' WHERE id=?", (cur["id"],))
            at = g.mentions()
            g.pf.lark_send(g.group, markdown=(
                (at + " " if at else "")
                + f"🔴 **#{cur['id']} — lượt mới có rủi ro cao**\n"
                  f"- **Câu hỏi:** {q[:300]}\nVào hỗ trợ: `#{cur['id']} tham gia`"))
        return cur["id"]
    return g.open("s1_answer", OBSERVE, risk=risk, session_id=sid, channel=channel,
                  requester_ref=uref, title=None,
                  payload={"chat_id": chat_id, "question": q[:500],
                           "summary": reply[:300], "intent": intent})


def worker(q, pf, store, engine, g):
    while True:
        job = q.get()
        jid = job["id"]
        # Câu nặng có thể vượt hạn khoá job (120s) → job bị giao lại. Đã trả lời thì bỏ qua.
        if store.get_meta(f"replied:{jid}"):
            print(f"↷ job#{jid}: đã trả lời trước đó, bỏ qua", flush=True)
            q.task_done()
            continue
        try:
            pf.event(jid, "progress", {"note": "đang tra cứu tài liệu pháp chế"})
            reply = handle(job, pf, store, engine, g)
            if reply:
                pf.reply(jid, reply)
            store.set_meta(f"replied:{jid}", "1")
            pf.complete(jid, {"ok": True, "replied": bool(reply)})
            print(f"✓ job#{jid}" + ("" if reply else " (cố ý không trả lời)"), flush=True)
        except Exception as exc:
            print(f"✗ job#{jid}: {exc}", file=sys.stderr, flush=True)
            pf.fail(jid, exc)
        finally:
            q.task_done()


def sync_loop(engine, store):
    """Đồng bộ KB định kỳ — CHẠY CHUNG TIẾN TRÌNH với consumer.

    Bắt buộc dùng chung engine: NotebookLM xoay cookie sau mỗi phiên, hai tiến trình
    dùng song song cùng tài khoản sẽ vô hiệu hoá phiên của nhau ("Authentication
    expired"). Một tiến trình = một client = một phiên.
    """
    interval = float(os.environ.get("SYNC_INTERVAL_H", "3")) * 3600
    lark = LarkKB(app_id=os.environ["LARK_APP_ID"],
                  app_secret=os.environ["LARK_APP_SECRET"],
                  base=os.environ.get("LARK_BASE", "https://open.larksuite.com"),
                  tenant_domain=os.environ.get("LARK_TENANT_DOMAIN",
                                               "o4pvcegwn6b.sg.larksuite.com"))
    while True:
        try:
            rep = sync_once(
                lark, engine, store,
                space_id=os.environ.get("LEGAL_WIKI_SPACE_ID", DEFAULT_SPACE),
                drive_folder=os.environ.get("LEGAL_DRIVE_FOLDER", DEFAULT_FOLDER),
                log=lambda m: print(f"[sync] {m}", flush=True))
            print(f"[sync] xong: +{rep['added']} ~{rep['updated']} -{rep['removed']} "
                  f"lỗi={len(rep['errors'])}", flush=True)
        except Exception as exc:
            print(f"[sync] thất bại: {exc}", file=sys.stderr, flush=True)
        time.sleep(interval)


def gate_loop(pf, engine, store, g):
    """Nhắc SLA + nạp lại instruction khi có version mới publish."""
    while True:
        try:
            for what, gid in g.sla_tick():
                print(f"[gate] #{gid} → {what}", flush=True)
            apply_instruction(pf, engine, store)
        except Exception as exc:
            print(f"[gate] lỗi: {exc}", file=sys.stderr, flush=True)
        time.sleep(float(os.environ.get("GATE_TICK_MIN", "10")) * 60)


def main():
    pf, store, engine, g = build()
    apply_instruction(pf, engine, store)
    n = g.sync_roles()
    print(f"legal_roles: đã resolve open_id cho {n} người" if n else
          "legal_roles: không có dòng nào cần resolve")
    if not g.roles():
        print("⚠️  legal_roles TRỐNG — chưa ai duyệt được. Chạy: python3 seed_roles.py",
              file=sys.stderr, flush=True)
    check_group(pf)

    if os.environ.get("KB_SYNC", "1") == "1" and os.environ.get("LARK_APP_ID"):
        threading.Thread(target=sync_loop, args=(engine, store), daemon=True,
                         name="kb-sync").start()
        print("kb-sync chạy nền (chung tiến trình)")
    threading.Thread(target=gate_loop, args=(pf, engine, store, g), daemon=True,
                     name="gate").start()

    jobs_q = queue.Queue()
    n_workers = int(os.environ.get("CHAT_WORKERS", "3"))
    for i in range(n_workers):
        threading.Thread(target=worker, args=(jobs_q, pf, store, engine, g), daemon=True,
                         name=f"chat-{i}").start()
    print(f"AG-LEGAL consumer chạy — {n_workers} luồng xử lý, chờ job...")

    while True:      # luồng nhận tin: chỉ poll và xếp hàng, không xử lý
        try:
            for job in pf.poll(wait=25, n=5) or []:
                jobs_q.put(job)
        except Exception as exc:
            code = getattr(exc, "status", 0)
            time.sleep(30 if code == 403 else 5)


if __name__ == "__main__":
    main()
