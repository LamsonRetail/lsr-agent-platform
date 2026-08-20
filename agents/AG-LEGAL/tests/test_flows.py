"""Test S2–S5 + hệ quả sau khi Pháp chế quyết định (PLAN Phase 3–6) — offline."""
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("NLM_NOTEBOOK_KB_ID", "nb-test")

import consumer
from legalkb import contracts, flows, news, review as review_mod, signing
from legalkb.engine import EngineAnswer
from legalkb.gates import GATE
from tests.test_consumer import make

GROUP = consumer.GROUP_CHAT_ID


class FakeLarkKB:
    """Drive giả: download trả docx thật (dựng bằng python-docx), upload ghi lại."""

    def __init__(self, template_bytes=b"", files=None):
        self.template_bytes = template_bytes
        self.uploaded = []
        self._files = files or []

    def drive_files(self, folder):
        return self._files

    def drive_download(self, token):
        return self.template_bytes

    def drive_upload(self, folder, name, data):
        self.uploaded.append((folder, name, data))
        return "tok_" + str(len(self.uploaded))

    def drive_file_url(self, token, file_type="file"):
        return f"https://tenant/file/{token}"


def docx_with(text):
    from docx import Document
    d = Document()
    d.add_paragraph(text)
    out = io.BytesIO()
    d.save(out)
    return out.getvalue()


def add_template(store, name="Hợp đồng dịch vụ", fields=None):
    fields = fields or [{"key": "ten_ben_a", "label": "tên bên A", "required": True},
                        {"key": "gia_tri", "label": "giá trị hợp đồng", "required": True}]
    store.write(
        "INSERT INTO contract_templates (key, name, file_token, lark_url, fields, status) "
        "VALUES ('drive:t1',?, 't1','https://tenant/file/t1',?,'active')",
        (name, json.dumps(fields, ensure_ascii=False)))


def add_approver(store):
    store.write("INSERT INTO legal_roles (email, role, contract_type, open_id, name, active)"
                " VALUES ('thint@hapas.vn','approver','*','ou_thint','Thi',1)")


# ==================== S2: điền docx ====================

def test_placeholders_found_even_when_word_splits_them():
    """Word cắt một chuỗi thành nhiều <w:t>; dò theo từng run sẽ bỏ sót placeholder."""
    data = docx_with("Bên A: {{ten_ben_a}}, giá trị {{gia_tri}} đồng")
    assert set(contracts.placeholders_in_docx(data)) == {"ten_ben_a", "gia_tri"}


def test_fill_docx_replaces_and_stamps_draft():
    from docx import Document
    data = docx_with("Bên A: {{ten_ben_a}} — giá trị {{gia_tri}}")
    out = contracts.fill_docx(data, {"ten_ben_a": "Công ty ABC", "gia_tri": "500 triệu"})
    text = "\n".join(p.text for p in Document(io.BytesIO(out)).paragraphs)
    assert "Công ty ABC" in text and "500 triệu" in text
    assert "{{" not in text
    assert contracts.DRAFT_MARK in text          # bản thảo luôn có dấu DRAFT


def test_fill_docx_keeps_unknown_placeholder_visible():
    """Field thiếu thì để nguyên {{...}} — im lặng xoá đi là cách tạo hợp đồng thiếu điều khoản."""
    out = contracts.fill_docx(docx_with("X: {{chua_co}}"), {})
    from docx import Document
    assert "{{chua_co}}" in "\n".join(p.text for p in Document(io.BytesIO(out)).paragraphs)


# ==================== S2: luồng đa lượt ====================

def test_s2_asks_fields_one_by_one_then_confirms(tmp_path):
    store, pf, eng, g, b = make(tmp_path)
    add_template(store)
    out1 = flows.s2_create(b, "tạo hợp đồng dịch vụ", "s1", "ou_u", "oc_u")
    assert "tên bên A" in out1
    out2 = flows.s2_create(b, "Công ty ABC", "s1", "ou_u", "oc_u")
    assert "giá trị hợp đồng" in out2 and "Còn" not in out2.split("\n")[0]
    out3 = flows.s2_create(b, "500 triệu", "s1", "ou_u", "oc_u")
    assert "xác nhận thông tin" in out3 and "Công ty ABC" in out3


def test_s2_state_survives_restart(tmp_path):
    """Bỏ dở rồi quay lại (Bundle mới = tiến trình mới) vẫn hỏi tiếp đúng field."""
    store, pf, eng, g, b = make(tmp_path)
    add_template(store)
    flows.s2_create(b, "tạo hợp đồng dịch vụ", "s-keep", "ou_u", "oc_u")
    flows.s2_create(b, "Công ty ABC", "s-keep", "ou_u", "oc_u")
    b2 = flows.Bundle(pf=pf, store=store, engine=eng, gates=g)   # "restart"
    assert "giá trị hợp đồng" in flows.s2_create(b2, "", "s-keep", "ou_u", "oc_u")


