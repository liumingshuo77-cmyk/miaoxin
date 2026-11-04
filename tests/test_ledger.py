import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ledger import Ledger, LedgerError, decode
from desktop_support import check_update


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = Ledger(Path(self.folder.name) / "state.json")

    def test_daily_backup_keeps_first_previous_version(self):
        for salary in ("100", "200", "300"):
            self.store.save({"salary": salary})
        backups = list(self.store.backups.glob("*-daily.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(decode(backups[0].read_bytes())["salary"], "100")
        self.assertEqual(self.store.load()["salary"], "300")

    def test_corrupt_file_is_never_silently_replaced(self):
        broken = b'{"salary":'
        self.store.path.write_bytes(broken)
        with self.assertRaises(LedgerError):
            self.store.load()
        with self.assertRaises(LedgerError):
            self.store.save({"salary": "100"})
        self.assertEqual(self.store.path.read_bytes(), broken)
        backup = self.store.restore({"salary": "200"})
        self.assertEqual(backup.read_bytes(), broken)
        self.assertEqual(self.store.load()["salary"], "200")

    def test_failed_atomic_replace_retains_original_and_cleans_temp(self):
        self.store.save({"salary": "100"})
        with patch("ledger.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.store.save({"salary": "200"})
        self.assertEqual(self.store.load()["salary"], "100")
        self.assertFalse(list(Path(self.folder.name).rglob("*.tmp")))

    def test_invalid_imports_leave_ledger_intact(self):
        self.store.save({"salary": "100"})
        for state in ({}, {"salary": "0", "_schemaVersion": 2}, {"salary": "0", "holdings": [None]},
                      {"sessions": {"2026-02-30": []}}, {"salary": float("nan")},
                      {"sessions": {"2026-11-04": [{"start": 20, "end": 10}]}},
                      {"salary": "0", "__proto__": {}}, {"salary": "0", "note": "x" * 1000001}):
            with self.subTest(state=str(state)[:80]), self.assertRaises(LedgerError):
                self.store.restore(state)
        self.assertEqual(self.store.load()["salary"], "100")

    def test_windows_ledger_can_be_restored_without_schema_marker(self):
        legacy = {"salary": "21000", "holdings": [{"id": "abc123", "symbol": "sh600519", "name": "贵州茅台", "qty": "100", "cost": ""}],
                  "sessions": {"2026-11-04": [{"start": 1000, "end": None}]}}
        self.store.restore(legacy)
        self.assertEqual(self.store.load(), dict(legacy, _schemaVersion=1))


class UpdateTests(unittest.TestCase):
    def test_versions_and_untrusted_release_metadata(self):
        for tag, expected in (("mac-v1.1.0", True), ("v0.9.0", False), ("mac-v1.0.0", False)):
            with self.subTest(tag=tag), patch("desktop_support.urllib.request.urlopen") as request:
                request.return_value.__enter__.return_value.read.return_value = json.dumps({"tag_name": tag}).encode()
                self.assertEqual(check_update(None)["newer"], expected)
        with patch("desktop_support.urllib.request.urlopen") as request:
            request.return_value.__enter__.return_value.read.return_value = b'{"tag_name":"https://evil.example"}'
            self.assertFalse(check_update(None)["ok"])

    def test_offline_update_is_recoverable(self):
        with patch("desktop_support.urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertFalse(check_update(None)["ok"])


if __name__ == "__main__":
    unittest.main()
