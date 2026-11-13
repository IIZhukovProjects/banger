from platform_codegen.runtime.operations import observed
import asyncio
import hashlib
import time

from generated.config import ImageGenerationConfig
from persistence import JobRepository
from providers import (
    FakeProvider,
    PolzaProvider,
    ProviderRejected,
    RetryProvider,
    inspect_image,
)


class ImageService:
    def __init__(self, runtime):
        self.runtime = runtime
        self.repository = JobRepository(runtime.database)
        self.storage = runtime.s3
        self.settings = runtime.settings
        self.providers = {"fake": FakeProvider()}
        if (
            self.settings.image_provider == "polza"
            or self.settings.polza_api_key.get_secret_value()
        ):
            self.providers["polza"] = PolzaProvider(self.settings)
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

            for client in (
                self.providers["polza"].client,
                self.providers["polza"].downloads,
            ):
                HTTPXClientInstrumentor().instrument_client(
                    client,
                    tracer_provider=runtime.telemetry.tracer_provider,
                    meter_provider=runtime.telemetry.meter_provider,
                )

    async def start(self):
        self.runtime.task(self.collect_statistics(), name="business-statistics")
        await self.repository.ready()
        self.runtime.ready_checks["migrations"] = self.repository.ready
        for index in range(self.settings.image_job_concurrency):
            self.runtime.task(self.worker(), name="image-worker-" + str(index))

    async def close(self):
        for provider in self.providers.values():
            await provider.close()

    @observed("llm.create")
    async def create(self, key, body):
        config = self.runtime.config.get(ImageGenerationConfig)
        provider = config.provider or self.settings.image_provider
        return self.repository.public(
            await self.repository.create(
                key,
                body.prompt,
                provider,
                config.model,
                self.settings.image_queue_limit,
                provider_base_url=config.base_url if provider == "polza" else None,
            )
        )

    @observed("llm.get")
    async def get(self, identifier):
        row = await self.repository.get(identifier)
        return self.repository.public(row) if row else None

    @observed("llm.finish")
    async def finish(self, job, result):
        if result.image is None:
            if not result.provider_id:
                raise RetryProvider("Provider result missing")
            await self.repository.save(
                job,
                provider_id=result.provider_id,
                phase="polling",
                next_attempt=time.time() + 1,
            )
            return
        raw, width, height = await asyncio.to_thread(inspect_image, result.image)
        key = "generated/" + job["id"] + ".png"
        await self.storage.put(key, raw, "image/png")
        artifact = {
            "resource": "s3",
            "objectKey": key,
            "mediaType": "image/png",
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "width": width,
            "height": height,
        }
        await self.repository.save(
            job, status="succeeded", phase="finished", result=artifact, error=None
        )

    @observed("image.job.process", parent="job")
    async def process(self, job):
        provider = self.providers.get(job["provider"])
        if provider is None:
            await self.repository.save(
                job,
                status="failed",
                phase="finished",
                error={
                    "code": "provider_auth",
                    "message": "Провайдер задания недоступен в конфигурации сервиса",
                },
            )
            return
        if time.time() - job["created_at"] > self.settings.image_job_timeout_seconds:
            await self.repository.save(
                job,
                status="failed",
                phase="finished",
                error={
                    "code": "retry_exhausted",
                    "message": "Истекло время ожидания генерации",
                },
            )
            return
        submitting = not job["provider_id"]
        base_url = job["provider_base_url"]
        try:
            if submitting:
                if not await self.repository.save(
                    job, release=False, phase="submitting"
                ):
                    return
                with self.runtime.telemetry.operation(
                    "image.provider.submit",
                    attributes={
                        "provider": (
                            job["provider"]
                            if job["provider"] in ("fake", "polza")
                            else "other"
                        )
                    },
                ):
                    result = await provider.submit(
                        job["prompt"], job["model"], base_url=base_url
                    )
                # Persist the external operation ID before downloading/storing any image.
                if result.provider_id:
                    await self.repository.save(
                        job,
                        provider_id=result.provider_id,
                        phase="polling",
                        next_attempt=time.time() + 1,
                    )
                    return
            else:
                with self.runtime.telemetry.operation(
                    "image.provider.poll",
                    attributes={
                        "provider": (
                            job["provider"]
                            if job["provider"] in ("fake", "polza")
                            else "other"
                        )
                    },
                ):
                    result = await provider.poll(job["provider_id"], base_url=base_url)
            await self.finish(job, result)
        except asyncio.CancelledError:
            raise
        except ProviderRejected as error:
            await self.repository.save(
                job,
                status="failed",
                phase="finished",
                error={"code": error.code, "message": error.message},
            )
        except Exception:
            if submitting and job["provider"] == "polza":
                await self.repository.save(
                    job,
                    status="needs_reconciliation",
                    phase="finished",
                    error={
                        "code": "submit_unknown",
                        "message": "Не удалось подтвердить отправку задания провайдеру. Нужна проверка операции.",
                    },
                )
            else:
                attempts = job["attempts"] + 1
                if attempts >= 10:
                    await self.repository.save(
                        job,
                        status="failed",
                        phase="finished",
                        error={
                            "code": "retry_exhausted",
                            "message": "Провайдер временно недоступен, попробуй позже",
                        },
                    )
                else:
                    await self.repository.save(
                        job,
                        phase="polling" if job["provider_id"] else "queued",
                        attempts=attempts,
                        next_attempt=time.time() + min(30, 2 ** min(attempts, 5)),
                    )

    async def worker(self):
        while True:
            try:
                job = await self.repository.claim()
                if job:
                    await self.process(job)
                else:
                    await asyncio.sleep(0.2)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.runtime.logger.error(
                    "Image job iteration failed; durable job will be recovered"
                )
                await asyncio.sleep(1)

    async def collect_statistics(self):
        while True:
            try:
                counts = await self.repository.statistics()
                for status in (
                    "queued",
                    "running",
                    "succeeded",
                    "failed",
                    "needs_reconciliation",
                ):
                    self.runtime.telemetry.gauge(
                        "image.jobs", counts.get(status, 0), {"status": status}
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                self.runtime.logger.warning("Job statistics refresh failed")
            await asyncio.sleep(10)
