"""Django 项目根路由（前后端分离，仅提供 API）"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls_auth")),
    path("api/accounts/", include("accounts.urls")),
    path("api/catalog/", include("catalog.urls")),
    path("api/documents/", include("documents.urls")),
    path("api/search/", include("search.urls")),
    path("api/rag/", include("rag.urls")),
]
