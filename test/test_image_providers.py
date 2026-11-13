import json
from types import SimpleNamespace
import unittest

import httpx
from pydantic import SecretStr

from providers import FakeProvider, PolzaProvider, ProviderRejected, inspect_image


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_fake_provider_is_deterministic_and_transparent(self):
        provider = FakeProvider()
        first = await provider.submit("Пластилиновый кот", "unused")
        second = await provider.submit("Пластилиновый кот", "unused")
        self.assertEqual(first.image, second.image)
        png, width, height = inspect_image(first.image)
        self.assertEqual((width, height), (512, 512))
        self.assertTrue(png.startswith(b"\x89PNG"))

    async def test_polza_submit_poll_and_safe_download_do_not_leak_bearer(self):
        png = (await FakeProvider().submit("test", "unused")).image
        calls = []

        def handler(request):
            calls.append(request)
            if request.url.host == "cdn.example":
                self.assertNotIn("Authorization", request.headers)
                return httpx.Response(200, content=png)
            self.assertEqual(
                request.headers["Authorization"], "Bearer private-test-key"
            )
            self.assertEqual(request.url.host, "provider.example")
            if request.method == "POST":
                self.assertEqual(request.url.path, "/api/custom/media")
                self.assertEqual(
                    json.loads(request.content)["model"], "custom/image-v2"
                )
                return httpx.Response(
                    200, json={"id": "provider-operation", "status": "pending"}
                )
            self.assertEqual(request.url.path, "/api/custom/media/provider-operation")
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "data": [{"url": "https://cdn.example/result.png"}],
                },
            )

        settings = SimpleNamespace(
            image_provider_base_url="https://polza.ai/api/v1",
            polza_api_origin="https://provider.example",
            polza_api_key=SecretStr("private-test-key"),
        )
        provider = PolzaProvider(settings, transport=httpx.MockTransport(handler))
        try:
            base_url = "https://provider.example/api/custom"
            submitted = await provider.submit(
                "test", "custom/image-v2", base_url=base_url
            )
            self.assertEqual(submitted.provider_id, "provider-operation")
            result = await provider.poll(submitted.provider_id, base_url=base_url)
            self.assertEqual(inspect_image(result.image)[1:], (512, 512))
            self.assertEqual(len(calls), 3)
            with self.assertRaises(ProviderRejected):
                await provider.submit(
                    "test", "custom/image-v2", base_url="http://provider.example"
                )
            with self.assertRaises(ProviderRejected):
                await provider.poll(
                    submitted.provider_id, base_url="https://other.example"
                )
            self.assertEqual(len(calls), 3)
        finally:
            await provider.close()

    def test_moderation_auth_and_invalid_images_have_safe_errors(self):
        for response, code in (
            (
                httpx.Response(
                    400, json={"error": "content policy violation secret prompt"}
                ),
                "moderated",
            ),
            (
                httpx.Response(401, json={"error": "private-provider-payload"}),
                "provider_auth",
            ),
            (
                httpx.Response(402, json={"error": "private-provider-payload"}),
                "provider_balance",
            ),
        ):
            with self.assertRaises(ProviderRejected) as error:
                PolzaProvider.checked(response)
            self.assertEqual(error.exception.code, code)
            self.assertNotIn("private-provider-payload", str(error.exception))
            self.assertNotIn("secret prompt", str(error.exception))
        with self.assertRaises(ProviderRejected):
            inspect_image(b"not image")
