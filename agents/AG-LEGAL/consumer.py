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

from legalkb import addressing, brain, contracts, flows, gates as gates_mod, news, voice
from legalkb.engine import NotebookLMEngine
from legalkb.flows import Bundle
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
GROUP_CHAT_ID = os.environ.get("LEGAL_GROUP_CHAT_ID", DEFAULT_GROUP)


# ============================ khởi tạo ============================

def make_lark_kb():
    """LarkKB chỉ để đọc/ghi Wiki-Drive (ngoại lệ C1). None khi chưa cấu hình app."""
    if not os.environ.get("LARK_APP_ID"):
        return None
    return LarkKB(app_id=os.environ["LARK_APP_ID"],
                  app_secret=os.environ["LARK_APP_SECRET"],
                  base=os.environ.get("LARK_BASE", "https://open.larksuite.com"),
                  tenant_domain=os.environ.get("LARK_TENANT_DOMAIN",
                                               "o4pvcegwn6b.sg.larksuite.com"))


def build():
    kb = make_lark_kb()
    # Ngoại lệ C9: broker chưa gửi được bằng app của AG-LEGAL → gửi trực tiếp, thà có
    # ngoại lệ có tài liệu hơn để agent im lặng trên kênh người dùng đang dùng.
    pf = Platform(fallback=(kb.im_send_markdown if kb else None))
    if not pf.token:
        sys.exit("thiếu LSR_AGENT_TOKEN — đăng ký agent trước (xem SETUP.md / PLAN §2.2)")
    store = SourceStore(os.environ.get("LEGALKB_DB"))
    engine = NotebookLMEngine(notebook_id=os.environ["NLM_NOTEBOOK_KB_ID"],
                              auth_path=os.environ.get("NLM_AUTH_PATH"), store=store)
    g = Gates(store, pf, GROUP_CHAT_ID,
              sla_hours=float(os.environ.get("GATE_SLA_HOURS", "4")))
    b = Bundle(pf=pf, store=store, engine=engine, gates=g, lark=kb)
    return b


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