def test_s2_edit_before_confirm(tmp_path):
    store, pf, eng, g, b = make(tmp_path)
    add_template(store)
    for msg in ("tạo hợp đồng dịch vụ", "Công ty ABC", "500 triệu"):
        flows.s2_create(b, msg, "s2", "ou_u", "oc_u")
    out = flows.s2_create(b, "sửa gia_tri: 800 triệu", "s2", "ou_u", "oc_u")
    assert "800 triệu" in out


def test_s2_cancel(tmp_path):
    store, pf, eng, g, b = make(tmp_path)
    add_template(store)
    flows.s2_create(b, "tạo hợp đồng dịch vụ", "s3", "ou_u", "oc_u")
    assert "Đã bỏ" in flows.s2_create(b, "huỷ", "s3", "ou_u", "oc_u")
    assert b.drafts.get("s3") is None


def test_s2_unknown_template_lists_options_without_inventing(tmp_path):
    store, pf, eng, g, b = make(tmp_path)
    add_template(store)
    out = flows.s2_create(b, "tạo hợp đồng thuê máy bay", "s4", "ou_u", "oc_u")
    assert "Hợp đồng dịch vụ" in out
    assert "máy bay" not in out            # không bịa ra mẫu không có


def test_s2_draft_goes_to_gate_not_to_requester(tmp_path, monkeypatch):
    """Review §A.1: bản thảo KHÔNG được gửi thẳng người yêu cầu."""
    lark = FakeLarkKB(docx_with("Bên A: {{ten_ben_a}} — {{gia_tri}}"))
    store, pf, eng, g, b = make(tmp_path, lark=lark)
    add_template(store)
    monkeypatch.setenv(flows.DRAFT_FOLDER_ENV, "fld_draft")
    for msg in ("tạo hợp đồng dịch vụ", "Công ty ABC", "500 triệu", "ok"):
        out = flows.s2_create(b, msg, "s5", "ou_u", "oc_requester")
    assert "chuyển bộ phận Pháp chế kiểm tra" in out
    assert lark.uploaded and lark.uploaded[0][1].startswith("DRAFT-")
    gate = store.one("SELECT * FROM legal_gates WHERE kind='s2_draft'")
    assert gate and gate["level"] == GATE and gate["status"] == "open"
    # người yêu cầu CHƯA nhận link nào
    assert not any(to == "oc_requester" for to, _ in pf.sent)


def test_s2_without_draft_folder_says_so(tmp_path, monkeypatch):
    lark = FakeLarkKB(docx_with("{{ten_ben_a}}"))
    store, pf, eng, g, b = make(tmp_path, lark=lark)
    add_template(store, fields=[{"key": "ten_ben_a", "label": "tên bên A"}])
    monkeypatch.delenv(flows.DRAFT_FOLDER_ENV, raising=False)
    flows.s2_create(b, "tạo hợp đồng dịch vụ", "s6", "ou_u", "oc_u")
    flows.s2_create(b, "ABC", "s6", "ou_u", "oc_u")
    out = flows.s2_create(b, "ok", "s6", "ou_u", "oc_u")
    assert "chưa xuất được file" in out and flows.DRAFT_FOLDER_ENV in out


# ==================== S2: sau khi Pháp chế quyết ====================

def _draft_to_gate(tmp_path, monkeypatch):
    lark = FakeLarkKB(docx_with("Bên A: {{ten_ben_a}} — {{gia_tri}}"))
    store, pf, eng, g, b = make(tmp_path, lark=lark)
    add_template(store)
    add_approver(store)
    monkeypatch.setenv(flows.DRAFT_FOLDER_ENV, "fld_draft")
    for msg in ("tạo hợp đồng dịch vụ", "Công ty ABC", "500 triệu", "ok"):
        flows.s2_create(b, msg, "sess", "ou_u", "oc_requester")
    return store, pf, g, b, store.one("SELECT * FROM legal_gates WHERE kind='s2_draft'")


def test_approved_draft_is_sent_to_requester(tmp_path, monkeypatch):
    store, pf, g, b, gate = _draft_to_gate(tmp_path, monkeypatch)
    pf.sent.clear()
    out = consumer.handle_group(
        {"id": 1, "payload": {"text": f"#{gate['id']} duyệt", "chat_id": GROUP,
                              "sender_open_id": "ou_thint"}}, b)
    assert "DUYỆT" in out
    msg = next(m for to, m in pf.sent if to == "oc_requester")
    assert "qua Pháp chế kiểm tra" in msg and "https://tenant/file/" in msg
    assert b.drafts.get("sess")["status"] == "done"


