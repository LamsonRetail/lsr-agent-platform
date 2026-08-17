"""Unit test offline cho legalkb — không cần secrets/network.

Chạy: python3 -m pytest agents/AG-LEGAL/tests/ -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from legalkb.engine import AnswerEngine, Citation, EngineAnswer
from legalkb.store import SourceStore
from legalkb.sync import RemoteDoc, plan_changes, sync_once


class FakeEngine(AnswerEngine):
    notebook_id = "nb-test"

    def __init__(self):
        self.sources = {}
        self.n = 0

    def add_text_source(self, title, content):
        self.n += 1
        sid = f"src-{self.n}"
        self.sources[sid] = (title, content)
        return sid

    def add_file_source(self, title, file_path):
        with open(file_path, "rb") as f:
            return self.add_text_source(title, f.read().decode(errors="replace"))

    def delete_source(self, source_id):
        self.sources.pop(source_id, None)

    def list_source_ids(self):
        return list(self.sources)


class FakeLark:
    """Không dùng trong sync_once (inventory truyền tay) — placeholder."""


def doc(key, title, edit_ts, body):
    return RemoteDoc(key=key, kind="wiki", obj_type="docx", title=title,
                     url=f"https://tenant/wiki/{key.split(':')[1]}",
                     edit_ts=edit_ts, fetch=lambda b=body: ("text", b))


def make(tmp_path):
    return SourceStore(str(tmp_path / "t.db")), FakeEngine()


def run_sync(store, engine, inventory, monkeypatch):
    import legalkb.sync as sync_mod
    monkeypatch.setattr(sync_mod, "collect_inventory", lambda *a, **k: inventory)
    return sync_once(FakeLark(), engine, store, "sp", "fl", log=lambda *a: None)


def test_first_sync_adds_all(tmp_path, monkeypatch):
    store, engine = make(tmp_path)
    inv = [doc("wiki:a", "Doc A", "100", "nội dung A"),
           doc("wiki:b", "Doc B", "200", "nội dung B")]
    r = run_sync(store, engine, inv, monkeypatch)
    assert r["added"] == 2 and not r["errors"]
    assert len(engine.sources) == 2
    assert store.get("wiki:a")["status"] == "synced"


def test_edit_replaces_source(tmp_path, monkeypatch):
    store, engine = make(tmp_path)
    run_sync(store, engine, [doc("wiki:a", "Doc A", "100", "v1")], monkeypatch)
    old_sid = store.get("wiki:a")["nlm_source_id"]
    r = run_sync(store, engine, [doc("wiki:a", "Doc A", "150", "v2")], monkeypatch)
    assert r["updated"] == 1
    new_sid = store.get("wiki:a")["nlm_source_id"]
    assert new_sid != old_sid and old_sid not in engine.sources


def test_same_hash_skips_upload(tmp_path, monkeypatch):
    store, engine = make(tmp_path)
    run_sync(store, engine, [doc("wiki:a", "Doc A", "100", "v1")], monkeypatch)
    # edit_ts đổi nhưng nội dung y hệt → không re-upload
    r = run_sync(store, engine, [doc("wiki:a", "Doc A", "150", "v1")], monkeypatch)
    assert r["unchanged_hash"] == 1 and r["updated"] == 0
    assert len(engine.sources) == 1


def test_disappeared_doc_removed(tmp_path, monkeypatch):
    store, engine = make(tmp_path)
    run_sync(store, engine, [doc("wiki:a", "A", "1", "x"),
                             doc("wiki:b", "B", "1", "y")], monkeypatch)
    r = run_sync(store, engine, [doc("wiki:a", "A", "1", "x")], monkeypatch)
    assert r["removed"] == 1
    assert store.get("wiki:b")["status"] == "removed"
    assert len(engine.sources) == 1


def test_one_error_does_not_kill_cycle(tmp_path, monkeypatch):
    store, engine = make(tmp_path)

    def boom():
        raise RuntimeError("download fail")

    bad = RemoteDoc(key="wiki:bad", kind="wiki", obj_type="docx", title="Bad",
                    url="u", edit_ts="1", fetch=boom)
    r = run_sync(store, engine, [bad, doc("wiki:ok", "OK", "1", "z")], monkeypatch)
    assert r["added"] == 1 and len(r["errors"]) == 1
    assert store.get("wiki:bad")["status"] == "error"
    # chu kỳ sau: doc lỗi được thử lại dù edit_ts không đổi
    to_check, _ = plan_changes([bad, doc("wiki:ok", "OK", "1", "z")], store)
    assert [d.key for d in to_check] == ["wiki:bad"]


def test_citation_mapping(tmp_path):
    store = SourceStore(str(tmp_path / "t.db"))
    store.upsert("wiki:a", kind="wiki", obj_type="docx", title="Quy chế X",
                 lark_url="https://tenant/wiki/a", edit_ts="1",
                 nlm_source_id="src-9", status="synced")
    row = store.by_nlm_source("src-9")
    assert row["title"] == "Quy chế X" and row["lark_url"].endswith("/wiki/a")
    assert store.by_nlm_source("src-unknown") is None


def test_store_usable_from_another_thread(tmp_path):
    """Luồng sync và luồng chat dùng chung store — không được vướng SQLite threading."""
    import threading
    store = SourceStore(str(tmp_path / "t.db"))
    err = []

    def work():
        try:
            store.upsert("wiki:x", kind="wiki", title="T", lark_url="u", edit_ts="1",
                         nlm_source_id="s1", status="synced")
            store.set_meta("last_sync_at", "now")
            assert store.by_nlm_source("s1")["title"] == "T"
        except Exception as e:      # sqlite3.ProgrammingError nếu regress
            err.append(e)

    t = threading.Thread(target=work)
    t.start()
    t.join()
    assert not err, err
    assert store.get_meta("last_sync_at") == "now"
