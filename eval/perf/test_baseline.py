"""baseline 性能基线判定单元测试。"""
from __future__ import annotations

import unittest

from ..perf.baseline import (BaselineConfig, BaselineThreshold,
                             evaluate_overall, relative_gain)


def _overall(**kwargs) -> dict:
    defaults = {"p99": 3.0, "error_rate": 0.01, "apde": 0.3,
                "throughput_req_s": 5.0, "avg": 1.0, "p50": 0.8, "p95": 2.0}
    defaults.update(kwargs)
    return defaults


class BaselineTest(unittest.TestCase):

    def test_all_pass(self):
        res = evaluate_overall(_overall())
        self.assertEqual(res["verdict"], "PASS")
        self.assertEqual(res["peak"]["p99"]["verdict"], "PASS")
        self.assertEqual(res["stability"]["error_rate"]["verdict"], "PASS")
        self.assertEqual(res["capacity"]["throughput_req_s"]["verdict"], "PASS")

    def test_peak_fail(self):
        res = evaluate_overall(_overall(p99=20.0))  # 远超 5s*1.5=7.5
        self.assertEqual(res["verdict"], "FAIL")
        self.assertEqual(res["peak"]["p99"]["verdict"], "FAIL")

    def test_peak_warn(self):
        res = evaluate_overall(_overall(p99=6.0))  # 5s<6s<7.5s
        self.assertEqual(res["verdict"], "WARN")
        self.assertEqual(res["peak"]["p99"]["verdict"], "WARN")

    def test_capacity_fail(self):
        res = evaluate_overall(_overall(throughput_req_s=0.5))  # 低于下限1.0
        self.assertEqual(res["verdict"], "FAIL")
        self.assertEqual(res["capacity"]["throughput_req_s"]["verdict"], "FAIL")

    def test_stability_error_rate_fail(self):
        res = evaluate_overall(_overall(error_rate=0.5))
        self.assertEqual(res["verdict"], "FAIL")

    def test_missing_value_na(self):
        res = evaluate_overall({})
        # 全部无值 -> N/A，不触发 FAIL/WARN
        self.assertEqual(res["verdict"], "PASS")
        self.assertEqual(res["peak"]["p99"]["verdict"], "N/A")

    def test_custom_baseline(self):
        cfg = BaselineConfig(
            capacity=[BaselineThreshold(key="throughput_req_s", min_value=10.0)],
        )
        res = evaluate_overall(_overall(throughput_req_s=5.0), baseline=cfg)
        self.assertEqual(res["verdict"], "FAIL")


class RelativeGainTest(unittest.TestCase):

    def test_no_previous(self):
        self.assertEqual(relative_gain(_overall(), None), {})

    def test_improvement_negative_delta(self):
        cur = _overall(p99=3.0)
        prev = _overall(p99=4.0)  # 历史更差，本次改善
        g = relative_gain(cur, prev)
        self.assertLess(g["p99"]["delta_pct"], 0)

    def test_regression_positive_delta(self):
        cur = _overall(p99=6.0)
        prev = _overall(p99=4.0)  # 本次劣化
        g = relative_gain(cur, prev)
        self.assertGreater(g["p99"]["delta_pct"], 0)

    def test_skip_zero_previous(self):
        cur = _overall()
        prev = _overall(p99=0.0)
        g = relative_gain(cur, prev)
        self.assertNotIn("p99", g)


if __name__ == "__main__":
    unittest.main()
