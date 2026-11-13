"""Explicit temporary PostgreSQL/S3 + backend/llm smoke. Never invokes Polza."""

import argparse
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid

import httpx
from PIL import Image
from sqlalchemy import text

from platform_codegen.infrastructure.commands import generate, compose
from platform_codegen.configuration.delivery import delivery
from platform_codegen.configuration.environment import service_documents
from platform_codegen.generation.apps import app_documents
from platform_codegen.generation.local_ingress import IMAGE, nginx_config
from platform_codegen.generation.services import generate_services
from platform_codegen.service.commands import migrate, context
from platform_codegen.service.scaffold import yaml_parser, serialize
from platform_codegen.runtime.database import Database


def free_port(used):
    while True:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        if port not in used:
            used.add(port)
            return port


def require(response, status=200):
    if response.status_code != status:
        raise AssertionError(
            f"HTTP {response.request.method} {response.request.url.path}: expected {status}, got {response.status_code}"
        )
    return response.json()


def run(source, proof=None, *, observability=False, frontend_image=None):
    parent = Path(
        tempfile.mkdtemp(
            dir=Path(tempfile.gettempdir()).resolve(), prefix="banger-full-smoke-"
        )
    )
    root = parent / "project"
    shutil.copytree(
        source,
        root,
        ignore=shutil.ignore_patterns(
            ".git",
            ".local",
            "infrastructure",
            "generated",
            "__pycache__",
            "node_modules",
            "dist",
        ),
    )
    parser = yaml_parser()
    used = set()
    ports = {
        name: free_port(used)
        for name in ("postgres", "s3", "grafana", "otlp_http", "otlp_grpc")
    }
    service_ports = {name: free_port(used) for name in ("backend", "llm")}
    p = root / "infrastructure.yaml"
    document = parser.load(p.read_text())
    document["infrastructure"]["modes"]["local"]["ports"] = ports
    p.write_text(serialize(parser, document))
    for name in service_ports:
        p = root / f"services/{name}/service.yaml"
        document = parser.load(p.read_text())
        document["service"]["server"]["http"]["port"] = service_ports[name]
        p.write_text(serialize(parser, document))
    generate(root)
    generate_services(root)
    processes = {}
    streams = []
    checks = {}
    ingress_trace = uuid.uuid4().hex
    traceparent = "00-" + ingress_trace + "-0123456789abcdef-01"
    frontend_container = None
    ingress_container = None

    def start(name):
        directory, configuration, environment = context(root, name, "local")
        environment["OBSERVABILITY_ENABLED"] = "true" if observability else "false"
        output = open(parent / (name + ".log"), "a", encoding="utf-8")
        streams.append(output)
        process = subprocess.Popen(
            [sys.executable, "-m", "generated"],
            cwd=directory,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        processes[name] = process
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(name + " process exited")
            try:
                if (
                    httpx.get(
                        f"http://127.0.0.1:{service_ports[name]}/readyz",
                        timeout=1,
                        trust_env=False,
                    ).status_code
                    == 200
                ):
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        raise AssertionError(name + " readiness timed out")

    def stop(name):
        process = processes.pop(name, None)
        if process:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise AssertionError(name + " did not shut down gracefully")

    try:
        core = (
            json.loads((root / "infrastructure/plan.json").read_text())["core"]
            if observability
            else ["pg-postgres", "s3"]
        )
        compose(root, "up", "--detach", "--wait", "--wait-timeout", "180", *core)
        compose(root, "run", "--rm", "--no-deps", "pg-postgres-init")
        compose(root, "run", "--rm", "--no-deps", "s3-init")
        for name in service_ports:
            migrate(root, name, "upgrade")
        checks["migrations"] = True
        seed_command = [
            sys.executable,
            str(root / "scripts/seed.py"),
            "--project",
            str(root),
        ]
        results = []
        for _ in range(2):
            result = subprocess.run(
                seed_command, cwd=root, capture_output=True, text=True, timeout=30
            )
            assert result.returncode == 0, "Seed script failed"
            results.append(json.loads(result.stdout))
        assert results == [{"modes": 16, "prompts": 118, "powers": 5}] * 2
        checks["catalogSeedIdempotent"] = True
        # Runtime must use PostgreSQL, even when no seed data file is available.
        (root / "services/backend/src/game/catalog_seed.json").rename(
            root / "services/backend/src/game/catalog_seed.json.seeded"
        )

        start("llm")
        start("backend")
        checks["readiness"] = True
        checks["catalogReadFromDatabaseWithoutSeedFile"] = True
        if frontend_image:
            frontend_container = "cg-banger-browser-" + uuid.uuid4().hex[:10]
            frontend_port = free_port(used)
            namespace = next(
                line.split("=", 1)[1]
                for line in (root / ".local/infrastructure/compose.env")
                .read_text()
                .splitlines()
                if line.startswith("CG_COMPOSE_PROJECT=")
            )
            result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--detach",
                    "--name",
                    frontend_container,
                    "--network",
                    namespace + "_default",
                    "--network-alias",
                    "frontend",
                    frontend_image,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert result.returncode == 0, "Frontend container did not start"
            app, services = service_documents(root)
            _, routes = delivery(root, app, services, app_documents(root))
            config = nginx_config(routes["local"]).replace(
                "http://backend:", "http://host.docker.internal:"
            )
            ingress_file = parent / "ingress.conf"
            ingress_file.write_text(config)
            ingress_container = frontend_container + "-ingress"
            result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--detach",
                    "--name",
                    ingress_container,
                    "--network",
                    namespace + "_default",
                    "--add-host",
                    "host.docker.internal:host-gateway",
                    "--publish",
                    f"127.0.0.1:{frontend_port}:80",
                    "--volume",
                    f"{ingress_file}:/etc/nginx/conf.d/default.conf:ro",
                    IMAGE,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert result.returncode == 0, "Ingress container did not start"
            url = f"http://127.0.0.1:{frontend_port}"
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    if httpx.get(url + "/api/meta", trust_env=False).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
            assert httpx.get(url + "/api/meta", trust_env=False).status_code == 200, (
                "Nginx proxy failed"
            )
            with httpx.Client(base_url=url, trust_env=False) as public:
                for path in ("/internal/v1/image-jobs", "/api/internal/v1/image-jobs"):
                    response = public.post(path, json={"prompt": "blocked"})
                    assert response.status_code in (404, 405), path
            checks["nginxProxy"] = True
            checks["llmRoutesUnavailableThroughNginx"] = True
            output = (
                proof.parent / "browser-artifacts"
                if proof
                else parent / "browser-artifacts"
            )
            browser_python = os.environ.get("BROWSER_TEST_PYTHON", sys.executable)
            browser = subprocess.run(
                [
                    browser_python,
                    str(Path(__file__).with_name("browser_smoke.py")),
                    "--url",
                    url,
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
                timeout=90,
            )
            if browser.returncode:
                raise AssertionError("Browser smoke failed: " + browser.stderr[-3000:])
            checks["browser"] = json.loads(browser.stdout)
        with (
            httpx.Client(
                base_url=f"http://127.0.0.1:{service_ports['backend']}",
                timeout=10,
                trust_env=False,
            ) as api,
            httpx.Client(
                base_url=f"http://127.0.0.1:{service_ports['llm']}",
                timeout=10,
                trust_env=False,
            ) as images,
        ):
            meta = require(api.get("/api/meta"))
            assert len(meta["modes"]) == 16
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
                        require(
                            api.get("/api/state", headers={"X-Room-Code": a["code"]})
                        )["round"]["answers"]
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
                target = next(
                    item for item in state["round"]["answers"] if not item["own"]
                )
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
            assert (
                require(api.get("/api/state", headers=players_a[0]))["phase"] == "final"
            )
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
                headers = {
                    **headers,
                    "traceparent": traceparent,
                    "tracestate": "platform=test",
                }
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
                    headers={"Idempotency-Key": "smoke-idempotency"},
                    json=payload,
                ),
                202,
            )
            repeat = require(
                images.post(
                    "/internal/v1/image-jobs",
                    headers={"Idempotency-Key": "smoke-idempotency"},
                    json=payload,
                ),
                202,
            )
            assert first["id"] == repeat["id"]
            assert (
                images.post(
                    "/internal/v1/image-jobs",
                    headers={"Idempotency-Key": "smoke-idempotency"},
                    json={"prompt": "Другой запрос"},
                ).status_code
                == 409
            )
            checks["llmIdempotencyAndConflict"] = True
            stop("backend")
            start("backend")
            assert (
                require(api.get("/api/state", headers=players_a[0]))["phase"] == "final"
            )
            assert (
                require(api.get("/api/state", headers=players_b[0]))["phase"] == "vote"
            )
            checks["backendRestartPersistence"] = True
            stop("llm")
            _, _, environment = context(root, "llm", "local")
            recovered_id, unknown_id = str(uuid.uuid4()), str(uuid.uuid4())

            async def seed_recovery():
                database = Database(environment["DATABASE_URL"])
                try:
                    async with database.transaction() as session:
                        for ident, provider in (
                            (recovered_id, "fake"),
                            (unknown_id, "polza"),
                        ):
                            now = time.time()
                            await session.execute(
                                text(
                                    """INSERT INTO image_jobs (id,idempotency_key,fingerprint,prompt,provider,model,phase,status,created_at,updated_at,lease_until,next_attempt,attempts,trace_context)
                                VALUES (:id,:key,:fingerprint,:prompt,:provider,:model,'submitting','running',:now,:now,0,0,0,CAST(:trace_context AS jsonb))"""
                                ),
                                {
                                    "id": ident,
                                    "key": "recovery-" + ident,
                                    "fingerprint": hashlib.sha256(
                                        b"recover"
                                    ).hexdigest(),
                                    "prompt": "recover",
                                    "trace_context": json.dumps(
                                        {
                                            "traceparent": traceparent,
                                            "tracestate": "platform=test",
                                        }
                                    ),
                                    "provider": provider,
                                    "model": "unused",
                                    "now": now,
                                },
                            )
                finally:
                    await database.close()

            asyncio.run(seed_recovery())
            start("llm")
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                recovered = require(
                    images.get("/internal/v1/image-jobs/" + recovered_id)
                )
                unknown = require(images.get("/internal/v1/image-jobs/" + unknown_id))
                if (
                    recovered["status"] == "succeeded"
                    and unknown["status"] == "needs_reconciliation"
                ):
                    break
                time.sleep(0.2)
            assert (
                recovered["status"] == "succeeded"
                and unknown["status"] == "needs_reconciliation"
            )
            checks["jobRecoveryAndNoBlindPaidResubmit"] = True
            for name in ("backend", "llm"):
                stop(name)
            checks["gracefulShutdown"] = True
            if observability:
                admin = json.loads(
                    (root / ".local/infrastructure/admin.json").read_text()
                )["grafana"]
                with httpx.Client(
                    base_url=f"http://127.0.0.1:{ports['grafana']}",
                    auth=(admin["username"], admin["password"]),
                    timeout=10,
                    trust_env=False,
                ) as grafana:
                    deadline = time.monotonic() + 60
                    while time.monotonic() < deadline:
                        try:
                            sources = grafana.get("/api/datasources")
                            if sources.status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(0.5)
                    assert {entry["uid"] for entry in sources.json()} >= {
                        "loki",
                        "tempo",
                        "prometheus",
                    }
                    observed = {
                        "logs": False,
                        "traces": False,
                        "metrics": False,
                        "durable_trace": False,
                        "business_metrics": False,
                    }
                    deadline = time.monotonic() + 60
                    while time.monotonic() < deadline and not all(observed.values()):
                        result = grafana.get(
                            "/api/datasources/proxy/uid/loki/loki/api/v1/query_range",
                            params={"query": '{service_name="backend"}', "limit": "20"},
                        )
                        if result.status_code == 200:
                            observed["logs"] = bool(
                                result.json().get("data", {}).get("result")
                            )
                        result = grafana.get(
                            "/api/datasources/proxy/uid/tempo/api/search",
                            params={"tags": "service.name=backend"},
                        )
                        if result.status_code == 200:
                            observed["traces"] = bool(result.json().get("traces"))
                        result = grafana.get(
                            "/api/datasources/proxy/uid/prometheus/api/v1/query",
                            params={
                                "query": 'sum({__name__=~"http_server_request_duration.*count",service_name="backend"})'
                            },
                        )
                        if result.status_code == 200:
                            values = result.json().get("data", {}).get("result", [])
                            observed["metrics"] = bool(
                                values and float(values[0]["value"][1]) > 0
                            )
                        result = grafana.get(
                            "/api/datasources/proxy/uid/tempo/api/traces/"
                            + ingress_trace
                        )
                        if result.status_code == 200:

                            def collect_names(value):
                                if isinstance(value, dict):
                                    names = (
                                        {value["name"]}
                                        if isinstance(value.get("name"), str)
                                        else set()
                                    )
                                    return names.union(
                                        *(collect_names(v) for v in value.values())
                                    )
                                if isinstance(value, list):
                                    return set().union(
                                        *(collect_names(v) for v in value)
                                    )
                                return set()

                            names = collect_names(result.json())
                            observed["durable_trace"] = {
                                "image.outbox.process",
                                "image.job.process",
                                "storage.s3.put",
                            } <= names
                        result = grafana.get(
                            "/api/datasources/proxy/uid/prometheus/api/v1/query",
                            params={
                                "query": 'sum({__name__=~"service_operation_calls.*",operation=~"image.job.process|storage.s3.put"})'
                            },
                        )
                        if result.status_code == 200:
                            values = result.json().get("data", {}).get("result", [])
                            observed["business_metrics"] = bool(
                                values and float(values[0]["value"][1]) > 0
                            )
                        if not all(observed.values()):
                            time.sleep(1)
                    assert all(observed.values()), (
                        "Missing observability signals: " + str(observed)
                    )
                    checks["grafanaLogsTracesMetrics"] = True
                    checks["ingressTraceThroughDurableJobsAndS3"] = True
                    checks["businessMetricsExported"] = True
        pools = json.loads(
            (root / ".local/infrastructure/credentials.json").read_text()
        )
        for path in root.rglob("*"):
            if path.is_file() and ("generated" in path.parts or path.suffix == ".log"):
                content = path.read_bytes()
                assert all(value.encode() not in content for value in pools.values()), (
                    "Secret found in generated output or logs"
                )
        checks["noCredentialsInGeneratedOrLogs"] = True
        if proof:
            proof.write_text(json.dumps(checks, indent=2) + "\n")
        print(json.dumps(checks))
        return checks
    except Exception as error:
        # Only fake test credentials exist here; still redact every generated password in diagnostics.
        passwords = json.loads(
            (root / ".local/infrastructure/credentials.json").read_text()
        ).values()
        for name in ("backend", "llm"):
            path = parent / (name + ".log")
            if path.exists():
                tail = path.read_text()[-12000:]
                for value in passwords:
                    tail = tail.replace(value, "[redacted]")
                print(name + " diagnostic:\n" + tail, file=sys.stderr)
        print("Temporary test project: " + str(root), file=sys.stderr)
        raise
    finally:
        for name in list(processes):
            stop(name)
        for stream in streams:
            stream.close()
        for container in (ingress_container, frontend_container):
            if container:
                subprocess.run(
                    ["docker", "rm", "--force", container],
                    capture_output=True,
                    timeout=30,
                )
        compose(root, "down", "--volumes")
        if all(
            checks.get(key)
            for key in ("gracefulShutdown", "noCredentialsInGeneratedOrLogs")
        ):
            shutil.rmtree(parent)


if __name__ == "__main__":
    arguments = argparse.ArgumentParser()
    arguments.add_argument("--project", type=Path, required=True)
    arguments.add_argument("--proof", type=Path)
    arguments.add_argument("--observability", action="store_true")
    arguments.add_argument("--frontend-image")
    args = arguments.parse_args()
    run(
        args.project,
        args.proof,
        observability=args.observability,
        frontend_image=args.frontend_image,
    )
