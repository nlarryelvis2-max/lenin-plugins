---
description: "Проверить состояние Lenin Client"
allowed-tools: ["Bash"]
---

Проверь оба компонента Lenin Client и кратко объясни результат:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lenin-core/scripts/doctor.py"
python3 "${CLAUDE_PLUGIN_ROOT}/lenin-uplink/scripts/doctor.py"
python3 "${CLAUDE_PLUGIN_ROOT}/client/scripts/projects.py" status
```

Если project access ещё не подключён, назови это отдельным необязательным
шагом, а не поломкой Core/Uplink. Не показывай token, содержимое сырых сессий
или приватную память.
