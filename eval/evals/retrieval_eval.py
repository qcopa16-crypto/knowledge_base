"""
向量检索召回评测（embedding 与 HyDE 两个模式）。

被测对象：
- NodeSearchEmbedding（--component embedding）→ embedding_chunks
- NodeSearchEmbeddingHyde（--component hyde）   → hyde_embedding_chunks

评估方法（白盒，直接调用被测节点真实 process）：
1. 从 Milvus chunks 集合采样若干“锚点切片”作为 ground truth。
2. 对每个锚点构造查询（用其 content 作为查询，或简化提取）。
3. 调用被测节点真实检索，得到召回结果。
4. 命中判定（两级）：
   - self_recall@k：锚点切片本身（chunk_id）是否被召回（自我召回）。
   - item_recall@k：锚点同 item_name 的切片是否有被召回（商品级召回）。
5. 指标：self_recall@k / item_recall@k / MRR@k。

需要：Milvus 已配置且有数据、BGE-M3 embedding 模型可用（embedding 模式）、LLM 可用（hyde 模式会生成假设文档）。
"""
from __future__ import annotations

import json
import time
from typing import Dict, List, Optional, Sequence

from .. import metrics
from .. import snapshot
from ..eva_config import config


# ---------------------------------------------------------------------------
# 从 Milvus 采样锚点切片作为 ground truth
# ---------------------------------------------------------------------------
def _sample_anchors(sample_size: int = 5, expr: Optional[str] = None) -> List[Dict]:
    try:
        from pymilvus import MilvusClient
    except ImportError:
        print("[retrieval] 缺少 pymilvus，无法采样。")
        return []
    if not config.milvus_url:
        print("[retrieval] 未配置 Milvus，无法采样。")
        return []

    try:
        client = MilvusClient(uri=config.milvus_url)
        rows = client.query(
            collection_name=config.chunks_collection,
            filter=expr or "",
            output_fields=["chunk_id", "content", "item_name"],
            limit=max(sample_size * 3, 100),
        )
    except Exception as e:
        print(f"[retrieval] Milvus 采样失败: {e}")
        return []

    # 过滤掉无 content 或内容过短的，洗牌后取前 sample_size
    valid = [r for r in rows if r.get("content")]
    import random
    random.shuffle(valid)
    return valid[:sample_size]


def _build_query(anchor: Dict) -> str:
    """从锚点切片构造查询。

    优先使用数据集里为该切片标注的自然问题 query（避免用原文自证导致的召回虚高）；
    没有标注时回退为截取 content 前若干字（此时标注为"自证偏置"，供评估时区分）。
    """
    nat_query = (anchor.get("query") or "").strip()
    if nat_query:
        return nat_query
    content = anchor.get("content", "")
    return content[:80] if content else ""


# ---------------------------------------------------------------------------
# 调用真实检索节点
# ---------------------------------------------------------------------------
def _retrieve(component: str, query: str, item_names: Optional[List[str]]):
    state = {"rewritten_query": query, "item_names": item_names or []}
    if component == "embedding":
        from processor.query_processor.nodes.node_search_embedding import NodeSearchEmbedding
        out = NodeSearchEmbedding().process(state)
        return out.get("embedding_chunks", [])
    elif component == "hyde":
        from processor.query_processor.nodes.node_search_embedding_hyde import NodeSearchEmbeddingHyde
        out = NodeSearchEmbeddingHyde().process(state)
        return out.get("hyde_embedding_chunks", [])
    raise ValueError(f"未知 component: {component}")


