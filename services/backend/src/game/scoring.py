from __future__ import annotations
import copy
from .state import authors


def reveal(room):
    r = room.current()
    if r["resolved"]:
        return
    r["resolved"] = True
    top_votes = max(
        (list(r["votes"].values()).count(a["id"]) for a in r["answers"]), default=0
    )
    for a in r["answers"]:
        voters = [pid for pid, target in r["votes"].items() if target == a["id"]]
        blocked = any(
            (
                e.get("target") == a["id"] and e["power"] == "block"
                for e in r["effects"].values()
            )
        )
        effects = []
        for pid in authors(a):
            effect = r["effects"].get(pid, {})
            if effect and effect.get("answer", a["id"]) == a["id"]:
                effects.append(effect["power"])
        a.update(
            voters=voters,
            blocked=blocked and "shield" not in effects,
            shield="shield" in effects,
            double="double" in effects,
            bank="bank" in effects,
            bonus="bonus" in effects,
        )
        points = len(voters) * (2 if a["double"] else 1)
        if a["bank"]:
            points = points * 3 if len(voters) == top_votes and top_votes > 0 else 0
        if a["bonus"] and voters:
            points += 1
        a["points"] = 0 if a["blocked"] or len(r["answers"]) < 2 else points
        for p in room.state["players"]:
            if p["id"] in authors(a):
                p["score"] += a["points"]
    room.state["history"].append(
        copy.deepcopy(
            {
                k: v
                for k, v in r.items()
                if k not in ("image_jobs", "relay_pairs", "scene")
            }
        )
    )
    room.state.update(phase="reveal", deadline=None)
