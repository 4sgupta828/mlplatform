"""Latency and cost proxies (spec §3).

Both live here so the router logic never depends on the exact formula — a
sharper curve fitted from real latency-at-load traces can replace
``predicted_latency`` without touching the router.
"""

from __future__ import annotations


def predicted_latency(base_ms: float, in_flight_after: int, concurrency: int, queue_factor: float) -> float:
    """Load-aware predicted latency (ms) if a request is admitted.

    Linear penalty: ``base * (1 + queue_factor * n'/C)`` where ``n'`` is the
    in-flight count *after* admitting this request and ``C`` is concurrency.
    """
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")
    utilization = in_flight_after / concurrency
    return base_ms * (1.0 + queue_factor * utilization)


def per_request_cost(predicted_ms: float, hourly_cost: float) -> float:
    """Cost (USD) = occupancy time (hours) * hourly price.

    occupancy_hours = predicted_ms / 1000 / 3600.
    """
    occupancy_hours = predicted_ms / 1000.0 / 3600.0
    return occupancy_hours * hourly_cost
