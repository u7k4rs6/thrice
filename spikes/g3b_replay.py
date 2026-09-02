"""G3 supplement: is session replay retrievable given a longer window?

The G3 run polled 10 times at 3s (30s total) and got 404 throughout. The
cookbook example uses the same cadence and notes the upload is asynchronous,
so 30s may simply be too short. Ranking replay last on a 30s window would be
unfair, so this polls for 3 minutes with backoff.
"""
from __future__ import annotations

import asyncio
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from _common import Ledger, api_key, emit, write

PAGE = "data:text/html,<title>g3b</title><h1>replay probe</h1>"


async def main() -> int:
    from solari_browser import Solari
    from solari_browser.errors import SolariError
    from playwright.async_api import async_playwright

    led = Ledger()
    r: dict[str, object] = {"gate": "G3b", "question": "replay retrievable with a longer poll"}
    solari = Solari(api_key=api_key())
    try:
        t0 = time.monotonic()
        session = await solari.sessions.create(recording=True)
        sid = session.id
        r["recording_flag_sent"] = True
        try:
            async with async_playwright() as pw:
                b = await pw.chromium.connect_over_cdp(session.cdp_endpoint)
                ctx = b.contexts[0] if b.contexts else await b.new_context()
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                await page.goto(PAGE)
                # Give rrweb real events to record, and time to batch them.
                for i in range(6):
                    await page.evaluate(f"document.title='g3b-{i}'")
                    await asyncio.sleep(1)
                await asyncio.sleep(3)
                await b.close()
        finally:
            await solari.sessions.release_and_wait(sid)
            led.browser("g3b", time.monotonic() - t0)

        attempts = []
        got = None
        t_poll = time.monotonic()
        delay = 3
        while time.monotonic() - t_poll < 180:
            try:
                blob = await solari.sessions.download_replay(sid)
                got = blob
                break
            except SolariError as e:
                attempts.append({"t": round(time.monotonic() - t_poll, 1), "status": e.status})
            except Exception as e:
                attempts.append({"t": round(time.monotonic() - t_poll, 1),
                                 "err": type(e).__name__})
            await asyncio.sleep(delay)
            delay = min(delay * 1.4, 20)

        r["poll_attempts"] = attempts
        r["poll_window_seconds"] = round(time.monotonic() - t_poll, 1)
        r["retrieved"] = got is not None
        if got is not None:
            lines = got.decode(errors="replace").splitlines()
            r["bytes"] = len(got)
            r["ndjson_lines"] = len(lines)
            r["first_line_prefix"] = lines[0][:80] if lines else ""
            r["is_video_container"] = got[:4] in (b"\x1aE\xdf\xa3", b"\x00\x00\x00\x18")
        r["verdict"] = "holds" if r["retrieved"] else "fails"
        return 0
    except Exception as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
        r["verdict"] = "fails"
        return 1
    finally:
        await solari.close()
        r["ledger"] = led.summary()
        emit(r)
        write("g3b.json", r)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
