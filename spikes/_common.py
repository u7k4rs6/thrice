"""Shared plumbing for the day-1 gates. Disposable."""
from __future__ import annotations

import json
import os
import pathlib
import time
import uuid
from typing import Any

BASE_URL = "https://api.getsolari.com"
SCRATCH = pathlib.Path(__file__).parent / "_scratch"
SCRATCH.mkdir(exist_ok=True)

# Starter plan caps (C1). The sandbox number is a platform limit.
MAX_SANDBOXES = 2
MAX_BROWSERS = 3

RATE_BROWSER_S = 0.10 / 3600.0
RATE_SANDBOX_S = 0.057 / 3600.0


def api_key() -> str:
    raw = os.environ.get("SOLARI_API_KEY", "").strip()
    if not raw:
        for line in (pathlib.Path(__file__).parents[1] / ".env").read_text().splitlines():
            if line.startswith("SOLARI_API_KEY="):
                raw = line.split("=", 1)[1].strip()
    if not raw or not raw.startswith("slr_live_"):
        raise SystemExit("SOLARI_API_KEY missing or malformed")
    return raw


def idem() -> str:
    """A fresh idempotency key. Every create call gets one."""
    return str(uuid.uuid4())


def redact(text: str) -> str:
    """Scrub the key and the preview pt_token before anything is printed."""
    import re
    text = re.sub(r"slr_live_[A-Za-z0-9_]+", "slr_live_[redacted]", text)
    text = re.sub(r"pt_token=[A-Za-z0-9._\-]+", "pt_token=[redacted]", text)
    return text


class Ledger:
    """Actual seconds consumed, so the report can compare against estimate."""

    def __init__(self) -> None:
        self.sandbox_seconds = 0.0
        self.browser_seconds = 0.0
        self.events: list[dict[str, Any]] = []

    def sandbox(self, label: str, seconds: float) -> None:
        self.sandbox_seconds += seconds
        self.events.append({"kind": "sandbox", "label": label, "seconds": round(seconds, 1)})

    def browser(self, label: str, seconds: float) -> None:
        self.browser_seconds += seconds
        self.events.append({"kind": "browser", "label": label, "seconds": round(seconds, 1)})

    def usd(self) -> float:
        return self.sandbox_seconds * RATE_SANDBOX_S + self.browser_seconds * RATE_BROWSER_S

    def summary(self) -> dict[str, Any]:
        return {
            "sandbox_seconds": round(self.sandbox_seconds, 1),
            "browser_seconds": round(self.browser_seconds, 1),
            "usd": round(self.usd(), 5),
            "events": self.events,
        }


def write(name: str, obj: Any) -> None:
    path = SCRATCH / name
    path.write_text(redact(json.dumps(obj, indent=2, default=str)))
    print(f"  -> {path}")


def emit(obj: Any) -> None:
    print(redact(json.dumps(obj, indent=2, default=str)))


class Timer:
    def __enter__(self):
        self.t0 = time.monotonic()
        return self

    def __exit__(self, *a):
        self.seconds = time.monotonic() - self.t0

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.t0
