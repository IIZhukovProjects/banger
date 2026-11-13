from fastapi import Request
from fastapi.responses import JSONResponse
from generated.app import create_app as generated_app

from api import delegates
from game.errors import GameError
from service import GameService
from settings import Settings


async def start(runtime):
    runtime.game = GameService(runtime)
    await runtime.game.start()
    runtime.logger.info("Game backend started")


def create_app():
    app = generated_app(http=delegates(), settings_class=Settings, startup=start)

    @app.exception_handler(GameError)
    async def game_error(request: Request, error: GameError):
        return JSONResponse({"detail": error.message}, status_code=error.status)

    return app
