# Banger

Пати-игра: телевизор показывает общую комнату, телефоны служат контроллерами.
16 режимов и 118 исходных заданий, ответы, голосование, очки и генерация изображений.

- `services/backend/src` — игровой домен, HTTP API, таймеры и durable outbox.
- `services/llm/src` — очередь генераций, fake/Polza, восстановление заданий, S3.
- `apps/frontend` — React/Vite и `app.yaml`; nginx генерируется кодгеном.
- `schemas` — OpenAPI-контракты; `generated/` воспроизводится, бизнес-код сохраняется.
- `application.yaml`, `infrastructure.yaml`, `environments/` — состав и зависимости.

## Запуск

Нужны Docker Compose 2.30+, Python 3.12 и закрепленный в `codegen.lock.yaml` CLI.
Из соседнего репозитория `codegen`:

```sh
python3.12 -m venv .venv
gh release download v0.2.0.dev9 --repo IIZhukovProjects/codegen --pattern '*.whl'
.venv/bin/pip install './platform_codegen-0.2.0.dev9-py3-none-any.whl[runtime,grpc,test]'
source .venv/bin/activate
codegen lock
codegen validate
codegen run
codegen status
```

Локальный вход — `http://localhost/`. Nginx ingress передаёт `/` фронту, а
`/api/` — backend. Остальные контейнеры доступны внутри сети Docker.
`run` собирает образы, поднимает ресурсы, применяет миграции, заполняет каталог и ждёт readiness.
При занятом порте 80 используйте `codegen run --port-offset 10000`
и откройте `http://localhost:10080/`. `run --no-build` использует предыдущую сборку.
Локально включен fake: платных запросов и ключа Polza нет.

```sh
codegen stop
codegen stop --infrastructure
```

Остановка сохраняет данные. `codegen infra down --volumes` явно удаляет локальные тома.
Не удаляйте `.local/` при сохраненных томах: там находятся пароли доступа.

## Разработка без сервисных контейнеров

```sh
codegen infra up
codegen migrations upgrade --service backend
codegen migrations upgrade --service llm
python scripts/seed.py
codegen service run llm
# В другом терминале с тем же venv:
codegen service run backend
# Frontend: cd apps/frontend && npm ci; затем из корня:
codegen app dev frontend
```

Для native запуска дополнительно установите `services/backend/requirements.txt`
и `services/llm/requirements.txt`. Каждый `service run` получает только свой пул ENV.
Регенерация: `codegen generate --scope services`; миграции принадлежат приложению в
`migrations/versions/`, Alembic scaffold — кодгену. Новая ревизия:
`codegen migrations revision --service backend --message change`.

## Конфигурация

Секреты задаются в `environments/`, сервис читает только ENV. В prod значение
`POLZA_API_KEY.secretRef.id` намеренно оставлено `null`; его нужно привязать в платформе.
Платформа также передает DATABASE_URL, S3 credentials, OTLP и LLM_URL.
В `schemas/llm/config.yaml` объявлен `ImageGenerationConfig`. LLM читает провайдера,
HTTPS-адрес и модель из текущего снимка при создании задания.
Для доставки из платформы передайте `PLATFORM_CONFIG_URL` и секрет
`PLATFORM_CONFIG_TOKEN` только процессу LLM в нужном окружении.

[Архитектура сервисов](docs/services.md), [инфраструктура](docs/infrastructure.md),
[проверки](docs/verification.md).

HTTP API реализуются ресурсами в src/api/: Rooms, RoomsPlayers, Game, Images,
Metadata и ImageJobs. Фабрика получает http=[...делегаты...]. Спецификации пишутся в schemas, маршруты и модели генерируются.
Серверы объявляются в service.server.http/grpc, уровни logging.local/platform независимы.

OpenAPI разбит на api.yaml и файлы PathItem в paths/<resource>/ со стандартными локальными $ref.
У каждой ручки вход и выход описаны прямо возле requestBody/responses; общего models.yaml нет.
Игровой каталог хранится в PostgreSQL: game_modes, game_prompts, game_powers.
Начальный каталог загружается перед стартом backend. Для явного обновления используйте `python scripts/seed.py`.
Backend не читает seed-файлы; после изменения данных нужен его перезапуск.
[Миграция и заполнение каталога](docs/catalog.md).
Трасса ingress проходит через HTTP, durable outbox/job, провайдер и S3; для этого
используются traceparent/tracestate. [Наблюдаемость](docs/observability.md).

DTO операции лежат рядом с HTTP binding: generated/api/rooms/create_room.py содержит
свои Request/Response. Клиент llm использует clients/llm/create_image_job.py и get_image_job.py;
их модели независимы. Бизнес-слой возвращает данные, а конкретный API адаптирует их в свой Response.
