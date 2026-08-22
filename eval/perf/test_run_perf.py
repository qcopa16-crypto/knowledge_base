"""run_perf 压测入口单元测试（注入 mock generator，避免真实网络）。"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from ..perf.load_gen import LoadGenerator, StageResult
from ..perf.latency import QueryRunner, TaskResult
from ..perf.perf_config import build_config
from ..perf.run_perf import main, _load_queries


def _ok_result(latency: float = 0.1) -> TaskResult:
    return TaskResult(task_id="t", status="ok", latency=latency)


def _mk_generator() -> LoadGenerator:
    return LoadGenerator(work_fn=lambda q: _ok_result(), poll_duration=0.05)


class _FakeGen:
    """记录调用，返回模拟 stage。"""
    def __init__(self):
        self.calls = []

    def run_fixed(self, query, concurrency, duration_secs, warmup_secs=0.0):
        self.calls.append(("fixed", concurrency))
        res = [_ok_result() for _ in range(3)]
        return StageResult(0, concurrency, duration_secs, duration_secs, res)

    def run_duration(self, query, qps, duration_secs, warmup_secs=0.0):
        self.calls.append(("duration", qps))
        res = [_ok_result() for _ in range(2)]
        return StageResult(0, 1, duration_secs, duration_secs, res)

    def run_staged(self, query, stages, warmup_secs=0.0, stage_cooldown=0.0):
        self.calls.append(("staged", len(stages)))
        outs = []
        for i, (c, d) in enumerate(stages):
            outs.append(StageResult(i, c, d, d, [_ok_result() for _ in range(c)]))
        return outs


class RunPerfTest(unittest.TestCase):

    def _cfg(self, d):
        return build_config(query_api_base="http://localhost:1", output_root=d,
                            concurrency_stages=[(1, 0.2), (2, 0.2)],
                            warmup_secs=0, stage_cooldown=0, poll_interval=0.01)

    def test_main_staged(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(d)
            gen = _FakeGen()
            rep = main(mode="staged", queries=["q1"], cfg=cfg, generator=gen,
                       report_path=os.path.join(d, "p.json"))
            self.assertEqual(gen.calls[0][0], "staged")
            self.assertEqual(rep["config"]["mode"], "staged")
            self.assertEqual(len(rep["stages"]), 2)
            self.assertIn("overall", rep)
            self.assertIn("baseline", rep)

    def test_main_fixed(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(d)
            gen = _FakeGen()
            rep = main(mode="fixed", queries=["q1"], cfg=cfg, generator=gen)
            self.assertEqual(gen.calls[0], ("fixed", 1))

    def test_main_duration(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(d)
            cfg.target_qps = 5.0
            gen = _FakeGen()
            rep = main(mode="duration", queries=["q1"], cfg=cfg, generator=gen)
            self.assertEqual(gen.calls[0][0], "duration")

    def test_main_report_written(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(d)
            gen = _FakeGen()
            p = os.path.join(d, "r.json")
            main(mode="staged", queries=["q1"], cfg=cfg, generator=gen, report_path=p)
            self.assertTrue(os.path.exists(p))

    def test_main_no_queries(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(d)
            gen = _FakeGen()
            with self.assertRaises(ValueError):
                main(mode="staged", queries=[], cfg=cfg, generator=gen)

    def test_load_queries_explicit(self):
        self.assertEqual(_load_queries("hello"), ["hello"])

    def test_load_queries_default(self):
        self.assertEqual(_load_queries(None, dataset_path=None), ["如何调节转印温度？"])


if __name__ == "__main__":
    unittest.main()
