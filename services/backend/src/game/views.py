from __future__ import annotations
import copy
from .state import authors, kind


def summary(room):
    return dict(
        code=room.code,
        name=room.name,
        phase=room.state["phase"],
        players=len(room.state["players"]),
        capacity=room.capacity(),
        mode=room.state["mode"],
        count=room.state["count"],
    )


def view(room, token):
    p = next((p for p in room.state["players"] if p["token"] == token), None)
    visible = copy.deepcopy(room.state)
    visible.pop("host", None)
    visible.pop("claimed", None)
    visible.pop("code", None)
    visible.pop("used", None)
    for x in visible["players"]:
        x.pop("token")
        x.pop("power", None)
    visible["room_code"] = room.code
    visible["room_name"] = room.name
    visible["rounds"] = []
    visible["capacity"] = room.capacity()
    visible["me"] = (
        None
        if not p
        else {
            **{k: v for k, v in p.items() if k != "token"},
            "power_info": room.catalog.powers[p["power"]],
        }
    )
    visible["is_leader"] = bool(
        p and room.leader() and (p["id"] == room.leader()["id"])
    )
    visible["leader_name"] = room.leader()["name"] if room.leader() else None
    visible["next_ready"] = room.state.get("next_ready", [])
    visible["mode"] = (
        room.state["mode"] if room.state["mode"] in room.catalog.mode_info else "mix"
    )
    visible["round"] = None
    visible["generating"] = False
    visible["image_error"] = None
    visible["image_pending"] = 0
    if room.state["rounds"]:
        r = copy.deepcopy(room.current())
        assignment = (
            room.caption_assignment(r, p["id"])
            if p and room.state["phase"] == "caption"
            else None
        )
        jobs = r.pop("image_jobs", {})
        r.pop("relay_pairs", None)
        r.pop("scene", None)
        r.pop("answers_demo", None)
        r["kind"] = kind(r, catalog=room.catalog)
        own_job = jobs.get(p["id"], {}) if p else {}
        visible["generating"] = own_job.get("status") == "queued"
        visible["image_error"] = own_job.get("error") or jobs.get("shared", {}).get(
            "error"
        )
        if room.state["phase"] == "answer" and own_job.get("edit_until"):
            visible["deadline"] = max(visible["deadline"], own_job["edit_until"])
        visible["image_retry"] = visible["generating"] and own_job.get("retries", 0) > 0
        visible["image_pending"] = sum(
            (job["status"] == "queued" for job in jobs.values())
        )
        visible["caption_image"] = assignment[1] if assignment else None
        if room.state["phase"] == "caption":
            visible["caption_total"] = sum(
                (
                    bool(room.caption_assignment(room.current(), player["id"]))
                    for player in room.active()
                )
            )
        if room.state["phase"] in ("briefing", "answer", "caption"):
            r["answers"] = [a for a in r["answers"] if p and a["player"] == p["id"]]
            r["votes"] = {}
            r["effects"] = {}
        elif room.state["phase"] == "vote":
            for a in r["answers"]:
                a["own"] = bool(p and p["id"] in authors(a))
                a.pop("player")
                a.pop("partner", None)
            r["votes"] = {}
            r["effects"] = {}
        visible["round"] = r
        visible["ready"] = (
            len(room.current()["answers"])
            if room.state["phase"] in ("answer", "caption")
            else len(room.current()["votes"])
        )
        if kind(r, catalog=room.catalog) == "relay" and room.state["phase"] == "answer":
            visible["ready"] = sum((job["status"] == "done" for job in jobs.values()))
        visible["submitted"] = bool(
            p
            and (
                any((a["player"] == p["id"] for a in room.current()["answers"]))
                or (
                    kind(r, catalog=room.catalog) == "relay"
                    and room.state["phase"] == "answer"
                    and (own_job.get("status") == "done")
                )
            )
        )
        visible["voted"] = bool(p and p["id"] in room.current()["votes"])
    return visible
