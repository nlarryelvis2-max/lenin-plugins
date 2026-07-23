#!/usr/bin/env python3
"""Local administrator credential registration and authenticated Lenin API client."""
from __future__ import annotations

import json
import os
import platform
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path.home() / ".claude" / "lenin_owner"
CONFIG = BASE / "config.json"
PROD_BASE = "https://lenin.nglain.com"


def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(value: dict) -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="config.", suffix=".tmp", dir=BASE)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, CONFIG)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def base_url(config: dict | None = None) -> str:
    url = str((config or load_config()).get("platform_url") or PROD_BASE).rstrip("/")
    if not url.startswith("https://") and not url.startswith("http://127.0.0.1"):
        raise ValueError("platform_url должен использовать HTTPS")
    return url


def request(path: str, *, method: str = "GET", body: dict | None = None, token: str = "") -> dict:
    config = load_config()
    credential = token or str(config.get("token") or "")
    if not credential:
        raise ValueError("Owner MCP не подключён: выполните /lenin-client:owner-connect <код>")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{base_url(config)}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {credential}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        try:
            message = json.loads(error.read().decode("utf-8")).get("error")
        except Exception:
            message = ""
        raise ValueError(message or f"платформа ответила HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise ValueError(f"платформа недоступна: {error.reason}") from error


def register(code: str) -> dict:
    pairing_code = str(code or "").strip()
    if not pairing_code.startswith("lpc_") or len(pairing_code) > 128:
        raise ValueError("нужен действующий одноразовый owner-код lpc_…")
    body = {"code": pairing_code, "device_id": platform.node() or "owner-terminal"}
    req = urllib.request.Request(
        f"{base_url()}/api/auth/client-register",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        raise ValueError("owner-код истёк, уже использован или недействителен") from error
    if result.get("scope") != "owner:admin" or not result.get("token"):
        raise ValueError("сервер не выдал owner-доступ")
    save_config({
        "platform_url": base_url(),
        "token": result["token"],
        "user_id": result.get("user_id", ""),
        "scope": result["scope"],
    })
    return {"user_id": result.get("user_id", ""), "scope": result["scope"]}
