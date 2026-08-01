#!/usr/bin/env python3
from __future__ import annotations

import json
import io
import os
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
        self.assertEqual(request.headers["X-lenin-owner-plugin-version"], "0.9.1")
        self.assertEqual(request.headers["Authorization"], "Bearer private-token")
        self.assertNotIn("Cookie", request.headers)

    def test_embedded_web_session_uses_loopback_cookie_instead_of_local_token(self):
        calls = []

        class Opener:
            def open(self, request, timeout):
                calls.append((request, timeout))
                return Response({"ok": True, "projects": 7})

        with (
            patch.dict(os.environ, {
                owner_client.AUTH_MODE_ENV: owner_client.WEB_SESSION_AUTH_MODE,
                owner_client.PLATFORM_URL_ENV: "http://127.0.0.1:3847",
                owner_client.SESSION_COOKIE_ENV: "lenin_session=signed-for-current-owner",
            }, clear=False),
            patch.object(owner_client, "load_config", return_value={
                "platform_url": "https://lenin.example",
                "token": "another-owner-token",
            }),
            patch.object(owner_client.urllib.request, "build_opener", return_value=Opener()),
            patch.object(owner_client.urllib.request, "urlopen") as urlopen,
        ):
            result = owner_client.request("/api/product/owner/portfolio-digest")

        self.assertEqual(result["projects"], 7)
        self.assertEqual(len(calls), 1)
        request, timeout = calls[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:3847/api/product/owner/portfolio-digest")
        self.assertEqual(timeout, 30)
        self.assertEqual(request.headers["Cookie"], "lenin_session=signed-for-current-owner")
        self.assertNotIn("Authorization", request.headers)
        urlopen.assert_not_called()

    def test_embedded_web_session_rejects_external_url_before_network(self):
        with (
            patch.dict(os.environ, {
                owner_client.AUTH_MODE_ENV: owner_client.WEB_SESSION_AUTH_MODE,
                owner_client.PLATFORM_URL_ENV: "https://attacker.example",
                owner_client.SESSION_COOKIE_ENV: "lenin_session=signed",
            }, clear=False),
            patch.object(owner_client.urllib.request, "build_opener") as build_opener,
            patch.object(owner_client.urllib.request, "urlopen") as urlopen,
        ):
            with self.assertRaisesRegex(ValueError, "только через loopback"):
                owner_client.request("/api/admin/overview")

        build_opener.assert_not_called()
        urlopen.assert_not_called()

    def test_embedded_web_session_rejects_header_injection(self):
        with patch.dict(os.environ, {
            owner_client.AUTH_MODE_ENV: owner_client.WEB_SESSION_AUTH_MODE,
            owner_client.PLATFORM_URL_ENV: "http://127.0.0.1:3847",
            owner_client.SESSION_COOKIE_ENV: "lenin_session=signed\r\nX-Evil: yes",
        }, clear=False):
            with self.assertRaisesRegex(ValueError, "некорректный формат"):
                owner_client.request("/api/admin/overview")

    def test_expired_web_session_does_not_recommend_terminal_pairing(self):
        class Opener:
            def open(self, request, timeout):
                raise urllib.error.HTTPError(
                    request.full_url,
                    401,
                    "Unauthorized",
                    {},
                    io.BytesIO(b'{"error":"Unauthorized"}'),
                )

        with (
            patch.dict(os.environ, {
                owner_client.AUTH_MODE_ENV: owner_client.WEB_SESSION_AUTH_MODE,
                owner_client.PLATFORM_URL_ENV: "http://127.0.0.1:3847",
                owner_client.SESSION_COOKIE_ENV: "lenin_session=expired",
            }, clear=False),
            patch.object(owner_client.urllib.request, "build_opener", return_value=Opener()),
        ):
            with self.assertRaisesRegex(ValueError, "Обновите страницу") as raised:
                owner_client.request("/api/admin/overview")

        self.assertNotIn("lenin-owner:connect", str(raised.exception))

    def test_embedded_mode_fails_closed_when_cookie_is_missing(self):
        with (
            patch.dict(os.environ, {
                owner_client.AUTH_MODE_ENV: owner_client.WEB_SESSION_AUTH_MODE,
                owner_client.PLATFORM_URL_ENV: "http://127.0.0.1:3847",
                owner_client.SESSION_COOKIE_ENV: "",
            }, clear=False),
            patch.object(owner_client, "load_config", return_value={"token": "server-resident-token"}),
            patch.object(owner_client.urllib.request, "urlopen") as urlopen,
        ):
            with self.assertRaisesRegex(ValueError, "Веб-сессия владельца недоступна"):
                owner_client.request("/api/admin/overview")

        urlopen.assert_not_called()

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
