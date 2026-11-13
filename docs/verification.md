# Проверки реализации

Проверки выполнены 12 ноября 2026, Polza не вызывался: локально используется fake.

- 40 тестов кодгена: scaffolding, строгая схема service.yaml, ENV isolation,
  детерминированный runtime wheel, ownership generated, gRPC server/client/health,
  Alembic SQLite upgrade/downgrade, OTLP signals и trace context, app/nginx, local run.
- 12 тестов приложения: все 16 режимов и 118 заданий, жизненный цикл комнаты,
  приватность ответов, голосование/очки/способности, fake и mock Polza/CDN/errors.
- PostgreSQL/S3: миграции, изоляция комнат и изображений, backend → llm, idempotency,
  рестарт с сохранением состояния, восстановление очереди, запрет повторной оплаты
  при неизвестном результате отправки, graceful shutdown и отсутствие секретов в generated.
- Observability: настоящий Collector/Loki/Prometheus/Tempo/Grafana; проверено наличие
  логов, HTTP-метрик и трасс через API источников Grafana.
- Контейнеры: три образа, `codegen run --no-build --port-offset 10000`, readiness,
  HTTP API через nginx и S3 с fake-провайдером. UI проверен в Chrome (1440px и 390px).
- Отдельный KV smoke кодгена: Valkey ACL, разные пользователи, запись/чтение,
  запрет чужих ключей, сохранение данных после рестарта.

Машиночитаемые результаты: [native](verification/banger-local-proof.json),
[observability](verification/banger-observability-proof.json),
[containers API](verification/container-api-proof.json),
[containers browser](verification/container-browser-proof.json).
Скриншоты: [TV](verification/television.png), [контроллер](verification/controller.png).

## Воспроизведение

```sh
python scripts/test.py
python test/smoke_local.py --project . --observability
python test/smoke_containers.py --url http://127.0.0.1:18080 --llm-url http://127.0.0.1:18001
python test/browser_smoke.py --url http://127.0.0.1:18080 --output /tmp/banger-browser
```

`smoke_local.py` создает временную копию, выбирает свободные порты и удаляет свои
контейнеры/тома после проверки. Native зависимости приложения должны быть установлены.
Для browser smoke дополнительно нужен Playwright; Chrome задается через CHROME_PATH,
на macOS системный Chrome находится автоматически. Проверки никогда не запускают prod.
Внешний Polza API проверен mock-ответами, реальная платная генерация не тестировалась.
Публикация в registry, VPS deploy и доставка dynamic config выполняются отдельно платформой.

Финальная проверка установленного wheel 0.2.0.dev2 в основных репозиториях:
[полный native+observability](verification/installed-local.json),
[контейнерный API](verification/installed-containers-api.json),
[браузер](verification/installed-containers-browser.json),
[регенерация и отсутствие секретов](verification/regeneration.json).
Контракт workload-token проверен по API платформы: refresh, ротация endpoints,
ограничение приватными адресами и допустимыми OTLP routes.

[Проверка Valkey установленным CLI](verification/kv.json).

## Контрактные серверы: 0.2.0.dev3

HTTP и gRPC находятся в service.server. Config-классы вынесены в schemas/llm/config.yaml;
local/platform logging имеют независимые уровни. HTTP API Banger реализуют абстрактные
делегаты generated.http.HTTPService, без ручных маршрутов. OpenAPI остается источником
моделей и маршрутов, /openapi.json отдает исходную спецификацию.

37 тестов CLI и 8 приложения прошли. Новые тесты проверяют inline/nested модели,
allOf, имена Request/Response, typed path/query/header/cookie, multipart, бинарные ответы,
валидацию response, абстрактные/ошибочные делегаты, внешний config и независимые log levels.
Все три образа пересобраны, контейнеры готовы на 18000/18001/18080.

[Native + observability](verification/http-contract-installed-smoke-proof.json),
[контейнерный API](verification/http-contract-container-api-proof.json),
[браузер](verification/http-contract-browser-proof.json),
[регенерация](verification/http-contract-regeneration-proof.json).

