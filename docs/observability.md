# Наблюдаемость

Ingress должен передавать стандартные W3C traceparent и tracestate. Одного произвольного
X-Trace-ID недостаточно для корректной родительской связи. HTTP middleware продолжает
входящую трассу и возвращает X-Trace-Id. Nginx проксирует оба W3C-заголовка к сервису.
HTTPX/gRPC продолжают контекст межсервисных вызовов; SQLAlchemy пишет SQL spans.

Генерируемый адаптер создает span api.<Resource>.<operation> и метрики операции.
Telemetry.operation / observed измеряют бизнес-операции, DB-транзакции, S3/KV,
запуск/опрос провайдера, outbox и выполнение заданий. Timers измеряются по итерациям,
а не одной трассой на всё время жизни процесса.

| Метрика | Назначение |
| --- | --- |
| http.server.request.duration | Время HTTP с method/route/status |
| service.operation.calls | Число операций с operation/outcome |
| service.operation.duration | Длительность операции, секунды |
| storage.s3.object.size | Размер объектов, байты, upload/download |
| game.rooms | Комнаты по фазе |
| image.outbox.pending | Ожидающие запросы backend |
| image.jobs | Задания llm по статусам |
| image.jobs.completed | Завершения succeeded/failed/needs_reconciliation |

Длительности имеют границы histogram от 5ms до 30s. Room/job IDs, токены, prompts и
динамические имена моделей не становятся labels. Ошибки пишутся по типу без payload.
Локальные логи содержат trace_id/span_id; OTLP log records получают текущий контекст.
Уровни console/file и платформенного OTLP независимы.

W3C carrier сохраняется в trace_context JSONB вместе с outbox/job (миграции приложения
0002_trace_context). Воркеры извлекают сохраненный контекст для каждой попытки, поэтому
асинхронная работа и рестарт продолжают исходную трассу. Baggage/секреты не сохраняются.
Старые задания с пустым carrier начинают новую трассу. Sampling входящего контекста
сохраняется; наличие данных в Tempo зависит от sampling ingress и настроек observability.

Статистика очередей/комнат обновляется асинхронно раз в 10 секунд; exporter callbacks
не выполняют SQL. Метрики операционные, не являются транзакционным учётом платежей.
