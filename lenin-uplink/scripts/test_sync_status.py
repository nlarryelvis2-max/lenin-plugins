#!/usr/bin/env python3
"""Focused tests for Uplink version and successful-sync reporting."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parent / "session_uplink.py"


class SyncStatusTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        with patch.dict(os.environ, {"HOME": self.home.name}):
            spec = importlib.util.spec_from_file_location("session_uplink_status", SCRIPT)
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)

    def tearDown(self):
        self.home.cleanup()

    def test_reports_the_installed_uplink_version(self):
        self.assertEqual(self.module.client_metadata()["version"], "0.2.1")
        self.assertEqual(self.module.client_metadata()["core_version"], "0.1.5")
        self.assertEqual(self.module.client_metadata()["uplink_version"], "1.1.4")
        self.assertIn("core 0.1.5", self.module.lenin_version())
        self.assertIn("uplink 1.1.4", self.module.lenin_version())

    def test_payload_reports_structured_client_versions(self):
        captured = {}

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"accepted":true,"files":{}}'

        def open_request(request, timeout):
            self.assertEqual(timeout, 120)
            captured["body"] = json.loads(self.module.gzip.decompress(request.data))
            return Response()

        config = {**self.module.DEFAULT_CONFIG, "token": "active", "owner_id": "larry", "core_id": "lenin-test"}
        with patch.object(self.module.urllib.request, "urlopen", side_effect=open_request):
            self.module.post_batch(config, "mac", [])
        self.assertEqual(captured["body"]["client"]["name"], "lenin-client")
        self.assertEqual(captured["body"]["client"]["uplink_version"], "1.1.4")

    def test_empty_run_sends_one_heartbeat_and_records_success(self):
        self.module.PROJECTS.mkdir(parents=True)
        self.module.save_json(self.module.CONFIG_F, {
            **self.module.DEFAULT_CONFIG,
            "enabled": True,
            "token": "active",
            "owner_id": "larry",
            "core_id": "lenin-test",
        })
        batches = []

        def accept(_config, _machine, batch):
            batches.append(batch)
            return 200, {"accepted": True, "files": {}}

        with patch.object(self.module, "post_batch", side_effect=accept):
            self.assertEqual(self.module.run(False, 1), 0)
        self.assertEqual(batches, [[]])
        self.assertTrue(json.loads(self.module.STATE_F.read_text())["last_ok"])


if __name__ == "__main__":
    unittest.main()
