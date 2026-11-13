from __future__ import annotations
import uuid
from .state import authors, new_image_job, fail, kind


def accept_answer(room, r, p, text, image=None, power=False, partner=None):
    answer = dict(id=uuid.uuid4().hex, player=p["id"], text=text, image=image)
    if partner:
        answer["partner"] = partner
    if power:
        r["effects"][p["id"]] = {"power": p["power"], "answer": answer["id"]}
        p["spent"] = True
    r["answers"].append(answer)


def caption_assignment(room, r, player_id):
    for author, captioner in r.get("relay_pairs", {}).items():
        if captioner == player_id:
            job = r.get("image_jobs", {}).get(author, {})
            if job.get("image"):
                return (author, job["image"])
    return None


def answer(room, token, body, *, image_allowed=False):
    player = room.player(token)
    if (
        room.state["phase"] not in ("answer", "caption")
        or player["waiting"]
        or room.current()["round_id"] != body["round_id"]
    ):
        fail("Приём ответов завершён")
    row = room.current()
    image = body.get("image")
    relay_upload = (
        kind(row, catalog=room.catalog) == "relay" and room.state["phase"] == "answer"
    )
    if relay_upload and (not image):
        fail("Сначала добавь картинку")
    if any((answer["player"] == player["id"] for answer in row["answers"])):
        fail("Ответ уже принят")
    if row.get("image_jobs", {}).get(player["id"], {}).get("status") == "queued":
        fail("Картинка ещё рисуется")
    text = body.get("text", "").strip()
    if not text and (not image):
        fail("Напиши ответ или добавь картинку")
    if image and (not image_allowed):
        fail("Неизвестная картинка")
    if relay_upload:
        if row["image_jobs"].get(player["id"], {}).get("status") == "done":
            fail("Картинка уже передана")
        row["image_jobs"][player["id"]] = {"status": "done", "image": image}
        room.progress()
        return
    power = body.get("power", False)
    if power and (player["spent"] or player["power"] == "block"):
        fail("Эту способность сейчас нельзя применить")
    fields = room.catalog.modes.get(row["mode"], {}).get("fields", [])
    if fields and (
        len(text.splitlines()) != len(fields)
        or any((not line.strip() for line in text.splitlines()))
    ):
        fail("Заполни обе реплики.")
    partner = None
    if room.state["phase"] == "caption":
        assignment = room.caption_assignment(row, player["id"])
        if not assignment:
            fail("Для тебя нет картинки в этом раунде")
        partner, image = assignment
    room.accept_answer(row, player, text, image, power, partner)
    room.progress()


def vote(room, token, body):
    player = room.player(token)
    if (
        room.state["phase"] != "vote"
        or player["waiting"]
        or room.current()["round_id"] != body["round_id"]
    ):
        fail("Голосование завершено")
    row = room.current()
    if player["id"] in row["votes"]:
        fail("Голос уже принят")
    options = [
        answer["id"] for answer in row["answers"] if player["id"] not in authors(answer)
    ]
    if body["answer"] not in options:
        fail("Выбери чужой ответ")
    if body.get("block"):
        if (
            player["spent"]
            or player["power"] != "block"
            or body["block"] not in options
        ):
            fail("Нельзя обнулить этот ответ")
        row["effects"][player["id"]] = {"power": "block", "target": body["block"]}
        player["spent"] = True
    row["votes"][player["id"]] = body["answer"]
    room.progress()


def generate(room, token, body):
    player = room.player(token)
    if (
        room.state["phase"] != "answer"
        or player["waiting"]
        or room.current()["round_id"] != body["round_id"]
    ):
        fail("Сейчас нельзя генерировать")
    row = room.current()
    if kind(row, catalog=room.catalog) not in ("image", "relay"):
        fail("В этом раунде нужен текстовый ответ")
    jobs = row.setdefault("image_jobs", {})
    existing = jobs.get(player["id"], {})
    if existing.get("status") in ("queued", "done"):
        return
    text = body["text"].strip()
    if len(text) < 3:
        fail("Опиши картинку хотя бы тремя символами")
    if any((answer["player"] == player["id"] for answer in row["answers"])):
        fail("Ответ уже принят")
    if existing.get("moderated") and text.casefold() == existing["text"].casefold():
        fail("Модель уже отклонила это описание. Измени его.")
    if room.clock() >= max(room.state["deadline"], existing.get("edit_until", 0)):
        fail("Время на новые генерации закончилось")
    power = body.get("power", False)
    if power and (
        player["spent"]
        or player["power"] == "block"
        or kind(row, catalog=room.catalog) == "relay"
    ):
        fail("Эту способность сейчас нельзя применить")
    jobs[player["id"]] = new_image_job(text, power)


def apply_image(
    room, round_id, owner, job_id, *, image=None, error=None, moderated=False
):
    if (
        room.state["phase"] not in ("answer", "briefing")
        or not room.state["rounds"]
        or room.current()["round_id"] != round_id
    ):
        return False
    row = room.current()
    job = row.get("image_jobs", {}).get(owner)
    if not job or job.get("id") != job_id or job.get("status") != "queued":
        return False
    if image:
        job.update(status="done", image=image)
        if owner != "shared" and kind(row, catalog=room.catalog) != "relay":
            player = next((p for p in room.active() if p["id"] == owner), None)
            if player:
                room.accept_answer(row, player, job["text"], image, job["power"])
    else:
        job.update(
            status="rejected",
            error=error or "Не удалось создать изображение",
            moderated=moderated,
        )
        if moderated and owner != "shared":
            job["edit_until"] = room.clock() + 30
    room.progress()
    return True
