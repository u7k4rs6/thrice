"""Plan schema. The full D4 predicate set is specified; today only two are implemented.

Day 3 builds a vertical slice for one corpus entry, so `element_visible` and
`element_absent` are the only predicate types with an evaluator. The rest are
declared here so the schema is the contract from the start and adding an
evaluator later does not mean reshaping plans that already exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PLAN_VERSION = 1

#: Every predicate type from docs/01-prd.md D4. `implemented` gates the evaluator.
PREDICATE_TYPES: dict[str, bool] = {
    "element_visible": True,
    "element_absent": True,
    "text_present": True,
    "text_absent": True,
    "url_matches": False,
    "console_error": False,
    "network_response": False,
    "attribute_equals": False,
    "count_equals": False,
    "screenshot_region_digest_equals": False,
}

#: Closed action allowlist. An unknown action is a validation error, never a
#: skipped step (docs/03-security-and-access.md section 3).
ACTIONS: dict[str, bool] = {
    "goto": True,
    "click": True,
    "wait_for": True,
    "assert": True,
    "fill": False,
    "press": False,
    "select": False,
    "scroll": False,
}

#: Locator strategies. No XPath, ever, and no JavaScript.
LOCATOR_BY = ("role", "text", "label", "testid", "css")


@dataclass(frozen=True)
class Locator:
    by: Literal["role", "text", "label", "testid", "css"]
    value: str
    name_re: str | None = None
    nth: int | None = None


@dataclass(frozen=True)
class Predicate:
    type: str
    args: dict[str, Any]
    #: Human-readable, used in reports. Never free text from a planner.
    summary: str = ""


@dataclass(frozen=True)
class Step:
    id: str
    action: str
    locators: tuple[Locator, ...] = ()
    args: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 15000


@dataclass(frozen=True)
class Seed:
    id: str
    endpoint: str
    payload: dict[str, Any]
    expected_response: dict[str, Any] = field(default_factory=lambda: {"status": 200})


@dataclass(frozen=True)
class AppSpec:
    name: str
    version: str
    ui_port: int
    otlp_port: int
    read_only_ui: bool = True


@dataclass(frozen=True)
class Plan:
    plan_version: int
    issue: dict[str, Any]
    app: AppSpec
    seeds: tuple[Seed, ...]
    steps: tuple[Step, ...]
    expected_predicate: Predicate
    actual_predicate: Predicate
    assertion_step_ids: tuple[str, ...] = ()
    notes: str = ""
