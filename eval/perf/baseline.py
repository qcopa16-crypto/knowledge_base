"""
性能基线判定与优化目标。

把压测聚合出的整体指标（overall）与预设基线阈值比对，输出 PASS / WARN / FAIL 判定。

基线分为三类：
1. 容量（capacity）  ：吞吐是否达到目标（QPS），衡量系统吞吐能力
2. 稳定性（stability）：错误率与抖动是否在可接受范围，衡量系统可靠性
3. 峰值（peak）      ：P99 延迟是否在预算内，衡量极端延迟表现

阈值支持绝对阈值 + 相对提升两种：
- 绝对阈值：直接与实测值比较（如 P99 <= 5.0s）
- 相对提升：与历史基线对比，要求改善/不劣化（如延迟相对上版本不劣化超过 X%）

判定规则：每项单项判定取最差作为最终 verdict。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BaselineThreshold:
    """单项基线阈值。"""
    key: str                      # overall 中的指标键，如 "p99" / "error_rate"
    max_value: Optional[float] = None   # 上限（低于该值 PASS），如延迟/错误率
    min_value: Optional[float] = None   # 下限（高于该值 PASS），如吞吐
    warn_scale: float = 1.5       # 阈值放大到 WARN 的比例（如 P99=5s，WARN 到 7.5s）
    label: str = ""               # 显示名


@dataclass
class BaselineConfig:
    """三类性能基线配置。"""
    capacity: List[BaselineThreshold] = field(default_factory=lambda: [
        BaselineThreshold(key="throughput_req_s", min_value=1.0,
                          label="吞吐(QPS) 下限"),
    ])
    stability: List[BaselineThreshold] = field(default_factory=lambda: [
        BaselineThreshold(key="error_rate", max_value=0.02, warn_scale=3.0,
                          label="错误率 上限(2%)"),
        BaselineThreshold(key="apde", max_value=0.5, warn_scale=2.0,
                          label="延迟抖动 APDE 上限"),
    ])
    peak: List[BaselineThreshold] = field(default_factory=lambda: [
        BaselineThreshold(key="p99", max_value=5.0, warn_scale=1.5,
                          label="P99 延迟上限(5s)"),
    ])


def _judge_single(threshold: BaselineThreshold, value: Optional[float]) -> str:
    """对单项返回 PASS / WARN / FAIL。"""
    if value is None:
        return "N/A"
    if threshold.min_value is not None:
        # 下限型（吞吐）：低于则失败
        if value < threshold.min_value:
            return "FAIL"
        if value < threshold.min_value * threshold.warn_scale * 0.8:
            # 接近下限视为 WARN（简化：低于下限即 FAIL，不再细分）
            pass
        return "PASS"
    if threshold.max_value is not None:
        # 上限型（延迟/错误率）：高于则失败，超过 warn_scale 边界内视为 WARN
        warn_bound = threshold.max_value * threshold.warn_scale
        if value > warn_bound:
            return "FAIL"
        if value > threshold.max_value:
            return "WARN"
        return "PASS"
    return "PASS"


def evaluate_overall(overall: Dict,
                     baseline: Optional[BaselineConfig] = None) -> Dict:
    """
    对整体指标做三类基线判定。

    :param overall: perf_stats 返回的整体指标 dict
    :param baseline: 基线配置；None 使用默认
    :return: {capacity: {...}, stability: {...}, peak: {...}, verdict: "PASS"/"WARN"/"FAIL"}
    """
    baseline = baseline or BaselineConfig()
    verdicts = []

    def _eval_group(name: str, thresholds: List[BaselineThreshold]) -> Dict:
        nonlocal verdicts
        items = {}
        for t in thresholds:
            v = overall.get(t.key)
            j = _judge_single(t, v)
            items[t.key] = {"value": v, "verdict": j, "label": t.label}
            if j in ("FAIL", "WARN"):
                verdicts.append(j)
        return items

    result = {
        "capacity": _eval_group("capacity", baseline.capacity),
        "stability": _eval_group("stability", baseline.stability),
        "peak": _eval_group("peak", baseline.peak),
    }

    if "FAIL" in verdicts:
        result["verdict"] = "FAIL"
    elif "WARN" in verdicts:
        result["verdict"] = "WARN"
    else:
        result["verdict"] = "PASS"
    return result


# ---- 相对提升（优化目标追踪） ----
def relative_gain(current: Dict, previous: Optional[Dict],
                  latency_keys: Optional[List[str]] = None) -> Dict:
    """
    对比历史基线，计算相对变化（相对提升/劣化）。

    :param current: 本次整体指标
    :param previous: 历史整体指标；None 表示无历史
    :param latency_keys: 延迟键（越小越好，计算劣化率）；默认常用延迟键
    :return: {key: {"current": x, "previous": y, "delta_pct": z}}，z>0 表示劣化
    """
    if previous is None:
        return {}
    keys = latency_keys or ["avg", "p50", "p95", "p99", "error_rate", "apde"]
    out = {}
    for k in keys:
        c = current.get(k)
        p = previous.get(k)
        if c is None or p is None or p == 0:
            continue
        out[k] = {
            "current": round(c, 4),
            "previous": round(p, 4),
            "delta_pct": round((c - p) / p * 100.0, 2),  # 正值=劣化
        }
    return out
