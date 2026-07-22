#!/usr/bin/env python3
"""register.py — device-flow онбординг аплинка (RFC 8628 + PKCE).

Безопасная привязка плагина к аккаунту на платформе: плагин НЕ отправляет
учётных данных. Device authorization grant (RFC 8628) с PKCE (защита device_code):

  1. Плагин генерит PKCE code_verifier → code_challenge (S256).
  2. POST {platform}/api/device/code {code_challenge, method} → user_code +
     device_code + verification_uri + verification_uri_complete.
  3. Юзер открывает verification_uri_complete (клик — код вшит) или вводит
     user_code; логинится; подтверждает.
  4. Плагин poll'ит POST {platform}/api/device/token {device_code, code_verifier}
     строго по interval, обрабатывая: authorization_pending / slow_down /
     expired_token / access_denied (RFC 8628 §3.5).
  5. 200 → {token, refresh_token, owner_id, endpoint} → config.json.

Запуск: register.py   (platform_url из config, default https://lenin.nglain.com)
"""
import base64
import hashlib
import json
import platform
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path.home() / ".claude" / "lenin_uplink"
CONFIG = BASE / "config.json"
PROD_BASE = "https://lenin.nglain.com"


def load_config():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(patch):
    BASE.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    cfg.update(patch)
    tmp = CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(CONFIG)
    try:
        CONFIG.chmod(0o600)  # token = secret
    except OSError:
        pass


def machine_id():
    try:
        r = subprocess.run(["scutil", "--get", "LocalHostName"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return platform.node() or "unknown"


# ── PKCE (RFC 7636) ──
def make_verifier():
    # 43-128 chars, base64url случайных байт
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")


def challenge_s256(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def post(url, payload, timeout=15):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json",
        "X-Machine-Id": machine_id(),
        "X-Core-Id": "lenin-core",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            pass
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"error": body or str(e)}
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        return 0, {"error": f"сеть/сервер недоступен: {e}"}


def main():
    cfg = load_config()
    base = cfg.get("platform_url", PROD_BASE).rstrip("/")
    if not base.startswith("https://"):
        print(f"⚠ platform_url не HTTPS: {base} — token может перехватить. Используй https://")
    verifier = make_verifier()
    challenge = challenge_s256(verifier)

    print(f"── device-flow регистрация ({base}) ──")
    code, resp = post(base + "/api/device/code", {
        "core_id": cfg.get("core_id", "lenin-core"),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    if code != 200 or "device_code" not in resp:
        print(f"❌ /api/device/code: {code} {resp}")
        print("   Платформа недоступна или не поддерживает device-flow (PKCE).")
        return 1

    device_code = resp["device_code"]
    user_code = resp["user_code"]
    uri = resp.get("verification_uri", base + "/device")
    uri_complete = resp.get("verification_uri_complete")
    interval = int(resp.get("interval", 5))
    expires_in = int(resp.get("expires_in", 600))

    print(f"\n  Открой ссылку и подтверди (код уже вшит):")
    if uri_complete:
        print(f"    {uri_complete}")
    print(f"  или вручную: {uri} → код: {user_code}")
    print(f"\n  Жду подтверждения (код действует {expires_in // 60} мин, poll каждые {interval}с)...\n")

    deadline = time.time() + expires_in
    cur_interval = interval
    while time.time() < deadline:
        time.sleep(cur_interval)
        code, resp = post(base + "/api/device/token", {
            "device_code": device_code,
            "code_verifier": verifier,  # PKCE: доказательство, что это мы запросили код
        }, timeout=15)
        err = (resp or {}).get("error", "")

        if code == 200 and "token" in resp:
            save_config({
                "token": resp["token"],
                "refresh_token": resp.get("refresh_token"),
                "owner_id": resp.get("owner_id", cfg.get("owner_id", "owner")),
                "endpoint": resp.get("endpoint", cfg.get("endpoint")),
            })
            print(f"✓ аккаунт привязан. owner_id={resp.get('owner_id')}")
            print(f"  endpoint={resp.get('endpoint')}")
            print(f"  синк настроен — /uplink run или launchd (уже стоит).")
            return 0

        # Polling state machine (RFC 8628 §3.5)
        if err == "authorization_pending":
            cur_interval = interval
            continue
        if err == "slow_down":
            cur_interval += 5  # замедляемся — сервер просит
            print(f"  (slow_down → poll каждые {cur_interval}с)")
            continue
        if err in ("expired_token", "expired_or_unknown_device"):
            print(f"❌ код истёк. Запусти /uplink register снова.")
            return 1
        if err == "access_denied":
            print(f"❌ вы отказали на платформе. Запустите /uplink register снова, если передумали.")
            return 1
        # неизвестная ошибка
        print(f"⚠ неожиданный ответ: {code} {resp}")
        time.sleep(cur_interval)

    print("❌ таймаут — код не подтверждён за отведённое время.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
