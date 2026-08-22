import asyncio
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from processor.query_processor.base import NodeBase
from processor.query_processor.state import QueryGraphState
from tool.logger import logger
from utils.json_format_utils import format_json
from utils.mcp_utils import MCP_TIMEOUT, mcp_call_client

# MCP 整体兜底超时（比 mcp_utils 内部超时略长，留出清理时间）
_MCP_NODE_TIMEOUT = MCP_TIMEOUT + 5


class NodeWebSearchMcp(NodeBase):
    """
    节点功能，调用外部搜索引擎补充信息
    """

    # 覆盖基类的 name 属性，标识节点名称
    name: str = "node_web_search_mcp"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        """
        节点逻辑
        :param state: 工作流状态对象
        :return: 更新后的状态对象
        """

        # 0、检索路开关：enable_web_search 为 False 时跳过本路（用于评测对比/降级）
        if state.get("enable_web_search", True) is False:
            logger.info("[node_web_search_mcp] enable_web_search=False，跳过 MCP 联网检索")
            return {}

        query = state.get("rewritten_query", "")
        docs = []
        # 如果没有查询内容，直接返回
        if query:
            result = self._call_mcp_with_timeout(query)
            if result:
                try:
                    pages = json.loads(result.content[0].text).get("pages") or []
                except (json.JSONDecodeError, AttributeError, IndexError):
                    pages = []
                # 统一输出结构化结果，供后续 rerank/引用使用
                # 每条：{title, url, snippet}

                for item in pages:
                    snippet = (item.get("snippet") or "").strip()
                    url = (item.get("url") or "").strip()
                    title = (item.get("title") or "").strip()
                    if not snippet:
                        continue
                    docs.append({"title": title, "url": url, "snippet": snippet})

                logger.info(f"MCP 搜索结果:{docs}")

        if docs:
            return {"web_search_docs": docs}

        return {}

    def _call_mcp_with_timeout(self, query: str):
        """在独立线程中运行 MCP 调用，并加整体超时兜底。

        使用线程池隔离 asyncio.run，避免事件循环与 worker 进程/协程模型冲突，
        并用 future.result(timeout) 确保任何情况下节点都能按时返回，不阻塞 join。
        """
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, mcp_call_client(query))
            try:
                return future.result(timeout=_MCP_NODE_TIMEOUT)
            except FuturesTimeoutError:
                logger.error(f"MCP 搜索整体超时（{_MCP_NODE_TIMEOUT}s），已降级")
                future.cancel()
                return None
            except Exception as e:
                logger.error(f"MCP 搜索执行异常: {e}")
                return None

if __name__ == "__main__":

    init_state = {
        "rewritten_query": "关于brother HAK180烫金机，如何调节转印温度？"
    }

    # 执行节点的业务调用
    node_web_search_mcp = NodeWebSearchMcp()

    result = node_web_search_mcp(init_state)

    logger.info(format_json(result, indent=4))