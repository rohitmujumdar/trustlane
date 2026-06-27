"""Blocked-action notification — the 'we stopped it' alert.

Posts to Slack if SLACK_WEBHOOK_URL is set; otherwise a silent no-op (the console
toast is the always-on visual). Stdlib only, with a short timeout so a slow/missing
webhook never stalls the demo.
"""
from __future__ import annotations

import json
import os
import urllib.request


def notify_blocked(label: str, score: int) -> bool:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return False
    text = f":no_entry: TrustLane blocked an action (score {score}) — {label}"
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False  # never let a notification failure break the demo
