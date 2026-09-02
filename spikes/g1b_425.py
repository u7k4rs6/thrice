"""G1 supplement: the 425 Too Early path and time to resolve.

The first G1 run never saw a 425 because python3 -m http.server was already up
by the time the URL was fetched. This asks for a preview URL on a port with
nothing listening, polls until it answers, and only then starts the server, so
the 425 window is actually observed and timed.
"""
from __future__ import annotations

import asyncio
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])

import httpx
from _common import Ledger, api_key, emit, write

PORT = 8123


async def main() -> int:
    from solari_sandbox import SandboxClient

    led = Ledger()
    r: dict[str, object] = {"gate": "G1b", "question": "425 Too Early behaviour"}
    sc = SandboxClient(api_key=api_key(), base_url="https://api.getsolari.com")
    sbx = None
    t_sb = None
    try:
        sbx = await sc.create(
            template="base", cpu=1, mem_mb=2048, timeout_ms=600_000,
            lifecycle={"onTimeout": "kill"}, metadata={"thrice_gate": "g1b"},
        )
        t_sb = time.monotonic()
        await sbx.connect()

        preview = await sbx.preview_url(PORT)
        url = preview["url"]

        # Nothing is listening on PORT yet. Poll and record what comes back.
        early: list[int] = []
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as http:
            for _ in range(6):
                try:
                    early.append((await http.get(url)).status_code)
                except Exception:
                    early.append(-1)
                await asyncio.sleep(0.5)
            r["status_before_server_starts"] = early
            r["saw_425_before_start"] = 425 in early

            # Now start the server and time the transition to 200.
            await sbx.files.write("/tmp/late/index.html", "<title>late</title>ok")
            t0 = time.monotonic()
            await sbx.commands.start(
                "sh", args=["-c", f"cd /tmp/late && python3 -m http.server {PORT}"]
            )
            seq: list[int] = []
            resolved = None
            for _ in range(60):
                try:
                    code = (await http.get(url)).status_code
                except Exception:
                    code = -1
                seq.append(code)
                if code == 200:
                    resolved = time.monotonic() - t0
                    break
                await asyncio.sleep(0.25)
            r["status_after_server_starts"] = seq
            r["seconds_from_start_to_200"] = round(resolved, 2) if resolved else None
            r["resolved"] = resolved is not None

            # Token tampering: doc 3 claims a 401 on an altered token.
            bad = url.replace("pt_token=", "pt_token=x")
            try:
                r["altered_token_status"] = (await http.get(bad)).status_code
            except Exception as exc:
                r["altered_token_status"] = f"{type(exc).__name__}"
            try:
                stripped = url.split("?")[0]
                r["no_token_status"] = (await http.get(stripped)).status_code
            except Exception as exc:
                r["no_token_status"] = f"{type(exc).__name__}"

        r["verdict"] = "holds" if r["resolved"] else "fails"
        return 0
    except Exception as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
        r["verdict"] = "fails"
        return 1
    finally:
        if sbx is not None:
            try:
                await sbx.kill()
                r["sandbox_killed"] = True
            except Exception:
                r["sandbox_killed"] = False
        if t_sb:
            led.sandbox("g1b", time.monotonic() - t_sb)
        await sc.aclose()
        r["ledger"] = led.summary()
        emit(r)
        write("g1b.json", r)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
