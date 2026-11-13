# Сервисы

| Сервис | API | Клиенты | Хранилища |
| --- | --- | --- | --- |
| backend | HTTP 8000 | llm | PostgreSQL game, S3 |
| llm | HTTP 8001 | Polza (в prod) | PostgreSQL llm, S3 |
| frontend | nginx 8080 | браузер обращается к /api/ через ingress | — |

Домен `GameRoom` не зависит от HTTP/SQL/S3. Он управляет составом игроков, лидером,
режимами, раундами, таймерами, ботами, ответами, голосами и очками. Каталог перенесен
из исходного приложения. Состояние сохраняется в JSONB с блокировкой строки комнаты;
параллельные команды сериализуются транзакцией. Приватные ответы скрываются до reveal.
Классы ресурсов в src/api/ реализуют отдельные контракты generated/api/ и передают команды
бизнес-сервисам. Маршруты, параметры и модели генерируются из schemas/*/api.yaml;
/openapi.json возвращает написанную вручную спецификацию.

Генерация изображений идет через durable outbox backend и типизированный клиент llm.
Запрос получает стабильный idempotency key, повторная отправка не создает второе задание.
LLM хранит provider/model, статус, lease и внешний operation ID. При неоднозначном
результате платной отправки задача становится `needs_reconciliation`: автоматической
повторной оплаты нет. Перезапуск восстанавливает очередь. Fake создает валидный PNG
без внешнего API. Polza проверяет ответы и изображения; ключ не отправляется на CDN.

Изображения хранятся в S3; backend проверяет тип/размер и принадлежность загрузки комнате.
Миграции явные и независимы от изменяемых runtime metadata.
Один процесс на сервис — локальная конфигурация по умолчанию. Lease/row locks защищают
воркеры, но распределенный deploy/rolling update отдельно не сертифицирован.

Секреты поступают только через ENV на старте. В `service.yaml` secrets нет.
Локальные пулы раздельные; platform bindings разрешает платформа. Prod Polza key пока null.
Observability подключает локальный файл и OTLP: логи, трассы и метрики. Scheduler выключен;
игровые timer/outbox задачи запускаются lifecycle приложения и завершаются до ресурсов.

Фронтенд раздаёт статику и SPA через собственный Nginx. Входной Nginx
маршрутизирует `/` на frontend и `/api/` на backend. Маршруты описаны
в `ingress.yaml`, а число инстансов и размещение в `deploy.yaml`.
Локальный ingress слушает 80 на loopback. Публичный домен в примере нужно
заменить перед включением prod.

## Динамический конфиг LLM

В `services/llm/service.yaml` задана ссылка config.schema на `schemas/llm/config.yaml`.
В этом файле объявлен `ImageGenerationConfig` с ключом `image-generation`.
Пример значений для публикации в динамический конфиг:

```yaml
provider: polza
base_url: https://polza.ai/api/v1
model: openai/gpt-image-1.5
```

`POLZA_API_KEY` поступает через ENV из секретницы платформы. При `provider: null`
используется `IMAGE_PROVIDER` из окружения (fake локально и в test, polza в prod).
`base_url` — HTTPS-адрес API, совместимого с Polza, до маршрута `/media`.
Провайдер, адрес и модель фиксируются при создании задания. Для старых заданий Polza
без сохраненного адреса используется прежняя настройка `IMAGE_PROVIDER_BASE_URL`
или ее значение по умолчанию. Сервис читает текущий снимок из `DynamicConfigStore`.
Платформа передает `PLATFORM_CONFIG_URL` (origin API), отдельный секрет
`PLATFORM_CONFIG_TOKEN` для сервиса и окружения и, при необходимости,
`PLATFORM_CONFIG_POLL_SECONDS`. Без этих настроек локальный запуск использует defaults.

Токен Polza отправляется только на доверенный HTTPS origin. Он берётся из
`POLZA_API_ORIGIN` либо из прежнего `IMAGE_PROVIDER_BASE_URL` (по умолчанию
`https://polza.ai`). Если другой провайдер принимает тот же протокол, задайте
его origin при запуске вместе с соответствующим секретом, а полный путь API
укажите в `base_url` динамического конфига.

HTTP/gRPC находятся в service.server. Независимые пороги логов задаются в
observability.logging.local.level (console/file) и platform.level (OTLP).

## Структура

В src нет пакета backend/llm: application.py, settings.py, service.py, persistence.py
и api/ находятся прямо в src. API-реализации разбиты по предметным ресурсам и подресурсам.
GameRoom — небольшой агрегат в game/room.py; правила разделены на membership, rounds,
answers, scoring, bots и views. Зависимость от HTTP/SQL/S3 в игровых правилах отсутствует.
Каталог режимов и заданий хранится в PostgreSQL и загружается скриптом scripts/seed.py.

## DTO каждой ручки

Схемы requestBody/responses объявлены непосредственно в PathItem-файлах
schemas/<service>/paths/<resource>/. Общих models.yaml и generated/api/models.py нет.
На сервере generated/api/<resource>/<operation>.py содержит локальные Request/Response,
вложенные DTO и HTTP binding; ресурсный contract.py импортирует эти типы.
У клиента clients/llm/create_image_job.py и get_image_job.py также разные типы Response.
Repository.public возвращает словарь данных; его преобразует в DTO конкретная ручка.

## Каталог БД

CatalogRepository загружает GameCatalog из PostgreSQL на startup. Этот снимок явно
передается в GameRoom; файловых/глобальных CATALOG/MODES/PROMPTS нет. Классы игрового
домена не обращаются к БД сами. Seed-файл находится в backend/src/game/catalog_seed.json, начальные
данные загружаются отдельно от миграции и запуска приложения. [Подробнее](catalog.md).
