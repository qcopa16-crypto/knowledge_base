"""搜索与日志模块模型"""
from django.conf import settings
from django.db import models

from documents.models import Document


class SearchLog(models.Model):
    """搜索日志"""

    keyword = models.CharField("关键词", max_length=255)
    result_count = models.IntegerField("结果数", default=0)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="search_logs",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "search_search_log"
        verbose_name = "搜索日志"
        verbose_name_plural = "搜索日志"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["keyword"])]


class DocumentLog(models.Model):
    """文档操作日志"""

    class Action(models.TextChoices):
        VIEW = "view", "浏览"
        DOWNLOAD = "download", "下载"
        PREVIEW = "preview", "预览"
        FAVORITE = "favorite", "收藏"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="logs")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_logs",
    )
    action = models.CharField("操作", max_length=16, choices=Action.choices)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "search_document_log"
        verbose_name = "文档操作日志"
        verbose_name_plural = "文档操作日志"
        ordering = ("-created_at",)
