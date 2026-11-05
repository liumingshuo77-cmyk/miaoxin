# -*- coding: utf-8 -*-
"""秒薪。双击 秒薪.exe，或双击本文件。"""

import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import ctypes
import json
import traceback
from threading import Lock, Thread

import webview

from server import DATA_ROOT, FILE_ROOT, quote_payload, read_state, resolve, write_state

LOG = DATA_ROOT / "秒薪.log"
LOCK = Lock()
MINI_W = 292
MINI_H = 76


class Api:
    def __init__(self):
        self._window = None
        self._mini = None
        self._live_text = "¥0.00"
        self._live_mood = ""
        self._mini_placed = False
        self._closing = False

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

    def set_live(self, text, mood=""):
        self._live_text = "¥0.00" if text is None else str(text)
        self._live_mood = "" if mood is None else str(mood)
        mini = self._mini
        if not mini or not mini.events._pywebviewready.is_set():
            return None
        payload = json.dumps({"text": self._live_text, "mood": self._live_mood})
        try:
            mini.evaluate_js("render(" + payload + ")")
        except Exception:
            pass
        return None

    def pull_live(self):
        return {"text": self._live_text, "mood": self._live_mood}

    def _place_mini(self):
        if self._mini_placed or not self._mini or not self._window:
            return
        try:
            x = int(self._window.x + max(0, self._window.width - MINI_W))
            y = int(self._window.y + max(24, self._window.height - MINI_H - 28))
            self._mini.move(x, y)
            self._mini_placed = True
        except Exception:
            pass

    def minimize(self):
        self._place_mini()
        if self._mini:
            self._mini.show()
        if self._window:
            self._window.hide()

    def restore(self):
        if self._mini:
            self._mini.hide()
        if self._window:
            self._window.show()

    def close(self):
        if self._closing:
            return
        self._closing = True
        for win in (self._mini, self._window):
            if not win:
                continue
            try:
                win.destroy()
            except Exception:
                pass


def _destroy(window):
    try:
        window.destroy()
    except Exception:
        pass


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
    mini = webview.create_window(
        "秒薪",
        url=(FILE_ROOT / "mini.html").as_uri(),
        js_api=api,
        width=MINI_W,
        height=MINI_H,
        min_size=(MINI_W, MINI_H),
        background_color="#111110",
        frameless=True,
        easy_drag=False,
        on_top=True,
        resizable=False,
        hidden=True,
        shadow=True,
        text_select=False,
    )
    api._window = window
    api._mini = mini
    window.events.shown += lambda: round_corners(window)
    mini.events.shown += lambda: round_corners(mini)

    def when_closed(other):
        def on_closing():
            if api._closing:
                return
            api._closing = True
            if other is not None:
                Thread(target=_destroy, args=(other,), daemon=True).start()

        return on_closing

    window.events.closing += when_closed(mini)
    mini.events.closing += when_closed(window)
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
