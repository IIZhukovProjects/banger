from __future__ import annotations
import uuid
from .state import authors, kind


def bot_step(room):
    if room.state["phase"] == "reveal":
        for p in room.active():
            if p.get("bot") and p["id"] not in room.state.setdefault("next_ready", []):
                room.state["next_ready"].append(p["id"])
        return
    if room.state["phase"] not in ("answer", "caption", "vote"):
        return
    r = room.current()
    for p in room.active():
        if not p.get("bot"):
            continue
        if kind(r, catalog=room.catalog) == "relay" and room.state["phase"] == "answer":
            r["image_jobs"].setdefault(
                p["id"], {"status": "done", "image": f"/assets/demo-{p['bot'] % 5}.png"}
            )
            continue
        if room.state["phase"] == "caption":
            assignment = room.caption_assignment(r, p["id"])
            if assignment and (not any((a["player"] == p["id"] for a in r["answers"]))):
                partner, image = assignment
                room.accept_answer(
                    r,
                    p,
                    "Согласно протоколу, так и было задумано.",
                    image,
                    partner=partner,
                )
            continue
        if room.state["phase"] == "answer" and (
            not any((a["player"] == p["id"] for a in r["answers"]))
        ):
            choices = r.get("answers_demo") or [
                "Это была бесплатная пробная версия реальности.",
                "Мама сказала, что так надёжнее.",
                "Всё по плану. Просто план у хомяка.",
            ]
            text = choices[p["bot"] % len(choices)]
            text = text.get("text") if isinstance(text, dict) else text
            if room.catalog.modes.get(r["mode"], {}).get("fields"):
                dialogue = [
                    "— Почему у вас счёт на десятерых?\n— Это муха с цифровой семьёй.",
                    "— Вы кто по профессии?\n— Причина закрытия этого заведения.",
                    "— Ваш пропуск?\n— Я зашёл как бесплатный пробный период.",
                    "— Почему вы смеётесь?\n— Мне зарплату прислали в виде панчлайна.",
                ]
                appeals = [
                    "Съел квартальный отчёт.\nЯ проверял, есть ли в нём хоть что-то питательное.",
                    "Занял три стула.\nНа двух сидит моя самооценка.",
                    "Объявил себя директором.\nНа бейдже было свободное место.",
                    "Подделал рабочее настроение.\nНастоящее не прошло испытательный срок.",
                ]
                text = (appeals if r["mode"] == "appeal" else dialogue)[
                    (p["bot"] - 1) % 4
                ]
            r["answers"].append(
                dict(
                    id=uuid.uuid4().hex,
                    player=p["id"],
                    text=text,
                    image=(
                        f"/assets/demo-{p['bot'] % 5}.png"
                        if kind(r, catalog=room.catalog) == "image"
                        else None
                    ),
                )
            )
        elif room.state["phase"] == "vote" and p["id"] not in r["votes"]:
            options = [a for a in r["answers"] if p["id"] not in authors(a)]
            if options:
                r["votes"][p["id"]] = room.rng.choice(options)["id"]
