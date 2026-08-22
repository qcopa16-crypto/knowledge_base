"""
评测公共运行框架。

把各 eval 模块重复的"断点续跑 / 熔断 / 限速 / 逐条打印 / 报告落盘"逻辑抽成统一的
批量评测循环。各 eval 模块只需提供：

    - items        待评测数据列表
    - run_one      单条评测函数：item -> Dict（必须含 status 字段：ok / failed / skipped）
    - aggregate    聚合函数：(results, meta) -> Dict（生成最终 report）

对外接口（run.py）保持完全不变。
"""
from __future__ import annotations

import json
import time
from typing import Callable, Dict, List, Optional, Sequence

from . import snapshot
from .eva_config import config

# 单条评测结果类型：Dict，必须含 "status" 字段
_Item = Dict
_Result = Dict
_Report = Dict


def run_batch(component: str,
              items: Sequence[_Item],
              run_one: Callable[[_Item], _Result],
              snapshot_path: str,
              report_path: Optional[str],
              aggregate: Callable[[List[_Result], Dict], _Report],
              resume: bool = True,
              sleep_secs: float = 0.3,
              log_line: Optional[Callable[[_Result], str]] = None,
              id_key: str = "query") -> _Report:
    """
    通用批量评测循环。

    :param component: 组件名（用于日志/断点元信息）
    :param items: 待评测数据（已由调用方按 limit 截断）
    :param run_one: 单条评测函数，返回含 status 的 Dict（结果须含 id_key 字段以支持断点）
    :param snapshot_path: 断点快照路径
    :param report_path: 报告输出路径（None 则不写盘）
    :param aggregate: 聚合函数 (results, meta) -> report Dict
    :param resume: 是否启用断点续跑
    :param sleep_secs: 每条之间限速（秒）
    :param log_line: 自定义逐条打印格式；None 则打印 status + query
    :param id_key: 断点去重主键字段（默认 query；如 retrieval 用 chunk_id）
    :return: 聚合后的 report
    """
    items = list(items)

    # ---- 断点续跑（用 id_key 字段作为去重主键；snapshot_path 为 None 时不做断点） ----
    if snapshot_path:
        done_map = snapshot.load_snapshot(snapshot_path) if resume else {}
        todo, done_list = [], []
        for item in items:
            k = item.get(id_key)
            if resume and done_map and k and k in done_map:
                done_list.append(done_map[k])
            else:
                todo.append(item)
        if resume and done_list:
            print(f"[{component}] 断点续跑：已有 {len(done_list)} 条完成，本次待评测 {len(todo)} 条")
        results = list(done_list)
    else:
        todo, done_list = list(items), []
        results = []

    # ---- 熔断循环 ----
    consecutive_failures = 0
    tripped = False
    for i, item in enumerate(todo):
        r = run_one(item)
        results.append(r)
        # 立即落盘断点，中断后重跑不丢失已完成进度
        snapshot.save_snapshot(snapshot_path, results, meta={"component": component})

        # 逐条打印
        if log_line:
            print(f"[{component}] {len(results)}/{len(items)} | {log_line(r)}")
        else:
            print(f"[{component}] {len(results)}/{len(items)} | {r.get('status')} | "
                  f"{str(r.get('query', r.get('original_query', '')))[:40]}")

        # 限速
        if sleep_secs > 0:
            time.sleep(sleep_secs)

        # 熔断
        if r.get("status") == "failed":
            consecutive_failures += 1
        else:
            consecutive_failures = 0
        if consecutive_failures >= config.max_consecutive_failures:
            print(f"[{component}] 连续 {consecutive_failures} 条失败，触发熔断，停止后续评测。")
            tripped = True
            break

    # ---- 聚合 ----
    meta = {
        "component": component,
        "total_samples": len(items),
        "success_samples": sum(1 for r in results if r.get("status") == "ok"),
        "skipped_samples": sum(1 for r in results if r.get("status") == "skipped"),
        "failed_count": sum(1 for r in results if r.get("status") == "failed"),
        "circuit_broken": tripped,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    report = aggregate(results, meta)
    report.setdefault("meta", {}).update(meta)

    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"[{component}] 报告已写入: {report_path}")
    return report
