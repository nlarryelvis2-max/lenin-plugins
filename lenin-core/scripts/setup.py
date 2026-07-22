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


def render_claude(owner, profile, survey):
    txt = (TEMPLATES / "CLAUDE.md.template").read_text(encoding="utf-8")
    sphere = survey.get("sphere", "").strip()
    values = survey.get("values", "").strip()
    context = survey.get("context", "").strip()
    bio = sphere or "<заполни: кем работаешь, какие проекты>"
    if values:
        bio += f". Важно: {values}"
    if context:
        bio += f". {context}"
    return (txt.replace("<OWNER>", owner)
              .replace("<PROFILE>", f"{profile} ({PROFILE_HINTS[profile]})")
              .replace("<заполни: кем работает, какие проекты, что важно>", bio))


def ask_survey():
    """Анкета холодного старта (опц) — кормит 14D и identity_context."""
    print("\nАнкета холодного старта (Enter = пропустить):")
    s = {
        "sphere": input("  Чем занимаешься (сфера/роль)? ").strip(),
        "values": input("  Что для тебя важно (ценности)? ").strip(),
        "context": input("  Контекст/опыт (чем наполнить Ленин)? ").strip(),
    }
    return {k: v for k, v in s.items() if v}


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
    survey = ask_survey() if interactive else {}
    default_dir = str(Path.home() / ".claude" / "lenin-kernel")
    kernel_s = args.dir or (input(f"Куда развернуть ядро [{default_dir}]: ").strip() if interactive else default_dir)
    kernel = Path(kernel_s).expanduser().resolve()

    # 1. config (анкета → кормит 14D-холодный старт + identity_context)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({
        "owner": owner, "profile": profile, "kernel": str(kernel),
        "survey": survey,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ конфиг: {CONFIG}")

    # 2. deploy templates
    kernel.mkdir(parents=True, exist_ok=True)
    (kernel / "CLAUDE.md").write_text(render_claude(owner, profile, survey), encoding="utf-8")
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

    # 3. авто-launchd для аплинка, если плагин установлен (синк с первого дня)
    uplink_script = _ensure_uplink_launchd()

    # 4. авто-register на платформе (device flow), если token ещё моковый
    _maybe_register(uplink_script)

    print(f"\nДальше: открой Claude Code в этой папке → Ленин живой:")
    print(f"  cd {kernel} && claude")


def _ensure_uplink_launchd():
    """Если lenin-uplink установлен — поставить его launchd. Возвращает путь к скрипт-директории uplink или None."""
    import subprocess
    cache = Path.home() / ".claude" / "plugins" / "cache" / "lenin" / "lenin-uplink"
    if not cache.exists():
        print("ℹ lenin-uplink не установлен — синк опционален (/plugin install lenin-uplink@lenin)")
        return None
    versions = sorted(
        (p for p in cache.iterdir() if p.is_dir() and p.name[:1].isdigit()),
        key=lambda p: [int(x) for x in p.name.split(".") if x.isdigit()],
    )
    if not versions:
        return None
    scripts_dir = versions[-1] / "scripts"
    script = scripts_dir / "session_uplink.py"
    if not script.exists():
        return None
    r = subprocess.run([sys.executable, str(script), "--install-launchd"],
                       capture_output=True, text=True, timeout=30)
    ok = r.returncode == 0
    print(f"{'✓' if ok else '⚠'} launchd для синка: {'установлен (ежедневно + при включении)' if ok else 'не установлен — /uplink install'}")
    return scripts_dir


def _maybe_register(uplink_scripts_dir):
    """Если uplink стоит и token ещё моковый — device-flow регистрация на платформе.
    Бесшовно: юзер подтверждает устройство на lenin.nglain.com → токен в config."""
    import subprocess
    if not uplink_scripts_dir:
        return
    cfg_uplink = Path.home() / ".claude" / "lenin_uplink" / "config.json"
    needs_register = True
    if cfg_uplink.exists():
        try:
            tok = json.loads(cfg_uplink.read_text(encoding="utf-8")).get("token", "")
            needs_register = (tok in ("", "dev-mock-token"))
        except Exception:
            pass
    if not needs_register:
        print("✓ синк уже привязан к аккаунту (token в config)")
        return
    register = uplink_scripts_dir / "register.py"
    if not register.exists():
        return
    print("\n── привязка к платформе (device flow) ──")
    print("   (потребует подтверждения на lenin.nglain.com)")
    try:
        subprocess.run([sys.executable, str(register)], timeout=660)
    except subprocess.TimeoutExpired:
        print("⚠ регистрация превысила время — заверши /uplink register позже")
    except FileNotFoundError:
        print("⚠ регистрация недоступна — /uplink register позже")


if __name__ == "__main__":
    main()
