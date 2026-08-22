"""
评测配置：集中管理评测相关的连接参数、阈值与路径。
所有对外调用地址与业务代码解耦，便于针对不同环境跑评测。

注意：
- 本模块命名为 eva_config（而非 config），避免与项目根目录的 config 包冲突。
- 评测产出（数据集、断点快照、报告）统一硬编码保存到 E:\\data_test，便于集中管理。
"""
from dataclasses import dataclass, field
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


# 评测数据/结果默认保存根目录
DEFAULT_OUTPUT_ROOT = r"E:\data_test"


@dataclass
class EvaConfig:
    # ---- 对外服务地址（被测系统，必须已启动） ----
    query_api_base: str = os.getenv("EVA_QUERY_API_BASE", "http://127.0.0.1:8001")
    # 非流式查询接口
    query_url: str = field(init=False)
    # 流式事件流接口
    stream_url_tpl: str = field(init=False)

    # ---- 生成数据集时直连 Milvus（若为 None 则跳过库内采样） ----
    milvus_url: str = os.getenv("EVA_MILVUS_URL", os.getenv("MILVUS_URL", ""))
    chunks_collection: str = os.getenv("EVA_CHUNKS_COLLECTION", os.getenv("CHUNKS_COLLECTION", "kb_chunks"))
    item_name_collection: str = os.getenv("EVA_ITEM_NAME_COLLECTION", os.getenv("ITEM_NAME_COLLECTION", "kb_item_names"))

    # ---- 生成数据集时调用 LLM 生成问题（复用业务 LLM 配置） ----
    openai_api_base: str = os.getenv("OPENAI_API_BASE", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    llm_model: str = os.getenv("LLM_DEFAULT_MODEL", "")

    # ---- 检索命中判定：命中判定参考阈值 ----
    retrieval_hit_threshold: float = 0.8

    # ---- 评测运行参数 ----
    default_limit: int = 1          # 每个模式默认评测条数（不传 limit 时使用 1 条）
    timeouts: float = 120.0          # 单个查询超时（秒），非流式同步调用后端一次图流程

    # ---- 熔断机制 ----
    # 连续失败达到该值即中断当前模式评测，避免外部服务异常时反复重试浪费资源/费用。
    max_consecutive_failures: int = 3

    # ---- 输出路径（默认 E:\data_test，可通过 build_config(output_root=...) 自定义） ----
    output_root: str = DEFAULT_OUTPUT_ROOT
    dataset_path: str = field(init=False)
    report_path: str = field(init=False)
    rrf_report_path: str = field(init=False)
    rerank_report_path: str = field(init=False)
    mcp_report_path: str = field(init=False)
    embedding_report_path: str = field(init=False)
    hyde_report_path: str = field(init=False)
    item_confirm_report_path: str = field(init=False)
    answer_report_path: str = field(init=False)
    import_report_path: str = field(init=False)
    compare_report_path: str = field(init=False)
    # 断点快照（断融机制）
    eva_snapshot_path: str = field(init=False)
    rerank_snapshot_path: str = field(init=False)
    mcp_snapshot_path: str = field(init=False)
    embedding_snapshot_path: str = field(init=False)
    hyde_snapshot_path: str = field(init=False)
    item_confirm_snapshot_path: str = field(init=False)
    answer_snapshot_path: str = field(init=False)
    compare_snapshot_path: str = field(init=False)

    def __post_init__(self):
        self.query_url = f"{self.query_api_base}/query"
        self.stream_url_tpl = f"{self.query_api_base}/stream/{{session_id}}"

        # 确保输出目录存在
        os.makedirs(self.output_root, exist_ok=True)

        self.dataset_path = os.path.join(self.output_root, "dataset.json")
        self.report_path = os.path.join(self.output_root, "report.json")
        self.rrf_report_path = os.path.join(self.output_root, "rrf_report.json")
        self.rerank_report_path = os.path.join(self.output_root, "rerank_report.json")
        self.mcp_report_path = os.path.join(self.output_root, "mcp_report.json")
        self.embedding_report_path = os.path.join(self.output_root, "embedding_report.json")
        self.hyde_report_path = os.path.join(self.output_root, "hyde_report.json")
        self.item_confirm_report_path = os.path.join(self.output_root, "item_confirm_report.json")
        self.answer_report_path = os.path.join(self.output_root, "answer_output_report.json")
        self.import_report_path = os.path.join(self.output_root, "import_report.json")
        self.compare_report_path = os.path.join(self.output_root, "compare_report.json")
        self.eva_snapshot_path = os.path.join(self.output_root, "eva_snapshot.json")
        self.rerank_snapshot_path = os.path.join(self.output_root, "rerank_snapshot.json")
        self.mcp_snapshot_path = os.path.join(self.output_root, "mcp_snapshot.json")
        self.embedding_snapshot_path = os.path.join(self.output_root, "embedding_snapshot.json")
        self.hyde_snapshot_path = os.path.join(self.output_root, "hyde_snapshot.json")
        self.item_confirm_snapshot_path = os.path.join(self.output_root, "item_confirm_snapshot.json")
        self.answer_snapshot_path = os.path.join(self.output_root, "answer_output_snapshot.json")
        self.compare_snapshot_path = os.path.join(self.output_root, "compare_snapshot.json")


def build_config(output_root: Optional[str] = None) -> EvaConfig:
    """
    创建评测配置实例。
    :param output_root: 自定义保存路径根目录；None 使用默认 E:\\data_test
    """
    return EvaConfig(output_root=output_root or DEFAULT_OUTPUT_ROOT)


# 默认配置单例（供 dataset.py / evaluator.py 等模块在默认路径下使用）
config = build_config()
