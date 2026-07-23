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
    def test_tool_list_includes_bounded_owner_operations(self):
        names = {tool["name"] for tool in owner_mcp.TOOLS}
        self.assertTrue({
            "lenin_owner_user_list",
            "lenin_owner_user_inspect",
            "lenin_owner_user_context_read",
            "lenin_owner_user_conversation_read",
            "lenin_owner_user_uplink_summary",
            "lenin_owner_user_password_reset",
            "lenin_owner_user_status_set",
            "lenin_owner_project_create",
            "lenin_owner_project_result_owner_set",
            "lenin_owner_user_context_update",
            "lenin_owner_project_context_read",
            "lenin_owner_project_context_update",
            "lenin_owner_user_history_read",
            "lenin_owner_team_chat_read",
            "lenin_owner_team_chat_post",
        }.issubset(names))

    def test_user_list_filters_and_resolves_project_names(self):
        overview = {
            "projects": [{"id": "p-one", "name": "Project One"}],
            "users": [
                {
                    "id": "fil",
                    "name": "Фил",
                    "role": "owner",
                    "status": "active",
                    "passwordConfigured": True,
                    "allProjects": True,
                    "effectiveProjectCount": 1,
                    "projects": [],
                    "uplink": {"state": "connected", "clientCount": 1, "lastSyncAt": "2026-07-23T12:00:00Z"},
                },
                {
                    "id": "sasha",
                    "name": "Саша",
                    "role": "participant",
                    "status": "active",
                    "passwordConfigured": False,
                    "allProjects": False,
                    "effectiveProjectCount": 1,
                    "projects": [{"projectId": "p-one", "role": "contributor"}],
                    "uplink": {"state": "not_connected"},
                },
            ],
        }
        with patch.object(owner_mcp, "request", return_value=overview):
            result = owner_mcp.call("lenin_owner_user_list", {"project_id": "p-one", "query": "саша"})
            inspected = owner_mcp.call("lenin_owner_user_inspect", {"login": "fil"})
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["users"][0]["access"]["grants"][0]["project_name"], "Project One")
        self.assertFalse(result["users"][0]["password_configured"])
        self.assertTrue(inspected["access"]["all_projects"])
        self.assertEqual(inspected["uplink"]["state"], "connected")

    def test_sensitive_reads_require_reason_and_bound_pagination(self):
        calls = []

        def fake_request(path, *, method="GET", body=None, token=""):
            calls.append((path, method, body))
            return {"ok": True}

        with patch.object(owner_mcp, "request", fake_request):
            with self.assertRaisesRegex(ValueError, "reason"):
                owner_mcp.call("lenin_owner_user_context_read", {"login": "a user"})
            owner_mcp.call("lenin_owner_user_context_read", {"login": "a user", "reason": "support review"})
            owner_mcp.call("lenin_owner_user_conversation_read", {
                "login": "a user",
                "project_id": "project/one",
                "reason": "trace issue",
                "limit": 500,
                "offset": -20,
            })
        self.assertEqual(calls[0][0], "/api/admin/users/a%20user/memory?reason=support+review")
        self.assertIn("/api/admin/users/a%20user/conversations?", calls[1][0])
        self.assertIn("projectId=project%2Fone", calls[1][0])
        self.assertIn("limit=100", calls[1][0])
        self.assertIn("offset=0", calls[1][0])

    def test_uplink_summary_falls_back_to_memory_without_private_content(self):
        calls = []

        def fake_request(path, *, method="GET", body=None, token=""):
            calls.append(path)
            if "/uplink?" in path:
                raise ValueError("Administrator endpoint not found")
            return {
                "user": {"id": "fil"},
                "context": {"text": "private"},
                "inventory": [{"path": "personal/context.md"}],
                "uplink": {"count": 2, "machines": [{"machineId": "Mac"}]},
            }

        with patch.object(owner_mcp, "request", fake_request):
            result = owner_mcp.call("lenin_owner_user_uplink_summary", {
                "login": "fil",
                "reason": "connection review",
            })
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["uplink"]["count"], 2)
        self.assertNotIn("context", result)
        self.assertNotIn("inventory", result)

    def test_mutations_require_confirmation_and_use_scoped_routes(self):
        calls = []

        def fake_request(path, *, method="GET", body=None, token=""):
            calls.append((path, method, body))
            return {"temporaryPassword": "temporary"}

        with patch.object(owner_mcp, "request", fake_request):
            with self.assertRaisesRegex(ValueError, "confirmed=true"):
                owner_mcp.call("lenin_owner_user_password_reset", {"login": "fil"})
            reset = owner_mcp.call("lenin_owner_user_password_reset", {"login": "fil", "confirmed": True})
            owner_mcp.call("lenin_owner_user_status_set", {
                "login": "sasha",
                "status": "disabled",
                "confirmed": True,
            })
        self.assertEqual(reset["temporaryPassword"], "temporary")
        self.assertEqual(calls[0], ("/api/admin/users/fil/password", "POST", {}))
        self.assertEqual(calls[1], ("/api/admin/users/sasha", "PATCH", {"status": "disabled"}))

    def test_project_lifecycle_and_context_tools_use_scoped_routes(self):
        calls = []

        def fake_request(path, *, method="GET", body=None, token=""):
            calls.append((path, method, body))
            return {"ok": True}

        with patch.object(owner_mcp, "request", fake_request):
            owner_mcp.call("lenin_owner_project_create", {
                "name": "Новый проект",
                "result_owner_login": "sasha",
                "result_owner_role": "project-owner",
                "confirmed": True,
            })
            owner_mcp.call("lenin_owner_project_result_owner_set", {
                "project_id": "p-one",
                "login": "fil",
                "confirmed": True,
            })
            owner_mcp.call("lenin_owner_user_context_update", {
                "login": "sasha",
                "text": "# Саша",
                "expected_sha256": "abc",
                "confirmed": True,
            })
            owner_mcp.call("lenin_owner_project_context_read", {"project_id": "p-one"})
            owner_mcp.call("lenin_owner_project_context_update", {
                "project_id": "p-one",
                "text": "# Проект",
                "expected_sha256": "def",
                "confirmed": True,
            })
        self.assertEqual(calls[0][0:2], ("/api/admin/projects", "POST"))
        self.assertEqual(calls[0][2]["resultOwnerUserId"], "sasha")
        self.assertEqual(calls[1], (
            "/api/admin/projects/p-one",
            "PATCH",
            {"resultOwnerUserId": "fil"},
        ))
        self.assertEqual(calls[2][0:2], ("/api/admin/users/sasha/memory/context", "PUT"))
        self.assertEqual(calls[3][0], "/api/project-context?projectId=p-one")
        self.assertEqual(calls[4][0:2], ("/api/project-context", "PUT"))

    def test_owner_history_and_team_chat_are_audited_and_scoped(self):
        calls = []

        def fake_request(path, *, method="GET", body=None, token=""):
            calls.append((path, method, body))
            return {"ok": True}

        with patch.object(owner_mcp, "request", fake_request):
            owner_mcp.call("lenin_owner_user_history_read", {
                "login": "sasha",
                "reason": "weekly review",
                "limit": 500,
            })
            owner_mcp.call("lenin_owner_team_chat_read", {
                "reason": "new messages",
                "project_id": "p-one",
                "after_sequence": 42,
            })
            with self.assertRaisesRegex(ValueError, "confirmed=true"):
                owner_mcp.call("lenin_owner_team_chat_post", {
                    "project_id": "p-one",
                    "text": "Принял",
                })
            owner_mcp.call("lenin_owner_team_chat_post", {
                "project_id": "p-one",
                "text": "Принял",
                "confirmed": True,
            })
        self.assertIn("/api/admin/users/sasha/history?", calls[0][0])
        self.assertIn("limit=200", calls[0][0])
        self.assertIn("reason=weekly+review", calls[0][0])
        self.assertIn("/api/product/owner/team-chat?", calls[1][0])
        self.assertIn("projectId=p-one", calls[1][0])
        self.assertEqual(calls[2], (
            "/api/product/owner/team-chat",
            "POST",
            {"projectId": "p-one", "text": "Принял", "confirmed": True},
        ))

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
