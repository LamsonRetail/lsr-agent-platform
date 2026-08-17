#!/usr/bin/env python3
"""Sync worker — đồng bộ Lark Wiki/Drive pháp chế → NotebookLM.

⚠️ CHỈ dùng để chạy TAY khi consumer đang DỪNG. Ở chế độ chạy thật, sync là
thread nền trong consumer.py: NotebookLM xoay cookie sau mỗi phiên nên hai tiến
trình dùng song song cùng tài khoản sẽ vô hiệu hoá phiên của nhau
("Authentication expired"). Muốn sync ngay: restart container (sync chạy lúc
khởi động) — xem SETUP.md mục 6.

Chạy một lần:   python3 sync_worker.py --once
Chạy theo lịch: python3 sync_worker.py --loop        (mặc định 3h/lần, SYNC_INTERVAL_H)

Env bắt buộc (xem .env.example / SETUP.md):
  LARK_APP_ID, LARK_APP_SECRET, NLM_NOTEBOOK_KB_ID
Env tuỳ chọn:
  LEGAL_WIKI_SPACE_ID (mặc định space pháp chế), LEGAL_DRIVE_FOLDER (văn bản luật),
  NLM_AUTH_PATH (storage_state.json), LEGALKB_DB, SYNC_INTERVAL_H
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from legalkb.engine import NotebookLMEngine
from legalkb.lark_kb import LarkKB
from legalkb.store import SourceStore
from legalkb.sync import sync_once

DEFAULT_SPACE = "7595876759661186785"          # Wiki pháp chế LSR
DEFAULT_FOLDER = "MIx2fFd8rlzWJBd9bQGlcLQegCd"  # Drive: văn bản luật


def build():
    lark = LarkKB(
        app_id=os.environ["LARK_APP_ID"],
        app_secret=os.environ["LARK_APP_SECRET"],
        base=os.environ.get("LARK_BASE", "https://open.larksuite.com"),
        tenant_domain=os.environ.get("LARK_TENANT_DOMAIN", "o4pvcegwn6b.sg.larksuite.com"))
    store = SourceStore(os.environ.get("LEGALKB_DB"))
    engine = NotebookLMEngine(
        notebook_id=os.environ["NLM_NOTEBOOK_KB_ID"],
        auth_path=os.environ.get("NLM_AUTH_PATH"),
        store=store)
    return lark, engine, store


def run_once():
    lark, engine, store = build()
    report = sync_once(
        lark, engine, store,
        space_id=os.environ.get("LEGAL_WIKI_SPACE_ID", DEFAULT_SPACE),
        drive_folder=os.environ.get("LEGAL_DRIVE_FOLDER", DEFAULT_FOLDER))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--once", action="store_true")
    g.add_argument("--loop", action="store_true")
    args = ap.parse_args()
    if args.once:
        sys.exit(run_once())
    interval = float(os.environ.get("SYNC_INTERVAL_H", "3")) * 3600
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"sync fail: {e}", file=sys.stderr)
        time.sleep(interval)


if __name__ == "__main__":
    main()
