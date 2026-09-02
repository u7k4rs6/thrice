"""Plan validation. The trust boundary between plan files and anything executed.

A plan is data authored by a human today and by an LLM later (D3), so this
runs before every attempt regardless of provenance. Rejections are hard: an
unknown action is an error, not a skipped step.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import (
    ACTIONS,
    LOCATOR_BY,
    PLAN_VERSION,
    PREDICATE_TYPES,
    AppSpec,
    Locator,
    Plan,
    Predicate,
    Seed,
    Step,
)

#: docs/03-security-and-access.md section 3.
MAX_SEEDS = 8
MAX_SEED_BYTES = 256 * 1024
MAX_STEPS = 40


class PlanInvalid(ValueError):
    """Raised with every problem found, not just the first."""


def _locator(d: dict[str, Any], where: str, errs: list[str]) -> Locator:
    by = d.get("by")
    if by not in LOCATOR_BY:
        errs.append(f"{where}: locator.by must be one of {LOCATOR_BY}, got {by!r}")
    if not isinstance(d.get("value"), str) or not d.get("value"):
        errs.append(f"{where}: locator.value must be a non-empty string")
    return Locator(by=by, value=d.get("value", ""), name_re=d.get("name_re"), nth=d.get("nth"))


def _predicate(d: Any, where: str, errs: list[str]) -> Predicate:
    if not isinstance(d, dict):
        errs.append(f"{where}: must be an object")
        return Predicate(type="", args={})
    t = d.get("type")
    if t not in PREDICATE_TYPES:
        errs.append(f"{where}: unknown predicate type {t!r}; known: {sorted(PREDICATE_TYPES)}")
    elif not PREDICATE_TYPES[t]:
        errs.append(
            f"{where}: predicate type {t!r} is specified but not implemented yet. "
            "Day 3 implements element_visible and element_absent only."
        )
    args = d.get("args")
    if not isinstance(args, dict):
        errs.append(f"{where}: args must be an object")
        args = {}
    if t in ("element_visible", "element_absent"):
        if "locator" not in args:
            errs.append(f"{where}: {t} requires args.locator")
        else:
            _locator(args["locator"], f"{where}.args.locator", errs)
    if t in ("text_present", "text_absent"):
        if "re" not in args:
            errs.append(f"{where}: {t} requires args.re")
        if args.get("scope"):
            _locator(args["scope"], f"{where}.args.scope", errs)
    return Predicate(type=t or "", args=args, summary=d.get("summary", ""))


def validate(raw: dict[str, Any]) -> Plan:
    errs: list[str] = []

    if raw.get("plan_version") != PLAN_VERSION:
        errs.append(f"plan_version must be {PLAN_VERSION}, got {raw.get('plan_version')!r}")

    app_d = raw.get("app") or {}
    app = AppSpec(
        name=app_d.get("name", ""),
        version=app_d.get("version", ""),
        ui_port=int(app_d.get("ui_port", 16686)),
        otlp_port=int(app_d.get("otlp_port", 4318)),
        read_only_ui=bool(app_d.get("read_only_ui", True)),
    )
    if not app.version:
        errs.append("app.version is required; a corpus entry is pinned to one release")

    seeds_raw = raw.get("seeds") or []
    if len(seeds_raw) > MAX_SEEDS:
        errs.append(f"at most {MAX_SEEDS} seeds, got {len(seeds_raw)}")
    seeds = []
    for i, s in enumerate(seeds_raw):
        if s.get("endpoint") != "/v1/traces":
            errs.append(f"seeds[{i}]: endpoint must be /v1/traces in v1")
        size = len(json.dumps(s.get("payload", {})))
        if size > MAX_SEED_BYTES:
            errs.append(f"seeds[{i}]: payload {size} bytes exceeds {MAX_SEED_BYTES}")
        seeds.append(
            Seed(
                id=s.get("id", f"s{i}"),
                endpoint=s.get("endpoint", ""),
                payload=s.get("payload", {}),
                expected_response=s.get("expected_response", {"status": 200}),
            )
        )

    steps_raw = raw.get("steps") or []
    if not steps_raw:
        errs.append("at least one step is required")
    if len(steps_raw) > MAX_STEPS:
        errs.append(f"at most {MAX_STEPS} steps, got {len(steps_raw)}")
    steps, seen = [], set()
    for i, s in enumerate(steps_raw):
        sid = s.get("id")
        if not sid:
            errs.append(f"steps[{i}]: id is required; the differ aligns runs on it")
        if sid in seen:
            errs.append(f"steps[{i}]: duplicate step id {sid!r}")
        seen.add(sid)
        act = s.get("action")
        if act not in ACTIONS:
            errs.append(f"steps[{i}]: unknown action {act!r}; allowlist is {sorted(ACTIONS)}")
        elif not ACTIONS[act]:
            errs.append(f"steps[{i}]: action {act!r} is specified but not implemented yet")
        locs = tuple(
            _locator(d, f"steps[{i}].locators[{j}]", errs)
            for j, d in enumerate(s.get("locators") or [])
        )
        args = s.get("args") or {}
        if act == "goto":
            path = args.get("path", "")
            if not isinstance(path, str) or not path.startswith("/"):
                errs.append(f"steps[{i}]: goto args.path must be a root-relative path")
            if "://" in path:
                errs.append(
                    f"steps[{i}]: goto args.path must not contain a scheme or host. "
                    "A plan supplies a path; the base URL comes from the environment manager."
                )
        steps.append(
            Step(id=sid or f"st{i}", action=act or "", locators=locs, args=args,
                 timeout_ms=int(s.get("timeout_ms", 15000)))
        )

    expected = _predicate(raw.get("expected_predicate"), "expected_predicate", errs)
    actual = _predicate(raw.get("actual_predicate"), "actual_predicate", errs)

    for sid in raw.get("assertion_step_ids") or []:
        if sid not in seen:
            errs.append(f"assertion_step_ids: {sid!r} is not a step id")

    if errs:
        raise PlanInvalid("plan is invalid:\n  - " + "\n  - ".join(errs))

    return Plan(
        plan_version=PLAN_VERSION,
        issue=raw.get("issue") or {},
        app=app,
        seeds=tuple(seeds),
        steps=tuple(steps),
        expected_predicate=expected,
        actual_predicate=actual,
        assertion_step_ids=tuple(raw.get("assertion_step_ids") or []),
        notes=raw.get("notes", ""),
    )


def load(path: str | Path) -> Plan:
    return validate(json.loads(Path(path).read_text()))
