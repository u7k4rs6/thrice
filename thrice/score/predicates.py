"""Predicate evaluation. Pure with respect to Solari: it sees a page, nothing else.

Only element_visible and element_absent have evaluators today (day 3 slice).
Every other D4 type raises rather than silently returning False, because a
predicate that quietly fails would turn a harness gap into a verdict.
"""

from __future__ import annotations

from typing import Any

from ..plan.schema import Locator, Predicate


class PredicateNotImplemented(NotImplementedError):
    """A specified but unimplemented predicate type was evaluated."""


def build_locator(page: Any, loc: Locator) -> Any:
    """Resolve a Locator to a Playwright locator. No XPath, no JavaScript."""
    if loc.by == "css":
        base = page.locator(loc.value)
    elif loc.by == "testid":
        base = page.get_by_test_id(loc.value)
    elif loc.by == "text":
        base = page.get_by_text(loc.value)
    elif loc.by == "label":
        base = page.get_by_label(loc.value)
    elif loc.by == "role":
        import re as _re
        kwargs: dict[str, Any] = {}
        if loc.name_re:
            kwargs["name"] = _re.compile(loc.name_re)
        base = page.get_by_role(loc.value, **kwargs)
    else:
        raise PredicateNotImplemented(f"locator strategy {loc.by!r}")
    return base.nth(loc.nth) if loc.nth is not None else base.first


async def evaluate(page: Any, pred: Predicate, timeout_ms: int = 5000) -> dict[str, Any]:
    """Return {held, detail}. Never raises for an ordinary miss, only for a gap."""
    if pred.type == "element_visible":
        loc = build_locator(page, Locator(**pred.args["locator"]))
        try:
            await loc.wait_for(state="visible", timeout=timeout_ms)
            return {"held": True, "detail": "visible"}
        except Exception as exc:
            return {"held": False, "detail": f"not visible: {type(exc).__name__}"}

    if pred.type == "element_absent":
        loc = build_locator(page, Locator(**pred.args["locator"]))
        try:
            await loc.wait_for(state="attached", timeout=timeout_ms)
            visible = await loc.is_visible()
            return {"held": not visible,
                    "detail": "present and visible" if visible else "present but hidden"}
        except Exception:
            return {"held": True, "detail": "absent"}

    raise PredicateNotImplemented(
        f"predicate type {pred.type!r} is specified in the schema but has no evaluator yet"
    )