def test_rejected_draft_tells_requester_the_reason(tmp_path, monkeypatch):
    store, pf, g, b, gate = _draft_to_gate(tmp_path, monkeypatch)
    pf.sent.clear()
    consumer.handle_group(
        {"id": 2, "payload": {"text": f"#{gate['id']} huỷ: sai pháp nhân",
                              "chat_id": GROUP, "sender_open_id": "ou_thint"}}, b)
    msg = next(m for to, m in pf.sent if to == "oc_requester")
    assert "không thông qua" in msg and "sai pháp nhân" in msg
    assert b.drafts.get("sess")["status"] == "cancelled"


def test_changes_request_applies_feedback_and_reopens_gate(tmp_path, monkeypatch):
    store, pf, g, b, gate = _draft_to_gate(tmp_path, monkeypatch)
    monkeypatch.setattr(flows.brain, "call_claude", lambda *a, **k:
                        '{"updates": {"gia_tri": "800 triệu"}, "unresolved": ""}')
    consumer.handle_group(
        {"id": 3, "payload": {"text": f"#{gate['id']} sửa: giá trị phải là 800 triệu",
                              "chat_id": GROUP, "sender_open_id": "ou_thint"}}, b)
    assert b.drafts.get("sess")["values"]["gia_tri"] == "800 triệu"
    gates = store.query("SELECT * FROM legal_gates WHERE kind='s2_draft' ORDER BY id")
    assert len(gates) == 2 and gates[1]["round"] == 2      # gate mới, vòng 2


def test_feedback_that_cannot_map_asks_human_instead_of_guessing(tmp_path, monkeypatch):
    store, pf, g, b, gate = _draft_to_gate(tmp_path, monkeypatch)
    monkeypatch.setattr(flows.brain, "call_claude", lambda *a, **k:
                        '{"updates": {}, "unresolved": "điều khoản bảo mật chưa ổn"}')
    pf.sent.clear()
    out = consumer.handle_group(
        {"id": 4, "payload": {"text": f"#{gate['id']} sửa: điều khoản bảo mật chưa ổn",
                              "chat_id": GROUP, "sender_open_id": "ou_thint"}}, b)
    assert "không đoán" in out
    assert any("sửa <tên_field>" in m for to, m in pf.sent if to == "oc_requester")
    assert len(store.query("SELECT * FROM legal_gates WHERE kind='s2_draft'")) == 1


# ==================== S3: review hợp đồng ====================

def test_s3_asks_for_file_when_none_attached(tmp_path):
    store, pf, eng, g, b = make(tmp_path)
    out = flows.s3_review(b, {"id": 1, "payload": {}}, "nhờ xem hợp đồng", "s", "ou", "oc")
    assert "đính kèm file" in out


def test_s3_reports_findings_and_does_not_close_when_dirty(tmp_path, monkeypatch):
    store, pf, eng, g, b = make(tmp_path,
                                engine_answer=EngineAnswer(ok=True, text="Checklist: A, B"))
    pf.resource = docx_with("Điều 1. Giá trị hợp đồng")
    monkeypatch.setattr(pf, "lark_resource", lambda *a, **k: pf.resource, raising=False)
    monkeypatch.setattr(flows.brain, "call_claude", lambda *a, **k: json.dumps(
        {"findings": [{"severity": "high", "clause": "THIẾU", "issue": "thiếu điều khoản phạt",
                       "suggestion": "bổ sung mức phạt"}], "clean": False, "note": "cần sửa"}))
    job = {"id": 2, "payload": {"file_key": "fk", "file_name": "hd.docx",
                                "message_id": "om_1", "chat_id": "oc_u"}}
    out = flows.s3_review(b, job, "nhờ review", "s3a", "ou_u", "oc_u")
    assert "thiếu điều khoản phạt" in out and "gửi lại file" in out
    r = b.reviews.latest("s3a")
    assert r["status"] == "issues_sent"
    assert not store.query("SELECT * FROM legal_gates WHERE kind='s3_review' AND level='gate'")


def test_s3_clean_contract_goes_to_approver(tmp_path, monkeypatch):
    store, pf, eng, g, b = make(tmp_path,
                                engine_answer=EngineAnswer(ok=True, text="Checklist: A"))
    monkeypatch.setattr(pf, "lark_resource", lambda *a, **k: docx_with("Điều 1"), raising=False)
    monkeypatch.setattr(flows.brain, "call_claude", lambda *a, **k: json.dumps(
        {"findings": [], "clean": True, "note": "ổn"}))
    job = {"id": 3, "payload": {"file_key": "fk", "file_name": "hd.docx",
                                "message_id": "om", "chat_id": "oc_u"}}
    out = flows.s3_review(b, job, "review", "s3b", "ou_u", "oc_u")
    assert "chuyển bộ phận Pháp chế xác nhận" in out
    assert b.reviews.latest("s3b")["status"] == "pending_approval"
    assert store.one("SELECT * FROM legal_gates WHERE kind='s3_review' AND level='gate'")


