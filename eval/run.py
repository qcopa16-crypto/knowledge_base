"""
评测主入口（函数调用式）。

用法：PyCharm 直接右键运行本文件即可（会自动把项目根加入 sys.path），
或命令行用模块方式运行。在底部 if __name__ == "__main__" 里调用 main() 指定模式，
可自定义保存路径 output_root。

支持的模式：
    item_confirm   商品名确认评测（白盒调 NodeItemNameConfirm，测提取 + 三分支 confirm/ask/reject）
    eva            端到端评测（黑盒调用 /query，测问答质量+检索+延迟）
    rrf            RRF 倒排融合组件评测（离线，无需外部服务）
    rerank         Rerank 交叉编码器重排组件评测（需 rerank 服务）
    mcp            MCP 联网搜索组件评测（需 MCP 服务配置，测 web_search 这一路）
    embedding      向量检索召回评测（白盒调 NodeSearchEmbedding，测 BGE-M3 召回质量）
    hyde           向量检索召回评测（白盒调 NodeSearchEmbeddingHyde，测 HyDE 增强效果）
    answer_output  答案生成评测（白盒调 NodeAnswerOutput，测 LLM 答案质量）
    import         入库链路评测（白盒调各入库节点；默认跑整链路 chain，
                   可用 import_submode 指定单环节 entry/split/item_name/embedding/milvus/pdf/md_img）
    all            按完整链路依次运行：item_confirm -> embedding -> hyde -> rrf -> rerank
                   -> answer_output -> eva -> mcp

示例（在底部 main() 调用）：
    main(mode="item_confirm")               # 商品确认，默认1条
    main(mode="rrf")                        # 测 RRF，默认1条，输出到默认 E:\\data_test
    main(mode="mcp", output_root="E:\\mcp_test")   # 测 MCP，自定义保存路径
    main(mode="embedding", limit=10)        # 测向量检索召回，采样10条锚点
    main(mode="hyde", limit=10)             # 测 HyDE 检索召回
    main(mode="answer_output", limit=5)     # 测答案生成 5 条
    main(mode="eva", limit=20)              # 端到端前 20 条
    main(mode="import")                     # 入库整链路（split->item_name->embedding->milvus），默认1条
    main(mode="import", import_submode="split")  # 只测文档切分（纯本地）
    main(mode="import", import_submode="pdf", pdf_path=r"D:\\test.pdf")  # 测 PDF 解析
    main(mode="all", output_root="E:\\data_test", limit=5, fresh=True)  # 全部各5条，强制从头

条数控制（limit）：
    统一控制各模式评测条数，默认只跑 1 条；自定义数量时传 limit=N。

熔断机制：
    各模式连续失败达 eva_config.max_consecutive_failures（默认 3）次即自动中断，
    避免外部服务异常时反复调用浪费资源/费用；中断后已完成的条目已落盘断点。

断融（断点续跑）：
    默认启用：中断后重跑自动跳过已完成条目；fresh=True 强制从头。
"""
from __future__ import annotations

import os
import sys
from typing import Optional

# =====================================================================
# 兼容"PyCharm 右键直接运行"：把项目根目录加入 sys.path，
# 使绝对导入（eval.*）可解析。
# =====================================================================
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))        # .../eval
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)                     # 项目根目录
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from eval.eva_config import EvaConfig, build_config


# ---------------------------------------------------------------------------
# 各模式实现
# ---------------------------------------------------------------------------
def _run_eva(cfg: EvaConfig, limit: Optional[int] = None,
             fresh: bool = False, dataset_path: Optional[str] = None) -> None:
    from eval.data.dataset import load_dataset
    from eval.evals.evaluator import run_evaluation
    from eval.embed_sim import try_enable_semantic

    dataset = load_dataset(dataset_path or cfg.dataset_path)
    if not dataset:
        print(f"[eva] 数据集为空，请先用 run_test.py 生成或检查路径：{cfg.dataset_path}")
        sys.exit(1)
    try_enable_semantic()
    run_evaluation(dataset, sample_count=limit,
                   report_path=cfg.report_path, resume=not fresh)


def _run_rrf(cfg: EvaConfig, limit: Optional[int] = None) -> None:
    from eval.evals.rrf_eval import run_rrf_eval
    run_rrf_eval(report_path=cfg.rrf_report_path, limit=limit)


