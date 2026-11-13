from generated.api.image_jobs import create_image_job, get_image_job
from generated.api.image_jobs import ImageJobs as Contract
from platform_codegen.runtime.http import HTTPContext
from fastapi.responses import JSONResponse
from uuid import UUID
from api.errors import error
from persistence import JobConflict, QueueFull


class ImageJobs(Contract):

    async def create_image_job(
        self,
        *,
        context: HTTPContext,
        body: create_image_job.Request,
        idempotency_key: str
    ) -> create_image_job.Response | JSONResponse:
        if not body.prompt.strip():
            return error("invalid_request", "Описание не может быть пустым", 422)
        try:
            return create_image_job.Response.model_validate(
                await context.runtime.images.create(idempotency_key, body)
            )
        except JobConflict:
            return error(
                "idempotency_conflict", "Ключ уже используется для другого задания", 409
            )
        except QueueFull:
            return error("rate_limited", "Очередь генерации заполнена", 429, True)

    async def get_image_job(
        self, *, context: HTTPContext, job_id: UUID
    ) -> get_image_job.Response | JSONResponse:
        value = await context.runtime.images.get(job_id)
        return (
            get_image_job.Response.model_validate(value)
            if value
            else error("not_found", "Задание не найдено", 404)
        )
