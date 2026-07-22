# lenin-uplink

Внутренний компонент публичного `Lenin Client`. Инкрементально доставляет новые
байты Claude Code sessions в приватный архив пользователя по протоколу
`lenin-uplink/1`.

Новые пользователи устанавливают [`lenin-client@lenin`](../README.md). Отдельная
установка компонента оставлена для совместимости и диагностики.

## Свойства

- stdlib Python без внешних зависимостей;
- byte-offset manifest и идемпотентный append;
- только полные JSONL-строки;
- лимиты 8 МБ на chunk, 24 МБ на batch, 200 МБ на run;
- flock от параллельных запусков;
- launchd ежедневно в 08:10 и при включении Mac;
- SessionStart-подхват после 24 часов без успешного sync;
- пустой heartbeat с версиями Client/Core/Uplink;
- token в конфиге с mode `0600`.

## Команды

```text
/lenin-client:uplink status
/lenin-client:uplink run
/lenin-client:uplink dry
/lenin-client:uplink doctor
/lenin-client:uplink register <одноразовый код>
```

Одноразовый код получает сам пользователь в **Профиль → Lenin Client** приватной
платформы. Ручной ввод endpoint/token не используется.

Контракты:

- [`UPLINK_CONTRACT.md`](UPLINK_CONTRACT.md)
- [`PLATFORM_INTEGRATION.md`](PLATFORM_INTEGRATION.md)
