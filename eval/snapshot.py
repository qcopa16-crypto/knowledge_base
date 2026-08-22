"""
断融（断点续跑）机制：
在评测逐条落盘，中断后重跑时跳过已完成条目，避免重复调用云上服务、重复扣费、重复耗时。

快照文件格式（JSON）：
{
  "done": [ {query: {...result...}}, ... ],   # 已完成条目（按顺序）
  "meta": { "component": "eva|rerank", ... }
}

以 query 作为去重主键。新增一条即整体重写快照文件（评测条目量级小，可接受）。
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional


def load_snapshot(path: str) -> Dict[str, dict]:
    """
    读取断点快照，返回 {query: result} 映射。
    文件不存在或非法时返回空 dict。
    """
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        done = data.get("done", [])
        return {item.get("query"): item for item in done if isinstance(item, dict) and item.get("query")}
    except (json.JSONDecodeError, OSError):
        return {}


def save_snapshot(path: str, results: List[Dict], meta: Optional[Dict] = None) -> None:
    """
    将已完成结果列表整体写入断点快照文件。
    :param path: 快照文件路径
    :param results: 已完成的结果列表（每条含 query 字段）
    :param meta: 附加元信息
    """
    if not path:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "meta": meta or {},
        "done": results,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def clear_snapshot(path: str) -> None:
    """删除断点快照（--fresh 时调用）。"""
    if path and os.path.exists(path):
        os.remove(path)


def filter_new_queries(dataset: List[Dict], snapshot: Dict[str, dict]) -> tuple:
    """
    根据断点快照拆分数据集。
    :return: (待评测项, 已完成项) 两个列表。
    """
    todo, done = [], []
    for item in dataset:
        q = item.get("query")
        if q and q in snapshot:
            done.append(snapshot[q])
        else:
            todo.append(item)
    return todo, done
