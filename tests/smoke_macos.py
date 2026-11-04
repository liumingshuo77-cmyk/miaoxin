"""Real Cocoa/WebKit smoke test; uses a temporary ledger, never personal data."""

import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]


def child(phase):
    sys.path.insert(0, str(ROOT))
    import webview
    from PyObjCTools import AppHelper
    from AppKit import NSApplication

    app = runpy.run_path(str(ROOT / "秒薪.pyw"))
    start = webview.start
    failures = []

    def exercise():
        window = webview.windows[0]
        try:
            if not window.events.loaded.wait(60):
                raise AssertionError(f"Page did not finish loading: shown={window.events.shown.is_set()}, url={window.real_url}")
            deadline = time.monotonic() + 30
            while not window.evaluate_js("typeof window.miaoxinSnapshot === 'function'"):
                if time.monotonic() > deadline:
                    raise AssertionError("WebKit/bridge boot timed out")
                time.sleep(0.1)
            info = window.evaluate_js("""({
                fatal: document.getElementById('fatal').textContent,
                platform: document.documentElement.dataset.platform,
                closeHidden: getComputedStyle(document.getElementById('winClose')).display,
                salary: window.miaoxinSnapshot().salary,
                clock: document.getElementById('clock').textContent
            })""")
            assert info["fatal"] == "", info
            assert info["platform"] == "darwin", info
            assert info["closeHidden"] == "none", info
            assert info["clock"] != "00:00", info
            if phase == "quit":
                assert info["salary"] == "12345", info
            salary = "12345" if phase == "close" else "23456"
            window.evaluate_js("""
                document.getElementById('openBack').click();
                document.getElementById('salary').value = %s;
                document.getElementById('salary').dispatchEvent(new Event('input'));
            """ % json.dumps(salary))
            # Quit immediately, while the normal 400 ms save is still pending.
            if phase == "close":
                AppHelper.callAfter(window.native.performClose_, None)
            else:
                AppHelper.callAfter(NSApplication.sharedApplication().terminate_, None)
        except Exception:
            failures.append(traceback.format_exc())
            window.destroy()

    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
    webview.start = lambda **kwargs: start(exercise, debug=bool(os.environ.get("CI")), **kwargs)
    app["main"]()
    if failures:
        raise AssertionError("\n".join(failures))


def main():
    if sys.platform != "darwin":
        raise SystemExit("This smoke test needs a macOS desktop session.")
    if len(sys.argv) > 1:
        child(sys.argv[1])
        return
    with tempfile.TemporaryDirectory(prefix="miaoxin-smoke-") as folder:
        env = dict(os.environ, MIAOXIN_DATA_DIR=folder)
        for phase, salary in (("close", "12345"), ("quit", "23456")):
            subprocess.run([sys.executable, __file__, phase], env=env, check=True, timeout=120)
            state = json.loads((Path(folder) / "state.json").read_text(encoding="utf-8"))
            assert state["salary"] == salary, state
            print(f"PASS: {phase}, saved salary {salary}", flush=True)


if __name__ == "__main__":
    main()
