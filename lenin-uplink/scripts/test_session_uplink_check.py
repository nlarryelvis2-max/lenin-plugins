#!/usr/bin/env python3
"""Focused tests for SessionStart Uplink rebinding after plugin updates."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_FILE = Path(__file__).resolve().parent / "session_uplink_check.py"


class SessionUplinkCheckTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("session_uplink_check", SCRIPT_FILE)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.module.PLIST = root / "com.lenin.session-uplink.plist"
        self.module.SCRIPT = root / "active" / "session_uplink.py"
        self.module.SCRIPT.parent.mkdir()
        self.module.SCRIPT.write_text("", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_rebinds_when_plist_points_to_an_older_cached_version(self):
        old_script = Path(self.temporary.name) / "old" / "session_uplink.py"
        old_script.parent.mkdir()
        old_script.write_text("", encoding="utf-8")
        self.module.PLIST.write_text(
            f"<plist><string>{old_script}</string></plist>",
            encoding="utf-8",
        )
        with patch.object(self.module.subprocess, "run") as run:
            self.module.ensure_launchd()
        self.assertEqual(
            run.call_args.args[0],
            [self.module.sys.executable, str(self.module.SCRIPT), "--install-launchd"],
        )

    def test_keeps_launchd_when_it_already_uses_the_active_version(self):
        self.module.PLIST.write_text(
            f"<plist><string>{self.module.SCRIPT}</string></plist>",
            encoding="utf-8",
        )
        with patch.object(self.module.subprocess, "run") as run:
            self.module.ensure_launchd()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
