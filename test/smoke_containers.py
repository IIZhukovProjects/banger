"""Exercise an already running LOCAL fake-provider stack through nginx."""

import argparse
import io
import json
import time
import uuid
from urllib.parse import urlsplit
import httpx
from PIL import Image
from smoke_local import require


def run(base, llm):
    for url in (base, llm):
        assert urlsplit(url).hostname in ("127.0.0.1", "localhost"), "Local stack only"
    checks = {}
    idempotency_key = "smoke-" + uuid.uuid4().hex
    with httpx.Client(
        base_url=base,
        timeout=10,
        trust_env=False,
    ) as api, httpx.Client(
        base_url=llm,
        timeout=10,
        trust_env=False,
    ) as images:
        incoming_trace = uuid.uuid4().hex
        response = api.get(
            "/api/meta",
            headers={
                "traceparent": "00-" + incoming_trace + "-0123456789abcdef-01",
                "tracestate": "platform=test",
            },
        )
        assert response.headers.get("X-Trace-Id") == incoming_trace
        checks["nginxIngressTraceContext"] = True
        meta = require(api.get("/api/meta"))
        assert len(meta["modes"]) == 16
        assert meta["image_provider"] == "fake", "Smoke requires fake provider"
        a = require(
            api.post(
                "/api/rooms",
                json={"name": "А", "mode": "excuses", "count": 1, "capacity": 2},
            ),
            201,
        )
        b = require(
            api.post(
                "/api/rooms",
                json={"name": "Б", "mode": "clue", "count": 1, "capacity": 2},
            ),
            201,
        )

        def join(room, name):
            token = require(
                api.post(
                    "/api/join",
                    headers={"X-Room-Code": room["code"]},
                    json={"name": name},
                )
            )["token"]
            return {"X-Room-Code": room["code"], "Authorization": token}

        players_a = [join(a, name) for name in ("Ведущий", "Друг")]
        players_b = [join(b, name) for name in ("Ведущий", "Друг")]
        assert (
            api.post(
                "/api/settings", headers=players_a[1], json={"mode": "sales"}
            ).status_code
            == 403
        )
        assert (
            api.post(
                "/api/leave", headers={**players_a[0], "X-Room-Code": b["code"]}
            ).status_code
            == 401
        )
        require(api.post("/api/start", headers=players_a[0]))
        state = require(api.get("/api/state", headers=players_a[0]))
        rid = state["round"]["round_id"]
        for index, headers in enumerate(players_a):
            require(
                api.post(
                    "/api/answer",
                    headers=headers,
                    json={"round_id": rid, "text": "Секретный ответ " + str(index)},
                )
            )
            if index == 0:
                assert (
                    require(api.get("/api/state", headers={"X-Room-Code": a["code"]}))[
                        "round"
                    ]["answers"]
                    == []
                )
        assert (
            api.post(
                "/api/answer",
                headers=players_a[0],
                json={"round_id": rid, "text": "duplicate"},
            ).status_code
            == 400
        )
        for headers in players_a:
            state = require(api.get("/api/state", headers=headers))
            own = next(item for item in state["round"]["answers"] if item["own"])
            assert (
                api.post(
                    "/api/vote",
                    headers=headers,
                    json={"round_id": rid, "answer": own["id"]},
                ).status_code
                == 400
            )
            target = next(item for item in state["round"]["answers"] if not item["own"])
            require(
                api.post(
                    "/api/vote",
                    headers=headers,
                    json={"round_id": rid, "answer": target["id"]},
                )
            )
        state = require(api.get("/api/state", headers=players_a[0]))
        assert (
            state["phase"] == "reveal"
            and sum(item["score"] for item in state["players"]) == 2
        )
        assert all("token" not in player for player in state["players"])
        require(
            api.post(
                "/api/next",
                headers=players_a[0],
                json={"round_id": rid, "force": True},
            )
        )
        assert require(api.get("/api/state", headers=players_a[0]))["phase"] == "final"
        checks["roomsAuthorityPrivacyScoring"] = True
        raw = io.BytesIO()
        Image.new("RGBA", (10, 10), (50, 100, 200, 0)).save(raw, "PNG")
        uploaded = require(
            api.post(
                "/api/upload",
                headers=players_a[0],
                files={"file": ("image.png", raw.getvalue(), "image/png")},
            )
        )
        assert api.get(uploaded["url"]).content == raw.getvalue()
        require(api.post("/api/start", headers=players_b[0]))
        image_round = require(api.get("/api/state", headers=players_b[0]))["round"][
            "round_id"
        ]
        assert (
            api.post(
                "/api/answer",
                headers=players_b[0],
                json={"round_id": image_round, "image": uploaded["url"]},
            ).status_code
            == 400
        )
        checks["s3UploadsAndRoomIsolation"] = True
        for index, headers in enumerate(players_b):
            payload = {
                "round_id": image_round,
                "text": "Кот из пластилина " + str(index),
            }
            require(api.post("/api/generate", headers=headers, json=payload), 202)
            require(api.post("/api/generate", headers=headers, json=payload), 202)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = require(api.get("/api/state", headers=players_b[0]))
            if state["phase"] == "vote":
                break
            time.sleep(0.25)
        assert state["phase"] == "vote", "Fake image workflow did not reach voting"
        assert len(state["round"]["answers"]) == 2
        for answer in state["round"]["answers"]:
            response = api.get(answer["image"])
            assert response.status_code == 200
            with Image.open(io.BytesIO(response.content)) as image:
                assert image.mode == "RGBA"
        checks["backendToLlmDurableFakeImages"] = True
        payload = {"prompt": "Идемпотентная картинка"}
        first = require(
            images.post(
                "/internal/v1/image-jobs",
                headers={"Idempotency-Key": idempotency_key},
                json=payload,
            ),
            202,
        )
        repeat = require(
            images.post(
                "/internal/v1/image-jobs",
                headers={"Idempotency-Key": idempotency_key},
                json=payload,
            ),
            202,
        )
        assert first["id"] == repeat["id"]
        assert (
            images.post(
                "/internal/v1/image-jobs",
                headers={"Idempotency-Key": idempotency_key},
                json={"prompt": "Другой запрос"},
            ).status_code
            == 409
        )
        checks["llmIdempotencyAndConflict"] = True
    return checks


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--llm-url", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.url, args.llm_url)))
