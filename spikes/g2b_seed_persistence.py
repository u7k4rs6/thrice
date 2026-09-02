"""G2 supplement: does a forked store actually carry the pre-snapshot seed?

The first G2 run reported trace_count 0 both before the snapshot and after the
fork, which is not evidence of an empty store: it is evidence of a broken
query. Jaeger's /api/traces applies a default lookback window, and the seed
spans were timestamped November 2023, so nothing matched either time. The
service list did carry thrice-probe across the fork, which points the other
way.

This repeats the test with spans timestamped to now AND an explicit start/end
range, so the answer is about the store rather than about the query.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from _common import Ledger, api_key, emit, write

VERSION = "2.20.0"
BASE = f"https://github.com/jaegertracing/jaeger/releases/download/v{VERSION}"
TARBALL = f"jaeger-{VERSION}-linux-amd64.tar.gz"
DIR = f"/opt/jaeger-{VERSION}-linux-amd64"


def spans(service: str, trace_id: str) -> str:
    now_ns = int(time.time() * 1e9)
    return json.dumps({"resourceSpans": [{
        "resource": {"attributes": [
            {"key": "service.name", "value": {"stringValue": service}}]},
        "scopeSpans": [{"scope": {"name": "thrice"}, "spans": [
            {"traceId": trace_id, "spanId": "051581bf3cb55c13", "name": "root",
             "kind": 1, "startTimeUnixNano": str(now_ns - 2_000_000_000),
             "endTimeUnixNano": str(now_ns - 1_000_000_000)},
            {"traceId": trace_id, "spanId": "051581bf3cb55c14",
             "parentSpanId": "051581bf3cb55c13", "name": "child", "kind": 3,
             "startTimeUnixNano": str(now_ns - 1_800_000_000),
             "endTimeUnixNano": str(now_ns - 1_200_000_000)}]}]}]})


async def sh(sbx, script, timeout_ms=300_000):
    return await sbx.commands.run("sh", args=["-c", script], timeout_ms=timeout_ms)


async def query(sbx, service: str) -> dict:
    """Explicit wide time range, so the default lookback cannot hide anything."""
    end_us = int(time.time() * 1e6) + 3_600_000_000
    start_us = end_us - 172_800_000_000  # 48h back
    svc = await sh(sbx, "curl -s localhost:16686/api/services")
    tr = await sh(sbx, f"curl -s 'localhost:16686/api/traces?service={service}"
                       f"&start={start_us}&end={end_us}&limit=50'")
    try:
        services = json.loads(svc.stdout or "{}").get("data") or []
    except Exception:
        services = ["<unparseable>"]
    try:
        data = json.loads(tr.stdout or "{}").get("data") or []
    except Exception:
        data = []
    return {"services": sorted(services), "traces": len(data),
            "spans": sum(len(t.get("spans", [])) for t in data)}


async def main() -> int:
    from solari_sandbox import SandboxClient

    led = Ledger()
    r: dict[str, object] = {"gate": "G2b", "question": "does a fork carry the seed"}
    sc = SandboxClient(api_key=api_key(), base_url="https://api.getsolari.com")
    build = fork = None
    tb = tf = None
    try:
        build = await sc.create(template="base", cpu=1, mem_mb=2048,
                                timeout_ms=1_200_000, lifecycle={"onTimeout": "kill"},
                                metadata={"thrice_gate": "g2b"})
        tb = time.monotonic()
        await build.connect()
        await sh(build, f"mkdir -p /opt && cd /opt && curl -fsSL -O {BASE}/{TARBALL} "
                        f"&& tar xzf {TARBALL}")
        await build.commands.run("sh", args=["-c",
            f"cd {DIR} && nohup ./jaeger > /var/log/jaeger.log 2>&1 &"], background=True)
        for _ in range(60):
            await asyncio.sleep(1)
            h = await sh(build, "curl -s -o /dev/null -w '%{http_code}' localhost:16686/")
            if h.stdout.strip() == "200":
                break

        await build.files.write("/tmp/s.json", spans("thrice-seeded", "11111111111111111111111111111111"))
        st = await sh(build, "curl -s -o /dev/null -w '%{http_code}' -X POST "
                             "-H 'Content-Type: application/json' --data @/tmp/s.json "
                             "localhost:4318/v1/traces")
        r["seed_post_status"] = st.stdout.strip()
        await asyncio.sleep(4)
        r["store_before_snapshot"] = await query(build, "thrice-seeded")

        snap = await build.snapshot(f"thrice-g2b-{VERSION}-seeded")
        await build.kill()
        led.sandbox("g2b-build", time.monotonic() - tb); tb = None

        t0 = time.monotonic()
        fork = await sc.create(template="base", from_snapshot=snap, cpu=1, mem_mb=2048,
                               timeout_ms=900_000, lifecycle={"onTimeout": "kill"},
                               metadata={"thrice_gate": "g2bfork"})
        tf = time.monotonic()
        r["fork_seconds"] = round(time.monotonic() - t0, 2)
        await fork.connect()
        for _ in range(30):
            h = await sh(fork, "curl -s -o /dev/null -w '%{http_code}' localhost:16686/")
            if h.stdout.strip() == "200":
                break
            await asyncio.sleep(1)
        r["store_after_fork"] = await query(fork, "thrice-seeded")

        before = r["store_before_snapshot"]["traces"]
        after = r["store_after_fork"]["traces"]
        r["query_was_working"] = before > 0
        r["forked_store_carries_seed"] = after > 0
        if not r["query_was_working"]:
            r["UNVERIFIED_6_answer"] = "INDETERMINATE: query still returns nothing pre-snapshot"
            r["verdict"] = "fails"
        else:
            r["UNVERIFIED_6_answer"] = (
                "a fork CARRIES the pre-snapshot seed, so snapshots must be built clean"
                if after > 0 else
                "a fork comes up EMPTY despite the pre-snapshot seed being queryable")
            r["verdict"] = "holds"
        return 0
    except Exception as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
        r["verdict"] = "fails"
        return 1
    finally:
        for sb, t in ((build, tb), (fork, tf)):
            if sb is not None:
                try:
                    await sb.kill()
                except Exception:
                    pass
                if t:
                    led.sandbox("sandbox", time.monotonic() - t)
        await sc.aclose()
        r["ledger"] = led.summary()
        emit(r)
        write("g2b.json", r)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