def test_s3_model_failure_never_declares_contract_clean(tmp_path, monkeypatch):
    """Model lỗi thì KHÔNG được kết luận 'hợp đồng sạch' — điểm an toàn."""
    monkeypatch.setattr(flows.brain, "call_claude", lambda *a, **k: "xin lỗi tôi không thể")
    findings, clean, note = review_mod.analyse(flows.brain, "hợp đồng...", "checklist", "x.pdf")
    assert findings == [] and clean is False
    assert "chưa rà soát được" in note.lower()


def test_s3_report_warns_when_kb_has_no_checklist():
    out = review_mod.render_report([], True, "", "hd.pdf", has_checklist=False)
    assert "chưa có" in out and "nguyên tắc chung" in out


def test_s3_unreadable_file_says_so(tmp_path, monkeypatch):
    store, pf, eng, g, b = make(tmp_path)
    monkeypatch.setattr(pf, "lark_resource", lambda *a, **k: b"khong-phai-docx", raising=False)
    job = {"id": 4, "payload": {"file_key": "fk", "file_name": "anh.png",
                                "message_id": "om", "chat_id": "oc_u"}}
    out = flows.s3_review(b, job, "review", "s3c", "ou_u", "oc_u")
    assert "chưa đọc được file" in out


# ==================== S4: crawl + digest ====================

def test_rss_parsed_and_doc_number_extracted():
    xml = """<rss><channel>
      <item><title>Nghị định 15/2026/NĐ-CP về thương mại điện tử</title>
            <link>https://x.vn/a</link><description>Nội dung</description></item>
      <item><title>Thông tư mới</title><link>https://x.vn/b</link></item>
    </channel></rss>"""
    items = news.parse_rss(xml)
    assert len(items) == 2
    assert news.doc_no_of(items[0]["title"]) == "15/2026/NĐ-CP"
    assert news.doc_no_of(items[1]["title"]) is None


def test_crawl_dedupes_by_doc_number(tmp_path, monkeypatch):
    store, pf, eng, g, b = make(tmp_path)
    store.write("INSERT INTO legal_news_sources (name, url, kind, active) "
                "VALUES ('X','https://x.vn/rss','rss',1)")
    xml = ("<rss><channel><item><title>Nghị định 15/2026/NĐ-CP</title>"
           "<link>https://x.vn/a</link></item></channel></rss>")
    monkeypatch.setattr(news, "fetch", lambda *a, **k: xml)
    assert len(news.crawl(store, log=lambda m: None)) == 1
    assert news.crawl(store, log=lambda m: None) == []      # lần 2 không trùng


def test_one_broken_source_does_not_kill_others(tmp_path, monkeypatch):
    store, pf, eng, g, b = make(tmp_path)
    store.write("INSERT INTO legal_news_sources (name,url,kind,active) "
                "VALUES ('Vỡ','https://bad.vn/rss','rss',1)")
    store.write("INSERT INTO legal_news_sources (name,url,kind,active) "
                "VALUES ('Tốt','https://ok.vn/rss','rss',1)")

    def fetch(url, timeout=30):
        if "bad" in url:
            raise RuntimeError("403 chặn bot")
        return ("<rss><channel><item><title>Nghị định 9/2026/NĐ-CP</title>"
                "<link>https://ok.vn/a</link></item></channel></rss>")

    monkeypatch.setattr(news, "fetch", fetch)
    assert len(news.crawl(store, log=lambda m: None)) == 1
    bad = store.one("SELECT * FROM legal_news_sources WHERE name='Vỡ'")
    assert "403" in bad["last_error"]


def test_item_without_source_link_is_dropped(tmp_path, monkeypatch):
    """Review §B: mục không trích được link nguồn thì loại, không đưa vào digest."""
    store, pf, eng, g, b = make(tmp_path)
    store.write("INSERT INTO legal_news_items (key, url, title, status, found_at) "
                "VALUES ('k1','','Không có link','new',0)")
    monkeypatch.setattr(flows.brain, "call_claude", lambda *a, **k: "{}")
    assert news.summarise(store, flows.brain, ["k1"], log=lambda m: None) == []
    assert store.one("SELECT status FROM legal_news_items WHERE key='k1'")["status"] == "dropped"


def test_digest_opens_gate_and_publishes_nothing_yet(tmp_path, monkeypatch):
    """Review §B: chưa duyệt thì group không nhận digest, notebook không có source mới."""
    store, pf, eng, g, b = make(tmp_path)
    store.write("INSERT INTO legal_news_sources (name,url,kind,active) "
                "VALUES ('X','https://x.vn/rss','rss',1)")
    monkeypatch.setattr(news, "fetch", lambda *a, **k:
                        "<rss><channel><item><title>Nghị định 7/2026/NĐ-CP</title>"
                        "<link>https://x.vn/a</link></item></channel></rss>")
    monkeypatch.setattr(flows.brain, "call_claude", lambda *a, **k: json.dumps(
        {"scope": "TMĐT", "effective": "01/01/2027", "impact": "ảnh hưởng bán online"}))
    gid = flows.news_cycle(b, GROUP, log=lambda m: None)
    gate = b.gates.get(gid)
    assert gate["level"] == GATE and gate["status"] == "open"
    assert store.one("SELECT status FROM legal_news_items WHERE doc_no='7/2026/NĐ-CP'"
                     )["status"] == "in_digest"
    # card thông báo có gửi, nhưng digest thì CHƯA phát hành
    assert not any("Hiệu lực" in (m or "") for _, m in pf.sent)


