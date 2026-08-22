"""Redis 客户端统一获取工具

区分不同用途的 db：
- db0：业务缓存（默认）
- db1：会话
- db2：Celery 结果后端 / 任务状态
"""
import os
from typing import Optional

import redis
from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_POOL_SIZE = int(os.getenv("REDIS_POOL_SIZE", "20"))
# Redis socket 超时（秒），避免 Redis 故障/网络抖动时任务永久阻塞
REDIS_SOCKET_TIMEOUT = float(os.getenv("REDIS_SOCKET_TIMEOUT", "5"))
REDIS_SOCKET_CONNECT_TIMEOUT = float(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "5"))

# 任务状态使用独立 db（db2），避免与业务缓存（db0）/ 会话（db1）冲突
TASK_STATE_DB = int(os.getenv("REDIS_TASK_DB", "2"))

# 按 (db, decode_responses) 缓存连接池，避免高并发下频繁建连/断连
_pools: dict = {}


def get_redis_client(db: Optional[int] = None, decode_responses: bool = True) -> redis.Redis:
    """获取 Redis 客户端（基于连接池，按 db 缓存）

    :param db: Redis db 编号，默认 0（业务缓存）
    :param decode_responses: 是否自动解码为 str，默认 True
    """
    if db is None:
        db = 0
    key = (db, decode_responses)
    if key not in _pools:
        _pools[key] = redis.ConnectionPool(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD or None,
            db=db,
            decode_responses=decode_responses,
            max_connections=REDIS_POOL_SIZE,
            socket_timeout=REDIS_SOCKET_TIMEOUT,
            socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
        )
    return redis.Redis(connection_pool=_pools[key])


def get_task_state_client() -> redis.Redis:
    """获取任务状态专用 Redis 客户端（db2）"""
    return get_redis_client(db=TASK_STATE_DB)
