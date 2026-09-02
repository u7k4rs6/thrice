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


def build_locator(page: Any, loc: Locator, first: bool = True) -> Any:
    """Resolve a Locator to a Playwright locator. No XPath, no JavaScript.

    `first=False` returns the unnarrowed locator so a caller can ask about all
    matches. Steps still want a single element; predicates want the set.
    """
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
    if loc.nth is not None:
        return base.nth(loc.nth)
    return base.first if first else base


async def evaluate(page: Any, pred: Predicate, timeout_ms: int = 5000) -> dict[str, Any]:
    """Return {held, detail}. Never raises for an ordinary miss, only for a gap."""
    if pred.type in ("element_visible", "element_absent"):
        spec = Locator(**pred.args["locator"])
        # ANY match, not just the first. build_locator pins .first when nth is
        # unset, which silently answers the wrong question when a page holds
        # several matching elements and only some are visible. #4045 scored
        # incorrect that way: jaeger-ui renders more than one VerticalResizer,
        # .first happened to be a hidden one, and both releases read "absent".
        # "Is any matching element visible" is what these predicates mean.
        base = build_locator(page, spec, first=spec.nth is not None)
        try:
            await base.first.wait_for(state="attached", timeout=timeout_ms)
        except Exception:
            return {"held": pred.type == "element_absent", "detail": "no match attached"}
        n = await base.count()
        vis = 0
        for i in range(n):
            try:
                if await base.nth(i).is_visible():
                    vis += 1
            except Exception:
                pass
        detail = f"{vis} visible of {n} matching"
        return {"held": (vis > 0) if pred.type == "element_visible" else (vis == 0),
                "detail": detail}

    if pred.type in ("text_present", "text_absent"):
        import re as _re
        scope = pred.args.get("scope")
        target = build_locator(page, Locator(**scope)) if scope else page.locator("body")
        try:
            await target.wait_for(state="attached", timeout=timeout_ms)
            text = await target.inner_text()
        except Exception as exc:
            # A missing scope is not the same as absent text, and conflating
            # them would let a broken locator read as a passing predicate.
            return {"held": False, "detail": f"scope not found: {type(exc).__name__}"}
        hit = _re.search(pred.args["re"], text) is not None
        held = hit if pred.type == "text_present" else not hit
        return {"held": held, "detail": f"scope text {text[:80]!r}"}

    raise PredicateNotImplemented(
        f"predicate type {pred.type!r} is specified in the schema but has no evaluator yet"
    )
