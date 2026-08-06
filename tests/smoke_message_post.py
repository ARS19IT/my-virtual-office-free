#!/usr/bin/env python3
"""Local smoke test for the agent composer POST route.

The server's explicit local mock mode prevents any Gateway/provider call.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

OPENER = build_opener(ProxyHandler({}))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED = {
    "main": "a6api",
    "2": "a6api-analitik",
    "team": "a6api-developer",
    "dising": "a6api",
    "memory": "a6api-memory",
    "worker": "a6api-worker",
    "designer": "a6api-designer",
}


def call(url, method="GET", payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = Request(url, data=body, method=method, headers={"Content-Type": "application/json"})
    try:
        with OPENER.open(req, timeout=15) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    port = free_port()
    ws_port = free_port()
    with tempfile.TemporaryDirectory(prefix="vo-message-smoke-") as status_dir:
        env = os.environ.copy()
        env.update({
            "VO_PORT": str(port),
            "VO_WS_PORT": str(ws_port),
            "VO_STATUS_DIR": status_dir,
            "VO_OPENCLAW_PATH": os.path.expanduser("~/.openclaw"),
            "VO_LOCAL_MESSAGE_MOCK": "1",
            "VO_FREE_FORK": "1",
        })
        proc = subprocess.Popen([sys.executable, "app/server.py"], cwd=ROOT, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.time() + 45
            while time.time() < deadline:
                try:
                    status, health = call(f"http://127.0.0.1:{port}/health")
                    if status == 200 and health.get("ok"):
                        break
                except Exception:
                    time.sleep(0.2)
            else:
                try:
                    stdout, stderr = proc.communicate(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    stdout, stderr = proc.communicate(timeout=5)
                raise AssertionError(
                    "server did not become healthy\n"
                    + stdout.decode(errors="replace")
                    + stderr.decode(errors="replace")
                )

            status, roster = call(f"http://127.0.0.1:{port}/api/agents")
            assert status == 200, roster
            agents = {agent["id"]: agent for agent in roster["agents"]}
            assert set(agents) == set(EXPECTED), sorted(agents)
            for agent_id, provider in EXPECTED.items():
                model = agents[agent_id].get("model")
                model_id = model.get("primary", "") if isinstance(model, dict) else str(model or "")
                assert model_id.startswith(provider + "/"), (agent_id, model_id, provider)
                status, result = call(
                    f"http://127.0.0.1:{port}/api/agent-platform-communications/send",
                    "POST",
                    {"fromType": "ui", "fromId": "user", "toAgentId": agent_id,
                     "message": f"smoke message to {agent_id}", "sourceApp": "smoke"},
                )
                assert status == 200 and result.get("ok"), (agent_id, status, result)
                assert result["to"]["id"] == agent_id
                assert "[MOCK REPLY]" in result["reply"]
            print("PASS: POST message delivery mocked for 7 agents; provider/model names verified")
        finally:
            proc.terminate()
            proc.wait(timeout=10)


if __name__ == "__main__":
    main()
