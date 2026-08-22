"""
性能指标聚合：把一个或多个 StageResult 聚合成指标字典，供压测报告使用。

复用 eval/metrics.py 的 perf_stats / latency_stats。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .. import metrics
from .load_gen import StageResult
from .latency import TaskResult


def _collect_results(stages: Sequence[StageResult]) -> List[TaskResult]:
    out: List[TaskResult] = []
    for sr in stages:
        out.extend(sr.results)
    return out


def stage_metrics(stage: StageResult) -> Dict:
    """聚合单个档位的指标。"""
    ok = stage.ok_results()
    failed = stage.failed_results()
    latencies = [r.latency for r in ok if r.latency is not None]
    return {
        "concurrency": stage.concurrency,
        "duration_secs": stage.duration_secs,
        "actual_duration": round(stage.actual_duration, 3),
        "total": len(stage.results),
        "perf": metrics.perf_stats(
            latencies,
            success_count=len(ok),
            fail_count=len(failed),
            duration_secs=stage.actual_duration,
        ),
    }


def summarize_stages(stages: Sequence[StageResult]) -> Dict:
    """汇总所有档位，输出整体指标 + 各档明细。"""
    all_res = _collect_results(stages)
    ok = [r for r in all_res if r.status == "ok"]
    failed = [r for r in all_res if r.status != "ok"]
    latencies = [r.latency for r in ok if r.latency is not None]
    total_dur = sum(s.actual_duration for s in stages) or 1.0

    return {
        "meta": {
            "stages": len(stages),
            "total_requests": len(all_res),
            "total_success": len(ok),
            "total_failed": len(failed),
            "total_duration_secs": round(total_dur, 3),
        },
        "overall": metrics.perf_stats(
            latencies,
            success_count=len(ok),
            fail_count=len(failed),
            duration_secs=total_dur,
        ),
        "stages": [stage_metrics(s) for s in stages],
    }


def merge_with_quality(summary: Dict, quality_report: Optional[Dict]) -> Dict:
    """将质量评测报告的关键指标并入性能汇总（形成性能+质量闭环）。"""
    out = dict(summary)
    q = {}
    if quality_report:
        q = {
            "rouge_l": _qget(quality_report, ["answer_quality", "rouge_l"]),
            "bleu": _qget(quality_report, ["answer_quality", "bleu"]),
            "semantic_sim": _qget(quality_report, ["answer_quality", "semantic_sim"]),
            "retrieval_hit_rate": _qget(quality_report, ["retrieval", "retrieval_hit_rate"]),
            "item_name_hit_rate": _qget(quality_report, ["retrieval", "item_name_hit_rate"]),
        }
    out["quality"] = q
    return out


def _qget(d: Dict, keys: Sequence[str]):
    """按路径安全取字典值，缺失返回 None。"""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur
