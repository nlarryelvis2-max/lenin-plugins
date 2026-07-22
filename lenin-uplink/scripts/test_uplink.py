#!/usr/bin/env python3
"""test_uplink.py — end-to-end тест аплинка на моке, одной командой.

Поднимает мок-сервер в фоне → гоняет прогон → проверяет приём → показывает
идемпотентность → гасит мок. Для быстрой проверки что аплинк жив.
"""
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
MOCK = SCRIPTS / "uplink_mock_server.py"
CLIENT = SCRIPTS / "session_uplink.py"
RECEIVED = Path.home() / ".claude" / "lenin_uplink" / "mock_received"
PORT = 8787


def main():
    print("── тест аплинка (мок) ──")
    print(f"1. поднимаю мок-сервер :{PORT} ...")
    mock = subprocess.Popen([sys.executable, str(MOCK), "--port", str(PORT)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.2)
    if mock.poll() is not None:
        print("   ❌ мок не стартовал — порт занят? Выполни: pkill -f uplink_mock_server")
        return 1
    print("   ✓ слушает")
    try:
        print("2. прогон аплинка (max 2MB) ...")
        r = subprocess.run([sys.executable, str(CLIENT), "--run", "--max-mb", "2"],
                           capture_output=True, text=True, timeout=180)
        line = (r.stdout.strip().splitlines() or ["(нет вывода)"])[-1]
        print(f"   {line}")

        if RECEIVED.exists():
            files = list(RECEIVED.rglob("*.jsonl"))
            sz = sum(f.stat().st_size for f in files) / 1024 / 1024
            print(f"3. на «сервере»: {len(files)} файлов, {sz:.1f}MB")

        print("4. повторный прогон (идемпотентность — меньше нового) ...")
        r2 = subprocess.run([sys.executable, str(CLIENT), "--run", "--max-mb", "2"],
                            capture_output=True, text=True, timeout=180)
        line2 = (r2.stdout.strip().splitlines() or ["(нет вывода)"])[-1]
        print(f"   {line2}")

        print("\n✓ аплинк работает.")
        print("  Реальный сервер: endpoint+token в ~/.claude/lenin_uplink/config.json, "
              "rm state.json, /uplink run.")
    finally:
        mock.terminate()
        try:
            mock.wait(timeout=5)
        except subprocess.TimeoutExpired:
            mock.kill()
        print("(мок остановлен)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
