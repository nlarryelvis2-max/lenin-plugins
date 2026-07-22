# Интеграция lenin.nglain.com ↔ плагин lenin-uplink

**Запрос на донастройку платформы** (для агента-разработчика `lenin.nglain.com`).
Дата: 2026-07-22 · Версия: 1 · Контракт аплинка: [`UPLINK_CONTRACT.md`](UPLINK_CONTRACT.md)

## Контекст

Есть клиентский плагин `lenin-uplink` (публичный, ставится командой
`/plugin install`). Он ежедневно шлёт новые байты сессионных файлов Claude Code
(`~/.claude/projects/**/*.jsonl`) на сервер по протоколу `lenin-uplink/1`.
Сейчас endpoint = локальный мок. Нужно, чтобы **платформа стала реальным
приёмником** и автоматизировала онбординг: юзер ставит плагин → `/lenin setup` →
платформа сама создаёт юзера и выписывает токен → синк работает без ручных шагов.

## Целевой flow (end-to-end, под ключ)

```
1. Юзер: /plugin install lenin-core@lenin + lenin-uplink@lenin
2. Юзер: /lenin setup   (спрашивает имя + профиль)
3. Плагин: POST https://lenin.nglain.com/api/uplink/register
           {owner_name, core_id, machine_id}
4. Платформа: создаёт user (owner_id), генерит token, возвращает:
              {owner_id, token, endpoint}
5. Плагин: пишет token+owner_id+endpoint в ~/.claude/lenin_uplink/config.json
6. launchd (уже стоит) ежедневно шлёт сессии → POST {endpoint} → платформа принимает
```

Шаги 3–5 — **новые** (сейчас юзер вписывает token вручную через `/uplink setup`).
Авто-регистрация делает онбординг бесшовным.

## Что платформе реализовать

### Endpoint 1 — `POST /api/uplink/register` (НОВЫЙ, онбординг)

Создаёт юзера + выписывает токен. Вызывается плагином один раз при `/lenin setup`.

**Запрос:**
```json
POST https://lenin.nglain.com/api/uplink/register
Content-Type: application/json
{ "owner_name": "<имя юзера>",
  "core_id": "lenin-core",
  "machine_id": "<LocalHostName>",
  "profile": "psych|cfo|ops|builder|designer|athlete" }
```

**Ответ 200:**
```json
{ "owner_id": "<платформенный id, напр. usr_abc123>",
  "token": "< bearer-токен, long-lived, скоуп = (owner, core) >",
  "endpoint": "https://lenin.nglain.com/v1/uplink/sessions" }
```

Логика:
- `owner_name` → человекочитаемое, не id. Платформа генерит `owner_id` (stable, UUID/slug).
- Один owner × много machines = один token (машины различаются по `machine_id` в заголовках).
- Token хранится хэшированным (как пароль). При потере — перевыпуск через UI платформы.
- Идемпотентность: повторный register с тем же `owner_name`+`machine_id` → вернуть
  существующий token (или 409 + инструкция перевыпуска). Решить политику.
- Rate-limit: жёстко (1 register/мин с IP) — публичный endpoint.

### Endpoint 2 — `POST /v1/uplink/sessions` (ПРИЁМ, по контракту)

Полная спека в [`UPLINK_CONTRACT.md`](UPLINK_CONTRACT.md). Кратко:

```json
POST https://lenin.nglain.com/v1/uplink/sessions
Authorization: Bearer <token>
Content-Type: application/json · Content-Encoding: gzip
X-Uplink-Proto: 1 · X-Owner-Id · X-Core-Id · X-Machine-Id

{ "proto":"lenin-uplink/1", "owner_id", "core_id", "machine_id", "sent_at",
  "chunks":[ {"path","offset","length","sha256","b64"} ] }
```

**Ответ 200:** `{ "accepted": true, "files": { "<path>": <next_offset> } }`
`next_offset` — сколько байт файла сервер теперь имеет (одно поле закрывает
append/дубль/дыру — см. §4 контракта).

Обязательно (чек-лист контракта §10):
- Bearer-auth: `token → (owner_id, core_id)`. Заголовки декларативны, истина в токене.
- Отклонять абсолютные пути и `..` в `path` (path traversal).
- Проверка `sha256` чанка → `400` при несовпадении, offset не двигать.
- Append-only хранение: `<owner_id>/<machine_id>/<path>`, байт-в-байт.
- Журнал приёмов (когда/кто/сколько).
- Revocation: помеченный token → `403`.

### Endpoint 3 — `GET /v1/uplink/health` (опц., мониторинг)

```json
GET https://lenin.nglain.com/v1/uplink/health
→ { "status": "ok", "proto": "lenin-uplink/1", "uptime_s": 12345 }
```

## Безопасность

- **Только TLS** на реальном сервере (мок — localhost).
- Token = secret. Хранится у юзера в `~/.claude/lenin_uplink/config.json` (chmod 600).
- Ручка **write-only** (GET сессий нет — утёкший token не даёт прочитать чужое).
- Revocation (right to erasure / GDPR Art.17): платформа умеет отозвать token → `403`.
  Плагин при `403` выставляет `enabled: false` (сейчас вручную, v2 — авто).
