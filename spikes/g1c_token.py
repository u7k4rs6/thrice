"""G1 supplement 2: is the preview pt_token actually load-bearing?

The g1b run suggested an altered token and a stripped token both return 200,
but that client had already made a successful request, so a session cookie
could explain it. This repeats the test with a FRESH client per request and
cookies disabled, which is the only way the answer means anything.

The security control in 03-security-and-access.md depends on the answer: if the
host alone grants access, redacting the token is not enough.
"""
from __future__ import annotations

import asyncio
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])

import httpx
from _common import Ledger, api_key, emit, write

PORT = 8155


async def probe(url: str, label: str, headers: dict | None = None) -> dict:
    """One request, brand new client, no cookie reuse, no redirect following."""
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, cookies=None) as c:
        try:
            resp = await c.get(url, headers=headers or {})
            return {
                "label": label,
                "status": resp.status_code,
                "len": len(resp.content),
                "body_is_app": "thrice-token-probe" in resp.text,
                "set_cookie": "set-cookie" in {k.lower() for k in resp.headers},
                "location": resp.headers.get("location", "")[:60],
            }
        except Exception as exc:
            return {"label": label, "error": f"{type(exc).__name__}: {exc}"}


async def main() -> int:
    from solari_sandbox import SandboxClient

    led = Ledger()
    r: dict[str, object] = {"gate": "G1c", "question": "is pt_token load-bearing"}
    sc = SandboxClient(api_key=api_key(), base_url="https://api.getsolari.com")
    sbx = None
    t_sb = None
    try:
        sbx = await sc.create(
            template="base", cpu=1, mem_mb=2048, timeout_ms=600_000,
            lifecycle={"onTimeout": "kill"}, metadata={"thrice_gate": "g1c"},
        )
        t_sb = time.monotonic()
        await sbx.connect()
        await sbx.files.write("/tmp/tp/index.html", "<title>thrice-token-probe</title>ok")
        await sbx.commands.start("sh", args=["-c", f"cd /tmp/tp && python3 -m http.server {PORT}"])
        await asyncio.sleep(2)

        preview = await sbx.preview_url(PORT)
        url, token = preview["url"], preview.get("token", "")
        origin = url.split("?")[0]

        probes = []
        # Order matters: try the UNAUTHENTICATED cases FIRST, so a valid
        # request cannot have primed anything.
        probes.append(await probe(origin, "no_token_first"))
        probes.append(await probe(origin + "?pt_token=deadbeef", "wrong_token"))
        probes.append(await probe(origin + "?pt_token=", "empty_token"))
        probes.append(await probe(url, "valid_token"))
        probes.append(await probe(origin, "no_token_after_valid"))
        probes.append(await probe(origin, "header_token",
                                  {"x-pinetree-preview-token": token}))
        r["probes"] = probes

        by = {p["label"]: p.get("status") for p in probes}
        r["status_by_case"] = by
        r["token_is_load_bearing"] = by.get("no_token_first") in (401, 403)
        r["host_alone_grants_access"] = by.get("no_token_first") == 200
        r["verdict"] = "holds"
        return 0
    except Exception as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
        r["verdict"] = "fails"
        return 1
    finally:
        if sbx is not None:
            try:
                await sbx.kill()
            except Exception:
                pass
        if t_sb:
            led.sandbox("g1c", time.monotonic() - t_sb)
        await sc.aclose()
        r["ledger"] = led.summary()
        emit(r)
        write("g1c.json", r)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