## Ресурсные API и сквозная телеметрия: 0.2.0.dev4

Исходники находятся непосредственно в services/<id>/src; пакеты с повторением имени
сервиса удалены. HTTP контракты и реализации разбиты на ресурсы и подресурсы в api/.
Корневой backend OpenAPI — 92 строки, с локальными $ref на paths/*.yaml и models.yaml.
GameRoom — 119 строк, правила вынесены в membership/rounds/answers/scoring/bots/views.
Каталог 16 режимов и 118 заданий находится в game/data/modes.json.

40 тестов кодгена и 8 приложения прошли. Проверены ресурс People/подресурс PeopleFriends,
многосоставные и рекурсивные локальные $ref, состав делегатов, W3C carrier и приватность
ошибок/labels. Новые миграции 0002_trace_context сохраняют trace context durable заданий.

Tempo подтвердил одну заданную ingress-трассу через backend/outbox/llm/S3. Проверено
восстановление заданий после рестарта, JSONB carrier и метрики операций. Через Grafana
проверены gauges комнат/очередей, счётчики операций и histogram размеров S3. Через nginx
проверены входящий traceparent и возвращаемый X-Trace-Id; браузерный сценарий прошёл.
Регенерация сохранила 52 бизнес-файла и побайтно воспроизвела 52 generated-файла.

[Полный цикл и tracing](verification/resources-installed-trace-proof.json),
[контейнеры/ingress](verification/resources-container-proof.json),
[браузер](verification/resources-browser-proof.json),
[регенерация](verification/resources-regeneration-proof.json),
[Prometheus](verification/resources-prometheus-proof.json).

## Независимые DTO ручек: 0.2.0.dev5

Общих generated/api/models.py, clients/<service>_models.py и schemas/*/models.yaml нет.
Каждая операция имеет свой модуль Request/Response и вложенных типов, даже при совпадении
полей. В серверном модуле рядом находится HTTP binding, в клиентском — функция вызова.
Ресурсные классы Rooms/ImageJobs сохраняются. OpenAPI схемы input/output описаны inline
в requestBody/responses соответствующей ручки, PathItem-файлы разбиты по ресурсам.
Корневой backend api.yaml — 21 строка.

40 тестов CLI и 8 приложения прошли. Тест изоляции подтверждает разные классы одинаковых
по полям моделей и отсутствие побайтных изменений соседней операции при правке ответа.
Проверены сервер и клиент, рекурсивные модели, nested optional/default поля, полный
native+observability цикл и контейнеры/nginx/Chrome.

[Интеграция и трассы](verification/endpoint-dtos-installed-smoke-proof.json),
[контейнеры](verification/endpoint-dtos-container-proof.json),
[браузер](verification/endpoint-dtos-browser-proof.json),
[детерминированная регенерация](verification/endpoint-dtos-regeneration-proof.json).

## Игровой каталог в БД

Миграция 0003_catalog создает game_modes/game_prompts/game_powers. Скрипт scripts/seed.py
валидирует начальные данные и выполняет атомарный upsert. Реальный PostgreSQL заполнен
16 режимами, 118 заданиями, 5 способностями. Повторный seed не создает дубликатов.
Данные больше не читаются из src/game/data/modes.json; seed JSON живет только в scripts/seeds.
Backend загружает GameCatalog из PostgreSQL на старте, домен получает снимок явно.

12 тестов приложения прошли, включая идемпотентность/обновление, дополнительные записи,
отказ на пустом каталоге и rollback при ошибке. Интеграционный тест после заполнения
убирает seed-файл и проверяет startup, игру и рестарт без него. Сохранены llm/S3/trace/metrics.
Образ backend не содержит seed JSON. Контейнерный API-сценарий прошел.

[БД и build context](verification/database-catalog.json),
[полный цикл](verification/database-catalog-integration.json),
[контейнеры](verification/database-catalog-containers.json).
