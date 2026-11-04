# -*- coding: utf-8 -*-
"""秒薪桌面入口：Windows / macOS。"""

import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import ctypes
import traceback
from threading import Lock, Thread

import webview

from server import DATA_ROOT, FILE_ROOT, quote_payload, read_state, resolve, write_state

LOG = DATA_ROOT / "秒薪.log"
LOCK = Lock()


class Api:
    def __init__(self):
        self._window = None
        self._closing = False
        self._allow_close = False

    def get_state(self):
        return {"state": read_state(), "platform": sys.platform}

    def save_state(self, state):
        if not isinstance(state, dict):
            return {"ok": False}
        with LOCK:
            if self._closing:
                return {"ok": False}
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

    def _on_closing(self):
        # Cocoa's close/Command-Q callback runs on the UI thread. Veto this
        # attempt, then fetch the final JS state off-thread before closing.
        if self._allow_close or not self._window.events.loaded.is_set():
            return True
        with LOCK:
            if self._closing:
                return False
            self._closing = True
        Thread(target=self._save_and_close, daemon=True).start()
        return False

    def _save_and_close(self):
        try:
            state = self._window.evaluate_js(
                "window.miaoxinSnapshot ? window.miaoxinSnapshot() : null"
            )
            if isinstance(state, dict):
                with LOCK:
                    write_state(state)
        except Exception:
            _log_error()
            with LOCK:
                self._closing = False
            self._window.create_confirmation_dialog(
                "账本保存失败", "请暂时保留窗口，检查账本目录的写入权限和剩余空间后再退出。"
            )
            return
        self._allow_close = True
        self._window.destroy()


def _log_error():
    error = traceback.format_exc()
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        LOG.write_text(error, encoding="utf-8")
    except OSError:
        # A full/unwritable disk must not break the close-error recovery path.
        print(error, file=sys.stderr)


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
    is_mac = sys.platform == "darwin"
    api = Api()
    page = (FILE_ROOT / "index.html").resolve()
    window = webview.create_window(
        "秒薪",
        # A path lets pywebview serve bundled resources on loopback. WKWebView
        # cannot reliably load file:// resources inside a frozen .app.
        url=str(page) if is_mac else page.as_uri(),
        js_api=api,
        width=420,
        height=712,
        min_size=(400, 680),
        background_color="#111110",
        frameless=not is_mac,
        easy_drag=False,
        shadow=True,
        text_select=True,
    )
    api._window = window
    if is_mac:
        window.events.closing += api._on_closing
        webview.start(gui="cocoa")
    elif sys.platform == "win32":
        window.events.shown += lambda: round_corners(window)
        try:
            webview.start(gui="edgechromium")
        except Exception:
            webview.start()
    else:
        webview.start()


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    try:
        main()
    except Exception:
        _log_error()
        raise
