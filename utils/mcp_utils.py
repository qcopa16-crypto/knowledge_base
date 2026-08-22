import asyncio
import os

from agents.mcp import MCPServerStreamableHttp

from config.bailian_mcp_config import mcp_config
from tool.logger import logger

# MCP 搜索整体超时（秒），避免外网搜索慢阻塞查询流程
MCP_TIMEOUT = float(os.getenv("MCP_TIMEOUT", "10"))


async def mcp_call_client(query: str):
    """
    调用百炼 MCP 搜索服务

    Args:
        query: 搜索关键词

    Returns:
        MCP tool 调用结果，超时/失败返回 None
    """

    search_mcp = MCPServerStreamableHttp(
        name="search_mcp",
        params={
            "url": mcp_config.mcp_base_url,
            "headers": {
                "Authorization": f"Bearer {mcp_config.api_key}"
            },
            "timeout": MCP_TIMEOUT,
        },
        cache_tools_list=True,
        max_retry_attempts=3,
    )

    try:
        # 用 asyncio.wait_for 强制超时，避免 connect/call_tool 无限等待
        await asyncio.wait_for(search_mcp.connect(), timeout=MCP_TIMEOUT)

        result = await asyncio.wait_for(
            search_mcp.call_tool(
                tool_name="bailian_web_search",
                arguments={
                    "query": query,
                    "count": 5,
                },
            ),
            timeout=MCP_TIMEOUT,
        )

        return result

    except asyncio.TimeoutError:
        logger.error(f"MCP 搜索调用超时（{MCP_TIMEOUT}s），已降级")
        return None
    except Exception as e:
        logger.error(f"MCP 搜索调用失败: {e}")
        return None

    finally:
        try:
            await search_mcp.cleanup()
        except Exception:
            # cleanup 失败不影响主流程
            pass
