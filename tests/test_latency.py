import unittest

from router.latency import per_request_cost, predicted_latency


class TestLatency(unittest.TestCase):
    def test_zero_load_is_base(self):
        # n'=0 -> utilization 0 -> latency == base.
        self.assertEqual(predicted_latency(20.0, 0, 4, 1.0), 20.0)

    def test_full_load_doubles_at_factor_one(self):
        # n'=C, queue_factor 1.0 -> base * 2.
        self.assertEqual(predicted_latency(20.0, 4, 4, 1.0), 40.0)

    def test_monotonic_in_load(self):
        prev = -1.0
        for n in range(0, 5):
            val = predicted_latency(50.0, n, 4, 1.0)
            self.assertGreater(val, prev)
            prev = val

    def test_queue_factor_scales_penalty(self):
        self.assertEqual(predicted_latency(20.0, 2, 4, 0.0), 20.0)  # no penalty
        self.assertEqual(predicted_latency(20.0, 2, 4, 2.0), 20.0 * (1 + 2.0 * 0.5))

    def test_cost_formula(self):
        # 3600 ms of occupancy = 1 second = 1/3600 hour.
        self.assertAlmostEqual(per_request_cost(3600.0, 3.60), 3.60 / 1000.0)

    def test_cheaper_when_faster_or_cheaper(self):
        fast_pricey = per_request_cost(30.0, 3.60)
        slow_cheap = per_request_cost(125.0, 0.40)
        # In this regime the slow cheap machine is cheaper per request.
        self.assertLess(slow_cheap, fast_pricey)

    def test_invalid_concurrency(self):
        with self.assertRaises(ValueError):
            predicted_latency(20.0, 1, 0, 1.0)


if __name__ == "__main__":
    unittest.main()
