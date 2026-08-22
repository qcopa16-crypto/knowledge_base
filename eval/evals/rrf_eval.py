"""
RRF（Reciprocal Rank Fusion，倒排融合）组件评测。

被测对象：processor.query_processor.nodes.node_rrf.NodeRrf._rrf_merge

评估方法（白盒，直接调用被测节点的真实 _rrf_merge 方法，不重写算法）：
- 构造多路检索结果（向量路 / HyDE 路 / 可选网络路），每路是 (文档列表, 权重)；
- 调用真实 _rrf_merge 得到融合排序结果；
- 校验两个 RRF 核心性质：
   1. **跨路重复文档应更靠前**：同一文档被多路召回时，RRF 分应高于单路召回。
   2. **同路内排名靠前的文档得分更高**。
- 用 NDCG@K 评估融合排序与"应命中文档"的一致性（当数据集标注了相关文档时）。

RRF 为纯确定性算法，评测无需外部服务，离线即可运行。
"""
from __future__ import annotations

import json
import time
from typing import Dict, List, Optional, Sequence

from .. import metrics


# ---------------------------------------------------------------------------
# 用例：构造多路检索结果
# 每个文档 dict 至少含 chunk_id 字段（RRF 以其作为融合键）
# ---------------------------------------------------------------------------
def _make_cases() -> List[Dict]:
    """
    内置用例。chunk_id 用于标识；expected_rank 是该文档应被排到的位置（0=第一）。
    这里主要验证 RRF 的两个核心性质：
      - 文档 D 同时出现在向量路(rank2)和HyDE路(rank1)，应比只出现在单路的文档靠前。
    """
    return [
        {
            "name": "跨路重复文档优先",
            "inputs": [
                # 向量路：返回 A(rank1) B(rank2) C(rank3)
                ([{"chunk_id": "A"}, {"chunk_id": "B"}, {"chunk_id": "C"}], 1.0),
                # HyDE 路：返回 B(rank1) D(rank2)
                ([{"chunk_id": "B"}, {"chunk_id": "D"}], 1.0),
            ],
            # 期望：B 同时被两路召回且两路排名都靠前，应排第一；A、D 单路；C 单路且 rank 最靠后
            # 精确排序断言：B 必须第一（跨路重复优先的核心性质），且 A 在 D 前（A rank1 vs D rank2）
            "expected_order": ["B", "A", "D", "C"],
            "relevant": ["B", "A", "D"],  # 用于 NDCG ground truth（预期前三）
        },
        {
            "name": "权重影响",
            "inputs": [
                ([{"chunk_id": "X"}, {"chunk_id": "Y"}], 1.0),
                ([{"chunk_id": "Y"}, {"chunk_id": "Z"}], 2.0),  # 权重更高的一路
            ],
            # Y 被两路召回（1/62 + 2/61），Z 仅在高权重路 rank2（2/62），X 在低权重路 rank1（1/61）
            # 期望：Y 第一，Z 第二（权重加成），X 第三
            "expected_order": ["Y", "Z", "X"],
            "relevant": ["Y", "X", "Z"],
        },
    ]


def _run_case(case: Dict) -> Dict:
    """评测单条 RRF 用例。"""
    from processor.query_processor.nodes.node_rrf import NodeRrf

    node = NodeRrf()
    inputs = case["inputs"]

    t0 = time.time()
    try:
        merged = node._rrf_merge(inputs)  # 调用真实 _rrf_merge
        latency = time.time() - t0
    except Exception as e:
        return {
            "name": case.get("name", ""),
            "status": "failed",
            "error": str(e),
            "latency": time.time() - t0,
            "ndcg@3": float("nan"),
            "ranked_chunk_ids": [],
        }

    # merged 结构：[(doc_dict, score), ...]，已按 score 降序
    ranked_ids = [d.get("chunk_id") for d, _ in merged]

    relevant = case.get("relevant", [])
    ndcg = metrics.ndcg_at_k(ranked_ids, relevant, k=3)
    mrr = metrics.mrr_at_k(ranked_ids, relevant, k=3)

    # 校验排序正确性：期望顺序是前缀匹配（不要求覆盖全部，但前 N 项必须完全一致）
    expected_order = case.get("expected_order", [])
    order_ok = False
    if expected_order:
        order_ok = ranked_ids[:len(expected_order)] == expected_order

    # 兼容旧的"包含在前三"判定（无 expected_order 时退化为集合包含）
    if not expected_order:
        top3 = ranked_ids[:3]
        order_ok = bool(case.get("assert_top3_contains")) and \
            set(case.get("assert_top3_contains")).issubset(set(top3))

    return {
        "name": case.get("name", ""),
        "status": "ok",
        "latency": round(latency, 6),
        "ranked_chunk_ids": ranked_ids,
        "expected_order": expected_order,
        "ndcg@3": ndcg,
        "mrr@3": mrr,
        "property_cross_retrieval_ok": order_ok,
    }


def run_rrf_eval(cases: Optional[Sequence[Dict]] = None,
                 report_path: Optional[str] = None,
                 limit: Optional[int] = None) -> Dict:
    """
    运行 RRF 组件评测。
    :param cases: 评测用例；None 使用内置用例
    :param report_path: 报告输出路径
    :param limit: 只评测前 N 条；None 表示全部
    """
    from ..runner import run_batch

    cases = list(cases) if cases is not None else _make_cases()
    if limit is not None and limit > 0:
        cases = cases[:limit]

    def _aggregate(results, meta):
        ok = [r for r in results if r.get("status") == "ok"]
        prop_ok = [r for r in ok if r.get("property_cross_retrieval_ok")]
        report = {
            "meta": {
                "success_cases": len(ok),
                "cross_retrieval_priority_passed": len(prop_ok),
            },
            "metrics": {
                "ndcg@3": metrics.safe_mean([r["ndcg@3"] for r in ok]),
                "mrr@3": metrics.safe_mean([r["mrr@3"] for r in ok]),
                "cross_retrieval_priority_rate": (len(prop_ok) / len(ok)) if ok else 0.0,
            },
            "samples": results,
        }
        return report

    def _log(r) -> str:
        return (f"{r['status']} | ndcg@3={metrics.fmt_score(r.get('ndcg@3'))} "
                f"mrr@3={metrics.fmt_score(r.get('mrr@3'))} | 排序={r.get('ranked_chunk_ids')}")

    report = run_batch(
        component="rrf",
        items=cases,
        run_one=_run_case,
        snapshot_path=None,  # rrf 为确定性离线算法，无需断点/熔断落盘
        report_path=report_path,
        aggregate=_aggregate,
        resume=False,
        sleep_secs=0,
        log_line=_log,
    )
    report["meta"]["component"] = "rrf"
    return report
