# Ленин — экосистема плагинов цифрового второго Я

Маркетплейс плагинов `lenin` для Claude Code. Превращает Claude в персональное
цифровое второе Я — собеседника и библиотекаря, который помнит, мыслит в 14
измерениях и централизует историю взаимодействия.

```
/plugin marketplace add https://github.com/nlarryelvis2-max/lenin-plugins.git
```

## Ценность

**До:** Ленин как второе Я жил одной папкой ядра — поведение (хуки, движки,
правила) и данные владельца (память, люди, проекты) вперемешку. Раздача = ручное
копирование папки; поделиться — значит отдать всё личное.

**После:** модульная раздача. **Поведение отделено от данных.** Человек ставит
плагин с платформы одной командой → получает рабочее второе Я (14D-движок, атомы,
память-как-механизм) → наполняет **своими** данными. Личное создателя не переезжает.

| Что | Было | Стало |
|---|---|---|
| Раздача ядра | ручное копирование папки | `/plugin install` с платформы |
| Поведение vs данные | вперемешку | разделены (плагин ≠ данные) |
| Онбординг | ручная настройка хуков/путей | `/lenin setup` под ключ |
| Синк истории | нет | автосинк сессий на сервер (launchd) |
| Память нового юзера | нет | с нуля, наполняет собой |

## Архитектура

**Принцип:** *ядро = данные владельца* (личное, НЕ раздаётся), *плагин = поведение*
(раздаётся через маркетплейс).

```
маркетплейс «lenin» (этот репо, публичный)
├── lenin-core        ← само второе Я: 14D-движок, атомы, Lean, память, онбординг
└── lenin-uplink      ← ежедневный синк сессий на сервер (protocol lenin-uplink/1)

        ↓ ставит плагин                      ↑ сессии текут (uplink)
┌─ машина юзера ─────────────────────┐    ┌─ платформа lenin.nglain.com ─────────┐
│ ~/.claude/lenin-kernel/  (ядро)    │    │ register → token → owner_id           │
│   CLAUDE.md, MEMORY.md, hot/,      │    │ POST /v1/uplink/sessions (приём)      │
│   library/  ← данные юзера         │    │ пост-обработка / дашборд              │
│ ~/.claude/lenin/ (onboarding-conf) │    └───────────────────────────────────────┘
│ ~/.claude/lenin_uplink/ (config)   │
└────────────────────────────────────┘
```

Два независимых плагина: можно поставить только core (Ленин без синка) или оба.

### lenin-core — поведение второго Я
- **14D-движок:** профиль из observations → веса E·C·S·P·Ph·T·X·M·N·A·R·I·L·G на
  старте сессии. Источник весов — observations (пишет сам Ленин), не хуки.
- **12 атомов:** линзы зрения (curiosity, verifier, therapist, builder…),
  сигналят активные углы на каждый промпт.
- **Гейты:** forcing-члены — read-before-infer, факт≠гипотеза.
- **Lean-канон:** формализация T1/T★/T2-T8 (free energy, posterior convergence).
- **Память = механизм + пустые полки:** CLAUDE.md, MEMORY.md, hot/, library/.
  **Данные создателя не входят** — каждый наполняет собой.
- **Контекст через hooks** (не `plugin/CLAUDE.md` — его нет по доке Anthropic):
  `identity_context.py` инжектит ядро Ленина в `additionalContext` при старте.
- **Единое ядро (user scope):** фиксированная папка → второе Я через все проекты,
  память не фрагментируется.

### lenin-uplink — централизация истории
- **Ежедневный синк** новых байт `~/.claude/projects/**/*.jsonl` на сервер
  (launchd 08:10 + при включении + SessionStart-подхват >24ч).
- **Инкрементально** (byte-offset манифест), **идемпотентно** (ретраи безвредны),
  **самовосстанавливается** (сервер — истина по offset).
- Контракт: [`lenin-uplink/UPLINK_CONTRACT.md`](lenin-uplink/UPLINK_CONTRACT.md).
- `/uplink test` — e2e проверка на моке одной командой.

## Установка (под ключ)

```
/plugin marketplace add https://github.com/nlarryelvis2-max/lenin-plugins.git
/plugin install lenin-core@lenin
/plugin install lenin-uplink@lenin     # опционально (синк)
(перезапустить Claude Code)
/lenin setup                            # онбординг: имя + профиль → ядро + launchd
```

`/lenin setup` одной командой: создаёт onboarding-конфиг → разворачивает ядро →
ставит launchd для синка (если uplink стоит). После — открыть Claude Code в папке
ядра, Ленин живой.

## Состояние

| Плагин | Версия | Статус |
|---|---|---|
| `lenin-core` | 0.1.4 | ✅ готов (9 движков, 7 skills, Lean-канон, templates, онбординг + анкета) |
| `lenin-uplink` | 1.1.2 | ✅ готов (device-flow register + PKCE, refresh, revoke, `/uplink test`, doctor) |

**Готово (клиент, полностью):** оба плагина + device-flow онбординг (RFC 8628 + PKCE)
+ refresh-token + revoke + контракт аплинк + ТЗ платформы (backend + фронтенд).
**В работе (платформа):** `lenin.nglain.com` — реализация 6 endpoint'ов из
`PLATFORM_INTEGRATION.md` (device/code, device/token, uplink/sessions, refresh,
revoke, health) + страница `/device` + страница установки. Это единственный
блокер end-to-end. Когда скинут URL+test-token — интеграционный тест вживую.

## Документация

- [`lenin-core/README.md`](lenin-core/README.md), [`lenin-core/INSTALL.md`](lenin-core/INSTALL.md) — ядро.
- [`lenin-uplink/README.md`](lenin-uplink/README.md), [`lenin-uplink/INSTALL.md`](lenin-uplink/INSTALL.md) — аплинк.
- [`lenin-uplink/UPLINK_CONTRACT.md`](lenin-uplink/UPLINK_CONTRACT.md) — контракт серверной ручки.
- [`lenin-uplink/PLATFORM_INTEGRATION.md`](lenin-uplink/PLATFORM_INTEGRATION.md) — ТЗ платформы (backend + фронтенд).

## Этика

Сырые сессии = personal_special (личное юзеров). Раздача ядра флоту — только с
явным consent владельца. Память создателя не входит в плагины. Отзыв токена →
`403` → синк стоп. Канон: `data-exchange-ethics`.

## Принцип раздачи

Разработка идёт в основном репо ядра (тут). Публикация маркетплейса —
`./publish_plugins.sh` (git subtree split → push в публичный репо `lenin-plugins`).
Один источник правды, зеркало для раздачи, история плагинов сохранена.
