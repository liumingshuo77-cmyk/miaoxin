"""Desktop utilities; no account, credentials or background updater required."""
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

from app_info import VERSION, release_repo, version_tuple


class SingleInstance:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.handle = None

    def acquire(self):
        if sys.platform != "darwin":
            return True
        import fcntl
        self.folder.mkdir(parents=True, exist_ok=True)
        self.handle = (self.folder / ".instance.lock").open("a+")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.handle.seek(0)
            try:
                from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps
                existing = NSRunningApplication.runningApplicationWithProcessIdentifier_(int(self.handle.read()))
                if existing:
                    existing.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            except (ValueError, ImportError):
                pass
            self.handle.close()
            self.handle = None
            return False
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(str(os.getpid()))
        self.handle.flush()
        return True

    def release(self):
        if self.handle:
            self.handle.close()
            self.handle = None


def check_update(context):
    repo = release_repo()
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    request = urllib.request.Request(url, headers={"User-Agent": f"Miaoxin/{VERSION}", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=8, context=context) as response:
            data = json.load(response)
        if data.get("draft") or data.get("prerelease"):
            return {"ok": True, "message": "目前没有新的正式版本。"}
        latest = version_tuple(data["tag_name"])
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"ok": True, "message": "目前还没有可用的正式发布版本。"}
        return {"ok": False, "message": "暂时无法检查更新，请稍后重试或打开下载页。"}
    except (OSError, ValueError, KeyError):
        return {"ok": False, "message": "暂时无法检查更新，请稍后重试或打开下载页。"}
    newer = latest > version_tuple(VERSION)
    return {"ok": True, "newer": newer, "message": (f"发现新版本 {'.'.join(map(str, latest))}，可在下载页更新。" if newer else f"当前 {VERSION} 已是最新正式版本。")}