def test_approved_digest_is_published_and_ingested(tmp_path, monkeypatch):
    store, pf, eng, g, b = make(tmp_path, lark=FakeLarkKB())
    add_approver(store)
    ingested = []
    eng.add_text_source = lambda title, content: ingested.append(title)
    store.write("INSERT INTO legal_news_sources (name,url,kind,active) "
                "VALUES ('X','https://x.vn/rss','rss',1)")
    monkeypatch.setattr(news, "fetch", lambda *a, **k:
                        "<rss><channel><item><title>Nghị định 8/2026/NĐ-CP</title>"
                        "<link>https://x.vn/a</link></item></channel></rss>")
    monkeypatch.setattr(flows.brain, "call_claude", lambda *a, **k: json.dumps(
        {"scope": "s", "effective": "e", "impact": "i"}))
    gid = flows.news_cycle(b, GROUP, log=lambda m: None)
    monkeypatch.setenv("LEGAL_DRIVE_FOLDER", "fld_law")
    pf.sent.clear()
    out = consumer.handle_group({"id": 9, "payload": {"text": f"#{gid} duyệt",
                                                      "chat_id": GROUP,
                                                      "sender_open_id": "ou_thint"}}, b)
    assert "phát hành digest" in out
    assert any("Hiệu lực" in (m or "") for _, m in pf.sent)      # digest đã gửi group
    assert ingested                                              # đã nạp notebook
    assert store.one("SELECT status FROM legal_news_items WHERE doc_no='8/2026/NĐ-CP'"
                     )["status"] == "published"


def test_rejected_digest_publishes_nothing(tmp_path, monkeypatch):
    store, pf, eng, g, b = make(tmp_path)
    add_approver(store)
    store.write("INSERT INTO legal_news_items (key, doc_no, url, title, summary, status, "
                "found_at) VALUES ('k9','9/2026/NĐ-CP','https://x/a','T','{}','in_digest',0)")
    gid = b.gates.open("s4_digest", GATE, payload={"keys": ["k9"], "digest": "d"})
    pf.sent.clear()
    out = consumer.handle_group({"id": 10, "payload": {"text": f"#{gid} huỷ: chưa cần",
                                                       "chat_id": GROUP,
                                                       "sender_open_id": "ou_thint"}}, b)
    assert "không gửi, không nạp KB" in out
    assert store.one("SELECT status FROM legal_news_items WHERE key='k9'")["status"] == "dropped"


# ==================== S5: trình ký ====================

def test_s5_step3_flags_missing_documents(tmp_path, monkeypatch):
    store, pf, eng, g, b = make(tmp_path)
    signing.set_checklist(store, "hợp đồng dịch vụ", ["Giấy ĐKKD", "Báo giá", "Tờ trình"])
    monkeypatch.setattr(flows.brain, "call_claude", lambda *a, **k: json.dumps(
        {"missing_docs": ["Báo giá"], "findings": [], "note": "thiếu 1 mục"}))
    res = signing.step3(flows.brain, store, "nội dung hồ sơ", "hợp đồng dịch vụ")
    out = signing.render_step3(res, "hợp đồng dịch vụ")
    assert res["ok"] and "Báo giá" in out and "Thiếu đầu mục" in out


def test_s5_step3_never_blocks_when_model_fails(tmp_path, monkeypatch):
    """Agent lỗi thì hồ sơ VẪN đi tiếp — máy không được làm nghẽn quy trình người."""
    store, pf, eng, g, b = make(tmp_path)
    monkeypatch.setattr(flows.brain, "call_claude", lambda *a, **k: "lỗi")
    res = signing.step3(flows.brain, store, "hồ sơ", "HĐ")
    assert res["ok"] is False
    assert "chưa rà soát kịp" in signing.render_step3(res)


def test_s5_step5_high_severity_bounces_back_to_step4(monkeypatch):
    monkeypatch.setattr(flows.brain, "call_claude", lambda *a, **k: json.dumps(
        {"findings": [{"severity": "high", "issue": "sai pháp nhân bên B"}], "note": ""}))
    res = signing.step5(flows.brain, "hồ sơ")
    assert res["blocking"] is True
    assert "quay lại Bước 4" in signing.render_step5(res, bounce_count=0)


