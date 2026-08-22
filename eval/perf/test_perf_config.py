"""perf_config 单元测试。"""
from __future__ import annotations

import os
import tempfile
import unittest

from ..perf.perf_config import PerfConfig, build_config


class PerfConfigTest(unittest.TestCase):

    def test_default_stages(self):
        cfg = PerfConfig()
        self.assertIsInstance(cfg.concurrency_stages, list)
        self.assertTrue(all(len(s) == 2 for s in cfg.concurrency_stages))
        self.assertGreaterEqual(cfg.poll_interval, 0)
        self.assertGreater(cfg.query_timeout, 0)

    def test_build_config_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = build_config(
                query_api_base="http://localhost:9999",
                output_root=d,
                poll_interval=0.1,
                concurrency_stages=[(3, 5)],
            )
            self.assertEqual(cfg.query_api_base, "http://localhost:9999")
            self.assertEqual(cfg.query_url, "http://localhost:9999/query")
            self.assertEqual(cfg.status_url_tpl.format(task_id="abc"),
                             "http://localhost:9999/status/abc")
            self.assertEqual(cfg.concurrency_stages, [(3, 5)])
            self.assertIn("perf_report.json", cfg.perf_report_path)

    def test_output_root_created(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "sub", "data")
            cfg = build_config(output_root=out)
            self.assertTrue(os.path.isdir(out))

    def test_quality_report_default(self):
        cfg = PerfConfig()
        # 默认关联到 eva 的 report.json
        self.assertTrue(cfg.quality_report_path.endswith("report.json"))

    def test_properties(self):
        cfg = build_config(query_api_base="http://127.0.0.1:8080")
        self.assertEqual(cfg.query_url, "http://127.0.0.1:8080/query")
        self.assertEqual(cfg.status_url_tpl.format(task_id="t1"),
                         "http://127.0.0.1:8080/status/t1")


if __name__ == "__main__":
    unittest.main()
