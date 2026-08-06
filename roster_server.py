#!/usr/bin/env python3
"""My Virtual Office Free - independent AGPL roster viewer backend."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).parent
OPENCLAW_HOME = Path(os.environ.get('VO_OPENCLAW_PATH', str(Path.home()/'.openclaw')))
PORT = int(os.environ.get('VO_PORT', '8092'))

sys.path.insert(0, str(ROOT/'app'))
from discovery import discover_agents  # noqa: E402


def load_agents():
    """Return the roster with inherited OpenClaw model defaults resolved."""
    agents = discover_agents(str(OPENCLAW_HOME))
    try:
        config = json.loads((OPENCLAW_HOME / "openclaw.json").read_text())
        default_model = config.get("agents", {}).get("defaults", {}).get("model", "")
    except (OSError, json.JSONDecodeError):
        default_model = ""

    for agent in agents:
        if not agent.get("model") and default_model:
            agent["model"] = {"primary": default_model, "fallbacks": []}
        if not agent.get("role") and agent.get("id") == "dising":
            agent["role"] = "визуальный дизайнер команды"
    return agents


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload, content_type="application/json"):
        if not isinstance(payload, (bytes, str)):
            payload = json.dumps(payload, ensure_ascii=False)
        body = payload if isinstance(payload, bytes) else payload.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = urlsplit(self.path).path.rstrip("/") or "/"
        try:
            if path in ("/health", "/api/agents", "/api/roster"):
                agents = load_agents()
                if path == "/health":
                    self._send(200, {"ok": True, "status": "running", "agents": len(agents)})
                elif path == "/api/agents":
                    self._send(200, {"agents": agents})
                else:
                    self._send(200, {"ok": True, "agents": agents})
                return
            if path in ("/", "/index.html"):
                self._send(200, (ROOT / "free-viewer.html").read_bytes(), "text/html; charset=utf-8")
                return
            self._send(404, {"ok": False, "error": "not_found", "path": path})
        except (OSError, json.JSONDecodeError) as exc:
            self._send(500, {"ok": False, "error": "roster_unavailable", "detail": str(exc)})

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
