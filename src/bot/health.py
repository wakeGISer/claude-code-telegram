"""Bot health tracking — request stats, uptime, and system metrics."""

import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Optional


@dataclass
class RequestRecord:
    """Single request outcome."""

    start_time: float
    duration_seconds: float
    success: bool
    error: Optional[str] = None


class BotHealthTracker:
    """Track bot health metrics in-memory. Thread-safe."""

    def __init__(self) -> None:
        self._boot_time = time.monotonic()
        self._boot_wall = datetime.now(timezone.utc)
        self._lock = Lock()
        self._today_key = self._date_key()

        # Today's stats
        self._total_requests = 0
        self._successful = 0
        self._timeouts = 0
        self._errors = 0
        self._total_duration = 0.0

        # Last request
        self._last_request: Optional[RequestRecord] = None

        # Active request tracking
        self._active_start: Optional[float] = None
        self._active_tool: Optional[str] = None

    @staticmethod
    def _date_key() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _rotate_if_new_day(self) -> None:
        """Reset counters on day change."""
        key = self._date_key()
        if key != self._today_key:
            self._today_key = key
            self._total_requests = 0
            self._successful = 0
            self._timeouts = 0
            self._errors = 0
            self._total_duration = 0.0

    def request_started(self) -> None:
        """Mark the beginning of a Claude request."""
        with self._lock:
            self._active_start = time.monotonic()
            self._active_tool = None

    def tool_updated(self, tool_name: str) -> None:
        """Update the currently executing tool name."""
        with self._lock:
            self._active_tool = tool_name

    def request_finished(
        self, success: bool, error: Optional[str] = None
    ) -> None:
        """Record a completed request."""
        with self._lock:
            self._rotate_if_new_day()
            duration = 0.0
            if self._active_start is not None:
                duration = time.monotonic() - self._active_start

            self._total_requests += 1
            self._total_duration += duration
            if success:
                self._successful += 1
            elif error and "timed out" in error.lower():
                self._timeouts += 1
            else:
                self._errors += 1

            self._last_request = RequestRecord(
                start_time=time.time() - duration,
                duration_seconds=duration,
                success=success,
                error=error,
            )
            self._active_start = None
            self._active_tool = None

    def get_active_elapsed(self) -> Optional[float]:
        """Seconds elapsed for the currently active request, or None."""
        with self._lock:
            if self._active_start is None:
                return None
            return time.monotonic() - self._active_start

    def get_active_tool(self) -> Optional[str]:
        """Currently executing tool name, or None."""
        with self._lock:
            return self._active_tool

    def format_status(self) -> str:
        """Format a compact health status string."""
        with self._lock:
            self._rotate_if_new_day()

            uptime_s = time.monotonic() - self._boot_time
            uptime_str = _format_duration(uptime_s)

            # Last request
            if self._last_request:
                lr = self._last_request
                ago = time.time() - lr.start_time
                last_str = (
                    f"{_format_duration(ago)} ago "
                    f"({lr.duration_seconds:.1f}s, "
                    f"{'ok' if lr.success else 'fail'})"
                )
            else:
                last_str = "none"

            # Active request
            if self._active_start is not None:
                elapsed = time.monotonic() - self._active_start
                tool = self._active_tool or "waiting"
                active_str = f"{_format_duration(elapsed)} — {tool}"
            else:
                active_str = "idle"

            # Today's stats
            avg_s = (
                self._total_duration / self._total_requests
                if self._total_requests > 0
                else 0
            )
            stats_str = (
                f"{self._total_requests} reqs, "
                f"{self._timeouts} timeouts, "
                f"avg {avg_s:.1f}s"
            )

            # System
            disk = shutil.disk_usage("/")
            disk_free_gb = disk.free / (1024**3)
            try:
                load_1m = os.getloadavg()[0]
                sys_str = f"{disk_free_gb:.0f}GB free · load {load_1m:.1f}"
            except OSError:
                sys_str = f"{disk_free_gb:.0f}GB free"

        lines = [
            f"Uptime: {uptime_str}",
            f"Last request: {last_str}",
            f"Active: {active_str}",
            f"Today: {stats_str}",
            f"System: {sys_str}",
        ]
        return "\n".join(lines)


def _format_duration(seconds: float) -> str:
    """Format seconds into a human-readable duration."""
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m{int(seconds % 60)}s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}h{minutes}m"
