"""Attempt orchestrator: plan file to verdict, for one entry on one version.

Day-3 vertical slice. No differ, no report HTML, no poster, no planner.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
import time
import uuid
from typing import Any

from .budget.guard import BudgetExceeded, BudgetGuard
from .env.manager import EnvError, EnvManager, redact
from .env.seed import stamp_now
from .plan.validate import load
from .run.runner import run_three
from .score.verdict import INCONCLUSIVE, verdict_for

BASE_URL = "https://api.getsolari.com"


def api_key() -> str:
    raw = os.environ.get("SOLARI_API_KEY", "").strip()
    if not raw:
        env = pathlib.Path(__file__).parents[1] / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("SOLARI_API_KEY="):
                    raw = line.split("=", 1)[1].strip()
    if not raw.startswith("slr_live_"):
        raise SystemExit("SOLARI_API_KEY missing or malformed")
    return raw


async def attempt(plan_path: str, guard: BudgetGuard) -> dict[str, Any]:
    from solari_browser import Solari
    from solari_sandbox import SandboxClient

    plan = load(plan_path)
    attempt_id = f"{plan.issue['number']}-{plan.app.version}-{uuid.uuid4().hex[:6]}"
    art = pathlib.Path("artifacts") / attempt_id
    art.mkdir(parents=True, exist_ok=True)

    rec: dict[str, Any] = {
        "attempt_id": attempt_id,
        "plan_file": plan_path,
        "issue": plan.issue,
        "app": {"name": plan.app.name, "version": plan.app.version},
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    guard.reserve_attempt()
    sc = SandboxClient(api_key=api_key(), base_url=BASE_URL)
    env = EnvManager(sc, guard)
    solari = Solari(api_key=api_key())
    sbx = None
    t_sbx = None
    try:
        async with guard.sandboxes:
            sbx, envinfo = await env.acquire(plan.app.version, attempt_id)
            t_sbx = time.monotonic()
            rec["env"] = envinfo

            stamped = [type(s)(id=s.id, endpoint=s.endpoint,
                               payload=stamp_now(s.payload),
                               expected_response=s.expected_response)
                       for s in plan.seeds]
            rec["seeds"] = await env.seed(sbx, stamped, plan.app.otlp_port)
            await asyncio.sleep(3)

            svc = plan.seeds[0].payload["resourceSpans"][0]["resource"]["attributes"][0]["value"]["stringValue"]
            rec["seed_visible"] = await env.verify_seed_visible(sbx, svc, plan.app.ui_port)
            if rec["seed_visible"]["traces"] < 1:
                raise EnvError(
                    f"seed accepted but not queryable for service {svc!r}: "
                    f"{rec['seed_visible']}. A run against an unseeded store would "
                    "produce a meaningless verdict."
                )

            base_url, prev = await env.preview(sbx, plan.app.ui_port)
            rec["preview"] = {k: v for k, v in prev.items() if k != "statuses"}
            rec["preview"]["status_sequence"] = prev["statuses"][:8]

            rec["runs"] = await run_three(solari, plan, base_url, art, guard)

        rec |= verdict_for(rec["runs"])
    except BudgetExceeded as exc:
        rec |= {"verdict": INCONCLUSIVE, "reason": "budget_refused", "error": str(exc)}
    except EnvError as exc:
        rec |= {"verdict": INCONCLUSIVE, "reason": "environment", "error": str(exc)}
    except Exception as exc:
        rec |= {"verdict": INCONCLUSIVE, "reason": "harness_error",
                "error": f"{type(exc).__name__}: {exc}"}
    finally:
        # Reap through the manager, which tracks everything it created. The
        # orchestrator alone cannot do this: acquire() may fail after creating
        # a sandbox, in which case `sbx` here is still None.
        rec["reaped"] = await env.reap()
        rec["sandbox_killed"] = all(r == "ok" for r in rec["reaped"]) if rec["reaped"] else True
        if t_sbx:
            guard.add_sandbox(time.monotonic() - t_sbx)
        await solari.close()
        await sc.aclose()
        guard.settle()
        rec["cost"] = guard.summary()
        out = art / "attempt.json"
        out.write_text(redact(json.dumps(rec, indent=2, default=str)))
        rec["_written"] = str(out)
    return rec


async def main() -> int:
    ap = argparse.ArgumentParser(description="Run one thrice attempt, plan file to verdict.")
    ap.add_argument("plans", nargs="+")
    args = ap.parse_args()

    guard = BudgetGuard()
    results = []
    for p in args.plans:
        r = await attempt(p, guard)
        results.append(r)
        print(redact(json.dumps({
            k: v for k, v in r.items()
            if k in ("attempt_id", "app", "fork_seconds", "health_seconds", "seed_visible",
                     "preview", "verdict", "runs_reproduced", "runs_total", "reason",
                     "error", "sandbox_killed", "cost", "_written")
        }, indent=2, default=str)))
        for run in r.get("runs", []):
            print(f"    run {run['run_index']}: completed={run.get('completed')} "
                  f"actual={run.get('actual_predicate_held')} "
                  f"expected={run.get('expected_predicate_held')} "
                  f"reproduced={run.get('reproduced')} "
                  f"frames={run.get('frames')} "
                  f"{run.get('incomplete_reason','')} {run.get('incomplete_detail','')}")
    print("\n=== summary ===")
    for r in results:
        print(f"  {r['app']['version']:8} {r.get('verdict'):16} "
              f"{r.get('runs_reproduced')}/{r.get('runs_total')} {r.get('reason') or ''}")
    print(f"  cost: {json.dumps(guard.summary())}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
