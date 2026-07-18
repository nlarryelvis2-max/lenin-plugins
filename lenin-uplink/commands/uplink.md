---
description: "Аплинк сессий Ленина: статус / прогон / установка launchd"
allowed-tools: ["Bash"]
---

Управление централизацией сессий (плагин lenin-uplink). Аргумент пользователя: `$ARGUMENTS`.

Выполни соответствующую команду через Bash:

- без аргумента или `status` → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_uplink.py" --status`
- `run` → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_uplink.py" --run`
- `dry` → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_uplink.py" --dry-run`
- `install` → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_uplink.py" --install-launchd`
- `setup` → покажи пользователю текущий `~/.claude/lenin_uplink/config.json`, спроси endpoint/token/owner_id/core_id, запиши ответы в конфиг и затем выполни `--install-launchd`.

Вывод команды передай пользователю кратко, без пересказа очевидного. Если конфиг отсутствует — первый запуск `--status` создаст его с дефолтами (мок-эндпоинт), скажи об этом.
