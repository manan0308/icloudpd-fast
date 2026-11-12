"""Live terminal progress for downloads.

One global bar shows photos checked vs. total, download rate, ETA, and a
running tally of new / already-present / failed files plus the current
adaptive worker count. While the bar is active, chatty per-file INFO logs
stay in the log file only; warnings and errors print above the bar without
breaking it.
"""
import logging
from threading import RLock

from tqdm import tqdm

_LOGGER_NAMES = ("icloudpd", "icloud", "unhandled")
_CONSOLE_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)s %(message)s"
_CONSOLE_DATEFMT = "%Y-%m-%d %H:%M:%S"

def human_bytes(num: float) -> str:
    """1234567 -> '1.2 MB'"""
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024
    return f"{num:.1f} TB"

class TqdmLoggingHandler(logging.Handler):
    """Routes log records through tqdm.write so the bar stays intact."""
    def emit(self, record: logging.LogRecord) -> None:
        try:
            tqdm.write(self.format(record))
        except Exception:  # pylint: disable=broad-except
            self.handleError(record)

class ProgressTracker():
    """Thread-safe download progress. Every method no-ops when disabled."""

    def __init__(self, enabled: bool):
        self.enabled = enabled
        self._lock = RLock()
        self._bar: tqdm | None = None
        self._gate = None
        self.new = 0
        self.skipped = 0
        self.failed = 0
        self.bytes = 0

    def start(self, gate) -> None:
        """Open the bar and move console logging out of its way."""
        if not self.enabled:
            return
        self._gate = gate
        self._quiet_console_logging()
        self._bar = tqdm(total=0, unit="photo", desc="downloading",
                         dynamic_ncols=True, smoothing=0.05)

    def _quiet_console_logging(self) -> None:
        """Replace console stream handlers with a WARNING-level tqdm handler.

        File handlers are untouched, so the full INFO/DEBUG detail still
        lands in the log file.
        """
        tqdm_handler = TqdmLoggingHandler(logging.WARNING)
        tqdm_handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT,
                                                    _CONSOLE_DATEFMT))
        for name in _LOGGER_NAMES:
            log = logging.getLogger(name)
            for handler in list(log.handlers):
                if (isinstance(handler, logging.StreamHandler)
                        and not isinstance(handler, logging.FileHandler)):
                    log.removeHandler(handler)
            log.addHandler(tqdm_handler)

    def add_total(self, count: int) -> None:
        """An album reported how many photos it plans to check."""
        if self._bar is None:
            return
        with self._lock:
            self._bar.total += count
            self._bar.refresh()

    def reduce_total(self, count: int) -> None:
        """An album finished early (date cutoff); drop the unchecked rest."""
        if self._bar is None or count <= 0:
            return
        with self._lock:
            self._bar.total = max(self._bar.n, self._bar.total - count)
            self._bar.refresh()

    def advance(self) -> None:
        """One photo fully checked (downloaded, skipped, or failed)."""
        if self._bar is None:
            return
        with self._lock:
            workers = self._gate.limit if self._gate else 0
            self._bar.set_postfix_str(
                f"new {self.new} · have {self.skipped} · fail {self.failed}"
                f" · {human_bytes(self.bytes)} · {workers}w",
                refresh=False)
            self._bar.update(1)

    def count_new(self, nbytes: int) -> None:
        """A file was actually downloaded."""
        with self._lock:
            self.new += 1
            self.bytes += nbytes

    def count_skip(self) -> None:
        """A file was already present locally."""
        with self._lock:
            self.skipped += 1

    def count_fail(self) -> None:
        """A file could not be downloaded after all retries."""
        with self._lock:
            self.failed += 1

    def finish(self) -> None:
        """Close the bar; summary() is still available afterwards."""
        if self._bar is not None:
            self._bar.close()
            self._bar = None

    def summary(self, elapsed) -> str:
        """One friendly line describing what the run did."""
        checked = self.new + self.skipped + self.failed
        parts = [f"{self.new:,} downloaded ({human_bytes(self.bytes)})",
                 f"{self.skipped:,} already on disk"]
        if self.failed:
            parts.append(f"{self.failed:,} FAILED (see log)")
        minutes, seconds = divmod(int(elapsed.total_seconds()), 60)
        hours, minutes = divmod(minutes, 60)
        took = (f"{hours}h {minutes}m {seconds}s" if hours
                else f"{minutes}m {seconds}s" if minutes else f"{seconds}s")
        return (f"checked {checked:,} files in {took} — " + ", ".join(parts))
