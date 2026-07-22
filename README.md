# Lenin Client

Публичный клиент для Claude Code, который создаёт личное ядро Ленина на
компьютере участника и, только после явного согласия, синхронизирует новые
байты сессий с приватной платформой [lenin.nglain.com](https://lenin.nglain.com).

Клиент не содержит аккаунтов, токенов, проектных данных или памяти других
пользователей. Приватная платформа и публичный клиент развиваются отдельно.

## Установка

1. Войти в приватную платформу.
2. Открыть **Профиль → Lenin Client**.
3. Подтвердить передачу сырых сессий и получить одноразовый код.
4. В Claude Code выполнить:

```text
/plugin marketplace add nlarryelvis2-max/lenin-plugins
/plugin install lenin-client@lenin
/reload-plugins
/lenin-client:setup <одноразовый код>
```

Код действует 10 минут и используется один раз. Платформа возвращает Uplink
token напрямую локальному скрипту. Token сохраняется в
`~/.claude/lenin_uplink/config.json` с правами `0600` и никогда не печатается.

Проверка после установки:

```text
/lenin-client:status
```

## Состав

`Lenin Client` — одна устанавливаемая поверхность поверх двух внутренних
компонентов. Код не копируется.

```text
lenin-client
├── lenin-core    личное ядро, память, навыки и hooks
└── lenin-uplink  инкрементальная доставка сессий и heartbeat
```

- `lenin-core` разворачивает личное ядро в `~/.claude/lenin-kernel`.
- `lenin-uplink` отправляет только новые полные JSONL-строки из
  `~/.claude/projects/**/*.jsonl`.
- launchd запускает Uplink ежедневно и при включении Mac.
- SessionStart страхует пропущенный sync, если последний успешный запуск был
  больше 24 часов назад.
- Пустой heartbeat сообщает платформе версии Client/Core/Uplink и состояние
  устройства, даже если новых строк нет.

## Граница приватности

Сырые сессии являются приватным архивом пользователя:

- они не становятся памятью автоматически;
- не относятся к проекту без явной привязки;
- не передаются другим участникам проекта;
- token write-only и не даёт читать архив;
- доступ можно отозвать на платформе;
- отключение `enabled: false` останавливает локальную отправку.

Публикация дистиллированного знания в проект — отдельный серверный процесс и не
является частью Uplink.

## Версии

| Поверхность | Версия |
|---|---:|
| `lenin-client` | 0.1.0 |
| `lenin-core` | 0.1.5 |
| `lenin-uplink` | 1.1.3 |
| протокол | `lenin-uplink/1` |

Явные версии обновляются при каждом релизе. История изменений:
[`CHANGELOG.md`](CHANGELOG.md).

## Для разработчика

```bash
claude plugin validate .
python3 -m unittest discover -s lenin-uplink/scripts -p 'test_*.py' -v
```

Документы:

- [`lenin-core/README.md`](lenin-core/README.md)
- [`lenin-uplink/README.md`](lenin-uplink/README.md)
- [`lenin-uplink/UPLINK_CONTRACT.md`](lenin-uplink/UPLINK_CONTRACT.md)
- [`lenin-uplink/PLATFORM_INTEGRATION.md`](lenin-uplink/PLATFORM_INTEGRATION.md)

## Совместимость

Старые установки `lenin-core@lenin` и `lenin-uplink@lenin` продолжают работать.
Новые участники устанавливают только `lenin-client@lenin`.
