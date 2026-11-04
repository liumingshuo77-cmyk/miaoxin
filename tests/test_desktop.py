import os
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import server


class DataTests(unittest.TestCase):
    def test_mac_source_and_bundle_share_writable_user_data(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, "platform", "darwin"), \
                patch.object(Path, "home", return_value=Path("/Users/example")):
            source_data, source_files = server._dirs()
            with patch.object(sys, "frozen", True, create=True), \
                    patch.object(sys, "_MEIPASS", "/Applications/秒薪.app/Contents/Resources", create=True):
                bundle_data, bundle_files = server._dirs()
            self.assertEqual(source_data, Path("/Users/example/Library/Application Support/Miaoxin"))
            self.assertEqual(bundle_data, source_data)
            self.assertEqual(source_files, Path(server.__file__).parent)
            self.assertEqual(bundle_files, Path("/Applications/秒薪.app/Contents/Resources"))

    def test_windows_keeps_portable_ledger(self):
        portable = Path(tempfile.gettempdir()).resolve() / "portable"
        resources = portable / "resources"
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, "platform", "win32"), \
                patch.object(sys, "frozen", True, create=True), \
                patch.object(sys, "executable", str(portable / "秒薪.exe")), \
                patch.object(sys, "_MEIPASS", str(resources), create=True):
            self.assertEqual(server._dirs(), (portable, resources))

    def test_override_and_first_save_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "独立账本"
            with patch.dict(os.environ, {"MIAOXIN_DATA_DIR": str(root)}):
                self.assertEqual(server._dirs()[0], root.resolve())
            with patch.object(server, "STATE_PATH", root / "state.json"):
                self.assertIsNone(server.read_state())
                state = {"salary": "12345", "holdings": [], "note": "秒薪"}
                server.write_state(state)
                self.assertEqual(server.read_state(), dict(state, _schemaVersion=1))
                with self.assertRaises(ValueError):
                    server.write_state({"note": "字" * 400000})
                self.assertEqual(server.read_state(), dict(state, _schemaVersion=1))
                self.assertFalse((root / "state.tmp").exists())


class CloseTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(sys.modules, {"webview": MagicMock()}):
            self.module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "秒薪.pyw"))
        self.api = self.module["Api"]()
        self.api._window = MagicMock()
        self.api._window.evaluate_js.return_value = {"salary": "23456"}
        self.globals = self.api._save_and_close.__globals__

    def test_native_close_vetoes_until_latest_snapshot_is_saved(self):
        thread = MagicMock()
        with patch.dict(self.globals, {"Thread": thread}):
            self.assertFalse(self.api._on_closing())
            self.assertFalse(self.api._on_closing())
        thread.return_value.start.assert_called_once()
        with patch.dict(self.globals, {"write_state": MagicMock()}) as scope:
            self.assertEqual(self.api.save_state({"salary": "older"}), {"ok": False, "skipped": True})
            self.api._save_and_close()
            scope["write_state"].assert_called_once_with({"salary": "23456"})
        self.api._window.destroy.assert_called_once()
        self.assertTrue(self.api._on_closing())

    def test_failed_save_keeps_window_open_and_allows_retry(self):
        self.api._closing = True
        with patch.dict(self.globals, {
            "write_state": MagicMock(side_effect=OSError("disk full")),
            "_log_error": MagicMock(),
        }):
            self.api._save_and_close()
        self.api._window.destroy.assert_not_called()
        self.assertFalse(self.api._closing)
        self.api._window.create_confirmation_dialog.assert_called_once()

    def test_import_restores_and_rejects_queued_old_saves(self):
        from ledger import Ledger
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            source = Path(folder) / "import.json"
            source.write_text('{"salary":"888"}')
            store = Ledger(path)
            store.save({"salary": "100"})
            self.api._window.create_file_dialog.return_value = [str(source)]
            self.api._window.create_confirmation_dialog.return_value = True
            with patch.dict(self.globals, {"STATE_PATH": path, "write_state": store.save}):
                result = self.api.import_backup()
                self.assertTrue(result["ok"], result)
                self.assertEqual(store.load()["salary"], "888")
                self.assertTrue(self.api.save_state({"salary": "stale"}, 0)["skipped"])
                self.assertEqual(store.load()["salary"], "888")
                before = list(store.backups.glob("*-before-import.json"))
                self.assertEqual(len(before), 1)
                import json
                self.assertEqual(json.loads(before[0].read_text())["salary"], "23456")

    def test_cancelled_import_does_not_write(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "import.json"
            source.write_text('{"salary":"888"}')
            self.api._window.create_file_dialog.return_value = [str(source)]
            self.api._window.create_confirmation_dialog.return_value = False
            writer = MagicMock()
            with patch.dict(self.globals, {"write_state": writer}):
                result = self.api.import_backup()
            self.assertTrue(result["ok"])
            writer.assert_not_called()
            self.api._window.evaluate_js.assert_not_called()

    def test_corrupt_ledger_blocks_saves_but_can_close(self):
        with patch.dict(self.globals, {"read_state": MagicMock(side_effect=ValueError("corrupt"))}):
            self.assertEqual(self.api.get_state()["error"], "corrupt")
        self.assertFalse(self.api.save_state({"salary": "100"})["ok"])
        self.assertTrue(self.api._on_closing())


if __name__ == "__main__":
    unittest.main()
