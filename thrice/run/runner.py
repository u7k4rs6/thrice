"""One run: connect over CDP, execute the plan's steps, evaluate both predicates.

Three runs happen concurrently, each with its own Solari browser session and
its own context, so they share nothing. Screencast capture is per D6 and per
the G3 result: frames arrive in the CDP message stream, which means they land
locally rather than on the browser host.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import time
from pathlib import Path
from typing import Any

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..plan.schema import Plan
from ..score.predicates import build_locator, evaluate


def resolve_url(base_url: str, path: str) -> str:
    """Join a plan's root-relative path onto the environment's base URL.

    Not string concatenation. The preview URL carries a signed `pt_token` in its
    query string, so `base + path` appends the path to the QUERY, producing
    `https://host/?pt_token=XYZ/trace/abc`. The browser then loads `/`, which
    jaeger-ui renders as the Search page whatever path was asked for.

    That is how a day-5 run put four attempts on the search page while asking
    for /trace/<id>, and why #4075 appeared to work: it asked for /search and
    `/` happens to render Search, so the mistake was invisible on the only plan
    that had been run until then.

    Query parameters from the plan's path merge over the base URL's, so a plan
    can pass its own params without dropping the token.
    """
    base = urlsplit(base_url)
    raw_path, _, raw_query = path.partition("?")
    merged = dict(parse_qsl(base.query)) | dict(parse_qsl(raw_query))
    return urlunsplit((base.scheme, base.netloc, raw_path or "/", urlencode(merged), ""))

STEP_SETTLE_MS = 1200


class RunFailed(Exception):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


async def _resolve(page: Any, step: Any) -> Any:
    """First locator that resolves wins. All missing is locator_miss."""
    last = ""
    for i, loc in enumerate(step.locators):
        try:
            handle = build_locator(page, loc)
            await handle.wait_for(state="attached", timeout=step.timeout_ms)
            return handle, i
        except Exception as exc:
            last = f"{loc.by}={loc.value}: {type(exc).__name__}"
    raise RunFailed("locator_miss", f"no locator resolved for step {step.id} ({last})")


async def run_one(
    solari: Any,
    plan: Plan,
    base_url: str,
    run_index: int,
    artifact_dir: Path,
    guard: Any,
) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    rec: dict[str, Any] = {"run_index": run_index, "events": [], "completed": False}
    frames_dir = artifact_dir / f"run_{run_index}_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    t_browser = time.monotonic()

    async with guard.browsers:
        session = await solari.sessions.create()
        rec["session_id"] = "[redacted]"
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.connect_over_cdp(session.cdp_endpoint)
                ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                await page.set_viewport_size({"width": 1280, "height": 800})

                console: list[dict[str, str]] = []
                page.on("console", lambda m: console.append({"level": m.type, "text": m.text[:200]}))

                cdp = await ctx.new_cdp_session(page)
                frames: list[bytes] = []

                def on_frame(ev: dict) -> None:
                    frames.append(base64.b64decode(ev["data"]))
                    asyncio.create_task(
                        cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]}))

                cdp.on("Page.screencastFrame", on_frame)
                await cdp.send("Page.startScreencast",
                               {"format": "png", "quality": 70, "everyNthFrame": 2,
                                "maxWidth": 900, "maxHeight": 600})

                t_run = time.monotonic()
                try:
                    for seq, step in enumerate(plan.steps):
                        t0 = time.monotonic()
                        ev: dict[str, Any] = {"step_id": step.id, "seq": seq,
                                              "action": step.action, "locator_index": None}
                        try:
                            if step.action == "goto":
                                await page.goto(resolve_url(base_url, step.args["path"]),
                                                wait_until="domcontentloaded",
                                                timeout=step.timeout_ms)
                            elif step.action == "wait_for":
                                if step.locators:
                                    handle, idx = await _resolve(page, step)
                                    ev["locator_index"] = idx
                                    await handle.wait_for(state="visible", timeout=step.timeout_ms)
                                else:
                                    await asyncio.sleep(step.args.get("ms", 1000) / 1000)
                            elif step.action == "click":
                                handle, idx = await _resolve(page, step)
                                ev["locator_index"] = idx
                                await handle.click(timeout=step.timeout_ms)
                                await page.wait_for_timeout(STEP_SETTLE_MS)
                            elif step.action == "assert":
                                pass
                            else:
                                raise RunFailed("harness_error",
                                                f"action {step.action!r} has no implementation")
                            ev["outcome"] = "ok"
                        except RunFailed:
                            ev["outcome"] = "locator_miss"
                            rec["events"].append(ev)
                            raise
                        except Exception as exc:
                            ev["outcome"] = "timeout"
                            ev["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
                            rec["events"].append(ev)
                            raise RunFailed("timeout", f"step {step.id}: {type(exc).__name__}")

                        if step.id in plan.assertion_step_ids:
                            shot = await page.screenshot()
                            ev["screenshot_sha256"] = hashlib.sha256(shot).hexdigest()[:16]
                            (artifact_dir / f"run_{run_index}_{step.id}.png").write_bytes(shot)

                        ev["t_ms"] = int((time.monotonic() - t0) * 1000)
                        rec["events"].append(ev)

                    # Both predicates are evaluated on every run (D4).
                    a = await evaluate(page, plan.actual_predicate)
                    e = await evaluate(page, plan.expected_predicate)
                    rec["actual_predicate_held"] = a["held"]
                    rec["actual_detail"] = a["detail"]
                    rec["expected_predicate_held"] = e["held"]
                    rec["expected_detail"] = e["detail"]
                    from ..score.verdict import run_reproduced
                    rec["reproduced"] = run_reproduced(a["held"], e["held"])
                    rec["completed"] = True
                except RunFailed as exc:
                    rec["incomplete_reason"] = exc.reason
                    rec["incomplete_detail"] = exc.detail
                finally:
                    rec["run_seconds"] = round(time.monotonic() - t_run, 2)
                    try:
                        await cdp.send("Page.stopScreencast")
                        await cdp.detach()
                    except Exception:
                        pass
                    for i, data in enumerate(frames):
                        (frames_dir / f"f{i:05d}.png").write_bytes(data)
                    rec["frames"] = len(frames)
                    rec["console_errors"] = [c for c in console if c["level"] == "error"][:10]
                    await browser.close()
        except Exception as exc:
            rec.setdefault("incomplete_reason", "harness_error")
            rec.setdefault("incomplete_detail", f"{type(exc).__name__}: {str(exc)[:200]}")
        finally:
            try:
                await solari.sessions.release_and_wait(session.id)
            except Exception:
                pass
            secs = time.monotonic() - t_browser
            guard.add_browser(secs)
            rec["browser_seconds"] = round(secs, 1)
    return rec


async def run_three(solari, plan, base_url, artifact_dir, guard) -> list[dict[str, Any]]:
    return list(await asyncio.gather(
        *[run_one(solari, plan, base_url, i, artifact_dir, guard) for i in range(3)]
    ))
