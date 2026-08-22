"""metrics.perf_stats / apde 等性能指标的单元测试。"""
from __future__ import annotations

import unittest

from .metrics import apde, perf_stats, _percentile


class PerfMetricsTest(unittest.TestCase):

    def test_percentile(self):
        s = sorted([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(_percentile(s, 0.5), 2.0)
        self.assertEqual(_percentile(s, 0.999), 4.0)
        self.assertEqual(_percentile([], 0.5), 0.0)

    def test_perf_stats_basic(self):
        lat = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        st = perf_stats(lat, success_count=10, fail_count=2, duration_secs=5.0)
        self.assertEqual(st["count"], 10)
        self.assertAlmostEqual(st["error_rate"], 2 / 12, places=4)
        self.assertAlmostEqual(st["throughput_req_s"], 2.0, places=3)
        self.assertAlmostEqual(st["avg"], 0.55, places=3)
        self.assertAlmostEqual(st["p50"], 0.5, places=3)
        self.assertAlmostEqual(st["p99"], 1.0, places=3)
        self.assertAlmostEqual(st["max"], 1.0, places=3)
        self.assertEqual(st["success_count"], 10)
        self.assertEqual(st["fail_count"], 2)

    def test_perf_stats_empty(self):
        st = perf_stats([], success_count=0, fail_count=0, duration_secs=0)
        self.assertEqual(st["count"], 0)
        self.assertEqual(st["error_rate"], 0.0)
        self.assertEqual(st["throughput_req_s"], 0.0)

    def test_perf_stats_zero_duration(self):
        st = perf_stats([0.1, 0.2], success_count=2, fail_count=0, duration_secs=0)
        self.assertEqual(st["throughput_req_s"], 0.0)

    def test_perf_stats_all_fail(self):
        st = perf_stats([], success_count=0, fail_count=5, duration_secs=10)
        self.assertEqual(st["error_rate"], 1.0)
        self.assertEqual(st["count"], 0)

    def test_apde_stable(self):
        # 完全均匀的延迟 -> 无抖动
        stable = [i * 0.1 for i in range(1, 21)]
        self.assertAlmostEqual(apde(stable), 0.0, places=4)

    def test_apde_low_entropy(self):
        # 少于 3 个样本返回 0
        self.assertEqual(apde([0.5, 0.6]), 0.0)
        self.assertEqual(apde([]), 0.0)

    def test_apde_has_some_deviation(self):
        # 前半段低延迟，后半段高延迟 -> 存在抖动
        vals = [0.1] * 10 + [1.0] * 10
        d = apde(vals)
        self.assertGreater(d, 0.0)


if __name__ == "__main__":
    unittest.main()
