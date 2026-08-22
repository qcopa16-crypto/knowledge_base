"""
端到端延迟测量与任务状态轮询。

适配被测 RAG 服务的异步架构：
- POST /query 同步返回 task_id（真实结果异步由 Celery worker 处理）
- 需通过 GET /status/{task_id} 轮询到任务终态（completed / failed）

本模块把网络调用封装为可注入的 http_post / http_get 函数，便于单元测试 mock。
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import requests

from .perf_config import config


# 网络调用注入点（测试可替换为 mock）
def default_http_post(url: str, json: Dict, timeout: float) -> Dict:
    resp = requests.post(url, json=json, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def default_http_get(url: str, timeout: float) -> Dict:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


class TaskTimeoutError(Exception):
    """任务在超时时间内未完成。"""


@dataclass
class TaskResult:
    """单次压测查询的结果。"""
    task_id: str = ""
    status: str = "ok"            # ok / failed / timeout
    submit_ts: float = 0.0        # 提交时刻（epoch 秒）
    done_ts: float = 0.0          # 完成时刻（epoch 秒）
    latency: float = 0.0          # 端到端延迟（秒）= done_ts - submit_ts
    error: str = ""
    extra: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "latency": round(self.latency, 4),
            "error": self.error,
        }


class QueryRunner:
    """负责提交一条查询并轮询到完成，记录端到端延迟。"""

    def __init__(self,
                 query_url: str,
                 status_url_tpl: str,
                 poll_interval: float,
                 query_timeout: float,
                 http_post: Callable = default_http_post,
                 http_get: Callable = default_http_get):
        self.query_url = query_url
        self.status_url_tpl = status_url_tpl
        self.poll_interval = poll_interval
        self.query_timeout = query_timeout
        self._post = http_post
        self._get = http_get

    @staticmethod
    def from_config(cfg=config) -> "QueryRunner":
        return QueryRunner(
            query_url=cfg.query_url,
            status_url_tpl=cfg.status_url_tpl,
            poll_interval=cfg.poll_interval,
            query_timeout=cfg.query_timeout,
        )

    def _submit(self, query: str, switches: Optional[Dict] = None) -> str:
        """提交 /query，返回 task_id。"""
        session_id = "perf_" + uuid.uuid4().hex
        payload = {
            "query": query,
            "session_id": session_id,
            "is_stream": False,
        }
        if switches:
            payload.update(switches)
        data = self._post(self.query_url, payload, self.query_timeout)
        task_id = data.get("task_id") or data.get("data", {}).get("task_id") or ""
        if not task_id:
            raise ValueError(f"响应缺少 task_id: {data}")
        return task_id

    def _poll(self, task_id: str, submit_ts: float) -> TaskResult:
        """轮询 /status/{task_id} 直到终态或超时。"""
        deadline = submit_ts + self.query_timeout
        while True:
            now = time.time()
            if now >= deadline:
                return TaskResult(
                    task_id=task_id, status="timeout",
                    submit_ts=submit_ts, done_ts=now,
                    latency=now - submit_ts,
                    error=f"任务 {self.query_timeout}s 内未完成",
                )
            try:
                data = self._get(self.status_url_tpl.format(task_id=task_id), self.poll_interval)
            except Exception as e:  # 轮询期间网络抖动，重试
                time.sleep(self.poll_interval)
                continue
            st = data.get("status", "")
            if st == "completed":
                return TaskResult(
                    task_id=task_id, status="ok",
                    submit_ts=submit_ts, done_ts=now,
                    latency=now - submit_ts,
                )
            if st == "failed":
                return TaskResult(
                    task_id=task_id, status="failed",
                    submit_ts=submit_ts, done_ts=now,
                    latency=now - submit_ts,
                    error=str(data.get("detail", "任务执行失败")),
                )
            time.sleep(self.poll_interval)

    def run(self, query: str, switches: Optional[Dict] = None) -> TaskResult:
        """执行一次完整查询：提交 + 轮询到完成。"""
        submit_ts = time.time()
        try:
            task_id = self._submit(query, switches)
        except Exception as e:
            return TaskResult(
                status="failed", submit_ts=submit_ts,
                done_ts=time.time(), latency=time.time() - submit_ts,
                error=f"提交失败: {e}",
            )
        return self._poll(task_id, submit_ts)


def run_single_query(query: str,
                     switches: Optional[Dict] = None,
                     runner: Optional[QueryRunner] = None) -> TaskResult:
    """便捷函数：用默认 runner 执行单条查询。"""
    runner = runner or QueryRunner.from_config()
    return runner.run(query, switches)
