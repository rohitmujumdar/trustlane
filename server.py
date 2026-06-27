"""Two-lane console server — standard library only, no pip install.

  python server.py        # then open http://localhost:8000

Serves the console and exposes a tiny API the front-end polls:
  GET  /api/state         -> all events so far (JSON)
  POST /api/run/{1|2|3}   -> fire a pre-staged scenario through engine + gate
  POST /api/attack        -> Scenario 4: score a judge's typed attack live
  POST /api/reset         -> clear the board

Everything runs deterministically off the rule-based engine and the mock vault,
so it is safe to drive live on stage (handoff section 8).
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agent_loop import run_scenario
from attack import run_attack
from credential_gate import CredentialGate
from dotenv_lite import load_env
from events import EventBus
from notify import notify_blocked
from scenarios import all_scenarios
from trust_engine import Decision

load_env()  # so the console picks up OP_SERVICE_ACCOUNT_TOKEN / TRUSTLANE_SECRET_REF
BUS = EventBus()
GATE = CredentialGate(  # live vault when a token is set, mock otherwise
    secret_ref=os.environ.get("TRUSTLANE_SECRET_REF", "op://TrustLane/ExpediaPayment/credential")
)
CONSOLE = Path(__file__).parent / "console" / "index.html"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet the default request logging
        pass

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self._send(204, b"", "text/plain")

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
            sc = scenarios[key]
            run_scenario(sc, GATE, BUS)
            if sc.expect is Decision.BLOCK:
                notify_blocked(sc.title, sc.expect_score)
            self._send(200, b'{"ok":true}', "application/json")
            return
        if self.path == "/api/attack":
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            text = payload.get("text", "")
            verdict = run_attack(text, GATE, BUS, lane="outbound")
            if verdict.decision is Decision.BLOCK:
                notify_blocked(f"attack: {text[:48]}", verdict.score)
            self._send(200, b'{"ok":true}', "application/json")
            return
        self._send(404, b"not found", "text/plain")


def main(port: int = 8077) -> None:
    mode = "LIVE 1Password vault" if GATE.live else "mock vault (no token)"
    print(f"TrustLane console on http://localhost:{port}   [{mode}]")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