# ---------------------------------------------------------------------------
# 单条评测
# ---------------------------------------------------------------------------
def _run_single(component: str, anchor: Dict, topk: int = 5) -> Dict:
    query = _build_query(anchor)
    anchor_id = str(anchor.get("chunk_id"))
    anchor_item = anchor.get("item_name", "") or ""

    t0 = time.time()
    try:
        chunks = _retrieve(component, query, [anchor_item] if anchor_item else None)
        latency = time.time() - t0
    except Exception as e:
        return {
            "chunk_id": anchor_id,
            "item_name": anchor_item,
            "query": query,
            "status": "failed",
            "error": str(e),
            "latency": round(time.time() - t0, 3),
            "recalled_count": 0,
            "self_recall@5": float("nan"),
            "item_recall@5": float("nan"),
            "mrr@5": float("nan"),
        }

    recalled_ids = [str(c.get("chunk_id")) for c in chunks[:topk]]
    # 过滤掉空/None 的 item_name，避免 str(None)="None" 污染集合
    recalled_items = set(
        str(c.get("item_name")).strip()
        for c in chunks[:topk]
        if c.get("item_name")
    )

    # self_recall：锚点自身是否被召回
    self_hit = anchor_id in recalled_ids
    # item_recall：是否召回了同 item_name 的任意切片
    item_hit = (anchor_item in recalled_items) if anchor_item else False
    # MRR：锚点自身在结果中的最前排名
    mrr = metrics.mrr_at_k(recalled_ids, [anchor_id], k=topk)

    return {
        "chunk_id": anchor_id,
        "item_name": anchor_item,
        "query": query,
        "status": "ok",
        "latency": round(latency, 3),
        "recalled_count": len(chunks),
        "recalled_ids": recalled_ids,
        "self_recall@5": 1.0 if self_hit else 0.0,
        "item_recall@5": 1.0 if item_hit else 0.0,
        "mrr@5": mrr,
    }


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def run_retrieval_eval(component: str = "embedding",
                       sample_size: int = 5,
                       topk: int = 5,
                       expr: Optional[str] = None,
                       report_path: Optional[str] = None,
                       resume: bool = True,
                       queries_map: Optional[Dict] = None) -> Dict:
    """
    运行向量检索召回评测。
    :param component: "embedding" 或 "hyde"
    :param sample_size: 锚点采样条数
    :param topk: Recall@K 的 K
    :param expr: Milvus 过滤表达式（可选，按商品/条件采样）
    :param report_path: 报告输出路径
    :param resume: 是否启用断融
    :param queries_map: 可选，{chunk_id: 自然问题} 映射。提供时用它替代切片原文构造查询，
        避免"用原文自证"导致的召回虚高，更贴近真实业务查询。
    """
    from ..runner import run_batch

    anchors = _sample_anchors(sample_size=sample_size, expr=expr)
    if not anchors:
        print("[retrieval] Milvus 无可用锚点切片，无法评测。")
        return {"meta": {"component": component, "error": "no_anchors"}}

    # 断融快照路径（按 component 区分）
    snapshot_path = _snapshot_path_for(component)

    queries_map = queries_map or {}
    # 用 chunk_id 作为断融主键
    def _to_query_item(a: Dict) -> Dict:
        cid = str(a.get("chunk_id"))
        # 优先用数据集标注的自然问题；否则回退切片原文（自证偏置）
        nat_q = queries_map.get(cid)
        if nat_q:
            a = {**a, "query": nat_q}
        return {"query": _build_query(a), "chunk_id": cid,
                "item_name": a.get("item_name", "")}

    anchors_with_query = [_to_query_item(a) for a in anchors]

    def _run_one(q: Dict) -> Dict:
        anchor = {"chunk_id": q["chunk_id"], "content": q["query"], "item_name": q["item_name"]}
        r = _run_single(component, anchor, topk=topk)
        # 确保结果含 chunk_id 主键，且 query 字段保留便于断点
        return {**r, "chunk_id": q["chunk_id"], "query": r.get("query", "")}

    def _aggregate(results, meta):
        ok = [r for r in results if r.get("status") == "ok"]
        report = {
            "metrics": {
                "self_recall@k": metrics.safe_mean([r["self_recall@5"] for r in ok]),
                "item_recall@k": metrics.safe_mean([r["item_recall@5"] for r in ok]),
                "mrr@k": metrics.safe_mean([r["mrr@5"] for r in ok]),
                "avg_recalled_count": round(sum(r["recalled_count"] for r in ok) / len(ok), 2) if ok else 0.0,
            },
            "latency": metrics.latency_stats(
                [r["latency"] for r in ok if r.get("latency") is not None]),
            "samples": results,
        }
        return report

    def _log(r) -> str:
        return (f"{r['status']} | self_recall@5={metrics.fmt_score(r.get('self_recall@5'))} "
                f"item_recall@5={metrics.fmt_score(r.get('item_recall@5'))} "
                f"mrr@5={metrics.fmt_score(r.get('mrr@5'))} | {r.get('chunk_id', '')}")

    report = run_batch(
        component=f"retrieval/{component}",
        items=anchors_with_query,
        run_one=_run_one,
        snapshot_path=snapshot_path,
        report_path=report_path,
        aggregate=_aggregate,
        resume=resume,
        sleep_secs=0.3,
        log_line=_log,
        id_key="chunk_id",
    )
    # 补充 retrieval 特有 meta 字段
    report["meta"]["total_anchors"] = len(anchors_with_query)
    report["meta"]["topk"] = topk
    report["meta"]["component"] = component
    return report


def _snapshot_path_for(component: str) -> str:
    if component == "hyde":
        return config.hyde_snapshot_path
    return config.embedding_snapshot_path
