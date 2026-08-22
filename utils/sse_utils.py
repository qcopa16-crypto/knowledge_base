"""SSE 流式消息工具（基于 Redis List + BRPOP 单通道跨进程桥接）

Celery worker 进程与 Django/FastAPI web 进程是不同进程，需要跨进程消息桥。
这里用 Redis List 作为消息队列：
- key：sse:{session_id}:queue
- worker 端 push_to_session 用 RPUSH 写入
- web 端 sse_generator_sync / sse_generator 用 BRPOP 阻塞读取

选型理由：
- Redis List + BRPOP 天然持久化，解决 pub/sub「即发即弃、订阅先行」导致的丢消息问题。
- 单通道消费，每条消息只被 BRPOP 取走一次，不会重复。
"""
import json
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import Request

from utils.redis_utils import get_redis_client


class SSEEvent:
    READY = "ready"         # 连接建立
    PROGRESS = "progress"   # 任务节点进度
    DELTA = "delta"         # LLM 流式输出增量
    FINAL = "final"         # 最终完整答案
    ERROR = "error"         # 错误信息
    CLOSE = "__close__"     # 关闭连接信号


# SSE 频道前缀
SSE_CHANNEL_PREFIX = "sse:"

# BRPOP 阻塞等待超时（秒），超时返回 None，用于连接心跳与断开检测
BRPOP_TIMEOUT = 1.0


def _list_key(session_id: str) -> str:
    """消息队列 List 的 key"""
    return f"{SSE_CHANNEL_PREFIX}{session_id}:queue"


# ---------------------------------------------------------------------------
# 兼容旧接口（List 队列无需预建，保留空实现避免调用方报错）
# ---------------------------------------------------------------------------
def create_sse_queue(session_id: str):
    """兼容旧接口：Redis List 无需预建队列，空实现"""
    return None


def remove_sse_queue(session_id: str):
    """兼容旧接口：Redis List 无需手动移除队列，空实现"""
    return None


def get_sse_queue(session_id: str):
    """兼容旧接口：返回 None"""
    return None


# ---------------------------------------------------------------------------
# 推送（worker 端调用）
# ---------------------------------------------------------------------------
def _sse_pack(event: str, data: Dict[str, Any]) -> str:
    """打包 SSE 消息格式"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def push_to_session(session_id: str, event: str, data: Dict[str, Any]):
    """推送 SSE 事件（Redis List，单通道）

    只写入 List，订阅端用 BRPOP 读取，天然不重复、不丢失。
    """
    try:
        client = get_redis_client(db=0)
        message = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        client.rpush(_list_key(session_id), message)
    except Exception as e:
        # 推送失败不影响主流程（如 Redis 短暂不可用）
        from tool.logger import logger
        logger.warning(f"SSE 推送失败（session_id={session_id}, event={event}）: {e}")


def push_close(session_id: str):
    """推送关闭信号，通知订阅端结束"""
    push_to_session(session_id, SSEEvent.CLOSE, {})


def _parse_message(raw) -> Optional[Dict[str, Any]]:
    """解析 Redis 中的消息 JSON，返回 {"event", "data"}，解析失败返回 None"""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _yield_message(payload: Dict[str, Any]):
    """根据 payload 决定是否 yield 以及是否关闭"""
    event = payload.get("event")
    event_data = payload.get("data", {})
    if event == SSEEvent.CLOSE:
        return True, None  # (should_close, sse_string)
    return False, _sse_pack(event, event_data)


# ---------------------------------------------------------------------------
# 订阅（web 端调用）
# ---------------------------------------------------------------------------
def _iter_sse_messages(session_id: str, disconnect_check=None):
    """从 Redis List 用 BRPOP 阻塞读取消息，逐条 yield SSE 字符串

    :param session_id: 会话 ID
    :param disconnect_check: 可选的可调用对象，返回 True 表示客户端已断开（async 场景传 await 版本）
    """
    client = get_redis_client(db=0)
    key = _list_key(session_id)
    try:
        # 先发 ready 信号
        yield _sse_pack(SSEEvent.READY, {})

        while True:
            if disconnect_check is not None and disconnect_check():
                break

            try:
                # BRPOP 阻塞等待，返回 (key, value) 元组；超时返回 None
                item = client.brpop(key, timeout=BRPOP_TIMEOUT)
            except Exception:
                item = None

            if item is None:
                # 超时，保持连接心跳
                continue

            value = item[1]
            payload = _parse_message(value)
            if payload is None:
                continue

            should_close, sse_str = _yield_message(payload)
            if sse_str:
                yield sse_str
            if should_close:
                break
    finally:
        # 清理残留的 List（连接关闭后不再需要）
        try:
            client.delete(key)
        except Exception:
            pass


def sse_generator_sync(session_id: str):
    """同步 SSE 生成器（供 Django StreamingHttpResponse 使用）"""
    return _iter_sse_messages(session_id, disconnect_check=None)


async def sse_generator(session_id: str, request: Request) -> AsyncGenerator[str, None]:
    """异步 SSE 生成器（供 FastAPI StreamingResponse 使用）

    与同步版一致：从 Redis List 用 BRPOP 读取消息。
    阻塞调用通过 run_in_executor 避免阻塞事件循环。
    """
    import asyncio

    loop = asyncio.get_running_loop()

    async def _disconnected():
        try:
            return await request.is_disconnected()
        except Exception:
            return False

    async def _brpop():
        return await loop.run_in_executor(
            None, client.brpop, key, BRPOP_TIMEOUT
        )

    client = get_redis_client(db=0)
    key = _list_key(session_id)
    try:
        yield _sse_pack(SSEEvent.READY, {})

        while True:
            if await _disconnected():
                break

            item = await _brpop()
            if item is None:
                continue

            payload = _parse_message(item[1])
            if payload is None:
                continue

            should_close, sse_str = _yield_message(payload)
            if sse_str:
                yield sse_str
            if should_close:
                break
    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
        return
    finally:
        try:
            client.delete(key)
        except Exception:
            pass
