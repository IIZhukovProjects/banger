import os
import unittest
from unittest.mock import AsyncMock, patch

from generated.clients import CLIENT_MOCKS, CLIENT_TYPES
from generated.clients.ai_gateway.create_chat import Request as CreateChatRequest
from generated.clients.ai_gateway.create_job import Request as CreateJobRequest
from generated.config import CONFIG_TYPES
from generated.manifest import SERVICE
from platform_codegen.runtime.clients import ServiceCallError
from platform_codegen.runtime.service import ServiceRuntime
from service import GameService
from settings import Settings


def runtime_for(environment):
    return ServiceRuntime(
        {"name": "backend-test", "clients": SERVICE["clients"]},
        Settings(service_environment=environment, observability_enabled=False),
        client_types=CLIENT_TYPES,
        client_mocks=CLIENT_MOCKS,
        config_types=CONFIG_TYPES,
    )


class GatewayImageTests(unittest.IsolatedAsyncioTestCase):
    async def test_backend_jobs_store_an_image_from_the_gateway_mock(self):
        runtime = runtime_for("local")
        with patch.dict(os.environ, {"SERVICE_RUNTIME_MODE": "local"}):
            await runtime.start()
        self.addAsyncCleanup(runtime.close)
        backend = GameService(runtime)
        backend.repository = AsyncMock()
        backend.repository.pin_image_model.return_value = True
        backend.storage = AsyncMock()
        request = {
            "id": "request-1",
            "room_code": "ROOM01",
            "prompt": "Пластилиновый кот",
            "remote_id": None,
            "gateway_model": None,
        }

        await backend.process_image(request)
        job_id = backend.repository.update_request.await_args.kwargs["remote_id"]
        await backend.process_image(request)
        assert (
            backend.repository.update_request.await_args.kwargs["remote_id"] == job_id
        )
        request["remote_id"] = job_id
        await backend.process_image(request)
        await backend.process_image(request)

        key, data, media_type = backend.storage.put.await_args.args
        assert key == "generated/ROOM01/request-1.png"
        assert data.startswith(b"\x89PNG") and media_type == "image/png"
        backend.repository.finish_image.assert_awaited_once_with(
            request, artifact=("request-1.png", key, media_type, len(data))
        )

        gateway = runtime.clients["ai-gateway"]
        chat = await gateway.create_chat(
            body=CreateChatRequest(title="Banger ROOM01"),
            idempotency_key="banger-room:ROOM01",
        )
        with self.assertRaises(ServiceCallError) as error:
            await gateway.create_job(
                chat_id=chat.id,
                body=CreateJobRequest(
                    model="polza-ai-grok-imagine", text="Другой запрос"
                ),
                idempotency_key=request["id"],
            )
        assert error.exception.status == 409

    async def test_platform_client_uses_the_injected_address_and_header(self):
        runtime = runtime_for("prod")
        self.addAsyncCleanup(runtime.close)
        with patch.dict(
            os.environ,
            {
                "SERVICE_RUNTIME_MODE": "platform",
                "AI_GATEWAY_URL": "http://gateway.internal/backend",
                "AI_GATEWAY_TOKEN": "fixture-token",
            },
        ):
            await runtime.start()
        gateway = runtime.clients["ai-gateway"]
        assert not gateway.is_mock
        assert str(gateway.client.base_url) == "http://gateway.internal/backend/"
        assert gateway.client.headers["Authorization"] == "Bearer fixture-token"
