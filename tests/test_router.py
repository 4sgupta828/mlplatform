import unittest

from router.models import ScenarioError, scenario_from_dict
from router.router import route


def _scn(requests, instances, config=None):
    return scenario_from_dict(
        {"name": "t", "config": config or {}, "requests": requests, "instances": instances}
    )


CPU = lambda id, hourly, base, conc=4, load=0, models=("m",): {  # noqa: E731
    "id": id, "kind": "cpu", "models": list(models), "hourly_cost": hourly,
    "base_latency_ms": base, "concurrency": conc, "load": load, "healthy": True,
}
GPU = lambda id, hourly, base, conc=2, load=0, models=("m",): {  # noqa: E731
    "id": id, "kind": "gpu", "models": list(models), "hourly_cost": hourly,
    "base_latency_ms": base, "concurrency": conc, "load": load, "healthy": True,
}
REQ = lambda id, prio, sla, model="m": {  # noqa: E731
    "id": id, "model_id": model, "priority": prio, "sla_ms": sla,
}


class TestRouting(unittest.TestCase):
    def test_chooses_cheaper_qualifying_instance(self):
        # Both meet a loose SLA; the cheap CPU should win on cost.
        scn = _scn(
            [REQ("r1", "high", 500)],
            [GPU("gpu", 3.60, {"m": 20}), CPU("cpu", 0.40, {"m": 100})],
        )
        d = route(scn).decisions[0]
        self.assertEqual(d.status, "served")
        self.assertEqual(d.instance_id, "cpu")

    def test_drops_sla_missers_and_uses_gpu(self):
        # Tight SLA only the GPU can meet -> GPU chosen despite higher price.
        scn = _scn(
            [REQ("r1", "high", 40)],
            [GPU("gpu", 3.60, {"m": 20}), CPU("cpu", 0.40, {"m": 100})],
        )
        d = route(scn).decisions[0]
        self.assertEqual(d.status, "served")
        self.assertEqual(d.instance_id, "gpu")

    def test_unassigned_when_nothing_qualifies(self):
        scn = _scn(
            [REQ("r1", "high", 5)],  # no machine can hit 5ms
            [CPU("cpu", 0.40, {"m": 100})],
        )
        d = route(scn).decisions[0]
        self.assertEqual(d.status, "unassigned")
        self.assertEqual(d.reason, "sla-miss")

    def test_unassigned_no_eligible_instance(self):
        scn = _scn([REQ("r1", "high", 500, model="other")], [CPU("cpu", 0.40, {"m": 100})])
        self.assertEqual(route(scn).decisions[0].reason, "no-eligible-instance")

    def test_unassigned_no_capacity(self):
        scn = _scn(
            [REQ("r1", "high", 500)],
            [CPU("cpu", 0.40, {"m": 100}, conc=1, load=1)],  # already full
        )
        self.assertEqual(route(scn).decisions[0].reason, "no-capacity")

    def test_priority_ordering_high_before_low(self):
        # One GPU slot; high-priority request must take it, low is starved.
        scn = _scn(
            [REQ("low1", "low", 40), REQ("high1", "high", 40)],
            [GPU("gpu", 3.60, {"m": 20}, conc=1)],
        )
        by_req = {d.request_id: d for d in route(scn).decisions}
        self.assertEqual(by_req["high1"].status, "served")
        self.assertEqual(by_req["low1"].status, "unassigned")

    def test_watch_degrades_after_repeated_misses(self):
        # A CPU repeatedly can't meet a tight search SLA (matched but always missing)
        # -> degraded and an alert is emitted.
        reqs = [REQ(f"s{i}", "high", 40) for i in range(4)]
        scn = _scn(
            reqs,
            [
                GPU("gpu", 3.60, {"m": 20}, conc=1),   # only 1 fast slot
                CPU("cpu", 0.40, {"m": 100}, conc=4),  # matched, always misses 40ms
            ],
            config={"watch_miss_threshold": 0.5, "watch_window": 10},
        )
        result = route(scn)
        self.assertTrue(any("cpu" in a and "degraded" in a for a in result.alerts))

    def test_load_increments_change_later_decisions(self):
        # Two requests, one GPU of concurrency 2; second sees higher predicted latency.
        scn = _scn(
            [REQ("r1", "high", 500), REQ("r2", "high", 500)],
            [GPU("gpu", 3.60, {"m": 20}, conc=2)],
        )
        d1, d2 = route(scn).decisions
        self.assertLess(d1.predicted_ms, d2.predicted_ms)


class TestValidation(unittest.TestCase):
    def test_missing_base_is_defaulted_not_rejected(self):
        scn = _scn(
            [REQ("r1", "high", 500)],
            [CPU("cpu", 0.40, {})],  # no measured base
            config={"default_base_latency_ms": {"cpu": 80}},
        )
        self.assertEqual(scn.base_ms("cpu", "m"), 80.0)
        self.assertEqual(len(scn.defaulted_bases), 1)
        self.assertEqual(scn.defaulted_bases[0].source, "kind-default")

    def test_builtin_default_when_no_config(self):
        scn = _scn([REQ("r1", "high", 500)], [CPU("cpu", 0.40, {})])
        self.assertEqual(scn.base_ms("cpu", "m"), 80.0)  # builtin cpu default
        self.assertEqual(scn.defaulted_bases[0].source, "builtin-default")

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ScenarioError):
            _scn(
                [REQ("r1", "high", 500)],
                [CPU("dup", 0.40, {"m": 50}), CPU("dup", 0.40, {"m": 50})],
            )

    def test_bad_numbers_rejected(self):
        with self.assertRaises(ScenarioError):
            _scn([REQ("r1", "high", 0)], [CPU("cpu", 0.40, {"m": 50})])  # sla 0
        with self.assertRaises(ScenarioError):
            _scn([REQ("r1", "high", 100)], [CPU("cpu", -1, {"m": 50})])  # hourly < 0


if __name__ == "__main__":
    unittest.main()
