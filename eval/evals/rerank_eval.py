"""
Rerank（交叉编码器重排）组件评测。

被测对象：utils.reranker_http_utils.rerank_documents(query, documents) -> list[float]

评估方法（白盒，直接调用被测 rerank 函数）：
- 构造 (query, 候选文档列表, 相关文档子集) 的数据集；
- 调用真实 rerank 模型对候选文档打分并按 score 降序排列；
- 用 NDCG@K / MRR@K / P@K 衡量重排后相关文档是否靠前。

该评测需要真实 rerank 服务在运行（dashscope / 配置的 rerank 模型）。
"""
from __future__ import annotations

import json
import random
import time
from typing import Dict, List, Optional, Sequence

from .. import metrics
from .. import snapshot
from ..eva_config import config


# ---------------------------------------------------------------------------
# 数据集构造
# ---------------------------------------------------------------------------
def _make_dataset() -> List[Dict]:
    """内置一组测试用例：query + 候选文档 + 相关文档子集（按业务常识设定）。"""
    return [
        {
            "query": "HAK180烫金机如何调节转印温度？",
            "docs": [
                "调节转印温度需要先打开操作面板，找到温度旋钮。",
                "今天天气不错，适合出门散步。",
                "转印温度建议设置在110摄氏度左右，具体要看烫金材料。",
                "苹果发布了新款手机。",
                "温度设置过高会导致烫金纸烧毁，请参考说明书。",
            ],
            # 与 query 相关的文档（ground truth），通常应被重排到前面
            "relevant": [0, 2, 4],
        },
        {
            "query": "万用表如何测量直流电压？",
            "docs": [
                "测量直流电压时把旋钮转到V档，红笔接正极。",
                "这款跑步机的减震效果很不错。",
                "注意直流电压有正负极之分，接反会烧表。",
                "周末去爬山是个不错的选择。",
                "读表时视线要正对刻度盘避免视差。",
            ],
            "relevant": [0, 2, 4],
        },
    ]


def _run_single(sample: Dict, topk: int = 3) -> Dict:
    """评测单条：调用 rerank_documents 并计算排序指标。"""
    from utils.reranker_http_utils import rerank_documents

    query = sample["query"]
    docs = sample["docs"]
    relevant = sample["relevant"]

    t0 = time.time()
    try:
        scores = rerank_documents(query, docs)
        latency = time.time() - t0
    except Exception as e:
        return {
            "query": query,
            "status": "failed",
            "error": str(e),
            "latency": time.time() - t0,
            "ndcg@3": float("nan"),
            "mrr@3": float("nan"),
            "p@3": float("nan"),
        }

    # 按 score 降序排列文档（并列时保持原顺序，用稳定排序）
    ranked = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)
    ranked_docs = [docs[i] for i in ranked]

    return {
        "query": query,
        "status": "ok",
        "latency": round(latency, 3),
        "ranked_indices": ranked,
        "ndcg@3": metrics.ndcg_at_k(ranked, relevant, k=topk),
        "mrr@3": metrics.mrr_at_k(ranked, relevant, k=topk),
        "p@3": metrics.precision_at_k(ranked, relevant, k=topk),
    }


def run_rerank_eval(samples: Optional[Sequence[Dict]] = None,
                    report_path: Optional[str] = None,
                    resume: bool = True,
                    limit: Optional[int] = None) -> Dict:
    """
    运行 Rerank 组件评测，聚合 NDCG@3 / MRR@3 / P@3。
    :param samples: 评测样本；None 使用内置用例
    :param report_path: 报告输出路径
    :param resume: 是否启用断融（True 续跑跳过已完成；False 从头跑）
    :param limit: 只评测前 N 条；None 表示全部
    """
    samples = list(samples) if samples is not None else _make_dataset()
    if limit is not None and limit > 0:
        samples = samples[:limit]

    from ..runner import run_batch

    def _aggregate(results, meta):
        ok = [r for r in results if r.get("status") == "ok"]
        report = {
            "metrics": {
                "ndcg@3": metrics.safe_mean([r["ndcg@3"] for r in ok]),
                "mrr@3": metrics.safe_mean([r["mrr@3"] for r in ok]),
                "p@3": metrics.safe_mean([r["p@3"] for r in ok]),
            },
            "latency": metrics.latency_stats(
                [r["latency"] for r in ok if r.get("latency") is not None]),
            "samples": results,
        }
        return report

    def _log(r) -> str:
        return (f"{r['status']} | ndcg@3={metrics.fmt_score(r.get('ndcg@3'))} "
                f"mrr@3={metrics.fmt_score(r.get('mrr@3'))} "
                f"p@3={metrics.fmt_score(r.get('p@3'))} | {r.get('query', '')[:30]}")

    return run_batch(
        component="rerank",
        items=samples,
        run_one=_run_single,
        snapshot_path=config.rerank_snapshot_path,
        report_path=report_path,
        aggregate=_aggregate,
        resume=resume,
        sleep_secs=0.2,
        log_line=_log,
    )
