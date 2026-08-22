"""perf_metrics 与 report 模块单元测试。"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from ..perf.load_gen import StageResult
from ..perf.latency import TaskResult
from ..perf.perf_metrics import merge_with_quality, stage_metrics, summarize_stages
from ..perf.report import build_report, write_report


def _mk_stage(concurrency, ok_n, fail_n, latency=0.1):
    res = [TaskResult(task_id=f"ok{i}", status="ok", latency=latency) for i in range(ok_n)]
    res += [TaskResult(task_id=f"f{i}", status="failed", error="e") for i in range(fail_n)]
    return StageResult(stage_index=0, concurrency=concurrency,
                       duration_secs=1.0, actual_duration=1.0, results=res)


class PerfMetricsTest(unittest.TestCase):

    def test_stage_metrics(self):
        sr = _mk_stage(concurrency=2, ok_n=8, fail_n=2)
        m = stage_metrics(sr)
        self.assertEqual(m["concurrency"], 2)
        self.assertEqual(m["total"], 10)
        self.assertEqual(m["perf"]["success_count"], 8)
        self.assertEqual(m["perf"]["fail_count"], 2)

    def test_summarize_stages(self):
        s1 = _mk_stage(1, ok_n=5, fail_n=0)
        s2 = _mk_stage(2, ok_n=5, fail_n=5)
        summ = summarize_stages([s1, s2])
        self.assertEqual(summ["meta"]["stages"], 2)
        self.assertEqual(summ["meta"]["total_requests"], 15)
        self.assertEqual(summ["meta"]["total_success"], 10)
        self.assertEqual(summ["meta"]["total_failed"], 5)
        self.assertEqual(len(summ["stages"]), 2)

    def test_merge_with_quality(self):
        q = {
            "answer_quality": {"rouge_l": 0.7, "bleu": 0.4, "semantic_sim": 0.8},
            "retrieval": {"retrieval_hit_rate": 0.9, "item_name_hit_rate": 0.85},
        }
        merged = merge_with_quality({"meta": {}}, q)
        self.assertEqual(merged["quality"]["rouge_l"], 0.7)
        self.assertEqual(merged["quality"]["retrieval_hit_rate"], 0.9)

    def test_merge_without_quality(self):
        merged = merge_with_quality({"meta": {}}, None)
        self.assertEqual(merged["quality"], {})


class ReportTest(unittest.TestCase):

    def test_build_report(self):
        rep = build_report(
            {"meta": {"stages": 1}, "overall": {"p99": 1.0}, "stages": []},
            baseline_result={"verdict": "PASS"},
            config_info={"concurrency": 1},
        )
        self.assertEqual(rep["baseline"]["verdict"], "PASS")
        self.assertEqual(rep["config"]["concurrency"], 1)
        self.assertIn("timestamp", rep["meta"])

    def test_write_report(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub", "report.json")
            written = write_report({"overall": {"p50": 0.5}}, p)
            self.assertEqual(written, p)
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["overall"]["p50"], 0.5)

    def test_write_report_none_path(self):
        self.assertEqual(write_report({"a": 1}), "")


if __name__ == "__main__":
    unittest.main()
