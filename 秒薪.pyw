# -*- coding: utf-8 -*-
"""秒薪。双击 秒薪.exe，或双击本文件。"""

import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import ctypes
import traceback
from threading import Lock

import webview

from server import DATA_ROOT, FILE_ROOT, quote_payload, read_state, resolve, write_state

LOG = DATA_ROOT / "秒薪.log"
LOCK = Lock()


class Api:
    def __init__(self):
        self._window = None

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

    def minimize(self):
        if self._window:
            self._window.minimize()

    def close(self):
        if self._window:
            self._window.destroy()


def round_corners(window):
    try:
        hwnd = int(str(window.native.Handle))
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(DWMWCP_ROUND), ctypes.sizeof(DWMWCP_ROUND)
        )
    except Exception:
        pass


def main():
    api = Api()
    window = webview.create_window(
        "秒薪",
        url=(FILE_ROOT / "index.html").as_uri(),
        js_api=api,
        width=420,
        height=712,
        min_size=(400, 680),
        background_color="#111110",
        frameless=True,
        easy_drag=False,
        shadow=True,
        text_select=True,
    )
    api._window = window
    window.events.shown += lambda: round_corners(window)
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
