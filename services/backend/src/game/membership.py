from __future__ import annotations
import secrets
import uuid
from .catalog import DEFAULT_CAPACITY
from .state import fail


def join(room, name):
    name = name.strip()
    if not name:
        fail("Как тебя зовут?")
    limit = room.capacity()
    if limit is not None and len(room.state["players"]) >= limit:
        fail(f"В лобби заняты все {limit} мест")
    if any(
        (
            player["name"].casefold() == name.casefold()
            for player in room.state["players"]
        )
    ):
        fail("Это имя уже занято")
    player = dict(
        id=uuid.uuid4().hex,
        token=secrets.token_urlsafe(32),
        name=name,
        score=0,
        power=room.rng.choice(list(room.catalog.powers)),
        spent=False,
        waiting=room.state["phase"] != "lobby",
    )
    room.state["players"].append(player)
    return {"token": player["token"], "room_code": room.code}


def leave(room, token):
    player = room.player(token)
    if room.state["phase"] == "lobby":
        room.state["players"] = [
            value for value in room.state["players"] if value["id"] != player["id"]
        ]
    else:
        player["waiting"] = True
        room.progress()


def configure(room, token, values, supplied):
    room.host(token)
    if room.state["phase"] != "lobby":
        fail("Настройки доступны в лобби")
    if values["mode"] not in [*room.catalog.mode_info, "mix"]:
        fail("Неизвестная игра")
    limit = values.get("capacity") if "capacity" in supplied else room.capacity()
    if limit is not None and limit < len(room.state["players"]):
        fail("Лимит меньше числа участников в лобби")
    if "name" in supplied:
        name = (values.get("name") or "").strip()
        if not name:
            fail("Придумай название комнаты.")
        room.name = name
    room.state.update(mode=values["mode"], count=values["count"], capacity=limit)


def add_bots(room, token):
    room.host(token)
    if room.state["phase"] != "lobby":
        fail("Демо доступно в лобби")
    limit = room.capacity()
    target = min(limit, DEFAULT_CAPACITY) if limit is not None else DEFAULT_CAPACITY
    for index, name in enumerate(
        ["Пельмень", "Тётя Люся", "Диджей Хомяк", "Кот Борис"]
    ):
        if len(room.state["players"]) >= target:
            break
        if any((player["name"] == name for player in room.state["players"])):
            continue
        room.state["players"].append(
            dict(
                id=uuid.uuid4().hex,
                token=secrets.token_urlsafe(32),
                name=name,
                score=0,
                power=room.rng.choice(list(room.catalog.powers)),
                spent=False,
                waiting=False,
                bot=index + 1,
            )
        )


def remove_player(room, token, player_id):
    room.host(token)
    if room.state["phase"] != "lobby":
        fail("Убирать игроков можно только в лобби")
    room.state["players"] = [
        player for player in room.state["players"] if player["id"] != player_id
    ]
