#!/usr/bin/env python3
"""Отключить устройство и отозвать его Uplink-токен.

POST {platform}/api/uplink/revoke с локальным Bearer-токеном прекращает будущую
отправку. Уже принятый приватный архив эта команда не удаляет.
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path.home() / ".claude" / "lenin_uplink"
CONFIG = BASE / "config.json"


def save_config(cfg):
    BASE.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG.with_suffix(".tmp")
    temporary.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(CONFIG)
    try:
        CONFIG.chmod(0o600)
    except OSError:
        pass


def clear_local_registration(cfg):
    cfg["token"] = ""
    cfg.pop("refresh_token", None)
    cfg.pop("owner_id", None)
    cfg.pop("core_id", None)
    cfg["enabled"] = False
    save_config(cfg)
    state = BASE / "state.json"
    if state.exists():
        state.unlink()


def revoke():
    if not CONFIG.exists():
        return "not_connected"
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    token = str(cfg.get("token") or "")
    if not token or token == "dev-mock-token":
        clear_local_registration(cfg)
        return "not_connected"

    # Stop local delivery before making the remote request. On a transient
    # failure the token is retained solely so the user can retry revocation.
    cfg["enabled"] = False
    save_config(cfg)
    base = str(cfg.get("platform_url") or "https://lenin.nglain.com").rstrip("/")
    request = urllib.request.Request(base + "/api/uplink/revoke", method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status != 200:
                raise RuntimeError(f"платформа ответила HTTP {response.status}")
    except urllib.error.HTTPError as error:
        if error.code != 401:
            raise RuntimeError(f"платформа ответила HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"платформа недоступна: {error.reason}") from error

    clear_local_registration(cfg)
    return "revoked"


def main():
    try:
        result = revoke()
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Uplink локально остановлен, но серверный доступ не отозван: {error}")
        print("Повторите отключение, когда платформа будет доступна.")
        return 1
    if result == "not_connected":
        print("Lenin Client не был подключён; локальная отправка выключена.")
        return 0
    print("✓ Устройство отключено, Uplink-токен отозван.")
    print("  Для повторного подключения получите новый код в профиле платформы.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
