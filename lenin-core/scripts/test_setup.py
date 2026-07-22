#!/usr/bin/env python3
"""Focused tests for bundled Uplink discovery and setup-code handoff."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parent / "setup.py"


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.home_env = patch.dict(os.environ, {"HOME": self.home.name})
        self.home_env.start()
        spec = importlib.util.spec_from_file_location("lenin_core_setup", SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        root = Path(self.home.name) / "client"
        self.module.PLUGIN = root / "lenin-core"
        self.scripts = root / "lenin-uplink" / "scripts"
        self.scripts.mkdir(parents=True)
        (self.scripts / "session_uplink.py").write_text("", encoding="utf-8")
        (self.scripts / "register.py").write_text("", encoding="utf-8")
        self.module.CONFIG_DIR = Path(self.home.name) / ".claude" / "lenin"
        self.module.CONFIG = self.module.CONFIG_DIR / "config.json"

    def tearDown(self):
        self.home_env.stop()
        self.home.cleanup()

    def test_bundled_uplink_is_used_without_separate_plugin_install(self):
        with patch("subprocess.run", return_value=SimpleNamespace(returncode=0)) as run:
            found = self.module._ensure_uplink_launchd()
        self.assertEqual(found, self.scripts)
        self.assertIn("--install-launchd", run.call_args.args[0])

    def test_setup_code_is_handed_only_to_register_script(self):
        with patch("subprocess.run", return_value=SimpleNamespace(returncode=0)) as run:
            self.module._maybe_register(self.scripts, "lsc_one-time")
        self.assertEqual(run.call_args.args[0][-1], "lsc_one-time")

    def test_existing_token_skips_registration(self):
        uplink = Path(self.home.name) / ".claude" / "lenin_uplink"
        uplink.mkdir(parents=True)
        (uplink / "config.json").write_text(json.dumps({"token": "lu1_active"}), encoding="utf-8")
        with patch("subprocess.run") as run:
            self.module._maybe_register(self.scripts, "lsc_unused")
        run.assert_not_called()

    def test_rerun_preserves_existing_identity_and_kernel_file(self):
        kernel = Path(self.home.name) / "kernel"
        kernel.mkdir()
        identity = kernel / "CLAUDE.md"
        identity.write_text("custom identity\n", encoding="utf-8")
        self.module.CONFIG_DIR.mkdir(parents=True)
        self.module.CONFIG.write_text(json.dumps({
            "owner": "Феликс",
            "profile": "ops",
            "kernel": str(kernel),
            "survey": {"sphere": "Продукт"},
            "created": "2026-07-01T00:00:00+00:00",
        }), encoding="utf-8")
        templates = Path(self.home.name) / "templates"
        templates.mkdir()
        (templates / "CLAUDE.md.template").write_text("<OWNER> <PROFILE>", encoding="utf-8")
        self.module.TEMPLATES = templates
        with patch.object(self.module, "_ensure_uplink_launchd", return_value=None), \
             patch.object(self.module.sys, "argv", ["setup.py"]):
            self.module.main()
        saved = json.loads(self.module.CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(saved["owner"], "Феликс")
        self.assertEqual(saved["profile"], "ops")
        self.assertEqual(saved["created"], "2026-07-01T00:00:00+00:00")
        self.assertEqual(identity.read_text(encoding="utf-8"), "custom identity\n")


if __name__ == "__main__":
    unittest.main()
