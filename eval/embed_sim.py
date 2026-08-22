"""
可选语义相似度适配器：复用业务侧的 BGE-M3 模型生成向量，供答案语义相似度指标使用。
若业务模型未就绪或依赖缺失，会自动跳过（semantic_sim 记为 N/A），不影响其它指标。
"""
from __future__ import annotations

from typing import Optional, Callable


def build_semantic_fn() -> Optional[Callable[[str], list]]:
    """尝试构建单文本 -> 稠密向量的函数；失败返回 None。"""
    try:
        from utils.embedding_utils import get_bge_m3_ef
        ef = get_bge_m3_ef()
    except Exception:
        return None

    def _embed(text: str) -> list:
        try:
            out = ef.encode_documents([text])
            return out["dense"][0].tolist()
        except Exception:
            return []

    return _embed


def try_enable_semantic():
    """在评测前尝试注入语义相似度函数。"""
    fn = build_semantic_fn()
    if fn is None:
        print("[eva] 未启用语义相似度（BGE 模型不可用），semantic_sim 记为 N/A")
        return
    from . import metrics
    metrics.set_embedding_fn(fn)
    print("[eva] 已启用语义相似度（复用 BGE-M3）")
