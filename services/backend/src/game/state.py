from __future__ import annotations
import uuid
from .catalog import DEFAULT_CAPACITY
from .errors import GameError


def fresh():
    return dict(
        phase="lobby",
        players=[],
        rounds=[],
        index=0,
        mode="mix",
        count=3,
        capacity=DEFAULT_CAPACITY,
        history=[],
        deadline=None,
        used=[],
        next_ready=[],
    )


def authors(answer):
    return [answer["player"], *([answer["partner"]] if answer.get("partner") else [])]


def new_image_job(text, power=False):
    return dict(
        id=uuid.uuid4().hex,
        text=text,
        power=power,
        status="queued",
        retry_at=0,
        retries=0,
    )


def pending_jobs(round_data):
    return any(
        (job["status"] == "queued" for job in round_data.get("image_jobs", {}).values())
    )


def fail(message):
    raise GameError(400, message)


def kind(r, *, catalog=None):
    if "kind" in r:
        return r["kind"]
    return (
        (catalog.modes if catalog else {})
        .get(r["mode"], {})
        .get("kind", "image" if r.get("is_image") else "text")
    )
