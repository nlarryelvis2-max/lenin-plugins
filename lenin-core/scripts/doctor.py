#!/usr/bin/env python3
"""doctor.py — health-check ядра Ленина в составе Lenin Client.

Проверяет: python3, onboarding-конфиг, развёрнутое ядро и активный клиент.
Exit 0 = всё ок, иначе ≠0.
"""
import json
import sys
from pathlib import Path

CLIENT_ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path.home() / ".claude" / "lenin" / "config.json"
checks = []


def out(ok, msg):
    checks.append(ok)
    print(f"  {'✅' if ok else '❌'} {msg}")


print("\n── Среда ──")
out(sys.version_info >= (3, 8), f"python3 {sys.version.split()[0]} (≥3.8)")

print("\n── Онбординг (~/.claude/lenin/config.json) ──")
cfg = {}
if not CONFIG.exists():
    out(False, "конфига нет — запусти /lenin-client:setup")
else:
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        out(True, "конфиг валиден")
        out(bool(cfg.get("owner")), f"owner = {cfg.get('owner', '<пусто>')}")
        out(bool(cfg.get("profile")), f"profile = {cfg.get('profile', '<пусто>')}")
    except Exception as e:
        out(False, f"конфиг битый: {e}")

print("\n── Ядро владельца ──")
kernel_value = str(cfg.get("kernel") or "").strip() if cfg else ""
kernel = Path(kernel_value).expanduser() if kernel_value else None
if kernel is None or not kernel.exists():
    out(False, f"ядро не развёрнуто: {kernel or '(нет в конфиге)'} — запусти /lenin-client:setup")
else:
    out(True, f"папка ядра: {kernel}")
    out((kernel / "CLAUDE.md").exists(), "CLAUDE.md на месте")
    out((kernel / "MEMORY.md").exists(), "MEMORY.md на месте")
    obs = kernel / "hot" / "observations.md"
    out(obs.exists(), f"observations.md {'есть — веса оживают' if obs.exists() else 'нет'}")
    if obs.exists():
        lines = sum(1 for _ in obs.open(encoding="utf-8"))
        out(lines > 3, f"observations: {lines} строк (наполняется с работы)")

print("\n── Плагин ──")
manifest = CLIENT_ROOT / ".claude-plugin" / "marketplace.json"
try:
    marketplace = json.loads(manifest.read_text(encoding="utf-8"))
    client = next(item for item in marketplace.get("plugins", []) if item.get("name") == "lenin-client")
    version = str(client.get("version") or "").strip()
    out(bool(version), f"Lenin Client {version or '<версия не задана>'}")
except Exception as error:
    out(False, f"manifest клиента недоступен: {error}")

print()
ok = all(checks)
print("ИТОГ:", "ядро Ленина готово ✅" if ok else f"есть проблемы ({checks.count(False)} пунктов выше)")
sys.exit(0 if ok else 1)
