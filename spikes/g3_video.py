"""G3: a video path, in the corrected order.

1. CDP Page.startScreencast, frames collected locally and stitched with ffmpeg.
2. Solari session replay (rrweb NDJSON, retrievable but not a video file).
3. Playwright record_video over connect_over_cdp.

Option 3 is tested last and expected to fail for two independent reasons, and
the point of running it is to turn an inference into a measurement:
  a. record_video_dir is a new_context() option, and connect_over_cdp attaches
     to an existing context that cannot be reconfigured.
  b. Even if a fresh context can be made, Playwright writes the .webm on the
     browser host (the Solari VM), and connect_over_cdp has no file-transfer
     channel, so the artifact is stranded.
Both are probed separately so the report can say which one bites first.
"""
from __future__ import annotations

import asyncio
import base64
import pathlib
import shutil
import subprocess
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from _common import SCRATCH, Ledger, api_key, emit, write

PAGE = ("data:text/html,<title>g3</title><style>body{font:48px sans-serif}</style>"
        "<div id=c>0</div><script>let n=0;setInterval(()=>{n++;"
        "document.getElementById('c').textContent=n;"
        "document.body.style.background='hsl('+(n*40%360)+',70%,85%)'},120)</script>")


async def opt1_screencast(session, led) -> dict:
    """Frames arrive in the CDP message stream, so they land on THIS machine."""
    from playwright.async_api import async_playwright

    out: dict = {"option": "1_screencast"}
    frames_dir = SCRATCH / "g3_frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    t0 = time.monotonic()
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp(session.cdp_endpoint)
        ctx = b.contexts[0] if b.contexts else await b.new_context()
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(PAGE)
        cdp = await ctx.new_cdp_session(page)

        frames: list[bytes] = []

        def on_frame(ev: dict) -> None:
            frames.append(base64.b64decode(ev["data"]))
            asyncio.create_task(
                cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]}))

        cdp.on("Page.screencastFrame", on_frame)
        await cdp.send("Page.startScreencast",
                       {"format": "png", "quality": 80, "everyNthFrame": 1,
                        "maxWidth": 800, "maxHeight": 600})
        await asyncio.sleep(5)
        await cdp.send("Page.stopScreencast")
        await cdp.detach()
        await b.close()

    for i, data in enumerate(frames):
        (frames_dir / f"f{i:05d}.png").write_bytes(data)
    out["frames_captured"] = len(frames)
    out["frames_landed_locally"] = len(list(frames_dir.glob("*.png")))
    out["total_bytes"] = sum(len(f) for f in frames)
    out["capture_seconds"] = round(time.monotonic() - t0, 2)

    ff = shutil.which("ffmpeg")
    out["ffmpeg_present"] = bool(ff)
    if ff and frames:
        mp4 = SCRATCH / "g3_screencast.mp4"
        proc = subprocess.run(
            [ff, "-y", "-framerate", "10", "-pattern_type", "glob",
             "-i", str(frames_dir / "*.png"), "-pix_fmt", "yuv420p", str(mp4)],
            capture_output=True)
        out["ffmpeg_exit"] = proc.returncode
        out["video_bytes"] = mp4.stat().st_size if mp4.exists() else 0
        out["video_path"] = str(mp4)
    out["works"] = out["frames_landed_locally"] > 0
    return out