def test_s5_step5_low_severity_is_advisory_only(monkeypatch):
    monkeypatch.setattr(flows.brain, "call_claude", lambda *a, **k: json.dumps(
        {"findings": [{"severity": "low", "issue": "câu chữ điều 3"}], "note": ""}))
    res = signing.step5(flows.brain, "hồ sơ")
    assert res["blocking"] is False
    out = signing.render_step5(res)
    assert "cảnh báo tham khảo" in out and "quay lại Bước 4" not in out


def test_s5_stops_bouncing_after_max_and_escalates(monkeypatch):
    monkeypatch.setattr(flows.brain, "call_claude", lambda *a, **k: json.dumps(
        {"findings": [{"severity": "high", "issue": "x"}], "note": ""}))
    res = signing.step5(flows.brain, "hồ sơ")
    out = signing.render_step5(res, bounce_count=signing.MAX_BOUNCE)
    assert "không quay lại" in out and "trưởng Pháp chế" in out


def test_s5_observe_gate_auto_passes_on_sla(tmp_path, monkeypatch):
    """Gate của S5 là observe → quá hạn tự thông, không giữ hồ sơ."""
    store, pf, eng, g, b = make(tmp_path)
    monkeypatch.setattr(pf, "lark_resource", lambda *a, **k: docx_with("hồ sơ"), raising=False)
    monkeypatch.setattr(flows.brain, "call_claude", lambda *a, **k: json.dumps(
        {"missing_docs": [], "findings": [], "note": "ok"}))
    job = {"id": 5, "payload": {"file_key": "fk", "file_name": "hs.docx",
                                "message_id": "om", "chat_id": "oc_u"}}
    flows.s5_dossier(b, job, "hồ sơ trình ký bước 3", "s5a", "ou_u", "oc_u")
    gate = store.one("SELECT * FROM legal_gates WHERE kind='s5_step3'")
    assert gate["level"] == "observe"
    store.write("UPDATE legal_gates SET sla_deadline=0 WHERE id=?", (gate["id"],))
    assert ("auto_passed", gate["id"]) in b.gates.sla_tick()


def test_s5_says_it_is_shadow_mode(tmp_path):
    store, pf, eng, g, b = make(tmp_path)
    out = flows.s5_dossier(b, {"id": 6, "payload": {}}, "trình ký", "s", "ou", "oc")
    assert "chạy thử song song" in out and "Lark Approval" in out


# ==================== S5: form thật của Lark Approval ====================

def test_parse_approval_form_maps_real_widget_ids():
    """Widget id đọc live từ workflow "Review và phê duyệt hợp đồng" (19/08/2026)."""
    form = json.dumps([
        {"id": "widget16500094298477484625790733479", "type": "input",
         "name": "Tên hợp đồng", "value": "HĐ dịch vụ ABC"},
        {"id": "widget16500094292359699894458073106", "type": "textarea",
         "name": "Mô tả nội dung cần review và phê duyệt", "value": "Nhờ rà soát điều 5"},
        {"id": "widget17871105849310001", "type": "date",
         "name": "Ngày cần hoàn thành", "value": "2026-09-01"},
    ])
    out = signing.parse_form(form)
    assert out["contract_name"] == "HĐ dịch vụ ABC"
    assert out["description"] == "Nhờ rà soát điều 5"
    assert out["due_date"] == "2026-09-01"
    assert out["attachments"] is None          # không đính kèm → None, không nổ
    assert len(out["raw"]) == 3                # giữ nguyên field lạ để không mất dữ liệu


def test_parse_approval_form_survives_garbage():
    assert signing.parse_form("không phải json") == {}
    assert signing.parse_form(None) == {"raw": [], "contract_name": None,
                                        "description": None, "attachments": None,
                                        "due_date": None}


# ==================== bộ nhớ index ====================

def test_approved_draft_is_indexed_into_brain(tmp_path, monkeypatch):
    """Hợp đồng đã gửi phải vào brain của platform để lượt sau tra lại được qua RAG."""
    store, pf, g, b, gate = _draft_to_gate(tmp_path, monkeypatch)
    items = []
    monkeypatch.setattr(pf, "add_brain_item",
                        lambda title, content, status="approved", source_url=None:
                        items.append((title, content, source_url)), raising=False)
    consumer.handle_group({"id": 30, "payload": {"text": f"#{gate['id']} duyệt",
                                                 "chat_id": GROUP,
                                                 "sender_open_id": "ou_thint"}}, b)
    assert items, "duyệt xong mà không index thì lượt sau không tra lại được"
    title, content, url = items[0]
    assert title.startswith("[Hợp đồng đã gửi]")
    assert "Người duyệt: thint@hapas.vn" in content
    assert url and url.startswith("https://")      # phải có link đối chứng