def _run_rerank(cfg: EvaConfig, limit: Optional[int] = None,
                fresh: bool = False) -> None:
    from eval.evals.rerank_eval import run_rerank_eval
    run_rerank_eval(report_path=cfg.rerank_report_path,
                    resume=not fresh, limit=limit)


def _run_mcp(cfg: EvaConfig, fresh: bool = False,
             queries: Optional[list] = None,
             limit: Optional[int] = None) -> None:
    from eval.evals.mcp_eval import run_mcp_eval
    run_mcp_eval(queries=queries,
                 report_path=cfg.mcp_report_path,
                 resume=not fresh, limit=limit)


def _load_queries_map(cfg: EvaConfig) -> dict:
    """从评测数据集加载 {chunk_id: 自然问题} 映射，供检索评测消除自证偏置。"""
    from eval.data.dataset import load_dataset
    dataset = load_dataset(cfg.dataset_path)
    mapping = {}
    for s in dataset:
        cid = s.get("expected_chunk_ids")
        q = s.get("query")
        if cid and q:
            for one in cid:
                mapping.setdefault(str(one), q)
    return mapping


def _run_embedding(cfg: EvaConfig, limit: Optional[int] = None,
                   fresh: bool = False) -> None:
    from eval.evals.retrieval_eval import run_retrieval_eval
    run_retrieval_eval(component="embedding",
                       sample_size=limit or 1,
                       report_path=cfg.embedding_report_path,
                       resume=not fresh,
                       queries_map=_load_queries_map(cfg))


def _run_hyde(cfg: EvaConfig, limit: Optional[int] = None,
              fresh: bool = False) -> None:
    from eval.evals.retrieval_eval import run_retrieval_eval
    run_retrieval_eval(component="hyde",
                       sample_size=limit or 1,
                       report_path=cfg.hyde_report_path,
                       resume=not fresh,
                       queries_map=_load_queries_map(cfg))


def _run_answer_output(cfg: EvaConfig, limit: Optional[int] = None,
                       fresh: bool = False) -> None:
    from eval.evals.answer_output_eval import run_answer_output_eval
    run_answer_output_eval(report_path=cfg.answer_report_path,
                           resume=not fresh, limit=limit)


def _run_compare(cfg: EvaConfig, limit: Optional[int] = None,
                 fresh: bool = False, paths: Optional[list] = None) -> None:
    """运行检索路引入/去除影响对比评测（提升度）。"""
    from eval.evals.compare_eval import run_compare_eval
    run_compare_eval(report_path=cfg.compare_report_path,
                     resume=not fresh, limit=limit, paths=paths)


def _run_import(cfg: EvaConfig, mode: str = "chain", limit: Optional[int] = None,
                fresh: bool = False, pdf_path: Optional[str] = None,
                md_img_path: Optional[str] = None) -> None:
    """运行入库链路评测。

    mode: entry / split / item_name / embedding / milvus / pdf / md_img / chain
    pdf_path / md_img_path 为依赖真实文件的节点提供测试文件路径。
    """
    from eval.evals.import_eval import run_import_eval
    run_import_eval(mode=mode,
                    report_path=cfg.import_report_path,
                    resume=not fresh, limit=limit,
                    pdf_path=pdf_path, md_img_path=md_img_path)


def _run_item_confirm(cfg: EvaConfig, limit: Optional[int] = None,
                      fresh: bool = False) -> None:
    from eval.evals.item_confirm_eval import run_item_confirm_eval
    run_item_confirm_eval(limit=limit or 1,
                          report_path=cfg.item_confirm_report_path,
                          resume=not fresh)


