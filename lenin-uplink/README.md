# lenin-uplink — плагин централизации сессий

Часть экосистемы Ленин. **Полный гайд по установке: [`INSTALL.md`](INSTALL.md).**
Health-check одной командой: `python3 scripts/doctor.py`.

Архитектурный принцип раздачи:
**ядро = данные владельца** (папка с CLAUDE.md / library / hot — личное, не
распространяется), **плагин = поведение** (хуки, команды, скрипты — ставится
и обновляется через маркетплейс). Этот плагин — первый в линии.

## Что делает

Раз в сутки отправляет **новые байты** сессионных файлов Claude Code
(`~/.claude/projects/**/*.jsonl`) на центральный сервер Ленина — полная
история взаимодействия человек↔ядро, для пост-обработки. Протокол и
требования к серверной ручке: `UPLINK_CONTRACT.md` (lenin-uplink/1).

Три триггера:

| Триггер | Механизм |
|---|---|
| ежедневно 08:10 | launchd `com.lenin.session-uplink` |
| Мак включили | тот же launchd, `RunAtLoad` |
| зашёл в Ленин, аплинка не было >24ч | SessionStart-хук плагина → фоновый прогон |

Инкрементально (byte-offset манифест, шлётся только новое), идемпотентно
(ретраи и дубли безвредны), самовосстанавливается (сервер — истина по
offset). Обкатано: heal/resync тесты, байт-в-байт сверка.

## Установка

Маркетплейс живёт в отдельном публичном репо `lenin-plugins` (чистое поведение,
без личных данных ядер). На любой Мак с доступом:

```
/plugin marketplace add https://github.com/nlarryelvis2-max/lenin-plugins.git
/plugin install lenin-uplink@lenin
/uplink install        # поставить launchd
/uplink setup          # endpoint / token / owner_id / core_id
```

Публичный репо — авторизация не нужна. (Для приватного форка: `gh auth login` (credential helper подхватит
git-операции) или SSH-ключ. Разработка плагина идёт в основном репо ядра;
переиздание маркетплейса — `./publish_plugins.sh` в корне основного репо.

Конфиг: `~/.claude/lenin_uplink/config.json`. Пока реального сервера нет —
дефолтный endpoint указывает на локальный мок (`scripts/uplink_mock_server.py`,
он же эталон поведения ручки для разработчика сервера).

## Команды

`/uplink` (= status) · `/uplink run` · `/uplink dry` · `/uplink install` · `/uplink setup` · `/uplink doctor`

## Этика (канон data-exchange-ethics)

Сырые транскрипты = personal_special. Плагин ставится на машины флота
**только с явным consent владельца ядра** — consent фиксируется при выдаче
токена. Отзыв: сервер помечает токен → 403; локально `enabled: false` в
конфиге выключает всё.

## Файлы

```
.claude-plugin/plugin.json      манифест
hooks/hooks.json                SessionStart-подхват
scripts/session_uplink.py       клиент (stdlib, один файл, позиционно-независим)
scripts/session_uplink_check.py проверка >24ч → фоновый прогон
scripts/uplink_mock_server.py   мок-ручка / эталон для серверной разработки
commands/uplink.md              слэш-команда /uplink
UPLINK_CONTRACT.md              контракт серверной ручки (передаётся на разработку)
```
