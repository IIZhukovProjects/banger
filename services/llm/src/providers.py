import asyncio
import base64
from dataclasses import dataclass
import hashlib
import io
import re
from urllib.parse import quote, urlsplit

import httpx
from PIL import Image, ImageDraw, UnidentifiedImageError

from image_prompt import grok_image_prompt, sticker_prompt


class ProviderRejected(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


class RetryProvider(Exception):
    pass


@dataclass(frozen=True)
class ProviderResult:
    provider_id: str | None = None
    image: bytes | None = None


def inspect_image(raw):
    if len(raw) > 10485760:
        raise ProviderRejected(
            "invalid_image", "Изображение превышает допустимый размер"
        )
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.width != image.height or image.width * image.height > 25000000:
                raise ProviderRejected("invalid_image", "Неверный размер изображения")
            image.load()
            rgba = image.convert("RGBA")
            output = io.BytesIO()
            rgba.save(output, "PNG")
            png = output.getvalue()
            if len(png) > 10485760:
                raise ProviderRejected(
                    "invalid_image", "Изображение превышает допустимый размер"
                )
            return png, rgba.width, rgba.height
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        raise ProviderRejected(
            "invalid_image", "Провайдер вернул поврежденное изображение"
        ) from None


class FakeProvider:
    def render(self, prompt):
        digest = hashlib.sha256(prompt.encode()).digest()
        image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        color = (80 + digest[0] % 170, 80 + digest[1] % 170, 80 + digest[2] % 170, 255)
        draw.rounded_rectangle((95, 95, 420, 420), radius=85, fill=(25, 25, 25, 90))
        draw.rounded_rectangle(
            (80, 80, 405, 405),
            radius=85,
            fill=color,
            outline=(25, 25, 25, 255),
            width=12,
        )
        draw.ellipse((135, 155, 175, 195), fill=(25, 25, 25, 255))
        draw.ellipse((305, 155, 345, 195), fill=(25, 25, 25, 255))
        draw.arc((155, 190, 330, 330), 0, 180, fill=(25, 25, 25, 255), width=12)
        stream = io.BytesIO()
        image.save(stream, "PNG")
        return stream.getvalue()

    async def submit(self, prompt, model, *, base_url=None):
        return ProviderResult(image=await asyncio.to_thread(self.render, prompt))

    async def poll(self, provider_id, *, base_url=None):
        raise RetryProvider("Fake jobs do not require polling")

    async def close(self):
        pass


class PolzaProvider:
    def __init__(self, settings, *, transport=None):
        self.legacy_base_url = settings.image_provider_base_url
        trusted = httpx.URL(settings.polza_api_origin or self.legacy_base_url)
        self.trusted_origin = (trusted.scheme, trusted.host, trusted.port)
        key = settings.polza_api_key.get_secret_value()
        if not key:
            raise RuntimeError("POLZA_API_KEY is required for the polza provider")
        self.auth_headers = {"Authorization": "Bearer " + key}
        self.client = httpx.AsyncClient(
            timeout=25,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )
        self.downloads = httpx.AsyncClient(
            timeout=30, follow_redirects=False, trust_env=False, transport=transport
        )

    def media_url(self, base_url, path):
        address = base_url if base_url is not None else self.legacy_base_url
        try:
            parsed = urlsplit(address)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.port == 0
                or any(char.isspace() for char in address)
                or any(char in address for char in "@?#\\")
            ):
                raise ValueError
            url = httpx.URL(address.rstrip("/") + "/" + path)
            if (url.scheme, url.host, url.port) != self.trusted_origin:
                raise ValueError
            return url
        except (ValueError, httpx.InvalidURL):
            raise ProviderRejected(
                "provider_config", "HTTPS-адрес провайдера не разрешён для этого токена"
            ) from None

    @staticmethod
    def checked(response):
        try:
            data = response.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            raise RetryProvider("Invalid provider response")
        if (
            response.status_code >= 400
            or data.get("error")
            or data.get("status") == "failed"
        ):
            normalized = re.sub(r"[^\w]+", " ", str(data).casefold())
            if any(
                token in normalized
                for token in (
                    "content policy",
                    "moderation",
                    "content filtered",
                    "nsfw",
                    "safety violations",
                    "модерац",
                )
            ):
                raise ProviderRejected(
                    "moderated", "Модель отклонила описание. Измени текст."
                )
            if response.status_code == 401:
                raise ProviderRejected("provider_auth", "Проверь ключ генератора.")
            if response.status_code == 402:
                raise ProviderRejected(
                    "provider_balance", "Пополните баланс генератора."
                )
            if response.status_code in (408, 429) or response.status_code >= 500:
                raise RetryProvider("Provider temporarily unavailable")
            raise ProviderRejected(
                "provider_failed", "Провайдер не смог создать изображение."
            )
        if not isinstance(data, dict):
            raise RetryProvider("Invalid provider response")
        return data

    async def result(self, data):
        if data.get("status") in ("pending", "processing"):
            identifier = data.get("id")
            if (
                not isinstance(identifier, str)
                or not identifier
                or len(identifier) > 300
            ):
                raise RetryProvider("Provider did not return an operation ID")
            return ProviderResult(provider_id=identifier)
        value = data.get("data")
        entry = value[0] if isinstance(value, list) and value else value
        if not isinstance(entry, dict):
            raise ProviderRejected("invalid_image", "Провайдер не вернул изображение")
        if entry.get("b64_json"):
            try:
                if len(entry["b64_json"]) > 14 * 1024 * 1024:
                    raise ValueError("Oversized image")
                return ProviderResult(
                    image=base64.b64decode(entry["b64_json"], validate=True)
                )
            except (ValueError, TypeError):
                raise ProviderRejected(
                    "invalid_image", "Поврежденное изображение"
                ) from None
        link = urlsplit(str(entry.get("url", "")))
        if (
            link.scheme != "https"
            or not link.hostname
            or link.username
            or link.password
        ):
            raise ProviderRejected(
                "invalid_image", "Провайдер не вернул корректную ссылку на изображение"
            )
        async with self.downloads.stream("GET", link.geturl()) as response:
            if not response.is_success:
                raise RetryProvider("Image download unavailable")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > 10485760:
                    raise ProviderRejected(
                        "invalid_image", "Изображение превышает допустимый размер"
                    )
            return ProviderResult(image=bytes(body))

    async def submit(self, prompt, model, *, base_url=None):
        if model == "x-ai/grok-imagine-image":
            image_input = {
                "prompt": grok_image_prompt(prompt),
                "aspect_ratio": "1:1",
            }
        else:
            image_input = {
                "prompt": sticker_prompt(prompt),
                "aspect_ratio": "1:1",
                "quality": "medium",
                "output_format": "png",
            }
        response = await self.client.post(
            self.media_url(base_url, "media"),
            headers=self.auth_headers,
            json={
                "model": model,
                "async": True,
                "input": image_input,
            },
        )
        return await self.result(self.checked(response))

    async def poll(self, provider_id, *, base_url=None):
        response = await self.client.get(
            self.media_url(base_url, "media/" + quote(provider_id, safe="")),
            headers=self.auth_headers,
        )
        if response.status_code == 404:
            raise ProviderRejected("provider_failed", "Задание исчезло у провайдера")
        return await self.result(self.checked(response))

    async def close(self):
        await self.client.aclose()
        await self.downloads.aclose()
