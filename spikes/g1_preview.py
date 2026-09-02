"""G1: does this org have a preview domain configured?

Create a sandbox, serve a static file on a port, call preview_url(port), fetch
it from outside, then load it in a Solari browser. Report the 425 Too Early
behaviour and time to resolve, and whether the pt_token is visible in page.url
from the browser side, because doc 3's redaction control depends on it.

If this fails, day 1 stops. No fallback is implemented.
"""
from __future__ import annotations

import asyncio
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])

import httpx
from _common import Ledger, Timer, api_key, emit, idem, write

PORT = 8099
PAGE = "<!doctype html><title>thrice-g1</title><h1 id=probe>thrice g1 ok</h1>"


async def main() -> int:
    from solari_browser import Solari
    from solari_sandbox import SandboxClient

    led = Ledger()
    r: dict[str, object] = {"gate": "G1"}
    sbx = None
    sc = SandboxClient(api_key=api_key(), base_url="https://api.getsolari.com")
    sandbox_t0 = None

    try:
        with Timer() as t:
            sbx = await sc.create(
                template="base", cpu=1, mem_mb=2048,
                timeout_ms=900_000, lifecycle={"onTimeout": "kill"},
                metadata={"thrice_gate": "g1"},
            )
        sandbox_t0 = time.monotonic()
        r["create_seconds"] = round(t.seconds, 2)
        r["sandbox_id_present"] = bool(sbx.id)
        await sbx.connect()
        r["connected"] = True

        # Serve a static file. Start the server BEFORE asking for a preview URL
        # in one ordering and after in another would confound the 425 test, so
        # ask for the URL first and poll while the server is still coming up.
        await sbx.files.write(f"/tmp/site/index.html", PAGE)
        await sbx.commands.start(
            "sh", args=["-c", f"cd /tmp/site && python3 -m http.server {PORT}"]
        )

        with Timer() as t:
            preview = await sbx.preview_url(PORT)
        r["preview_url_seconds"] = round(t.seconds, 2)
        url = preview.get("url", "")
        r["preview_returned_url"] = bool(url)
        r["preview_returned_token_field"] = bool(preview.get("token"))
        r["preview_has_pt_token_in_url"] = "pt_token=" in url
        r["preview_host"] = url.split("/")[2] if "://" in url else ""

        # 425 Too Early behaviour and time to resolve.
        codes: list[int] = []
        t0 = time.monotonic()
        resolved_at = None
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as http:
            for _ in range(40):
                try:
                    resp = await http.get(url)
                    codes.append(resp.status_code)
                    if resp.status_code == 200:
                        resolved_at = time.monotonic() - t0
                        r["body_matches"] = "thrice g1 ok" in resp.text
                        break
                except Exception as exc:
                    codes.append(-1)
                    r.setdefault("fetch_errors", []).append(f"{type(exc).__name__}")
                await asyncio.sleep(0.5)
        r["status_sequence"] = codes
        r["saw_425"] = 425 in codes
        r["seconds_to_200"] = round(resolved_at, 2) if resolved_at else None
        r["reached_200"] = resolved_at is not None

        if not r["reached_200"]:
            r["verdict"] = "fails"
            return 1

        # Now the browser half: can a Solari browser load it, and is the token
        # visible from inside the page?
        from playwright.async_api import async_playwright

        async with Solari(api_key=api_key()) as solari:
            bt0 = time.monotonic()
            session = await solari.sessions.create(stealth=False)
            try:
                async with async_playwright() as pw:
                    b = await pw.chromium.connect_over_cdp(session.cdp_endpoint)
                    ctx = b.contexts[0] if b.contexts else await b.new_context()
                    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                    await page.goto(url, wait_until="load", timeout=30_000)
                    r["browser_loaded"] = (await page.title()) == "thrice-g1"
                    r["browser_sees_probe"] = (
                        await page.evaluate("document.getElementById('probe')?.textContent")
                    ) == "thrice g1 ok"
                    page_url = page.url
                    r["page_url_contains_pt_token"] = "pt_token=" in page_url
                    r["page_url_shape"] = (
                        page_url.split("?")[0].replace(r["preview_host"], "<preview-host>")
                        + ("?" + page_url.split("?", 1)[1].split("=")[0] + "=<...>"
                           if "?" in page_url else "")
                    )
                    loc = await page.evaluate("location.search")
                    r["js_location_search_contains_token"] = "pt_token=" in loc
                    await b.close()
            finally:
                await solari.sessions.release_and_wait(session.id)
                led.browser("g1-browser", time.monotonic() - bt0)

        r["verdict"] = "holds" if (r["reached_200"] and r.get("browser_loaded")) else "fails"
        return 0 if r["verdict"] == "holds" else 1

    except Exception as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
        r["verdict"] = "fails"
        return 1
    finally:
        if sbx is not None:
            try:
                await sbx.kill()
                r["sandbox_killed"] = True
            except Exception as exc:
                r["sandbox_killed"] = False
                r["kill_error"] = f"{type(exc).__name__}: {exc}"
        if sandbox_t0:
            led.sandbox("g1-sandbox", time.monotonic() - sandbox_t0)
        await sc.aclose()
        r["ledger"] = led.summary()
        emit(r)
        write("g1.json", r)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
