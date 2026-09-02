"""Budget ceilings and concurrency semaphores. Ledger persistence is deferred.

Rates and ceilings from docs/01-prd.md section 8 at Starter (C1). The
semaphores are the more important half today: the sandbox limit of 2 is a
platform cap, and exceeding it returns a non-retryable 429.
"""

from __future__ import annotations

import asyncio

RATE_BROWSER_S = 0.10 / 3600.0
RATE_SANDBOX_S = 0.057 / 3600.0

ATTEMPT_CEILING_USD = 0.10
DAILY_CEILING_USD = 2.00

#: Starter plan hard cap. Never raise this without changing plan.
MAX_SANDBOXES = 2
#: Self-imposed: three runs per attempt. Starter allows 20, so browsers are
#: not the scarce resource; the sandbox cap is what serialises attempts.
MAX_BROWSERS = 3


class BudgetExceeded(RuntimeError):
    """Raised before anything is launched, never after."""


class BudgetGuard:
    def __init__(
        self,
        attempt_ceiling: float = ATTEMPT_CEILING_USD,
        daily_ceiling: float = DAILY_CEILING_USD,
    ) -> None:
        self.attempt_ceiling = attempt_ceiling
        self.daily_ceiling = daily_ceiling
        self._spent = 0.0
        self._reserved = 0.0
        self.sandbox_seconds = 0.0
        self.browser_seconds = 0.0
        self.sandboxes = asyncio.Semaphore(MAX_SANDBOXES)
        self.browsers = asyncio.Semaphore(MAX_BROWSERS)

    def reserve_attempt(self) -> None:
        """Refuse before any Solari call, so a refusal costs nothing."""
        if self._spent + self._reserved + self.attempt_ceiling > self.daily_ceiling:
            raise BudgetExceeded(
                f"attempt would cross the daily ceiling: spent ${self._spent:.4f} "
                f"+ reserved ${self._reserved:.4f} + ceiling ${self.attempt_ceiling:.2f} "
                f"> ${self.daily_ceiling:.2f}"
            )
        self._reserved += self.attempt_ceiling

    def settle(self) -> None:
        """Replace the reservation with what was actually consumed."""
        self._reserved = max(0.0, self._reserved - self.attempt_ceiling)
        self._spent = self.usd()

    def add_sandbox(self, seconds: float) -> None:
        self.sandbox_seconds += seconds

    def add_browser(self, seconds: float) -> None:
        self.browser_seconds += seconds

    def usd(self) -> float:
        return self.sandbox_seconds * RATE_SANDBOX_S + self.browser_seconds * RATE_BROWSER_S

    def summary(self) -> dict[str, float]:
        return {
            "sandbox_seconds": round(self.sandbox_seconds, 1),
            "browser_seconds": round(self.browser_seconds, 1),
            "usd": round(self.usd(), 5),
            "attempt_ceiling_usd": self.attempt_ceiling,
            "over_attempt_ceiling": self.usd() > self.attempt_ceiling,
        }
