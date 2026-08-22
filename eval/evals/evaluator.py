"""
评测执行器：针对被测知识库的 /query 接口发起非流式查询，评估检索与问答质量。

单条流程：
1. POST {query_api_base}/query  {query, session_id, is_stream:false}
2. 从响应取 answer（同步模式直接返回）
3. 若数据集中标注了 expected_chunk_ids，则通过 /history 回溯当前会话，取检索命中的相关文档做命中判定
   （注意：业务接口不直接暴露“检索到的chunk_id”，因此命中判定改为基于 answer 文本与期望内容的语义/文本匹配，
    或依赖历史会话中的 item_names 与 reference 的相关性，作为代理指标。）
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Dict, List, Optional, Sequence

import requests

from ..eva_config import config
from .. import metrics
from .. import snapshot


def _call_query(query: str, session_id: str, timeout: float,
                switches: Optional[Dict] = None) -> Dict:
    """调用非流式 /query 接口，返回后端 JSON。

    :param switches: 检索路开关，如 {"enable_hyde": False}；None 表示全开。
    """
    payload = {"query": query, "session_id": session_id, "is_stream": False}
    if switches:
        payload.update(switches)
    resp = requests.post(config.query_url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _fetch_history(session_id: str, limit: int = 20) -> List[Dict]:
    """拉取会话历史，用于核对关联商品名/答案。"""
    url = f"{config.query_api_base}/history/{session_id}?limit={limit}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("items", [])
    except Exception:
        pass
    return []


def _history_item_names(session_id: str) -> List[str]:
    """从历史中提取本次会话被确认/关联的商品名。"""
    names: List[str] = []
    for it in _fetch_history(session_id):
        for n in (it.get("item_names") or []):
            if n and n not in names:
                names.append(n)
    return names


def evaluate_sample(sample: Dict, switches: Optional[Dict] = None) -> Dict:
    """
    评测单条样本，返回指标字典。
    无 reference / expected_chunk_ids 的样本自动跳过相应指标（记 NaN）。

    :param switches: 检索路开关，如 {"enable_hyde": False}；None 表示全开。
    """
    query = sample.get("query", "")
    reference = sample.get("reference", "")
    expected_ids = sample.get("expected_chunk_ids", []) or []
    expected_item = sample.get("item_name", "")

    session_id = "eva_" + uuid.uuid4().hex
    t0 = time.time()
    try:
        result = _call_query(query, session_id, timeout=config.timeouts, switches=switches)
        latency = time.time() - t0
    except Exception as e:
        return {
            "query": query,
            "status": "failed",
            "error": str(e),
            "latency": time.time() - t0,
            "answer": "",
            "rouge_l": float("nan"),
            "bleu": float("nan"),
            "semantic_sim": float("nan"),
            "retrieval_hit": float("nan"),
            "item_name_hit": float("nan"),
        }

    answer = result.get("answer", "") or ""
    status = result.get("message", "ok")

    # ---- 检索命中（代理）：期望商品是否被会话关联/答案是否提到 ----
    item_names_now = _history_item_names(session_id)
    item_name_hit = float("nan")
    if expected_item:
        hit = any(expected_item in n or n in expected_item for n in item_names_now)
        item_name_hit = 1.0 if hit else 0.0

    # ---- 检索命中（代理）：期望切片内容是否出现在答案上下文 ----
    retrieval_hit = float("nan")
    if expected_ids and sample.get("source_content"):
        # 简化判定：答案或会话历史里是否出现期望切片的代表性片段
        snippet = (sample.get("source_content") or "")[:80].strip()
        if snippet:
            combined = answer + "".join(it.get("text", "") for it in _fetch_history(session_id))
            retrieval_hit = 1.0 if snippet in combined else 0.0

    # ---- 问答质量 ----
    if reference:
        rouge = metrics.rouge_l_f1(reference, answer)
        bleu = metrics.bleu(reference, answer)
        sem = metrics.semantic_similarity(reference, answer)
    else:
        rouge = bleu = sem = float("nan")

    return {
        "query": query,
        "status": status,
        "latency": round(latency, 3),
        "answer": answer,
        "reference": reference,
        "rouge_l": rouge,
        "bleu": bleu,
        "semantic_sim": sem,
        "retrieval_hit": retrieval_hit,
        "item_name_hit": item_name_hit,
    }


def run_evaluation(dataset: Sequence[Dict],
                   sample_count: Optional[int] = None,
                   report_path: Optional[str] = None,
                   resume: bool = True) -> Dict:
    """
    批量评测整个数据集，聚合指标并写报告。

    断融机制（由公共框架 runner.run_batch 提供）：
    - 逐条评测完成后立即写入断点快照（config.eva_snapshot_path），中断后重跑可跳过已完成条目。
    - resume=True 时读取快照跳过已完成；resume=False（或快照文件不存在）时从第一条开始。
    - 连续失败达到阈值自动熔断。
    """
    from ..runner import run_batch

    items = list(dataset)
    if sample_count is not None:
        items = items[:sample_count]

    def _aggregate(results, meta):
        latencies = [r["latency"] for r in results if r.get("latency") is not None]
        answer_samples = [r for r in results if not _is_nan(r.get("rouge_l"))]
        retrieval_samples = [r for r in results if not _is_nan(r.get("retrieval_hit"))]
        item_samples = [r for r in results if not _is_nan(r.get("item_name_hit"))]
        report = {
            "latency": metrics.latency_stats(latencies),
            "answer_quality": {
                "rouge_l": metrics.safe_mean([r["rouge_l"] for r in answer_samples]),
                "bleu": metrics.safe_mean([r["bleu"] for r in answer_samples]),
                "semantic_sim": metrics.safe_mean([r["semantic_sim"] for r in answer_samples]),
            },
            "retrieval": {
                "retrieval_hit_rate": metrics.safe_mean([r["retrieval_hit"] for r in retrieval_samples]),
                "item_name_hit_rate": metrics.safe_mean([r["item_name_hit"] for r in item_samples]),
            },
            "samples": results,
        }
        return report

    def _log(r) -> str:
        return (f"{r['status']} | rouge={_fmt(r.get('rouge_l'))} bleu={_fmt(r.get('bleu'))} "
                f"hit={_fmt(r.get('retrieval_hit'))} | {r.get('query', '')[:40]}")

    return run_batch(
        component="eva",
        items=items,
        run_one=evaluate_sample,
        snapshot_path=config.eva_snapshot_path,
        report_path=report_path or config.report_path,
        aggregate=_aggregate,
        resume=resume,
        sleep_secs=0.2,
        log_line=_log,
    )


def _fmt(v) -> str:
    return "N/A" if _is_nan(v) else f"{v:.3f}"


def _is_nan(v) -> bool:
    return v is None or (isinstance(v, float) and v != v)
