#!/usr/bin/env python3
"""Focused tests for one-time setup-code registration."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parent / "register.py"


class RegisterTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        with patch.dict(os.environ, {"HOME": self.home.name}):
            spec = importlib.util.spec_from_file_location("lenin_uplink_register", SCRIPT)
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)

    def tearDown(self):
        self.home.cleanup()

    def test_redeems_setup_code_without_printing_token(self):
        self.module.save_config({"platform_url": "https://lenin.example"})
        captured = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "owner_id": "felix",
                    "core_id": "lenin-felix-mac",
                    "token": "lu1_secret",
                    "sessions_endpoint": "/v1/uplink/sessions",
                }).encode()

        def open_request(request, timeout):
            captured["url"] = request.full_url
            captured["payload"] = json.loads(request.data)
            self.assertEqual(timeout, 30)
            return Response()

        with patch.object(self.module, "machine_id", return_value="Felix-Mac"), patch.object(
            self.module.urllib.request, "urlopen", side_effect=open_request
        ):
            result = self.module.register("lsc_valid-code")

        self.assertEqual(captured["url"], "https://lenin.example/api/uplink/register")
        self.assertEqual(captured["payload"], {"code": "lsc_valid-code", "machine_id": "Felix-Mac"})
        self.assertEqual(result, {"owner_id": "felix", "core_id": "lenin-felix-mac"})
        config = json.loads(self.module.CONFIG.read_text())
        self.assertEqual(config["token"], "lu1_secret")
        self.assertEqual(config["endpoint"], "https://lenin.example/v1/uplink/sessions")
        self.assertEqual(self.module.CONFIG.stat().st_mode & 0o777, 0o600)

    def test_rejects_non_setup_code_before_network(self):
        with patch.object(self.module.urllib.request, "urlopen") as request:
            with self.assertRaisesRegex(ValueError, "одноразовый код"):
                self.module.register("not-a-code")
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
