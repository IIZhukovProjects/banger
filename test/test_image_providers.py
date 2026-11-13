import io
import json
from types import SimpleNamespace
import unittest

import httpx
from PIL import Image
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

    def test_grok_opaque_image_is_accepted_and_converted_to_png(self):
        stream = io.BytesIO()
        Image.new("RGB", (32, 32), "orange").save(stream, "JPEG")
        raw = stream.getvalue()
        png, width, height = inspect_image(raw, model="x-ai/grok-imagine-image")
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertEqual((width, height), (32, 32))
        with self.assertRaises(ProviderRejected):
            inspect_image(raw, model="openai/gpt-image-1.5")

    async def test_grok_sends_subject_and_visual_style(self):
        def handler(request):
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "x-ai/grok-imagine-image")
            image_input = payload["input"]
            self.assertEqual(set(image_input), {"prompt", "aspect_ratio"})
            self.assertTrue(image_input["prompt"].startswith("Рыжий кот в синей шляпе."))
            self.assertNotIn("пати-игры", image_input["prompt"])
            return httpx.Response(200, json={"id": "job", "status": "pending"})

        settings = SimpleNamespace(
            image_provider_base_url="https://polza.ai/api/v1",
            polza_api_origin="",
            polza_api_key=SecretStr("test-key"),
        )
        provider = PolzaProvider(settings, transport=httpx.MockTransport(handler))
        try:
            await provider.submit("Рыжий кот в синей шляпе", "x-ai/grok-imagine-image")
        finally:
            await provider.close()

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
