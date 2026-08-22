"""
性能压测配置：集中管理压测并发档位、持续时长、QPS 目标、轮询参数与超时阈值。

风格与 eval/eva_config.py 保持一致：dataclass + 环境变量覆盖，默认值可直接用于
独立测试环境（2 核 4GB）避免压垮被测服务。

注意：
- 本模块依赖 eva_config 提供被测服务地址（query_url / query_api_base）。
- 所有阈值均为"合理基线"而非硬性指标，可在 baseline.py 中按环境调整。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class PerfConfig:
    # ---- 被测服务（复用 eva_config 的连接，但允许独立覆盖便于压测环境隔离） ----
    query_api_base: str = os.getenv(
        "PERF_QUERY_API_BASE", os.getenv("EVA_QUERY_API_BASE", "http://127.0.0.1:8080"))

    # ---- 负载档位：依次执行的并发数阶梯 ----
    # 每个元组 (并发数, 持续时长秒)
    concurrency_stages: List[Tuple[int, int]] = field(default_factory=lambda: [
        (1, 5),    # 单用户基线：纯延迟基准
        (2, 10),   # 低并发：容量起步
        (5, 10),   # 中并发：稳定区
        (10, 10),  # 高并发：寻找拐点
    ])

    # ---- 时间参数 ----
    poll_interval: float = 0.5       # 轮询 /status 的间隔（秒）
    query_timeout: float = 120.0     # 单条查询从提交到完成的端到端超时（秒）
    stage_cooldown: float = 2.0      # 相邻档位之间的冷却时间（秒），避免负载叠加
    warmup_secs: float = 2.0         # 每档预热时长（秒），稳定连接池/JIT

    # ---- 目标与熔断 ----
    target_qps: float = 0.0          # 目标吞吐（0 表示不设目标，仅记录实测）
    error_rate_trip: float = 0.30    # 错误率超过该值即触发压测熔断（中止后续档位）
    consecutive_fail_trip: int = 10  # 连续失败达到该值即中止当前档位

    # ---- 报告输出（默认与 eva 输出根一致，可覆盖） ----
    output_root: str = os.getenv("PERF_OUTPUT_ROOT", "")
    perf_report_path: str = field(init=False)
    perf_snapshot_path: str = field(init=False)
    quality_report_path: str = field(init=False)  # 关联的既有质量评测报告

    def __post_init__(self):
        # 默认输出根：优先 PERF_OUTPUT_ROOT，否则与 eva 共用
        if not self.output_root:
            try:
                from ..eva_config import config as eva_cfg
                self.output_root = eva_cfg.output_root
            except Exception:
                self.output_root = os.getenv("EVA_OUTPUT_ROOT", r"E:\data_test")

        import os as _os
        _os.makedirs(self.output_root, exist_ok=True)
        import os.path as _p
        self.perf_report_path = _p.join(self.output_root, "perf_report.json")
        self.perf_snapshot_path = _p.join(self.output_root, "perf_snapshot.json")
        self.quality_report_path = _p.join(self.output_root, "report.json")

    @property
    def query_url(self) -> str:
        """统一检索接口地址。"""
        return f"{self.query_api_base}/query"

    @property
    def status_url_tpl(self) -> str:
        """任务状态轮询地址模板，format(task_id=...)。"""
        return f"{self.query_api_base}/status/{{task_id}}"


def build_config(**overrides) -> PerfConfig:
    """创建压测配置实例；可用关键字覆盖任意字段。"""
    cfg = PerfConfig()
    for k, v in overrides.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)
    cfg.__post_init__()
    return cfg


# 默认配置单例
config = build_config()
