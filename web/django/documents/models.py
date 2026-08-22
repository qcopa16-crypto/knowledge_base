"""文档管理模块模型"""
from django.conf import settings
from django.db import models

from catalog.models import Brand, Category, DeviceType


class Document(models.Model):
    """文档元数据"""

    class Status(models.TextChoices):
        PENDING = "pending", "待解析"
        PROCESSING = "processing", "解析中"
        READY = "ready", "已就绪"
        FAILED = "failed", "解析失败"

    class DocType(models.TextChoices):
        USER_GUIDE = "user_guide", "用户指南"
        USER_MANUAL = "user_manual", "用户手册"
        INSTRUCTION = "instruction", "使用说明书"
        SAFETY = "safety", "产品安全手册"
        CONFIG_GUIDE = "config_guide", "配置指导"
        COMM_CONFIG = "comm_config", "通讯配置说明"
        OTHER = "other", "其他"

    class OSType(models.TextChoices):
        WINDOWS11 = "windows11", "Windows 11"
        HARMONYOS = "harmonyos", "HarmonyOS"
        UOS = "uos", "UOS"
        KOS = "kos", "KOS"
        EMUI = "emui", "EMUI"
        ANDROID = "android", "Android"
        OTHER = "other", "其他"

    title = models.CharField("标题", max_length=255)
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents")
    device_type = models.ForeignKey(DeviceType, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents")
    model_code = models.CharField("型号编码", max_length=128, db_index=True)
    os_type = models.CharField("操作系统", max_length=32, choices=OSType.choices, blank=True, default="")
    doc_type = models.CharField("文档类型", max_length=32, choices=DocType.choices, default=DocType.USER_MANUAL)
    version = models.CharField("版本号", max_length=64, blank=True, default="")
    file_path = models.CharField("文件路径(MinIO)", max_length=512, blank=True, default="")
    file_md5 = models.CharField("文件MD5", max_length=64, blank=True, default="", db_index=True)
    file_size = models.BigIntegerField("文件大小(字节)", default=0)
    cover = models.CharField("封面图", max_length=512, blank=True, default="")
    summary = models.TextField("摘要", blank=True, default="")
    keywords = models.CharField("关键词", max_length=255, blank=True, default="")
    view_count = models.IntegerField("浏览量", default=0)
    download_count = models.IntegerField("下载量", default=0)
    is_latest = models.BooleanField("是否最新版本", default=True)
    status = models.CharField("状态", max_length=16, choices=Status.choices, default=Status.PENDING)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "documents_document"
        verbose_name = "文档"
        verbose_name_plural = "文档"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["model_code", "version"]),
        ]

    def __str__(self):
        return self.title


class DocumentVersion(models.Model):
    """文档版本历史"""

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="versions")
    version = models.CharField("版本号", max_length=64)
    file_path = models.CharField("文件路径", max_length=512, blank=True, default="")
    file_md5 = models.CharField("文件MD5", max_length=64, blank=True, default="")
    remark = models.CharField("备注", max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_versions",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "documents_document_version"
        verbose_name = "文档版本"
        verbose_name_plural = "文档版本"
        ordering = ("-created_at",)


class DocumentContent(models.Model):
    """文档解析文本内容（用于检索）"""

    class ParseStatus(models.TextChoices):
        PENDING = "pending", "待解析"
        PARSING = "parsing", "解析中"
        SUCCESS = "success", "解析成功"
        FAILED = "failed", "解析失败"

    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="content")
    content_text = models.TextField("全文文本", blank=True, default="")
    page_count = models.IntegerField("页数", default=0)
    parse_status = models.CharField("解析状态", max_length=16, choices=ParseStatus.choices, default=ParseStatus.PENDING)
    parse_time = models.DateTimeField("解析时间", null=True, blank=True)

    class Meta:
        db_table = "documents_document_content"
        verbose_name = "文档解析内容"
        verbose_name_plural = "文档解析内容"


class UserFavorite(models.Model):
    """用户收藏"""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites")
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="favorites")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "documents_user_favorite"
        unique_together = ("user", "document")
        verbose_name = "用户收藏"
        verbose_name_plural = "用户收藏"
