from generated.api.game.images import generate_image
from generated.api.game.images import GameImages as Contract
from platform_codegen.runtime.http import HTTPContext
from api.identity import identity


class GameImages(Contract):

    async def generate_image(
        self,
        *,
        context: HTTPContext,
        body: generate_image.Request,
        x_room_code=None,
        authorization=None
    ):
        room, token = identity(x_room_code, authorization)
        return await context.runtime.game.mutate(room, "generate", token, body)
