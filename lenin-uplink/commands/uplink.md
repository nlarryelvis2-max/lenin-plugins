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
- `doctor` → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py"` — health-check всей установки одним прогоном.
- `test` → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/test_uplink.py"` — end-to-end тест на моке одной командой (поднимает мок → прогон → проверка приёма → идемпотентность → гасит мок).
- `register` → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/register.py"` — привязка к платформе (device flow RFC 8628 + PKCE): покажет код → юзер подтверждает на lenin.nglain.com → токен в config.
- `unregister` → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/revoke.py"` — отозвать привязку: платформа revoke + локально очищает token, синк отключён.

Вывод команды передай пользователю кратко, без пересказа очевидного. Если конфиг отсутствует — первый запуск `--status` создаст его с дефолтами (мок-эндпоинт), скажи об этом.
