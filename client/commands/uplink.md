---
description: "Управлять синхронизацией Lenin Client"
allowed-tools: ["Bash"]
---

Управляй Uplink. Аргумент пользователя: `$ARGUMENTS`.

- без аргумента или `status` → `python3 "${CLAUDE_PLUGIN_ROOT}/lenin-uplink/scripts/session_uplink.py" --status`
- `run` → `python3 "${CLAUDE_PLUGIN_ROOT}/lenin-uplink/scripts/session_uplink.py" --run`
- `dry` → `python3 "${CLAUDE_PLUGIN_ROOT}/lenin-uplink/scripts/session_uplink.py" --dry-run`
- `install` → `python3 "${CLAUDE_PLUGIN_ROOT}/lenin-uplink/scripts/session_uplink.py" --install-launchd`
- `doctor` → `python3 "${CLAUDE_PLUGIN_ROOT}/lenin-uplink/scripts/doctor.py"`
- `register <lsc_…>` → `python3 "${CLAUDE_PLUGIN_ROOT}/lenin-uplink/scripts/register.py" "<lsc_…>"`
- `disconnect` → `python3 "${CLAUDE_PLUGIN_ROOT}/lenin-uplink/scripts/revoke.py"`

Одноразовый код выдаёт приватная платформа в **Профиль → Lenin Client**. Никогда
не проси token и не выводи его из локального конфига. Перед `disconnect` коротко
уточни подтверждение: команда отзовёт доступ этого Mac, но не удалит уже принятый
приватный архив.
