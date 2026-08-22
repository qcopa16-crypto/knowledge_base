"""
检索路引入/去除影响对比评测。

用途：量化"引入某一路检索（embedding / hyde / mcp）"对端到端回答质量的提升度，
用于简历量化结论、方案选型、消融实验（Ablation）。

原理：
    同一批 query，分别以"不同检索路组合"调用 /query（通过 enable_* 开关控制），
    比较各版本的回答质量指标（ROUGE-L / BLEU / 语义相似度 / 检索命中）。
    - 完整版（三路全开）为基线
    - 去 embedding / 去 hyde / 去 mcp 为对比版
    "引入某路提升" = 完整版指标 - 去某路指标（每条 query 逐条计算，再汇总平均）

设计要点：
    - 默认只用 1 条测试数据，减少 API 消耗
    - 每条 query 需要跑 (1 + N) 次完整链路，N=要对比的路数
    - 结果带断点续跑 + 熔断
"""
from __future__ import annotations

import json
import time
from typing import Dict, List, Optional, Sequence

from .. import metrics
from .. import snapshot
from ..eva_config import config
from .evaluator import evaluate_sample

# 各路开关映射：显示名 -> (开关字段, 关闭值)
RETRIEVAL_PATHS = {
    "embedding": "enable_embedding",
    "hyde": "enable_hyde",
    "web_search": "enable_web_search",
}


def _build_switches(disable: Optional[str] = None) -> Dict:
    """构造检索路开关。disable 指定要去掉的路名（None 表示全开）。"""
    switches = {"enable_embedding": True, "enable_hyde": True, "enable_web_search": True}
    if disable:
        field = RETRIEVAL_PATHS.get(disable)
        if field:
            switches[field] = False
    return switches


def _metric_value(r: Dict, key: str) -> Optional[float]:
    v = r.get(key)
    return v if v is not None and not metrics.is_nan(v) else None


def _run_single_compare(sample: Dict, paths: Sequence[str]) -> Dict:
    """对单条样本，跑完整版 + 各去路版，返回各版本指标与提升度。"""
    query = sample.get("query", "")

    # 1) 完整版（基线）
    full = evaluate_sample(sample, switches=_build_switches(None))
    full_metrics = {
        "rouge_l": _metric_value(full, "rouge_l"),
        "bleu": _metric_value(full, "bleu"),
        "semantic_sim": _metric_value(full, "semantic_sim"),
        "retrieval_hit": _metric_value(full, "retrieval_hit"),
        "item_name_hit": _metric_value(full, "item_name_hit"),
    }

    # 2) 各去路版
    ablations = {}
    for p in paths:
        r = evaluate_sample(sample, switches=_build_switches(p))
        ablations[p] = {
            "rouge_l": _metric_value(r, "rouge_l"),
            "bleu": _metric_value(r, "bleu"),
            "semantic_sim": _metric_value(r, "semantic_sim"),
            "retrieval_hit": _metric_value(r, "retrieval_hit"),
            "item_name_hit": _metric_value(r, "item_name_hit"),
        }

    # 3) 提升度：完整版 - 去路版（正值表示"引入某路带来提升"）
    gains = {}
    for p in paths:
        gains[p] = {}
        for key in ("rouge_l", "bleu", "semantic_sim", "retrieval_hit", "item_name_hit"):
            fv = full_metrics.get(key)
            av = ablations[p].get(key)
            if fv is not None and av is not None:
                gains[p][key] = round(fv - av, 4)
            else:
                gains[p][key] = None

    return {
        "query": query,
        "status": "ok",
        "full": full_metrics,
        "ablations": ablations,
        "gains": gains,
    }


def run_compare_eval(samples: Optional[Sequence[Dict]] = None,
                     report_path: Optional[str] = None,
                     resume: bool = True,
                     limit: Optional[int] = None,
                     paths: Optional[Sequence[str]] = None,
                     dataset_path: Optional[str] = None) -> Dict:
    """
    运行检索路对比评测，输出各路的引入/去除影响（提升度）。

    :param samples: 评测样本；None 从数据集读取
    :param report_path: 报告输出路径
    :param resume: 是否启用断点续跑
    :param limit: 只评测前 N 条；None 表示全部
    :param paths: 要对比的检索路（默认 embedding/hyde/web_search 全对比）
    :param dataset_path: 数据集路径（samples 为 None 时使用）
    """
    if samples is None:
        from ..data.dataset import load_dataset
        samples = load_dataset(dataset_path or config.dataset_path)
    samples = [s for s in samples if s.get("query")]
    samples = list(samples)
    if limit is not None and limit > 0:
        samples = samples[:limit]

    paths = list(paths) if paths else list(RETRIEVAL_PATHS.keys())

    snapshot_path = config.compare_snapshot_path
    done_map = snapshot.load_snapshot(snapshot_path) if resume else {}

    if resume and done_map:
        todo, done_list = [], []
        for s in samples:
            k = s.get("query")
            if done_map and k and k in done_map:
                done_list.append(done_map[k])
            else:
                todo.append(s)
        print(f"[compare] 断点续跑：已有 {len(done_list)} 条完成，本次待评测 {len(todo)} 条")
    else:
        todo, done_list = list(samples), []

    results = list(done_list)
    consecutive_failures = 0
    tripped = False
    for i, s in enumerate(todo):
        r = _run_single_compare(s, paths)
        results.append(r)
        snapshot.save_snapshot(snapshot_path, results, meta={"component": "compare"})
        # 输出本条的提升度概览
        g = r.get("gains", {})
        g_str = " ".join(
            f"{p}:rouge={'+' if (g[p].get('rouge_l') or 0) >= 0 else ''}{g[p].get('rouge_l')}"
            for p in paths if p in g
        )
        print(f"[compare] {len(results)}/{len(samples)} | {r['status']} | {r['query'][:30]} | {g_str}")
        time.sleep(0.3)
        if r.get("status") == "failed":
            consecutive_failures += 1
        else:
            consecutive_failures = 0
        if consecutive_failures >= config.max_consecutive_failures:
            print(f"[compare] 连续 {consecutive_failures} 条失败，触发熔断。")
            tripped = True
            break

    # ---- 聚合提升度 ----
    ok = [r for r in results if r.get("status") == "ok"]
    metric_keys = ("rouge_l", "bleu", "semantic_sim", "retrieval_hit", "item_name_hit")
    agg_gains = {}
    for p in paths:
        agg_gains[p] = {}
        for key in metric_keys:
            vals = [g[p].get(key) for g in (r.get("gains", {}) for r in ok)
                    if g.get(p) and g[p].get(key) is not None]
            agg_gains[p][key] = metrics.safe_mean(vals) if vals else None

    report = {
        "meta": {
            "component": "compare",
            "total_samples": len(samples),
            "success_samples": len(ok),
            "paths_compared": list(paths),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "avg_gains": agg_gains,
        "failed_count": sum(1 for r in results if r.get("status") == "failed"),
        "circuit_broken": tripped,
        "samples": results,
    }

    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"[compare] 报告已写入: {report_path}")

    # 控制台汇总
    print("\n===== 提升度汇总（完整版 - 去某路）=====")
    for p in paths:
        row = agg_gains.get(p, {})
        print(f"引入 {p:10s} | " + " ".join(
            f"{k}={row.get(k)}" for k in metric_keys if row.get(k) is not None))
    return report
