#!/usr/bin/env python3
"""session_uplink.py — ежедневная централизация сессионных файлов Claude Code.

Задумка (Фил, 2026-07-17): каждый Мак с Лениным раз в день (или при включении /
первом заходе в Ленин) отправляет НОВОЕ из ~/.claude/projects/**/*.jsonl на
центральный сервер для пост-обработки. Ручка сервера пока dummy-макет
(uplink_mock_server.py); реальная подставляется одной строкой в config.json.

Инкрементальность: манифест per-file byte-offset (паттерн telegram_ingest).
Шлём только байты после offset, только до последнего полного '\n'.
Повторный запуск ничего не задваивает — state двигается только после 200 OK.

Контракт ручки (v1, согласован 2026-07-17):
  POST {endpoint}   (default /v1/uplink/sessions)
  Headers: Authorization: Bearer <token> · X-Core-Id · X-Machine-Id
           Content-Type: application/json · Content-Encoding: gzip
  Body (gzip JSON): {machine_id, core_id, sent_at,
                     chunks: [{path, offset, length, sha256, b64}]}
  Ответ 200: {"accepted": true, "files": {path: next_offset}}

Состояние/конфиг:  ~/.claude/lenin_uplink/{state.json, config.json, uplink.log}

Usage:
  session_uplink.py --run                # обычный прогон (для launchd/хука)
  session_uplink.py --dry-run            # показать что ушло бы, не слать
  session_uplink.py --status             # сводка состояния
  session_uplink.py --install-launchd    # поставить com.lenin.session-uplink
  session_uplink.py --max-mb 5           # кэп сырых байт за прогон
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import gzip
import hashlib
import json
import os
import platform
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
PROJECTS = HOME / ".claude" / "projects"
BASE = HOME / ".claude" / "lenin_uplink"
STATE_F = BASE / "state.json"
CONFIG_F = BASE / "config.json"
LOG_F = BASE / "uplink.log"
LOCK_F = BASE / ".lock"
PLIST = HOME / "Library" / "LaunchAgents" / "com.lenin.session-uplink.plist"

DEFAULT_CONFIG = {
    "enabled": True,
    "endpoint": "http://127.0.0.1:8787/v1/uplink/sessions",
    "token": "dev-mock-token",
    "owner_id": "owner",
    "core_id": "lenin-core",
    "max_mb_per_run": 200,
    "max_chunk_mb": 8,
    "max_batch_mb": 24,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg: str) -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    with LOG_F.open("a", encoding="utf-8") as f:
        f.write(f"{now_iso()} {msg}\n")


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(load_json(CONFIG_F, {}))
    if not CONFIG_F.exists():
        save_json(CONFIG_F, cfg)  # первый запуск — материализуем дефолты для правки
    return cfg


def machine_id() -> str:
    try:
        out = subprocess.run(["scutil", "--get", "LocalHostName"],
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return platform.node() or "unknown-mac"


def scan_pending(state: dict, max_chunk: int, only: str | None = None) -> list[dict]:
    """Собрать чанки новых байт по всем *.jsonl (до последнего полного \\n)."""
    chunks = []
    if not PROJECTS.exists():
        return chunks
    files_state = state.setdefault("files", {})
    for p in sorted(PROJECTS.rglob("*.jsonl")):
        if only and only not in str(p):
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        rel = str(p.relative_to(PROJECTS))
        offset = int(files_state.get(rel, {}).get("offset", 0))
        if size < offset:
            offset = 0  # файл пересоздан/усечён — перечитываем с нуля
        if size <= offset:
            continue
        with p.open("rb") as f:
            f.seek(offset)
            data = f.read(max_chunk)
        # резать только по границе строки — активная сессия дописывается
        nl = data.rfind(b"\n")
        if nl < 0:
            continue  # нет ни одной завершённой строки в куске — подождём
        data = data[: nl + 1]
        chunks.append({
            "path": rel,
            "offset": offset,
            "length": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "b64": base64.b64encode(data).decode("ascii"),
            "_raw_len": len(data),
        })
    return chunks


def post_batch(cfg: dict, mid: str, batch: list[dict]) -> dict:
    body = {
        "proto": "lenin-uplink/1",
        "owner_id": cfg.get("owner_id", "unknown"),
        "machine_id": mid,
        "core_id": cfg["core_id"],
        "sent_at": now_iso(),
        "chunks": [{k: v for k, v in c.items() if not k.startswith("_")} for c in batch],
    }
    raw = gzip.compress(json.dumps(body, ensure_ascii=False).encode("utf-8"))
    req = urllib.request.Request(cfg["endpoint"], data=raw, method="POST", headers={
        "Content-Type": "application/json",
        "Content-Encoding": "gzip",
        "Authorization": f"Bearer {cfg['token']}",
        "X-Uplink-Proto": "1",
        "X-Owner-Id": cfg.get("owner_id", "unknown"),
        "X-Core-Id": cfg["core_id"],
        "X-Machine-Id": mid,
    })
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run(dry: bool, max_mb: float | None, only: str | None = None) -> int:
    cfg = load_config()
    if not cfg.get("enabled", True):
        print("uplink: disabled в config.json")
        return 0
    state = load_json(STATE_F, {})
    mid = machine_id()
    max_chunk = int(cfg["max_chunk_mb"] * 1024 * 1024)
    run_cap = int((max_mb if max_mb is not None else cfg["max_mb_per_run"]) * 1024 * 1024)
    batch_cap = int(cfg["max_batch_mb"] * 1024 * 1024)

    state["last_run"] = now_iso()
    total_sent = 0
    total_files = 0
    # цикл: скан → батчи → пока есть новое и не упёрлись в кэп прогона
    while total_sent < run_cap:
        pending = scan_pending(state, max_chunk, only)
        pending = [c for c in pending if c["_raw_len"] > 0]
        if not pending:
            break
        batch, batch_bytes = [], 0
        for c in pending:
            if batch and batch_bytes + c["_raw_len"] > batch_cap:
                break
            if total_sent + batch_bytes + c["_raw_len"] > run_cap and batch:
                break
            batch.append(c)
            batch_bytes += c["_raw_len"]
        if not batch:
            break
        if dry:
            for c in batch:
                print(f"  would send {c['path']}  offset={c['offset']}  +{c['length']}b")
            total_sent += batch_bytes
            total_files += len(batch)
            # dry-run не двигает state — показываем только первый круг
            break
        try:
            resp = post_batch(cfg, mid, batch)
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            log(f"FAIL post: {e}")
            print(f"uplink: ошибка отправки ({e}); state не сдвинут, повторим в следующий раз")
            save_json(STATE_F, state)
            return 1
        if not resp.get("accepted"):
            log(f"FAIL server rejected: {resp}")
            save_json(STATE_F, state)
            return 1
        srv_files = resp.get("files", {})
        progressed = False
        for c in batch:
            prev = int(state.get("files", {}).get(c["path"], {}).get("offset", c["offset"]))
            nxt = int(srv_files.get(c["path"], c["offset"] + c["length"]))
            if nxt != prev:
                progressed = True
            state.setdefault("files", {})[c["path"]] = {"offset": nxt}
        if not progressed:
            # сервер принял, но ни один offset не сдвинулся — не жечь кэп впустую
            log("WARN no-progress batch; стоп до следующего прогона")
            save_json(STATE_F, state)
            break
        total_sent += batch_bytes
        total_files += len(batch)
        state["last_ok"] = now_iso()
        save_json(STATE_F, state)  # state двигается только после подтверждения

    if not dry:
        save_json(STATE_F, state)
    mb = total_sent / 1024 / 1024
    verb = "would send" if dry else "sent"
    msg = f"uplink: {verb} {mb:.1f}MB / {total_files} chunk(s) → {cfg['endpoint']}"
    print(msg)
    log(msg)
    return 0


def status() -> None:
    cfg = load_config()
    state = load_json(STATE_F, {})
    files = state.get("files", {})
    tracked = sum(1 for _ in PROJECTS.rglob("*.jsonl")) if PROJECTS.exists() else 0
    pend = 0
    for p in PROJECTS.rglob("*.jsonl") if PROJECTS.exists() else []:
        rel = str(p.relative_to(PROJECTS))
        off = int(files.get(rel, {}).get("offset", 0))
        try:
            pend += max(0, p.stat().st_size - off)
        except OSError:
            pass
    print(f"endpoint:  {cfg['endpoint']}")
    print(f"core_id:   {cfg['core_id']} · machine: {machine_id()}")
    print(f"last_run:  {state.get('last_run', '—')} · last_ok: {state.get('last_ok', '—')}")
    print(f"файлов в ~/.claude/projects: {tracked} · в манифесте: {len(files)}")
    print(f"не отправлено: {pend/1024/1024:.1f}MB")
    print(f"launchd:   {'установлен' if PLIST.exists() else 'НЕ установлен'} ({PLIST.name})")


def install_launchd() -> None:
    py = sys.executable or "/usr/bin/python3"
    script = str(Path(__file__).resolve())
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.lenin.session-uplink</string>
    <key>ProgramArguments</key>
    <array>
        <string>{py}</string>
        <string>{script}</string>
        <string>--run</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>10</integer></dict>
    <key>RunAtLoad</key><true/>
    <key>StandardOutPath</key><string>{BASE}/launchd.log</string>
    <key>StandardErrorPath</key><string>{BASE}/launchd.err</string>
</dict>
</plist>
"""
    BASE.mkdir(parents=True, exist_ok=True)
    PLIST.write_text(plist, encoding="utf-8")
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
    r = subprocess.run(["launchctl", "load", str(PLIST)], capture_output=True, text=True)
    ok = r.returncode == 0
    print(f"launchd: {'загружен' if ok else 'ошибка загрузки: ' + r.stderr.strip()} → {PLIST}")
    log(f"install-launchd ok={ok}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", action="store_true", help="обычный прогон")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--install-launchd", action="store_true")
    ap.add_argument("--max-mb", type=float, default=None)
    ap.add_argument("--only", default=None, help="фильтр путей (подстрока) — для тестов")
    args = ap.parse_args()

    if args.status:
        status()
        return 0
    if args.install_launchd:
        install_launchd()
        return 0
    if not (args.run or args.dry_run):
        ap.print_help()
        return 0

    BASE.mkdir(parents=True, exist_ok=True)
    with LOCK_F.open("w") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("uplink: уже идёт другой прогон — выходим")
            return 0
        return run(dry=args.dry_run, max_mb=args.max_mb, only=args.only)


if __name__ == "__main__":
    sys.exit(main())
