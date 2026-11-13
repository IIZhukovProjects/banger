from __future__ import annotations
import copy
import uuid
from .catalog import MIN_PLAYERS, ROUND_SECONDS
from .state import authors, new_image_job, pending_jobs, fail, kind


def begin_round(room):
    r = room.current()
    r.update(answers=[], votes={}, effects={}, resolved=False, image_jobs={})
    phase = "answer"
    if kind(r, catalog=room.catalog) == "shared":
        phase = "briefing"
        r["image_jobs"]["shared"] = new_image_job(r["scene"])
    elif kind(r, catalog=room.catalog) == "relay":
        ids = [p["id"] for p in room.active()]
        r["relay_pairs"] = dict(zip(ids, ids[1:] + ids[:1])) if len(ids) > 1 else {}
    room.state.update(
        phase=phase,
        next_ready=[],
        deadline=None if phase == "briefing" else room.clock() + ROUND_SECONDS,
    )


def advance_round(room):
    if room.state["index"] + 1 == len(room.state["rounds"]):
        room.state.update(phase="final", next_ready=[])
    else:
        room.state["index"] += 1
        if (
            room.state["mode"] == "mix"
            and room.current()["mode"] == "sales"
            and room.state["history"][0]["answers"]
        ):
            hit = max(room.state["history"][0]["answers"], key=lambda a: a["points"])[
                "text"
            ]
            room.current().update(
                prompt="Продай бенгер первого раунда!",
                context="Преврати эту шутку в товар ночного телемагазина и придумай рекламу.",
                callback=hit,
            )
        room.begin_round()


def progress(room):
    if room.state["phase"] == "reveal":
        if room.active() and all(
            (p["id"] in room.state.get("next_ready", []) for p in room.active())
        ):
            room.advance_round()
        return
    phase = room.state["phase"]
    if phase not in ("briefing", "answer", "caption", "vote"):
        return
    r = room.current()
    if phase == "briefing":
        if pending_jobs(r):
            return
        shared = r["image_jobs"]["shared"]
        if shared.get("image"):
            r["shared_image"] = shared["image"]
            room.state.update(phase="answer", deadline=room.clock() + ROUND_SECONDS)
        else:
            room.reveal()
        return
    timeout = room.clock() >= room.state["deadline"]
    eligible = room.active()
    if phase == "answer" and timeout:
        jobs = r.get("image_jobs", {})
        if any(
            (
                jobs.get(p["id"], {}).get("edit_until", 0) > room.clock()
                for p in eligible
            )
        ):
            return
    if phase == "answer" and kind(r, catalog=room.catalog) == "relay":
        eligible = [p for p in eligible if p["id"] in r["relay_pairs"]]
        jobs = r["image_jobs"]
        if pending_jobs(r):
            return
        if timeout or all(
            (p["id"] in jobs and jobs[p["id"]]["status"] == "done" for p in eligible)
        ):
            room.state.update(phase="caption", deadline=room.clock() + ROUND_SECONDS)
            room.progress()
        return
    if phase == "caption":
        eligible = [p for p in eligible if room.caption_assignment(r, p["id"])]
    if phase in ("answer", "caption"):
        if pending_jobs(r):
            return
        submitted = {a["player"] for a in r["answers"]}
        if timeout or all((p["id"] in submitted for p in eligible)):
            room.rng.shuffle(r["answers"])
            if len(r["answers"]) < 2:
                room.reveal()
            else:
                room.state.update(phase="vote", deadline=room.clock() + ROUND_SECONDS)
    elif phase == "vote":
        eligible = [
            p
            for p in eligible
            if any((p["id"] not in authors(a) for a in r["answers"]))
        ]
        if timeout or all((p["id"] in r["votes"] for p in eligible)):
            room.reveal()