def test_template_content_indexed_not_just_name(tmp_path, monkeypatch):
    """Index NỘI DUNG mẫu, không chỉ tên — để trả lời được 'mẫu X có điều khoản gì'."""
    lark = FakeLarkKB(docx_with("Điều 1. Phạm vi. Điều 2. Giá trị {{gia_tri}}. " * 4))
    store, pf, eng, g, b = make(tmp_path, lark=lark)
    add_template(store)
    items = []
    monkeypatch.setattr(pf, "add_brain_item",
                        lambda title, content, status="approved", source_url=None:
                        items.append((title, content, source_url)), raising=False)
    assert flows.index_templates(b, log=lambda m: None) == 1
    title, content, url = items[0]
    assert title.startswith("[Mẫu hợp đồng]")
    assert "Điều 1. Phạm vi" in content          # nội dung thật
    assert "ten_ben_a" in content                # kèm danh sách field
    # chạy lần 2: mẫu không đổi → không index lại, khỏi rác brain
    items.clear()
    assert flows.index_templates(b, log=lambda m: None) == 0
    assert items == []


# ==================== S4 hằng tuần: nguồn theo nước + lưu Drive + index ====================

class FakeDrive(FakeLarkKB):
    """Drive giả có ensure_folder — kiểm việc tách folder theo nước."""

    def __init__(self):
        super().__init__(b"")
        self.folders, self.existing = {}, []

    def drive_files(self, folder):
        return self.existing

    def ensure_folder(self, parent, name):
        tok = self.folders.get(name)
        if not tok:
            tok = self.folders[name] = f"fld_{name}"
        return tok


def _add_item(store, key, country, url, doc_no=None, title="Văn bản"):
    store.write("INSERT INTO legal_news_items (key, country, doc_no, title, url, status, "
                "found_at) VALUES (?,?,?,?,?,'new',0)", (key, country, doc_no, title, url))


def test_sources_carry_country_and_dead_ones_start_inactive(tmp_path):
    """Seed phải phản ánh trạng thái ĐÃ KIỂM: nguồn chết để inactive kèm note, không
    để active rồi mỗi tuần báo lỗi mà không ai biết vì sao."""
    store, pf, eng, g, b = make(tmp_path)
    news.seed_sources(store)
    rows = news.sources(store, only_active=False)
    by_cc = {}
    for r in rows:
        by_cc.setdefault(r["country"], []).append(r)
    assert set(by_cc) == {"VN", "TH"}
    active = [r for r in rows if r["active"]]
    assert [r["name"] for r in active] == ["LuatVietnam — văn bản mới"]
    for r in rows:
        if not r["active"]:
            assert r["note"], f"{r['name']} tắt mà không nói vì sao"


def test_seed_does_not_reactivate_source_admin_turned_off(tmp_path):
    store, pf, eng, g, b = make(tmp_path)
    news.seed_sources(store)
    store.write("UPDATE legal_news_sources SET active=0 WHERE name LIKE 'LuatVietnam%'")
    news.seed_sources(store)
    assert not news.sources(store)      # vẫn tắt — seed không bật lại sau lưng admin


def test_html_source_without_pattern_reports_instead_of_silently_empty(tmp_path, monkeypatch):
    store, pf, eng, g, b = make(tmp_path)
    store.write("INSERT INTO legal_news_sources (name,url,kind,country,active) "
                "VALUES ('TH x','https://th.example/law','html','TH',1)")
    monkeypatch.setattr(news, "fetch", lambda *a, **k: "<a href='/law/1'>Thông tư</a>")
    assert news.crawl(store, log=lambda m: None) == []
    err = store.one("SELECT last_error FROM legal_news_sources WHERE name='TH x'")
    assert "link_pattern" in err["last_error"]


def test_html_source_with_pattern_extracts_docs(tmp_path, monkeypatch):
    store, pf, eng, g, b = make(tmp_path)
    store.write("INSERT INTO legal_news_sources (name,url,kind,country,link_pattern,active)"
                " VALUES ('TH gazette','https://th.example/list','html','TH','/law/',1)")
    monkeypatch.setattr(news, "fetch", lambda *a, **k: (
        '<a href="/law/123">ประกาศ 12/2569</a>'
        '<a href="/about">Về chúng tôi</a>'          # không khớp pattern → bỏ
        '<a href="/law/124">ประกาศ 13/2569</a>'))
    keys = news.crawl(store, log=lambda m: None)
    assert len(keys) == 2
    rows = store.query("SELECT * FROM legal_news_items")
    assert all(r["country"] == "TH" for r in rows)
    assert all(r["url"].startswith("https://th.example/law/") for r in rows)


def test_archive_saves_original_into_per_country_folder(tmp_path, monkeypatch):
    """Bản gốc về Drive, tách folder theo nước — không cần ai duyệt vì đó là tài liệu
    nhà nước, không phải nội dung AI sinh ra."""
    store, pf, eng, g, b = make(tmp_path, lark=FakeDrive())
    _add_item(store, "k-vn", "VN", "https://x.vn/nd-15.pdf", "15/2026/NĐ-CP")
    _add_item(store, "k-th", "TH", "https://x.th/notice.pdf", None, "ประกาศ")
    monkeypatch.setattr(news, "fetch_bytes", lambda *a, **k: b"%PDF-1.4 noi dung")
    assert news.archive(store, b.lark, ["k-vn", "k-th"], "fld_root",
                        log=lambda m: None) == 2
    assert set(b.lark.folders) == {"VN", "TH"}
    assert [f for f, _n, _d in b.lark.uploaded] == ["fld_VN", "fld_TH"]
    vn = store.one("SELECT * FROM legal_news_items WHERE key='k-vn'")
    assert vn["drive_url"].startswith("https://tenant/file/") and vn["status"] == "archived"


