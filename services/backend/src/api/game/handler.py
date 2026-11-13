from generated.api.game import next_round, submit_answer, submit_vote
from generated.api.game import Game as Contract
from platform_codegen.runtime.http import HTTPContext
from api.identity import identity


class Game(Contract):

    async def get_state(
        self, *, context: HTTPContext, x_room_code=None, authorization=None
    ):
        return await context.runtime.game.state(*identity(x_room_code, authorization))

    async def start_game(
        self, *, context: HTTPContext, x_room_code=None, authorization=None
    ):
        room, token = identity(x_room_code, authorization)
        return await context.runtime.game.mutate(room, "start", token)

    async def next_round(
        self,
        *,
        context: HTTPContext,
        body: next_round.Request,
        x_room_code=None,
        authorization=None
    ):
        room, token = identity(x_room_code, authorization)
        return await context.runtime.game.mutate(room, "next", token, body)

    async def return_to_lobby(
        self, *, context: HTTPContext, x_room_code=None, authorization=None
    ):
        room, token = identity(x_room_code, authorization)
        return await context.runtime.game.mutate(room, "lobby", token)

    async def submit_answer(
        self,
        *,
        context: HTTPContext,
        body: submit_answer.Request,
        x_room_code=None,
        authorization=None
    ):
        room, token = identity(x_room_code, authorization)
        return await context.runtime.game.mutate(room, "answer", token, body)

    async def submit_vote(
        self,
        *,
        context: HTTPContext,
        body: submit_vote.Request,
        x_room_code=None,
        authorization=None
    ):
        room, token = identity(x_room_code, authorization)
        return await context.runtime.game.mutate(room, "vote", token, body)
