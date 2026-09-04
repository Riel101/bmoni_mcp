"""Per-principal rate limiting and max-concurrency.

A token bucket protects the partner's upstream budget and avoids 429s/cost
abuse; ``BMONI_RATE_LIMIT_RPS`` / ``BMONI_RATE_LIMIT_BURST`` configure it.
Heavy tool groups (receipt PDF generation, balance polling, exchange quotes,
provider lookups) are charged more tokens per call.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

HEAVY_TOOL_MARKERS = (
    "receipt_pdf",
    "balance",
    "account_balances",
    "exchange_rate",
    "exchange_convert",
    "exchange_quote",
    "bvn_lookup",
    "nin_lookup",
    "payout_banks",
    "payout_bank_branches",
    "nigerian_banks",
    "verify_nigeria",
)


def tool_weight(tool: str) -> float:
    """Tokens a single call costs. Heavy groups cost more."""
    return 3.0 if any(marker in tool for marker in HEAVY_TOOL_MARKERS) else 1.0


class RateLimiter:
    """Thread/loop-agnostic token bucket keyed by principal."""

    def __init__(self, rps: float, burst: int) -> None:
        self.rps = max(float(rps), 0.01)
        self.burst = max(int(burst), 1)
        self._buckets: dict[str, tuple[float, float]] = {}

    def allow(self, key: str, *, weight: float = 1.0) -> tuple[bool, float]:
        """Return (allowed, retry_after_seconds)."""
        if key == "":
            key = "__anonymous__"
        now = time.monotonic()
        tokens, last = self._buckets.get(key, (float(self.burst), now))
        tokens = min(float(self.burst), tokens + (now - last) * self.rps)
        if tokens >= weight:
            self._buckets[key] = (tokens - weight, now)
            return True, 0.0
        needed = weight - tokens
        retry_after = needed / self.rps
        self._buckets[key] = (tokens, now)
        return False, round(retry_after, 3)

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._buckets.clear()
        else:
            self._buckets.pop(key, None)


class ConcurrencyLimiter:
    """Global in-flight call cap; 0 = unlimited."""

    def __init__(self, max_concurrent: int) -> None:
        self.max_concurrent = max_concurrent
        self._sems: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}

    def _semaphore(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        sem = self._sems.get(loop)
        if sem is None:
            sem = asyncio.Semaphore(self.max_concurrent)
            self._sems[loop] = sem
        return sem

    @asynccontextmanager
    async def guard(self):
        if self.max_concurrent <= 0:
            yield
            return
        sem = self._semaphore()
        async with sem:
            yield
