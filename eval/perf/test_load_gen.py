"""load_gen 并发压测引擎单元测试（注入 mock work_fn）。"""
from __future__ import annotations

import time
import unittest

from ..perf.load_gen import LoadGenerator, StageResult
from ..perf.latency import TaskResult


def _ok_result(latency: float = 0.01) -> TaskResult:
    return TaskResult(task_id="t", status="ok", latency=latency)


def _fail_result() -> TaskResult:
    return TaskResult(task_id="t", status="failed", error="boom")


class LoadGeneratorTest(unittest.TestCase):

    def test_run_fixed_collects_results(self):
        # 快速 mock：每次立即返回 ok
        def work(query):
            return _ok_result()

        gen = LoadGenerator(work_fn=work, poll_duration=0.1)
        sr = gen.run_fixed("q", concurrency=3, duration_secs=0.3)
        self.assertIsInstance(sr, StageResult)
        self.assertEqual(sr.concurrency, 3)
        self.assertGreaterEqual(len(sr.results), 1)
        self.assertEqual(len(sr.ok_results()), len(sr.results))
        self.assertEqual(len(sr.failed_results()), 0)

    def test_run_fixed_invalid_concurrency(self):
        gen = LoadGenerator(work_fn=lambda q: _ok_result())
        with self.assertRaises(ValueError):
            gen.run_fixed("q", concurrency=0, duration_secs=0.1)

    def test_run_staged_sequence(self):
        def work(query):
            return _ok_result()

        gen = LoadGenerator(work_fn=work, poll_duration=0.05)
        stages = [(1, 0.2), (2, 0.2)]
        outs = gen.run_staged("q", stages, stage_cooldown=0.0)
        self.assertEqual(len(outs), 2)
        self.assertEqual([s.concurrency for s in outs], [1, 2])

    def test_run_duration_estimation(self):
        def work(query):
            return _ok_result()

        gen = LoadGenerator(work_fn=work, poll_duration=0.2)
        sr = gen.run_duration("q", target_qps=5, duration_secs=0.2)
        self.assertEqual(sr.concurrency, 1)  # int(5*0.2)=1

    def test_run_duration_invalid_qps(self):
        gen = LoadGenerator(work_fn=lambda q: _ok_result())
        with self.assertRaises(ValueError):
            gen.run_duration("q", target_qps=0, duration_secs=0.2)

    def test_failed_results_separated(self):
        def work(query):
            return _fail_result()

        gen = LoadGenerator(work_fn=work, poll_duration=0.05)
        sr = gen.run_fixed("q", concurrency=1, duration_secs=0.2)
        self.assertGreaterEqual(len(sr.failed_results()), 1)
        self.assertEqual(len(sr.ok_results()), 0)

    def test_mixed_ok_and_fail(self):
        calls = {"n": 0}

        def work(query):
            calls["n"] += 1
            return _ok_result() if calls["n"] % 2 == 0 else _fail_result()

        gen = LoadGenerator(work_fn=work, poll_duration=0.05)
        sr = gen.run_fixed("q", concurrency=1, duration_secs=0.3)
        total = len(sr.results)
        self.assertEqual(len(sr.ok_results()) + len(sr.failed_results()), total)


if __name__ == "__main__":
    unittest.main()
