"""Cost-aware routing engine (spec §4): Match -> Check time -> Choose cost -> Watch."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from .latency import per_request_cost, predicted_latency
from .models import Instance, Request, Scenario

log = logging.getLogger("router.engine")

# Minimum observations before an instance can be judged "degraded" by Watch,
# so a single unlucky sample cannot trip it (spec §4.4).
_MIN_WATCH_OBSERVATIONS = 3


@dataclass
class Decision:
    request_id: str
    model_id: str
    priority: str
    status: str  # "served" | "missed_sla" | "unassigned"
    instance_id: Optional[str] = None
    predicted_ms: Optional[float] = None
    cost: Optional[float] = None
    reason: Optional[str] = None  # populated when unassigned


@dataclass
class RoutingResult:
    policy: str
    decisions: list[Decision]
    alerts: list[str] = field(default_factory=list)


def request_order(requests: list[Request]) -> list[Request]:
    """Deterministic processing order: priority, then tightest SLA, then id."""
    return sorted(requests, key=lambda r: (r.priority.rank, r.sla_ms, r.id))


def _matched_instances(scenario: Scenario, req: Request, loads: dict[str, int]) -> list[Instance]:
    """Healthy instances serving the model with free capacity (spec §4.1)."""
    out = []
    for inst in scenario.instances:
        if not inst.healthy:
            continue
        if req.model_id not in inst.models:
            continue
        if loads[inst.id] + 1 > inst.concurrency:
            continue
        out.append(inst)
    return out


def _unassigned_reason(scenario: Scenario, req: Request, loads: dict[str, int]) -> str:
    eligible = [i for i in scenario.instances if i.healthy and req.model_id in i.models]
    if not eligible:
        return "no-eligible-instance"
    with_capacity = [i for i in eligible if loads[i.id] + 1 <= i.concurrency]
    if not with_capacity:
        return "no-capacity"
    return "sla-miss"


class CostAwareRouter:
    """Routes a scenario's requests, respecting SLAs and minimizing cost."""

    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.qf = scenario.config.queue_factor
        # Watch state (spec §4.4).
        self._windows: dict[str, deque] = {
            i.id: deque(maxlen=scenario.config.watch_window) for i in scenario.instances
        }
        self._degraded: set[str] = set()

    def route(self) -> RoutingResult:
        loads = {i.id: i.load for i in self.scenario.instances}
        by_id = self.scenario.instances_by_id
        alerts: list[str] = []
        decisions: list[Decision] = []

        for req in request_order(self.scenario.requests):
            matched = _matched_instances(self.scenario, req, loads)

            # Check time: predicted latency per candidate; qualify those within SLA.
            predicted: dict[str, float] = {}
            qualifying: list[Instance] = []
            for inst in matched:
                p = predicted_latency(
                    self.scenario.base_ms(inst.id, req.model_id),
                    loads[inst.id] + 1,
                    inst.concurrency,
                    self.qf,
                )
                predicted[inst.id] = p
                if p <= req.sla_ms:
                    qualifying.append(inst)

            # Prefer non-degraded pools; fall back to degraded only if needed.
            pool = [i for i in qualifying if i.id not in self._degraded] or qualifying

            if not pool:
                reason = _unassigned_reason(self.scenario, req, loads)
                decisions.append(
                    Decision(req.id, req.model_id, req.priority.value, "unassigned", reason=reason)
                )
                log.info("request %s unassigned (%s)", req.id, reason)
            else:
                # Choose cost: lowest per-request cost, tie-break predicted then id.
                chosen = min(
                    pool,
                    key=lambda i: (per_request_cost(predicted[i.id], i.hourly_cost), predicted[i.id], i.id),
                )
                cost = per_request_cost(predicted[chosen.id], chosen.hourly_cost)
                loads[chosen.id] += 1
                decisions.append(
                    Decision(
                        req.id, req.model_id, req.priority.value, "served",
                        instance_id=chosen.id, predicted_ms=predicted[chosen.id], cost=cost,
                    )
                )
                log.debug(
                    "request %s -> %s predicted=%.1fms cost=$%.6f",
                    req.id, chosen.id, predicted[chosen.id], cost,
                )

            # Watch: record whether each matched instance would have missed the SLA,
            # then re-evaluate degradation for those instances.
            for inst in matched:
                self._windows[inst.id].append(predicted[inst.id] > req.sla_ms)
            self._update_degraded(matched, alerts, by_id)

        return RoutingResult(policy="cost-aware", decisions=decisions, alerts=alerts)

    def _update_degraded(self, matched: list[Instance], alerts: list[str], by_id) -> None:
        threshold = self.scenario.config.watch_miss_threshold
        for inst in matched:
            window = self._windows[inst.id]
            if len(window) < _MIN_WATCH_OBSERVATIONS:
                continue
            miss_rate = sum(window) / len(window)
            if miss_rate > threshold and inst.id not in self._degraded:
                self._degraded.add(inst.id)
                msg = (
                    f"instance {inst.id} degraded: {miss_rate:.0%} of last {len(window)} "
                    f"candidate requests would miss SLA; shifting new traffic away"
                )
                alerts.append(msg)
                log.warning(msg)
            elif miss_rate <= threshold and inst.id in self._degraded:
                self._degraded.discard(inst.id)
                log.info("instance %s recovered (miss rate %.0f%%)", inst.id, miss_rate * 100)


def route(scenario: Scenario) -> RoutingResult:
    return CostAwareRouter(scenario).route()
