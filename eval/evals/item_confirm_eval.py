"""
商品名确认（item_name_confirm）组件评测。

被测对象：processor.query_processor.nodes.node_item_name_confirm.NodeItemNameConfirm

评估方法（白盒，直接调用被测节点真实 process）：
- 构造用例集，每条含：
    original_query        用户问题
    expected_item_names   期望识别出的商品名列表（可空）
    expected_branch       期望分支：confirm(确认)/ask(反问)/reject(拒答)
- 用隔离的随机 session_id 调用真实 process（避免污染真实会话历史）。
- 评估：
    item_hit_rate         实际确认/识别的商品名与期望的重叠度
    branch_acc            实际触发的分支与期望分支是否一致

需要：真实 Milvus（kb_item_names 商品名库）+ LLM + MongoDB（会写入隔离会话历史）。

注意：process 会真实写 MongoDB（隔离 session 下），评测结束后可自行清理隔离会话。
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Dict, List, Optional, Sequence

from .. import metrics
from .. import snapshot
from ..eva_config import config


# ---------------------------------------------------------------------------
# 内置用例集
# ---------------------------------------------------------------------------
def _default_cases() -> List[Dict]:
    """内置用例，覆盖商品确认的三种分支：
    - confirm: 商品名清晰，直接确认，进入后续检索
    - ask:     商品名模糊/有多个候选，反问用户明确型号
    - reject:  库中无匹配商品，拒答
    默认只测前 1 条（confirm）；传 limit=3 可覆盖全部分支。
    """
    return [
        {
            "original_query": "HAK180烫金机怎么调节转印温度？",
            "expected_item_names": ["HAK180烫金机"],
            "expected_branch": "confirm",  # 商品名清晰，应直接确认
        },
        {
            "original_query": "华为MateBook怎么选配置？",
            "expected_item_names": [],
            "expected_branch": "ask",  # 商品名不够唯一（库中有多个型号），应反问明确型号
        },
        {
            "original_query": "今天天气怎么样？",
            "expected_item_names": [],
            "expected_branch": "reject",  # 与库中商品无关，应拒答
        },
    ]


# ---------------------------------------------------------------------------
# 单条评测
# ---------------------------------------------------------------------------
def _run_single(case: Dict) -> Dict:
    from processor.query_processor.nodes.node_item_name_confirm import NodeItemNameConfirm

    original_query = case.get("original_query", "")
    expected_names = set(case.get("expected_item_names", []) or [])
    expected_branch = case.get("expected_branch", "")

    # 用隔离的 session_id，避免污染真实会话
    session_id = "eva_item_" + uuid.uuid4().hex

    state = {"session_id": session_id, "original_query": original_query}

    t0 = time.time()
    try:
        result_state = NodeItemNameConfirm().process(state)
        latency = time.time() - t0
    except Exception as e:
        return {
            "original_query": original_query,
            "status": "failed",
            "error": str(e),
            "latency": round(time.time() - t0, 3),
            "item_names": [],
            "answer": "",
            "item_hit": float("nan"),
            "branch_acc": float("nan"),
        }

    item_names = result_state.get("item_names", []) or []
    answer = result_state.get("answer", "") or ""
    rewritten_query = result_state.get("rewritten_query", "")

    # 判定分支（贴合 NodeItemNameConfirm.process 的真实逻辑）：
    #   分支A confirm：item_names 非空 且 answer 为空（可直接进入检索）
    #   分支B ask    ：answer 非空且给出候选商品（"以下哪个产品...请明确"）
    #   分支C reject ：answer 非空且未找到匹配（"未找到相关产品"）
    # 用 item_names + answer 内容双重判断，替代脆弱的硬编码字符串匹配。
    if item_names and not answer:
        actual_branch = "confirm"
    elif "以下哪个产品" in answer and ("请明确" in answer):
        actual_branch = "ask"
    else:
        actual_branch = "reject"

    # 商品名命中率：用包含匹配（期望名与实际名互为子串即命中），更贴合业务
    # 例如查询"HAK180烫金机"，库中标准名"BrotherHAK180烫金机"，应判定命中
    combined_names = list(item_names) + actual_names_from_answer(answer)
    item_hit = 1.0 if _name_matches(expected_names, combined_names) else 0.0
    branch_acc = 1.0 if actual_branch == expected_branch else 0.0

    return {
        "original_query": original_query,
        "session_id": session_id,
        "status": "ok",
        "latency": round(latency, 3),
        "item_names": list(item_names),
        "rewritten_query": rewritten_query,
        "answer": answer,
        "actual_branch": actual_branch,
        "expected_branch": expected_branch,
        "item_hit": item_hit,
        "branch_acc": branch_acc,
    }


def _name_matches(expected: set, actual: list) -> bool:
    """
    判断实际商品名是否匹配期望集合（任一期望名与实际名互为子串即命中）。
    同时去掉常见品牌前缀/空格差异，增强容错。
    """
    for exp in expected:
        exp_norm = exp.replace(" ", "").lower()
        for act in actual:
            act_norm = (act or "").replace(" ", "").lower()
            if act_norm and (exp_norm in act_norm or act_norm in exp_norm):
                return True
    return False


def actual_names_from_answer(answer: str) -> List[str]:
    """从反问 answer 文本中粗略提取候选商品名（用于与期望比对）。"""
    if "请明确一下型号" not in answer:
        return []
    # 提取 "您是想问以下哪个产品：xxx？" 中的 xxx
    start = answer.find("以下哪个产品：")
    if start == -1:
        return []
    rest = answer[start + len("以下哪个产品："):]
    end = rest.find("？")
    names = rest[:end] if end != -1 else rest
    return [n.strip() for n in names.split("、") if n.strip()]


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def run_item_confirm_eval(cases: Optional[Sequence[Dict]] = None,
                          limit: int = 1,
                          report_path: Optional[str] = None,
                          resume: bool = True) -> Dict:
    """
    运行商品确认评测。
    :param cases: 用例集；None 使用内置
    :param limit: 只评测前 N 条（默认 1）
    :param report_path: 报告输出路径
    :param resume: 是否启用断融
    """
    cases = list(cases) if cases is not None else _default_cases()
    if limit and limit > 0:
        cases = cases[:limit]

    from ..runner import run_batch

    # 断点主键用 复合键 original_query::expected_branch，作为每个 case 的 query 字段
    for c in cases:
        c.setdefault("query", f"{c.get('original_query', '')}::{c.get('expected_branch', '')}")

    def _run_one(c: Dict) -> Dict:
        r = _run_single(c)
        # 确保结果含断点主键（query = 复合键）
        return {**r, "query": c.get("query", ""), "original_query": c.get("original_query", "")}

    def _aggregate(results, meta):
        ok = [r for r in results if r.get("status") == "ok"]
        report = {
            "metrics": {
                "item_hit_rate": metrics.safe_mean([r["item_hit"] for r in ok]),
                "branch_acc": metrics.safe_mean([r["branch_acc"] for r in ok]),
            },
            "latency": metrics.latency_stats(
                [r["latency"] for r in ok if r.get("latency") is not None]),
            "samples": results,
        }
        return report

    def _log(r) -> str:
        return (f"{r['status']} | branch={r.get('actual_branch')}(exp:{r.get('expected_branch')}) "
                f"item_hit={metrics.fmt_score(r.get('item_hit'))} | {r.get('original_query', '')[:30]}")

    report = run_batch(
        component="item_confirm",
        items=cases,
        run_one=_run_one,
        snapshot_path=config.item_confirm_snapshot_path,
        report_path=report_path,
        aggregate=_aggregate,
        resume=resume,
        sleep_secs=0.5,
        log_line=_log,
    )
    report["meta"]["component"] = "item_name_confirm"
    return report
