"""Cost report: aggregation + table/JSON rendering (spec §6).

Cost accounting: a request that is *assigned* incurs cost whether or not it
meets its SLA (the machine time is spent). ``total_cost`` therefore sums cost
over all assigned requests (served + missed_sla); ``cost_per_success`` divides
that by the number served. For the cost-aware router, missed_sla is always 0, so
the two views coincide; the distinction only affects the baselines.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from .models import Scenario
from .router import Decision, RoutingResult


@dataclass
class ModelStat:
    model_id: str
    requests: int
    served: int
    missed_sla: int
    unassigned: int
    total_cost: float
    cost_per_success: Optional[float]


@dataclass
class PolicySummary:
    policy: str
    total_requests: int
    served: int
    missed_sla: int
    unassigned: int
    dropped: int          # missed_sla + unassigned (requests not successfully served)
    drop_rate: float      # dropped / total_requests
    total_cost: float
    sla_hit_rate: float
    cost_per_success: Optional[float]
    # Combined metric: (total_cost + drop_penalty * dropped) / total_requests.
    effective_cost_per_request: float


@dataclass
class PriorityStat:
    priority: str
    served: int
    unassigned: int


@dataclass
class Report:
    scenario_name: str
    per_model: list[ModelStat]
    per_priority: list[PriorityStat]
    summaries: list[PolicySummary]
    defaulted_bases: list[dict]
    alerts: list[str]
    drop_penalty_usd: float = 0.0

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario_name,
            "drop_penalty_usd": self.drop_penalty_usd,
            "per_model": [asdict(m) for m in self.per_model],
            "per_priority": [asdict(p) for p in self.per_priority],
            "summaries": [asdict(s) for s in self.summaries],
            "defaulted_bases": self.defaulted_bases,
            "alerts": self.alerts,
        }


def _assigned(d: Decision) -> bool:
    return d.status in ("served", "missed_sla")


def _cost_per_success(total_cost: float, served: int) -> Optional[float]:
    return (total_cost / served) if served else None


def _per_model(decisions: list[Decision]) -> list[ModelStat]:
    models = sorted({d.model_id for d in decisions})
    stats = []
    for m in models:
        ds = [d for d in decisions if d.model_id == m]
        served = sum(1 for d in ds if d.status == "served")
        missed = sum(1 for d in ds if d.status == "missed_sla")
        unassigned = sum(1 for d in ds if d.status == "unassigned")
        total_cost = sum(d.cost or 0.0 for d in ds if _assigned(d))
        stats.append(
            ModelStat(m, len(ds), served, missed, unassigned, total_cost, _cost_per_success(total_cost, served))
        )
    return stats


def _per_priority(decisions: list[Decision]) -> list[PriorityStat]:
    order = {"high": 0, "medium": 1, "low": 2}
    prios = sorted({d.priority for d in decisions}, key=lambda p: order.get(p, 99))
    out = []
    for p in prios:
        ds = [d for d in decisions if d.priority == p]
        served = sum(1 for d in ds if d.status == "served")
        unassigned = sum(1 for d in ds if d.status == "unassigned")
        out.append(PriorityStat(p, served, unassigned))
    return out


def _summary(result: RoutingResult, drop_penalty_usd: float) -> PolicySummary:
    ds = result.decisions
    total = len(ds)
    served = sum(1 for d in ds if d.status == "served")
    missed = sum(1 for d in ds if d.status == "missed_sla")
    unassigned = sum(1 for d in ds if d.status == "unassigned")
    total_cost = sum(d.cost or 0.0 for d in ds if _assigned(d))
    sla_hit_rate = served / total if total else 0.0
    dropped = missed + unassigned
    drop_rate = dropped / total if total else 0.0
    effective = (total_cost + drop_penalty_usd * dropped) / total if total else 0.0
    return PolicySummary(
        result.policy, total, served, missed, unassigned, dropped, drop_rate,
        total_cost, sla_hit_rate, _cost_per_success(total_cost, served), effective,
    )


def build_report(scenario: Scenario, router_result: RoutingResult, baselines: list[RoutingResult]) -> Report:
    defaulted = [
        {"instance_id": rb.instance_id, "model_id": rb.model_id, "kind": rb.kind,
         "value_ms": rb.value_ms, "source": rb.source}
        for rb in scenario.defaulted_bases
    ]
    return Report(
        scenario_name=scenario.name,
        per_model=_per_model(router_result.decisions),
        per_priority=_per_priority(router_result.decisions),
        summaries=[_summary(r, scenario.config.drop_penalty_usd) for r in [router_result, *baselines]],
        defaulted_bases=defaulted,
        alerts=router_result.alerts,
        drop_penalty_usd=scenario.config.drop_penalty_usd,
    )


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def _money(x: Optional[float]) -> str:
    return "—" if x is None else f"${x:.6f}"


def render_table(report: Report) -> str:
    lines: list[str] = []
    lines.append(f"Cost-aware routing report — scenario: {report.scenario_name}")
    lines.append("")

    # Per model (router).
    lines.append("Per model (cost-aware router)")
    hdr = f"{'model':<22}{'req':>5}{'served':>8}{'missed':>8}{'unassigned':>12}{'total_cost':>14}{'cost/success':>16}"
    lines.append(hdr)
    lines.append("-" * len(hdr))
    for m in report.per_model:
        lines.append(
            f"{m.model_id:<22}{m.requests:>5}{m.served:>8}{m.missed_sla:>8}{m.unassigned:>12}"
            f"{_money(m.total_cost):>14}{_money(m.cost_per_success):>16}"
        )
    lines.append("")

    # Per priority.
    lines.append("Per priority (cost-aware router)")
    phdr = f"{'priority':<10}{'served':>8}{'unassigned':>12}"
    lines.append(phdr)
    lines.append("-" * len(phdr))
    for p in report.per_priority:
        lines.append(f"{p.priority:<10}{p.served:>8}{p.unassigned:>12}")
    lines.append("")

    # Policy comparison.
    lines.append("Policy comparison")
    lines.append(
        f"(dropped = missed_sla + unassigned; eff_cost/req prices each drop at "
        f"${report.drop_penalty_usd:.6f} and is the combined metric — lower is better)"
    )
    shdr = (
        f"{'policy':<16}{'served':>8}{'dropped%':>10}{'sla_hit':>9}"
        f"{'total_cost':>14}{'cost/success':>16}{'eff_cost/req':>16}"
    )
    lines.append(shdr)
    lines.append("-" * len(shdr))
    for s in report.summaries:
        lines.append(
            f"{s.policy:<16}{s.served:>8}{s.drop_rate:>9.0%} {s.sla_hit_rate:>8.0%} "
            f"{_money(s.total_cost):>13}{_money(s.cost_per_success):>16}"
            f"{_money(s.effective_cost_per_request):>16}"
        )
    best = min(report.summaries, key=lambda s: s.effective_cost_per_request)
    lines.append("")
    lines.append(f"Best by effective cost/request: {best.policy} ({_money(best.effective_cost_per_request)})")
    if report.drop_penalty_usd == 0.0:
        lines.append("  (drop_penalty_usd=0 — drops are NOT priced in; set it to rank on drops + cost)")
    lines.append("")

    # Data-quality note.
    if report.defaulted_bases:
        lines.append(
            f"⚠ data quality: {len(report.defaulted_bases)} (instance, model) base times use "
            f"estimated defaults — replace with measurements:"
        )
        for d in report.defaulted_bases:
            lines.append(
                f"    {d['instance_id']} / {d['model_id']}: {d['value_ms']:.1f}ms ({d['source']})"
            )
        lines.append("")

    # Alerts.
    if report.alerts:
        lines.append("Watch alerts")
        for a in report.alerts:
            lines.append(f"    ⚠ {a}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