def _run_all(cfg: EvaConfig, limit: Optional[int] = None,
             fresh: bool = False) -> None:
    """按完整链路运行：item_confirm -> embedding/hyde -> rrf -> rerank -> answer_output -> eva -> mcp。"""
    limit = limit or 1
    print("=" * 60)
    print(f"[all] 依次评测 8 个环节，每环节各跑 {limit} 条")
    print("[all] 步骤 1/8：商品名确认评测")
    _run_item_confirm(cfg, limit=limit, fresh=fresh)
    print("=" * 60)
    print("[all] 步骤 2/8：向量检索召回评测（embedding）")
    _run_embedding(cfg, limit=limit, fresh=fresh)
    print("=" * 60)
    print("[all] 步骤 3/8：向量检索召回评测（HyDE）")
    _run_hyde(cfg, limit=limit, fresh=fresh)
    print("=" * 60)
    print("[all] 步骤 4/8：RRF 组件评测")
    _run_rrf(cfg, limit=limit)
    print("=" * 60)
    print("[all] 步骤 5/8：Rerank 组件评测")
    _run_rerank(cfg, limit=limit, fresh=fresh)
    print("=" * 60)
    print("[all] 步骤 6/8：答案生成评测")
    _run_answer_output(cfg, limit=limit, fresh=fresh)
    print("=" * 60)
    print("[all] 步骤 7/8：端到端评测")
    _run_eva(cfg, limit=limit, fresh=fresh)
    print("=" * 60)
    print("[all] 步骤 8/8：MCP 联网搜索评测")
    _run_mcp(cfg, limit=limit, fresh=fresh)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def main(mode: str = "rrf",
         output_root: Optional[str] = None,
         limit: Optional[int] = None,
         fresh: bool = False,
         dataset_path: Optional[str] = None,
         queries: Optional[list] = None,
         pdf_path: Optional[str] = None,
         md_img_path: Optional[str] = None,
         import_submode: str = "chain",
         compare_paths: Optional[list] = None) -> None:
    """
    评测入口。

    :param mode: 评测模式：item_confirm / eva / embedding / hyde / rrf / rerank / mcp /
        answer_output / import / all
    :param output_root: 保存路径根目录（默认 E:\\data_test，可自定义）
    :param limit: 各模式评测条数，统一控制（默认 1 条）
    :param fresh: 强制从头重跑，忽略断点
    :param dataset_path: 端到端评测的数据集路径（默认 output_root/dataset.json）
    :param queries: MCP 评测查询集（None 用内置）
    :param pdf_path: import 模式下 pdf 节点评测的真实 PDF 文件路径
    :param md_img_path: import 模式下 md_img 节点评测的真实 MD 文件路径
    :param import_submode: import 模式下的子环节（entry/split/item_name/embedding/milvus/pdf/md_img/chain）
    :param compare_paths: compare 模式下要对比的检索路（默认 embedding/hyde/web_search）
    """
    cfg = build_config(output_root=output_root)
    limit = limit or 1  # 统一默认只跑 1 条

    print(f"[run] mode={mode}, limit={limit}, output_root={cfg.output_root}")

    dispatcher = {
        "item_confirm": lambda: _run_item_confirm(cfg, limit=limit, fresh=fresh),
        "eva": lambda: _run_eva(cfg, limit=limit, fresh=fresh, dataset_path=dataset_path),
        "rrf": lambda: _run_rrf(cfg, limit=limit),
        "rerank": lambda: _run_rerank(cfg, limit=limit, fresh=fresh),
        "mcp": lambda: _run_mcp(cfg, fresh=fresh, queries=queries, limit=limit),
        "embedding": lambda: _run_embedding(cfg, limit=limit, fresh=fresh),
        "hyde": lambda: _run_hyde(cfg, limit=limit, fresh=fresh),
        "answer_output": lambda: _run_answer_output(cfg, limit=limit, fresh=fresh),
        "import": lambda: _run_import(cfg, mode=import_submode, limit=limit, fresh=fresh,
                                      pdf_path=pdf_path, md_img_path=md_img_path),
        "compare": lambda: _run_compare(cfg, limit=limit, fresh=fresh, paths=compare_paths),
        "all": lambda: _run_all(cfg, limit=limit, fresh=fresh),
    }
    if mode not in dispatcher:
        print(f"[run] 未知模式: {mode}，可选 {list(dispatcher.keys())}")
        sys.exit(1)

    dispatcher[mode]()


if __name__ == "__main__":
    # ======================================================================
    # 在这里直接指定要运行的评测模式，并可选自定义保存路径。
    # 可用模式：item_confirm / eva / embedding / hyde / rrf / rerank / mcp / all
    # limit 统一控制各模式评测条数，默认 1 条；不传则只跑 1 条。
    # 示例：
    #   main(mode="item_confirm")                           # 商品确认，默认1条
    #   main(mode="rrf")                                    # RRF，默认1条
    #   main(mode="mcp", output_root="E:\\data_test")       # 测 MCP
    #   main(mode="embedding", limit=10)                    # 向量检索召回10条
    #   main(mode="hyde", limit=10)                         # HyDE 检索召回10条
    #   main(mode="eva", limit=20, fresh=False)             # 端到端前20条
    #   main(mode="all", output_root="E:\\data_test", limit=5, fresh=False)  # 全部各5条
    # ======================================================================
    main(mode="rrf", output_root=r"E:\data_test", limit=1)
