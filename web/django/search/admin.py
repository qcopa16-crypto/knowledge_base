from django.contrib import admin

from search.models import DocumentLog, SearchLog


@admin.register(SearchLog)
class SearchLogAdmin(admin.ModelAdmin):
    list_display = ("id", "keyword", "result_count", "user", "created_at")


@admin.register(DocumentLog)
class DocumentLogAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "user", "action", "created_at")
