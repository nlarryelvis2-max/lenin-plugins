---
description: "Статус ядра Ленина"
allowed-tools: ["Bash"]
---

Покажи статус ядра Ленина. Выполни через Bash:

```
cat ~/.claude/lenin/config.json 2>/dev/null || echo "(конфига нет — запусти /lenin setup)"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" 2>/dev/null | tail -20
```

Кратко перескажи пользователю: кто владелец, профиль, развёрнуто ли ядро, живы ли хуки. Если конфига нет — предложи `/lenin setup`.
