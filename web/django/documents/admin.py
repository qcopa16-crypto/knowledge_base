from django.contrib import admin

from documents.models import Document, DocumentContent, DocumentVersion, UserFavorite


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "model_code", "brand", "device_type", "status", "version", "is_latest")
    list_filter = ("status", "brand", "device_type", "os_type", "doc_type")
    search_fields = ("title", "model_code", "keywords")


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "version", "created_at")


@admin.register(DocumentContent)
class DocumentContentAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "parse_status", "page_count")


@admin.register(UserFavorite)
class UserFavoriteAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "document")
