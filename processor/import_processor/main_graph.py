import logging
import json
from langgraph.constants import END
from langgraph.graph import StateGraph

from processor.import_processor.base import setup_logging
from processor.import_processor.nodes.node_bge_embedding import NodeBGEEmbedding
from processor.import_processor.nodes.node_document_split import NodeDocumentSplit
from processor.import_processor.nodes.node_entry import NodeEntry
from processor.import_processor.nodes.node_import_milvus import NodeImportMilvus
from processor.import_processor.nodes.node_item_name_recognition import NodeItemNameRecognition
from processor.import_processor.nodes.node_md_img import NodeMDImg
from processor.import_processor.nodes.node_pdf_to_md import NodePDFToMD
from processor.import_processor.state import ImportGraphState


class KBImportWorkflow:
    """知识库导入工作流"""

    def __init__(self, config=None):
        """
            初始化工作流
        """
        self._compiled_graph = None

    @property
    def graph(self):
        """
            懒加载：只在第一次使用时编译图
        """
        logging.info("获取图实例")
        if self._compiled_graph is None:
            self._compiled_graph = self.build_graph()

        return self._compiled_graph

    @staticmethod
    def route_after_entry(state: ImportGraphState) -> str:
        """
            入口节点后的条件路由函数
            :param state: 当前状态
            :return: 下一个节点名称
        """
        if state.get("is_pdf_read_enabled"):
            return "node_pdf_to_md"
        elif state.get("is_md_read_enabled"):
            return "node_md_img"
        else:
            logging.info("route_after_entry路由器：未指定导入文件类型")
            return END

    def build_graph(self):
        """
            创建图结构
            :return: 编译后的图
        """
        graph = StateGraph(ImportGraphState)

        # 1. 注册节点
        graph.add_node("node_entry", NodeEntry())
        graph.add_node("node_pdf_to_md", NodePDFToMD())
        graph.add_node("node_md_img", NodeMDImg())
        graph.add_node("node_document_split", NodeDocumentSplit())
        graph.add_node("node_item_name_recognition", NodeItemNameRecognition())
        graph.add_node("node_bge_embedding", NodeBGEEmbedding())
        graph.add_node("node_import_milvus", NodeImportMilvus())

        graph.set_entry_point("node_entry")

        # 2. 节点边
        graph.add_conditional_edges(
            "node_entry",
            self.route_after_entry,
            {
                "node_pdf_to_md": "node_pdf_to_md",
                "node_md_img": "node_md_img",
                END: END
            }
        )

        graph.add_edge("node_pdf_to_md", "node_md_img")
        graph.add_edge("node_md_img", "node_document_split")
        graph.add_edge("node_document_split", "node_item_name_recognition")
        graph.add_edge("node_item_name_recognition", "node_bge_embedding")
        graph.add_edge("node_bge_embedding", "node_import_milvus")
        graph.add_edge("node_import_milvus", END)

        # 3. 编译图
        graph_compile = graph.compile()

        return graph_compile

    def run(self, state: ImportGraphState, stream: bool = False):
        """
            统一执行入口，支持切换invoke/stream
            :param state: 初始状态
            :param stream: 是否流式输出
            :return: 执行结果
        """
        if stream:
            return self.graph.stream(state)
        else:
            return self.graph.invoke(state)


if __name__ == "__main__":
    #启用日志
    setup_logging()

    workflow = KBImportWorkflow()

    init_state = {
        "import_file_path": r"E:\学习视频\掌柜智库课件0525\掌柜智库课件0525\2.资料\04-设备手册汇总\doc\hak180产品安全手册.pdf"
    }

    for event in workflow.run(init_state, stream=True):
        print(f"state: {event}")

    # 方式2：非流式执行
    # final_state = workflow.run(init_state, stream=False)
    # print(json.dumps(final_state, ensure_ascii=False, indent=4))

    # 打印编译后的图结构
    # workflow.graph.get_graph().print_ascii()
