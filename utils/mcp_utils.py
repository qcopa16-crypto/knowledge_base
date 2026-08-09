from agents.mcp import MCPServerStreamableHttp

from config.bailian_mcp_config import mcp_config
from tool.logger import logger


async def mcp_call_client(query: str):
    """
    调用百炼 MCP 搜索服务

    Args:
        query: 搜索关键词

    Returns:
        MCP tool 调用结果
    """

    search_mcp = MCPServerStreamableHttp(
        name="search_mcp",
        params={
            "url": mcp_config.mcp_base_url,
            "headers": {
                "Authorization": f"Bearer {mcp_config.api_key}"
            },
            "timeout": 10,
        },
        cache_tools_list=True,
        max_retry_attempts=3,
    )

    try:
        await search_mcp.connect()

        result = await search_mcp.call_tool(
            tool_name="bailian_web_search",
            arguments={
                "query": query,
                "count": 5,
            },
        )

        return result

    except Exception as e:
        logger.error(f"MCP 搜索调用失败: {e}")
        return None

    finally:
        await search_mcp.cleanup()