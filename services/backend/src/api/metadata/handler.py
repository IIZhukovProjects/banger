from generated.api.metadata import Metadata as Contract
from platform_codegen.runtime.http import HTTPContext


class Metadata(Contract):

    async def get_meta(self, *, context: HTTPContext):
        return context.runtime.game.meta()

    async def get_health(self, *, context: HTTPContext):
        return {"status": "ok"}
