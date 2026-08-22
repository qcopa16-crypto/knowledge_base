"""
性能压测入口。

按负载档位执行阶梯加压压测，汇总吞吐/延迟/错误率，并与既有质量评测输出关联，
形成"性能 + 质量"闭环报告。风格与 eval/run.py 一致（函数调用式 main）。

用法（函数式）：
    from eval.perf.run_perf import main
    main(mode="staged", queries=["如何调节转印温度？"], report_path="perf_report.json")

CLI 用法：
    python -m eval.perf.run_perf --mode staged --query "..." --report perf_report.json
"""
from __future__ import annotations

import json
import os
import sys
from typing import Dict, List, Optional, Sequence

# 控制台编码健壮性：避免 GBK 等非 UTF-8 控制台打印特殊字符时抛 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from .baseline import BaselineConfig, evaluate_overall, relative_gain
from .latency import QueryRunner
from .load_gen import LoadGenerator, StageResult
from .perf_config import config
from .perf_metrics import merge_with_quality, summarize_stages
from .report import build_report, write_report


def _load_queries(query: Optional[str],
                  dataset_path: Optional[str] = None) -> List[str]:
    """确定压测查询集：优先显式 query，否则从数据集读取，兜底用默认查询。"""
    if query:
        return [query]
    if dataset_path:
        try:
            from ..data.dataset import load_dataset
            items = load_dataset(dataset_path)
            qs = [i.get("query") for i in items if i.get("query")]
            if qs:
                return qs
        except Exception:
            pass
    return ["如何调节转印温度？"]


def _load_previous_report(report_path: Optional[str]) -> Optional[Dict]:
    """读取历史压测报告（用于相对提升对比），不存在返回 None。"""
    if not report_path or not os.path.exists(report_path):
        return None
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main(mode: str = "staged",
         queries: Optional[Sequence[str]] = None,
         query: Optional[str] = None,
         dataset_path: Optional[str] = None,
         report_path: Optional[str] = None,
         cfg=config,
         runner: Optional[QueryRunner] = None,
         generator: Optional[LoadGenerator] = None) -> Dict:
    """
    运行性能压测。

    :param mode: "staged"(默认,阶梯加压) | "fixed"(固定并发) | "duration"(持续时长)
    :param queries: 压测查询列表；None 时用 query / dataset_path 决定
    :param query: 单个压测查询
    :param dataset_path: 数据集路径（queries 为 None 时读取 query 列表）
    :param report_path: 报告输出路径；None 用配置默认
    :param cfg: 压测配置
    :param runner: 查询执行器；None 用配置默认（真实网络）
    :param generator: 压测引擎；None 自动构建
    :return: 压测报告 dict
    """
    # 1) 确定查询集（压测取第一条即可，重点测延迟/吞吐而非覆盖面）
    if queries is not None:
        qs = list(queries)
    else:
        qs = _load_queries(query, dataset_path)
    if not qs:
        raise ValueError("无可用压测查询")
    target_query = qs[0]

    # 2) 构建压测引擎
    runner = runner or QueryRunner.from_config(cfg)
    gen = generator or LoadGenerator.from_config(runner, cfg=cfg)

    # 3) 执行压测
    stages: List[StageResult]
    if mode == "fixed":
        conc = cfg.concurrency_stages[0][0] if cfg.concurrency_stages else 1
        dur = cfg.concurrency_stages[0][1] if cfg.concurrency_stages else 5
        sr = gen.run_fixed(target_query, conc, dur, warmup_secs=cfg.warmup_secs)
        stages = [sr]
    elif mode == "duration":
        sr = gen.run_duration(target_query, cfg.target_qps or 1.0,
                              (cfg.concurrency_stages[0][1] if cfg.concurrency_stages else 5),
                              warmup_secs=cfg.warmup_secs)
        stages = [sr]
    else:  # staged
        stages = gen.run_staged(
            target_query,
            cfg.concurrency_stages,
            warmup_secs=cfg.warmup_secs,
            stage_cooldown=cfg.stage_cooldown,
        )

    # 4) 聚合性能指标
    summary = summarize_stages(stages)

    # 5) 关联质量评测报告（如存在）
    q_report = _load_previous_report(cfg.quality_report_path)
    summary = merge_with_quality(summary, q_report)

    # 6) 基线判定 + 相对提升
    overall = summary["overall"]
    baseline_result = evaluate_overall(overall, BaselineConfig())
    prev = _load_previous_report(report_path or cfg.perf_report_path)
    prev_overall = (prev or {}).get("overall") if prev else None
    baseline_result["relative_gain"] = relative_gain(overall, prev_overall)

    # 7) 组装报告并落盘
    config_info = {
        "mode": mode,
        "query": target_query,
        "concurrency_stages": list(cfg.concurrency_stages),
        "poll_interval": cfg.poll_interval,
        "query_timeout": cfg.query_timeout,
        "target_qps": cfg.target_qps,
    }
    report = build_report(summary, baseline_result, config_info)
    out = report_path or cfg.perf_report_path
    write_report(report, out)

    # 8) 控制台汇总
    print(f"\n===== 性能压测汇总 [{mode}] =====")
    print(f"query: {target_query[:40]}")
    print(f"verdict: {report['baseline']['verdict']}")
    o = report["overall"]
    print(f"吞吐={o.get('throughput_req_s')} req/s | 错误率={o.get('error_rate')} | "
          f"P50={o.get('p50')}s P95={o.get('p95')}s P99={o.get('p99')}s | "
          f"总请求={report['meta'].get('total_requests')}")
    return report


def _cli_main():
    import argparse
    parser = argparse.ArgumentParser(description="RAG 性能压测")
    parser.add_argument("--mode", default="staged",
                        choices=["staged", "fixed", "duration"])
    parser.add_argument("--query", default=None, help="压测查询")
    parser.add_argument("--dataset", default=None, help="数据集路径")
    parser.add_argument("--report", default=None, help="报告输出路径")
    args = parser.parse_args()
    report = main(mode=args.mode, query=args.query, dataset_path=args.dataset,
                  report_path=args.report)
    print(f"报告已写入: {args.report or config.perf_report_path}")


if __name__ == "__main__":
    _cli_main()
