"""In-process Gateway HTTP contract for consumers of image generation."""

import hashlib
import struct
import time
from uuid import uuid4
import zlib

from fastapi import HTTPException
from fastapi.responses import Response

from .api.chat import Chat
from .api.files import Files
from .api.media import Media


def png(key):
    color = hashlib.sha256(key.encode()).digest()[:3]
    size = 96

    def chunk(kind, data):
        return (
            struct.pack("!I", len(data))
            + kind
            + data
            + struct.pack("!I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack("!2I5B", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\x00" + (color + b"\xff") * size) * size))
        + chunk(b"IEND", b"")
    )


class MockChat(Chat):
    def __init__(self):
        self.ids = set()
        self.keys = {}

    async def create_chat(self, *, context, body, idempotency_key=None):
        identifier = self.keys.get(idempotency_key) or uuid4().hex
        if idempotency_key:
            self.keys[idempotency_key] = identifier
        self.ids.add(identifier)
        return {"id": identifier}


class MockMedia(Media):
    def __init__(self, chats):
        self.chats = chats
        self.jobs = {}
        self.keys = {}

    async def create_job(self, *, context, chat_id, body, idempotency_key=None):
        if chat_id not in self.chats.ids:
            raise HTTPException(404, "Диалог не найден")
        request = body.model_dump_json()
        key = (chat_id, idempotency_key)
        if idempotency_key and key in self.keys:
            previous, identifier = self.keys[key]
            if request != previous:
                raise HTTPException(409, "Ключ уже использован для другого запроса")
            return self.jobs[identifier]
        identifier = uuid4().hex
        job = {
            "id": identifier,
            "kind": "image",
            "chat_id": chat_id,
            "message_id": uuid4().hex,
            "status": "queued",
            "result": None,
            "error": None,
            "created_at": time.time(),
        }
        self.jobs[identifier] = job
        if idempotency_key:
            self.keys[key] = (request, identifier)
        return job

    async def get_job(self, *, context, job_id):
        if job_id not in self.jobs:
            raise HTTPException(404, "Задание не найдено")
        job = self.jobs[job_id]
        if job["status"] == "queued":
            job["status"] = "running"
        elif job["status"] == "running":
            job["status"] = "succeeded"
            job["result"] = {
                "file_id": job_id,
                "type": "image/png",
                "name": "image.png",
            }
        return job


class MockFiles(Files):
    def __init__(self, media):
        self.media = media

    async def get_file(self, *, context, file_id):
        job = self.media.jobs.get(file_id)
        if job is None or job["status"] != "succeeded":
            raise HTTPException(404, "Файл не найден")
        return Response(png(file_id), media_type="image/png")


def create_handlers():
    chat = MockChat()
    media = MockMedia(chat)
    return [chat, media, MockFiles(media)]
