"""目录管理模块模型：品牌、设备类型、分类（树形）"""
from django.db import models


class Brand(models.Model):
    """品牌"""

    name = models.CharField("品牌名", max_length=64, unique=True)
    code = models.CharField("品牌编码", max_length=64, unique=True)
    description = models.CharField("描述", max_length=255, blank=True, default="")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "catalog_brand"
        verbose_name = "品牌"
        verbose_name_plural = "品牌"

    def __str__(self):
        return self.name


class DeviceType(models.Model):
    """设备类型"""

    name = models.CharField("设备类型名", max_length=64, unique=True)
    code = models.CharField("类型编码", max_length=64, unique=True)
    description = models.CharField("描述", max_length=255, blank=True, default="")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "catalog_device_type"
        verbose_name = "设备类型"
        verbose_name_plural = "设备类型"

    def __str__(self):
        return self.name


class Category(models.Model):
    """分类（树形结构，parent_id + path）"""

    name = models.CharField("分类名", max_length=64)
    code = models.CharField("分类编码", max_length=64, unique=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="父分类",
    )
    path = models.CharField("路径", max_length=255, blank=True, default="", db_index=True)
    level = models.PositiveSmallIntegerField("层级", default=1)
    sort_order = models.IntegerField("排序", default=0)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "catalog_category"
        verbose_name = "分类"
        verbose_name_plural = "分类"
        ordering = ("sort_order", "id")

    def __str__(self):
        return self.name
