#!/usr/bin/env python3
"""doctor.py — health-check ядра Ленина (lenin-core).

Проверяет: python3, onboarding-конфиг, развёрнутое ядро, хуки плагина.
Exit 0 = всё ок, иначе ≠0.
"""
import json
import sys
from pathlib import Path

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
    out(False, "конфига нет — запусти /lenin setup")
else:
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        out(True, "конфиг валиден")
        out(bool(cfg.get("owner")), f"owner = {cfg.get('owner', '<пусто>')}")
        out(bool(cfg.get("profile")), f"profile = {cfg.get('profile', '<пусто>')}")
    except Exception as e:
        out(False, f"конфиг битый: {e}")

print("\n── Ядро владельца ──")
kernel = Path(cfg.get("kernel", "")).expanduser() if cfg else Path()
if not kernel or not kernel.exists():
    out(False, f"ядро не развёрнуто: {kernel or '(нет в конфиге)'} — запусти /lenin setup")
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
cache = Path.home() / ".claude" / "plugins" / "cache" / "lenin" / "lenin-core"
out(cache.exists(), f"плагин в кэше: {'да' if cache.exists() else 'нет — /plugin install lenin-core@lenin'}")
if cache.exists():
    versions = [p.name for p in cache.iterdir() if p.is_dir() and p.name != ".git"]
    out(True, f"версии: {', '.join(versions)}")

print()
ok = all(checks)
print("ИТОГ:", "ядро Ленина готово ✅" if ok else f"есть проблемы ({checks.count(False)} пунктов выше) — в основном /lenin setup")
sys.exit(0 if ok else 1)
