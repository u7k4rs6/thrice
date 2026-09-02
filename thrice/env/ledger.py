"""Sandbox ledger: record every sandbox at creation, sweep at exit, assert zero live.

This is a correctness check, not a budget feature. The bug it exists to catch
is a sandbox the harness does not know it owns. That has happened twice:

  Day 3  acquire() created a sandbox internally, then failed before handing it
         back, so the caller's `finally` had nothing to kill. It billed for
         about ten minutes and was found only by a manual sweep.
  Day 4  A foreground run was killed by a two-minute shell timeout mid-attempt.
         No `finally` and no atexit hook runs when the process is killed, so
         again the leak was invisible until swept by hand.

The second case is why the ledger is on DISK rather than in memory. An
in-process registry dies with the process that leaked. A file survives, so the
next run (or `sweep`) can reap what the last one abandoned. The design rule:
the record is written BEFORE the sandbox is created, never after, because a
create that times out may still have created something.
"""

from __future__ import annotations

import atexit
import json
import os
import signal
import threading
import time
from pathlib import Path
from typing import Any

LEDGER_PATH = Path(os.environ.get("THRICE_LEDGER", Path.home() / ".thrice" / "sandboxes.jsonl"))

OPEN = "open"
CLOSED = "closed"


class LeakDetected(AssertionError):
    """Raised by assert_zero_live when the account still has live sandboxes."""


class SandboxLedger:
    def __init__(self, path: Path = LEDGER_PATH, api_key: str | None = None,
                 base_url: str = "https://api.getsolari.com") -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._lock = threading.Lock()
        self._installed = False
        self.events: list[dict[str, Any]] = []

    # ---------- recording ----------

    def _append(self, rec: dict[str, Any]) -> None:
        rec["ts"] = time.time()
        with self._lock, self.path.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self.events.append(rec)

    def intent(self, attempt_id: str, note: str = "") -> str:
        """Record the INTENT to create, before the API call.

        A create that times out or resets can still have created a sandbox that
        the client never learns the id of. Recording intent means the sweep at
        least knows to go looking, even when there is no id to record.
        """
        token = f"intent-{time.time_ns()}"
        self._append({"kind": "intent", "token": token, "attempt_id": attempt_id, "note": note})
        return token

    def opened(self, sandbox_id: str, attempt_id: str, token: str | None = None) -> None:
        self._append({"kind": OPEN, "sandbox_id": sandbox_id,
                      "attempt_id": attempt_id, "token": token})

    def closed(self, sandbox_id: str) -> None:
        self._append({"kind": CLOSED, "sandbox_id": sandbox_id})

    # ---------- reading ----------

    def open_ids(self) -> list[str]:
        """Sandbox ids recorded open and never recorded closed, across all runs."""
        if not self.path.exists():
            return []
        opened: list[str] = []
        closed: set[str] = set()
        for line in self.path.read_text().splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("kind") == OPEN and r.get("sandbox_id"):
                opened.append(r["sandbox_id"])
            elif r.get("kind") == CLOSED and r.get("sandbox_id"):
                closed.add(r["sandbox_id"])
        seen, out = set(), []
        for sid in opened:
            if sid not in closed and sid not in seen:
                seen.add(sid)
                out.append(sid)
        return out

    # ---------- sweeping ----------

    def sweep_sync(self, reason: str = "exit") -> list[dict[str, Any]]:
        """Blocking DELETE for every open id. Safe from a signal handler.

        Synchronous on purpose: a signal handler cannot reliably drive an
        asyncio loop that is already unwinding, and httpx's sync client needs
        no running loop.
        """
        ids = self.open_ids()
        if not ids or not self._api_key:
            return []
        import httpx

        results = []
        with httpx.Client(timeout=20) as c:
            for sid in ids:
                try:
                    r = c.delete(f"{self._base_url}/sandboxes/{sid}",
                                 headers={"Authorization": f"Bearer {self._api_key}"})
                    ok = r.status_code in (200, 204, 404)
                    results.append({"sandbox_id": sid[:16], "status": r.status_code, "ok": ok})
                    if ok:
                        self.closed(sid)
                except Exception as exc:
                    results.append({"sandbox_id": sid[:16], "error": type(exc).__name__})
        self._append({"kind": "sweep", "reason": reason, "results": results})
        return results

    def install(self) -> None:
        """atexit plus SIGINT/SIGTERM. Nothing can be done about SIGKILL.

        SIGKILL is exactly why the ledger is on disk: the next process reads
        the file and reaps what this one could not.
        """
        if self._installed:
            return
        self._installed = True
        atexit.register(lambda: self.sweep_sync("atexit"))

        def handler(signum, frame):  # noqa: ARG001
            self.sweep_sync(f"signal-{signum}")
            raise SystemExit(128 + signum)

        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass

    # ---------- assertion ----------

    async def assert_zero_live(self, client: Any, *, reap: bool = True) -> dict[str, Any]:
        """Ask the API what is actually live and fail loudly if anything is.

        The ledger can only be trusted about sandboxes it recorded. This is the
        independent check: it asks Solari, not the local file, which is what
        would have caught both previous leaks at the moment they happened.
        """
        page = await client.list()
        live = page.get("sandboxes", [])
        info: dict[str, Any] = {
            "live_count": len(live),
            "live_ids": [s.sandboxId[:16] for s in live],
            "ledger_open": [i[:16] for i in self.open_ids()],
        }
        if live and reap:
            reaped = []
            for s in live:
                try:
                    await client.kill(s.sandboxId)
                    self.closed(s.sandboxId)
                    reaped.append(s.sandboxId[:16])
                except Exception as exc:
                    reaped.append(f"{s.sandboxId[:16]}:{type(exc).__name__}")
            info["reaped"] = reaped
            raise LeakDetected(
                f"{len(live)} sandbox(es) still live at exit: {info['live_ids']}. "
                f"Reaped {reaped}. Ledger thought open: {info['ledger_open']}. "
                "A live sandbox the harness did not know about is a correctness "
                "bug, not a billing detail."
            )
        return info
