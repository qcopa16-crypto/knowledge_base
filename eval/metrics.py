"""
评测指标计算：
- 问答质量：ROUGE-L、BLEU、基于 Embedding 的语义相似度
- 检索质量：期望命中召回率（当数据集中标注了应命中的文档ID/商品名时）
- 性能：延迟统计
指标实现尽量少依赖，纯标准库 + numpy；语义相似度可选复用业务 BGE 模型。
"""
from __future__ import annotations

import re
import time
import statistics
from typing import List, Dict, Optional, Sequence

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


# ---------------------------------------------------------------------------
# 文本预处理
# ---------------------------------------------------------------------------
def _tokenize(text: str) -> List[str]:
    """中英文混合切词：英文按词、中文按单字，简单鲁棒。"""
    text = (text or "").lower().strip()
    # 中文单字 + 英文/数字词
    tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", text)
    return tokens


# ---------------------------------------------------------------------------
# ROUGE-L（基于最长公共子序列的召回率/精确率/F1）
# ---------------------------------------------------------------------------
def _lcs_len(a: List[str], b: List[str]) -> int:
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[n][m]


def rouge_l_f1(reference: str, candidate: str) -> float:
    """ROUGE-L F1，用于生成答案与参考答案的匹配度。"""
    ref = _tokenize(reference)
    cand = _tokenize(candidate)
    if not ref or not cand:
        return 0.0
    lcs = _lcs_len(ref, cand)
    recall = lcs / len(ref)
    precision = lcs / len(cand)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


