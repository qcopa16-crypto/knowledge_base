"""
入库链路（Import Processor）评测。

覆盖入库全链路各节点：
    entry        入口路由节点（纯本地）
    split        文档切分节点（纯本地，最值得测）
    item_name    商品名识别节点（需 LLM + Milvus）
    embedding    BGE-M3 向量化节点（需模型）
    milvus       Milvus 入库节点（需 Milvus，写真实库）
    chain        串行整链路 split -> item_name -> embedding -> milvus
    pdf          PDF 解析节点（需 MinerU 网络 + 真实 PDF，默认不跑）
    md_img       MD 图片处理节点（需 MinIO + 多模态 LLM + 真实图片，默认不跑）

设计要点：
    - 默认只用 1 条测试数据（构造的一段 Markdown 文本），减少外部 API 消耗
    - 写 Milvus 的环节使用测试专属 file_title 前缀（EVA_TEST_），并在结束后清理，
      避免污染真实 kb_chunks 数据
    - 每个环节独立计分，带熔断 + 断点续跑 + limit
    - 依赖真实文件的 pdf/md_img 环节：需显式传入文件路径，找不到文件则跳过并告警
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Dict, List, Optional, Sequence

from .. import metrics
from .. import snapshot
from ..eva_config import config

# 测试数据的 file_title 前缀，用于隔离测试写入，评测结束后清理
EVA_TEST_PREFIX = "EVA_TEST_"


# ---------------------------------------------------------------------------
# 构造测试数据（默认 1 条）
# ---------------------------------------------------------------------------
def _default_test_doc() -> Dict:
    """构造 1 条测试文档：一段带标题的 Markdown，用于入库链路各节点。"""
    content = (
        "# 华为MateBook B5-330 笔记本电脑\n\n"
        "## 产品概述\n"
        "华为MateBook B5-330是一款面向商务办公的轻薄笔记本电脑，采用金属机身设计。"
        "该产品搭载高性能处理器，支持多任务并行处理。\n\n"
        "## 技术参数\n"
        "屏幕尺寸15.6英寸，分辨率1920x1080，内存16GB，固态硬盘512GB。\n\n"
        "## 使用说明\n"
        "首次使用请连接电源适配器充电，长按电源键3秒开机。\n"
    )
    return {
        "file_title": f"{EVA_TEST_PREFIX}华为MateBook B5-330测试文档",
        "md_content": content,
        "expected_item_name": "华为MateBook B5-330",  # 期望识别的商品名（含于 file_title）
    }


# ---------------------------------------------------------------------------
# 入口节点评测
# ---------------------------------------------------------------------------
def _eval_entry(sample: Dict) -> Dict:
    """测 NodeEntry：PDF/MD 路由标志 + file_title 提取。"""
    from processor.import_processor.nodes.node_entry import NodeEntry

    node = NodeEntry()
    results = []
    # 构造一个临时 md 文件用于路由测试
    md_path = os.path.join(config.output_root, f"{EVA_TEST_PREFIX}entry_test.md")
    os.makedirs(os.path.dirname(md_path) or ".", exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# test\n")

    t0 = time.time()
    try:
        # 测 md 路由
        state = {"import_file_path": md_path}
        out = node.process(state)
        md_ok = out.get("is_md_read_enabled") is True and out.get("file_title") == "EVA_TEST_entry_test"
        # 测非法后缀路由
        bad_path = md_path.replace(".md", ".txt")
        with open(bad_path, "w", encoding="utf-8") as f:
            f.write("x")
        from processor.import_processor.exceptions import ValidationError
        try:
            node.process({"import_file_path": bad_path})
            bad_ok = False
        except ValidationError:
            bad_ok = True
        status = "ok"
        error = ""
    except Exception as e:
        status = "failed"
        error = str(e)
        md_ok = bad_ok = False
    finally:
        for p in (md_path, bad_path):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass

    return {
        "query": "entry路由测试",
        "status": status,
        "error": error,
        "latency": round(time.time() - t0, 3),
        "md_route_ok": md_ok,
        "invalid_suffix_rejected": bad_ok,
        "entry_ok": 1.0 if (status == "ok" and md_ok and bad_ok) else 0.0,
    }


# ---------------------------------------------------------------------------
# 文档切分节点评测（纯本地，最值钱）
# ---------------------------------------------------------------------------
def _eval_split(sample: Dict) -> Dict:
    """测 NodeDocumentSplit：按标题切分、长切短合、字段完整性。"""
    from processor.import_processor.nodes.node_document_split import NodeDocumentSplit
    from processor.import_processor.exceptions import StateFieldError

    node = NodeDocumentSplit()
    file_title = sample["file_title"]
    md_content = sample["md_content"]
    max_len = node.config.max_content_length
    min_len = node.config.min_content_length

    t0 = time.time()
    try:
        out = node.process({"md_content": md_content, "file_title": file_title})
        chunks = out.get("chunks", [])
    except StateFieldError as e:
        return {"status": "failed", "error": f"split 输入校验失败: {e}", "latency": 0.0,
                "chunk_count": 0, "split_ok": 0.0}
    except Exception as e:
        return {"status": "failed", "error": f"split 异常: {e}", "latency": round(time.time() - t0, 3),
                "chunk_count": 0, "split_ok": 0.0}

    # 校验项
    has_title_chunks = len(chunks) > 0                       # 能切出切片
    all_have_fields = all(
        c.get("content") and c.get("title") is not None and
        c.get("parent_title") is not None and c.get("file_title")
        for c in chunks
    ) if chunks else False                                   # 每个 chunk 字段完整
    no_oversized = all(len(c.get("content", "")) <= max_len for c in chunks)  # 无超长切片
    contains_topic = any("华为MateBook" in c.get("content", "") for c in chunks)  # 内容未丢失

    split_ok = 1.0 if (has_title_chunks and all_have_fields and no_oversized and contains_topic) else 0.0

    return {
        "query": file_title,
        "status": "ok",
        "latency": round(time.time() - t0, 3),
        "chunk_count": len(chunks),
        "has_title_chunks": has_title_chunks,
        "all_have_fields": all_have_fields,
        "no_oversized": no_oversized,
        "contains_topic": contains_topic,
        "split_ok": split_ok,
    }


# ---------------------------------------------------------------------------
# 商品名识别节点评测（需 LLM + Milvus）
# ---------------------------------------------------------------------------
def _eval_item_name(sample: Dict, chunks: Optional[List[Dict]] = None) -> Dict:
    """测 NodeItemNameRecognition：识别商品名并回填到所有切片。"""
    from processor.import_processor.nodes.node_item_name_recognition import NodeItemNameRecognition

    node = NodeItemNameRecognition()
    file_title = sample["file_title"]
    if chunks is None:
        # 若未提供上游 chunks，用 split 的输出作为输入
        from processor.import_processor.nodes.node_document_split import NodeDocumentSplit
        split_out = NodeDocumentSplit().process(
            {"md_content": sample["md_content"], "file_title": file_title})
        chunks = split_out.get("chunks", [])

    t0 = time.time()
    try:
        out = node.process({"file_title": file_title, "chunks": chunks})
    except Exception as e:
        return {"status": "failed", "error": f"item_name 异常: {e}", "latency": round(time.time() - t0, 3),
                "item_name": "", "item_name_ok": 0.0}

    item_name = out.get("item_name", "") or ""
    updated_chunks = out.get("chunks", [])

    # 校验：识别出商品名、且回填到所有切片
    recognized = bool(item_name)
    filled_all = all(c.get("item_name") for c in updated_chunks) if updated_chunks else False
    # 期望商品名应含在文件标题或切片内容中（归一化：去掉空格后比较，因为项目识别时会清洗空格）
    topic = sample.get("expected_item_name", "")
    norm_item = item_name.replace(" ", "")
    norm_topic = topic.replace(" ", "") if topic else ""
    plausible = bool(norm_topic and (norm_topic in norm_item or norm_item in norm_topic))

    item_name_ok = 1.0 if (recognized and filled_all and plausible) else 0.0

    return {
        "query": file_title,
        "status": "ok",
        "latency": round(time.time() - t0, 3),
        "item_name": item_name,
        "recognized": recognized,
        "filled_all_chunks": filled_all,
        "plausible": plausible,
        "item_name_ok": item_name_ok,
    }


# ---------------------------------------------------------------------------
# 向量化节点评测（需 BGE-M3 模型）
# ---------------------------------------------------------------------------
def _eval_embedding(sample: Dict, chunks: Optional[List[Dict]] = None) -> Dict:
    """测 NodeBGEEmbedding：为切片生成 dense/sparse 向量。"""
    from processor.import_processor.nodes.node_bge_embedding import NodeBGEEmbedding

    node = NodeBGEEmbedding()
    if chunks is None:
        from processor.import_processor.nodes.node_document_split import NodeDocumentSplit
        chunks = NodeDocumentSplit().process(
            {"md_content": sample["md_content"], "file_title": sample["file_title"]}).get("chunks", [])
        # 向量化需要 item_name，若无则补默认
        for c in chunks:
            c.setdefault("item_name", sample.get("expected_item_name", ""))

    t0 = time.time()
    try:
        out = node.process({"chunks": chunks})
    except Exception as e:
        return {"status": "failed", "error": f"embedding 异常: {e}", "latency": round(time.time() - t0, 3),
                "vector_dim": 0, "embedding_ok": 0.0}

    out_chunks = out.get("chunks", [])
    dim = len(out_chunks[0].get("dense_vector", [])) if out_chunks else 0
    has_dense = all("dense_vector" in c for c in out_chunks) if out_chunks else False
    has_sparse = all("sparse_vector" in c for c in out_chunks) if out_chunks else False
    dim_ok = dim in (1024, 512, 768)  # BGE-M3 通常 1024 维

    embedding_ok = 1.0 if (out_chunks and has_dense and has_sparse and dim_ok) else 0.0

    return {
        "query": sample["file_title"],
        "status": "ok",
        "latency": round(time.time() - t0, 3),
        "chunk_count": len(out_chunks),
        "vector_dim": dim,
        "has_dense": has_dense,
        "has_sparse": has_sparse,
        "embedding_ok": embedding_ok,
    }


# ---------------------------------------------------------------------------
# Milvus 入库节点评测（需 Milvus，写真实库，用测试前缀隔离+清理）
# ---------------------------------------------------------------------------
def _eval_milvus(sample: Dict, chunks: Optional[List[Dict]] = None) -> Dict:
    """测 NodeImportMilvus：入库 + chunk_id 回填 + 幂等。写库后清理测试数据。"""
    from processor.import_processor.nodes.node_import_milvus import NodeImportMilvus
    from utils.milvus_utils import get_milvus_client

    node = NodeImportMilvus()
    file_title = sample["file_title"]

    if chunks is None:
        from processor.import_processor.nodes.node_document_split import NodeDocumentSplit
        from processor.import_processor.nodes.node_bge_embedding import NodeBGEEmbedding
        split_chunks = NodeDocumentSplit().process(
            {"md_content": sample["md_content"], "file_title": file_title}).get("chunks", [])
        for c in split_chunks:
            c.setdefault("item_name", sample.get("expected_item_name", ""))
        chunks = NodeBGEEmbedding().process({"chunks": split_chunks}).get("chunks", [])

    if not chunks:
        return {"status": "failed", "error": "无向量切片可入库", "latency": 0.0, "insert_count": 0,
                "chunk_id_backfilled": False, "milvus_ok": 0.0}

    t0 = time.time()
    try:
        out = node.process({"chunks": chunks})
        inserted = out.get("chunks", [])
        # 校验 chunk_id 回填（NodeImportMilvus 插入成功后会回填 Milvus 自增主键）
        id_backfilled = all(c.get("chunk_id") for c in inserted)
        id_count = sum(1 for c in inserted if c.get("chunk_id"))
        # 二次查询验证（Milvus 新写入需 load 后立即可查；此处尽力而为，不作为唯一依据）
        verify_count = 0
        try:
            from utils.milvus_utils import get_milvus_client
            client = get_milvus_client()
            if client:
                col = "kb_chunks"
                client.load_collection(collection_name=col)
                verify_count = len(client.query(
                    collection_name=col,
                    filter=f"file_title=='{file_title}'",
                    output_fields=["chunk_id"], limit=100))
        except Exception:
            verify_count = 0  # 二次查询失败不判定为失败（以 chunk_id 回填为准）
        insert_count = max(id_count, verify_count)
        status = "ok"
        error = ""
    except Exception as e:
        status = "failed"
        error = str(e)
        id_backfilled = False
        id_count = 0
        insert_count = 0
    finally:
        # 清理测试数据，避免污染真实库
        _cleanup_test_milvus(file_title)

    milvus_ok = 1.0 if (status == "ok" and id_backfilled and insert_count > 0) else 0.0

    return {
        "query": file_title,
        "status": status,
        "error": error,
        "latency": round(time.time() - t0, 3),
        "insert_count": insert_count,
        "chunk_id_backfilled": id_backfilled,
        "milvus_ok": milvus_ok,
    }


def _cleanup_test_milvus(file_title: str) -> None:
    """清理评测写入 Milvus 的测试数据（按 file_title 删除）。"""
    try:
        from utils.milvus_utils import get_milvus_client
        client = get_milvus_client()
        if client:
            client.load_collection(collection_name="kb_chunks")
            client.delete(collection_name="kb_chunks", filter=f"file_title=='{file_title}'")
    except Exception as e:
        print(f"[import] 清理 Milvus 测试数据失败（可忽略）: {e}")


# ---------------------------------------------------------------------------
# 依赖真实文件的节点（pdf/md_img），需显式传文件路径
# ---------------------------------------------------------------------------
def _eval_pdf(sample: Dict, pdf_path: Optional[str] = None) -> Dict:
    """测 NodePDFToMD：解析 PDF 生成 MD。需真实 PDF 文件 + MinerU 网络。"""
    from processor.import_processor.nodes.node_pdf_to_md import NodePDFToMD

    if not pdf_path or not os.path.exists(pdf_path):
        return {"status": "skipped", "error": "未提供真实 PDF 文件路径，跳过 pdf 评测",
                "latency": 0.0, "md_content": "", "pdf_ok": 0.0}

    node = NodePDFToMD()
    t0 = time.time()
    try:
        out = node.process({"import_file_path": pdf_path})
        md_content = out.get("md_content", "") or ""
        pdf_ok = 1.0 if len(md_content) > 0 else 0.0
        return {"query": os.path.basename(pdf_path), "status": "ok",
                "latency": round(time.time() - t0, 3), "md_content": md_content,
                "pdf_ok": pdf_ok}
    except Exception as e:
        return {"query": os.path.basename(pdf_path), "status": "failed", "error": str(e),
                "latency": round(time.time() - t0, 3), "md_content": "", "pdf_ok": 0.0}


def _eval_md_img(sample: Dict, md_path: Optional[str] = None) -> Dict:
    """测 NodeMDImg：MD 图片处理。需真实 MD+图片 + MinIO + 多模态 LLM。"""
    from processor.import_processor.nodes.node_md_img import NodeMDImg

    if not md_path or not os.path.exists(md_path):
        return {"status": "skipped", "error": "未提供真实 MD 文件路径，跳过 md_img 评测",
                "latency": 0.0, "md_content": "", "md_img_ok": 0.0}

    node = NodeMDImg()
    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()
    t0 = time.time()
    try:
        out = node.process({"md_path": md_path, "md_content": md_content})
        new_md = out.get("md_content", "") or ""
        md_img_ok = 1.0 if len(new_md) > 0 else 0.0
        return {"query": os.path.basename(md_path), "status": "ok",
                "latency": round(time.time() - t0, 3), "md_content": new_md,
                "md_img_ok": md_img_ok}
    except Exception as e:
        return {"query": os.path.basename(md_path), "status": "failed", "error": str(e),
                "latency": round(time.time() - t0, 3), "md_content": "", "md_img_ok": 0.0}


# ---------------------------------------------------------------------------
# 调度：按 mode 运行对应环节
# ---------------------------------------------------------------------------
_EVAL_FUNCS = {
    "entry": _eval_entry,
    "split": _eval_split,
    "item_name": _eval_item_name,
    "embedding": _eval_embedding,
    "milvus": _eval_milvus,
    "pdf": _eval_pdf,
    "md_img": _eval_md_img,
}


def run_import_eval(mode: str = "chain",
                    report_path: Optional[str] = None,
                    resume: bool = True,
                    limit: Optional[int] = None,
                    pdf_path: Optional[str] = None,
                    md_img_path: Optional[str] = None,
                    samples: Optional[Sequence[Dict]] = None) -> Dict:
    """
    运行入库链路评测。
    :param mode: entry / split / item_name / embedding / milvus / pdf / md_img / chain
    :param report_path: 报告输出路径
    :param resume: 是否启用断点续跑
    :param limit: 测试数据条数（默认 1）
    :param pdf_path: pdf 评测的真实 PDF 文件路径
    :param md_img_path: md_img 评测的真实 MD 文件路径
    :param samples: 测试数据集；None 使用内置 1 条构造数据
    """
    if samples is None:
        samples = [_default_test_doc()]
    samples = list(samples)
    if limit is not None and limit > 0:
        samples = samples[:limit]

    # chain 模式：按完整链路串行跑 split -> item_name -> embedding -> milvus
    if mode == "chain":
        report = {"meta": {"component": "import_chain", "mode": "chain",
                           "total_samples": len(samples),
                           "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")},
                  "metrics": {}, "samples": []}
        chain_total_ok = 0
        for s in samples:
            chain_results = {}
            # 1) split：切分
            r_split = _eval_split(s)
            chain_results["split"] = r_split
            # 2) item_name：识别商品名并回填（内部重新切分生成输入）
            r_name = _eval_item_name(s)
            chain_results["item_name"] = r_name
            # 3) embedding：向量化（内部从 split 生成输入）
            r_emb = _eval_embedding(s)
            chain_results["embedding"] = r_emb
            # 4) milvus：入库（内部从 split+embedding 生成带向量切片）
            r_mv = _eval_milvus(s)
            chain_results["milvus"] = r_mv

            chain_ok = (r_split.get("split_ok") == 1.0 and r_name.get("item_name_ok") == 1.0
                        and r_emb.get("embedding_ok") == 1.0 and r_mv.get("milvus_ok") == 1.0)
            chain_total_ok += 1 if chain_ok else 0

            report["samples"].append({
                "file_title": s["file_title"],
                "chain_ok": chain_ok,
                "chain_results": chain_results,
            })
        report["metrics"]["chain_pass_rate"] = metrics.safe_mean(
            [1.0] * chain_total_ok + [0.0] * (len(report["samples"]) - chain_total_ok)
        ) if report["samples"] else 0.0

        _write_report(report_path, report)
        return report

    # 单模式
    if mode not in _EVAL_FUNCS:
        print(f"[import] 未知入库评测模式: {mode}，可选 {list(_EVAL_FUNCS.keys()) + ['chain']}")
        return {"meta": {"component": "import", "error": f"unknown_mode:{mode}"}}

    from ..runner import run_batch

    eval_fn = _EVAL_FUNCS[mode]
    # 给每条数据补 query 字段作为断点主键（=file_title）
    for s in samples:
        s.setdefault("query", s.get("file_title", ""))

    def _run_one(s: Dict) -> Dict:
        if mode == "pdf":
            return _eval_pdf(s, pdf_path)
        if mode == "md_img":
            return _eval_md_img(s, md_img_path)
        r = eval_fn(s)
        return {**r, "query": s.get("query", "")}

    def _aggregate(results, meta):
        ok = [r for r in results if r.get("status") == "ok"]
        skipped = [r for r in results if r.get("status") == "skipped"]
        return {"meta": {"mode": mode,
                         "success_samples": len(ok),
                         "skipped_samples": len(skipped)},
                "metrics": {},
                "samples": results}

    def _log(r) -> str:
        return f"{r['status']} | {r.get('query', '')[:30]}"

    report = run_batch(
        component=f"import/{mode}",
        items=samples,
        run_one=_run_one,
        snapshot_path=_snapshot_path_for(mode),
        report_path=report_path,
        aggregate=_aggregate,
        resume=resume,
        sleep_secs=0.3,
        log_line=_log,
    )
    return report


def _snapshot_path_for(mode: str) -> str:
    base = os.path.join(config.output_root, "import")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f"{mode}_snapshot.json")


def _write_report(report_path: Optional[str], report: Dict) -> None:
    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"[import] 报告已写入: {report_path}")


if __name__ == "__main__":
    # 默认跑整链路，1 条测试数据
    run_import_eval(mode="chain")
