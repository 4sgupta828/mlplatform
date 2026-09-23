import json
import os
import unittest

from router.baselines import always_cheapest, always_fastest, cheapest_fit
from router.models import scenario_from_dict
from router.report import build_report, render_table
from router.router import route


def _load(name):
    path = os.path.join(os.path.dirname(__file__), "..", "scenarios", name)
    with open(path, encoding="utf-8") as fh:
        return scenario_from_dict(json.load(fh))


def _report_for(name):
    scn = _load(name)
    r = route(scn)
    return scn, build_report(scn, r, [always_cheapest(scn), cheapest_fit(scn), always_fastest(scn)])


class TestReport(unittest.TestCase):
    def test_totals_add_up(self):
        scn, report = _report_for("flash-sale.json")
        total_requests = len(scn.requests)
        for s in report.summaries:
            self.assertEqual(s.served + s.missed_sla + s.unassigned, total_requests)

    def test_cost_per_success_math(self):
        _, report = _report_for("flash-sale.json")
        for m in report.per_model:
            if m.served:
                self.assertAlmostEqual(m.cost_per_success, m.total_cost / m.served)
            else:
                self.assertIsNone(m.cost_per_success)

    def test_json_schema_stable(self):
        _, report = _report_for("simple.json")
        d = report.to_dict()
        self.assertEqual(
            set(d.keys()),
            {"scenario", "drop_penalty_usd", "per_model", "per_priority",
             "summaries", "defaulted_bases", "alerts"},
        )
        # Round-trips through JSON.
        json.loads(json.dumps(d))

    def test_defaulted_bases_surfaced(self):
        _, report = _report_for("simple.json")
        self.assertTrue(report.defaulted_bases)
        self.assertIn("estimated defaults", render_table(report))

    def test_acceptance_router_beats_baselines(self):
        # Spec §8 acceptance on flash-sale.
        _, report = _report_for("flash-sale.json")
        by = {s.policy: s for s in report.summaries}
        router, cheapest, fastest = by["cost-aware"], by["always-cheapest"], by["always-fastest"]

        # SLA-hit rate at least as good as always-cheapest.
        self.assertGreaterEqual(router.sla_hit_rate, cheapest.sla_hit_rate)
        # Cost no worse than always-fastest.
        self.assertLessEqual(router.total_cost, fastest.total_cost)
        # Infeasible demand surfaced rather than hidden.
        self.assertGreater(router.unassigned, 0)
        # Router never assigns an SLA-missing request.
        self.assertEqual(router.missed_sla, 0)

    def test_drop_rate_captured_per_policy(self):
        _, report = _report_for("flash-sale.json")
        by = {s.policy: s for s in report.summaries}
        for s in report.summaries:
            # dropped = missed_sla + unassigned; drop_rate = dropped / total.
            self.assertEqual(s.dropped, s.missed_sla + s.unassigned)
            self.assertAlmostEqual(s.drop_rate, s.dropped / s.total_requests)
            # drop_rate is the complement of sla_hit_rate.
            self.assertAlmostEqual(s.drop_rate, 1.0 - s.sla_hit_rate)
        # always-cheapest drops more than the cost-aware router on this scenario.
        self.assertGreater(by["always-cheapest"].drop_rate, by["cost-aware"].drop_rate)

    def test_effective_cost_prices_in_drops(self):
        # flash-sale sets drop_penalty_usd; effective = (total_cost + penalty*dropped)/total.
        scn, report = _report_for("flash-sale.json")
        penalty = scn.config.drop_penalty_usd
        self.assertGreater(penalty, 0.0)
        for s in report.summaries:
            expected = (s.total_cost + penalty * s.dropped) / s.total_requests
            self.assertAlmostEqual(s.effective_cost_per_request, expected)
        by = {s.policy: s for s in report.summaries}
        # Naive cheapest (40% drops) is worst on the combined metric.
        self.assertGreater(
            by["always-cheapest"].effective_cost_per_request,
            by["cost-aware"].effective_cost_per_request,
        )

    def test_cost_aware_beats_cheapest_fit_on_tradeoff(self):
        # Same drops, but cost-aware routes by occupancy cost and wins on cost.
        _, report = _report_for("cost-tradeoff.json")
        by = {s.policy: s for s in report.summaries}
        self.assertEqual(by["cost-aware"].dropped, by["cheapest-fit"].dropped)
        self.assertLess(by["cost-aware"].total_cost, by["cheapest-fit"].total_cost)
        self.assertLess(
            by["cost-aware"].cost_per_success, by["cheapest-fit"].cost_per_success
        )

    def test_starvation_visible_per_priority(self):
        _, report = _report_for("flash-sale.json")
        low = next(p for p in report.per_priority if p.priority == "low")
        self.assertGreater(low.unassigned, 0)


if __name__ == "__main__":
    unittest.main()
