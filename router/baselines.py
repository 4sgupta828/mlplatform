"""Baseline policies for comparison (spec §5).

Three comparators sit beside the cost-aware router:

* ``always-cheapest`` — pick the lowest **hourly rate** instance that has
  capacity, ignoring the SLA. Spills to the next-cheapest only when the current
  one is *full*. Naive floor: shows what ignoring latency costs (it pays for SLA
  failures).
* ``cheapest-fit`` — improved cheapest: pick the lowest **hourly rate** instance
  that has capacity **and** meets the SLA at current load. Spills up the cost
  ladder past instances that are full *or* would miss the SLA; records the
  request as unassigned only when no instance can meet it. This is the
  "go to the next instance if the cheapest can't do the job" policy.
* ``always-fastest`` — pick the lowest predicted-latency instance with capacity,
  ignoring cost.

All use the same request order and capacity rules as the router, so contention
is comparable.
"""

from __future__ import annotations

from typing import Callable

from .latency import per_request_cost, predicted_latency
from .models import Instance, Request, Scenario
from .router import Decision, RoutingResult, _matched_instances, _unassigned_reason, request_order

# pick(candidates, predicted, req) -> chosen Instance
Picker = Callable[[list[Instance], dict, Request], Instance]


def _run(scenario: Scenario, policy: str, pick: Picker, honor_sla: bool) -> RoutingResult:
    loads = {i.id: i.load for i in scenario.instances}
    qf = scenario.config.queue_factor
    decisions: list[Decision] = []

    for req in request_order(scenario.requests):
        matched = _matched_instances(scenario, req, loads)
        if not matched:
            decisions.append(
                Decision(req.id, req.model_id, req.priority.value, "unassigned",
                         reason=_unassigned_reason(scenario, req, loads))
            )
            continue

        predicted = {
            inst.id: predicted_latency(
                scenario.base_ms(inst.id, req.model_id), loads[inst.id] + 1, inst.concurrency, qf
            )
            for inst in matched
        }

        if honor_sla:
            candidates = [i for i in matched if predicted[i.id] <= req.sla_ms]
            if not candidates:
                # No instance can meet the SLA -> record honestly, don't hide it.
                decisions.append(
                    Decision(req.id, req.model_id, req.priority.value, "unassigned", reason="sla-miss")
                )
                continue
        else:
            candidates = matched

        chosen = pick(candidates, predicted, req)
        cost = per_request_cost(predicted[chosen.id], chosen.hourly_cost)
        loads[chosen.id] += 1
        status = "served" if predicted[chosen.id] <= req.sla_ms else "missed_sla"
        decisions.append(
            Decision(
                req.id, req.model_id, req.priority.value, status,
                instance_id=chosen.id, predicted_ms=predicted[chosen.id], cost=cost,
            )
        )

    return RoutingResult(policy=policy, decisions=decisions)


def _cheapest(candidates, predicted, req):
    return min(candidates, key=lambda i: (i.hourly_cost, i.id))


def _fastest(candidates, predicted, req):
    return min(candidates, key=lambda i: (predicted[i.id], i.id))


def always_cheapest(scenario: Scenario) -> RoutingResult:
    """Lowest hourly-cost instance with capacity, ignoring the SLA (naive floor)."""
    return _run(scenario, "always-cheapest", _cheapest, honor_sla=False)


def cheapest_fit(scenario: Scenario) -> RoutingResult:
    """Lowest hourly-cost instance that has capacity AND meets the SLA (spills up)."""
    return _run(scenario, "cheapest-fit", _cheapest, honor_sla=True)


def always_fastest(scenario: Scenario) -> RoutingResult:
    """Lowest predicted-latency instance with capacity, ignoring cost."""
    return _run(scenario, "always-fastest", _fastest, honor_sla=False)
