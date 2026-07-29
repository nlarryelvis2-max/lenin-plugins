#!/usr/bin/env python3
from __future__ import annotations

import sys
from owner_client import register


def main() -> int:
    if len(sys.argv) != 2:
        print("Использование: /lenin-owner:connect <одноразовый owner-код>")
        return 2
    try:
        result = register(sys.argv[1])
    except ValueError as error:
        print(f"Owner MCP не подключён: {error}")
        return 1
    print(f"✓ Owner MCP подключён для {result['user_id']}. Токен сохранён локально с mode 0600.")
    print("Перезапустите Claude Code, чтобы появился MCP lenin-owner.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
