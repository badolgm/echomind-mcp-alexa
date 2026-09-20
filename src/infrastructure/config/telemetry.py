"""Dependency-free telemetry and metrics for the ecosystem.

Collects request latency percentiles (p50/p95/p99), per-tool call counts and
quota-fallback activations. Pure standard library; no Prometheus client, no
external metrics backend. Exposition happens through the ``/metrics`` endpoint
in the composition root.
"""

from __future__ import annotations

import math
import statistics
import threading
import time
from collections.abc import Callable
from typing import Any

MetricListener = Callable[[], None]


def percentile(sorted_values: list[float], ratio: float) -> float:
    """Nearest-rank percentile of an ascending sorted list."""
    if not sorted_values:
        return 0.0
    index = min(
        len(sorted_values) - 1,
        max(0, math.ceil(ratio * len(sorted_values)) - 1),
    )
    return round(float(sorted_values[index]), 2)


class Telemetry:
    """Thread-safe in-memory metrics registry.

    Latencies are stored per operation and only sorted on read, which keeps
    recording O(1) and the module independent of any metrics dependency.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started = time.perf_counter()
        self._latencies: dict[str, list[float]] = {}
        self._tool_calls: dict[str, int] = {}
        self._fallbacks = 0

    @property
    def fallback_listener(self) -> MetricListener:
        """Return a zero-arg callable recording a fallback activation."""
        return self.record_fallback

    def record_latency(self, operation: str, milliseconds: float) -> None:
        with self._lock:
            self._latencies.setdefault(operation, []).append(milliseconds)

    def record_tool_call(self, tool_name: str) -> None:
        with self._lock:
            self._tool_calls[tool_name] = self._tool_calls.get(tool_name, 0) + 1

    def record_fallback(self) -> None:
        with self._lock:
            self._fallbacks += 1

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serialisable metrics snapshot."""
        with self._lock:
            uptime = round(time.perf_counter() - self._started, 2)
            tool_calls = dict(self._tool_calls)
            fallbacks = self._fallbacks
            latency_ms: dict[str, dict[str, float | int]] = {}
            for operation, values in self._latencies.items():
                ordered = sorted(values)
                latency_ms[operation] = {
                    "count": len(ordered),
                    "mean_ms": (round(statistics.mean(ordered), 2) if ordered else 0.0),
                    "p50_ms": percentile(ordered, 0.5),
                    "p95_ms": percentile(ordered, 0.95),
                    "p99_ms": percentile(ordered, 0.99),
                }
        return {
            "uptime_seconds": uptime,
            "tool_calls": tool_calls,
            "total_tool_calls": sum(tool_calls.values()),
            "fallbacks_activated": fallbacks,
            "latency_ms": latency_ms,
        }

    def summary(self) -> str:
        """Render a human-readable metrics report (used by the demo script)."""
        data = self.snapshot()
        lines = [
            "ECHOSYSTEM TELEMETRY REPORT",
            f"uptime: {data['uptime_seconds']}s",
            f"total tool calls: {data['total_tool_calls']}",
            f"quota fallbacks activated: {data['fallbacks_activated']}",
            "",
            "tool calls by name:",
        ]
        for name, count in sorted(data["tool_calls"].items()):
            lines.append(f"  {name}: {count}")
        lines.append("")
        lines.append("request latency (ms) mean/p50/p95/p99:")
        for operation, metrics in sorted(data["latency_ms"].items()):
            lines.append(
                f"  {operation}: {metrics['mean_ms']}/{metrics['p50_ms']}/"
                f"{metrics['p95_ms']}/{metrics['p99_ms']} "
                f"(count={metrics['count']})"
            )
        return "\n".join(lines)
