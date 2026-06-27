"""Tiny in-memory event bus the two-lane console reads.

Every step of a scenario appends an event tagged with its lane ("inbound" or
"outbound"). The console polls snapshot() and renders identity -> score+signals
-> credential lifecycle per lane. Thread-safe so the stdlib HTTP server can append
from request threads while the console polls.
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Event:
    lane: str           # "inbound" | "outbound"
    type: str           # "identity" | "score" | "credential" | "booking" | "blocked" | "note"
    title: str
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


class EventBus:
    def __init__(self) -> None:
        self._events: list[Event] = []
        self._lock = threading.Lock()

    def emit(self, lane: str, type: str, title: str, detail: str = "", **data: Any) -> Event:
        ev = Event(lane=lane, type=type, title=title, detail=detail, data=data)
        with self._lock:
            self._events.append(ev)
        return ev

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [asdict(e) for e in self._events]

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
