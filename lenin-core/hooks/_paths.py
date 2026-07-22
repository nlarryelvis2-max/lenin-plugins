"""_paths.py — позиционно-независимые пути для плагина lenin-core.

Плагин ставится в кэш Claude Code (read-only). Состояние ядра (posterior,
observations, optimal) живёт в ПАПКЕ ЯДРА ВЛАДЕЛЬЦА — там, где он открыл
Claude Code. CLAUDE_PROJECT_DIR указывает туда; fallback — текущая папка.
"""
import json
import os
from pathlib import Path


def kernel_dir() -> Path:
    """Папка ядра владельца (где открыт Claude Code)."""
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def plugin_dir() -> Path:
    """Папка плагина (где лежат скрипты, read-only ресурс)."""
    return Path(__file__).resolve().parent


def owner() -> str:
    """Имя владельца из onboarding-конфига, fallback 'owner'."""
    try:
        cfg = Path.home() / ".claude" / "lenin" / "config.json"
        return json.loads(cfg.read_text(encoding="utf-8")).get("owner", "owner")
    except Exception:
        return "owner"