def test_archive_is_idempotent_and_survives_one_bad_download(tmp_path, monkeypatch):
    store, pf, eng, g, b = make(tmp_path, lark=FakeDrive())
    _add_item(store, "ok", "VN", "https://x.vn/a.pdf")
    _add_item(store, "bad", "VN", "https://x.vn/b.pdf")

    def fetch_bytes(url, timeout=60):
        if "b.pdf" in url:
            raise RuntimeError("404")
        return b"data"

    monkeypatch.setattr(news, "fetch_bytes", fetch_bytes)
    assert news.archive(store, b.lark, ["ok", "bad"], "fld_root", log=lambda m: None) == 1
    # chạy lại: mục đã có drive_url thì không tải/upload lần nữa
    assert news.archive(store, b.lark, ["ok", "bad"], "fld_root", log=lambda m: None) == 0


def test_archive_without_folder_config_is_skipped_not_crash(tmp_path):
    store, pf, eng, g, b = make(tmp_path, lark=FakeDrive())
    _add_item(store, "k", "VN", "https://x.vn/a.pdf")
    assert news.archive(store, b.lark, ["k"], None, log=lambda m: None) == 0


def test_index_points_to_where_to_retrieve(tmp_path):
    """Mục index phải nói rõ: nước, số hiệu, link nguồn gốc VÀ link bản lưu nội bộ."""
    store, pf, eng, g, b = make(tmp_path)
    _add_item(store, "k1", "TH", "https://th.example/law/1", "12/2569", "ประกาศ นาฬิกา")
    store.write("UPDATE legal_news_items SET drive_url='https://tenant/file/tok1' "
                "WHERE key='k1'")
    assert flows.index_legal_docs(b, ["k1"], log=lambda m: None) == 1
    title, content, url = pf.brain_items[0]
    assert "[Văn bản pháp luật · TH]" in title and "12/2569" in title
    assert "Nguồn gốc: https://th.example/law/1" in content
    assert "Lark Drive): https://tenant/file/tok1" in content
    assert url == "https://tenant/file/tok1"


def test_index_says_when_no_internal_copy(tmp_path):
    store, pf, eng, g, b = make(tmp_path)
    _add_item(store, "k2", "VN", "https://x.vn/a")
    flows.index_legal_docs(b, ["k2"], log=lambda m: None)
    _t, content, url = pf.brain_items[0]
    assert "CHƯA có" in content and url == "https://x.vn/a"


def test_index_skips_item_without_source_url(tmp_path):
    store, pf, eng, g, b = make(tmp_path)
    store.write("INSERT INTO legal_news_items (key, country, title, url, status, found_at) "
                "VALUES ('k3','VN','Không link','','new',0)")
    assert flows.index_legal_docs(b, ["k3"], log=lambda m: None) == 0
    assert pf.brain_items == []


def test_weekly_cycle_archives_and_indexes_before_gate(tmp_path, monkeypatch):
    """Lưu + index xảy ra TRƯỚC gate: dữ kiện có ngay, chỉ phần model diễn giải mới chờ duyệt."""
    store, pf, eng, g, b = make(tmp_path, lark=FakeDrive())
    store.write("INSERT INTO legal_news_sources (name,url,kind,country,active) "
                "VALUES ('LVN','https://x.vn/rss','rss','VN',1)")
    monkeypatch.setattr(news, "fetch", lambda *a, **k:
                        "<rss><channel><item><title>Nghị định 21/2026/NĐ-CP</title>"
                        "<link>https://x.vn/nd21.pdf</link></item></channel></rss>")
    monkeypatch.setattr(news, "fetch_bytes", lambda *a, **k: b"pdf")
    monkeypatch.setattr(flows.brain, "call_claude", lambda *a, **k: json.dumps(
        {"scope": "s", "effective": "e", "impact": "i"}))
    monkeypatch.setenv("LEGAL_DRIVE_FOLDER", "fld_root")
    gid = flows.news_cycle(b, GROUP, log=lambda m: None)
    it = store.one("SELECT * FROM legal_news_items WHERE doc_no='21/2026/NĐ-CP'")
    assert it["drive_url"], "phải lưu bản gốc trước khi mở gate"
    assert pf.brain_items, "phải index trước khi mở gate"
    assert b.gates.get(gid)["status"] == "open"      # digest vẫn chờ Pháp chế duyệt
