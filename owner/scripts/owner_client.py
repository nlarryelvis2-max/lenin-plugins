#!/usr/bin/env python3
"""Local administrator credential registration and authenticated Lenin API client."""
from __future__ import annotations

import json
import os
import platform
import re
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

BASE = Path.home() / ".claude" / "lenin_owner"
CONFIG = BASE / "config.json"
PROD_BASE = "https://lenin.nglain.com"
PLUGIN_VERSION = "0.9.1"
RETRYABLE_HTTP = {429, 502, 503, 504}
SESSION_COOKIE_ENV = "LENIN_OWNER_SESSION_COOKIE"
PLATFORM_URL_ENV = "LENIN_OWNER_PLATFORM_URL"
AUTH_MODE_ENV = "LENIN_OWNER_AUTH_MODE"
WEB_SESSION_AUTH_MODE = "web-session"
MAX_SESSION_COOKIE_LENGTH = 8 * 1024


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Keep the short-lived browser credential on the loopback hop only."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


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


def embedded_web_session() -> tuple[str, str] | None:
    """Return the server-injected loopback URL and browser cookie, if present."""
    auth_mode = str(os.environ.get(AUTH_MODE_ENV) or "").strip()
    if auth_mode not in {"", WEB_SESSION_AUTH_MODE}:
        raise ValueError("Встроенный Owner MCP получил неизвестный режим авторизации")
    cookie = str(os.environ.get(SESSION_COOKIE_ENV) or "").strip()
    if not cookie and auth_mode != WEB_SESSION_AUTH_MODE:
        return None
    if not cookie:
        raise ValueError("Веб-сессия владельца недоступна. Обновите страницу и войдите снова.")
    cookie_name, separator, cookie_value = cookie.partition("=")
    if (
        len(cookie) > MAX_SESSION_COOKIE_LENGTH
        or "\r" in cookie
        or "\n" in cookie
        or ";" in cookie
        or separator != "="
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", cookie_name)
        or not cookie_value
    ):
        raise ValueError("Веб-сессия владельца имеет некорректный формат")

    url = str(os.environ.get(PLATFORM_URL_ENV) or "").rstrip("/")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Встроенный Owner MCP принимает веб-сессию только через loopback платформы")
    return url, cookie


def request(path: str, *, method: str = "GET", body: dict | None = None, token: str = "") -> dict:
    config = load_config()
    web_session = embedded_web_session() if not token else None
    credential = token or ("" if web_session else str(config.get("token") or ""))
    if not credential and not web_session:
        raise ValueError("Owner MCP не подключён: выполните /lenin-owner:connect <код>")
    platform_url = web_session[0] if web_session else base_url(config)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Lenin-Owner-Plugin-Version": PLUGIN_VERSION,
    }
    if web_session:
        headers["Cookie"] = web_session[1]
    else:
        headers["Authorization"] = f"Bearer {credential}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    idempotent_mutation = (
        method == "POST"
        and (
            (
                path.endswith("/delegate")
                and isinstance(body, dict)
                and bool(str(body.get("operationId") or "").strip())
            )
            or (
                path == "/api/product/owner/messages/send"
                and isinstance(body, dict)
                and bool(str(body.get("confirmationToken") or "").strip())
            )
        )
    )
    attempts = 3 if method == "GET" or idempotent_mutation else 1
    for attempt in range(attempts):
        req = urllib.request.Request(
            f"{platform_url}{path}",
            data=data,
            method=method,
            headers=headers,
        )
        try:
            timeout = 45 if idempotent_mutation else 30
            response_context = (
                urllib.request.build_opener(_RejectRedirects()).open(req, timeout=timeout)
                if web_session
                else urllib.request.urlopen(req, timeout=timeout)
            )
            with response_context as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:
            if error.code in RETRYABLE_HTTP and attempt + 1 < attempts:
                time.sleep(0.25 * (2 ** attempt))
                continue
            if web_session and error.code in {401, 403}:
                raise ValueError("Веб-сессия владельца истекла. Обновите страницу и войдите снова.") from error
            try:
                message = json.loads(error.read().decode("utf-8")).get("error")
            except Exception:
                message = ""
            raise ValueError(message or f"платформа ответила HTTP {error.code}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt + 1 < attempts:
                time.sleep(0.25 * (2 ** attempt))
                continue
            reason = getattr(error, "reason", error)
            raise ValueError(f"платформа недоступна: {reason}") from error
    raise ValueError("платформа недоступна")


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
