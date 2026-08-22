from django.contrib import admin

from catalog.models import Brand, Category, DeviceType


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "description")


@admin.register(DeviceType)
class DeviceTypeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "description")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "parent", "path", "level", "sort_order")
