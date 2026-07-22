#!/usr/bin/env python3
"""revoke.py — отозвать привязку устройства к платформе (right to erasure).

POST {platform}/api/revoke (Authorization: Bearer <token>) → платформа отзывает
token. Лочно: очищает token/refresh_token/owner_id в config, выставляет enabled:false.
Сессии больше не шлются. Повторное использование — /uplink register (новый device flow).
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path.home() / ".claude" / "lenin_uplink"
CONFIG = BASE / "config.json"


def main():
    if not CONFIG.exists():
        print("config не найден — нечего отзывать.")
        return 0
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    token = cfg.get("token", "")
    base = cfg.get("platform_url", "https://lenin.nglain.com").rstrip("/")
    if token and token != "dev-mock-token":
        req = urllib.request.Request(base + "/api/revoke", method="POST", headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                print(f"платформа: revoke → {resp.status}")
        except urllib.error.HTTPError as e:
            print(f"платформа: revoke → HTTP {e.code} (продолжаю локальную очистку)")
        except Exception as e:
            print(f"платформа недоступна ({e}) — очищаю локально всё равно")
    # локальная очистка (atomic, как в session_uplink)
    cfg["token"] = "dev-mock-token"
    cfg.pop("refresh_token", None)
    cfg.pop("owner_id", None)
    cfg["enabled"] = False
    tmp = CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(CONFIG)
    try:
        CONFIG.chmod(0o600)
    except OSError:
        pass
    # сброс state.json — иначе после re-register (новый owner_id) синк досылает
    # с чужих offset'ов, пропуская начало. Новый owner должен стартовать с нуля.
    state = BASE / "state.json"
    if state.exists():
        state.unlink()
        print("✓ state.json сброшен (новая привязка начнёт с нуля)")
    print("✓ привязка отозвана. token очищен, синк отключён (enabled=false).")
    print("  повторное использование: /uplink register")
    return 0


if __name__ == "__main__":
    sys.exit(main())
