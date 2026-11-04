# -*- coding: utf-8 -*-
"""秒薪。双击 秒薪.exe，或双击本文件。"""

import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import traceback
from threading import Lock

import webview

from server import DATA_ROOT, FILE_ROOT, quote_payload, read_state, resolve, write_state

LOG = DATA_ROOT / "秒薪.log"
LOCK = Lock()


class Api:
    def get_state(self):
        return {"state": read_state()}

    def save_state(self, state):
        if not isinstance(state, dict):
            return {"ok": False}
        with LOCK:
            write_state(state)
        return {"ok": True}

    def get_quotes(self, symbols, month):
        return quote_payload({
            "symbols": [symbols or ""],
            "month": [month or ""],
        })

    def search(self, q):
        return {"matches": resolve(q or "")}


def main():
    webview.create_window(
        "秒薪",
        url=(FILE_ROOT / "index.html").as_uri(),
        js_api=Api(),
        width=440,
        height=760,
        min_size=(400, 620),
        background_color="#E9E2D6",
        easy_drag=False,
        text_select=True,
    )
    try:
        webview.start(gui="edgechromium")
    except Exception:
        webview.start()


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    try:
        main()
    except Exception:
        LOG.write_text(traceback.format_exc(), encoding="utf-8")
        raise
