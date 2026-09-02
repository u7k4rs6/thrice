"""The D4 reproduction rule and the D5 four-outcome taxonomy. Pure functions."""

from __future__ import annotations

from typing import Any

REPRODUCED = "REPRODUCED"
FLAKY = "FLAKY"
NOT_REPRODUCED = "NOT_REPRODUCED"
INCONCLUSIVE = "INCONCLUSIVE"


def run_reproduced(actual_held: bool | None, expected_held: bool | None) -> bool | None:
    """D4: reproduced only if the actual predicate holds AND the expected fails.

    Both are evaluated every run. `None` on either side means the run did not
    get far enough to evaluate, which is not a False.
    """
    if actual_held is None or expected_held is None:
        return None
    return bool(actual_held) and not bool(expected_held)


def verdict_for(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """D5. Any incomplete run makes the whole attempt INCONCLUSIVE.

    Deliberately strict: a 2-of-3 split where the third run timed out is not
    FLAKY, because FLAKY is a claim about the target and an incomplete run is
    a claim about the harness. Conflating them would let harness failures
    masquerade as findings.
    """
    total = len(runs)
    incomplete = [r for r in runs if not r.get("completed")]
    if incomplete:
        reasons = sorted({str(r.get("incomplete_reason") or "unknown") for r in incomplete})
        return {
            "verdict": INCONCLUSIVE,
            "runs_total": total,
            "runs_reproduced": None,
            "reason": ",".join(reasons),
            "incomplete_runs": [r["run_index"] for r in incomplete],
        }

    n = sum(1 for r in runs if r.get("reproduced") is True)
    if n == total:
        v = REPRODUCED
    elif n == 0:
        v = NOT_REPRODUCED
    else:
        v = FLAKY
    return {"verdict": v, "runs_total": total, "runs_reproduced": n, "reason": None}
