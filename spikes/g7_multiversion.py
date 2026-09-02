"""G7: multi-version feasibility. The corpus design rests on this.

Build two different Jaeger release tarballs into two separate snapshots, then
fork from each and confirm both are healthy. Report per-version snapshot build
time. Two versions are built CONCURRENTLY, which also exercises the Starter
sandbox cap of 2 exactly: a third concurrent create would be a non-retryable
429, so this is the boundary.

Versions chosen deliberately far apart: 2.19.0 (recent) and 2.14.0 (the oldest
2.x release that publishes a linux-amd64 tarball at all).
"""
from __future__ import annotations

import asyncio
import json
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from _common import Ledger, api_key, emit, write

VERSIONS = ["2.19.0", "2.14.0"]


async def sh(sbx, script, timeout_ms=300_000):
    return await sbx.commands.run("sh", args=["-c", script], timeout_ms=timeout_ms)


async def build_one(sc, version: str, led: Ledger) -> dict:
    """Download, verify, start, health, snapshot, kill. Returns a report."""
    base = f"https://github.com/jaegertracing/jaeger/releases/download/v{version}"
    tarball = f"jaeger-{version}-linux-amd64.tar.gz"
    sums = f"jaeger-{version}-linux-amd64.sha256sum.txt"
    d = f"/opt/jaeger-{version}-linux-amd64"
    out: dict = {"version": version}
    sbx = None
    t0_sb = None
    wall = time.monotonic()
    try:
        sbx = await sc.create(template="base", cpu=1, mem_mb=2048,
                              timeout_ms=1_200_000, lifecycle={"onTimeout": "kill"},
                              metadata={"thrice_gate": "g7", "v": version})
        t0_sb = time.monotonic()
        await sbx.connect()

        t = time.monotonic()
        dl = await sh(sbx, f"mkdir -p /opt && cd /opt && curl -fsSL -O {base}/{tarball} "
                           f"&& curl -fsSL -O {base}/{sums} && tar xzf {tarball}")
        out["download_extract_seconds"] = round(time.monotonic() - t, 2)
        out["download_exit"] = dl.exitCode
        if dl.exitCode != 0:
            out["error"] = dl.stderr[:300]
            out["ok"] = False
            return out

        ls = await sh(sbx, f"ls {d}")
        out["archive_contents"] = sorted(ls.stdout.split())
        ck = await sh(sbx, f"cd /opt && sha256sum -c {sums} 2>&1")
        out["sha256_verified"] = ck.exitCode == 0
        out["sha256_lines"] = ck.stdout.strip().splitlines()

        await sbx.commands.run("sh", args=["-c",
            f"cd {d} && nohup ./jaeger > /var/log/jaeger.log 2>&1 &"], background=True)
        t = time.monotonic()
        healthy = False
        for _ in range(60):
            await asyncio.sleep(1)
            h = await sh(sbx, "curl -s -o /dev/null -w '%{http_code}' localhost:16686/")
            o = await sh(sbx, "curl -s -o /dev/null -w '%{http_code}' -X POST "
                              "-H 'Content-Type: application/json' -d '{\"resourceSpans\":[]}' "
                              "localhost:4318/v1/traces")
            if h.stdout.strip() == "200":
                healthy = True
                out["health"] = {"ui_16686": h.stdout.strip(), "otlp_4318": o.stdout.strip()}
                break
        out["seconds_to_healthy"] = round(time.monotonic() - t, 2)
        out["healthy"] = healthy
        if not healthy:
            tail = await sh(sbx, "tail -15 /var/log/jaeger.log")
            out["log_tail"] = tail.stdout[-600:]
            out["ok"] = False
            return out

        ver = await sh(sbx, f"{d}/jaeger version 2>&1 | head -3")
        out["binary_version_output"] = ver.stdout.strip()[:200]

        t = time.monotonic()
        snap = await sbx.snapshot(f"thrice-jaeger-{version}-ready")
        out["snapshot_seconds"] = round(time.monotonic() - t, 2)
        out["snapshot_id_present"] = bool(snap)
        out["_snap"] = snap
        out["build_wall_seconds"] = round(time.monotonic() - wall, 2)
        out["ok"] = True
        return out
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["ok"] = False
        return out
    finally:
        if sbx is not None:
            try:
                await sbx.kill()
            except Exception:
                pass
            if t0_sb:
                led.sandbox(f"g7-build-{version}", time.monotonic() - t0_sb)


async def fork_one(sc, version: str, snap: str, led: Ledger) -> dict:
    out: dict = {"version": version}
    sbx = None
    t0_sb = None
    try:
        t = time.monotonic()
        sbx = await sc.create(template="base", from_snapshot=snap, cpu=1, mem_mb=2048,
                              timeout_ms=600_000, lifecycle={"onTimeout": "kill"},
                              metadata={"thrice_gate": "g7fork", "v": version})
        t0_sb = time.monotonic()
        out["fork_create_seconds"] = round(time.monotonic() - t, 2)
        await sbx.connect()
        t2 = time.monotonic()
        for _ in range(30):
            h = await sh(sbx, "curl -s -o /dev/null -w '%{http_code}' localhost:16686/")
            if h.stdout.strip() == "200":
                out["healthy_after_fork"] = True
                break
            await asyncio.sleep(1)
        else:
            out["healthy_after_fork"] = False
        out["fork_seconds_to_healthy"] = round(time.monotonic() - t2, 2)
        svc = await sh(sbx, "curl -s localhost:16686/api/services")
        try:
            out["services"] = sorted(json.loads(svc.stdout or "{}").get("data") or [])
        except Exception:
            out["services"] = None
        return out
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["healthy_after_fork"] = False
        return out
    finally:
        if sbx is not None:
            try:
                await sbx.kill()
            except Exception:
                pass
            if t0_sb:
                led.sandbox(f"g7-fork-{version}", time.monotonic() - t0_sb)


async def main() -> int:
    from solari_sandbox import SandboxClient

    led = Ledger()
    r: dict[str, object] = {"gate": "G7", "versions": VERSIONS,
                            "note": "two concurrent sandboxes, exactly the Starter cap"}
    sc = SandboxClient(api_key=api_key(), base_url="https://api.getsolari.com")
    try:
        t = time.monotonic()
        builds = await asyncio.gather(*[build_one(sc, v, led) for v in VERSIONS])
        r["parallel_build_wall_seconds"] = round(time.monotonic() - t, 2)
        r["builds"] = [{k: v for k, v in b.items() if k != "_snap"} for b in builds]
        r["two_concurrent_sandboxes_ok"] = all(b.get("ok") for b in builds)
        if not r["two_concurrent_sandboxes_ok"]:
            r["verdict"] = "fails"
            return 1

        snaps = {b["version"]: b["_snap"] for b in builds}
        t = time.monotonic()
        forks = await asyncio.gather(*[fork_one(sc, v, snaps[v], led) for v in VERSIONS])
        r["parallel_fork_wall_seconds"] = round(time.monotonic() - t, 2)
        r["forks"] = forks
        r["all_forks_healthy"] = all(f.get("healthy_after_fork") for f in forks)
        r["verdict"] = "holds" if r["all_forks_healthy"] else "fails"
        return 0 if r["verdict"] == "holds" else 1
    except Exception as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
        r["verdict"] = "fails"
        return 1
    finally:
        await sc.aclose()
        r["ledger"] = led.summary()
        emit(r)
        write("g7.json", r)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
