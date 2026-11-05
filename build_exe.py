# -*- coding: utf-8 -*-
"""打成单个 秒薪.exe，拷到本目录。双击即可，不用装 Python。"""

import shutil
from pathlib import Path

import PyInstaller.__main__

HERE = Path(__file__).resolve().parent

PyInstaller.__main__.run([
    "--noconfirm",
    "--clean",
    "--windowed",
    "--onefile",
    "--name", "秒薪",
    "--icon", str(HERE / "icon.ico"),
    "--distpath", str(HERE / "dist"),
    "--workpath", str(HERE / "build"),
    "--specpath", str(HERE / "build"),
    "--add-data", str(HERE / "index.html") + ";.",
    "--add-data", str(HERE / "app.js") + ";.",
    "--add-data", str(HERE / "mini.html") + ";.",
    "--collect-all", "webview",
    "--collect-all", "pythonnet",
    "秒薪.pyw",
])

src = HERE / "dist" / "秒薪.exe"
dst = HERE / "秒薪.exe"
shutil.copy2(src, dst)
print(dst, dst.stat().st_size)
