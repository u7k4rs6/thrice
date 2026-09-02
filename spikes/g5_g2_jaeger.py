"""G5 and G2, in one sandbox because G5's question is G2's first phase.

G5: sandbox egress to github.com, and the extracted binaries verified against
    the project's published sha256sum.txt (doc 2 section 4 correction: the
    published file covers the extracted binaries, not the tarball).
G2: start jaeger, health check 16686 and 4318, seed two spans over OTLP,
    snapshot, kill, create(from_snapshot), measure fork time, and answer
    UNVERIFIED item 6: does the forked store come up empty or carry the seed?
    Then test revert(snapshot_id) for time and resulting state.

Stops before G2 if G5 fails.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from _common import Ledger, api_key, emit, idem, write

VERSION = "2.20.0"
BASE = f"https://github.com/jaegertracing/jaeger/releases/download/v{VERSION}"
TARBALL = f"jaeger-{VERSION}-linux-amd64.tar.gz"
SUMS = f"jaeger-{VERSION}-linux-amd64.sha256sum.txt"
DIR = f"/opt/jaeger-{VERSION}-linux-amd64"

SPAN_JSON = json.dumps({
    "resourceSpans": [{
        "resource": {"attributes": [
            {"key": "service.name", "value": {"stringValue": "thrice-probe"}}]},
        "scopeSpans": [{
            "scope": {"name": "thrice"},
            "spans": [
                {"traceId": "5b8aa5a2d2c872e8321cf37308d69df2",
                 "spanId": "051581bf3cb55c13", "name": "probe-root",
                 "kind": 1, "startTimeUnixNano": "1700000000000000000",
                 "endTimeUnixNano": "1700000001000000000"},
                {"traceId": "5b8aa5a2d2c872e8321cf37308d69df2",
                 "spanId": "051581bf3cb55c14", "parentSpanId": "051581bf3cb55c13",
                 "name": "probe-child", "kind": 3,
                 "startTimeUnixNano": "1700000000200000000",
                 "endTimeUnixNano": "1700000000800000000"},
            ]}]}]})


async def sh(sbx, script: str, timeout_ms: int = 300_000):
    return await sbx.commands.run("sh", args=["-c", script], timeout_ms=timeout_ms)


async def health(sbx) -> dict:
    """Both ports. 16686 is the UI, 4318 is OTLP ingest."""
    ui = await sh(sbx, "curl -s -o /dev/null -w '%{http_code}' localhost:16686/")
    otlp = await sh(sbx, "curl -s -o /dev/null -w '%{http_code}' "
                         "-X POST -H 'Content-Type: application/json' "
                         "-d '{\"resourceSpans\":[]}' localhost:4318/v1/traces")
    return {"ui_16686": ui.stdout.strip(), "otlp_4318": otlp.stdout.strip()}


async def store_state(sbx) -> dict:
    svc = await sh(sbx, "curl -s localhost:16686/api/services")
    tr = await sh(sbx, "curl -s 'localhost:16686/api/traces?service=thrice-probe'")
    try:
        services = json.loads(svc.stdout or "{}").get("data") or []
    except Exception:
        services = None
    try:
        traces = json.loads(tr.stdout or "{}").get("data") or []
    except Exception:
        traces = None
    return {
        "services": services,
        "trace_count": len(traces) if traces is not None else None,
        "span_count": sum(len(t.get("spans", [])) for t in traces) if traces else 0,
    }


async def main() -> int:
    from solari_sandbox import SandboxClient

    led = Ledger()
    r: dict[str, object] = {"gates": ["G5", "G2"], "version": VERSION}
    sc = SandboxClient(api_key=api_key(), base_url="https://api.getsolari.com")
    build = fork = None
    t_build = t_fork = None
    snap_id = None
    try:
        # ---------- G5: egress and checksum ----------
        build = await sc.create(
            template="base", cpu=1, mem_mb=2048, timeout_ms=1_500_000,
            lifecycle={"onTimeout": "kill"}, metadata={"thrice_gate": "g5g2"},
        )
        t_build = time.monotonic()
        await build.connect()

        t0 = time.monotonic()
        dl = await sh(build, f"mkdir -p /opt && cd /opt && "
                             f"curl -fsSL -O {BASE}/{TARBALL} && "
                             f"curl -fsSL -O {BASE}/{SUMS} && ls -l {TARBALL} | awk '{{print $5}}'")
        r["download_seconds"] = round(time.monotonic() - t0, 2)
        r["download_exit"] = dl.exitCode
        r["tarball_bytes"] = dl.stdout.strip().splitlines()[-1] if dl.stdout.strip() else None
        if dl.exitCode != 0:
            r["G5_verdict"] = "fails"
            r["G5_reason"] = f"download failed: {dl.stderr[:300]}"
            return 1
        r["G5_egress"] = "reachable"

        ex = await sh(build, f"cd /opt && tar xzf {TARBALL} && ls {DIR}")
        r["tarball_contents"] = ex.stdout.split()
        ck = await sh(build, f"cd /opt && sha256sum -c {SUMS} 2>&1")
        r["sha256sum_c_output"] = ck.stdout.strip().splitlines()
        r["sha256sum_exit"] = ck.exitCode
        r["G5_verdict"] = "holds" if ck.exitCode == 0 else "fails"
        if ck.exitCode != 0:
            return 1

        # ---------- G2: run, health, seed, snapshot, fork ----------
        await build.commands.run(
            "sh", args=["-c", f"cd {DIR} && nohup ./jaeger > /var/log/jaeger.log 2>&1 &"],
            background=True)
        h = None
        t0 = time.monotonic()
        for _ in range(60):
            await asyncio.sleep(1)
            h = await health(build)
            if h["ui_16686"] == "200" and h["otlp_4318"] in ("200", "202"):
                break
        r["seconds_to_healthy"] = round(time.monotonic() - t0, 2)
        r["health_before_snapshot"] = h
        if not h or h["ui_16686"] != "200":
            tail = await sh(build, "tail -20 /var/log/jaeger.log")
            r["jaeger_log_tail"] = tail.stdout[-800:]
            r["G2_verdict"] = "fails"
            r["G2_reason"] = "jaeger never became healthy"
            return 1

        await build.files.write("/tmp/spans.json", SPAN_JSON)
        seed = await sh(build, "curl -s -o /dev/null -w '%{http_code}' -X POST "
                               "-H 'Content-Type: application/json' "
                               "--data @/tmp/spans.json localhost:4318/v1/traces")
        r["seed_status"] = seed.stdout.strip()
        await asyncio.sleep(3)
        r["store_before_snapshot"] = await store_state(build)

        t0 = time.monotonic()
        snap_id = await build.snapshot(f"thrice-jaeger-{VERSION}-seeded-probe")
        r["snapshot_seconds"] = round(time.monotonic() - t0, 2)
        r["snapshot_created"] = bool(snap_id)

        await build.kill()
        led.sandbox("g2-build", time.monotonic() - t_build)
        t_build = None
        r["build_sandbox_killed"] = True

        t0 = time.monotonic()
        fork = await sc.create(
            template="base", from_snapshot=snap_id, cpu=1, mem_mb=2048,
            timeout_ms=900_000, lifecycle={"onTimeout": "kill"},
            metadata={"thrice_gate": "g2fork"},
        )
        t_fork = time.monotonic()
        r["fork_create_seconds"] = round(time.monotonic() - t0, 2)
        await fork.connect()
        r["fork_connect_seconds"] = round(time.monotonic() - t0, 2)

        # Is jaeger still running after the fork, without restarting it?
        h2 = None
        t0 = time.monotonic()
        for _ in range(30):
            h2 = await health(fork)
            if h2["ui_16686"] == "200":
                break
            await asyncio.sleep(1)
        r["fork_seconds_to_healthy"] = round(time.monotonic() - t0, 2)
        r["health_after_fork"] = h2
        r["jaeger_survived_fork"] = h2 is not None and h2["ui_16686"] == "200"

        # UNVERIFIED item 6: empty or seeded?
        after = await store_state(fork)
        r["store_after_fork"] = after
        r["forked_store_carries_seed"] = (after.get("trace_count") or 0) > 0
        r["UNVERIFIED_6_answer"] = (
            "forked store CARRIES the pre-snapshot seed"
            if r["forked_store_carries_seed"] else "forked store is EMPTY"
        )

        # revert(snapshot_id): add a second service, revert, check it is gone.
        extra = SPAN_JSON.replace("thrice-probe", "thrice-after-snap").replace(
            "5b8aa5a2d2c872e8321cf37308d69df2", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        await fork.files.write("/tmp/extra.json", extra)
        await sh(fork, "curl -s -o /dev/null -X POST -H 'Content-Type: application/json' "
                       "--data @/tmp/extra.json localhost:4318/v1/traces")
        await asyncio.sleep(3)
        r["store_before_revert"] = await store_state(fork)

        t0 = time.monotonic()
        try:
            await fork.revert(snap_id)
            r["revert_seconds"] = round(time.monotonic() - t0, 2)
            r["revert_ok"] = True
            for _ in range(30):
                h3 = await health(fork)
                if h3["ui_16686"] == "200":
                    break
                await asyncio.sleep(1)
            r["health_after_revert"] = h3
            r["store_after_revert"] = await store_state(fork)
        except Exception as exc:
            r["revert_ok"] = False
            r["revert_error"] = f"{type(exc).__name__}: {exc}"

        r["G2_verdict"] = "holds" if r["jaeger_survived_fork"] else "fails"
        r["snapshot_id_for_g7"] = "recorded in scratch"
        (sys.modules["_common"].SCRATCH / "snap_2200.txt").write_text(snap_id or "")
        return 0
    except Exception as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
        r.setdefault("G2_verdict", "fails")
        return 1
    finally:
        for sb, t in ((build, t_build), (fork, t_fork)):
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
        write("g5_g2.json", r)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
