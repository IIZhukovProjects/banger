from generated.api.rooms import create_room, join_room, update_room
from generated.api.rooms import Rooms as Contract
from platform_codegen.runtime.http import HTTPContext
from api.identity import identity


class Rooms(Contract):

    async def list_rooms(self, *, context: HTTPContext):
        return {"rooms": await context.runtime.game.repository.list()}

    async def create_room(self, *, context: HTTPContext, body: create_room.Request):
        return await context.runtime.game.create(body)

    async def get_room(self, *, context: HTTPContext, code: str):
        return await context.runtime.game.summary(code)

    async def join_room(
        self,
        *,
        context: HTTPContext,
        body: join_room.Request,
        x_room_code=None,
        authorization=None
    ):
        room, token = identity(x_room_code, authorization)
        return await context.runtime.game.mutate(room, "join", token, body)

    async def leave_room(
        self, *, context: HTTPContext, x_room_code=None, authorization=None
    ):
        room, token = identity(x_room_code, authorization)
        return await context.runtime.game.mutate(room, "leave", token)

    async def update_room(
        self,
        *,
        context: HTTPContext,
        body: update_room.Request,
        x_room_code=None,
        authorization=None
    ):
        room, token = identity(x_room_code, authorization)
        return await context.runtime.game.mutate(room, "settings", token, body)
