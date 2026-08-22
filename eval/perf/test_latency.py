"""latency 模块单元测试（mock 网络调用）。"""
from __future__ import annotations

import unittest

from ..perf.latency import QueryRunner, TaskResult, TaskTimeoutError


def _runner(post_responses=None, get_responses=None, poll_interval=0.0, query_timeout=5.0):
    """构造带 mock 网络调用的 QueryRunner。

    :param post_responses: 提交响应列表（依次返回）
    :param get_responses: 轮询响应列表（依次返回，可为 Callable）
    """
    post_vals = list(post_responses or [])
    get_vals = list(get_responses or [])

    def fake_post(url, json, timeout):
        if not post_vals:
            return {"task_id": "t1"}
        v = post_vals.pop(0)
        if isinstance(v, Exception):
            raise v
        return v

    def fake_get(url, timeout):
        if not get_vals:
            return {"status": "completed"}
        v = get_vals.pop(0)
        if callable(v):
            return v(url)
        if isinstance(v, Exception):
            raise v
        return v

    return QueryRunner(
        query_url="http://test/query",
        status_url_tpl="http://test/status/{task_id}",
        poll_interval=poll_interval,
        query_timeout=query_timeout,
        http_post=fake_post,
        http_get=fake_get,
    )


class QueryRunnerTest(unittest.TestCase):

    def test_success_completed(self):
        r = _runner(get_responses=[{"status": "processing"}, {"status": "completed"}])
        result = r.run("hello")
        self.assertEqual(result.status, "ok")
        self.assertGreaterEqual(result.latency, 0)

    def test_task_id_extracted(self):
        # 响应可能嵌套在 data 中
        r = _runner(post_responses=[{"data": {"task_id": "nested_id"}}],
                    get_responses=[{"status": "completed"}])
        result = r.run("hi")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.task_id, "nested_id")

    def test_failed_status(self):
        r = _runner(get_responses=[{"status": "failed", "detail": "boom"}])
        result = r.run("hi")
        self.assertEqual(result.status, "failed")
        self.assertIn("boom", result.error)

    def test_submit_error(self):
        r = _runner(post_responses=[Exception("conn refused")])
        result = r.run("hi")
        self.assertEqual(result.status, "failed")
        self.assertIn("提交失败", result.error)

    def test_missing_task_id(self):
        r = _runner(post_responses=[{"message": "ok"}])
        result = r.run("hi")
        self.assertEqual(result.status, "failed")
        self.assertIn("task_id", result.error)

    def test_timeout(self):
        # 一直 processing，直到超时
        r = _runner(get_responses=[{"status": "processing"}] * 100,
                    query_timeout=0.2, poll_interval=0.1)
        result = r.run("hi")
        self.assertEqual(result.status, "timeout")
        self.assertIn("未完成", result.error)

    def test_to_dict(self):
        tr = TaskResult(task_id="t", status="ok", latency=1.23)
        d = tr.to_dict()
        self.assertEqual(d["task_id"], "t")
        self.assertEqual(d["latency"], 1.23)

    def test_poll_network_error_retries(self):
        # 轮询时抛一次异常，之后成功
        calls = {"n": 0}

        def flaky(url):
            calls["n"] += 1
            if calls["n"] == 1:
                raise Exception("temporary")
            return {"status": "completed"}

        r = _runner(get_responses=[flaky, flaky, flaky], poll_interval=0.0)
        result = r.run("hi")
        self.assertEqual(result.status, "ok")


if __name__ == "__main__":
    unittest.main()
