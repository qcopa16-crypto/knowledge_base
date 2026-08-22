"""
MCP（百炼联网搜索）组件评测。

被测对象：processor.query_processor.nodes.node_web_search_mcp.NodeWebSearchMcp

评估方法（白盒，直接调用被测节点的真实 process 方法）：
- 构造一组查询（query）；
- 调用 NodeWebSearchMcp.process，触发真实 MCP 联网搜索（调用 utils.mcp_utils.mcp_call_client）；
- 评估返回结果：
   - 是否返回结构化 web_search_docs（title/url/snippet 齐全）；
   - 命中条数 / 平均耗时；
   - 是否含空结果（MCP 返回异常、json 解析失败等）。

需要配置：config/bailian_mcp_config.py 的 mcp_base_url 与 api_key，且有网络。
"""
from __future__ import annotations

import json
import time
from typing import Dict, List, Optional, Sequence

from .. import metrics
from .. import snapshot
from ..eva_config import config


def _default_queries() -> List[Dict]:
    """内置评测查询集。"""
    return [
        {"query": "brother HAK180烫金机 如何调节转印温度？"},
        {"query": "万用表 测量直流电压 方法"},
        {"query": "烫金机 常见故障 温度过高怎么办"},
    ]


def _run_single(query_item: Dict) -> Dict:
    """评测单条 MCP 查询。"""
    from processor.query_processor.nodes.node_web_search_mcp import NodeWebSearchMcp

    query = query_item.get("query", "")
    node = NodeWebSearchMcp()
    state = {"rewritten_query": query}

    t0 = time.time()
    try:
        result_state = node.process(state)
        latency = time.time() - t0
    except Exception as e:
        return {
            "query": query,
            "status": "failed",
            "error": str(e),
            "latency": round(time.time() - t0, 3),
            "result_count": 0,
            "field_ok": False,
        }

    docs = result_state.get("web_search_docs", [])
    status = "ok" if docs else "empty"

    # 校验字段完整性：每条须含 title/url/snippet 且非空
    field_ok = all(
        d.get("title") and d.get("url") and d.get("snippet")
        for d in docs
    ) if docs else False

    return {
        "query": query,
        "status": status,
        "latency": round(latency, 3),
        "result_count": len(docs),
        "field_ok": field_ok,
        "docs": docs,
    }


def run_mcp_eval(queries: Optional[Sequence[Dict]] = None,
                 report_path: Optional[str] = None,
                 resume: bool = True,
                 limit: Optional[int] = None) -> Dict:
    """
    运行 MCP 组件评测。
    :param queries: 评测查询集；None 使用内置
    :param report_path: 报告输出路径
    :param resume: 是否启用断融
    :param limit: 只评测前 N 条；None 表示全部
    """
    queries = list(queries) if queries is not None else _default_queries()
    if limit is not None and limit > 0:
        queries = queries[:limit]

    from ..runner import run_batch

    def _aggregate(results, meta):
        ok = [r for r in results if r.get("status") == "ok"]
        field_ok_count = sum(1 for r in ok if r.get("field_ok"))
        success_count = len(ok)
        report = {
            "metrics": {
                "success_rate": (success_count / len(results)) if results else 0.0,
                "field_completeness_rate": (field_ok_count / success_count) if success_count else 0.0,
                "avg_result_count": round(sum(r["result_count"] for r in ok) / success_count, 2) if success_count else 0.0,
            },
            "latency": metrics.latency_stats(
                [r["latency"] for r in ok if r.get("latency") is not None]),
            "samples": results,
        }
        return report

    def _log(r) -> str:
        return f"{r['status']} | count={r.get('result_count')} latency={r.get('latency')}s | {r.get('query', '')[:30]}"

    return run_batch(
        component="mcp",
        items=queries,
        run_one=_run_single,
        snapshot_path=config.mcp_snapshot_path,
        report_path=report_path,
        aggregate=_aggregate,
        resume=resume,
        sleep_secs=0.5,
        log_line=_log,
    )