async def opt2_replay(solari, led) -> dict:
    """Retrievable over ordinary HTTP, but it is rrweb NDJSON, not a video."""
    from playwright.async_api import async_playwright

    out: dict = {"option": "2_session_replay"}
    t0 = time.monotonic()
    session = await solari.sessions.create(recording=True)
    sid = session.id
    try:
        async with async_playwright() as pw:
            b = await pw.chromium.connect_over_cdp(session.cdp_endpoint)
            ctx = b.contexts[0] if b.contexts else await b.new_context()
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto(PAGE)
            await asyncio.sleep(4)
            await b.close()
    finally:
        await solari.sessions.release_and_wait(sid)
        led.browser("g3-replay", time.monotonic() - t0)

    from solari_browser.errors import SolariError
    attempts = []
    for i in range(10):
        await asyncio.sleep(3)
        try:
            blob = await solari.sessions.download_replay(sid)
            out["retrieved"] = True
            out["bytes"] = len(blob)
            lines = blob.decode(errors="replace").splitlines()
            out["ndjson_lines"] = len(lines)
            out["first_line_prefix"] = lines[0][:70] if lines else ""
            out["is_video_container"] = blob[:4] in (b"\x1aE\xdf\xa3", b"\x00\x00\x00\x18")
            break
        except SolariError as e:
            attempts.append(e.status)
        except Exception as e:
            attempts.append(f"{type(e).__name__}")
    out["poll_statuses"] = attempts
    out.setdefault("retrieved", False)
    out["works_as_evidence"] = out.get("retrieved", False)
    out["works_as_embeddable_video"] = bool(out.get("is_video_container"))
    return out


async def opt3_record_video(session, led) -> dict:
    """The two independent failure modes, probed separately."""
    from playwright.async_api import async_playwright

    out: dict = {"option": "3_record_video"}
    vdir = SCRATCH / "g3_recordvideo"
    if vdir.exists():
        shutil.rmtree(vdir)
    vdir.mkdir(parents=True)

    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp(session.cdp_endpoint)

        # Reason (a): the existing context cannot be reconfigured.
        existing = b.contexts[0] if b.contexts else None
        out["existing_context_present"] = existing is not None
        out["existing_context_has_record_video_setter"] = hasattr(existing, "record_video")

        # Can a fresh context be created over CDP with record_video_dir at all?
        try:
            ctx = await b.new_context(record_video_dir=str(vdir),
                                      record_video_size={"width": 640, "height": 480})
            out["new_context_with_record_video_dir"] = "accepted"
            page = await ctx.new_page()
            await page.goto(PAGE)
            await asyncio.sleep(4)
            vid = page.video
            out["page_video_object"] = vid is not None
            await ctx.close()
            if vid is not None:
                try:
                    p = await asyncio.wait_for(vid.path(), timeout=15)
                    out["video_path_reported"] = str(p)
                    out["path_exists_locally"] = pathlib.Path(p).exists()
                except Exception as exc:
                    out["video_path_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
                try:
                    dest = vdir / "saved.webm"
                    await asyncio.wait_for(vid.save_as(str(dest)), timeout=20)
                    out["save_as_ok"] = dest.exists()
                    out["save_as_bytes"] = dest.stat().st_size if dest.exists() else 0
                except Exception as exc:
                    out["save_as_ok"] = False
                    out["save_as_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        except Exception as exc:
            out["new_context_with_record_video_dir"] = "rejected"
            out["new_context_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"

        await b.close()

    out["files_landed_locally"] = sorted(p.name for p in vdir.glob("*"))
    out["works"] = bool(out.get("save_as_ok")) or bool(out["files_landed_locally"])
    return out


async def main() -> int:
    from solari_browser import Solari

    led = Ledger()
    r: dict[str, object] = {"gate": "G3"}
    solari = Solari(api_key=api_key())
    try:
        s1 = await solari.sessions.create()
        t0 = time.monotonic()
        try:
            r["opt1"] = await opt1_screencast(s1, led)
        finally:
            await solari.sessions.release_and_wait(s1.id)
            led.browser("g3-screencast", time.monotonic() - t0)

        r["opt2"] = await opt2_replay(solari, led)

        s3 = await solari.sessions.create()
        t0 = time.monotonic()
        try:
            r["opt3"] = await opt3_record_video(s3, led)
        finally:
            await solari.sessions.release_and_wait(s3.id)
            led.browser("g3-recordvideo", time.monotonic() - t0)

        r["chosen"] = ("screencast" if r["opt1"].get("works")
                       else "replay" if r["opt2"].get("works_as_evidence") else "none")
        r["verdict"] = "holds" if r["chosen"] != "none" else "fails"
        return 0 if r["verdict"] == "holds" else 1
    except Exception as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
        r["verdict"] = "fails"
        return 1
    finally:
        await solari.close()
        r["ledger"] = led.summary()
        emit(r)
        write("g3.json", r)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
