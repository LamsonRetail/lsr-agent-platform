"""Đồng bộ Lark Wiki/Drive → notebook NotebookLM.

Thuật toán mỗi chu kỳ:
1. Inventory: toàn bộ wiki node (đệ quy) + file trong Drive folder văn bản luật.
2. Mỗi tài liệu: mới hoặc edit_ts đổi → tải nội dung → hash đổi thì thay source
   (NotebookLM không sửa tại chỗ text/file → delete + add).
3. Tài liệu trong DB nhưng biến mất khỏi Lark → gỡ source, đánh dấu removed.
Lỗi từng tài liệu không làm chết cả chu kỳ (test case #11).
"""
import hashlib
import os
import tempfile
import time


# obj_type đọc được dạng text qua docx raw_content
TEXT_OBJ_TYPES = {"doc", "docx"}
# đuôi file được upload thẳng làm source (ảnh/bitable ngoài phạm vi KB text)
FILE_EXTS = {".pdf", ".docx", ".doc", ".txt", ".md"}


def _ext_of(name):
    return os.path.splitext(name or "")[1].lower()


def _hash(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


class RemoteDoc:
    """Một tài liệu phía Lark, đủ thông tin để so sánh & tải nội dung."""

    def __init__(self, key, kind, obj_type, title, url, edit_ts, fetch):
        self.key = key
        self.kind = kind
        self.obj_type = obj_type
        self.title = title
        self.url = url
        self.edit_ts = str(edit_ts or "")
        self.fetch = fetch  # () -> ("text", str) | ("file", bytes, ext)


def collect_inventory(lark, space_id, drive_folder, log=None):
    """Liệt kê tài liệu từ wiki space + drive folder thành RemoteDoc list.

    Wiki chứa cả doc/docx (đọc text) lẫn file đính kèm (PDF… tải nhị phân).
    Bitable/sheet/slides và ảnh: ngoài phạm vi KB text — bỏ qua, có log.
    """
    docs = []
    skipped = []
    if space_id:
        for n in lark.wiki_nodes(space_id):
            node_token, obj_token = n["node_token"], n["obj_token"]
            otype = n.get("obj_type")
            title = n.get("title") or node_token
            url = lark.wiki_node_url(node_token)
            if otype in TEXT_OBJ_TYPES:
                docs.append(RemoteDoc(
                    key=f"wiki:{node_token}", kind="wiki", obj_type=otype,
                    title=title, url=url, edit_ts=n.get("obj_edit_time"),
                    fetch=lambda t=obj_token: ("text", lark.docx_raw_content(t))))
            elif otype == "file":
                ext = _ext_of(title) or ".pdf"
                if ext not in FILE_EXTS:
                    skipped.append(f"{title} ({otype}{ext})")
                    continue
                docs.append(RemoteDoc(
                    key=f"wiki:{node_token}", kind="wiki", obj_type="file",
                    title=title, url=url, edit_ts=n.get("obj_edit_time"),
                    fetch=lambda t=obj_token, e=ext: ("file", lark.drive_download(t), e)))
            else:
                skipped.append(f"{title} ({otype})")
    if drive_folder:
        for f in lark.drive_files(drive_folder):
            name = f.get("name") or f["token"]
            ftype = f.get("type", "file")
            if ftype == "folder":
                docs.extend(collect_inventory(lark, None, f["token"], log=log))
                continue
            if ftype in TEXT_OBJ_TYPES:  # cloud doc nằm trong Drive
                tok = f["token"]
                docs.append(RemoteDoc(
                    key=f"drive:{tok}", kind="drive", obj_type=ftype, title=name,
                    url=f.get("url") or lark.drive_file_url(tok, ftype),
                    edit_ts=f.get("modified_time"),
                    fetch=lambda t=tok: ("text", lark.docx_raw_content(t))))
                continue
            ext = _ext_of(name)
            if ext not in FILE_EXTS:
                skipped.append(f"{name} (drive{ext})")
                continue
            tok = f["token"]
            docs.append(RemoteDoc(
                key=f"drive:{tok}", kind="drive", obj_type="file", title=name,
                url=f.get("url") or lark.drive_file_url(tok),
                edit_ts=f.get("modified_time"),
                fetch=lambda t=tok, e=ext: ("file", lark.drive_download(t), e)))
    if skipped and log:
        log(f"bỏ qua {len(skipped)} mục ngoài phạm vi KB text: "
            + "; ".join(skipped[:8]) + ("..." if len(skipped) > 8 else ""))
    return docs


def plan_changes(inventory, store):
    """So inventory với DB → (to_check, to_remove). Pure — test được offline."""
    known = {r["key"]: r for r in store.all_active()}
    to_check = []
    for d in inventory:
        row = known.pop(d.key, None)
        if row is None or row["edit_ts"] != d.edit_ts or row["status"] == "error":
            to_check.append(d)
    return to_check, list(known.values())


def sync_once(lark, engine, store, space_id, drive_folder, log=print):
    report = {"checked": 0, "added": 0, "updated": 0, "removed": 0,
              "unchanged_hash": 0, "errors": []}
    inventory = collect_inventory(lark, space_id, drive_folder, log=log)
    to_check, to_remove = plan_changes(inventory, store)
    log(f"inventory={len(inventory)} thay_doi={len(to_check)} bien_mat={len(to_remove)}")

    for d in to_check:
        report["checked"] += 1
        try:
            content = d.fetch()
            if content[0] == "text":
                body = content[1]
                h = _hash(body)
            else:
                body = content[1]
                h = _hash(body)
            row = store.get(d.key)
            if row and row.get("content_hash") == h and row.get("nlm_source_id"):
                store.upsert(d.key, edit_ts=d.edit_ts, status="synced", error=None)
                report["unchanged_hash"] += 1
                continue
            # thay source: xoá bản cũ (nếu có) rồi thêm bản mới
            if row and row.get("nlm_source_id"):
                engine.delete_source(row["nlm_source_id"])
            if content[0] == "text":
                sid = engine.add_text_source(d.title, body)
            else:
                ext = content[2]
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tf:
                    tf.write(body)
                    tmp = tf.name
                try:
                    sid = engine.add_file_source(d.title, tmp)
                finally:
                    os.unlink(tmp)
            store.upsert(d.key, kind=d.kind, obj_type=d.obj_type, title=d.title,
                         lark_url=d.url, edit_ts=d.edit_ts, content_hash=h,
                         nlm_source_id=sid, notebook_id=engine.notebook_id,
                         status="synced", error=None)
            report["updated" if row else "added"] += 1
            log(f"  ✓ {d.title}")
        except Exception as e:
            store.upsert(d.key, kind=d.kind, obj_type=d.obj_type, title=d.title,
                         lark_url=d.url, status="error", error=str(e)[:400])
            report["errors"].append({"key": d.key, "title": d.title, "error": str(e)[:400]})
            log(f"  ✗ {d.title}: {e}")

    for row in to_remove:
        try:
            if row.get("nlm_source_id"):
                engine.delete_source(row["nlm_source_id"])
            store.mark_removed(row["key"])
            report["removed"] += 1
            log(f"  − {row['title']} (đã gỡ)")
        except Exception as e:
            report["errors"].append({"key": row["key"], "title": row["title"],
                                     "error": str(e)[:400]})

    store.set_meta("last_sync_at", time.strftime("%Y-%m-%d %H:%M:%S"))
    store.set_meta("last_sync_report", str(report))
    return report
