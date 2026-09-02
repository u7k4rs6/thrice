"""Environment manager: snapshot build, fork, seed, health, preview URL.

Every finding from spikes/GATES.md that changes behaviour is applied here:

  G2  A fork carries the pre-snapshot seed, so snapshots are built CLEAN and
      seeding happens only after the fork. A snapshot whose name does not end
      in `-ready` is never forked.
  G1  The not-ready preview status is 502, not the documented 425. 502 cannot
      distinguish "nothing listening yet" from "the gateway is broken", so the
      external poll gets a hard deadline and the in-sandbox health check runs
      FIRST. If curl to localhost already works and the preview still 502s,
      the problem is the gateway, and the error says so.
  G1  The preview URL carries a one-hour pt_token and is a bearer credential.
      It is redacted on the way into any artifact.
  G7  Snapshots are per version, named jaeger-<version>-ready.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from typing import Any

BASE_URL = "https://api.getsolari.com"
GH = "https://github.com/jaegertracing/jaeger/releases/download"

#: Hard deadline on the external preview poll. G1 measured 0.53 s from server
#: start to first 200 on a healthy sandbox, so anything past this is broken
#: rather than slow.
PREVIEW_DEADLINE_S = 90.0
#: In-sandbox health deadline. G7 measured 1.53 s to healthy on both versions.
LOCAL_HEALTH_DEADLINE_S = 90.0


def redact(text: str) -> str:
    text = re.sub(r"slr_live_[A-Za-z0-9_]+", "slr_live_[redacted]", text)
    text = re.sub(r"pt_token=[A-Za-z0-9._\-]+", "pt_token=[redacted]", text)
    return re.sub(r"https://[a-z0-9]+-\d+\.preview\.getsolari\.com", "https://<preview-host>", text)


def idem() -> str:
    return str(uuid.uuid4())


class EnvError(RuntimeError):
    pass


async def _sh(sbx: Any, script: str, timeout_ms: int = 300_000) -> Any:
    return await sbx.commands.run("sh", args=["-c", script], timeout_ms=timeout_ms)


class EnvManager:
    def __init__(self, client: Any, guard: Any, ledger: Any = None) -> None:
        self.sc = client
        self.guard = guard
        #: On-disk ledger. Survives the process, which the in-memory list below
        #: does not; see thrice/env/ledger.py for why that matters.
        self.ledger = ledger
        #: Every sandbox this manager created, so a failure between create and
        #: hand-off cannot leak one. A leaked sandbox bills until its plan
        #: deadline, and on day 3 one leaked for about ten minutes because
        #: acquire() created it internally and the caller's finally block had
        #: nothing to kill.
        self._created: list[Any] = []

    async def reap(self) -> list[str]:
        """Kill everything this manager created. Safe to call twice."""
        killed = []
        for sbx in self._created:
            try:
                await sbx.kill()
                if self.ledger:
                    self.ledger.closed(sbx.id)
                killed.append("ok")
            except Exception as exc:
                killed.append(f"{type(exc).__name__}")
        self._created.clear()
        return killed

    # ---------- environment acquisition ----------

    async def acquire(self, version: str, attempt_id: str) -> tuple[Any, dict[str, Any]]:
        """Return a live, healthy sandbox running jaeger at `version`.

        Preferred path is snapshot-and-fork (D1): about 10 s and a couple of
        hundredths of a cent. Fallback is building in place, about 25 s, which
        is the contingency docs/01-prd.md section 9 names for "G2 failing means
        every attempt pays the full build cost".

        The fallback exists because snapshotting became unavailable on this
        account after day 1: `snapshot()` returns 409 "Not snapshottable" even
        on a trivial freshly created sandbox with no other sandboxes live and
        only two snapshots stored. G7 performed the identical call successfully
        on 2026-09-02. Ruled out as causes: concurrent-sandbox state (reaped to
        zero, still 409) and a snapshot quota (deleted down to two, still 409).
        Recorded as Q25.
        """
        info: dict[str, Any] = {"version": version}
        try:
            snap_id, snap_info = await self.ensure_snapshot(version)
            info["snapshot"] = snap_info
            sbx, fork_s = await self._fork_with_retry(snap_id, attempt_id)
            info |= {"path": "fork", "fork_seconds": fork_s}
            info["health_seconds"] = await self._local_health(sbx, 16686, 4318)
            return sbx, info
        except Exception as exc:
            info["snapshot_path_error"] = f"{type(exc).__name__}: {str(exc)[:280]}"
            # Anything created on the failed path is killed before trying
            # another, so a fallback never doubles the live sandbox count.
            info["reaped_after_snapshot_path"] = await self.reap()

        try:
            sbx, build = await self._build_in_place(version, attempt_id)
        except Exception:
            await self.reap()
            raise
        info |= {"path": "build_in_place"} | build
        return sbx, info

    async def _build_in_place(self, version: str, attempt_id: str) -> tuple[Any, dict[str, Any]]:
        """Download, verify and start jaeger in a fresh sandbox. No snapshot."""
        tarball = f"jaeger-{version}-linux-amd64.tar.gz"
        sums = f"jaeger-{version}-linux-amd64.sha256sum.txt"
        d = f"/opt/jaeger-{version}-linux-amd64"
        out: dict[str, Any] = {}
        t = time.monotonic()
        sbx = await self._create_with_retry(
            template="base", cpu=1, mem_mb=2048, timeout_ms=1_200_000,
            lifecycle={"onTimeout": "kill"}, metadata={"thrice_attempt": attempt_id})
        self._created.append(sbx)
        await sbx.connect()
        dl = await _sh(sbx, f"mkdir -p /opt && cd /opt && curl -fsSL -O {GH}/v{version}/{tarball} "
                            f"&& curl -fsSL -O {GH}/v{version}/{sums} && tar xzf {tarball}")
        if dl.exitCode != 0:
            raise EnvError(f"download/extract failed for {version}: {dl.stderr[:300]}")
        ck = await _sh(sbx, f"cd /opt && sha256sum -c {sums} 2>&1")
        if ck.exitCode != 0:
            raise EnvError(f"checksum verification failed for {version}: {ck.stdout[:300]}")
        out["sha256_verified"] = True
        await sbx.commands.run(
            "sh", args=["-c", f"cd {d} && nohup ./jaeger > /var/log/jaeger.log 2>&1 &"],
            background=True)
        out["health_seconds"] = await self._local_health(sbx, 16686, 4318)
        out["build_seconds"] = round(time.monotonic() - t, 2)
        return sbx, out

    async def _create_with_retry(self, **kw: Any) -> Any:
        """Retry capacity failures. 503/NoCapacity is documented retryable; 429 never is.

        The ledger records intent BEFORE the call and the id immediately after,
        so a create that succeeds server-side but fails client-side still
        leaves a trail for the sweep.
        """
        attempt_id = (kw.get("metadata") or {}).get("thrice_attempt", "unknown")
        last: Exception | None = None
        for attempt in range(4):
            token = self.ledger.intent(attempt_id, note=str(kw.get("from_snapshot") or "fresh")) \
                if self.ledger else None
            try:
                sbx = await self.sc.create(**kw)
                if self.ledger:
                    self.ledger.opened(sbx.id, attempt_id, token)
                return sbx
            except Exception as exc:
                status = getattr(exc, "status", None)
                name = type(exc).__name__
                if name == "ConcurrencyLimitError" or status == 429:
                    raise
                if name not in ("NoCapacityError", "GatewayError") and status not in (502, 503, 504):
                    raise
                last = exc
                await asyncio.sleep(2 * (attempt + 1))
        raise EnvError(f"create failed after retries: {type(last).__name__}: {last}")

    async def _fork_with_retry(self, snapshot_id: str, attempt_id: str) -> tuple[Any, float]:
        t = time.monotonic()
        sbx = await self._create_with_retry(
            template="base", from_snapshot=snapshot_id, cpu=1, mem_mb=2048,
            timeout_ms=900_000, lifecycle={"onTimeout": "kill"},
            metadata={"thrice_attempt": attempt_id})
        self._created.append(sbx)
        await sbx.connect()
        return sbx, round(time.monotonic() - t, 2)

    # ---------- snapshots ----------

    async def ensure_snapshot(self, version: str) -> tuple[str, dict[str, Any]]:
        """Return (snapshot_id, info). Reuses a clean `-ready` snapshot if present."""
        name = f"thrice-jaeger-{version}-ready"
        info: dict[str, Any] = {"version": version, "snapshot_name": name}
        for s in await self.sc.list_snapshots():
            if getattr(s, "name", None) == name:
                sid = getattr(s, "snapshotId", None) or getattr(s, "id", None)
                info |= {"reused": True, "snapshot_id": sid}
                return sid, info
        info["reused"] = False
        sid, build = await self._build_snapshot(version, name)
        info |= build | {"snapshot_id": sid}
        return sid, info

    async def _build_snapshot(self, version: str, name: str) -> tuple[str, dict[str, Any]]:
        """Download, verify against the published sha256sum, start, health, snapshot.

        Built clean: no seeding happens before the snapshot, per G2.
        """
        tarball = f"jaeger-{version}-linux-amd64.tar.gz"
        sums = f"jaeger-{version}-linux-amd64.sha256sum.txt"
        d = f"/opt/jaeger-{version}-linux-amd64"
        out: dict[str, Any] = {}
        async with self.guard.sandboxes:
            sbx = await self._create_with_retry(
                template="base", cpu=1, mem_mb=2048, timeout_ms=1_200_000,
                lifecycle={"onTimeout": "kill"}, metadata={"thrice": "snapshot-build"},
            )
            self._created.append(sbx)
            t0 = time.monotonic()
            try:
                await sbx.connect()
                t = time.monotonic()
                dl = await _sh(sbx, f"mkdir -p /opt && cd /opt && curl -fsSL -O {GH}/v{version}/{tarball} "
                                    f"&& curl -fsSL -O {GH}/v{version}/{sums} && tar xzf {tarball}")
                if dl.exitCode != 0:
                    raise EnvError(f"download/extract failed for {version}: {dl.stderr[:300]}")
                out["download_extract_seconds"] = round(time.monotonic() - t, 2)

                # G5: the published sums cover the EXTRACTED binaries, not the tarball.
                ck = await _sh(sbx, f"cd /opt && sha256sum -c {sums} 2>&1")
                if ck.exitCode != 0:
                    raise EnvError(f"checksum verification failed for {version}: {ck.stdout[:300]}")
                out["sha256_verified"] = True

                await sbx.commands.run(
                    "sh", args=["-c", f"cd {d} && nohup ./jaeger > /var/log/jaeger.log 2>&1 &"],
                    background=True)
                out["seconds_to_healthy"] = await self._local_health(sbx, 16686, 4318)

                t = time.monotonic()
                try:
                    sid = await sbx.snapshot(name)
                except Exception as exc:
                    raise EnvError(
                        f"snapshot() failed for {version}: {type(exc).__name__}: {exc} "
                        f"(status {getattr(exc, 'status', None)}). See Q25."
                    ) from exc
                out["snapshot_seconds"] = round(time.monotonic() - t, 2)
                return sid, out
            finally:
                try:
                    await sbx.kill()
                finally:
                    self.guard.add_sandbox(time.monotonic() - t0)

    # ---------- per-attempt ----------

    async def fork(self, snapshot_id: str, attempt_id: str) -> tuple[Any, float]:
        t = time.monotonic()
        sbx = await self.sc.create(
            template="base", from_snapshot=snapshot_id, cpu=1, mem_mb=2048,
            timeout_ms=900_000, lifecycle={"onTimeout": "kill"},
            metadata={"thrice_attempt": attempt_id},
        )
        await sbx.connect()
        return sbx, round(time.monotonic() - t, 2)

    async def _local_health(self, sbx: Any, ui_port: int, otlp_port: int) -> float:
        """Inside the sandbox first, so a preview failure is attributable."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < LOCAL_HEALTH_DEADLINE_S:
            ui = await _sh(sbx, f"curl -s -o /dev/null -w '%{{http_code}}' localhost:{ui_port}/")
            otlp = await _sh(
                sbx,
                f"curl -s -o /dev/null -w '%{{http_code}}' -X POST "
                f"-H 'Content-Type: application/json' -d '{{\"resourceSpans\":[]}}' "
                f"localhost:{otlp_port}/v1/traces",
            )
            if ui.stdout.strip() == "200" and otlp.stdout.strip() in ("200", "202"):
                return round(time.monotonic() - t0, 2)
            await asyncio.sleep(1)
        tail = await _sh(sbx, "tail -20 /var/log/jaeger.log")
        raise EnvError(
            f"jaeger not healthy inside the sandbox after {LOCAL_HEALTH_DEADLINE_S}s. "
            f"log tail: {tail.stdout[-400:]}"
        )

    async def health(self, sbx: Any, ui_port: int, otlp_port: int) -> float:
        return await self._local_health(sbx, ui_port, otlp_port)

    async def seed(self, sbx: Any, seeds: Any, otlp_port: int) -> list[dict[str, Any]]:
        """POST each OTLP payload to localhost. Timestamps are the plan's problem.

        G2 correction: Jaeger's query API applies a default lookback window, so
        a seed timestamped in the past is invisible even though it is stored.
        `stamp_now` in thrice.env.seed rewrites payload timestamps to now.
        """
        results = []
        for s in seeds:
            await sbx.files.write(f"/tmp/seed_{s.id}.json", json.dumps(s.payload))
            r = await _sh(
                sbx,
                f"curl -s -o /dev/null -w '%{{http_code}}' -X POST "
                f"-H 'Content-Type: application/json' --data @/tmp/seed_{s.id}.json "
                f"localhost:{otlp_port}{s.endpoint}",
            )
            status = r.stdout.strip()
            want = str(s.expected_response.get("status", 200))
            results.append({"seed_id": s.id, "status": status, "ok": status == want})
            if status != want:
                raise EnvError(f"seed {s.id} returned {status}, expected {want}")
        return results

    async def verify_seed_visible(self, sbx: Any, service: str, ui_port: int) -> dict[str, Any]:
        """Confirm the seed is queryable with an explicit time range, per G2."""
        end_us = int(time.time() * 1e6) + 3_600_000_000
        start_us = end_us - 172_800_000_000
        svc = await _sh(sbx, f"curl -s localhost:{ui_port}/api/services")
        tr = await _sh(sbx, f"curl -s 'localhost:{ui_port}/api/traces?service={service}"
                            f"&start={start_us}&end={end_us}&limit=50'")
        try:
            services = sorted(json.loads(svc.stdout or "{}").get("data") or [])
        except Exception:
            services = []
        try:
            traces = json.loads(tr.stdout or "{}").get("data") or []
        except Exception:
            traces = []
        return {"services": services, "traces": len(traces),
                "spans": sum(len(t.get("spans", [])) for t in traces)}

    async def preview(self, sbx: Any, port: int) -> tuple[str, dict[str, Any]]:
        """Signed preview URL, polled to a hard deadline.

        G1: nothing-listening answers 502, not the documented 425, and 502
        cannot distinguish not-ready from broken. The in-sandbox health check
        has already passed by the time this runs, so a persistent 502 here is
        a gateway problem and the message says so rather than blaming jaeger.
        """
        import httpx

        p = await sbx.preview_url(port)
        url = p["url"]
        info: dict[str, Any] = {"has_pt_token": "pt_token=" in url, "statuses": []}
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as http:
            while time.monotonic() - t0 < PREVIEW_DEADLINE_S:
                try:
                    code = (await http.get(url)).status_code
                except Exception:
                    code = -1
                info["statuses"].append(code)
                if code == 200:
                    info["seconds_to_200"] = round(time.monotonic() - t0, 2)
                    return url, info
                await asyncio.sleep(1)
        raise EnvError(
            f"preview URL never returned 200 within {PREVIEW_DEADLINE_S}s "
            f"(statuses: {info['statuses'][:12]}). Jaeger is healthy on localhost inside "
            "the sandbox, so this is the preview gateway, not the app. Note that 502 is "
            "what this deployment returns when nothing is listening, despite the docs "
            "naming 425 Too Early."
        )
