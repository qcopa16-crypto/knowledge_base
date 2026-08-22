"""Django 侧 Celery 应用

Django 作为任务生产者，通过此 Celery app 投递 RAG 任务到 RabbitMQ。
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kb_platform.settings")

app = Celery("kb_platform")

# 从 Django settings 读取 Celery 配置（前缀 CELERY_）
app.config_from_object("django.conf:settings", namespace="CELERY")

# 自动发现任务
app.autodiscover_tasks()

# 同时注册共享的 RAG 任务模块
app.conf.imports = ("tasks.rag_tasks",)


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
