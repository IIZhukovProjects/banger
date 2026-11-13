from generated.api.images import Images as Contract
from platform_codegen.runtime.http import HTTPContext
from fastapi import UploadFile
from fastapi.responses import Response
from api.identity import identity


class Images(Contract):

    async def upload_image(
        self,
        *,
        context: HTTPContext,
        file: UploadFile,
        x_room_code=None,
        authorization=None
    ):
        service = context.runtime.game
        body = await file.read(service.settings.max_upload_bytes + 1)
        return await service.upload(*identity(x_room_code, authorization), body)

    async def download_image(self, *, context: HTTPContext, path: str):
        data = await context.runtime.game.download(path)
        return Response(
            data.body,
            media_type=data.content_type,
            headers={
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "public, max-age=604800",
                "ETag": data.etag,
            },
        )
