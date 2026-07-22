# Lenin Client ↔ приватная платформа

Актуальный onboarding contract. Клиент публичный; платформа, пользователи,
проекты, токены и сырые сессии приватны.

## Поток подключения

```text
1. Пользователь входит в платформу.
2. Меню профиля → **Установить Ленина** → consent → одноразовый lsc_… код.
3. Пользователь устанавливает lenin-client@lenin.
4. /lenin-client:setup <код>
5. POST /api/uplink/register { code, machine_id }
6. Платформа атомарно погашает код и возвращает token + identity + endpoint.
7. Клиент сохраняет token с mode 0600 и отправляет пустой heartbeat.
8. Платформа показывает устройство, версии и последний успешный sync.
```

Владельцы платформы не выпускают постоянный token от имени другого человека.
Consent подтверждает сам пользователь в своей авторизованной сессии.

## Регистрация

```http
POST /api/uplink/register
Content-Type: application/json

{
  "code": "lsc_…",
  "machine_id": "Felix-Mac"
}
```

Успех `201`:

```json
{
  "owner_id": "felix",
  "core_id": "lenin-felix-mac-…",
  "machine_id": "Felix-Mac",
  "token": "lu1_…",
  "sessions_endpoint": "/v1/uplink/sessions",
  "protocol": "lenin-uplink/1"
}
```

Код короткоживущий, одноразовый, хранится на сервере только как SHA-256 и
привязан к пользователю, который дал consent.

## Heartbeat и сессии

`POST /v1/uplink/sessions` принимает тот же gzip JSON как для данных, так и для
пустого heartbeat. Структурированная информация клиента передаётся additively:

```json
{
  "proto": "lenin-uplink/1",
  "client": {
    "name": "lenin-client",
    "version": "0.1.1",
    "core_version": "0.1.5",
    "uplink_version": "1.1.4"
  },
  "chunks": []
}
```

Legacy-поле `lenin_version` сохраняется до обновления старых установок.

## Серверные состояния

- `not_connected` — нет погашенного кода и успешного heartbeat;
- `setup_issued` — одноразовый код выдан и ещё действует;
- `pending` — устройство зарегистрировано, heartbeat ещё не принят;
- `connected` — heartbeat/sync свежий;
- `stale` — активное устройство давно не синхронизировалось;
- `revoked` — доступ устройства отозван.

`not_connected` означает только отсутствие наблюдаемого клиента. Сервер не
утверждает, что `lenin-core` физически отсутствует на Mac.

## Граница данных

Приёмник хранит сырые сессии по пользователю и устройству. Uplink не назначает
их проектам и не публикует в знания. Project binding, дистилляция и публикация
являются отдельным серверным контуром с собственной авторизацией и provenance.
