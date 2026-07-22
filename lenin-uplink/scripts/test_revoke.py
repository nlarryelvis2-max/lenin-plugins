#!/usr/bin/env python3
"""Focused tests for safe client-initiated Uplink revocation."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parent / "revoke.py"


class RevokeTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        with patch.dict(os.environ, {"HOME": self.home.name}):
            spec = importlib.util.spec_from_file_location("lenin_uplink_revoke", SCRIPT)
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        self.module.save_config({
            "enabled": True,
            "platform_url": "https://lenin.example",
            "token": "lu1_secret",
            "owner_id": "felix",
            "core_id": "lenin-felix-mac",
        })

    def tearDown(self):
        self.home.cleanup()

    def test_revokes_remote_token_then_clears_local_registration(self):
        captured = {}

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        def open_request(request, timeout):
            captured["url"] = request.full_url
            captured["authorization"] = request.headers["Authorization"]
            self.assertEqual(timeout, 20)
            return Response()

        with patch.object(self.module.urllib.request, "urlopen", side_effect=open_request):
            self.assertEqual(self.module.revoke(), "revoked")

        self.assertEqual(captured["url"], "https://lenin.example/api/uplink/revoke")
        self.assertEqual(captured["authorization"], "Bearer lu1_secret")
        config = json.loads(self.module.CONFIG.read_text())
        self.assertFalse(config["enabled"])
        self.assertEqual(config["token"], "")
        self.assertNotIn("owner_id", config)
        self.assertEqual(self.module.CONFIG.stat().st_mode & 0o777, 0o600)

    def test_network_failure_stops_sync_but_keeps_token_for_retry(self):
        with patch.object(
            self.module.urllib.request,
            "urlopen",
            side_effect=urllib.error.URLError("offline"),
        ):
            with self.assertRaisesRegex(RuntimeError, "недоступна"):
                self.module.revoke()

        config = json.loads(self.module.CONFIG.read_text())
        self.assertFalse(config["enabled"])
        self.assertEqual(config["token"], "lu1_secret")


if __name__ == "__main__":
    unittest.main()
