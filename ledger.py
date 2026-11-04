"""Validated, atomic local ledger storage and recoverable imports."""
import json
import math
import os
import re
import tempfile
from datetime import date, datetime
from pathlib import Path
from threading import RLock

MAX_BYTES = 1_000_000
LOCK = RLock()


class LedgerError(ValueError):
    pass


def validate(state):
    if not isinstance(state, dict) or not any(k in state for k in ("salary", "holdings", "sessions", "expenses")):
        raise LedgerError("这不是秒薪账本。请选择秒薪导出的 JSON 或原来的 state.json。")
    if any(key in state for key in ("__proto__", "constructor", "prototype")):
        raise LedgerError("账本包含不支持的字段。")
    if state.get("_schemaVersion", 1) != 1:
        raise LedgerError("账本来自更新版本的秒薪，请先更新应用。")
    for key in ("salary", "rent", "ot", "start", "end", "lunchStart", "lunchEnd"):
        if key in state and not isinstance(state[key], (str, int, float)):
            raise LedgerError(f"账本字段 {key} 格式不正确。")
    for key in ("useHoliday", "deductLunch"):
        if key in state and not isinstance(state[key], bool):
            raise LedgerError(f"账本字段 {key} 格式不正确。")
    if "weekdays" in state and (not isinstance(state["weekdays"], list) or
            any(str(v) not in tuple(map(str, range(7))) for v in state["weekdays"])):
        raise LedgerError("工作日格式不正确。")
    for key in ("holdings", "sales"):
        rows = state.get(key, [])
        if not isinstance(rows, list):
            raise LedgerError("持仓或卖出记录格式不正确。")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("symbol"), str):
                raise LedgerError("持仓或卖出记录缺少股票代码。")
            if not re.fullmatch(r"(?:sh|sz|bj)\d{6}|hk\d{5}|us[A-Z][A-Z0-9.-]{0,9}", row["symbol"]):
                raise LedgerError("股票代码格式不正确。")
            if not isinstance(row.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", row["id"]):
                raise LedgerError("持仓或卖出记录标识不正确。")
            for field in ("name", "qty", "cost", "sell", "price", "date", "fx", "pnl", "currency"):
                if field in row and row[field] is not None and not isinstance(row[field], (str, int, float)):
                    raise LedgerError("持仓或卖出记录字段格式不正确。")
    for key in ("leaves", "sessions", "expenses"):
        entries = state.get(key, {})
        if not isinstance(entries, dict):
            raise LedgerError(f"账本字段 {key} 格式不正确。")
        for day, value in entries.items():
            try:
                if date.fromisoformat(day).isoformat() != day:
                    raise ValueError()
            except (ValueError, TypeError):
                raise LedgerError("账本包含无效日期。") from None
            if key == "leaves" and value not in ("paid", "unpaid", "off", "work"):
                raise LedgerError("休假记录格式不正确。")
            if key == "expenses" and not isinstance(value, (str, int, float)):
                raise LedgerError("开销记录格式不正确。")
            if key == "sessions":
                if not isinstance(value, list):
                    raise LedgerError("打卡记录格式不正确。")
                for segment in value:
                    if not isinstance(segment, dict) or not isinstance(segment.get("start"), (int, float)):
                        raise LedgerError("打卡时间格式不正确。")
                    if not math.isfinite(segment["start"]):
                        raise LedgerError("打卡时间无效。")
                    end = segment.get("end")
                    if end is not None and (not isinstance(end, (int, float)) or not math.isfinite(end) or end < segment["start"]):
                        raise LedgerError("下班时间无效。")
    try:
        raw = json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise LedgerError("账本包含无效数值。") from None
    if len(raw) > MAX_BYTES:
        raise LedgerError("账本太大（上限 1 MB）。")
    return raw


def decode(raw):
    if len(raw) > MAX_BYTES:
        raise LedgerError("账本太大（上限 1 MB）。")
    try:
        state = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError):
        raise LedgerError("账本无法读取，原文件已保留。请从备份恢复。") from None
    validate(state)
    return state


def atomic_write(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".miaoxin-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Ledger:
    def __init__(self, path):
        self.path = Path(path)
        self.backups = self.path.parent / "backups"

    def load(self):
        with LOCK:
            return decode(self.path.read_bytes()) if self.path.exists() else None

    def _backup(self, raw, reason):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = self.backups / f"{stamp}-{reason}.json"
        atomic_write(target, raw)
        return target

    def save(self, state):
        validate(state)
        raw = validate(dict(state, _schemaVersion=1))
        with LOCK:
            if self.path.exists():
                old = self.path.read_bytes()
                decode(old)  # Never silently replace a corrupt or newer ledger.
                if old == raw:
                    return
                daily = self.backups / (date.today().isoformat() + "-daily.json")
                if not daily.exists():
                    atomic_write(daily, old)
            atomic_write(self.path, raw)

    def restore(self, state):
        validate(state)
        raw = validate(dict(state, _schemaVersion=1))
        with LOCK:
            backup = self._backup(self.path.read_bytes(), "before-import") if self.path.exists() else None
            atomic_write(self.path, raw)
            return backup
