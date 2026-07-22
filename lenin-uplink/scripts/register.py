#!/usr/bin/env python3
"""Привязать Uplink к приватной платформе одноразовым setup-кодом.

Код выдаётся авторизованному пользователю после явного consent и действует
10 минут. Платформа возвращает долгоживущий token только этому локальному
процессу; token сохраняется с mode 0600 и никогда не печатается.
"""
from __future__ import annotations

import json
import platform
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path.home() / ".claude" / "lenin_uplink"
CONFIG = BASE / "config.json"
PROD_BASE = "https://lenin.nglain.com"


def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(patch: dict) -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    config = load_config()
    config.update(patch)
    temporary = CONFIG.with_suffix(".tmp")
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(CONFIG)
    CONFIG.chmod(0o600)


def machine_id() -> str:
    try:
        result = subprocess.run(
            ["scutil", "--get", "LocalHostName"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return platform.node() or "unknown-mac"


def registration_url(config: dict) -> str:
    platform_url = str(config.get("platform_url") or PROD_BASE).rstrip("/")
    if not platform_url.startswith("https://") and not platform_url.startswith("http://127.0.0.1"):
        raise ValueError("platform_url должен использовать HTTPS")
    return f"{platform_url}/api/uplink/register"


def absolute_endpoint(registration: dict, config: dict) -> str:
    value = str(registration.get("sessions_endpoint") or "").strip()
    if not value:
        raise ValueError("платформа не вернула sessions_endpoint")
    if value.startswith("https://") or value.startswith("http://127.0.0.1"):
        return value
    platform_url = str(config.get("platform_url") or PROD_BASE).rstrip("/") + "/"
    return urllib.parse.urljoin(platform_url, value.lstrip("/"))


def register(code: str) -> dict:
    setup_code = str(code or "").strip()
    if not setup_code.startswith("lsc_") or len(setup_code) > 128:
        raise ValueError("нужен действующий одноразовый код lsc_… из Профиль → Lenin Client")
    config = load_config()
    body = json.dumps({"code": setup_code, "machine_id": machine_id()}).encode("utf-8")
    request = urllib.request.Request(
        registration_url(config),
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            registration = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        try:
            message = json.loads(error.read().decode("utf-8")).get("error")
        except Exception:
            message = ""
        if error.code in (401, 409):
            raise ValueError("код истёк, уже использован или этот Mac уже подключён") from error
        raise ValueError(message or f"платформа ответила HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise ValueError(f"платформа недоступна: {error.reason}") from error

    token = str(registration.get("token") or "")
    owner_id = str(registration.get("owner_id") or "")
    core_id = str(registration.get("core_id") or "")
    if not token or not owner_id or not core_id:
        raise ValueError("платформа вернула неполный ответ")
    save_config({
        "enabled": True,
        "endpoint": absolute_endpoint(registration, config),
        "token": token,
        "owner_id": owner_id,
        "core_id": core_id,
    })
    return {"owner_id": owner_id, "core_id": core_id}


def main() -> int:
    if len(sys.argv) != 2:
        print("Получите одноразовый код в Профиль → Lenin Client на приватной платформе.")
        print("Затем выполните: /lenin-client:uplink register <код>")
        return 2
    try:
        registration = register(sys.argv[1])
    except ValueError as error:
        print(f"Uplink не подключён: {error}")
        return 1
    print(f"✓ Uplink подключён для {registration['owner_id']}.")
    print("  Token сохранён локально и не выводится.")
    heartbeat = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("session_uplink.py")), "--heartbeat"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if heartbeat.returncode == 0:
        print("✓ Платформа увидела этот Mac; полная синхронизация продолжится в фоне.")
    else:
        print("⚠ Mac подключён, но первый heartbeat не доставлен; Uplink повторит его автоматически.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
