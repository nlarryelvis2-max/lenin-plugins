#!/usr/bin/env python3
from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import owner_mcp


class OwnerMcpTest(unittest.TestCase):
    def test_bootstrap_skips_existing_and_writes_private_credentials_file(self):
        calls = []

        def fake_request(path, *, method="GET", body=None, token=""):
            calls.append((path, method, body))
            if path == "/api/admin/overview":
                return {"users": [{"id": "existing"}]}
            return {"temporaryPassword": f"temporary-for-{body['id']}"}

        with tempfile.TemporaryDirectory() as directory, patch.object(owner_mcp, "request", fake_request):
            output = Path(directory) / "credentials.tsv"
            result = owner_mcp.bootstrap({
                "output_path": str(output),
                "users": [
                    {"login": "existing", "name": "Existing"},
                    {"login": "new-user", "name": "New\tUser"},
                ],
            })
            self.assertEqual(result["created"], 1)
            self.assertEqual(result["skipped_existing"], ["existing"])
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "login\tname\ttemporary_password\nnew-user\tNew User\ttemporary-for-new-user\n",
            )
            self.assertEqual(calls[-1][2]["projectIds"], [])


if __name__ == "__main__":
    unittest.main()
