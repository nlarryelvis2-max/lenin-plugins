#!/usr/bin/env python3
"""session_uplink_check.py — SessionStart-подхват аплинка сессий (плагин lenin-uplink).

Если последний успешный аплинк (session_uplink.py) был >24ч назад или его не
было вовсе — запускаем прогон в фоне (не блокируя старт сессии). Страховка на
случай, когда launchd-агент не установлен/слетел или Мак был выключен.

Позиционно-независим: session_uplink.py ищется рядом (sibling) — скрипты
живут вместе в scripts/ плагина, где бы плагин ни был установлен.
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path.home() / ".claude" / "lenin_uplink"
STATE_F = BASE / "state.json"
SCRIPT = Path(__file__).resolve().parent / "session_uplink.py"
PLIST = Path.home() / "Library" / "LaunchAgents" / "com.lenin.session-uplink.plist"


def ensure_launchd():
    """Привязать launchd именно к активной версии bundled Uplink."""
    try:
        m = re.search(r"<string>(/[^<]*session_uplink\.py)</string>", PLIST.read_text())
        if m and Path(m.group(1)).resolve() == SCRIPT.resolve():
            return
    except FileNotFoundError:
        pass
    subprocess.run([sys.executable or "python3", str(SCRIPT), "--install-launchd"],
                   capture_output=True, timeout=30)


def main():
    config_path = BASE / "config.json"
    if not config_path.exists():
        return
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        if not cfg.get("enabled", True):
            return
    except Exception:
        return
    ensure_launchd()
    try:
        state = json.loads(STATE_F.read_text(encoding="utf-8"))
        last_ok = datetime.fromisoformat(state["last_ok"])
    except Exception:
        last_ok = None
    if last_ok and datetime.now(timezone.utc) - last_ok < timedelta(hours=24):
        return
    subprocess.Popen(
        [sys.executable or "python3", str(SCRIPT), "--run"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    print("── 📡 uplink: последний аплинк сессий >24ч назад — запустил в фоне ──")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # страховка не должна ломать старт сессии
    sys.exit(0)
