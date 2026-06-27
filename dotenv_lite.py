"""Minimal .env loader — no dependency, so the live demo "just works".

Loads KEY=VALUE lines from a .env file into os.environ without overriding values
already set in the real environment. Good enough for the hackathon; swap for
python-dotenv if you want the full feature set.
"""
from __future__ import annotations

import os
from pathlib import Path


def load_env(path: str | Path = ".env") -> bool:
    p = Path(path)
    if not p.exists():
        return False
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
    return True
