#!/usr/bin/env python3
"""setup.py — онбординг ядра Ленина.

Шаги:
  1. Спросить имя владельца + тип профиля.
  2. Записать ~/.claude/lenin/config.json.
  3. Развернуть templates/ в папку ядра владельца (CLAUDE.md, MEMORY.md, hot/, library/).

Режимы:
  setup.py --owner X --profile psych --dir ~/my-lenin   # неинтерактив (для slash command)
  setup.py                                               # интерактив (в терминале)
"""
import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
TEMPLATES = PLUGIN / "templates"
CONFIG_DIR = Path.home() / ".claude" / "lenin"
CONFIG = CONFIG_DIR / "config.json"
PROFILES = ["psych", "cfo", "ops", "builder", "designer", "athlete"]
PROFILE_HINTS = {
    "psych": "психотерапия/люди", "cfo": "финансы/цифры", "ops": "операционка/процессы",
    "builder": "стройка/производство", "designer": "дизайн/креатив", "athlete": "спорт/тело",
}


def ask_profile():
    print("Тип профиля (определяет язык Ленина — метафоры, глубину, тон):")
    for i, p in enumerate(PROFILES, 1):
        print(f"  {i}. {p} — {PROFILE_HINTS[p]}")
    while True:
        s = input(f"Выбери 1-{len(PROFILES)}: ").strip()
        if s.isdigit() and 1 <= int(s) <= len(PROFILES):
            return PROFILES[int(s) - 1]
        if s in PROFILES:
            return s


def render_claude(owner, profile):
    txt = (TEMPLATES / "CLAUDE.md.template").read_text(encoding="utf-8")
    return txt.replace("<OWNER>", owner).replace("<PROFILE>", f"{profile} ({PROFILE_HINTS[profile]})")


def main():
    ap = argparse.ArgumentParser(description="Онбординг ядра Ленина")
    ap.add_argument("--owner", help="имя владельца")
    ap.add_argument("--profile", choices=PROFILES, help="тип профиля")
    ap.add_argument("--dir", help="куда развернуть ядро")
    ap.add_argument("--force", action="store_true", help="перезаписать существующие файлы")
    args = ap.parse_args()

    interactive = sys.stdin.isatty() and not (args.owner and args.profile)
    owner = args.owner or (input("Имя владельца: ").strip() if interactive else "owner")
    profile = args.profile or (ask_profile() if interactive else "psych")
    default_dir = str(Path.home() / ".claude" / "lenin-kernel")
    kernel_s = args.dir or (input(f"Куда развернуть ядро [{default_dir}]: ").strip() if interactive else default_dir)
    kernel = Path(kernel_s).expanduser().resolve()

    # 1. config
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({
        "owner": owner, "profile": profile, "kernel": str(kernel),
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ конфиг: {CONFIG}")

    # 2. deploy templates
    kernel.mkdir(parents=True, exist_ok=True)
    (kernel / "CLAUDE.md").write_text(render_claude(owner, profile), encoding="utf-8")
    for name in ["MEMORY.md"]:
        src, dst = TEMPLATES / f"{name}.template", kernel / name
        if src.exists() and (args.force or not dst.exists()):
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    hot = kernel / "hot"
    hot.mkdir(exist_ok=True)
    for f in (TEMPLATES / "hot").glob("*.md"):
        dst = hot / f.name
        if args.force or not dst.exists():
            dst.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    lib = kernel / "library"
    lib.mkdir(exist_ok=True)
    tmpl = TEMPLATES / "library" / "_template.md"
    if tmpl.exists() and (args.force or not (lib / "_template.md").exists()):
        shutil.copy(tmpl, lib / "_template.md")
    print(f"✓ ядро развёрнуто: {kernel}")
    print(f"  owner={owner} · profile={profile}")
    print(f"\nДальше: открой Claude Code в этой папке → Ленин живой:")
    print(f"  cd {kernel} && claude")


if __name__ == "__main__":
    main()
