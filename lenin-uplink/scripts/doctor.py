#!/usr/bin/env python3
"""doctor.py — health-check установки lenin-uplink.

Одним прогоном проверяет всё, что нужно для работающего аплинка, и говорит
конкретно что не так. Exit 0 = всё ок, иначе ≠0 (для launchd/CI).

Usage:  python3 doctor.py
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path.home() / ".claude" / "lenin_uplink"
CONFIG_F = BASE / "config.json"
STATE_F = BASE / "state.json"
PLIST = Path.home() / "Library" / "LaunchAgents" / "com.lenin.session-uplink.plist"
PROJECTS = Path.home() / ".claude" / "projects"

REQUIRED_FIELDS = ["endpoint", "token", "owner_id", "core_id"]
checks = []  # (ok, msg)


def out(ok: bool, msg: str):
    mark = "✅" if ok else "❌"
    checks.append((ok, msg))
    print(f"  {mark} {msg}")


def section(title: str):
    print(f"\n── {title} ──")


# 1. python3
section("Среда")
pyok = sys.version_info >= (3, 8)
out(pyok, f"python3 {sys.version.split()[0]} (нужно ≥3.8)")

# 2. config.json
section("Конфиг (~/.claude/lenin_uplink/config.json)")
if not CONFIG_F.exists():
    out(False, "config.json не найден — запусти session_uplink.py --status (создаст дефолт)")
else:
    try:
        cfg = json.loads(CONFIG_F.read_text(encoding="utf-8"))
        out(True, "config.json валиден")
        out(bool(cfg.get("enabled", True)), f"enabled = {cfg.get('enabled', True)}")
        for f in REQUIRED_FIELDS:
            v = cfg.get(f, "")
            filled = bool(v) and v not in ("dev-mock-token",) or f != "token"
            # token: считаем незаполненным только если dev-mock
            if f == "token":
                filled = bool(v) and v != "dev-mock-token"
            else:
                filled = bool(v)
            shown = ("<пусто>" if not v else ("dev-mock-token" if v == "dev-mock-token" else "<заполнено>"))
            out(filled, f"{f} = {shown}")
    except Exception as e:
        out(False, f"config.json битый: {e}")
        cfg = {}

# 3. endpoint достижимость
section("Endpoint")
endpoint = cfg.get("endpoint", "") if cfg else ""
if not endpoint:
    out(False, "endpoint не задан")
else:
    host = endpoint.split("//", 1)[-1].split("/", 1)[0]
    try:
        socket.getaddrinfo(host, None, timeout=5)
        out(True, f"DNS {host} — резолвится")
    except Exception as e:
        out(False, f"DNS {host} — не резолвится: {e}")
    # лёгкий ping: HEAD/OPTIONS или короткий таймаут на соединение
    try:
        req = urllib.request.Request(endpoint, method="POST", data=b"{}",
                                     headers={"Authorization": f"Bearer {cfg.get('token','')}",
                                              "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=8)
        out(True, "endpoint отвечает (постучались)")  # 200 — повезло; любой ответ = достижим
    except urllib.error.HTTPError as e:
        # HTTP-ошибка (401/400/422) = сервер жив, просто не принял тестовый пустой запрос — это ОК
        out(e.code in (400, 401, 422, 413), f"endpoint ответил HTTP {e.code} (сервер жив)")
    except urllib.error.URLError as e:
        out(False, f"endpoint недостижим: {e.reason}")
    except Exception as e:
        out(False, f"endpoint: {e}")

# 4. launchd
section("launchd (автозапуск)")
plist_ok = PLIST.exists()
out(plist_ok, f"plist установлен: {PLIST.name}")
if plist_ok:
    r = subprocess.run(["launchctl", "list", "com.lenin.session-uplink"],
                       capture_output=True, text=True)
    loaded = r.returncode == 0
    out(loaded, "агент загружен в launchd")
    if loaded:
        m = [l for l in r.stdout.splitlines() if "LastExitStatus" in l]
        if m:
            code = m[0].split("=")[1].strip().rstrip(";").strip('"')
            out(code == "0", f"LastExitStatus = {code}")
        # путь в plist жив?
        body = PLIST.read_text()
        import re
        mpath = re.search(r"<string>(/[^<]*session_uplink\.py)</string>", body)
        if mpath:
            alive = Path(mpath.group(1)).exists()
            out(alive, f"путь plist жив: {mpath.group(1)}")
        else:
            out(False, "в plist не найден путь session_uplink.py")
else:
    out(False, "запусти: /uplink install (или session_uplink.py --install-launchd)")

# 5. данные / состояние
section("Данные")
if PROJECTS.exists():
    n = sum(1 for _ in PROJECTS.rglob("*.jsonl"))
    out(n > 0, f"сессионных файлов: {n}")
else:
    out(False, "~/.claude/projects не найден")
if STATE_F.exists():
    try:
        st = json.loads(STATE_F.read_text(encoding="utf-8"))
        out(True, f"state: last_ok={st.get('last_ok','—')}, файлов в манифесте={len(st.get('files',{}))}")
    except Exception:
        out(False, "state.json битый")
else:
    out(True, "state.json ещё не создан (первый прогон создаст)")

# итог
print()
ok = all(c[0] for c in checks)
print("ИТОГ:", "всё готово к аплинку ✅" if ok else f"есть проблемы ({sum(1 for c in checks if not c[0])} пунктов выше)")
sys.exit(0 if ok else 1)