def handle_group(job, b):
    """Tin trong group Pháp chế/Admin: chỉ xử lý LỆNH, còn lại im lặng.

    Im lặng là chủ ý: group này người ta còn trao đổi việc khác, agent nhảy vào trả lời
    mọi câu sẽ thành nhiễu — mà đây cũng là group nhận lệnh duyệt, làm ồn là người ta tắt
    thông báo và mất luôn đường phê duyệt.
    """
    g = b.gates
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
        notify_requester(b.pf, gate,
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
        ok = notify_requester(b.pf, gate,
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

    # Biến quyết định thành việc thật: gửi bản thảo, phát hành digest, báo kết quả review.
    extra = None
    try:
        extra = flows.dispatch_decision(b, out, action, arg)
    except Exception as exc:
        print(f"dispatch #{gate_id} lỗi: {exc}", file=sys.stderr, flush=True)
        extra = f"⚠️ Đã ghi nhận quyết định nhưng bước thực thi lỗi: {exc}"
    msg = (f"Đã ghi nhận **{label}** cho `#{gate_id}` bởi "
           f"{who.get('name') or who['email']}." + (f"\nGóp ý: {arg}" if arg else ""))
    return msg + (f"\n\n{extra}" if extra else "")


def notify_requester(pf, gate, text):
    """Gửi tin cho người đã yêu cầu — qua broker platform, theo chat_id của hội thoại."""
    chat_id = (gate.get("payload") or {}).get("chat_id")
    if not chat_id:
        return False
    return pf.lark_send(chat_id, markdown=text)


# ============================ luồng chính ============================

def handle(job, b):
    """Trả về text để reply, hoặc None nếu cố ý không trả lời."""
    pf, store, engine, g = b.pf, b.store, b.engine, b.gates
    payload = job.get("payload") or {}
    q = payload.get("text", "")
    # Khoá phiên theo chat/nhóm — KHÔNG theo job id. Gateway không set session_id nên nếu
    # rơi về job id thì mỗi tin là một phiên mới và agent không nhớ gì (xem addressing.py).
    sid = addressing.session_for(job, payload)
    uref = payload.get("sender_open_id") or payload.get("user_ref") or ""
    chat_id = payload.get("chat_id") or (job.get("reply_to") or {}).get("chat_id")

    # Lệnh duyệt nhận từ MỌI kênh, không chỉ group.
    #
    # Vì sao không khoá theo group: trên VM mỗi app Lark cần một CẶP — service
    # `event_gateway_<app>` để NHẬN tin và tên app trong `LARK_EXTRA_APPS` để GỬI tin.
    # App của AG-LEGAL (đang là bot trong group) chưa có cả hai; app Admin có gửi nhưng
    # không có gateway ⇒ tin nhắn trong group CHƯA tới được agent (chờ core C9).
    # Web chat console thì đã chạy → cho phép duyệt ở đó để không bị chặn hoàn toàn.
    # Quyền vẫn kiểm bằng `sender_open_id` trong `legal_roles`, nên mở kênh không nới quyền.
    in_group = bool(chat_id) and chat_id == GROUP_CHAT_ID
    if in_group or gates_mod.parse_command(q):
        # Trong group mà không phải lệnh → handle_group trả None = im lặng (chủ ý).
        return handle_group(job, b)

    # Nhóm thường: chỉ lên tiếng khi được gọi tên. Nhảy vào mọi câu là cách nhanh nhất
    # để bị đá khỏi nhóm — trong nhóm người ta bàn việc với nhau, không phải hỏi agent.
    ok, why = addressing.should_answer(payload, job, admin_group=GROUP_CHAT_ID)
    if not ok:
        # Vẫn GHI lượt của nhóm vào phiên: nhờ vậy khi có ai gọi tên, agent đã có ngữ cảnh
        # cuộc trao đổi trước đó chứ không hỏi lại từ đầu.
        if q:
            pf.add_turn(sid, "user", q, user_ref=uref, channel=job.get("channel"))
        print(f"↷ job#{job['id']}: không trả lời ({why}) — đã ghi lượt vào {sid}",
              flush=True)
        return None

    # Tin thoại: nghe trước, rồi xử lý như câu hỏi bằng chữ.
    if voice.is_voice(payload):
        heard, err = voice.hear(pf, job, payload,
                               log=lambda m: print(m, file=sys.stderr, flush=True))
        if err:
            pf.add_turn(sid, "user", "(tin nhắn thoại)", user_ref=uref,
                        channel=job.get("channel"))
            return err + "\n\n" + DISCLAIMER
        q = heard
        print(f"[voice] job#{job['id']}: nghe được {len(q)} ký tự", flush=True)

    # Đang có người Pháp chế tham gia → Agent im, nhưng vẫn ghi lượt để không mất lịch sử.
    if g.mode(sid) == "joined":
        pf.add_turn(sid, "user", q, user_ref=uref, channel=job.get("channel"))
        print(f"↷ job#{job['id']}: session {sid} đang do người xử lý — agent im", flush=True)
        return None

    ctx = pf.context(sid, user_ref=uref, q=q)
    # n_turns của platform = số lượt đã ghi. Lấy context TRƯỚC khi ghi lượt này nên
    # 0 nghĩa là đây là lượt đầu của hội thoại → chào + nói rõ việc giám sát.
    first_turn = int(ctx.get("n_turns") or 0) == 0
    b.model = ctx.get("model")
    # Tin thoại CŨNG có file_key, nhưng sau khi nghe xong nó là CÂU HỎI, không phải tài
    # liệu đính kèm — nếu tính là file thì router (`brain.route`) sẽ đẩy sang S3 "rà soát
    # hợp đồng" và trả về lỗi không đọc được định dạng.
    has_file = bool(payload.get("file_key")) and not voice.is_voice(payload)

    # Đang dở luồng tạo hợp đồng thì lượt này thuộc luồng đó — không cho router
    # phân lại, nếu không "Công ty ABC" sẽ bị hiểu thành câu hỏi mới.
    draft = b.drafts.get(sid)
    in_s2 = bool(draft and draft["status"] in ("collecting", "confirming", "revising"))

    if in_s2:
        intent, risk = "s2_create_contract", "medium"
    else:
        r = brain.route(q, ctx, has_attachment=has_file)
        intent, risk = r["intent"], r["risk"]
        pf.event(job["id"], "route", r)

    if intent == "other":
        reply = ("Câu này ngoài phạm vi pháp chế nội bộ mình hỗ trợ. Nếu là việc pháp lý "
                 "cá nhân, bạn liên hệ luật sư ngoài; việc của công ty thì hỏi bộ phận "
                 "Pháp chế.\n\n" + DISCLAIMER)
    elif intent == "s2_create_contract":
        reply = flows.s2_create(b, q, sid, uref, chat_id) + "\n\n" + DISCLAIMER
    elif intent == "s3_review_contract":
        reply = flows.s3_review(b, job, q, sid, uref, chat_id) + "\n\n" + DISCLAIMER
    elif intent == "s5_signing":
        reply = flows.s5_dossier(b, job, q, sid, uref, chat_id) + "\n\n" + DISCLAIMER
    elif intent == "s4_news":
        reply = flows.s4_answer(b, q) + "\n\n" + DISCLAIMER
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
    # S2/S3/S5 đã tự mở gate riêng nên không mở thêm card S1 cho đỡ trùng.
    if intent in ("s1_qa", "s4_news", "other"):
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


def worker(q, b):
    while True:
        job = q.get()
        jid = job["id"]
        # Câu nặng có thể vượt hạn khoá job (120s) → job bị giao lại. Đã trả lời thì bỏ qua.
        if b.store.get_meta(f"replied:{jid}"):
            print(f"↷ job#{jid}: đã trả lời trước đó, bỏ qua", flush=True)
            q.task_done()
            continue
        try:
            b.pf.event(jid, "progress", {"note": "đang tra cứu tài liệu pháp chế"})
            reply = handle(job, b)
            if reply:
                b.pf.reply(jid, reply)
            b.store.set_meta(f"replied:{jid}", "1")
            b.pf.complete(jid, {"ok": True, "replied": bool(reply)})
            print(f"✓ job#{jid}" + ("" if reply else " (cố ý không trả lời)"), flush=True)
        except Exception as exc:
            print(f"✗ job#{jid}: {exc}", file=sys.stderr, flush=True)
            b.pf.fail(jid, exc)
        finally:
            q.task_done()


def sync_loop(b):
    """Đồng bộ KB + registry template định kỳ — CHẠY CHUNG TIẾN TRÌNH với consumer.

    Bắt buộc dùng chung engine: NotebookLM xoay cookie sau mỗi phiên, hai tiến trình
    dùng song song cùng tài khoản sẽ vô hiệu hoá phiên của nhau ("Authentication
    expired"). Một tiến trình = một client = một phiên.
    """
    interval = float(os.environ.get("SYNC_INTERVAL_H", "3")) * 3600
    while True:
        try:
            rep = sync_once(
                b.lark, b.engine, b.store,
                space_id=os.environ.get("LEGAL_WIKI_SPACE_ID", DEFAULT_SPACE),
                drive_folder=os.environ.get("LEGAL_DRIVE_FOLDER", DEFAULT_FOLDER),
                log=lambda m: print(f"[sync] {m}", flush=True))
            print(f"[sync] xong: +{rep['added']} ~{rep['updated']} -{rep['removed']} "
                  f"lỗi={len(rep['errors'])}", flush=True)
        except Exception as exc:
            print(f"[sync] thất bại: {exc}", file=sys.stderr, flush=True)
        try:
            rep = contracts.sync_templates(
                b.lark, b.store, os.environ.get(flows.TEMPLATE_FOLDER_ENV),
                log=lambda m: print(m, flush=True))
            print(f"[template] {rep}", flush=True)
            # Index NỘI DUNG mẫu vào brain (không chỉ tên) — chỉ mẫu nào đổi.
            n = flows.index_templates(b, log=lambda m: print(m, flush=True))
            if n:
                print(f"[index] đã index nội dung {n} mẫu vào brain", flush=True)
        except Exception as exc:
            print(f"[template] thất bại: {exc}", file=sys.stderr, flush=True)
        time.sleep(interval)


def news_loop(b):
    """S4 **hằng tuần, thứ 2 07:00**: crawl nguồn pháp luật (VN, TH, thêm nước sau)
    → lưu bản gốc về Lark Drive theo nước → index vào bộ nhớ → tóm tắt → MỞ GATE.

    Chốt tuần thay vì ngày: văn bản pháp luật không ra theo giờ, quét mỗi ngày chỉ làm ồn
    và tốn quota model. Đổi được qua env mà không sửa code.

    Khoá theo TUẦN (`%G-W%V`) chứ không theo ngày: nếu khoá theo ngày mà container restart
    trong cùng thứ 2 thì chạy lại lần nữa.

    Thread trong cùng tiến trình vì dùng chung phiên NotebookLM (xem sync_loop).
    """
    weekday = int(os.environ.get("NEWS_WEEKDAY", "0"))     # 0 = thứ 2
    hour = int(os.environ.get("NEWS_HOUR", "7"))
    while True:
        now = time.localtime()
        week = time.strftime("%G-W%V")
        due = (now.tm_wday == weekday and now.tm_hour >= hour
               and b.store.get_meta("news_week") != week)
        if due:
            b.store.set_meta("news_week", week)
            print(f"[news] chu kỳ tuần {week} bắt đầu", flush=True)
            try:
                flows.news_cycle(b, GROUP_CHAT_ID, log=lambda m: print(m, flush=True))
            except Exception as exc:
                print(f"[news] chu kỳ lỗi: {exc}", file=sys.stderr, flush=True)
        time.sleep(600)


def gate_loop(b):
    """Nhắc SLA + nạp lại instruction khi có version mới publish."""
    while True:
        try:
            for what, gid in b.gates.sla_tick():
                print(f"[gate] #{gid} → {what}", flush=True)
            apply_instruction(b.pf, b.engine, b.store)
        except Exception as exc:
            print(f"[gate] lỗi: {exc}", file=sys.stderr, flush=True)
        time.sleep(float(os.environ.get("GATE_TICK_MIN", "10")) * 60)


def main():
    b = build()
    apply_instruction(b.pf, b.engine, b.store)
    n = b.gates.sync_roles()
    print(f"legal_roles: đã resolve open_id cho {n} người" if n else
          "legal_roles: không có dòng nào cần resolve")
    if not b.gates.roles():
        print("⚠️  legal_roles TRỐNG — chưa ai duyệt được. Chạy: python3 seed_roles.py",
              file=sys.stderr, flush=True)
    check_group(b.pf)
    if not brain.available():
        print("⚠️  KHÔNG tìm thấy CLI `claude` trong PATH — router sẽ dùng mặc định và "
              "S2–S5 (tạo/rà soát hợp đồng, digest, trình ký) chỉ trả thông báo không rà "
              "soát được. S1 hỏi đáp vẫn chạy. Cách đúng: deploy qua POST /v1/self/deploy "
              "(runner image của platform có sẵn claude), hoặc cài Claude Code vào image.",
              file=sys.stderr, flush=True)
    if not news.sources(b.store):
        print("ℹ️  chưa có nguồn luật nào — chạy: python3 seed_news.py", flush=True)

    if os.environ.get("KB_SYNC", "1") == "1" and b.lark:
        threading.Thread(target=sync_loop, args=(b,), daemon=True, name="kb-sync").start()
        print("kb-sync chạy nền (chung tiến trình)")
    if os.environ.get("NEWS_CRAWL", "1") == "1":
        threading.Thread(target=news_loop, args=(b,), daemon=True, name="news").start()
        print(f"news-crawl chạy nền (hằng tuần, thứ "
              f"{int(os.environ.get('NEWS_WEEKDAY', '0')) + 2}, "
              f"{os.environ.get('NEWS_HOUR', '7')}h)")
    threading.Thread(target=gate_loop, args=(b,), daemon=True, name="gate").start()

    jobs_q = queue.Queue()
    n_workers = int(os.environ.get("CHAT_WORKERS", "3"))
    for i in range(n_workers):
        threading.Thread(target=worker, args=(jobs_q, b), daemon=True,
                         name=f"chat-{i}").start()
    print(f"AG-LEGAL consumer chạy — {n_workers} luồng xử lý, chờ job...")

    while True:      # luồng nhận tin: chỉ poll và xếp hàng, không xử lý
        try:
            for job in b.pf.poll(wait=25, n=5) or []:
                jobs_q.put(job)
        except Exception as exc:
            code = getattr(exc, "status", 0)
            time.sleep(30 if code == 403 else 5)


if __name__ == "__main__":
    main()