- Сессии = personal_special (там личное юзеров). По канону data-exchange-ethics:
  платформа = хранилище для самого юзера, доступ к его данным — только его.

## Что доработать в плагине (на стороне lenin-uplink)

Чтобы `/lenin setup` делал шаги 3–5 автоматически:

1. **`scripts/register.py`** (новый) — `POST /api/uplink/register` →
   пишет `token`/`owner_id`/`endpoint` в `config.json`.
2. **`commands/uplink.md`** — добавить `/uplink register` (и вызов из setup).
3. **`scripts/setup.py`** (lenin-core) — после развёртывания ядра, если uplink
   установлен И endpoint = мок (не настроен) → вызвать `register.py` авто.
4. **`scripts/session_uplink.py`** — при `403` от сервера → `enabled: false` (auto-disable).

> Доработку плагина делаю по готовности endpoints на платформе. Контракт
> (`UPLINK_CONTRACT.md`) и мок-эталон (`uplink_mock_server.py`) уже есть —
> реальная ручка должна проходить тот же прогон: `python3 test_uplink.py`.

## Чек-лист для агента платформы

- [ ] `POST /api/uplink/register` — создать user, выдать token (hashed), rate-limit.
- [ ] `POST /v1/uplink/sessions` — gzip-тело, Bearer-auth, append по правилу 3 случаев
      (§4 контракта), ответ `{accepted, files:{path:next_offset}}`.
- [ ] sha256-проверка чанков.
- [ ] Отклонение абсолютных путей / `..`.
- [ ] Append-only хранилище `<owner>/<machine>/<path>`.
- [ ] Журнал приёмов.
- [ ] Revocation → `403`.
- [ ] (опц.) `GET /v1/uplink/health`.
- [ ] Прогон `test_uplink.py` против реального endpoint (скиньте URL+test-token —
      проверю интеграцию вживую).

## Согласование

- Скиньте URL платформы + test-token → я прогоню `test_uplink.py` и
  `/uplink register` против реального сервера, выловлю расхождения.
- После того как register заработает — дорабатываю плагин (register.py, авто-вызов
  из `/lenin setup`) → онбординг становится полностью бесшовным.

---

# Страница установки + раздача маркетплейса (фронтенд платформы)

Плагин собран и публично доступен. Чтобы юзер ставил с **платформы** (а не
искал GitHub), нужен UX-гайд на `lenin.nglain.com` + (опц.) раздача маркетплейса.

## 1. Страница «Поставить Ленин» (готовый контент-блок)

Где-то в UI: `/install` или кнопка в хедере. Контент можно копировать:

```
# Поставить Ленин — цифровое второе Я
Предпосылки: Claude Code, macOS/Linux, python3 ≥ 3.8.

В Claude Code выполни:
  /plugin marketplace add <MARKETPLACE_URL>
  /plugin install lenin-core@lenin       ← сам Ленин (14D, атомы, память)
  /plugin install lenin-uplink@lenin     ← синк сессий сюда (опционально)

Перезапусти Claude Code, затем:
  /lenin setup                           ← онбординг: имя + профиль, разворачивает ядро

Готово. /lenin setup создаст твоё ядро и (если стоит uplink) настроит синк.
Проверка: /uplink test, /lenin.
```

## 2. Откуда `<MARKETPLACE_URL>` (развилка)

| Опция | URL | Что нужно платформе |
|---|---|---|
| **A. Раздача с платформы** (рекомендую, брендинг) | `https://lenin.nglain.com/plugins` | Раздавать `marketplace.json` + файлы плагинов по HTTP. Источник = git-репо `lenin-plugins` (cron-pull/webhook). Claude Code `marketplace add` поддерживает HTTP-URL на каталог с `.claude-plugin/marketplace.json`. |
| **B. Прямая GitHub-ссылка** (проще, уже работает) | `https://github.com/nlarryelvis2-max/lenin-plugins.git` | Ничего. Минус: юзер видит GitHub, не платформу. |

## 3. (После register) Кнопка «Создать аккаунт»

Когда `POST /api/uplink/register` готов — страница либо ведёт юзера на `/lenin setup`
(плагин сам зарегистрирует — **бесшовно**), либо создаёт аккаунт в UI и показывает
token для ручного ввода. Рекомендую первый вариант.

## Что есть готового (переиспользовать)

- `INSTALL.md` — полный пошаговый гайд.
- `README.md` — краткое описание плагинов.
- `marketplace.json` — готовый манифест (для опции A).
- `UPLINK_CONTRACT.md` — контракт ручки (backend).
- `PLATFORM_INTEGRATION.md` (этот файл) — всё в одном для агента платформы.

## Чек-лист для фронтенда

- [ ] Страница «Поставить Ленин» с контентом выше.
- [ ] Решить: опция A (раздача с платформы) или B (GitHub-ссылка).
- [ ] Если A — раздавать `marketplace.json` + файлы (статика из git-репо).
- [ ] (После register) — авто-аккаунт через `/lenin setup`.
