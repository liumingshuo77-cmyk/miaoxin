"""Build a versioned, self-contained Mac app and optional drag-to-install DMG."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from app_info import NAME, VERSION, BUILD, BUNDLE_ID, MIN_MACOS, UPSTREAM


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dmg", action="store_true", help="also build the download/installation disk image")
    parser.add_argument("--release-repo", default=UPSTREAM, help="owner/repo used by update and feedback links")
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise SystemExit("请在 macOS 上运行 build_mac.py。Windows 请使用 build_exe.py。")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.release_repo):
        raise SystemExit("Invalid release repository")
    import PyInstaller.__main__
    from PIL import Image

    here = Path(__file__).resolve().parent
    build = here / "build" / "mac"
    build.mkdir(parents=True, exist_ok=True)
    icon = build / "icon.icns"
    with Image.open(here / "icon.ico") as source:
        source.convert("RGBA").save(icon)
    config = build / "release-config.json"
    config.write_text(json.dumps({"repository": args.release_repo}), encoding="utf-8")
    licenses = build / "ThirdPartyLicenses"
    licenses.mkdir(exist_ok=True)
    for package in ("pywebview", "bottle", "proxy_tools", "certifi", "pyobjc-core", "pyobjc-framework-Cocoa",
                    "pyobjc-framework-WebKit", "pyobjc-framework-Quartz", "pyobjc-framework-security", "PyInstaller"):
        distribution = importlib.metadata.distribution(package)
        for file in distribution.files or []:
            if "/licenses/" in str(file) or file.name.upper().startswith(("LICENSE", "COPYING")):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    shutil.copy2(source, licenses / f"{package}-{file.name}")

    PyInstaller.__main__.run([
        "--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", NAME, "--osx-bundle-identifier", BUNDLE_ID,
        "--icon", str(icon), "--distpath", str(here / "dist"),
        "--workpath", str(build), "--specpath", str(build),
        "--add-data", str(here / "index.html") + ":.",
        "--add-data", str(here / "app.js") + ":.",
        "--add-data", str(config) + ":.",
        "--add-data", str(here / "THIRD_PARTY_NOTICES.txt") + ":.",
        "--add-data", str(licenses) + ":ThirdPartyLicenses",
        "--hidden-import", "webview.platforms.cocoa", str(here / "秒薪.pyw"),
    ])
    app = here / "dist" / f"{NAME}.app"
    info_path = app / "Contents" / "Info.plist"
    info = plistlib.loads(info_path.read_bytes())
    info.update({
        "CFBundleShortVersionString": VERSION, "CFBundleVersion": BUILD,
        "LSMinimumSystemVersion": MIN_MACOS, "LSApplicationCategoryType": "public.app-category.finance",
        "CFBundleDevelopmentRegion": "zh_CN", "CFBundleLocalizations": ["zh_CN"],
        "NSHumanReadableCopyright": "秒薪 · 原项目 liumingshuo77-cmyk/miaoxin",
    })
    info_path.write_bytes(plistlib.dumps(info))
    # Metadata changes invalidate the build's initial ad-hoc signature.
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    print(app)
    if not args.dmg:
        return

    arch = platform.machine()
    output = here / "dist" / f"Miaoxin-{VERSION}-macOS-{arch}.dmg"
    with tempfile.TemporaryDirectory(prefix="dmg-", dir=build) as staging:
        root = Path(staging)
        subprocess.run(["ditto", str(app), str(root / app.name)], check=True)
        (root / "Applications").symlink_to("/Applications")
        shutil.copy2(here / "INSTALL-macOS.txt", root / "安装说明.txt")
        subprocess.run(["hdiutil", "create", "-volname", f"秒薪 {VERSION}", "-srcfolder", str(root),
                        "-format", "UDZO", "-ov", str(output)], check=True)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".dmg.sha256").write_text(f"{digest}  {output.name}\n", encoding="ascii")
    manifest = {"version": VERSION, "build": BUILD, "architecture": arch, "minimum_macos": MIN_MACOS,
                "repository": args.release_repo, "file": output.name, "sha256": digest,
                "signature": "ad-hoc", "notarized": False}
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
