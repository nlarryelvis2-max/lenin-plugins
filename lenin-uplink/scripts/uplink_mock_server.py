#!/usr/bin/env python3
"""uplink_mock_server.py — dummy-макет серверной ручки для session_uplink.py.

Реализует контракт v1 (см. session_uplink.py) на stdlib, чтобы обкатать весь
конвейер независимо от production. Принятые байты складывает в
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
        if self.path == "/api/uplink/register":
            body = self._read_json()
            code = str(body.get("code", ""))
            machine = str(body.get("machine_id", "mock-mac"))
            if not code.startswith("lsc_"):
                return self._reply(401, {"error": "invalid setup code"})
            return self._reply(201, {
                "owner_id": "mock-owner",
                "core_id": f"lenin-{machine}",
                "machine_id": machine,
                "token": "dev-mock-token",
                "sessions_endpoint": "http://127.0.0.1:8787/v1/uplink/sessions",
                "protocol": "lenin-uplink/1",
            })
        if self.path != "/v1/uplink/sessions":
            return self._reply(404, {"error": "unknown endpoint"})
        auth = self.headers.get("Authorization", "")
        tok = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
        if tok != TOKEN:
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
