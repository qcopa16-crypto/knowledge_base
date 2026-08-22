"""
压测报告生成与落盘。

将 summarize_stages 的结果 + 可选基线判定写入 JSON 报告，风格复用 runner 落盘模式。
基线判定由 baseline.py 提供；report 仅负责组装与写盘。
"""
from __future__ import annotations

import json
import os
import time
from typing import Dict, List, Optional


def write_report(report: Dict, report_path: Optional[str] = None) -> str:
    """
    将压测报告写入 JSON 文件。
    :param report: 报告字典（含 meta/overall/stages/baseline 等）
    :param report_path: 输出路径；None 则仅返回但不落盘
    :return: 实际写入路径（未落盘返回空串）
    """
    report.setdefault("meta", {}).setdefault("timestamp", time.strftime("%Y-%m-%d %H:%M:%S"))
    if not report_path:
        return ""
    os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report_path


def build_report(summary: Dict,
                 baseline_result: Optional[Dict] = None,
                 config_info: Optional[Dict] = None) -> Dict:
    """组装完整压测报告字典。"""
    meta = dict(summary.get("meta", {}))
    meta.setdefault("timestamp", time.strftime("%Y-%m-%d %H:%M:%S"))
    report = {
        "meta": meta,
        "overall": summary.get("overall", {}),
        "stages": summary.get("stages", []),
        "quality": summary.get("quality", {}),
        "baseline": baseline_result or {},
        "config": config_info or {},
    }
    return report
