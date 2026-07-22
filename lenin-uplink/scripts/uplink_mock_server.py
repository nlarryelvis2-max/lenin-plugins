#!/usr/bin/env python3
"""uplink_mock_server.py — dummy-макет серверной ручки для session_uplink.py.

Реализует контракт v1 (см. session_uplink.py) на stdlib, чтобы обкатать весь
конвейер до появления реального сервера. Принятые байты складывает в
~/.claude/lenin_uplink/mock_received/<machine_id>/<path> — append по offset,
т.е. на выходе точные копии сессионных файлов, собранные инкрементально.

Usage:  python3 uplink_mock_server.py [--port 8787] [--token dev-mock-token]
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

RECEIVED = Path.home() / ".claude" / "lenin_uplink" / "mock_received"
TOKEN = "dev-mock-token"


def safe_rel(path: str) -> Path | None:
    """Защита от traversal: только относительный путь без .. """
    p = Path(path)
    if p.is_absolute() or ".." in p.parts:
        return None
    return p


class Handler(BaseHTTPRequestHandler):
    # device-flow state (мок): device_code → {created, confirmed}
    devices = {}

    def log_message(self, fmt, *args):  # тихий лог в одну строку
        print(f"[mock] {self.address_string()} {fmt % args}")

    def _reply(self, code: int, obj: dict):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return {}

    def do_POST(self):
        # ── device-flow: /api/device/code (RFC 8628 + PKCE) ──
        if self.path == "/api/device/code":
            body = self._read_json()
            import secrets, time
            alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # без I/O/0/1 (RFC 8628 §6.1)
            def grp(): return "".join(secrets.choice(alphabet) for _ in range(4))
            user_code = f"{grp()}-{grp()}"
            device_code = secrets.token_urlsafe(32)
            verification_uri = "http://127.0.0.1:8787/device"
            self.devices[device_code] = {
                "created": time.time(),
                "core_id": body.get("core_id", "lenin-core"),
                "challenge": body.get("code_challenge"),
                "method": body.get("code_challenge_method"),
            }
            return self._reply(200, {
                "device_code": device_code,
                "user_code": user_code,
                "verification_uri": verification_uri,
                "verification_uri_complete": f"{verification_uri}?code={user_code}",
                "expires_in": 600,
                "interval": 2,
            })
        # ── device-flow: /api/device/token (poll, RFC 8628 §3.5 + PKCE) ──
        if self.path == "/api/device/token":
            body = self._read_json()
            dc = body.get("device_code", "")
            dev = self.devices.get(dc)
            if not dev:
                return self._reply(404, {"error": "expired_token"})
            import time, hashlib, base64
            if dev.get("challenge"):  # PKCE-проверка
                v = body.get("code_verifier", "")
                calc = base64.urlsafe_b64encode(hashlib.sha256(v.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
                if calc != dev["challenge"]:
                    return self._reply(400, {"error": "invalid_grant", "error_description": "PKCE mismatch"})
            if time.time() - dev["created"] < 4:  # «юзер подтвердил» через ~4с
                return self._reply(202, {"error": "authorization_pending"})
            return self._reply(200, {
                "token": f"mock-token-{dc[:8]}",
                "refresh_token": f"mock-refresh-{dc[:8]}",
                "owner_id": f"mock-owner-{dc[:4]}",
                "endpoint": "http://127.0.0.1:8787/v1/uplink/sessions",
                "expires_in": 3600,
            })
        if self.path != "/v1/uplink/sessions":
            return self._reply(404, {"error": "unknown endpoint"})
        auth = self.headers.get("Authorization", "")
        tok = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
        if tok != TOKEN and not tok.startswith("mock-token-"):
            return self._reply(401, {"error": "bad token"})
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        if self.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception as e:
            return self._reply(400, {"error": f"bad json: {e}"})

        owner = re.sub(r"[^\w.-]", "_", body.get("owner_id", "unknown"))
        machine = re.sub(r"[^\w.-]", "_", body.get("machine_id", "unknown"))
        files_resp = {}
        for c in body.get("chunks", []):
            rel = safe_rel(c.get("path", ""))
            if rel is None:
                return self._reply(400, {"error": f"bad path: {c.get('path')}"})
            dest = RECEIVED / owner / machine / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            cur = dest.stat().st_size if dest.exists() else 0
            offset = int(c.get("offset", 0))
            data = base64.b64decode(c.get("b64", ""))
            if hashlib.sha256(data).hexdigest() != c.get("sha256"):
                return self._reply(400, {"error": f"sha256 mismatch: {c['path']}"})
            if offset == cur:
                with dest.open("ab") as f:
                    f.write(data)
                files_resp[c["path"]] = cur + len(data)
            elif offset < cur:
                files_resp[c["path"]] = cur  # уже есть — идемпотентность ретраев
            else:
                # дыра: сервер отстал — просим клиента с нашего offset
                files_resp[c["path"]] = cur
        self._reply(200, {"accepted": True, "files": files_resp})


def main():
    global TOKEN
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--token", default=TOKEN)
    args = ap.parse_args()
    TOKEN = args.token
    RECEIVED.mkdir(parents=True, exist_ok=True)
    print(f"[mock] listening :{args.port} → {RECEIVED}")
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
