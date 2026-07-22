# lenin-core — ядро Ленина (цифровое второе Я)

Плагин поведения: 14D-движок, атомные линзы, Lean-формализация (T★/FEP),
память (механизм + пустые полки), онбординг. **Без личных данных владельца** —
каждый наполняет ядро собой.

Для новых установок ядро входит в единый публичный пакет `lenin-client` вместе
с Uplink. Отдельный `lenin-core` оставлен для совместимости.

## Что делает

- **14D-веса** — на старте сессии движок считает профиль (из observations) и
  подсказывает фокус/слепые зоны. Источник весов — observations.md, который
  наполняет сам Ленин в работе.
- **Атомы** — 12 линз (curiosity, memory, verifier, therapist, …) сигналят
  активные углы зрения на каждый промпт.
- **Гейты** — forcing-члены: read-before-infer (slow_read), факт≠гипотеза (verify).
- **Lean-канон** — формализация T1/T★/T2-T8 (free energy, posterior convergence).
- **Память** — ритуал сессии + шаблоны (CLAUDE.md, MEMORY.md, hot/, library/).

## Установка

Полный гайд: [`INSTALL.md`](INSTALL.md). Кратко:

```bash
claude plugin marketplace add nlarryelvis2-max/lenin-plugins && claude plugin install lenin-client@lenin
```

Затем открыть новую сессию Claude Code и выполнить `/lenin-client:setup`.
Приватная синхронизация подключается позже одноразовым кодом из платформы и не
нужна для работы личного ядра.

## Файлы

```
hooks/           9 движков + identity_context + _paths (все через CLAUDE_PLUGIN_ROOT)
skills/          7 базовых правил (атомы, позы, trust, …) — модель вызывает по контексту
lean/            формализация T1-T8 + T★ + lakefile
templates/       скелеты ядра (CLAUDE.md, MEMORY.md, hot/, library/)
commands/        /lenin (status), /lenin setup (онбординг)
scripts/         setup.py (онбординг), doctor.py (health-check)
```

## Принцип

**Ядро = данные владельца (личное, не раздаётся). Плагин = поведение (раздаётся).**
Память создателя НЕ входит — у каждого владельца своя, с нуля.

## Онбординг-профили

Setup спросит тип: psych / cfo / ops / builder / designer / athlete.
От профиля зависит язык Ленина (метафоры, глубина, тон).
