import pymysql

# 将 pymysql 伪装成 MySQLdb，供 Django 的 MySQL 后端使用
pymysql.install_as_MySQLdb()

# 导入 Celery app，确保 Django 启动时 celery 可用
from .celery import app as celery_app

__all__ = ("celery_app",)
