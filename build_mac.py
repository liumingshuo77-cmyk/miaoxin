"""在 Mac 上构建可独立运行的 dist/秒薪.app（当前 Python 的架构）。"""

import sys
from pathlib import Path


def main():
    if sys.platform != "darwin":
        raise SystemExit("请在 macOS 上运行 build_mac.py。Windows 请使用 build_exe.py。")

    import PyInstaller.__main__
    from PIL import Image

    here = Path(__file__).resolve().parent
    build = here / "build" / "mac"
    build.mkdir(parents=True, exist_ok=True)
    icon = build / "icon.icns"
    # Reuse the original artwork; no Windows fonts are required to build.
    with Image.open(here / "icon.ico") as source:
        source.convert("RGBA").save(icon)

    PyInstaller.__main__.run([
        "--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", "秒薪",
        "--osx-bundle-identifier", "com.miaoxin.desktop",
        "--icon", str(icon),
        "--distpath", str(here / "dist"),
        "--workpath", str(build),
        "--specpath", str(build),
        "--add-data", str(here / "index.html") + ":.",
        "--add-data", str(here / "app.js") + ":.",
        "--hidden-import", "webview.platforms.cocoa",
        str(here / "秒薪.pyw"),
    ])
    print(here / "dist" / "秒薪.app")


if __name__ == "__main__":
    main()
