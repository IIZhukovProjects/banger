# Локальная инфраструктура Banger

Генерация без запуска контейнеров из корня приложения:

```sh
codegen infra generate --mode local
```

Явный запуск/остановка:

```sh
codegen infra up --mode local
codegen infra status --mode local
codegen infra down --mode local
```

`infrastructure/` и `.local/` исключены из Git и Docker context.
Compose, init-скрипты и конфиги observability лежат в infrastructure/.
Пароли сохраняются в .local/infrastructure/credentials.json, доступ Grafana —
в .local/infrastructure/admin.json. Пулы backend и llm независимы:
.local/secrets/backend.json и .local/secrets/llm.json. Каталоги имеют права 0700, файлы — 0600.
Повторная генерация сохраняет пароли; секретных значений в YAML приложения нет.

PostgreSQL 17 содержит banger_game и banger_llm, каждому сервису выдается собственный
пользователь и доступ только к назначенной БД. Общий приватный S3-бакет обслуживает
MinIO с отдельными учетными записями backend и llm. KV пока не используется.
Scheduler обоих сервисов выключен.

Локальный observability включен: Grafana, Prometheus, Loki, Tempo, Collector.
OTLP принимает телеметрию с индивидуальной Basic-аутентификацией сервисов.
Порты заданы в infrastructure.modes.local.ports; доступны только через loopback:
PostgreSQL 15432, S3 19000, Grafana 13000, OTLP HTTP 14318 и gRPC 14317.
Полный поток телеметрии проверен через Grafana: Loki получил логи backend,
Prometheus — HTTP-метрики, Tempo — трассы межсервисных запросов.

Доступы к PostgreSQL, S3 и Collector определяются по `service.resources`.
Кодген подставляет их из пула соответствующего сервиса при запуске. Для контейнеров
используются внутренние адреса Docker. `environments/local.yaml` содержит прикладные
настройки. Пароли хранятся в приватных пулах.

`codegen infra generate --mode platform` формирует
`infrastructure/platform/requirements.json` для будущего деплоя.

Проверены PostgreSQL (парольный вход/изоляция/повторная настройка), S3 uploads и
генерации, восстановление заданий, graceful shutdown. Отдельный тест кодгена проверяет
Valkey: ACL пользователя на свой префикс, запрет чужих ключей и сохранение после рестарта.
KV поддерживается кодгеном, но в Banger выключен.

`down` сохраняет данные. Для удаления есть `down --volumes`.
