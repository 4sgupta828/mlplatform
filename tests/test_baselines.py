import unittest

from router.baselines import always_cheapest, always_fastest, cheapest_fit
from router.models import scenario_from_dict


def _flash():
    import json
    import os

    path = os.path.join(os.path.dirname(__file__), "..", "scenarios", "flash-sale.json")
    with open(path, encoding="utf-8") as fh:
        return scenario_from_dict(json.load(fh))


class TestBaselines(unittest.TestCase):
    def test_cheapest_ignores_sla_and_can_miss(self):
        scn = scenario_from_dict(
            {
                "name": "t",
                "config": {},
                "requests": [{"id": "r1", "model_id": "m", "priority": "high", "sla_ms": 40}],
                "instances": [
                    {"id": "gpu", "kind": "gpu", "models": ["m"], "hourly_cost": 3.60,
                     "base_latency_ms": {"m": 20}, "concurrency": 2, "load": 0, "healthy": True},
                    {"id": "cpu", "kind": "cpu", "models": ["m"], "hourly_cost": 0.40,
                     "base_latency_ms": {"m": 100}, "concurrency": 4, "load": 0, "healthy": True},
                ],
            }
        )
        d = always_cheapest(scn).decisions[0]
        self.assertEqual(d.instance_id, "cpu")       # cheapest hourly
        self.assertEqual(d.status, "missed_sla")     # but misses the 40ms SLA

    def test_fastest_picks_lowest_latency(self):
        scn = scenario_from_dict(
            {
                "name": "t",
                "config": {},
                "requests": [{"id": "r1", "model_id": "m", "priority": "high", "sla_ms": 500}],
                "instances": [
                    {"id": "gpu", "kind": "gpu", "models": ["m"], "hourly_cost": 3.60,
                     "base_latency_ms": {"m": 20}, "concurrency": 2, "load": 0, "healthy": True},
                    {"id": "cpu", "kind": "cpu", "models": ["m"], "hourly_cost": 0.40,
                     "base_latency_ms": {"m": 100}, "concurrency": 4, "load": 0, "healthy": True},
                ],
            }
        )
        self.assertEqual(always_fastest(scn).decisions[0].instance_id, "gpu")

    def test_cheapest_fit_spills_past_sla_missers(self):
        # cpu is cheapest and has capacity, but misses the tight SLA -> cheapest-fit
        # should skip it and use the GPU that meets the SLA.
        scn = scenario_from_dict(
            {
                "name": "t",
                "config": {},
                "requests": [{"id": "r1", "model_id": "m", "priority": "high", "sla_ms": 40}],
                "instances": [
                    {"id": "gpu", "kind": "gpu", "models": ["m"], "hourly_cost": 3.60,
                     "base_latency_ms": {"m": 20}, "concurrency": 2, "load": 0, "healthy": True},
                    {"id": "cpu", "kind": "cpu", "models": ["m"], "hourly_cost": 0.40,
                     "base_latency_ms": {"m": 100}, "concurrency": 4, "load": 0, "healthy": True},
                ],
            }
        )
        cheap = always_cheapest(scn).decisions[0]
        fit = cheapest_fit(scn).decisions[0]
        self.assertEqual((cheap.instance_id, cheap.status), ("cpu", "missed_sla"))
        self.assertEqual((fit.instance_id, fit.status), ("gpu", "served"))

    def test_cheapest_fit_beats_naive_cheapest_drop_rate(self):
        scn = _flash()

        def drop_rate(res):
            n = len(res.decisions)
            dropped = sum(1 for d in res.decisions if d.status in ("missed_sla", "unassigned"))
            return dropped / n

        self.assertLess(drop_rate(cheapest_fit(scn)), drop_rate(always_cheapest(scn)))

    def test_flash_sale_baselines_run(self):
        scn = _flash()
        self.assertEqual(len(always_cheapest(scn).decisions), len(scn.requests))
        self.assertEqual(len(cheapest_fit(scn).decisions), len(scn.requests))
        self.assertEqual(len(always_fastest(scn).decisions), len(scn.requests))


if __name__ == "__main__":
    unittest.main()
