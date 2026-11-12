"""AIMD-controlled gate that bounds concurrent downloads.

Additive increase / multiplicative decrease, like TCP congestion control:
grow the allowed parallelism by 1 after every clean streak of downloads,
halve it the moment Apple pushes back (throttle error, session kick,
timeout). The limit hovers just under whatever iCloud tolerates right now.
"""
import logging
from threading import Condition

logger = logging.getLogger("icloudpd")

INCREASE_EVERY = 25  # successful downloads per +1 step
MIN_LIMIT = 2

class AdaptiveGate():
    """Context-manager gate; limit resizes at runtime when adaptive."""

    def __init__(self, initial: int, maximum: int, adaptive: bool = True):
        self._cond = Condition()
        self._max = maximum
        self._limit = min(initial, maximum) if adaptive else maximum
        self._adaptive = adaptive
        self._active = 0
        self._successes = 0
        self._peak = self._limit

    def __enter__(self):
        with self._cond:
            while self._active >= self._limit:
                self._cond.wait()
            self._active += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        with self._cond:
            self._active -= 1
            self._cond.notify_all()
        return False

    def report_success(self) -> None:
        """Count a clean download; raise the limit after a streak."""
        if not self._adaptive:
            return
        with self._cond:
            self._successes += 1
            if self._successes >= INCREASE_EVERY and self._limit < self._max:
                self._successes = 0
                self._limit += 1
                self._peak = max(self._peak, self._limit)
                logger.info("adaptive: %d clean downloads, raising parallel "
                            "downloads to %d", INCREASE_EVERY, self._limit)
                self._cond.notify_all()

    def report_throttle(self) -> None:
        """Apple pushed back: halve the limit and restart the streak."""
        if not self._adaptive:
            return
        with self._cond:
            new_limit = max(MIN_LIMIT, self._limit // 2)
            if new_limit < self._limit:
                logger.warning("adaptive: throttle signal, cutting parallel "
                               "downloads from %d to %d", self._limit, new_limit)
                self._limit = new_limit
            self._successes = 0

    @property
    def limit(self) -> int:
        """Current allowed parallelism."""
        with self._cond:
            return self._limit

    @property
    def peak(self) -> int:
        """Highest limit reached this run — the ceiling Apple tolerated."""
        with self._cond:
            return self._peak
