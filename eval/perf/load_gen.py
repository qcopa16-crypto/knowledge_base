"""
并发压测引擎。

基于 ThreadPoolExecutor 实现多线程并发压测，支持三种模式：
1. 固定并发（fixed）：以固定并发数持续一段时长
2. 阶梯加压（staged）：依次执行 [并发, 时长] 档位，逐档加压并记录每档指标
3. 持续时长（duration）：以目标 QPS 估算并发，持续一段时长

逐条采集提交/完成时间戳，输出到 perf_metrics 聚合。压测前做预热（warm-up）。

为保证可测试性，本引擎通过注入"执行单条查询"的可调用对象 work_fn 工作，
默认实现包装 latency.QueryRunner，测试时可替换为同步 mock。
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .perf_config import config
from .latency import QueryRunner, TaskResult


# 单条工作函数签名：work_fn(query: str) -> TaskResult
WorkFn = Callable[[str], TaskResult]


def _default_work_fn(runner: QueryRunner, switches: Optional[Dict] = None) -> WorkFn:
    def work(query: str) -> TaskResult:
        return runner.run(query, switches)
    return work


@dataclass
class StageResult:
    """一个负载档位的压测结果。"""
    stage_index: int
    concurrency: int
    duration_secs: float
    actual_duration: float
    results: List[TaskResult]

    def ok_results(self) -> List[TaskResult]:
        return [r for r in self.results if r.status == "ok"]

    def failed_results(self) -> List[TaskResult]:
        return [r for r in self.results if r.status != "ok"]


class LoadGenerator:
    """并发压测引擎。"""

    def __init__(self,
                 work_fn: WorkFn,
                 poll_duration: float = 1.0,
                 max_workers: Optional[int] = None):
        self.work_fn = work_fn
        self.poll_duration = poll_duration
        self.max_workers = max_workers

    @staticmethod
    def from_config(runner: Optional[QueryRunner] = None,
                    switches: Optional[Dict] = None,
                    cfg=config) -> "LoadGenerator":
        runner = runner or QueryRunner.from_config(cfg)
        return LoadGenerator(
            work_fn=_default_work_fn(runner, switches),
            max_workers=None,
        )

    # ---- 固定并发：持续 N 秒 ----
    def run_fixed(self, query: str, concurrency: int,
                  duration_secs: float, warmup_secs: float = 0.0) -> StageResult:
        if concurrency < 1:
            raise ValueError("concurrency 必须 >= 1")
        # 预热：以并发=min(concurrency,2) 快速打几条，稳定连接池
        if warmup_secs > 0:
            self._warmup(query, max(1, min(concurrency, 2)), warmup_secs)

        start = time.time()
        results: List[TaskResult] = []

        def one_round() -> None:
            # 单轮：并发 workers 各执行一次，直至达到持续时长
            while time.time() - start < duration_secs:
                r = self.work_fn(query)
                results.append(r)  # list.append 在 CPython 下原子，无需加锁

        # 用 ThreadPoolExecutor 承载并发 worker，直到超过持续时长
        workers = min(concurrency, self.max_workers or concurrency)
        futures = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            # 每个 worker 提交一个持续执行的 Future
            for _ in range(concurrency):
                futures.append(pool.submit(one_round))
            for fut in as_completed(futures):
                # 收集 worker 内部异常（不中断压测）
                fut.result()

        return StageResult(
            stage_index=0, concurrency=concurrency,
            duration_secs=duration_secs, actual_duration=time.time() - start,
            results=results,
        )

    # ---- 阶梯加压：依次执行档位 ----
    def run_staged(self, query: str,
                   stages: Sequence[Tuple[int, float]],
                   warmup_secs: float = 0.0,
                   stage_cooldown: float = 0.0) -> List[StageResult]:
        outputs: List[StageResult] = []
        for i, (conc, dur) in enumerate(stages):
            sr = self.run_fixed(query, conc, dur, warmup_secs)
            outputs.append(sr)
            if stage_cooldown > 0 and i < len(stages) - 1:
                time.sleep(stage_cooldown)
        return outputs

    # ---- 持续时长：以目标 QPS 估算并发 ----
    def run_duration(self, query: str, target_qps: float,
                     duration_secs: float, warmup_secs: float = 0.0) -> StageResult:
        if target_qps <= 0:
            raise ValueError("target_qps 必须 > 0")
        # 粗估算并发：期望每请求 latency ~ 由 poll_duration 决定，用启发式
        est_concurrency = max(1, int(target_qps * self.poll_duration))
        return self.run_fixed(query, est_concurrency, duration_secs, warmup_secs)

    # ---- 预热 ----
    def _warmup(self, query: str, concurrency: int, warmup_secs: float) -> None:
        self.run_fixed(query, concurrency, min(warmup_secs, 5.0), warmup_secs=0.0)