# ---------------------------------------------------------------------------
# BLEU-1/2（简版 n-gram 精确率，带长度惩罚）
# ---------------------------------------------------------------------------
def _n_grams(tokens: List[str], n: int):
    return [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def bleu(reference: str, candidate: str, max_n: int = 2) -> float:
    """简版 BLEU-N，返回 0~1。用于答案相关性粗评估。"""
    ref = _tokenize(reference)
    cand = _tokenize(candidate)
    if not ref or not cand:
        return 0.0
    # 长度惩罚：候选过短时惩罚
    bp = min(1.0, len(ref) / len(cand)) if len(cand) > 0 else 0.0
    precisions = []
    for n in range(1, max_n + 1):
        ref_ng = _n_grams(ref, n)
        cand_ng = _n_grams(cand, n)
        if not cand_ng:
            precisions.append(0.0)
            continue
        ref_count: Dict = {}
        for g in ref_ng:
            ref_count[g] = ref_count.get(g, 0) + 1
        matches = 0
        cand_count: Dict = {}
        for g in cand_ng:
            if ref_count.get(g, 0) > cand_count.get(g, 0):
                matches += 1
            cand_count[g] = cand_count.get(g, 0) + 1
        precisions.append(matches / len(cand_ng))
    if not precisions:
        return 0.0
    geo = 1.0
    for p in precisions:
        geo *= max(p, 1e-9)
    geo = geo ** (1.0 / len(precisions))
    return geo * bp


# ---------------------------------------------------------------------------
# 语义相似度（可选：复用业务 BGE-M3 模型）
# ---------------------------------------------------------------------------
_embedding_fn = None


def set_embedding_fn(fn):
    """注入语义相似度计算函数，签名：fn(text: str) -> List[float]。"""
    global _embedding_fn
    _embedding_fn = fn


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if np is None:
        return 0.0
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def semantic_similarity(reference: str, candidate: str) -> float:
    """基于注入的 embedding 函数计算语义余弦相似度。未注入时返回 0.0。"""
    if _embedding_fn is None:
        return 0.0
    try:
        return _cosine(_embedding_fn(reference), _embedding_fn(candidate))
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# 检索命中率（数据集标注了应命中 chunk_id / item_name 时）
# ---------------------------------------------------------------------------
def retrieval_hit(ground_truth_ids: Optional[Sequence],
                  retrieved_ids: Optional[Sequence]) -> float:
    """返回 1.0（命中）或 0.0（未命中）。ground_truth_ids 为空时不参与统计。"""
    if not ground_truth_ids:
        return float("nan")  # 无标注，跳过
    gt = {str(x) for x in ground_truth_ids}
    rt = {str(x) for x in (retrieved_ids or [])}
    return 1.0 if gt & rt else 0.0


# ---------------------------------------------------------------------------
# 延迟统计
# ---------------------------------------------------------------------------
def latency_stats(latencies: Sequence[float]) -> Dict[str, float]:
    if not latencies:
        return {"avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0, "count": 0}
    s = sorted(latencies)
    return {
        "avg": round(statistics.mean(s), 3),
        "p50": round(s[min(len(s) - 1, int(len(s) * 0.50))], 3),
        "p95": round(s[min(len(s) - 1, int(len(s) * 0.95))], 3),
        "max": round(s[-1], 3),
        "count": len(s),
    }


# ---------------------------------------------------------------------------
# 排序质量指标（用于 RRF / Rerank 组件评测）
# ---------------------------------------------------------------------------
def _dcg_at_k(relevance: Sequence[float], k: int) -> float:
    """DCG@K：relevance[i] 是第 i+1 位的相关性分值（0/1 或连续）。"""
    if np is None:
        # 无 numpy 时用纯 Python 实现
        s = 0.0
        for i, rel in enumerate(relevance[:k]):
            s += rel / (i + 2.0)  # log2(i+2)
        return s
    rel = np.asarray(relevance[:k], dtype=float)
    pos = np.log2(np.arange(1, len(rel) + 1) + 1.0)
    return float(np.sum(rel / pos))


def ndcg_at_k(ranked_items: Sequence,
              relevant: Sequence,
              k: Optional[int] = None,
              key: Optional[callable] = None) -> float:
    """
    计算 NDCG@K。
    :param ranked_items: 模型排好序的条目列表（score 降序）
    :param relevant: 相关的条目集合（ground truth）
    :param k: 截断位置；None 取全部
    :param key: 从条目中取标识的函数；None 则条目本身即标识
    :return: 0~1 的 NDCG
    """
    k = k if k is not None else len(ranked_items)
    if k <= 0 or not ranked_items:
        return 0.0
    rel_map = {x: 1.0 for x in relevant}
    get_id = key or (lambda x: x)
    # 每个条目的相关性（0/1）
    rels = [rel_map.get(get_id(item), 0.0) for item in ranked_items[:k]]
    if not any(rels):
        return 0.0
    ideal = sorted((rel_map.get(get_id(x), 0.0) for x in ranked_items), reverse=True)[:k]
    dcg = _dcg_at_k(rels, k)
    idcg = _dcg_at_k(ideal, k)
    return 0.0 if idcg == 0 else float(dcg / idcg)


def mrr_at_k(ranked_items: Sequence,
             relevant: Sequence,
             k: Optional[int] = None,
             key: Optional[callable] = None) -> float:
    """
    计算 MRR@K：第一个相关条目在排名中的倒数。
    :param ranked_items: 模型排好序的条目列表
    :param relevant: 相关条目集合
    :param k: 只在排名前 k 内查找；None 取全部
    :param key: 取条目标识的函数
    :return: 0~1
    """
    get_id = key or (lambda x: x)
    rel_set = set(relevant)
    limit = k if k is not None else len(ranked_items)
    for i, item in enumerate(ranked_items[:limit]):
        if get_id(item) in rel_set:
            return 1.0 / (i + 1)
    return 0.0


def precision_at_k(ranked_items: Sequence,
                   relevant: Sequence,
                   k: int,
                   key: Optional[callable] = None) -> float:
    """P@K：前 K 条中相关条目的占比。"""
    if k <= 0:
        return 0.0
    get_id = key or (lambda x: x)
    rel_set = set(relevant)
    hits = sum(1 for item in ranked_items[:k] if get_id(item) in rel_set)
    return hits / min(k, len(ranked_items)) if ranked_items else 0.0


# ---------------------------------------------------------------------------
# 聚合工具
# ---------------------------------------------------------------------------
def safe_mean(values: Sequence[float]) -> float:
    vals = [v for v in values if v == v]  # 过滤 NaN
    if not vals:
        return 0.0
    return round(sum(vals) / len(vals), 4)


def safe_avg(values: Sequence[float]) -> float:
    return safe_mean(values)


def is_nan(v) -> bool:
    """判断是否为 NaN（用于跳过无标注/失败的指标）。"""
    return v is None or (isinstance(v, float) and v != v)


def fmt_score(v) -> str:
    """格式化分数：NaN 显示 N/A，否则保留 3 位小数。"""
    return "N/A" if is_nan(v) else f"{v:.3f}"


# ---------------------------------------------------------------------------
# 性能指标（性能压测模块使用，向后兼容既有 latency_stats）
# ---------------------------------------------------------------------------
def _percentile(sorted_vals: Sequence[float], p: float) -> float:
    """
    在已升序序列上计算 p 分位数（0~1）。空序列返回 0.0。
    约定：返回排序后第 ceil(p * n) 个元素（1-based）。
    """
    if not sorted_vals:
        return 0.0
    n = len(sorted_vals)
    pos = max(1, min(n, int(p * n) + 1 if (p * n) % 1 else int(p * n)))
    return round(sorted_vals[pos - 1], 3)


def apde(sorted_latencies: Sequence[float], percentile: float = 0.9) -> float:
    """
    绝对百分位延迟误差（Absolute Percentile Deviation Error）：
    衡量延迟分布的稳定性/抖动。

    简化实现：基于相邻采样延迟差分的变异系数（标准差/均值）。
    - 延迟完全稳定（相邻差恒定）→ 返回 0
    - 延迟剧烈波动（差分变化大）→ 返回较大正值
    值越小表示延迟越稳定。
    """
    vals = sorted(sorted_latencies)
    if len(vals) < 3:
        return 0.0
    diffs = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    mean = sum(diffs) / len(diffs)
    if mean <= 0:
        # 相邻差分非正（单调非增或全相同）视为稳定
        return 0.0
    var = sum((d - mean) ** 2 for d in diffs) / len(diffs)
    std = var ** 0.5
    return round(std / mean, 4)


def perf_stats(latencies: Sequence[float],
               success_count: int,
               fail_count: int,
               duration_secs: float) -> Dict[str, float]:
    """
    计算完整的性能指标集合，供压测报告使用。

    :param latencies: 成功请求的端到端延迟（秒）列表
    :param success_count: 成功请求数
    :param fail_count: 失败请求数
    :param duration_secs: 压测实际持续时长（秒）
    :return: dict，含吞吐/延迟分布/错误率/抖动
    """
    s = sorted(latencies)
    total = success_count + fail_count
    error_rate = (fail_count / total) if total > 0 else 0.0
    throughput = (success_count / duration_secs) if duration_secs > 0 else 0.0

    return {
        "count": len(s),
        "avg": _safe_avg(s),
        "p50": _percentile(s, 0.50),
        "p95": _percentile(s, 0.95),
        "p99": _percentile(s, 0.99),
        "p999": _percentile(s, 0.999),
        "max": round(s[-1], 3) if s else 0.0,
        "throughput_req_s": round(throughput, 3),
        "error_rate": round(error_rate, 4),
        "success_count": success_count,
        "fail_count": fail_count,
        "apde": apde(s),
    }


def _safe_avg(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)
