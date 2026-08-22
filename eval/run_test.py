"""
评测数据集生成入口。

用法：PyCharm 直接右键运行本文件即可（会自动把项目根加入 sys.path），
或命令行用模块方式运行。支持自定义保存路径 output_root。

生成的测试集：从 Milvus 采样真实切片 + LLM 生成问题与参考答案，
导出 JSON 到指定路径。

示例（在底部 main() 调用）：
    main()                                                 # 默认采样1条，默认 E:\\data_test\\dataset.json
    main(size=20, output_root="E:\\mytest")                # 自定义条数与保存路径
    main(size=10, use_llm=False, print_samples=True)       # 只采样不调LLM，打印核验
    main(size=10, expr="item_name=='HAK180烫金机'")         # 按商品筛选采样
"""
from __future__ import annotations

import os
import sys
from typing import Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))        # .../eval
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)                     # 项目根目录
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from eval.eva_config import build_config


def main(size: int = 1,
         output_root: Optional[str] = None,
         use_llm: bool = True,
         print_samples: bool = False,
         expr: Optional[str] = None,
         dataset_path: Optional[str] = None) -> None:
    """
    生成评测数据集。

    :param size: 采样条数
    :param output_root: 保存路径根目录（默认 E:\\data_test）
    :param use_llm: 是否调用 LLM 生成问题/答案；False 仅导出素材
    :param print_samples: 是否打印样本核验
    :param expr: Milvus 过滤表达式（如 item_name 过滤）
    :param dataset_path: 数据集输出路径（覆盖默认）
    """
    cfg = build_config(output_root=output_root)
    out = dataset_path or cfg.dataset_path

    from eval.data.dataset import generate_dataset, print_dataset_sample

    print(f"[run_test] output_root={cfg.output_root}, size={size}, use_llm={use_llm}")

    samples = generate_dataset(
        sample_size=size,
        expr=expr,
        use_llm=use_llm,
        output_path=out,
    )
    if print_samples:
        print_dataset_sample(samples)

    if not samples:
        print(f"[run_test] 未生成任何样本（Milvus 为空或未配置？），检查 {out}")


if __name__ == "__main__":
    # ======================================================================
    # 在这里直接指定测试集生成参数，可选自定义保存路径。
    # size 控制生成条数，默认 1 条；需要更多时自定义 size。
    # 示例：
    #   main()                                              # 默认1条，默认路径 E:\\data_test
    #   main(size=20, output_root="E:\\mytest")             # 自定义条数与路径
    #   main(size=10, use_llm=False, print_samples=True)    # 只采样不调LLM
    #   main(size=10, expr="item_name=='HAK180烫金机'")       # 按商品筛选
    # ======================================================================
    main(size=1, output_root=r"E:\data_test")
