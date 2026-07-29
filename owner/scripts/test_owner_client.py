#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import owner_client


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class OwnerClientRetryTest(unittest.TestCase):
    def config(self):
        return {"platform_url": "https://lenin.example", "token": "private-token"}

    def test_get_retries_transient_transport_errors(self):
        with (
            patch.object(owner_client, "load_config", side_effect=self.config),
            patch.object(owner_client.time, "sleep") as sleep,
            patch.object(
                owner_client.urllib.request,
                "urlopen",
                side_effect=[
                    urllib.error.URLError("temporary"),
                    urllib.error.URLError("temporary"),
                    Response({"ok": True}),
                ],
            ) as urlopen,
        ):
            result = owner_client.request("/api/product/owner/capabilities")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.headers["X-lenin-owner-plugin-version"], "0.9.0")

    def test_web_session_cookie_takes_precedence_without_bearer_header(self):
        with (
            patch.dict(
                owner_client.os.environ,
                {
                    "LENIN_OWNER_PLATFORM_URL": "http://127.0.0.1:3847",
                    "LENIN_OWNER_SESSION_COOKIE": "lenin_session=signed",
                },
                clear=False,
            ),
            patch.object(owner_client, "load_config", side_effect=self.config),
            patch.object(owner_client.urllib.request, "urlopen", return_value=Response({"ok": True})) as urlopen,
        ):
            result = owner_client.request("/api/product/owner/capabilities")

        self.assertEqual(result, {"ok": True})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.headers["Cookie"], "lenin_session=signed")
        self.assertNotIn("Authorization", request.headers)
        self.assertEqual(request.full_url, "http://127.0.0.1:3847/api/product/owner/capabilities")

    def test_plain_mutation_is_not_retried(self):
        with (
            patch.object(owner_client, "load_config", side_effect=self.config),
            patch.object(owner_client.time, "sleep") as sleep,
            patch.object(
                owner_client.urllib.request,
                "urlopen",
                side_effect=urllib.error.URLError("temporary"),
            ) as urlopen,
        ):
            with self.assertRaisesRegex(ValueError, "недоступна"):
                owner_client.request("/api/admin/projects/luna", method="PATCH", body={"status": "archived"})

        self.assertEqual(urlopen.call_count, 1)
        sleep.assert_not_called()

    def test_delegate_retries_only_with_stable_operation_id(self):
        calls = []

        def urlopen(request, timeout):
            calls.append((request.data, timeout))
            if len(calls) == 1:
                raise urllib.error.URLError("response lost")
            return Response({"ok": True, "recovered": True})

        body = {
            "instruction": "Подготовь итог",
            "operationId": "delegate-123",
            "confirmed": True,
        }
        with (
            patch.object(owner_client, "load_config", side_effect=self.config),
            patch.object(owner_client.time, "sleep"),
            patch.object(owner_client.urllib.request, "urlopen", side_effect=urlopen),
        ):
            result = owner_client.request(
                "/api/product/owner/projects/luna/delegate",
                method="POST",
                body=body,
            )

        self.assertEqual(result["recovered"], True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], calls[1][0])
        self.assertEqual(calls[0][1], 45)

    def test_confirmed_message_send_retries_with_the_same_one_time_token(self):
        calls = []

        def urlopen(request, timeout):
            calls.append((request.data, timeout))
            if len(calls) == 1:
                raise urllib.error.URLError("response lost")
            return Response({"ok": True, "deduplicated": True})

        body = {"confirmationToken": "lom_abcdefghijklmnopqrstuvwxyzABCDEFG"}
        with (
            patch.object(owner_client, "load_config", side_effect=self.config),
            patch.object(owner_client.time, "sleep"),
            patch.object(owner_client.urllib.request, "urlopen", side_effect=urlopen),
        ):
            result = owner_client.request(
                "/api/product/owner/messages/send",
                method="POST",
                body=body,
            )

        self.assertEqual(result["deduplicated"], True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], calls[1][0])
        self.assertEqual(calls[0][1], 45)


if __name__ == "__main__":
    unittest.main()
