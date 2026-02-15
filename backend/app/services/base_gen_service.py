from __future__ import annotations
"""Base generation service — unified retry, fallback, timeout, and cost tracking."""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class GenResult(Generic[T]):
    """Standardized generation result."""
    data: T
    provider: str
    latency_ms: int
    cost_estimate: float
    retries_used: int
    fallback_used: bool = False


@dataclass
class GenServiceConfig:
    """Configuration for a generation service."""
    max_retries: int = 3
    retry_delay: float = 2.0
    timeout: float = 180.0
    fallback_enabled: bool = True


class BaseGenService(ABC, Generic[T]):
    """Abstract base class for all generation services.

    Provides:
    - Automatic retry with exponential backoff
    - Optional fallback strategy
    - Timeout enforcement
    - Cost tracking and metrics
    """

    service_name: str = "unknown"
    config: GenServiceConfig

    def __init__(self, config: GenServiceConfig | None = None):
        self.config = config or GenServiceConfig()
        self._total_calls = 0
        self._total_cost = 0.0
        self._total_errors = 0
        self._total_latency_ms = 0

    async def execute(self, **kwargs: Any) -> GenResult[T]:
        """Unified execution entry point with retry/fallback/metrics."""
        self._total_calls += 1
        start = time.monotonic()
        last_error: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    self._generate(**kwargs),
                    timeout=self.config.timeout,
                )
                latency = int((time.monotonic() - start) * 1000)
                cost = self._estimate_cost(**kwargs)
                self._total_cost += cost
                self._total_latency_ms += latency

                return GenResult(
                    data=result,
                    provider=self.service_name,
                    latency_ms=latency,
                    cost_estimate=cost,
                    retries_used=attempt,
                )
            except Exception as e:
                last_error = e
                self._total_errors += 1
                logger.warning(
                    "%s attempt %d/%d failed: %s",
                    self.service_name, attempt + 1, self.config.max_retries + 1, e,
                )
                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))

        # All retries exhausted — try fallback
        if self.config.fallback_enabled:
            try:
                logger.info("%s: attempting fallback...", self.service_name)
                result = await self._fallback(**kwargs)
                latency = int((time.monotonic() - start) * 1000)
                self._total_latency_ms += latency
                return GenResult(
                    data=result,
                    provider=f"{self.service_name}_fallback",
                    latency_ms=latency,
                    cost_estimate=0.0,
                    retries_used=self.config.max_retries,
                    fallback_used=True,
                )
            except NotImplementedError:
                pass
            except Exception as fb_err:
                logger.error("%s fallback failed: %s", self.service_name, fb_err)

        raise RuntimeError(
            f"{self.service_name} failed after {self.config.max_retries} retries: {last_error}"
        )

    @abstractmethod
    async def _generate(self, **kwargs: Any) -> T:
        """Subclass implements actual generation logic."""
        ...

    async def _fallback(self, **kwargs: Any) -> T:
        """Optional fallback — override in subclass."""
        raise NotImplementedError(f"{self.service_name} has no fallback")

    def _estimate_cost(self, **kwargs: Any) -> float:
        """Optional cost estimation — override in subclass."""
        return 0.0

    def get_metrics(self) -> dict[str, Any]:
        """Return usage statistics for this service."""
        return {
            "service": self.service_name,
            "total_calls": self._total_calls,
            "total_cost": round(self._total_cost, 4),
            "total_errors": self._total_errors,
            "error_rate": round(self._total_errors / max(self._total_calls, 1), 3),
            "avg_latency_ms": (
                round(self._total_latency_ms / max(self._total_calls - self._total_errors, 1))
                if self._total_calls > self._total_errors else 0
            ),
        }