def start(room, token):
    room.host(token)
    if room.state["phase"] not in ("lobby", "final"):
        fail("Партия уже идёт")
    count = len(room.state["players"])
    if count < MIN_PLAYERS:
        fail("Для старта нужны хотя бы два игрока.")
    selected_mode = (
        room.state["mode"] if room.state["mode"] in room.catalog.mode_info else "mix"
    )
    if (
        selected_mode != "mix"
        and room.catalog.modes[selected_mode]["kind"] == "relay"
        and (count < 3)
    ):
        fail("Для эстафеты нужны хотя бы три игрока.")
    for offset in range(0, count, len(room.catalog.powers)):
        powers = room.rng.sample(list(room.catalog.powers), len(room.catalog.powers))
        for player, power in zip(
            room.state["players"][offset : offset + len(room.catalog.powers)], powers
        ):
            player.update(score=0, spent=False, waiting=False, power=power)
    playlist = [
        mode
        for mode in room.catalog.mix_modes
        if count >= 3 or room.catalog.modes[mode]["kind"] != "relay"
    ]
    alternatives = [
        mode
        for mode in playlist
        if mode not in ("excuses", "sales", "dialogue", "appeal")
    ]
    if (
        selected_mode == "mix"
        and {"dialogue", "appeal"}.issubset(playlist)
        and room.rng.choice((False, True))
    ):
        first, second = (playlist.index("dialogue"), playlist.index("appeal"))
        playlist[first], playlist[second] = (playlist[second], playlist[first])
    for group in {room.catalog.modes[mode]["kind"] for mode in alternatives}:
        positions = [
            index
            for index, mode in enumerate(playlist)
            if mode in alternatives and room.catalog.modes[mode]["kind"] == group
        ]
        shuffled = room.rng.sample(
            [playlist[index] for index in positions], len(positions)
        )
        for index, mode in zip(positions, shuffled):
            playlist[index] = mode
    cast = room.rng.sample(room.state["players"], count)
    rounds = []
    for index in range(room.state["count"]):
        mode = (
            selected_mode if selected_mode != "mix" else playlist[index % len(playlist)]
        )
        pool = [
            row
            for row in room.catalog.prompts[mode]
            if row["id"] not in room.state["used"]
        ]
        if not pool:
            identifiers = {row["id"] for row in room.catalog.prompts[mode]}
            room.state["used"] = [
                value for value in room.state["used"] if value not in identifiers
            ]
            pool = room.catalog.prompts[mode]
        themed = [row for row in pool if row.get("twists")]
        row = copy.deepcopy(room.rng.choice(themed or pool))
        if row.get("twists"):
            row["context"] += " " + room.rng.choice(row.pop("twists"))
        if index % 2 == 0 and "{player}" not in row["context"]:
            row["context"] = "В главной роли: {player}. " + row["context"]
        row["context"] = row["context"].replace("{player}", cast[index % count]["name"])
        room.state["used"].append(row["id"])
        row.update(
            mode=mode,
            kind=room.catalog.modes[mode]["kind"],
            mode_info=room.catalog.mode_info[mode],
            is_image=mode in room.catalog.image_modes,
            round_id=uuid.uuid4().hex,
            answers_demo=row.pop("answers", []),
        )
        rounds.append(row)
    room.state.update(rounds=rounds, index=0, history=[], mode=selected_mode)
    room.begin_round()


def next(room, token, round_id, force=False):
    player = room.player(token)
    if (
        room.state["phase"] != "reveal"
        or player.get("waiting")
        or round_id != room.current()["round_id"]
    ):
        fail("Этот раунд уже завершён или результаты ещё не раскрыты")
    if force:
        room.host(token)
        room.advance_round()
    else:
        ready = room.state.setdefault("next_ready", [])
        if player["id"] not in ready:
            ready.append(player["id"])
        room.progress()


def lobby(room, token):
    room.host(token)
    room.state.update(
        phase="lobby", deadline=None, rounds=[], history=[], next_ready=[]
    )
    for player in room.state["players"]:
        player.update(waiting=False, score=0)
