---
description: "Обновить Lenin Client без потери локальных данных"
allowed-tools: ["Bash"]
---

Обнови установленный Lenin Client штатным механизмом Claude Code:

```bash
claude plugin marketplace update lenin
claude plugin update lenin-client@lenin
```

Если обе команды завершились успешно, сообщи установленную версию из:

```bash
claude plugin list
```

Личное ядро, память, доступ к проектам в Keychain и настройки Uplink находятся
вне plugin cache и при обновлении не меняются. Не запускай setup повторно и не
переподключай проекты без отдельной причины.

Новая версия применяется после `/reload-plugins` или в новой сессии Claude
Code. После перезагрузки предложи проверить её командой
`/lenin-client:status`.
