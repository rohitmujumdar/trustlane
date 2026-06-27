"""Two-lane console server — standard library only, no pip install.

  python server.py        # then open http://localhost:8000

Serves the console and exposes a tiny API the front-end polls:
  GET  /api/state         -> all events so far (JSON)
  POST /api/run/{1|2|3}   -> fire a pre-staged scenario through engine + gate
  POST /api/reset         -> clear the board

Everything runs deterministically off the rule-based engine and the mock vault,
so it is safe to drive live on stage (handoff section 8).
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agent_loop import run_scenario
from credential_gate import CredentialGate
from events import EventBus
from scenarios import all_scenarios

BUS = EventBus()
GATE = CredentialGate()  # mock vault unless OP_SERVICE_ACCOUNT_TOKEN is set
CONSOLE = Path(__file__).parent / "console" / "index.html"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet the default request logging
        pass

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(200, CONSOLE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            body = json.dumps({"events": BUS.snapshot()}).encode()
            self._send(200, body, "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        if self.path == "/api/reset":
            BUS.reset()
            self._send(200, b'{"ok":true}', "application/json")
            return
        if self.path.startswith("/api/run/"):
            key = self.path.rsplit("/", 1)[-1]
            scenarios = all_scenarios()
            if key not in scenarios:
                self._send(404, b'{"ok":false}', "application/json")
                return
            run_scenario(scenarios[key], GATE, BUS)
            self._send(200, b'{"ok":true}', "application/json")
            return
        self._send(404, b"not found", "text/plain")


def main(port: int = 8077) -> None:
    mode = "LIVE 1Password vault" if GATE.live else "mock vault (no token)"
    print(f"TrustLane console on http://localhost:{port}   [{mode}]")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
