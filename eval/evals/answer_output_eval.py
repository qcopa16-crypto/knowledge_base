"""
答案生成节点（node_answer_output）评测。

被测对象：processor.query_processor.nodes.node_answer_output.NodeAnswerOutput

评估方法（白盒，直接调用被测节点真实 process）：
- 从数据集读取自然问题（query）与参考答案（reference）；
- 用 Milvus 检索出的真实相关切片构造 reranked_docs（符合 NodeRerank 输出格式）；
- 调用 NodeAnswerOutput.process 生成答案；
- 用 ROUGE-L / BLEU / 语义相似度 衡量生成答案与参考答案的匹配度。

该节点需要 LLM 生成答案 + MongoDB 写历史（隔离 session），默认只测 1 条。
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Dict, List, Optional, Sequence

from .. import metrics
from .. import snapshot
from ..eva_config import config
from ..embed_sim import try_enable_semantic


# ---------------------------------------------------------------------------
# 从 Milvus 取与 query 相关的切片，构造 reranked_docs
# ---------------------------------------------------------------------------
def _retrieve_context(query: str, item_names: Optional[List[str]], topk: int = 5) -> List[Dict]:
    """复用业务向量检索节点取真实相关切片，构造符合 NodeRerank 输出的 reranked_docs。"""
    from processor.query_processor.nodes.node_search_embedding import NodeSearchEmbedding
    state = {"rewritten_query": query, "item_names": item_names or []}
    out = NodeSearchEmbedding().process(state)
    chunks = out.get("embedding_chunks", []) or []
    docs = []
    for c in chunks[:topk]:
        docs.append({
            "chunk_id": c.get("chunk_id"),
            "title": c.get("title", ""),
            "content": c.get("content", ""),
            "url": None,
            "source": "local",
            "score": 0.9,  # 评测场景下简化打分；真实排序由上游 rerank 决定
        })
    return docs


def _run_single(sample: Dict, topk: int = 5) -> Dict:
    """评测单条样本：生成答案并计算与参考的匹配度。"""
    from processor.query_processor.nodes.node_answer_output import NodeAnswerOutput

    query = sample.get("query", "")
    reference = sample.get("reference", "")
    item_names = sample.get("item_names") or []
    # 数据集里的 item_name 是字符串，转成列表形式
    if isinstance(item_names, str):
        item_names = [item_names] if item_names else []

    session_id = "eva_answer_" + uuid.uuid4().hex
    try:
        reranked_docs = _retrieve_context(query, item_names, topk=topk)
    except Exception as e:
        return {
            "query": query,
            "status": "failed",
            "error": f"retrieve: {e}",
            "latency": 0.0,
            "answer": "",
            "rouge_l": float("nan"),
            "bleu": float("nan"),
            "semantic_sim": float("nan"),
            "doc_count": 0,
        }

    state = {
        "session_id": session_id,
        "original_query": query,
        "rewritten_query": query,
        "item_names": item_names,
        "history": [],
        "reranked_docs": reranked_docs,
        "is_stream": False,   # 非流式，避免 SSE 推送依赖
        "answer": None,
    }

    t0 = time.time()
    try:
        result_state = NodeAnswerOutput().process(state)
        latency = time.time() - t0
    except Exception as e:
        return {
            "query": query,
            "status": "failed",
            "error": str(e),
            "latency": round(time.time() - t0, 3),
            "answer": "",
            "rouge_l": float("nan"),
            "bleu": float("nan"),
            "semantic_sim": float("nan"),
            "doc_count": len(reranked_docs),
        }

    answer = result_state.get("answer", "") or ""

    if reference:
        rouge = metrics.rouge_l_f1(reference, answer)
        bleu = metrics.bleu(reference, answer)
        sem = metrics.semantic_similarity(reference, answer)
    else:
        rouge = bleu = sem = float("nan")

    return {
        "query": query,
        "status": "ok",
        "latency": round(latency, 3),
        "answer": answer,
        "reference": reference,
        "doc_count": len(reranked_docs),
        "rouge_l": rouge,
        "bleu": bleu,
        "semantic_sim": sem,
    }


def run_answer_output_eval(samples: Optional[Sequence[Dict]] = None,
                           report_path: Optional[str] = None,
                           resume: bool = True,
                           limit: Optional[int] = None,
                           dataset_path: Optional[str] = None) -> Dict:
    """
    运行答案生成评测，聚合 ROUGE-L / BLEU / 语义相似度。
    :param samples: 评测样本；None 从数据集读取
    :param report_path: 报告输出路径
    :param resume: 是否启用断融
    :param limit: 只评测前 N 条；None 表示全部
    :param dataset_path: 数据集路径（samples 为 None 时使用）
    """
    if samples is None:
        from ..data.dataset import load_dataset
        samples = load_dataset(dataset_path or config.dataset_path)
        # 只需 query/reference/item_name，剔除无关字段
        samples = [
            {"query": s.get("query", ""), "reference": s.get("reference", ""),
             "item_name": s.get("item_name", "")}
            for s in samples if s.get("query")
        ]
    samples = list(samples)
    if limit is not None and limit > 0:
        samples = samples[:limit]

    try_enable_semantic()

    from ..runner import run_batch

    def _aggregate(results, meta):
        ok = [r for r in results if r.get("status") == "ok"]
        ans_ok = [r for r in ok if not metrics.is_nan(r.get("rouge_l"))]
        report = {
            "meta": {
                "answer_quality_samples": len(ans_ok),
            },
            "metrics": {
                "rouge_l": metrics.safe_mean([r["rouge_l"] for r in ans_ok]),
                "bleu": metrics.safe_mean([r["bleu"] for r in ans_ok]),
                "semantic_sim": metrics.safe_mean([r["semantic_sim"] for r in ans_ok]),
            },
            "latency": metrics.latency_stats(
                [r["latency"] for r in ok if r.get("latency") is not None]),
            "samples": results,
        }
        return report

    def _log(r) -> str:
        return (f"{r['status']} | rouge={metrics.fmt_score(r.get('rouge_l'))} "
                f"bleu={metrics.fmt_score(r.get('bleu'))} | {r.get('query', '')[:40]}")

    return run_batch(
        component="answer_output",
        items=samples,
        run_one=_run_single,
        snapshot_path=config.answer_snapshot_path,
        report_path=report_path,
        aggregate=_aggregate,
        resume=resume,
        sleep_secs=0.3,
        log_line=_log,
    )
