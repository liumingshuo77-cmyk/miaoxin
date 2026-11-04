# -*- coding: utf-8 -*-
"""秒薪桌面入口：Windows / macOS。"""

import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import ctypes
import json
import subprocess
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path
from threading import Lock, Thread

import webview

from server import DATA_ROOT, FILE_ROOT, STATE_PATH, https_context, quote_payload, read_state, resolve, write_state
from app_info import NAME, VERSION, BUILD, release_repo
from desktop_support import SingleInstance, check_update
from ledger import Ledger, MAX_BYTES, atomic_write, decode, validate

LOG = DATA_ROOT / "秒薪.log"
LOCK = Lock()


class Api:
    def __init__(self):
        self._window = None
        self._closing = False
        self._allow_close = False
        self._load_error = None
        self._busy = False
        self._generation = 0

    def get_state(self):
        try:
            state = read_state()
            self._load_error = None
        except (OSError, ValueError) as exc:
            state = None
            self._load_error = str(exc)
        return {"state": state, "platform": sys.platform, "error": self._load_error,
                "version": VERSION, "build": BUILD, "generation": self._generation}

    def save_state(self, state, generation=0):
        if not isinstance(state, dict):
            return {"ok": False}
        with LOCK:
            if self._closing or self._busy or generation != self._generation:
                return {"ok": False, "skipped": True}
            if self._load_error:
                return {"ok": False, "error": "账本读取失败，请先从备份恢复。"}
            try:
                write_state(state)
            except (OSError, ValueError) as exc:
                return {"ok": False, "error": str(exc)}
        return {"ok": True}

    def export_backup(self):
        try:
            if self._load_error:
                return {"ok": False, "message": "当前账本无法读取，请先打开数据目录保留原文件并恢复备份。"}
            target = self._window.create_file_dialog(
                webview.FileDialog.SAVE, save_filename=f"秒薪备份-{datetime.now():%Y%m%d-%H%M%S}.json",
                file_types=("JSON 账本 (*.json)",))
            if not target:
                return {"ok": True, "message": "已取消导出。"}
            target = target[0] if isinstance(target, (tuple, list)) else target
            if Path(target).resolve() == STATE_PATH.resolve():
                return {"ok": False, "message": "请选择其他位置，不能用导出文件覆盖当前账本。"}
            state = self._window.evaluate_js("window.miaoxinSnapshot()")
            with LOCK:
                write_state(state)
            atomic_write(target, validate(dict(state, _schemaVersion=1)))
            return {"ok": True, "message": "备份已导出。请妥善保存，其中包含你的账本数据。"}
        except Exception as exc:
            return {"ok": False, "message": f"导出失败：{exc}"}

    def import_backup(self):
        if self._busy:
            return {"ok": False, "message": "请等待当前操作完成。"}
        try:
            selected = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False,
                                                       file_types=("JSON 账本 (*.json)",))
            if not selected:
                return {"ok": True, "message": "已取消导入。"}
            source = Path(selected[0])
            with source.open("rb") as stream:
                replacement = decode(stream.read(MAX_BYTES + 1))
            if not self._window.create_confirmation_dialog("恢复账本", "将使用所选账本替换当前数据。替换前会自动备份当前文件；确认恢复？"):
                return {"ok": True, "message": "已取消导入。"}
            with LOCK:
                self._busy = True
            if not self._load_error:
                snapshot = self._window.evaluate_js("window.miaoxinSnapshot()")
                write_state(snapshot)
            with LOCK:
                Ledger(STATE_PATH).restore(replacement)
                self._generation += 1
                self._load_error = None
            self._window.evaluate_js(f"window.miaoxinReplaceState({json.dumps(replacement)}, {self._generation})")
            return {"ok": True, "message": "账本已恢复；替换前的文件保存在数据目录的 backups 文件夹。"}
        except Exception as exc:
            return {"ok": False, "message": f"恢复失败：{exc}"}
        finally:
            with LOCK:
                self._busy = False

    def open_data_folder(self):
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(DATA_ROOT)])
        elif sys.platform == "win32":
            os.startfile(DATA_ROOT)
        return {"ok": True, "message": "已打开账本与备份目录。"}

    def check_updates(self):
        return check_update(https_context())

    def open_downloads(self):
        webbrowser.open(f"https://github.com/{release_repo()}/releases/latest")
        return {"ok": True, "message": "已打开 GitHub 下载页。更新前退出秒薪，用新版本替换应用即可，账本会保留。"}

    def open_feedback(self):
        webbrowser.open(f"https://github.com/{release_repo()}/issues")
        return {"ok": True, "message": "已打开问题反馈页。请勿在公开反馈中附上完整账本。"}

    def _show_tools(self):
        self._window.evaluate_js("window.miaoxinShowTools && window.miaoxinShowTools()")

    def _show_settings(self):
        self._window.evaluate_js("document.getElementById('openBack').click()")

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
        if self._allow_close or self._load_error or not self._window.events.loaded.is_set():
            return True
        if self._busy:
            return False
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
    instance = SingleInstance(DATA_ROOT)
    if not instance.acquire():
        return
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
        from webview.menu import Menu, MenuAction
        menu = [Menu("__app__", [MenuAction("设置…", api._show_settings),
                              MenuAction("数据与帮助…", api._show_tools)]),
                Menu("帮助", [MenuAction("数据与帮助…", api._show_tools)])]
        def shortcuts():
            from AppKit import NSApplication
            from PyObjCTools import AppHelper
            def configure():
                main_menu = NSApplication.sharedApplication().mainMenu()
                app_menu = main_menu.itemAtIndex_(0).submenu()
                for item in app_menu.itemArray():
                    if str(item.title()) == "设置…":
                        item.setKeyEquivalent_(",")
                # Standard Cocoa responder action for Command-W.
                view_menu = next((item.submenu() for item in main_menu.itemArray()
                                  if str(item.title()) == "显示"), None)
                if view_menu:
                    view_menu.addItemWithTitle_action_keyEquivalent_("关闭窗口", "performClose:", "w")
            AppHelper.callAfter(configure)
        window.events.shown += shortcuts
        try:
            webview.start(gui="cocoa", menu=menu, localization={
                "global.ok": "确定", "global.cancel": "取消", "global.quit": "退出",
                "cocoa.menu.about": "关于", "cocoa.menu.services": "服务", "cocoa.menu.view": "显示",
                "cocoa.menu.edit": "编辑", "cocoa.menu.hide": "隐藏", "cocoa.menu.hideOthers": "隐藏其他",
                "cocoa.menu.showAll": "全部显示", "cocoa.menu.quit": "退出", "cocoa.menu.fullscreen": "进入全屏",
                "cocoa.menu.cut": "剪切", "cocoa.menu.copy": "复制", "cocoa.menu.paste": "粘贴", "cocoa.menu.selectAll": "全选",
            })
        finally:
            instance.release()
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
