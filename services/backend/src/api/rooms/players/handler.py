from generated.api.rooms.players import RoomsPlayers as Contract
from platform_codegen.runtime.http import HTTPContext
from api.identity import identity


class RoomsPlayers(Contract):

    async def add_bots(
        self, *, context: HTTPContext, x_room_code=None, authorization=None
    ):
        room, token = identity(x_room_code, authorization)
        return await context.runtime.game.mutate(room, "bots", token)

    async def remove_player(
        self,
        *,
        context: HTTPContext,
        player_id: str,
        x_room_code=None,
        authorization=None
    ):
        room, token = identity(x_room_code, authorization)
        return await context.runtime.game.mutate(room, "remove", token, player_id)
