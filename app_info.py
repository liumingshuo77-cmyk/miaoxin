"""Shared application and release metadata."""
import json
import re
import sys
from pathlib import Path

NAME = "秒薪"
VERSION = "1.0.0"
BUILD = "1"
BUNDLE_ID = "com.miaoxin.desktop"
MIN_MACOS = "15.0"
UPSTREAM = "liumingshuo77-cmyk/miaoxin"
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def release_repo():
    config = ROOT / "release-config.json"
    repo = json.loads(config.read_text(encoding="utf-8"))["repository"] if config.exists() else UPSTREAM
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Invalid release repository")
    return repo


def version_tuple(value):
    match = re.fullmatch(r"(?:mac-v|v)?(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise ValueError("Unsupported version")
    return tuple(map(int, match.groups()))
