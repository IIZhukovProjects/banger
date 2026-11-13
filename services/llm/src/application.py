from fastapi import Request
from fastapi.exceptions import RequestValidationError
from generated.app import create_app as generated_app

from api import delegates
from api.errors import error
from service import ImageService
from settings import Settings


async def start(runtime):
    runtime.images = ImageService(runtime)
    await runtime.images.start()
    runtime.logger.info("Image generation service started")


async def stop(runtime):
    if hasattr(runtime, "images"):
        await runtime.images.close()


def create_app():
    app = generated_app(
        http=delegates(), settings_class=Settings, startup=start, shutdown=stop
    )

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exception: RequestValidationError):
        return error("invalid_request", "Некорректный запрос", 422)

    return app
