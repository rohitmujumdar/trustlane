"""Central tunables. This is the file you tweak during the hackathon.

Rename PROJECT_NAME once you pick a real name, then rename the package folder.
"""
from __future__ import annotations

PROJECT_NAME = "trustgate"  # placeholder

# Trust score (0..100) thresholds, checked high -> low.
# A request's score lands in the first band whose threshold it clears.
BANDS = [
    (80, "allow"),    # full scoped credential
    (60, "narrow"),   # reduced scope + short TTL
    (40, "approve"),  # human in the loop
    (0,  "deny"),     # refused, nothing released
]

# Credential time-to-live (seconds) per policy band.
TTL = {
    "allow": 300,
    "narrow": 60,
    "approve": 60,
    "deny": 0,
}

# action name -> blast-radius sensitivity (0.0 harmless .. 1.0 catastrophic).
# Anything not listed defaults to 0.5.
SENSITIVITY = {
    "read": 0.1,
    "list": 0.1,
    "search": 0.1,
    "send_email": 0.4,
    "update_record": 0.5,
    "deploy": 0.7,
    "delete": 0.85,
    "wire_transfer": 0.95,
    "export_pii": 0.95,
}
