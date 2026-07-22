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
- `setup` → объясни, что ручной ввод endpoint/token больше не используется; предложи получить одноразовый код в Профиль → Устройства.
- `doctor` → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py"` — health-check всей установки одним прогоном.
- `test` → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/test_uplink.py"` — end-to-end тест на моке одной командой (поднимает мок → прогон → проверка приёма → идемпотентность → гасит мок).
- `register <lsc_…>` → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/register.py" "<lsc_…>"` — одноразовая привязка к платформе; token сохраняется локально и не выводится.

Вывод команды передай пользователю кратко, без пересказа очевидного. Если конфиг отсутствует — первый запуск `--status` создаст его с дефолтами (мок-эндпоинт), скажи об этом.
