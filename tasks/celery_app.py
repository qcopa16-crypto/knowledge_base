"""Celery 应用实例（共享 broker/backend 配置）

Django 侧（kb_platform/celery.py）与 FastAPI worker 侧共用此实例，
broker 用 RabbitMQ，result backend 用 Redis。
"""
import os
from celery import Celery

from config.rabbitmq_config import celery_config

broker_url = os.getenv("CELERY_BROKER_URL", celery_config.broker_url)
result_backend = os.getenv("CELERY_RESULT_BACKEND", celery_config.result_backend)

celery_app = Celery(
    "knowledge_base",
    broker=broker_url,
    backend=result_backend,
    include=["tasks.rag_tasks"],
)

# 并发模型：threads 多线程（适配 Windows）
# - Windows 无 fork()，prefork 会报 "not enough values to unpack"；
# - gevent 会与 Redis/asyncio 冲突（socket monkey-patch）；
# - threads 是 Windows 上可用的多线程并发，redis-py 连接池线程安全，无上述问题。
# 并发数默认取 CPU 核数（上限 8），可通过环境变量 CELERY_CONCURRENCY 覆盖。
_default_concurrency = min(os.cpu_count() or 4, 8)
_worker_concurrency = int(os.getenv("CELERY_CONCURRENCY", str(_default_concurrency)))

# 默认配置
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    result_expires=3600,  # 结果保留 1 小时
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # 多线程并发（Windows 兼容）
    worker_pool="threads",
    worker_concurrency=_worker_concurrency,
    # 结果回投队列
    task_default_queue="kb_rag",
    task_default_routing_key="kb_rag",
)
