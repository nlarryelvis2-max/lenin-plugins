# Установка Lenin Client

## Требования

- актуальный Claude Code;
- macOS;
- Python 3.8+;
- аккаунт на приватной платформе Lenin.

## Основной путь

В платформе откройте **Профиль → Lenin Client**, подтвердите consent и получите
одноразовый код. Затем в Claude Code:

```text
/plugin marketplace add nlarryelvis2-max/lenin-plugins
/plugin install lenin-client@lenin
/reload-plugins
/lenin-client:setup <одноразовый код>
```

Проверка:

```text
/lenin-client:status
```

Успешная установка сразу отправляет пустой heartbeat. Владелец платформы видит
устройство, версии и время sync во вкладке **Команда**.

## Переподключение

Получите новый код в профиле и выполните:

```text
/lenin-client:uplink register <новый код>
```

Код и прежний token не восстанавливаются. При отзыве доступа требуется новое
подключение.

## Отключение

Установите `enabled: false` в `~/.claude/lenin_uplink/config.json` или удалите
клиент:

```text
/plugin uninstall lenin-client@lenin
```

Удаление клиента не удаляет уже переданный приватный архив. Его жизненный цикл
управляется на платформе.
